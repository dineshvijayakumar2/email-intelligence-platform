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

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import logging
import os

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

        # Import Google OAuth flow
        from google_auth_oauthlib.flow import Flow

        # Create OAuth flow with Gmail scopes
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["postmessage"]
                }
            },
            scopes=[
                'https://www.googleapis.com/auth/gmail.readonly',
                'https://www.googleapis.com/auth/gmail.settings.basic',
                'https://www.googleapis.com/auth/userinfo.email',
                'openid'
            ]
        )
        flow.redirect_uri = "postmessage"

        # Exchange code for tokens
        flow.fetch_token(code=request.code)

        access_token = flow.credentials.token
        refresh_token = flow.credentials.refresh_token
        expiry = flow.credentials.expiry

        if not access_token:
            raise HTTPException(status_code=400, detail="No access token received from Google")

        # Get user email from Gmail
        from googleapiclient.discovery import build
        service = build('gmail', 'v1', credentials=flow.credentials)
        profile = service.users().getProfile(userId='me').execute()
        gmail_email = profile.get('emailAddress', '')

        # Store tokens in user_integrations
        token_data = {
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
            _supabase.table('user_integrations').update(token_data).eq(
                'user_id', request.user_id
            ).eq('provider', 'gmail').execute()
            logger.info(f"Updated Gmail tokens for user: {request.user_id}")
        else:
            token_data['created_at'] = datetime.now(timezone.utc).isoformat()
            _supabase.table('user_integrations').insert(token_data).execute()
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
async def fetch_emails_by_date_range(request: DateRangeFetchRequest, background_tasks: BackgroundTasks):
    """
    Fetch emails from Gmail for a specific date range.

    This allows pulling historical emails on-demand without processing
    entire archive files. Useful for:
    - Getting older emails selectively
    - Filling gaps in email history
    - Investigation of specific time periods

    Args:
        request: Contains mailbox_id, user_id, start_date, end_date, max_emails

    Returns:
        Job ID and status for tracking the fetch progress
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

        # Check user ID matches
        gmail_user_id = connection_config.get('gmail_user_id')
        if gmail_user_id != request.user_id:
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

        # Get user's Gmail credentials
        integration = _supabase.table('user_integrations').select(
            'access_token, refresh_token'
        ).eq('user_id', user_id).eq('provider', 'gmail').execute()

        if not integration.data:
            raise ValueError("Gmail not connected for this user")

        token_data = integration.data[0]

        # Create and connect Gmail extractor
        extractor = GmailExtractor(connection_config={
            'user_id': user_id,
            'access_token': token_data['access_token'],
            'refresh_token': token_data.get('refresh_token'),
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
