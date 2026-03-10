"""
Gmail API Router - OAuth and sync endpoints

Stage 2 Epic 1.3 Implementation:
- S1-07: Connect Gmail via OAuth
- S1-08: Import Gmail filters
- S1-09: 15-minute automatic sync
- S1-10: Sync status dashboard

Endpoints:
- POST /api/gmail/auth/exchange - Exchange OAuth code for tokens
- GET /api/gmail/auth/status/{user_id} - Check connection status
- DELETE /api/gmail/auth/disconnect/{user_id} - Revoke connection
- POST /api/gmail/{user_id}/sync - Trigger manual sync
- GET /api/gmail/{user_id}/sync-status - Get sync status
- GET /api/gmail/{user_id}/filters - Get imported filters
- POST /api/gmail/{user_id}/import-filters - Import filters from Gmail
- POST /api/gmail/extend-mailbox - Extend archive mailbox with LIVE sync
- POST /api/gmail/cron-sync - External cron endpoint to trigger sync
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import logging
import os
from ..dependencies.auth import get_current_user
from ..utils.audit import log_audit, audit_from_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/gmail", tags=["gmail"])

# Dependencies injected from main.py
_supabase = None
_sync_service = None


def init_gmail_router(supabase_client, sync_service=None):
    """
    Initialize the router with dependencies

    Args:
        supabase_client: Supabase client instance
        sync_service: GmailSyncService instance
    """
    global _supabase, _sync_service
    _supabase = supabase_client
    _sync_service = sync_service


# =========================================================================
# Request/Response Models
# =========================================================================

class GmailOAuthRequest(BaseModel):
    code: str
    user_id: str


class SyncStatusResponse(BaseModel):
    user_id: str
    connected: bool
    last_sync_at: Optional[str] = None
    sync_status: str = "disconnected"
    email_count: int = 0
    error: Optional[str] = None


class GmailFilterResponse(BaseModel):
    id: str
    filter_id: str
    criteria: Dict[str, Any]
    action: Dict[str, Any]
    is_active: bool


class ExtendMailboxRequest(BaseModel):
    mailbox_id: str
    user_id: str


class DateRangeFetchRequest(BaseModel):
    mailbox_id: str
    user_id: str
    start_date: str  # YYYY-MM-DD format
    end_date: str    # YYYY-MM-DD format
    max_emails: Optional[int] = None


class GmailConfigUpdate(BaseModel):
    sync_interval_minutes: Optional[int] = None


class MailboxGmailConnectRequest(BaseModel):
    code: str  # OAuth authorization code


class MailboxGmailStatusResponse(BaseModel):
    connected: bool
    gmail_email: Optional[str] = None
    last_sync_at: Optional[str] = None
    sync_status: str = "disconnected"
    email_count: int = 0
    error: Optional[str] = None


# =========================================================================
# Helper Functions
# =========================================================================

def _get_config_from_db() -> Dict[str, Any]:
    """Get Gmail config from database with fallback to env vars"""
    config = {
        'sync_interval_minutes': int(os.getenv('GMAIL_SYNC_INTERVAL_MINUTES', '15')),
    }

    try:
        if _supabase:
            result = _supabase.table('app_config').select('*').eq(
                'config_key', 'gmail_sync_interval'
            ).execute()

            if result.data:
                db_interval = result.data[0].get('config_value')
                if db_interval:
                    config['sync_interval_minutes'] = int(db_interval)
    except Exception as e:
        logger.debug(f"Config table not available, using env var: {e}")

    return config


def _save_config_to_db(key: str, value: Any) -> bool:
    """Save config value to database"""
    try:
        if not _supabase:
            return False

        # Try upsert
        _supabase.table('app_config').upsert({
            'config_key': key,
            'config_value': str(value),
            'updated_at': datetime.now(timezone.utc).isoformat()
        }, on_conflict='config_key').execute()

        return True
    except Exception as e:
        logger.error(f"Failed to save config: {e}")
        return False


# =========================================================================
# OAuth Endpoints (S1-07)
# =========================================================================

@router.post("/auth/exchange")
async def exchange_gmail_oauth_code(request: GmailOAuthRequest):
    """
    Exchange OAuth2 authorization code for tokens and store

    This enables Gmail account connection (S1-07)

    Args:
        request: Contains OAuth code and user_id

    Returns:
        Success status with user info
    """
    try:
        logger.info(f"Starting Gmail OAuth exchange for user: {request.user_id}")

        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")

        if not client_id or not client_secret:
            raise HTTPException(
                status_code=500,
                detail="Missing Google OAuth credentials in environment"
            )

        # Required scopes we need for Gmail operations
        required_scopes = {
            'https://www.googleapis.com/auth/gmail.readonly',
            'https://www.googleapis.com/auth/gmail.settings.basic',
        }

        # Exchange authorization code for tokens using direct HTTP request
        # This avoids the google-auth-oauthlib library's strict scope validation
        # which fails when Google returns additional previously-authorized scopes
        import requests as http_requests

        token_response = http_requests.post(
            'https://oauth2.googleapis.com/token',
            data={
                'code': request.code,
                'client_id': client_id,
                'client_secret': client_secret,
                'redirect_uri': 'postmessage',
                'grant_type': 'authorization_code'
            }
        )

        if token_response.status_code != 200:
            error_data = token_response.json()
            logger.error(f"Token exchange failed: {error_data}")
            raise HTTPException(
                status_code=400,
                detail=f"Token exchange failed: {error_data.get('error_description', error_data.get('error', 'Unknown error'))}"
            )

        token_data = token_response.json()
        access_token = token_data.get('access_token')
        refresh_token = token_data.get('refresh_token', '')
        expires_in = token_data.get('expires_in', 3600)
        granted_scope = token_data.get('scope', '')

        if not access_token:
            raise HTTPException(status_code=400, detail="No access token received from Google")

        # Verify we have required scopes (allow additional scopes)
        granted_scopes = set(granted_scope.split()) if granted_scope else set()
        missing_scopes = required_scopes - granted_scopes

        if missing_scopes:
            logger.warning(f"Missing required scopes: {missing_scopes}. Granted: {granted_scopes}")
            raise HTTPException(
                status_code=400,
                detail=f"Missing required Gmail permissions. Please re-authorize with full permissions."
            )

        logger.info(f"Token exchange successful. Granted scopes: {granted_scopes}")

        # Calculate expiry time
        from datetime import timedelta
        expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        # Get user email from Gmail using the access token
        from googleapiclient.discovery import build
        from google.oauth2.credentials import Credentials

        credentials = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=client_id,
            client_secret=client_secret
        )

        service = build('gmail', 'v1', credentials=credentials)
        profile = service.users().getProfile(userId='me').execute()
        gmail_email = profile.get('emailAddress', '')

        # Store tokens in user_integrations
        integration_data = {
            'user_id': request.user_id,
            'provider': 'gmail',
            'access_token': access_token,
            'refresh_token': refresh_token or '',
            'token_expires_at': expiry.isoformat() if expiry else None,
            'sync_status': 'idle',
            'email_count': 0,
            'updated_at': datetime.now(timezone.utc).isoformat()
        }

        # Check if exists
        existing = _supabase.table('user_integrations').select('id').eq(
            'user_id', request.user_id
        ).eq('provider', 'gmail').execute()

        if existing.data:
            _supabase.table('user_integrations').update(integration_data).eq(
                'user_id', request.user_id
            ).eq('provider', 'gmail').execute()
            logger.info(f"Updated Gmail tokens for user: {request.user_id}")
        else:
            integration_data['created_at'] = datetime.now(timezone.utc).isoformat()
            _supabase.table('user_integrations').insert(integration_data).execute()
            logger.info(f"Stored Gmail tokens for new user: {request.user_id}")

        return {
            "status": "success",
            "message": "Gmail connected successfully",
            "user_id": request.user_id,
            "gmail_email": gmail_email
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Gmail OAuth exchange failed: {e}")
        raise HTTPException(status_code=400, detail=f"OAuth failed: {str(e)}")


@router.get("/auth/status/{user_id}")
async def get_gmail_connection_status(user_id: str) -> SyncStatusResponse:
    """
    Check if user has connected Gmail (S1-07, S1-10)

    Args:
        user_id: User identifier

    Returns:
        Connection and sync status
    """
    try:
        result = _supabase.table('user_integrations').select(
            'access_token, last_sync_at, sync_status, email_count, sync_error'
        ).eq('user_id', user_id).eq('provider', 'gmail').execute()

        if result.data:
            data = result.data[0]
            return SyncStatusResponse(
                user_id=user_id,
                connected=True,
                last_sync_at=data.get('last_sync_at'),
                sync_status=data.get('sync_status', 'idle'),
                email_count=data.get('email_count', 0),
                error=data.get('sync_error')
            )

        return SyncStatusResponse(
            user_id=user_id,
            connected=False,
            sync_status='disconnected',
            email_count=0
        )

    except Exception as e:
        logger.error(f"Failed to check Gmail status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/auth/disconnect/{user_id}")
async def disconnect_gmail(user_id: str):
    """
    Disconnect Gmail integration

    Args:
        user_id: User identifier

    Returns:
        Success status
    """
    try:
        # Delete integration record
        _supabase.table('user_integrations').delete().eq(
            'user_id', user_id
        ).eq('provider', 'gmail').execute()

        # Also delete imported filters
        _supabase.table('gmail_filters').delete().eq('user_id', user_id).execute()

        logger.info(f"Gmail disconnected for user: {user_id}")

        return {
            "status": "success",
            "message": "Gmail disconnected successfully"
        }

    except Exception as e:
        logger.error(f"Failed to disconnect Gmail: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================================
# Sync Endpoints (S1-09, S1-10)
# =========================================================================

@router.post("/{user_id}/sync")
async def trigger_gmail_sync(user_id: str, background_tasks: BackgroundTasks):
    """
    Manually trigger Gmail sync for a user

    Args:
        user_id: User identifier
        background_tasks: FastAPI background tasks

    Returns:
        Sync started status
    """
    try:
        if not _sync_service:
            raise HTTPException(status_code=503, detail="Sync service not available")

        # Run sync in background
        background_tasks.add_task(_run_sync, user_id)

        return {
            "status": "started",
            "message": "Gmail sync started in background"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to trigger sync: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _run_sync(user_id: str):
    """Background task wrapper for sync"""
    try:
        await _sync_service.trigger_sync(user_id)
    except Exception as e:
        logger.error(f"Background sync failed for {user_id}: {e}")


@router.get("/{user_id}/sync-status")
async def get_sync_status(user_id: str):
    """
    Get detailed sync status for dashboard (S1-10)

    Args:
        user_id: User identifier

    Returns:
        Detailed sync status with recent jobs
    """
    try:
        # Get integration status
        integration = _supabase.table('user_integrations').select('*').eq(
            'user_id', user_id
        ).eq('provider', 'gmail').execute()

        if not integration.data:
            return {"connected": False}

        data = integration.data[0]

        # Get recent sync jobs
        jobs = _supabase.table('processing_jobs').select(
            'id, status, processed_records, failed_records, started_at, completed_at'
        ).eq('job_type', 'gmail_sync').order(
            'created_at', desc=True
        ).limit(5).execute()

        return {
            "connected": True,
            "last_sync_at": data.get('last_sync_at'),
            "sync_status": data.get('sync_status', 'idle'),
            "email_count": data.get('email_count', 0),
            "error": data.get('sync_error'),
            "recent_syncs": jobs.data or []
        }

    except Exception as e:
        logger.error(f"Failed to get sync status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================================
# Filter Endpoints (S1-08)
# =========================================================================

@router.get("/{user_id}/filters")
async def get_gmail_filters(user_id: str):
    """
    Get imported Gmail filters for a user

    Args:
        user_id: User identifier

    Returns:
        List of imported filters
    """
    try:
        result = _supabase.table('gmail_filters').select('*').eq(
            'user_id', user_id
        ).execute()

        return {
            "filters": result.data or [],
            "count": len(result.data or [])
        }

    except Exception as e:
        logger.error(f"Failed to get filters: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{user_id}/import-filters")
async def import_gmail_filters(user_id: str):
    """
    Import filters from Gmail (S1-08)

    Args:
        user_id: User identifier

    Returns:
        Imported filters with count
    """
    try:
        if not _sync_service:
            raise HTTPException(status_code=503, detail="Sync service not available")

        filters = await _sync_service.import_filters(user_id)

        return {
            "status": "success",
            "imported_count": len(filters),
            "filters": filters
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to import filters: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================================
# Mailbox Extension Endpoint
# =========================================================================

@router.post("/extend-mailbox")
async def extend_mailbox_with_gmail(request: ExtendMailboxRequest):
    """
    Extend an existing archive-based mailbox with LIVE Gmail sync

    This allows users who imported historical emails from MBOX/PST/OLM
    to keep the mailbox synced with new emails from Gmail.

    Args:
        request: Contains mailbox_id and user_id

    Returns:
        Updated mailbox record
    """
    try:
        if not _sync_service:
            raise HTTPException(status_code=503, detail="Sync service not available")

        result = await _sync_service.extend_mailbox_with_gmail(
            request.mailbox_id,
            request.user_id
        )

        return {
            "status": "success",
            "message": "Mailbox extended with Gmail LIVE sync",
            "mailbox": result
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to extend mailbox: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================================
# Date Range Fetch Endpoint
# =========================================================================

@router.post("/fetch-date-range")
async def fetch_emails_by_date_range(
    request: DateRangeFetchRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """
    Fetch emails from Gmail for a specific date range.

    This allows pulling historical emails on-demand without processing
    entire archive files. Useful for:
    - Getting older emails selectively
    - Filling gaps in email history
    - Investigation of specific time periods

    Args:
        request: Contains mailbox_id, user_id, start_date, end_date, max_emails
        current_user: Authenticated user (injected by dependency)

    Returns:
        Job ID and status for tracking the fetch progress

    Security:
        - Admins can fetch from any mailbox
        - Non-admins can only fetch from mailboxes they own
    """
    try:
        # Validate mailbox exists and has Gmail LIVE sync enabled
        mailbox = _supabase.table('mailboxes').select('*').eq(
            'id', request.mailbox_id
        ).execute()

        if not mailbox.data:
            raise HTTPException(status_code=404, detail="Mailbox not found")

        mailbox_data = mailbox.data[0]
        connection_config = mailbox_data.get('connection_config', {}) or {}

        if not connection_config.get('gmail_sync_enabled'):
            raise HTTPException(
                status_code=400,
                detail="Mailbox does not have Gmail LIVE sync enabled. Please link Gmail first."
            )

        # Check user ID matches - unless user is admin
        gmail_user_id = connection_config.get('gmail_user_id')
        is_admin = 'admin' in current_user.get('roles', [])

        if not is_admin and gmail_user_id != current_user['user_id']:
            raise HTTPException(
                status_code=403,
                detail="User ID does not match the Gmail account linked to this mailbox"
            )

        # Validate dates
        try:
            from datetime import datetime as dt
            start = dt.strptime(request.start_date, '%Y-%m-%d')
            end = dt.strptime(request.end_date, '%Y-%m-%d')
            if start > end:
                raise HTTPException(status_code=400, detail="Start date must be before end date")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid date format. Use YYYY-MM-DD. Error: {e}")

        # Create a processing job to track progress
        job_data = {
            'mailbox_id': request.mailbox_id,
            'job_type': 'gmail_date_range_fetch',
            'status': 'pending',
            'processed_records': 0,
            'failed_records': 0,
            'total_records': 0,
            'filter_start_date': f"{request.start_date}T00:00:00Z",
            'filter_end_date': f"{request.end_date}T23:59:59Z",
            'created_at': datetime.now(timezone.utc).isoformat()
        }

        job_result = _supabase.table('processing_jobs').insert(job_data).execute()
        job_id = job_result.data[0]['id']

        # Run the fetch in background
        background_tasks.add_task(
            _run_date_range_fetch,
            job_id,
            request.mailbox_id,
            request.user_id,
            request.start_date,
            request.end_date,
            request.max_emails
        )

        return {
            "status": "started",
            "message": f"Fetching emails from {request.start_date} to {request.end_date}",
            "job_id": job_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start date range fetch: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _run_date_range_fetch(
    job_id: str,
    mailbox_id: str,
    user_id: str,
    start_date: str,
    end_date: str,
    max_emails: Optional[int]
):
    """Background task to fetch emails by date range (runs in thread pool)"""
    try:
        from src.extractors.gmail_extractor import GmailExtractor
        from src.database.operations import EmailOperations

        # Update job status to running
        _supabase.table('processing_jobs').update({
            'status': 'running',
            'started_at': datetime.now(timezone.utc).isoformat()
        }).eq('id', job_id).execute()

        # Get Gmail credentials from mailbox connection_config
        mailbox = _supabase.table('mailboxes').select('connection_config').eq('id', mailbox_id).execute()

        if not mailbox.data:
            raise ValueError("Mailbox not found")

        connection_config = mailbox.data[0].get('connection_config', {}) or {}

        if not connection_config.get('gmail_sync_enabled'):
            raise ValueError("Gmail not connected for this mailbox")

        access_token = connection_config.get('gmail_access_token')
        refresh_token = connection_config.get('gmail_refresh_token')

        if not access_token:
            raise ValueError("Gmail access token not found in mailbox configuration")

        # Create and connect Gmail extractor
        extractor = GmailExtractor(connection_config={
            'user_id': user_id,
            'access_token': access_token,
            'refresh_token': refresh_token,
            'mailbox_id': mailbox_id
        })
        extractor.connect()

        # Initialize email operations for batch insert
        email_ops = EmailOperations(mailbox_id=mailbox_id)

        # Fetch emails
        processed = 0
        failed = 0
        batch = []
        BATCH_SIZE = 100

        for email_dict in extractor.extract_emails_by_date_range(
            start_date=start_date,
            end_date=end_date,
            max_emails=max_emails
        ):
            try:
                batch.append(email_dict)
                processed += 1

                # Store in batches
                if len(batch) >= BATCH_SIZE:
                    result = email_ops.batch_insert_emails(batch, mailbox_id, batch_size=BATCH_SIZE)
                    failed += result.get('failed', 0)
                    batch = []

                    # Update progress
                    _supabase.table('processing_jobs').update({
                        'processed_records': processed,
                        'failed_records': failed
                    }).eq('id', job_id).execute()

            except Exception as e:
                logger.warning(f"Failed to process email: {e}")
                failed += 1

        # Store remaining batch
        if batch:
            result = email_ops.batch_insert_emails(batch, mailbox_id, batch_size=len(batch))
            failed += result.get('failed', 0)

        # Update job as completed
        _supabase.table('processing_jobs').update({
            'status': 'completed',
            'processed_records': processed,
            'failed_records': failed,
            'completed_at': datetime.now(timezone.utc).isoformat()
        }).eq('id', job_id).execute()

        # Update mailbox email count
        count_result = _supabase.table('emails').select('id', count='exact').eq(
            'mailbox_id', mailbox_id
        ).execute()
        new_count = count_result.count if count_result.count else 0

        _supabase.table('mailboxes').update({
            'total_emails': new_count
        }).eq('id', mailbox_id).execute()

        logger.info(f"Date range fetch completed: {processed} emails from {start_date} to {end_date}")

        extractor.disconnect()

    except Exception as e:
        logger.error(f"Date range fetch failed for job {job_id}: {e}")
        _supabase.table('processing_jobs').update({
            'status': 'failed',
            'error_log': {'error': str(e)},
            'completed_at': datetime.now(timezone.utc).isoformat()
        }).eq('id', job_id).execute()


# =========================================================================
# Cron Endpoints (for avoiding cold start)
# =========================================================================

@router.post("/cron-sync")
async def cron_trigger_all_syncs(background_tasks: BackgroundTasks, api_key: Optional[str] = None):
    """
    External cron endpoint to trigger sync for all users

    This can be called by an external cron service (e.g., cron-job.org)
    to keep the service warm and trigger syncs on schedule.

    Security: Optionally require an API key via query param

    Args:
        background_tasks: FastAPI background tasks
        api_key: Optional API key for security

    Returns:
        Sync triggered status
    """
    try:
        # Optional: Verify API key if configured
        expected_key = os.getenv("GMAIL_SYNC_API_KEY")
        if expected_key and api_key != expected_key:
            raise HTTPException(status_code=401, detail="Invalid API key")

        if not _sync_service:
            raise HTTPException(status_code=503, detail="Sync service not available")

        # Get all Gmail integrations
        result = _supabase.table('user_integrations').select('user_id').eq(
            'provider', 'gmail'
        ).neq('sync_status', 'error').execute()

        users = result.data or []

        # Trigger sync for each user in background
        for user in users:
            background_tasks.add_task(_run_sync, user['user_id'])

        return {
            "status": "success",
            "message": f"Triggered sync for {len(users)} users",
            "user_count": len(users)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Cron sync trigger failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def gmail_health_check():
    """
    Health check endpoint to keep service warm

    Can be pinged by uptime monitors to prevent cold start
    """
    return {
        "status": "healthy",
        "service": "gmail_sync",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@router.get("/config")
async def get_gmail_config():
    """
    Get Gmail sync configuration

    Returns current sync settings including interval
    """
    config = _get_config_from_db()
    sync_interval = config['sync_interval_minutes']

    # Get current service interval (may differ if not restarted)
    service_interval = _sync_service.sync_interval_minutes if _sync_service else sync_interval

    return {
        "sync_interval_minutes": sync_interval,
        "service_interval_minutes": service_interval,
        "max_emails_per_sync": 500,
        "rate_limit_backoff_minutes": 60,
        "sync_service_running": _sync_service is not None and _sync_service._running if _sync_service else False,
        "interval_synced": sync_interval == service_interval,
        "note": "Use PUT /api/gmail/config to update settings. Changes apply immediately to running service."
    }


@router.put("/config")
async def update_gmail_config(config: GmailConfigUpdate):
    """
    Update Gmail sync configuration

    Args:
        config: Configuration updates

    Returns:
        Updated configuration
    """
    try:
        updated = {}

        if config.sync_interval_minutes is not None:
            # Validate range
            interval = config.sync_interval_minutes
            if interval < 1 or interval > 1440:
                raise HTTPException(
                    status_code=400,
                    detail="sync_interval_minutes must be between 1 and 1440 (24 hours)"
                )

            # Save to database
            saved = _save_config_to_db('gmail_sync_interval', interval)

            if saved:
                updated['sync_interval_minutes'] = interval

                # Update running service immediately
                if _sync_service:
                    _sync_service.sync_interval_minutes = interval
                    logger.info(f"Updated Gmail sync interval to {interval} minutes (live)")
            else:
                # Fallback: just update the running service
                if _sync_service:
                    _sync_service.sync_interval_minutes = interval
                    updated['sync_interval_minutes'] = interval
                    logger.info(f"Updated Gmail sync interval to {interval} minutes (memory only)")
                else:
                    raise HTTPException(
                        status_code=500,
                        detail="Failed to save config and no sync service running"
                    )

        return {
            "status": "success",
            "message": "Configuration updated",
            "updated": updated,
            "current_config": await get_gmail_config()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================================
# Per-Mailbox Gmail Endpoints (Multi-Gmail Support)
# =========================================================================

@router.post("/mailbox/{mailbox_id}/connect")
async def connect_gmail_to_mailbox(
    mailbox_id: str,
    request: MailboxGmailConnectRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Connect Gmail account directly to a specific mailbox.

    Stores tokens in mailbox.connection_config instead of user_integrations.
    This enables each mailbox to have its own Gmail connection.

    Args:
        mailbox_id: UUID of the mailbox
        request: Contains OAuth authorization code

    Returns:
        Success status with Gmail email
    """
    try:
        logger.info(f"Connecting Gmail to mailbox: {mailbox_id}")

        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")

        if not client_id or not client_secret:
            raise HTTPException(
                status_code=500,
                detail="Missing Google OAuth credentials in environment"
            )

        # Verify mailbox exists
        mailbox_result = _supabase.table('mailboxes').select('id, name, connection_config').eq(
            'id', mailbox_id
        ).execute()

        if not mailbox_result.data:
            raise HTTPException(status_code=404, detail="Mailbox not found")

        existing_config = mailbox_result.data[0].get('connection_config') or {}

        # Exchange authorization code for tokens
        import requests as http_requests

        token_response = http_requests.post(
            'https://oauth2.googleapis.com/token',
            data={
                'code': request.code,
                'client_id': client_id,
                'client_secret': client_secret,
                'redirect_uri': 'postmessage',
                'grant_type': 'authorization_code'
            }
        )

        if token_response.status_code != 200:
            error_data = token_response.json()
            logger.error(f"Token exchange failed: {error_data}")
            raise HTTPException(
                status_code=400,
                detail=f"Token exchange failed: {error_data.get('error_description', error_data.get('error', 'Unknown error'))}"
            )

        token_data = token_response.json()
        access_token = token_data.get('access_token')
        refresh_token = token_data.get('refresh_token', '')
        expires_in = token_data.get('expires_in', 3600)

        if not access_token:
            raise HTTPException(status_code=400, detail="No access token received from Google")

        # Calculate expiry time
        from datetime import timedelta
        expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        # Get Gmail profile
        from googleapiclient.discovery import build
        from google.oauth2.credentials import Credentials

        credentials = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=client_id,
            client_secret=client_secret
        )

        service = build('gmail', 'v1', credentials=credentials)
        profile = service.users().getProfile(userId='me').execute()
        gmail_email = profile.get('emailAddress', '')
        history_id = profile.get('historyId', '')

        # Build Gmail config for mailbox
        gmail_config = {
            'gmail_sync_enabled': True,
            'gmail_user_id': current_user['user_id'],  # Store authenticated user ID
            'gmail_email': gmail_email,
            'gmail_access_token': access_token,
            'gmail_refresh_token': refresh_token,
            'gmail_token_expires_at': expiry.isoformat(),
            'gmail_last_history_id': history_id,
            'gmail_sync_status': 'idle',
            'gmail_sync_error': None,
            'gmail_email_count': existing_config.get('gmail_email_count', 0),
            'gmail_connected_at': datetime.now(timezone.utc).isoformat()
        }

        # Merge with existing connection_config
        updated_config = {**existing_config, **gmail_config}

        # Update mailbox
        _supabase.table('mailboxes').update({
            'connection_config': updated_config
        }).eq('id', mailbox_id).execute()

        logger.info(f"Gmail {gmail_email} connected to mailbox {mailbox_id}")

        return {
            "success": True,
            "gmail_email": gmail_email,
            "message": f"Gmail {gmail_email} connected to mailbox"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to connect Gmail to mailbox: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/mailbox/{mailbox_id}/disconnect")
async def disconnect_gmail_from_mailbox(mailbox_id: str):
    """
    Remove Gmail connection from a specific mailbox.

    Clears Gmail-related fields from mailbox.connection_config.

    Args:
        mailbox_id: UUID of the mailbox

    Returns:
        Success status
    """
    try:
        # Get current config
        result = _supabase.table('mailboxes').select('connection_config').eq(
            'id', mailbox_id
        ).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Mailbox not found")

        config = result.data[0].get('connection_config') or {}

        # Remove all gmail_ prefixed keys
        cleaned_config = {k: v for k, v in config.items() if not k.startswith('gmail_')}

        # Update mailbox
        _supabase.table('mailboxes').update({
            'connection_config': cleaned_config
        }).eq('id', mailbox_id).execute()

        logger.info(f"Gmail disconnected from mailbox {mailbox_id}")

        return {
            "success": True,
            "message": "Gmail disconnected from mailbox"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to disconnect Gmail from mailbox: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mailbox/{mailbox_id}/status")
async def get_mailbox_gmail_status(mailbox_id: str) -> MailboxGmailStatusResponse:
    """
    Get Gmail sync status for a specific mailbox.

    Args:
        mailbox_id: UUID of the mailbox

    Returns:
        Gmail connection and sync status
    """
    try:
        result = _supabase.table('mailboxes').select('connection_config').eq(
            'id', mailbox_id
        ).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Mailbox not found")

        config = result.data[0].get('connection_config') or {}

        if not config.get('gmail_sync_enabled') or not config.get('gmail_access_token'):
            return MailboxGmailStatusResponse(connected=False)

        return MailboxGmailStatusResponse(
            connected=True,
            gmail_email=config.get('gmail_email'),
            last_sync_at=config.get('gmail_last_sync_at'),
            sync_status=config.get('gmail_sync_status', 'idle'),
            email_count=config.get('gmail_email_count', 0),
            error=config.get('gmail_sync_error')
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get mailbox Gmail status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mailbox/{mailbox_id}/sync")
async def trigger_mailbox_gmail_sync(mailbox_id: str, background_tasks: BackgroundTasks, current_user: dict = Depends(get_current_user)):
    """
    Manually trigger Gmail sync for a specific mailbox.

    Args:
        mailbox_id: UUID of the mailbox
        background_tasks: FastAPI background tasks

    Returns:
        Sync started status
    """
    try:
        if not _sync_service:
            raise HTTPException(status_code=503, detail="Sync service not available")

        # Verify mailbox has Gmail connected
        result = _supabase.table('mailboxes').select('connection_config').eq(
            'id', mailbox_id
        ).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Mailbox not found")

        config = result.data[0].get('connection_config') or {}

        if not config.get('gmail_sync_enabled') or not config.get('gmail_access_token'):
            raise HTTPException(status_code=400, detail="Mailbox does not have Gmail connected")

        # Run sync in background
        background_tasks.add_task(_run_mailbox_sync, mailbox_id)
        audit_from_user(current_user, "sync", "mailbox", resource_id=mailbox_id, details={"provider": "gmail"})

        return {
            "status": "started",
            "message": "Gmail sync started for mailbox"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to trigger mailbox sync: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _run_mailbox_sync(mailbox_id: str):
    """Background task wrapper for mailbox sync"""
    try:
        await _sync_service.trigger_mailbox_sync(mailbox_id)
    except Exception as e:
        logger.error(f"Background mailbox sync failed for {mailbox_id}: {e}")
