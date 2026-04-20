"""
Gmail Sync Service - Handles Gmail synchronization via external cron

Features:
- Incremental sync using Gmail historyId
- Support for extending archive-based mailboxes with LIVE sync
- Token refresh handling
- Error recovery with exponential backoff
- Sync status tracking in database
- Per-mailbox interval checking (via connection_config.sync_interval_minutes)

Triggered by: Railway cron calling POST /api/internal/jobs/gmail-sync

This service supports two modes:
1. Pure Gmail mailbox - Created fresh via OAuth connection
2. Extended mailbox - Archive file (MBOX/PST/OLM) + LIVE Gmail sync
   (e.g., user imports historical archive, then connects Gmail for ongoing sync)
"""

import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Any
from concurrent.futures import ThreadPoolExecutor
import traceback

logger = logging.getLogger(__name__)

class GmailSyncService:
    """
    Service for Gmail synchronization

    Responsibilities:
    - Sync all connected Gmail accounts when triggered by external cron
    - Optional per-mailbox throttle via connection_config.sync_interval_minutes
      (if not set, syncs on every cron tick — cron schedule is the interval)
    - Track sync state per user in user_integrations table
    - Handle rate limits and errors with exponential backoff
    - Update sync status in database
    - Support extending existing mailboxes with LIVE sync
    """

    MAX_EMAILS_PER_SYNC = 500  # Limit per sync to avoid rate limits
    RATE_LIMIT_BACKOFF_MINUTES = 60
    MAX_CONSECUTIVE_ERRORS = 3  # After this, skip until manual intervention

    def __init__(self, supabase_client=None):
        self._supabase = supabase_client
        self.executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="gmail_sync")
        self._active_syncs = {}

    @property
    def supabase(self):
        if self._supabase is None:
            from ..database.supabase_client import SupabaseClient
            self._supabase = SupabaseClient.get_client(use_service_key=True)
        return self._supabase

    async def stop(self):
        self.executor.shutdown(wait=False)
        logger.info("Gmail sync service stopped")

    async def _sync_all_mailboxes(self):
        """
        Sync all mailboxes that have Gmail tokens stored directly in connection_config.
        This is the new per-mailbox approach where each mailbox has its own Gmail connection.
        """
        try:
            # Get all mailboxes
            result = self.supabase.table('mailboxes').select('*').execute()

            gmail_mailboxes = []
            for mailbox in (result.data or []):
                config = mailbox.get('connection_config') or {}
                # Check for per-mailbox Gmail tokens (new approach)
                if config.get('gmail_sync_enabled') and config.get('gmail_access_token'):
                    gmail_mailboxes.append(mailbox)

            if gmail_mailboxes:
                logger.info(f"Found {len(gmail_mailboxes)} mailboxes with per-mailbox Gmail sync")

            for mailbox in gmail_mailboxes:
                mailbox_id = mailbox['id']

                # Skip if currently syncing
                sync_key = f"mailbox:{mailbox_id}"
                if sync_key in self._active_syncs:
                    logger.debug(f"Skipping mailbox {mailbox_id} - sync already in progress")
                    continue

                config = mailbox.get('connection_config') or {}

                # Skip if auth has expired - requires user to reconnect (no retry loop)
                if config.get('gmail_sync_status') == 'auth_expired':
                    logger.debug(f"Skipping mailbox {mailbox_id} - authentication expired, user reconnection required")
                    continue

                # Per-mailbox interval throttle (optional — if not set, syncs every cron tick)
                mailbox_interval = config.get('sync_interval_minutes')
                if mailbox_interval:
                    last_sync = config.get('gmail_last_sync_at') or mailbox.get('last_sync_at')
                    if last_sync:
                        last_sync_dt = datetime.fromisoformat(last_sync.replace('Z', '+00:00'))
                        next_due_at = last_sync_dt + timedelta(minutes=mailbox_interval)
                        if datetime.now(timezone.utc) < next_due_at:
                            logger.debug(
                                f"Skipping mailbox {mailbox_id} - last synced {last_sync_dt.strftime('%H:%M:%S')}, "
                                f"next due at {next_due_at.strftime('%H:%M:%S')}"
                            )
                            continue

                # Skip if in transient error state and not enough time has passed
                if config.get('gmail_sync_status') == 'error':
                    last_sync_err = config.get('gmail_last_sync_at')
                    if last_sync_err:
                        last_sync_dt = datetime.fromisoformat(last_sync_err.replace('Z', '+00:00'))
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

    def _sync_mailbox_blocking(self, config: Dict, mailbox_id: str) -> Dict:
        """
        Blocking I/O for Gmail sync — runs in thread pool so it doesn't starve the event loop.

        Returns dict with success_count, failed_count, history_id, refreshed_tokens, auth_error.
        """
        from ..extractors.gmail_extractor import GmailExtractor
        from ..database.operations import EmailOperations

        extractor = GmailExtractor({
            'access_token': config['gmail_access_token'],
            'refresh_token': config.get('gmail_refresh_token'),
            'history_id': config.get('gmail_last_history_id'),
            'mailbox_id': mailbox_id
        })

        if not extractor.connect():
            if extractor.auth_expired:
                return {'auth_error': extractor.auth_error or 'Refresh token revoked or expired'}
            return {'error': 'Failed to connect to Gmail API'}

        email_ops = EmailOperations()
        success_count = 0
        failed_count = 0
        emails_batch = []
        batch_size = 100

        for email in extractor.extract_emails(max_emails=self.MAX_EMAILS_PER_SYNC):
            emails_batch.append(email)

            if len(emails_batch) >= batch_size:
                result = email_ops.batch_insert_emails(emails_batch, mailbox_id)
                success_count += result.get('success', 0)
                failed_count += result.get('failed', 0)
                emails_batch = []

        if emails_batch:
            result = email_ops.batch_insert_emails(emails_batch, mailbox_id)
            success_count += result.get('success', 0)
            failed_count += result.get('failed', 0)

        history_id = extractor.get_current_history_id()
        refreshed_tokens = extractor.get_refreshed_tokens()
        extractor.disconnect()

        return {
            'success_count': success_count,
            'failed_count': failed_count,
            'history_id': history_id,
            'refreshed_tokens': refreshed_tokens,
        }

    async def _sync_mailbox(self, mailbox: Dict):
        """
        Sync a single mailbox. Delegates blocking I/O to thread pool
        so the event loop stays responsive for HTTP/WebSocket requests.
        """
        mailbox_id = mailbox['id']
        mailbox_name = mailbox.get('name', 'Unknown')
        config = mailbox.get('connection_config') or {}

        logger.info(f"Starting Gmail sync for mailbox: {mailbox_name}", extra={'mailbox_id': mailbox_id})

        try:
            await self._update_mailbox_sync_status(mailbox_id, 'syncing')
            job_id = await self._create_sync_job(mailbox_id)

            # Run all blocking I/O (Gmail API + Supabase) in thread pool
            loop = asyncio.get_event_loop()
            sync_result = await loop.run_in_executor(
                self.executor,
                self._sync_mailbox_blocking,
                config, mailbox_id
            )

            # Handle connection / auth errors from the blocking call
            if sync_result.get('auth_error'):
                raise ConnectionError(f"AUTH_EXPIRED: {sync_result['auth_error']}")
            if sync_result.get('error'):
                raise ConnectionError(sync_result['error'])

            success_count = sync_result['success_count']
            failed_count = sync_result['failed_count']

            if sync_result.get('refreshed_tokens'):
                await self._update_mailbox_tokens(mailbox_id, sync_result['refreshed_tokens'])

            await self._complete_sync_job(job_id, success_count, failed_count)

            await self._update_mailbox_sync_status(
                mailbox_id,
                'idle',
                history_id=sync_result.get('history_id'),
                email_count=success_count
            )

            logger.info(f"Gmail sync completed for mailbox {mailbox_name}: {success_count} emails synced", extra={'mailbox_id': mailbox_id})

            # WORKER MIGRATION 2026-04-17: replaced inline extraction with worker pipeline job.
            # Old code preserved below for one-week rollback window. Remove after 2026-04-24.
            #
            # OLD CODE:
            # await self._trigger_post_sync_extraction(mailbox_id, success_count)
            #
            # NEW CODE:
            if success_count > 0:
                try:
                    from ..services.jobs import create_job, JobSpec, JobAlreadyActive
                    create_job(self.supabase, JobSpec(
                        job_type='email_pipeline',
                        mailbox_id=mailbox_id,
                        client_id=None,  # handler resolves from mailbox row
                        parameters={'trigger_source': 'sync'},
                        triggered_by='sync',
                        max_attempts=1,
                    ))
                    logger.info(f"Pipeline job created for mailbox {mailbox_id}")
                except JobAlreadyActive:
                    logger.info(f"Pipeline already active for mailbox {mailbox_id}, skipping")
                except Exception as e:
                    logger.error(f"Failed to create pipeline job for mailbox {mailbox_id}: {e}", exc_info=True)
                    # Do NOT re-raise — sync should report success even if pipeline trigger fails.

        except Exception as e:
            error_str = str(e)
            is_auth_error = 'AUTH_EXPIRED:' in error_str or any(
                pat in error_str.lower() for pat in ['invalid_grant', 'token has been expired or revoked']
            )
            if is_auth_error:
                user_msg = "Authentication expired. Please reconnect your Gmail account."
                logger.error(f"Gmail auth expired — reconnection required", extra={'mailbox_id': mailbox_id})
                await self._update_mailbox_sync_status(mailbox_id, 'auth_expired', error=user_msg)
            else:
                logger.error(f"Gmail sync failed: {e}", extra={'mailbox_id': mailbox_id})
                logger.error(traceback.format_exc())
                if 'googleapis.com' in error_str:
                    user_error = f"Gmail API error: {error_str[:100]}"
                else:
                    user_error = error_str[:200]
                await self._update_mailbox_sync_status(mailbox_id, 'error', error=user_error)

    # DEPRECATED 2026-04-17 — superseded by email_pipeline worker job. Remove after 2026-04-24 if stable.
    async def _trigger_post_sync_extraction(self, mailbox_id: str, emails_synced: int):
        """Auto-trigger Sprint 2 extraction pipeline after successful sync (fire-and-forget)."""
        if emails_synced == 0:
            logger.info(f"No new emails, skipping extraction", extra={'mailbox_id': mailbox_id})
            return

        # Fire-and-forget: don't block sync completion
        asyncio.create_task(self._run_extraction_background(mailbox_id))

    async def _run_extraction_background(self, mailbox_id: str):
        """Run extraction in a separate executor so it doesn't block sync threads."""
        try:
            from ..services.extraction_orchestrator import ExtractionOrchestrator

            orchestrator = ExtractionOrchestrator(
                mailbox_id=mailbox_id,
                extraction_mode='incremental',
                lookback_days=7,
                use_redis=True,
            )

            # Use a separate single-thread executor so it doesn't compete with sync pool
            extraction_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="extraction")
            try:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    extraction_executor,
                    lambda: orchestrator.run_extraction(
                        exclude_mailing_lists=True,
                        exclude_noreply=True,
                        lightweight=True,  # Skip heavy steps 10-12 during auto-sync
                    )
                )

                if result.get('success'):
                    logger.info(f"Post-sync extraction completed for {mailbox_id}: "
                                f"{result.get('steps_completed', 0)} steps, "
                                f"{result.get('duration_seconds', 0):.1f}s")
                else:
                    logger.warning(f"Post-sync extraction failed for {mailbox_id}: {result.get('error')}")
            finally:
                extraction_executor.shutdown(wait=False)

        except Exception as e:
            logger.error(f"Post-sync extraction error for {mailbox_id}: {e}")

    async def _update_mailbox_sync_status(
        self,
        mailbox_id: str,
        status: str,
        history_id: str = None,
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
            config['gmail_sync_status'] = status
            config['gmail_last_sync_at'] = datetime.now(timezone.utc).isoformat()

            if history_id:
                config['gmail_last_history_id'] = history_id

            if email_count is not None and email_count > 0:
                current_count = config.get('gmail_email_count') or 0
                config['gmail_email_count'] = current_count + email_count

            if status == 'syncing':
                config['gmail_sync_error'] = None
            elif status == 'auth_expired':
                config['gmail_requires_reauth'] = True
                config['gmail_sync_error'] = error[:500] if error else 'Authentication expired'
            elif error:
                config['gmail_sync_error'] = error[:500]
            elif status == 'idle':
                config['gmail_sync_error'] = None
                config['gmail_requires_reauth'] = False

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
            config['gmail_access_token'] = tokens['access_token']
            if tokens.get('refresh_token'):
                config['gmail_refresh_token'] = tokens['refresh_token']

            self.supabase.table('mailboxes').update({
                'connection_config': config
            }).eq('id', mailbox_id).execute()

        except Exception as e:
            logger.error(f"Failed to update mailbox tokens: {e}")

    async def _sync_all_users(self):
        """Sync all users with active Gmail connections (legacy approach via user_integrations)"""
        try:
            # Get all users with Gmail integration that are not in error state
            # or have been in error state long enough for retry
            result = self.supabase.table('user_integrations').select(
                'user_id, access_token, refresh_token, last_history_id, sync_status, sync_error, last_sync_at, email_count'
            ).eq('provider', 'gmail').execute()

            users = result.data or []
            logger.info(f"Found {len(users)} Gmail integrations to check")

            for user in users:
                user_id = user['user_id']

                # Skip if currently syncing
                if user_id in self._active_syncs:
                    logger.debug(f"Skipping {user_id} - sync already in progress")
                    continue

                # Legacy users have no per-user interval — sync on every cron tick

                # Skip if in error state and not enough time has passed
                if user.get('sync_status') == 'error':
                    last_sync_err = user.get('last_sync_at')
                    if last_sync_err:
                        last_sync_dt = datetime.fromisoformat(last_sync_err.replace('Z', '+00:00'))
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
        Sync a single user's Gmail (legacy path).
        Delegates blocking I/O to thread pool.
        """
        user_id = user_data['user_id']
        logger.info(f"Starting Gmail sync for user: {user_id}")

        try:
            await self._update_sync_status(user_id, 'syncing')

            mailbox = await self._get_gmail_mailbox(user_id)
            if not mailbox:
                logger.info(f"Skipping user {user_id} - Gmail connected but no mailbox linked.")
                await self._update_sync_status(user_id, 'idle',
                    error="No mailbox linked. Use 'Link Gmail' on a mailbox to enable sync.")
                return

            job_id = await self._create_sync_job(mailbox['id'])

            # Build config for the blocking call
            extractor_config = {
                'user_id': user_id,
                'access_token': user_data['access_token'],
                'refresh_token': user_data['refresh_token'],
                'history_id': user_data.get('last_history_id'),
                'mailbox_id': mailbox['id'],
                'gmail_access_token': user_data['access_token'],
                'gmail_refresh_token': user_data.get('refresh_token'),
                'gmail_last_history_id': user_data.get('last_history_id'),
            }

            # Run blocking I/O in thread pool
            loop = asyncio.get_event_loop()
            sync_result = await loop.run_in_executor(
                self.executor,
                self._sync_mailbox_blocking,
                extractor_config, mailbox['id']
            )

            if sync_result.get('auth_error'):
                raise ConnectionError(f"AUTH_EXPIRED: {sync_result['auth_error']}")
            if sync_result.get('error'):
                raise ConnectionError(sync_result['error'])

            success_count = sync_result['success_count']

            if sync_result.get('refreshed_tokens'):
                await self._update_tokens(user_id, sync_result['refreshed_tokens'])

            await self._complete_sync_job(job_id, success_count, sync_result['failed_count'])

            await self._update_sync_status(
                user_id,
                'idle',
                history_id=sync_result.get('history_id'),
                email_count=success_count
            )

            logger.info(f"Gmail sync completed for user {user_id}: {success_count} emails synced")

            # WORKER MIGRATION 2026-04-17: replaced inline extraction with worker pipeline job.
            # Old code preserved below for one-week rollback window. Remove after 2026-04-24.
            #
            # OLD CODE:
            # await self._trigger_post_sync_extraction(mailbox['id'], success_count)
            #
            # NEW CODE:
            if success_count > 0:
                try:
                    from ..services.jobs import create_job, JobSpec, JobAlreadyActive
                    create_job(self.supabase, JobSpec(
                        job_type='email_pipeline',
                        mailbox_id=mailbox['id'],
                        client_id=None,  # handler resolves from mailbox row
                        parameters={'trigger_source': 'sync'},
                        triggered_by='sync',
                        max_attempts=1,
                    ))
                    logger.info(f"Pipeline job created for mailbox {mailbox['id']}")
                except JobAlreadyActive:
                    logger.info(f"Pipeline already active for mailbox {mailbox['id']}, skipping")
                except Exception as e:
                    logger.error(f"Failed to create pipeline job for mailbox {mailbox['id']}: {e}", exc_info=True)
                    # Do NOT re-raise — sync should report success even if pipeline trigger fails.

        except Exception as e:
            error_str = str(e)
            is_auth_error = 'AUTH_EXPIRED:' in error_str or any(
                pat in error_str.lower() for pat in ['invalid_grant', 'token has been expired or revoked']
            )
            if is_auth_error:
                user_msg = "Authentication expired. Please reconnect your Gmail account."
                logger.error(f"Gmail auth expired for user {user_id} - user reconnection required")
                await self._update_sync_status(user_id, 'auth_expired', error=user_msg)
            else:
                logger.error(f"Gmail sync failed for user {user_id}: {e}")
                logger.error(traceback.format_exc())
                await self._update_sync_status(user_id, 'error', error=error_str)

    async def _get_gmail_mailbox(self, user_id: str) -> Optional[Dict]:
        """
        Get Gmail mailbox for user

        Looks for:
        1. Mailbox with type 'gmail'
        2. Mailbox with gmail_user_id in connection_config (extended archive mailbox)
        """
        # First, look for pure Gmail mailbox
        result = self.supabase.table('mailboxes').select('*').eq(
            'mailbox_type', 'gmail'
        ).execute()

        for mailbox in (result.data or []):
            config = mailbox.get('connection_config') or {}
            if config.get('user_id') == user_id:
                return mailbox

        # Look for extended mailbox (archive + LIVE sync)
        result = self.supabase.table('mailboxes').select('*').execute()
        for mailbox in (result.data or []):
            config = mailbox.get('connection_config') or {}
            if config.get('gmail_user_id') == user_id and config.get('gmail_sync_enabled'):
                return mailbox

        return None

    async def _create_gmail_mailbox(self, user_id: str) -> Optional[Dict]:
        """Create a new Gmail mailbox for user"""
        try:
            # Get user's Gmail email address
            from ..extractors.gmail_extractor import GmailExtractor

            # Get tokens
            result = self.supabase.table('user_integrations').select(
                'access_token, refresh_token'
            ).eq('user_id', user_id).eq('provider', 'gmail').execute()

            if not result.data:
                return None

            tokens = result.data[0]

            # Create temporary extractor to get email
            extractor = GmailExtractor({
                'user_id': user_id,
                'access_token': tokens['access_token'],
                'refresh_token': tokens['refresh_token']
            })

            if not extractor.connect():
                return None

            gmail_email = extractor.user_email
            extractor.disconnect()

            # Create mailbox
            mailbox_data = {
                'name': f'Gmail - {gmail_email}',
                'email_address': gmail_email,
                'mailbox_type': 'gmail',
                'is_active': True,
                'sync_enabled': True,
                'connection_config': {
                    'user_id': user_id,
                    'provider': 'gmail',
                    'gmail_email': gmail_email
                }
            }

            result = self.supabase.table('mailboxes').insert(mailbox_data).execute()
            return result.data[0] if result.data else None

        except Exception as e:
            logger.error(f"Failed to create Gmail mailbox: {e}")
            return None

    async def _create_sync_job(self, mailbox_id: str) -> str:
        """Create a processing job for the sync"""
        from .jobs import create_job, JobSpec
        try:
            return create_job(self.supabase, JobSpec(
                job_type="gmail_sync",
                mailbox_id=mailbox_id,
                initial_status="running",
                triggered_by="cron",
            ))
        except Exception as e:
            logger.error(f"Failed to create sync job for mailbox {mailbox_id}: {e}")
            return None

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
        history_id: str = None,
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

        if history_id:
            update_data['last_history_id'] = history_id

        if email_count is not None and email_count > 0:
            # Increment email count
            current = self.supabase.table('user_integrations').select('email_count').eq(
                'user_id', user_id
            ).eq('provider', 'gmail').execute()

            if current.data:
                current_count = current.data[0].get('email_count') or 0
                update_data['email_count'] = current_count + email_count

        if error:
            update_data['sync_error'] = error[:500]  # Truncate long errors

        self.supabase.table('user_integrations').update(update_data).eq(
            'user_id', user_id
        ).eq('provider', 'gmail').execute()

    async def _update_tokens(self, user_id: str, tokens: Dict):
        """Update refreshed tokens in database"""
        self.supabase.table('user_integrations').update({
            'access_token': tokens['access_token'],
            'updated_at': datetime.now(timezone.utc).isoformat()
        }).eq('user_id', user_id).eq('provider', 'gmail').execute()

    # =========================================================================
    # Public API Methods
    # =========================================================================

    async def run_cron_sync(self) -> dict:
        """Entry point for external cron. Syncs all due mailboxes and legacy users."""
        await self._sync_all_mailboxes()
        await self._sync_all_users()
        return {"status": "ok"}

    async def trigger_sync(self, user_id: str):
        """
        Manually trigger sync for a user (legacy approach)

        Args:
            user_id: User ID to sync
        """
        result = self.supabase.table('user_integrations').select(
            'user_id, access_token, refresh_token, last_history_id, email_count'
        ).eq('user_id', user_id).eq('provider', 'gmail').execute()

        if result.data:
            await self._sync_user(result.data[0])
        else:
            raise ValueError(f"No Gmail integration found for user {user_id}")

    async def trigger_mailbox_sync(self, mailbox_id: str):
        """
        Manually trigger sync for a specific mailbox using its own Gmail tokens.

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

        if not config.get('gmail_sync_enabled') or not config.get('gmail_access_token'):
            raise ValueError(f"Mailbox {mailbox_id} does not have Gmail connected")

        await self._sync_mailbox(mailbox)

    async def import_filters(self, user_id: str, access_token: str = None, refresh_token: str = None, mailbox_id: str = None) -> List[Dict]:
        """
        Import Gmail filters for a user (S1-08)

        Args:
            user_id: User ID
            access_token: Optional token from mailbox connection_config
            refresh_token: Optional refresh token from mailbox connection_config
            mailbox_id: Optional mailbox ID to link filters to

        Returns:
            List of imported filter records
        """
        # Use provided tokens or look up from user_integrations
        if access_token:
            tokens = {'access_token': access_token, 'refresh_token': refresh_token or ''}
        else:
            result = self.supabase.table('user_integrations').select(
                'access_token, refresh_token'
            ).eq('user_id', user_id).eq('provider', 'gmail').execute()

            if not result.data:
                raise ValueError(f"No Gmail integration found for user {user_id}")

            tokens = result.data[0]

        # Import here to avoid circular imports
        from ..extractors.gmail_extractor import GmailExtractor

        # Create extractor for API access
        extractor = GmailExtractor({
            'user_id': user_id,
            'access_token': tokens['access_token'],
            'refresh_token': tokens['refresh_token']
        })

        if not extractor.connect():
            raise ConnectionError("Failed to connect to Gmail API")

        try:
            # Fetch filters from Gmail
            filters_result = extractor.service.users().settings().filters().list(
                userId='me'
            ).execute()

            gmail_filters = filters_result.get('filter', [])
            imported = []

            for filter_data in gmail_filters:
                filter_record = {
                    'user_id': user_id,
                    'filter_id': filter_data['id'],
                    'criteria': filter_data.get('criteria', {}),
                    'action': filter_data.get('action', {}),
                    'is_active': True,
                    'updated_at': datetime.now(timezone.utc).isoformat()
                }
                if mailbox_id:
                    filter_record['mailbox_id'] = mailbox_id

                # Upsert filter
                self.supabase.table('gmail_filters').upsert(
                    filter_record,
                    on_conflict='user_id,filter_id'
                ).execute()

                imported.append(filter_record)

            logger.info(f"Imported {len(imported)} Gmail filters for user {user_id}")
            return imported

        finally:
            extractor.disconnect()

    async def extend_mailbox_with_gmail(
        self,
        mailbox_id: str,
        user_id: str
    ) -> Dict:
        """
        Extend an existing archive-based mailbox with LIVE Gmail sync

        This allows users who imported historical emails from MBOX/PST/OLM
        to now keep the mailbox synced with new emails from Gmail.

        Key feature: Only syncs NEW emails that aren't already in the archive.
        Uses Gmail's historyId for incremental sync after extension.

        Args:
            mailbox_id: Existing mailbox ID (from archive import)
            user_id: User ID with Gmail integration

        Returns:
            Updated mailbox record
        """
        # Verify Gmail integration exists
        integration = self.supabase.table('user_integrations').select('*').eq(
            'user_id', user_id
        ).eq('provider', 'gmail').execute()

        if not integration.data:
            raise ValueError(f"No Gmail integration found for user {user_id}")

        # Get mailbox
        mailbox = self.supabase.table('mailboxes').select('*').eq(
            'id', mailbox_id
        ).execute()

        if not mailbox.data:
            raise ValueError(f"Mailbox {mailbox_id} not found")

        current_config = mailbox.data[0].get('connection_config') or {}

        # Get current Gmail history ID to start incremental sync from NOW
        # This ensures we only sync NEW emails, not re-import archive ones
        from ..extractors.gmail_extractor import GmailExtractor

        tokens = integration.data[0]
        extractor = GmailExtractor({
            'user_id': user_id,
            'access_token': tokens['access_token'],
            'refresh_token': tokens['refresh_token']
        })

        initial_history_id = None
        gmail_email = None
        if extractor.connect():
            initial_history_id = extractor.get_current_history_id()
            gmail_email = extractor.user_email
            extractor.disconnect()

        # Update mailbox to enable Gmail sync
        updated_config = {
            **current_config,
            'gmail_user_id': user_id,
            'gmail_sync_enabled': True,
            'gmail_email': gmail_email,
            'gmail_extended_at': datetime.now(timezone.utc).isoformat(),
            'original_type': mailbox.data[0].get('mailbox_type'),
            'initial_history_id': initial_history_id  # Start point for LIVE sync
        }

        result = self.supabase.table('mailboxes').update({
            'connection_config': updated_config,
            'sync_enabled': True,
            'updated_at': datetime.now(timezone.utc).isoformat()
        }).eq('id', mailbox_id).execute()

        # Also update the user_integrations with initial history ID
        # This ensures first sync only gets NEW emails
        if initial_history_id:
            self.supabase.table('user_integrations').update({
                'last_history_id': initial_history_id
            }).eq('user_id', user_id).eq('provider', 'gmail').execute()

        logger.info(f"Extended mailbox {mailbox_id} with Gmail LIVE sync for user {user_id}")
        logger.info(f"Starting incremental sync from history ID: {initial_history_id}")

        return result.data[0] if result.data else None

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
        ).eq('user_id', user_id).eq('provider', 'gmail').execute()

        if not result.data:
            return {'connected': False}

        data = result.data[0]
        return {
            'connected': True,
            'sync_status': data.get('sync_status', 'idle'),
            'last_sync_at': data.get('last_sync_at'),
            'email_count': data.get('email_count', 0),
            'error': data.get('sync_error')
        }


# =========================================================================
# Singleton instance management
# =========================================================================

_gmail_sync_service: Optional[GmailSyncService] = None


def get_gmail_sync_service(supabase_client=None) -> GmailSyncService:
    """
    Get or create the Gmail sync service singleton

    Args:
        supabase_client: Optional Supabase client to use

    Returns:
        GmailSyncService instance
    """
    global _gmail_sync_service

    if _gmail_sync_service is None:
        _gmail_sync_service = GmailSyncService(supabase_client)

    return _gmail_sync_service


def reset_gmail_sync_service():
    """Reset the singleton (for testing)"""
    global _gmail_sync_service
    _gmail_sync_service = None
