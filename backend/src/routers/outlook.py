"""
Outlook API Router - OAuth and sync endpoints

Microsoft Graph API integration for Outlook/O365 LIVE email sync:
- OAuth2 authentication with Microsoft Identity Platform
- Per-user and per-mailbox connections
- Incremental sync using delta queries
- Date range fetch for historical emails

Endpoints:
- POST /api/outlook/auth/exchange - Exchange OAuth code for tokens
- GET /api/outlook/auth/status/{user_id} - Check connection status
- DELETE /api/outlook/auth/disconnect/{user_id} - Revoke connection
- POST /api/outlook/{user_id}/sync - Trigger manual sync
- GET /api/outlook/{user_id}/sync-status - Get sync status
- POST /api/outlook/extend-mailbox - Extend archive mailbox with LIVE sync
- POST /api/outlook/fetch-date-range - Fetch emails by date range
- POST /api/outlook/cron-sync - External cron endpoint to trigger sync
- POST /api/outlook/mailbox/{mailbox_id}/connect - Connect Outlook to mailbox
- DELETE /api/outlook/mailbox/{mailbox_id}/disconnect - Disconnect from mailbox
- GET /api/outlook/mailbox/{mailbox_id}/status - Get mailbox Outlook status
- POST /api/outlook/mailbox/{mailbox_id}/sync - Trigger mailbox sync
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
import logging
import os
from ..dependencies.auth import get_current_user
import requests

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/outlook", tags=["outlook"])

# Dependencies injected from main.py
_supabase = None
_sync_service = None


def init_outlook_router(supabase_client, sync_service=None):
    """
    Initialize the router with dependencies

    Args:
        supabase_client: Supabase client instance
        sync_service: OutlookSyncService instance
    """
    global _supabase, _sync_service
    _supabase = supabase_client
    _sync_service = sync_service


# =========================================================================
# Request/Response Models
# =========================================================================

class OutlookOAuthRequest(BaseModel):
    code: str
    user_id: str
    redirect_uri: str  # Microsoft requires explicit redirect_uri


class SyncStatusResponse(BaseModel):
    user_id: str
    connected: bool
    last_sync_at: Optional[str] = None
    sync_status: str = "disconnected"
    email_count: int = 0
    error: Optional[str] = None


class ExtendMailboxRequest(BaseModel):
    mailbox_id: str
    user_id: str


class DateRangeFetchRequest(BaseModel):
    mailbox_id: str
    user_id: str
    start_date: str  # YYYY-MM-DD format
    end_date: str    # YYYY-MM-DD format
    max_emails: Optional[int] = None


class OutlookConfigUpdate(BaseModel):
    sync_interval_minutes: Optional[int] = None


class MailboxOutlookConnectRequest(BaseModel):
    code: str  # OAuth authorization code
    redirect_uri: str  # Microsoft requires explicit redirect_uri


class MailboxOutlookStatusResponse(BaseModel):
    connected: bool
    outlook_email: Optional[str] = None
    last_sync_at: Optional[str] = None
    sync_status: str = "disconnected"
    email_count: int = 0
    error: Optional[str] = None


# =========================================================================
# Helper Functions
# =========================================================================

def _get_config_from_db() -> Dict[str, Any]:
    """Get Outlook config from database with fallback to env vars"""
    config = {
        'sync_interval_minutes': int(os.getenv('OUTLOOK_SYNC_INTERVAL_MINUTES', '15')),
    }

    try:
        if _supabase:
            result = _supabase.table('app_config').select('*').eq(
                'config_key', 'outlook_sync_interval'
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

        _supabase.table('app_config').upsert({
            'config_key': key,
            'config_value': str(value),
            'updated_at': datetime.now(timezone.utc).isoformat()
        }, on_conflict='config_key').execute()

        return True
    except Exception as e:
        logger.error(f"Failed to save config: {e}")
        return False


def _exchange_code_for_tokens(code: str, redirect_uri: str) -> Dict[str, Any]:
    """
    Exchange OAuth authorization code for tokens via Microsoft Identity Platform

    Args:
        code: Authorization code from OAuth flow
        redirect_uri: Redirect URI used in the authorization request

    Returns:
        Dict with access_token, refresh_token, expires_in

    Raises:
        HTTPException if exchange fails
    """
    client_id = os.getenv("MICROSOFT_CLIENT_ID")
    client_secret = os.getenv("MICROSOFT_CLIENT_SECRET")
    tenant_id = os.getenv("MICROSOFT_TENANT_ID", "common")

    if not client_id or not client_secret:
        raise HTTPException(
            status_code=500,
            detail="Missing Microsoft OAuth credentials in environment"
        )

    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

    token_response = requests.post(
        token_url,
        data={
            'code': code,
            'client_id': client_id,
            'client_secret': client_secret,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code',
            'scope': 'openid profile email offline_access Mail.Read User.Read MailboxSettings.Read'
        }
    )

    if token_response.status_code != 200:
        error_data = token_response.json()
        logger.error(f"Outlook token exchange failed: {error_data}")
        raise HTTPException(
            status_code=400,
            detail=f"Token exchange failed: {error_data.get('error_description', error_data.get('error', 'Unknown error'))}"
        )

    return token_response.json()


def _get_user_profile(access_token: str) -> Dict[str, Any]:
    """
    Get user profile from Microsoft Graph API

    Args:
        access_token: Valid access token

    Returns:
        User profile dict with mail/userPrincipalName

    Raises:
        HTTPException if request fails
    """
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }

    response = requests.get(
        'https://graph.microsoft.com/v1.0/me',
        headers=headers
    )

    if response.status_code != 200:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to get user profile: {response.text}"
        )

    return response.json()


# =========================================================================
# OAuth Endpoints
# =========================================================================

@router.post("/auth/exchange")
async def exchange_outlook_oauth_code(request: OutlookOAuthRequest):
    """
    Exchange OAuth2 authorization code for tokens and store

    Args:
        request: Contains OAuth code, user_id, and redirect_uri

    Returns:
        Success status with user info and outlook_email
    """
    try:
        logger.info(f"Exchanging Outlook OAuth code for user: {request.user_id}")

        # Exchange code for tokens
        token_data = _exchange_code_for_tokens(request.code, request.redirect_uri)

        access_token = token_data.get('access_token')
        refresh_token = token_data.get('refresh_token', '')
        expires_in = token_data.get('expires_in', 3600)

        if not access_token:
            raise HTTPException(status_code=400, detail="No access token received from Microsoft")

        # Calculate expiry time
        expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        # Get user profile
        profile = _get_user_profile(access_token)
        outlook_email = profile.get('mail') or profile.get('userPrincipalName', '')

        # Store tokens in user_integrations
        integration_data = {
            'user_id': request.user_id,
            'provider': 'outlook',
            'access_token': access_token,
            'refresh_token': refresh_token or '',
            'token_expires_at': expiry.isoformat(),
            'sync_status': 'idle',
            'email_count': 0,
            'updated_at': datetime.now(timezone.utc).isoformat()
        }

        # Check if exists
        existing = _supabase.table('user_integrations').select('id').eq(
            'user_id', request.user_id
        ).eq('provider', 'outlook').execute()

        if existing.data:
            _supabase.table('user_integrations').update(integration_data).eq(
                'user_id', request.user_id
            ).eq('provider', 'outlook').execute()
            logger.info(f"Updated Outlook tokens for user: {request.user_id}")
        else:
            integration_data['created_at'] = datetime.now(timezone.utc).isoformat()
            _supabase.table('user_integrations').insert(integration_data).execute()
            logger.info(f"Stored Outlook tokens for new user: {request.user_id}")

        return {
            "status": "success",
            "message": "Outlook connected successfully",
            "user_id": request.user_id,
            "outlook_email": outlook_email
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Outlook OAuth exchange failed: {e}")
        raise HTTPException(status_code=400, detail=f"OAuth failed: {str(e)}")


@router.get("/auth/status/{user_id}")
async def get_outlook_connection_status(user_id: str) -> SyncStatusResponse:
    """
    Check if user has connected Outlook

    Args:
        user_id: User identifier

    Returns:
        Connection and sync status
    """
    try:
        result = _supabase.table('user_integrations').select(
            'access_token, last_sync_at, sync_status, email_count, sync_error'
        ).eq('user_id', user_id).eq('provider', 'outlook').execute()

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
            sync_status="disconnected"
        )

    except Exception as e:
        logger.error(f"Failed to get Outlook status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/auth/disconnect/{user_id}")
async def disconnect_outlook(user_id: str):
    """
    Disconnect Outlook integration and remove tokens

    Args:
        user_id: User identifier

    Returns:
        Success status
    """
    try:
        result = _supabase.table('user_integrations').delete().eq(
            'user_id', user_id
        ).eq('provider', 'outlook').execute()

        logger.info(f"Outlook disconnected for user: {user_id}")

        return {
            "status": "success",
            "message": "Outlook disconnected successfully"
        }

    except Exception as e:
        logger.error(f"Failed to disconnect Outlook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================================
# Sync Endpoints
# =========================================================================

@router.post("/{user_id}/sync")
async def trigger_manual_sync(user_id: str, background_tasks: BackgroundTasks):
    """
    Manually trigger Outlook sync for a user

    Args:
        user_id: User identifier
        background_tasks: FastAPI background tasks

    Returns:
        Sync started status
    """
    try:
        if not _sync_service:
            raise HTTPException(status_code=503, detail="Sync service not available")

        # Check user has Outlook connected
        result = _supabase.table('user_integrations').select('id').eq(
            'user_id', user_id
        ).eq('provider', 'outlook').execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Outlook not connected for this user")

        # Run sync in background
        background_tasks.add_task(_run_user_sync, user_id)

        return {
            "status": "started",
            "message": "Outlook sync started"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to trigger sync: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _run_user_sync(user_id: str):
    """Background task wrapper for user sync"""
    try:
        await _sync_service.trigger_sync(user_id)
    except Exception as e:
        logger.error(f"Background sync failed for user {user_id}: {e}")


@router.get("/{user_id}/sync-status")
async def get_sync_status(user_id: str):
    """
    Get detailed sync status including recent jobs

    Args:
        user_id: User identifier

    Returns:
        Detailed sync status with recent jobs
    """
    try:
        # Get integration status
        integration = _supabase.table('user_integrations').select(
            'last_sync_at, sync_status, email_count, sync_error, delta_link'
        ).eq('user_id', user_id).eq('provider', 'outlook').execute()

        if not integration.data:
            return {
                "connected": False,
                "sync_status": "disconnected"
            }

        data = integration.data[0]

        # Get recent processing jobs for Outlook sync
        jobs = _supabase.table('processing_jobs').select(
            'id, status, processed_records, failed_records, started_at, completed_at, error_log'
        ).eq('job_type', 'outlook_sync').order(
            'created_at', desc=True
        ).limit(5).execute()

        return {
            "connected": True,
            "sync_status": data.get('sync_status', 'idle'),
            "last_sync_at": data.get('last_sync_at'),
            "email_count": data.get('email_count', 0),
            "error": data.get('sync_error'),
            "has_delta_link": bool(data.get('delta_link')),
            "recent_jobs": jobs.data if jobs.data else []
        }

    except Exception as e:
        logger.error(f"Failed to get sync status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================================
# Cron/External Sync Endpoint
# =========================================================================

@router.post("/cron-sync")
async def cron_triggered_sync(background_tasks: BackgroundTasks):
    """
    External cron endpoint to trigger sync for all connected users

    This allows external schedulers (Railway cron, cloud schedulers) to trigger
    sync instead of relying on in-process background loops.

    Returns:
        Number of users queued for sync
    """
    try:
        # Verify API key if configured
        api_key = os.getenv('OUTLOOK_SYNC_API_KEY')
        # Note: In production, add API key verification here

        if not _sync_service:
            raise HTTPException(status_code=503, detail="Sync service not available")

        # Get all users with Outlook connected
        result = _supabase.table('user_integrations').select(
            'user_id'
        ).eq('provider', 'outlook').execute()

        users = result.data if result.data else []

        # Queue sync for each user
        for user in users:
            background_tasks.add_task(_run_user_sync, user['user_id'])

        return {
            "status": "success",
            "users_queued": len(users),
            "message": f"Queued sync for {len(users)} users"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Cron sync failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================================
# Extend Archive Mailbox Endpoint
# =========================================================================

@router.post("/extend-mailbox")
async def extend_mailbox_with_outlook(request: ExtendMailboxRequest):
    """
    Extend an existing archive mailbox with Outlook LIVE sync capability.

    This converts a static imported mailbox (MBOX, PST, OLM) into a hybrid
    that continues receiving new emails from Outlook.

    Args:
        request: Contains mailbox_id and user_id

    Returns:
        Updated mailbox details
    """
    try:
        if not _sync_service:
            raise HTTPException(status_code=503, detail="Sync service not available")

        result = await _sync_service.extend_mailbox_with_outlook(
            request.mailbox_id,
            request.user_id
        )

        return result

    except HTTPException:
        raise
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
    Fetch emails from Outlook for a specific date range.

    This allows pulling historical emails on-demand. Useful for:
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
        # Validate mailbox exists and has Outlook LIVE sync enabled
        mailbox = _supabase.table('mailboxes').select('*').eq(
            'id', request.mailbox_id
        ).execute()

        if not mailbox.data:
            raise HTTPException(status_code=404, detail="Mailbox not found")

        mailbox_data = mailbox.data[0]
        connection_config = mailbox_data.get('connection_config', {}) or {}

        if not connection_config.get('outlook_sync_enabled'):
            raise HTTPException(
                status_code=400,
                detail="Mailbox does not have Outlook LIVE sync enabled. Please link Outlook first."
            )

        # Check user ID matches - unless user is admin
        outlook_user_id = connection_config.get('outlook_user_id')
        is_admin = 'admin' in current_user.get('roles', [])

        if not is_admin and outlook_user_id != current_user['user_id']:
            raise HTTPException(
                status_code=403,
                detail="User ID does not match the Outlook account linked to this mailbox"
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
            'job_type': 'outlook_date_range_fetch',
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
        from src.extractors.outlook_extractor import OutlookExtractor
        from src.database.operations import EmailOperations

        # Update job status to running
        _supabase.table('processing_jobs').update({
            'status': 'running',
            'started_at': datetime.now(timezone.utc).isoformat()
        }).eq('id', job_id).execute()

        # Get Outlook credentials from mailbox connection_config
        mailbox = _supabase.table('mailboxes').select('connection_config').eq('id', mailbox_id).execute()

        if not mailbox.data:
            raise ValueError("Mailbox not found")

        connection_config = mailbox.data[0].get('connection_config', {}) or {}

        if not connection_config.get('outlook_sync_enabled'):
            raise ValueError("Outlook not connected for this mailbox")

        access_token = connection_config.get('outlook_access_token')
        refresh_token = connection_config.get('outlook_refresh_token')

        if not access_token:
            raise ValueError("Outlook access token not found in mailbox configuration")

        # Create and connect Outlook extractor
        extractor = OutlookExtractor(connection_config={
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
            'error_log': [{'error': str(e), 'timestamp': datetime.now(timezone.utc).isoformat()}],
            'completed_at': datetime.now(timezone.utc).isoformat()
        }).eq('id', job_id).execute()


# =========================================================================
# Health and Config Endpoints
# =========================================================================

@router.get("/health")
async def health_check():
    """Health check endpoint for Outlook sync service"""
    service_status = "running" if _sync_service and _sync_service._running else "stopped"
    return {
        "status": "healthy",
        "service": "outlook-sync",
        "sync_service_status": service_status
    }


@router.get("/config")
async def get_outlook_config():
    """Get current Outlook sync configuration"""
    config = _get_config_from_db()

    service_interval = None
    if _sync_service:
        service_interval = _sync_service.sync_interval_minutes

    return {
        "sync_interval_minutes": config['sync_interval_minutes'],
        "service_interval_minutes": service_interval,
        "max_emails_per_sync": 500,
        "sync_service_running": _sync_service._running if _sync_service else False,
        "interval_synced": service_interval == config['sync_interval_minutes'] if service_interval else False
    }


@router.put("/config")
async def update_outlook_config(config: OutlookConfigUpdate):
    """Update Outlook sync configuration"""
    try:
        updates = {}

        if config.sync_interval_minutes is not None:
            if config.sync_interval_minutes < 1 or config.sync_interval_minutes > 1440:
                raise HTTPException(
                    status_code=400,
                    detail="sync_interval_minutes must be between 1 and 1440"
                )

            _save_config_to_db('outlook_sync_interval', config.sync_interval_minutes)
            updates['sync_interval_minutes'] = config.sync_interval_minutes

            # Update running service
            if _sync_service:
                _sync_service.sync_interval_minutes = config.sync_interval_minutes
                logger.info(f"Updated Outlook sync interval to {config.sync_interval_minutes} minutes")

        return {
            "status": "success",
            "message": "Configuration updated",
            "current_config": _get_config_from_db()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================================
# Per-Mailbox Outlook Endpoints (Multi-Outlook Support)
# =========================================================================

@router.post("/mailbox/{mailbox_id}/connect")
async def connect_outlook_to_mailbox(
    mailbox_id: str,
    request: MailboxOutlookConnectRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Connect Outlook account directly to a specific mailbox.

    Stores tokens in mailbox.connection_config instead of user_integrations.
    This enables each mailbox to have its own Outlook connection.

    Args:
        mailbox_id: UUID of the mailbox
        request: Contains OAuth authorization code and redirect_uri

    Returns:
        Success status with Outlook email
    """
    try:
        logger.info(f"Connecting Outlook to mailbox: {mailbox_id}")

        # Verify mailbox exists
        mailbox_result = _supabase.table('mailboxes').select('id, name, connection_config').eq(
            'id', mailbox_id
        ).execute()

        if not mailbox_result.data:
            raise HTTPException(status_code=404, detail="Mailbox not found")

        existing_config = mailbox_result.data[0].get('connection_config') or {}

        # Exchange authorization code for tokens
        token_data = _exchange_code_for_tokens(request.code, request.redirect_uri)

        access_token = token_data.get('access_token')
        refresh_token = token_data.get('refresh_token', '')
        expires_in = token_data.get('expires_in', 3600)

        if not access_token:
            raise HTTPException(status_code=400, detail="No access token received from Microsoft")

        # Calculate expiry time
        expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        # Get user profile
        profile = _get_user_profile(access_token)
        outlook_email = profile.get('mail') or profile.get('userPrincipalName', '')

        # Build Outlook config for mailbox
        outlook_config = {
            'outlook_sync_enabled': True,
            'outlook_user_id': current_user['user_id'],  # Store authenticated user ID
            'outlook_email': outlook_email,
            'outlook_access_token': access_token,
            'outlook_refresh_token': refresh_token,
            'outlook_token_expires_at': expiry.isoformat(),
            'outlook_delta_link': None,  # Will be set after first sync
            'outlook_sync_status': 'idle',
            'outlook_sync_error': None,
            'outlook_email_count': existing_config.get('outlook_email_count', 0),
            'outlook_connected_at': datetime.now(timezone.utc).isoformat()
        }

        # Merge with existing connection_config
        updated_config = {**existing_config, **outlook_config}

        # Update mailbox
        _supabase.table('mailboxes').update({
            'connection_config': updated_config
        }).eq('id', mailbox_id).execute()

        logger.info(f"Outlook {outlook_email} connected to mailbox {mailbox_id}")

        return {
            "success": True,
            "outlook_email": outlook_email,
            "message": f"Outlook {outlook_email} connected to mailbox"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to connect Outlook to mailbox: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/mailbox/{mailbox_id}/disconnect")
async def disconnect_outlook_from_mailbox(mailbox_id: str):
    """
    Remove Outlook connection from a specific mailbox.

    Clears Outlook-related fields from mailbox.connection_config.

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

        # Remove all outlook_ prefixed keys
        cleaned_config = {k: v for k, v in config.items() if not k.startswith('outlook_')}

        # Update mailbox
        _supabase.table('mailboxes').update({
            'connection_config': cleaned_config
        }).eq('id', mailbox_id).execute()

        logger.info(f"Outlook disconnected from mailbox {mailbox_id}")

        return {
            "success": True,
            "message": "Outlook disconnected from mailbox"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to disconnect Outlook from mailbox: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mailbox/{mailbox_id}/status")
async def get_mailbox_outlook_status(mailbox_id: str) -> MailboxOutlookStatusResponse:
    """
    Get Outlook sync status for a specific mailbox.

    Args:
        mailbox_id: UUID of the mailbox

    Returns:
        Outlook connection and sync status
    """
    try:
        result = _supabase.table('mailboxes').select('connection_config').eq(
            'id', mailbox_id
        ).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Mailbox not found")

        config = result.data[0].get('connection_config') or {}

        if not config.get('outlook_sync_enabled') or not config.get('outlook_access_token'):
            return MailboxOutlookStatusResponse(connected=False)

        return MailboxOutlookStatusResponse(
            connected=True,
            outlook_email=config.get('outlook_email'),
            last_sync_at=config.get('outlook_last_sync_at'),
            sync_status=config.get('outlook_sync_status', 'idle'),
            email_count=config.get('outlook_email_count', 0),
            error=config.get('outlook_sync_error')
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get mailbox Outlook status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mailbox/{mailbox_id}/sync")
async def trigger_mailbox_outlook_sync(mailbox_id: str, background_tasks: BackgroundTasks):
    """
    Manually trigger Outlook sync for a specific mailbox.

    Args:
        mailbox_id: UUID of the mailbox
        background_tasks: FastAPI background tasks

    Returns:
        Sync started status
    """
    try:
        if not _sync_service:
            raise HTTPException(status_code=503, detail="Sync service not available")

        # Verify mailbox has Outlook connected
        result = _supabase.table('mailboxes').select('connection_config').eq(
            'id', mailbox_id
        ).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Mailbox not found")

        config = result.data[0].get('connection_config') or {}

        if not config.get('outlook_sync_enabled') or not config.get('outlook_access_token'):
            raise HTTPException(status_code=400, detail="Mailbox does not have Outlook connected")

        # Run sync in background
        background_tasks.add_task(_run_mailbox_sync, mailbox_id)

        return {
            "status": "started",
            "message": "Outlook sync started for mailbox"
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


# =========================================================================
# Outlook Rules Endpoints
# =========================================================================

@router.get("/{user_id}/rules")
async def get_outlook_rules(user_id: str):
    """
    Get imported Outlook rules for a user.

    Returns:
        List of imported rules from outlook_rules table
    """
    try:
        result = _supabase.table('outlook_rules').select('*').eq(
            'user_id', user_id
        ).order('sequence').execute()

        return {
            "rules": result.data or [],
            "total": len(result.data or [])
        }

    except Exception as e:
        logger.error(f"Failed to get Outlook rules: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{user_id}/import-rules")
async def import_outlook_rules(user_id: str):
    """
    Import inbox rules from Outlook via Microsoft Graph API.

    Fetches rules from the user's Outlook account and stores them
    in the outlook_rules table for analysis.
    """
    try:
        if not _sync_service:
            raise HTTPException(status_code=503, detail="Sync service not available")

        rules = await _sync_service.import_rules(user_id=user_id)

        return {
            "status": "success",
            "imported_count": len(rules),
            "rules": rules
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to import Outlook rules: {e}")
        raise HTTPException(status_code=500, detail=str(e))
