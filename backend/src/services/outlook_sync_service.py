"""
Outlook Sync Service - Handles periodic Outlook synchronization

Features:
- 15-minute automatic polling interval
- Incremental sync using Microsoft Graph delta queries
- Support for extending archive-based mailboxes with LIVE sync
- Token refresh handling
- Error recovery with exponential backoff
- Sync status tracking in database

This service supports two modes:
1. Pure Outlook mailbox - Created fresh via OAuth connection
2. Extended mailbox - Archive file (MBOX/PST/OLM) + LIVE Outlook sync
   (e.g., user imports historical archive, then connects Outlook for ongoing sync)
"""

import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Any
from concurrent.futures import ThreadPoolExecutor
import traceback

logger = logging.getLogger(__name__)


def _get_sync_interval() -> int:
    """
    Get sync interval from environment variable

    Environment variable: OUTLOOK_SYNC_INTERVAL_MINUTES
    Default: 15 minutes
    Minimum: 1 minute (for testing)
    Maximum: 1440 minutes (24 hours)
    """
    try:
        interval = int(os.getenv('OUTLOOK_SYNC_INTERVAL_MINUTES', '15'))
        # Clamp to reasonable range
        return max(1, min(1440, interval))
    except (ValueError, TypeError):
        return 15


class OutlookSyncService:
    """
    Service for periodic Outlook synchronization

    Responsibilities:
    - Schedule periodic sync jobs for all connected Outlook accounts
    - Sync interval configurable via OUTLOOK_SYNC_INTERVAL_MINUTES env var (default: 15)
    - Track sync state per user in user_integrations table
    - Handle rate limits and errors with exponential backoff
    - Update sync status in database
    - Support extending existing mailboxes with LIVE sync
    """

    MAX_EMAILS_PER_SYNC = 500  # Limit per sync to avoid rate limits
    RATE_LIMIT_BACKOFF_MINUTES = 60
    MAX_CONSECUTIVE_ERRORS = 3  # After this, skip until manual intervention

    def __init__(self, supabase_client=None):
        """
        Initialize the sync service

        Args:
            supabase_client: Supabase client instance (optional, will create if not provided)
        """
        self._supabase = supabase_client
        self.executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="outlook_sync")
        self._running = False
        self._sync_task = None
        self._active_syncs = {}  # user_id/mailbox_id -> sync task
        self.sync_interval_minutes = _get_sync_interval()
        logger.info(f"Outlook sync interval set to {self.sync_interval_minutes} minutes")

    @property
    def supabase(self):
        """Lazy-load Supabase client"""
        if self._supabase is None:
            from ..database.supabase_client import SupabaseClient
            self._supabase = SupabaseClient.get_client(use_service_key=True)
        return self._supabase

    async def start(self):
        """Start the sync service"""
        if self._running:
            logger.warning("Outlook sync service already running")
            return

        self._running = True
        logger.info("Outlook sync service started")

        # Start background sync loop
        self._sync_task = asyncio.create_task(self._sync_loop())

    async def stop(self):
        """Stop the sync service"""
        self._running = False

        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass

        self.executor.shutdown(wait=False)
        logger.info("Outlook sync service stopped")

    async def _sync_loop(self):
        """Main sync loop - runs at configured interval"""
        while self._running:
            try:
                # Sync mailboxes with per-mailbox Outlook tokens (new approach)
                await self._sync_all_mailboxes()
                # Also sync legacy user_integrations-based connections
                await self._sync_all_users()
            except Exception as e:
                logger.error(f"Error in Outlook sync loop: {e}")
                logger.error(traceback.format_exc())

            # Wait for next interval
            logger.debug(f"Next Outlook sync in {self.sync_interval_minutes} minutes")
            await asyncio.sleep(self.sync_interval_minutes * 60)

    async def _sync_all_mailboxes(self):
        """
        Sync all mailboxes that have Outlook tokens stored directly in connection_config.
        This is the new per-mailbox approach where each mailbox has its own Outlook connection.
        """
        try:
            # Get all mailboxes
            result = self.supabase.table('mailboxes').select('*').execute()

            outlook_mailboxes = []
            for mailbox in (result.data or []):
                config = mailbox.get('connection_config') or {}
                # Check for per-mailbox Outlook tokens (new approach)
                if config.get('outlook_sync_enabled') and config.get('outlook_access_token'):
                    outlook_mailboxes.append(mailbox)

            if outlook_mailboxes:
                logger.info(f"Found {len(outlook_mailboxes)} mailboxes with per-mailbox Outlook sync")

            for mailbox in outlook_mailboxes:
                mailbox_id = mailbox['id']

                # Skip if currently syncing
                sync_key = f"mailbox:{mailbox_id}"
                if sync_key in self._active_syncs:
                    logger.debug(f"Skipping mailbox {mailbox_id} - sync already in progress")
                    continue

                config = mailbox.get('connection_config') or {}

                # Skip if auth has expired - requires user to reconnect (no retry loop)
                if config.get('outlook_sync_status') == 'auth_expired':
                    logger.debug(f"Skipping mailbox {mailbox_id} - authentication expired, user reconnection required")
                    continue

                # Skip if in transient error state and not enough time has passed
                if config.get('outlook_sync_status') == 'error':
                    last_sync = config.get('outlook_last_sync_at')
                    if last_sync:
                        last_sync_dt = datetime.fromisoformat(last_sync.replace('Z', '+00:00'))
                        backoff_time = datetime.now(timezone.utc) - timedelta(minutes=self.RATE_LIMIT_BACKOFF_MINUTES)
                        if last_sync_dt > backoff_time:
                            logger.debug(f"Skipping mailbox {mailbox_id} - in error backoff period")
                            continue

                # Run sync in background
                task = asyncio.create_task(self._sync_mailbox(mailbox))
                self._active_syncs[sync_key] = task

                # Clean up completed task
                task.add_done_callback(lambda t, key=sync_key: self._active_syncs.pop(key, None))

        except Exception as e:
            logger.error(f"Failed to fetch mailboxes for sync: {e}")

    async def _sync_mailbox(self, mailbox: Dict):
        """
        Sync a single mailbox using its own Outlook tokens stored in connection_config.

        Args:
            mailbox: Mailbox record with Outlook config in connection_config
        """
        mailbox_id = mailbox['id']
        mailbox_name = mailbox.get('name', 'Unknown')
        config = mailbox.get('connection_config') or {}

        logger.info(f"Starting Outlook sync for mailbox: {mailbox_name} ({mailbox_id})")

        try:
            # Update status to syncing
            await self._update_mailbox_sync_status(mailbox_id, 'syncing')

            # Import here to avoid circular imports
            from ..extractors.outlook_extractor import OutlookExtractor
            from ..database.operations import EmailOperations

            # Create extractor using mailbox's own tokens
            extractor = OutlookExtractor({
                'access_token': config['outlook_access_token'],
                'refresh_token': config.get('outlook_refresh_token'),
                'delta_link': config.get('outlook_delta_link'),
                'folders': ['inbox', 'sentitems'],
                'mailbox_id': mailbox_id
            })

            if not extractor.connect():
                if extractor.auth_expired:
                    raise ConnectionError(f"AUTH_EXPIRED: {extractor.auth_error or 'Refresh token revoked or expired'}")
                raise ConnectionError("Failed to connect to Outlook API")

            # Create processing job
            job_id = await self._create_sync_job(mailbox_id)

            # Process emails using EmailOperations
            email_ops = EmailOperations()
            success_count = 0
            failed_count = 0

            # Extract and insert emails
            emails_batch = []
            batch_size = 100

            for email in extractor.extract_emails(max_emails=self.MAX_EMAILS_PER_SYNC):
                emails_batch.append(email)

                if len(emails_batch) >= batch_size:
                    result = email_ops.batch_insert_emails(emails_batch, mailbox_id)
                    success_count += result.get('success', 0)
                    failed_count += result.get('failed', 0)
                    emails_batch = []

            # Insert remaining emails
            if emails_batch:
                result = email_ops.batch_insert_emails(emails_batch, mailbox_id)
                success_count += result.get('success', 0)
                failed_count += result.get('failed', 0)

            # Update delta link for next incremental sync
            new_delta_link = extractor.get_current_delta_link()

            # Check if tokens were refreshed and update mailbox config
            refreshed_tokens = extractor.get_refreshed_tokens()
            if refreshed_tokens:
                await self._update_mailbox_tokens(mailbox_id, refreshed_tokens)

            # Complete the job
            await self._complete_sync_job(job_id, success_count, failed_count)

            # Update sync status in mailbox config
            await self._update_mailbox_sync_status(
                mailbox_id,
                'idle',
                delta_link=new_delta_link,
                email_count=success_count
            )

            extractor.disconnect()

            logger.info(f"Outlook sync completed for mailbox {mailbox_name}: {success_count} emails synced")

        except Exception as e:
            error_str = str(e)
            is_auth_error = 'AUTH_EXPIRED:' in error_str or any(
                pat in error_str.lower() for pat in [
                    'invalid_grant', 'failed to refresh access token',
                    'aadsts70008', 'aadsts700082', 'aadsts70043'
                ]
            )
            if is_auth_error:
                user_msg = "Authentication expired. Please reconnect your Outlook account."
                logger.error(f"Outlook auth expired for mailbox {mailbox_id} - user reconnection required")
                await self._update_mailbox_sync_status(mailbox_id, 'auth_expired', error=user_msg)
            else:
                logger.error(f"Outlook sync failed for mailbox {mailbox_id}: {e}")
                logger.error(traceback.format_exc())
                await self._update_mailbox_sync_status(mailbox_id, 'error', error=error_str)

    async def _update_mailbox_sync_status(
        self,
        mailbox_id: str,
        status: str,
        delta_link: str = None,
        email_count: int = None,
        error: str = None
    ):
        """Update sync status in mailbox.connection_config"""
        try:
            # Get current config
            result = self.supabase.table('mailboxes').select('connection_config').eq(
                'id', mailbox_id
            ).execute()

            if not result.data:
                return

            config = result.data[0].get('connection_config') or {}

            # Update status fields
            config['outlook_sync_status'] = status
            config['outlook_last_sync_at'] = datetime.now(timezone.utc).isoformat()

            if delta_link:
                config['outlook_delta_link'] = delta_link

            if email_count is not None and email_count > 0:
                current_count = config.get('outlook_email_count') or 0
                config['outlook_email_count'] = current_count + email_count

            if status == 'auth_expired':
                config['outlook_requires_reauth'] = True
                config['outlook_sync_error'] = error[:500] if error else 'Authentication expired'
            elif error:
                config['outlook_sync_error'] = error[:500]  # Truncate long errors
            elif status == 'idle':
                config['outlook_sync_error'] = None
                config['outlook_requires_reauth'] = False

            # Update mailbox
            update_data = {'connection_config': config}
            if status == 'idle':
                update_data['last_sync_at'] = datetime.now(timezone.utc).isoformat()
            self.supabase.table('mailboxes').update(update_data).eq('id', mailbox_id).execute()

        except Exception as e:
            logger.error(f"Failed to update mailbox sync status: {e}")

    async def _update_mailbox_tokens(self, mailbox_id: str, tokens: Dict):
        """Update refreshed tokens in mailbox.connection_config"""
        try:
            result = self.supabase.table('mailboxes').select('connection_config').eq(
                'id', mailbox_id
            ).execute()

            if not result.data:
                return

            config = result.data[0].get('connection_config') or {}
            config['outlook_access_token'] = tokens['access_token']
            if tokens.get('refresh_token'):
                config['outlook_refresh_token'] = tokens['refresh_token']

            self.supabase.table('mailboxes').update({
                'connection_config': config
            }).eq('id', mailbox_id).execute()

        except Exception as e:
            logger.error(f"Failed to update mailbox tokens: {e}")

    async def _sync_all_users(self):
        """Sync all users with active Outlook connections (legacy approach via user_integrations)"""
        try:
            # Get all users with Outlook integration
            result = self.supabase.table('user_integrations').select(
                'user_id, access_token, refresh_token, delta_link, sync_status, sync_error, last_sync_at, email_count'
            ).eq('provider', 'outlook').execute()

            users = result.data or []
            logger.info(f"Found {len(users)} Outlook integrations to check")

            for user in users:
                user_id = user['user_id']

                # Skip if currently syncing
                if user_id in self._active_syncs:
                    logger.debug(f"Skipping {user_id} - sync already in progress")
                    continue

                # Skip if in error state and not enough time has passed
                if user.get('sync_status') == 'error':
                    last_sync = user.get('last_sync_at')
                    if last_sync:
                        last_sync_dt = datetime.fromisoformat(last_sync.replace('Z', '+00:00'))
                        backoff_time = datetime.now(timezone.utc) - timedelta(minutes=self.RATE_LIMIT_BACKOFF_MINUTES)
                        if last_sync_dt > backoff_time:
                            logger.debug(f"Skipping {user_id} - in error backoff period")
                            continue

                # Run sync in background
                task = asyncio.create_task(self._sync_user(user))
                self._active_syncs[user_id] = task

                # Clean up completed task
                task.add_done_callback(lambda t, uid=user_id: self._active_syncs.pop(uid, None))

        except Exception as e:
            logger.error(f"Failed to fetch users for sync: {e}")

    async def _sync_user(self, user_data: Dict):
        """
        Sync a single user's Outlook

        Args:
            user_data: User integration data from database
        """
        user_id = user_data['user_id']
        logger.info(f"Starting Outlook sync for user: {user_id}")

        try:
            # Update status to syncing
            await self._update_sync_status(user_id, 'syncing')

            # Get mailbox for this user
            mailbox = await self._get_outlook_mailbox(user_id)
            if not mailbox:
                logger.info(f"Skipping user {user_id} - Outlook connected but no mailbox linked. "
                           "User needs to link Outlook to a mailbox via the Mailboxes page.")
                await self._update_sync_status(user_id, 'idle',
                    error="No mailbox linked. Use 'Link Outlook' on a mailbox to enable sync.")
                return

            # Import here to avoid circular imports
            from ..extractors.outlook_extractor import OutlookExtractor
            from ..database.operations import EmailOperations

            # Create extractor
            extractor = OutlookExtractor({
                'user_id': user_id,
                'access_token': user_data['access_token'],
                'refresh_token': user_data['refresh_token'],
                'delta_link': user_data.get('delta_link'),
                'folders': ['inbox', 'sentitems'],
                'mailbox_id': mailbox['id']
            })

            if not extractor.connect():
                raise ConnectionError("Failed to connect to Outlook API")

            # Create processing job
            job_id = await self._create_sync_job(mailbox['id'])

            # Process emails using EmailOperations
            email_ops = EmailOperations()
            success_count = 0
            failed_count = 0

            # Extract and insert emails
            emails_batch = []
            batch_size = 100

            for email in extractor.extract_emails(max_emails=self.MAX_EMAILS_PER_SYNC):
                emails_batch.append(email)

                if len(emails_batch) >= batch_size:
                    result = email_ops.batch_insert_emails(emails_batch, mailbox['id'])
                    success_count += result.get('success', 0)
                    failed_count += result.get('failed', 0)
                    emails_batch = []

            # Insert remaining emails
            if emails_batch:
                result = email_ops.batch_insert_emails(emails_batch, mailbox['id'])
                success_count += result.get('success', 0)
                failed_count += result.get('failed', 0)

            # Update delta link for next incremental sync
            new_delta_link = extractor.get_current_delta_link()

            # Check if tokens were refreshed
            refreshed_tokens = extractor.get_refreshed_tokens()
            if refreshed_tokens:
                await self._update_tokens(user_id, refreshed_tokens)

            # Complete the job
            await self._complete_sync_job(job_id, success_count, failed_count)

            # Update sync status
            await self._update_sync_status(
                user_id,
                'idle',
                delta_link=new_delta_link,
                email_count=success_count
            )

            extractor.disconnect()

            logger.info(f"Outlook sync completed for user {user_id}: {success_count} emails synced")

        except Exception as e:
            logger.error(f"Outlook sync failed for user {user_id}: {e}")
            logger.error(traceback.format_exc())
            await self._update_sync_status(user_id, 'error', error=str(e))

    async def _get_outlook_mailbox(self, user_id: str) -> Optional[Dict]:
        """
        Get Outlook mailbox for user

        Looks for:
        1. Mailbox with type 'outlook_live'
        2. Mailbox with outlook_user_id in connection_config (extended archive mailbox)
        """
        # First, look for pure Outlook mailbox
        result = self.supabase.table('mailboxes').select('*').eq(
            'mailbox_type', 'outlook_live'
        ).execute()

        for mailbox in (result.data or []):
            config = mailbox.get('connection_config') or {}
            if config.get('user_id') == user_id:
                return mailbox

        # Look for extended mailbox (archive + LIVE sync)
        result = self.supabase.table('mailboxes').select('*').execute()
        for mailbox in (result.data or []):
            config = mailbox.get('connection_config') or {}
            if config.get('outlook_user_id') == user_id and config.get('outlook_sync_enabled'):
                return mailbox

        return None

    async def _create_sync_job(self, mailbox_id: str) -> Optional[str]:
        """Create a sync job record for tracking"""
        job_data = {
            'job_type': 'outlook_sync',
            'mailbox_id': mailbox_id,
            'status': 'running',
            'processed_records': 0,
            'failed_records': 0,
            'started_at': datetime.now(timezone.utc).isoformat()
        }

        result = self.supabase.table('processing_jobs').insert(job_data).execute()
        return result.data[0]['id'] if result.data else None

    async def _complete_sync_job(self, job_id: str, success: int, failed: int):
        """Mark sync job as completed"""
        if not job_id:
            return

        self.supabase.table('processing_jobs').update({
            'status': 'completed',
            'processed_records': success,
            'failed_records': failed,
            'completed_at': datetime.now(timezone.utc).isoformat()
        }).eq('id', job_id).execute()

    async def _update_sync_status(
        self,
        user_id: str,
        status: str,
        delta_link: str = None,
        email_count: int = None,
        error: str = None
    ):
        """Update sync status in user_integrations table"""
        update_data = {
            'sync_status': status,
            'updated_at': datetime.now(timezone.utc).isoformat()
        }

        if status == 'idle':
            update_data['last_sync_at'] = datetime.now(timezone.utc).isoformat()
            update_data['sync_error'] = None

        if delta_link:
            update_data['delta_link'] = delta_link

        if email_count is not None and email_count > 0:
            # Increment email count
            current = self.supabase.table('user_integrations').select('email_count').eq(
                'user_id', user_id
            ).eq('provider', 'outlook').execute()

            if current.data:
                current_count = current.data[0].get('email_count') or 0
                update_data['email_count'] = current_count + email_count

        if error:
            update_data['sync_error'] = error[:500]  # Truncate long errors

        self.supabase.table('user_integrations').update(update_data).eq(
            'user_id', user_id
        ).eq('provider', 'outlook').execute()

    async def _update_tokens(self, user_id: str, tokens: Dict):
        """Update refreshed tokens in database"""
        update_data = {
            'access_token': tokens['access_token'],
            'updated_at': datetime.now(timezone.utc).isoformat()
        }
        if tokens.get('refresh_token'):
            update_data['refresh_token'] = tokens['refresh_token']

        self.supabase.table('user_integrations').update(update_data).eq(
            'user_id', user_id
        ).eq('provider', 'outlook').execute()

    # =========================================================================
    # Public API Methods
    # =========================================================================

    async def trigger_sync(self, user_id: str):
        """
        Manually trigger sync for a user (legacy approach)

        Args:
            user_id: User ID to sync
        """
        result = self.supabase.table('user_integrations').select(
            'user_id, access_token, refresh_token, delta_link, email_count'
        ).eq('user_id', user_id).eq('provider', 'outlook').execute()

        if result.data:
            await self._sync_user(result.data[0])
        else:
            raise ValueError(f"No Outlook integration found for user {user_id}")

    async def trigger_mailbox_sync(self, mailbox_id: str):
        """
        Manually trigger sync for a specific mailbox using its own Outlook tokens.

        Args:
            mailbox_id: UUID of the mailbox to sync
        """
        result = self.supabase.table('mailboxes').select('*').eq(
            'id', mailbox_id
        ).execute()

        if not result.data:
            raise ValueError(f"Mailbox {mailbox_id} not found")

        mailbox = result.data[0]
        config = mailbox.get('connection_config') or {}

        if not config.get('outlook_sync_enabled') or not config.get('outlook_access_token'):
            raise ValueError(f"Mailbox {mailbox_id} does not have Outlook connected")

        await self._sync_mailbox(mailbox)

    async def extend_mailbox_with_outlook(self, mailbox_id: str, user_id: str) -> Dict:
        """
        Extend an existing archive mailbox with Outlook LIVE sync capability.

        This converts a static imported mailbox (MBOX, PST, OLM) into a hybrid
        that continues receiving new emails from Outlook.

        Args:
            mailbox_id: UUID of the mailbox to extend
            user_id: User ID who owns the Outlook connection

        Returns:
            Updated mailbox details
        """
        # Verify mailbox exists and is an archive type
        mailbox_result = self.supabase.table('mailboxes').select('*').eq(
            'id', mailbox_id
        ).execute()

        if not mailbox_result.data:
            raise ValueError(f"Mailbox {mailbox_id} not found")

        mailbox = mailbox_result.data[0]

        # Only allow extending archive-based mailboxes
        valid_types = ['mbox', 'pst', 'olm']
        if mailbox.get('mailbox_type') not in valid_types:
            raise ValueError(
                f"Can only extend archive mailboxes ({', '.join(valid_types)}). "
                f"Current type: {mailbox.get('mailbox_type')}"
            )

        # Verify user has Outlook connected
        integration_result = self.supabase.table('user_integrations').select(
            'access_token, refresh_token'
        ).eq('user_id', user_id).eq('provider', 'outlook').execute()

        if not integration_result.data:
            raise ValueError(f"No Outlook connection found for user {user_id}")

        # Get current delta link to avoid re-importing old emails
        from ..extractors.outlook_extractor import OutlookExtractor

        tokens = integration_result.data[0]
        extractor = OutlookExtractor({
            'access_token': tokens['access_token'],
            'refresh_token': tokens.get('refresh_token'),
        })

        if extractor.connect():
            # Get current delta link - all emails before this will be skipped
            initial_delta_link = extractor.get_current_delta_link()
            extractor.disconnect()
        else:
            initial_delta_link = None

        # Update mailbox connection_config to enable LIVE sync
        existing_config = mailbox.get('connection_config') or {}
        updated_config = {
            **existing_config,
            'outlook_sync_enabled': True,
            'outlook_user_id': user_id,
            'outlook_extended_at': datetime.now(timezone.utc).isoformat(),
            'original_type': mailbox.get('mailbox_type'),  # Remember original type
            'initial_delta_link': initial_delta_link,  # Sync only new emails
        }

        self.supabase.table('mailboxes').update({
            'connection_config': updated_config
        }).eq('id', mailbox_id).execute()

        logger.info(f"Mailbox {mailbox_id} extended with Outlook LIVE sync for user {user_id}")

        return {
            'success': True,
            'message': f'Mailbox "{mailbox["name"]}" extended with Outlook LIVE sync',
            'mailbox': {
                'id': mailbox_id,
                'name': mailbox['name'],
                'original_type': mailbox['mailbox_type'],
                'outlook_sync_enabled': True
            }
        }

    async def get_sync_status(self, user_id: str) -> Dict:
        """
        Get sync status for a user

        Args:
            user_id: User ID

        Returns:
            Sync status dict
        """
        result = self.supabase.table('user_integrations').select(
            'sync_status, last_sync_at, email_count, sync_error'
        ).eq('user_id', user_id).eq('provider', 'outlook').execute()

        if not result.data:
            return {
                'connected': False,
                'sync_status': 'disconnected'
            }

        data = result.data[0]
        return {
            'connected': True,
            'sync_status': data.get('sync_status', 'idle'),
            'last_sync_at': data.get('last_sync_at'),
            'email_count': data.get('email_count', 0),
            'error': data.get('sync_error')
        }


    # =====================================================================
    # Outlook Inbox Rules Import
    # =====================================================================

    async def import_rules(self, user_id: str = None, mailbox_id: str = None) -> List[Dict]:
        """
        Import inbox rules from Outlook via Microsoft Graph API.

        Supports two modes:
        1. user_id → reads tokens from user_integrations (legacy)
        2. mailbox_id → reads tokens from mailbox connection_config (preferred)

        Returns:
            List of imported rule records
        """
        access_token = None
        refresh_token = None

        if mailbox_id:
            result = self.supabase.table('mailboxes').select(
                'connection_config,user_id'
            ).eq('id', mailbox_id).execute()

            if not result.data:
                raise ValueError(f"Mailbox {mailbox_id} not found")

            mailbox_row = result.data[0]
            config = mailbox_row.get('connection_config') or {}
            if not config.get('outlook_access_token'):
                raise ValueError(f"Mailbox {mailbox_id} does not have Outlook connected")

            access_token = config['outlook_access_token']
            refresh_token = config.get('outlook_refresh_token')
            # Resolve user_id: config > mailbox row > fallback to mailbox_id
            user_id = (
                config.get('outlook_user_id')
                or mailbox_row.get('user_id')
                or user_id
                or mailbox_id
            )

        elif user_id:
            result = self.supabase.table('user_integrations').select(
                'access_token, refresh_token'
            ).eq('user_id', user_id).eq('provider', 'outlook').execute()

            if not result.data:
                raise ValueError(f"No Outlook integration found for user {user_id}")

            access_token = result.data[0]['access_token']
            refresh_token = result.data[0].get('refresh_token')
        else:
            raise ValueError("Either user_id or mailbox_id must be provided")

        # Fetch rules from Microsoft Graph
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
        }

        import requests as http_requests
        response = http_requests.get(
            'https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messageRules',
            headers=headers,
        )

        # If 401, try token refresh
        if response.status_code == 401 and refresh_token:
            logger.info("Token expired, attempting refresh for rules import")
            new_token = self._refresh_token_for_import(refresh_token)
            if new_token:
                access_token = new_token
                headers['Authorization'] = f'Bearer {access_token}'
                response = http_requests.get(
                    'https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messageRules',
                    headers=headers,
                )
                # Update stored token
                if mailbox_id:
                    await self._update_mailbox_token(mailbox_id, access_token)

        response.raise_for_status()
        rules = response.json().get('value', [])
        imported = []

        for rule_data in rules:
            rule_record = {
                'user_id': user_id,
                'rule_id': rule_data['id'],
                'display_name': rule_data.get('displayName', ''),
                'sequence': rule_data.get('sequence', 0),
                'is_enabled': rule_data.get('isEnabled', True),
                'conditions': rule_data.get('conditions') or {},
                'actions': rule_data.get('actions') or {},
                'exceptions': rule_data.get('exceptions') or {},
                'updated_at': datetime.now(timezone.utc).isoformat(),
            }
            if mailbox_id:
                rule_record['mailbox_id'] = mailbox_id

            self.supabase.table('outlook_rules').upsert(
                rule_record,
                on_conflict='user_id,rule_id',
            ).execute()

            imported.append(rule_record)

        logger.info(f"Imported {len(imported)} Outlook rules for user {user_id}")
        return imported

    def _refresh_token_for_import(self, refresh_token: str) -> Optional[str]:
        """Refresh access token for rules import. Returns new access_token or None."""
        try:
            client_id = os.getenv("MICROSOFT_CLIENT_ID")
            client_secret = os.getenv("MICROSOFT_CLIENT_SECRET")
            tenant_id = os.getenv("MICROSOFT_TENANT_ID", "common")

            if not client_id or not client_secret:
                return None

            import requests as http_requests
            token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
            response = http_requests.post(token_url, data={
                'client_id': client_id,
                'client_secret': client_secret,
                'refresh_token': refresh_token,
                'grant_type': 'refresh_token',
                'scope': 'openid profile email offline_access Mail.Read User.Read MailboxSettings.Read',
            })
            response.raise_for_status()
            return response.json().get('access_token')
        except Exception as e:
            logger.error(f"Token refresh failed for rules import: {e}")
            return None

    async def _update_mailbox_token(self, mailbox_id: str, new_token: str):
        """Update the access token in mailbox connection_config after refresh."""
        try:
            result = self.supabase.table('mailboxes').select('connection_config').eq('id', mailbox_id).execute()
            if result.data:
                config = result.data[0].get('connection_config') or {}
                config['outlook_access_token'] = new_token
                self.supabase.table('mailboxes').update({
                    'connection_config': config,
                }).eq('id', mailbox_id).execute()
        except Exception as e:
            logger.warning(f"Failed to update mailbox token: {e}")


# =========================================================================
# Singleton instance management
# =========================================================================

_outlook_sync_service: Optional[OutlookSyncService] = None


def get_outlook_sync_service(supabase_client=None) -> OutlookSyncService:
    """
    Get or create the Outlook sync service singleton

    Args:
        supabase_client: Optional Supabase client to use

    Returns:
        OutlookSyncService instance
    """
    global _outlook_sync_service

    if _outlook_sync_service is None:
        _outlook_sync_service = OutlookSyncService(supabase_client)

    return _outlook_sync_service


def reset_outlook_sync_service():
    """Reset the singleton (for testing)"""
    global _outlook_sync_service
    _outlook_sync_service = None
