"""
Mailbox CRUD Router — Create, read, update, delete mailboxes, test connections, cached downloads.

Extracted from main.py for modularity.
"""

import os
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends

from ..models.api_models import MailboxConfig, ConnectionTest
from ..dependencies.auth import get_current_user, get_accessible_mailbox_ids, require_role
from ..utils.audit import audit_from_user
from ..processors.email_processor import EmailProcessor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mailboxes", tags=["mailboxes"])

# Supabase getter — set via init
_get_supabase = None
# run_reprocessing callback — set via init (lives in processing_jobs router)
_run_reprocessing = None


def init_mailboxes_router(supabase_getter, run_reprocessing_fn=None):
    """Initialize with a callable that returns the Supabase client."""
    global _get_supabase, _run_reprocessing
    _get_supabase = supabase_getter
    _run_reprocessing = run_reprocessing_fn


# ── List ────────────────────────────────────────────────────────────────

@router.get("")
async def get_mailboxes(accessible_mailbox_ids: list = Depends(get_accessible_mailbox_ids)):
    """Get mailboxes accessible to current user with email counts."""
    try:
        sb = _get_supabase()

        if not accessible_mailbox_ids:
            logger.warning("[Mailboxes API] No accessible mailboxes for user")
            return []

        mailboxes_result = sb.table('mailboxes').select('*').in_('id', accessible_mailbox_ids).order('created_at', desc=True).execute()

        if not mailboxes_result.data:
            return []

        # Try to get email counts via RPC (most efficient)
        count_map = {}
        try:
            counts_result = sb.rpc('get_email_counts_by_mailbox', {}).execute()
            if counts_result.data:
                for row in counts_result.data:
                    if row['mailbox_id'] in accessible_mailbox_ids:
                        count_map[row['mailbox_id']] = row['email_count']
        except Exception as rpc_error:
            logger.debug(f"RPC not available, using fallback: {rpc_error}")
            for mailbox in mailboxes_result.data:
                try:
                    count_result = sb.table('emails').select('id', count='exact').eq('mailbox_id', mailbox['id']).limit(1).execute()
                    count_map[mailbox['id']] = count_result.count or 0
                except Exception as count_error:
                    logger.debug(f"Count failed for {mailbox['id']}: {count_error}")
                    count_map[mailbox['id']] = 0

        return [
            {**mailbox, 'total_emails': count_map.get(mailbox['id'], 0)}
            for mailbox in mailboxes_result.data
        ]

    except Exception as e:
        logger.error(f"Error fetching mailboxes: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch mailboxes: {str(e)}")


# ── Single ──────────────────────────────────────────────────────────────

@router.get("/{mailbox_id}")
async def get_mailbox(mailbox_id: str, current_user: dict = Depends(get_current_user)):
    """Get a single mailbox by ID."""
    try:
        sb = _get_supabase()
        result = sb.table('mailboxes').select('*').eq('id', mailbox_id).single().execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Mailbox not found")
        return result.data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching mailbox {mailbox_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch mailbox: {str(e)}")


# ── Create ──────────────────────────────────────────────────────────────

@router.post("")
async def create_mailbox(mailbox_data: MailboxConfig, current_user: dict = Depends(get_current_user)):
    """Create a new mailbox."""
    try:
        sb = _get_supabase()
        insert_data = {
            "name": mailbox_data.name,
            "mailbox_type": mailbox_data.mailbox_type,
            "is_active": mailbox_data.is_active,
            "connection_config": mailbox_data.connection_config,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "total_emails": 0,
            "client_id": mailbox_data.client_id,
            "user_id": mailbox_data.user_id,
        }
        if mailbox_data.email_address:
            insert_data["email_address"] = mailbox_data.email_address

        result = sb.table('mailboxes').insert(insert_data).execute()

        if result.data and len(result.data) > 0:
            mailbox_id = result.data[0]['id']
            created_result = sb.table('mailboxes').select('*').eq('id', mailbox_id).single().execute()
            audit_from_user(current_user, "mailbox_create", "mailbox", resource_id=mailbox_id,
                            details={"name": mailbox_data.name, "type": mailbox_data.mailbox_type})
            return created_result.data
        else:
            raise HTTPException(status_code=500, detail="Failed to create mailbox")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating mailbox: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create mailbox: {str(e)}")


# ── Update ──────────────────────────────────────────────────────────────

@router.put("/{mailbox_id}")
async def update_mailbox(mailbox_id: str, mailbox_data: MailboxConfig, current_user: dict = Depends(get_current_user)):
    """Update an existing mailbox."""
    try:
        sb = _get_supabase()

        current_mailbox = sb.table('mailboxes').select('*').eq('id', mailbox_id).single().execute()
        if not current_mailbox.data:
            raise HTTPException(status_code=404, detail="Mailbox not found")

        # Validate email_address against connected provider
        if mailbox_data.email_address:
            current_config = current_mailbox.data.get('connection_config') or {}
            gmail_email = current_config.get('gmail_email')
            outlook_email = current_config.get('outlook_email')
            if gmail_email and mailbox_data.email_address.lower() != gmail_email.lower():
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot change email address to {mailbox_data.email_address}. "
                           f"This mailbox is connected to Gmail account {gmail_email}. "
                           f"Please disconnect Gmail first or use the connected email address."
                )
            if outlook_email and mailbox_data.email_address.lower() != outlook_email.lower():
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot change email address to {mailbox_data.email_address}. "
                           f"This mailbox is connected to Outlook account {outlook_email}. "
                           f"Please disconnect Outlook first or use the connected email address."
                )

        update_data = {
            "name": mailbox_data.name,
            "mailbox_type": mailbox_data.mailbox_type,
            "is_active": mailbox_data.is_active,
            "connection_config": mailbox_data.connection_config,
            "client_id": mailbox_data.client_id,
            "user_id": mailbox_data.user_id,
        }
        if mailbox_data.email_address:
            update_data["email_address"] = mailbox_data.email_address

        sb.table('mailboxes').update(update_data).eq('id', mailbox_id).execute()
        updated_result = sb.table('mailboxes').select('*').eq('id', mailbox_id).single().execute()
        if not updated_result.data:
            raise HTTPException(status_code=404, detail="Mailbox not found")
        return updated_result.data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating mailbox {mailbox_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update mailbox: {str(e)}")


# ── Delete ──────────────────────────────────────────────────────────────

@router.delete("/{mailbox_id}")
async def delete_mailbox(mailbox_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a mailbox and all related data.

    Explicitly deletes related records first to avoid Supabase statement
    timeout on large cascade deletes.
    """
    try:
        sb = _get_supabase()

        check_result = sb.table('mailboxes').select('id').eq('id', mailbox_id).execute()
        if not check_result.data:
            raise HTTPException(status_code=404, detail="Mailbox not found")

        related_tables = [
            "ai_daily_digests", "ai_email_intelligence", "ai_business_entities",
            "ai_usage_log", "unified_email_rules", "thread_status",
        ]
        for table in related_tables:
            try:
                sb.table(table).delete().eq("mailbox_id", mailbox_id).execute()
            except Exception as e:
                logger.warning(f"Failed to clean {table} for mailbox {mailbox_id}: {e}")

        # Delete emails in batches
        deleted_total = 0
        while True:
            batch = sb.table("emails").select("id").eq("mailbox_id", mailbox_id).limit(500).execute()
            ids = [r["id"] for r in (batch.data or [])]
            if not ids:
                break
            sb.table("emails").delete().in_("id", ids).execute()
            deleted_total += len(ids)
            logger.info(f"Deleted {deleted_total} emails for mailbox {mailbox_id}...")

        for table in ["folders", "processing_jobs"]:
            try:
                sb.table(table).delete().eq("mailbox_id", mailbox_id).execute()
            except Exception as e:
                logger.warning(f"Failed to clean {table} for mailbox {mailbox_id}: {e}")

        sb.table('mailboxes').delete().eq('id', mailbox_id).execute()

        logger.info(f"Mailbox {mailbox_id} deleted with {deleted_total} emails")
        audit_from_user(current_user, "mailbox_delete", "mailbox",
                        resource_id=mailbox_id, details={"emails_deleted": deleted_total})
        return {"message": "Mailbox deleted successfully", "emails_deleted": deleted_total}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting mailbox {mailbox_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete mailbox: {str(e)}")


# ── Assign ──────────────────────────────────────────────────────────────

@router.patch("/{mailbox_id}/assign-client")
async def assign_mailbox_to_client(
    mailbox_id: str, assignment: dict,
    current_user: dict = Depends(require_role('admin'))
):
    """Assign a mailbox to a client (admin only)."""
    try:
        sb = _get_supabase()
        result = sb.table('mailboxes').update({
            'client_id': assignment.get('client_id')
        }).eq('id', mailbox_id).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Mailbox not found")
        return {"success": True, "message": "Mailbox assigned to client successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error assigning mailbox to client: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to assign mailbox: {str(e)}")


@router.patch("/{mailbox_id}/assign-user")
async def assign_mailbox_to_user(
    mailbox_id: str, assignment: dict,
    current_user: dict = Depends(require_role('admin'))
):
    """Assign a mailbox to an account manager (admin only)."""
    try:
        sb = _get_supabase()
        result = sb.table('mailboxes').update({
            'user_id': assignment.get('user_id')
        }).eq('id', mailbox_id).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Mailbox not found")
        return {"success": True, "message": "Mailbox assigned to account manager successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error assigning mailbox to user: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to assign mailbox: {str(e)}")


# ── Sync / Resync ──────────────────────────────────────────────────────

@router.post("/{mailbox_id}/sync")
async def sync_mailbox(mailbox_id: str, current_user: dict = Depends(get_current_user)):
    """Trigger sync for a mailbox."""
    try:
        sb = _get_supabase()
        result = sb.table('mailboxes').update({
            "last_sync_at": datetime.now(timezone.utc).isoformat()
        }).eq('id', mailbox_id).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Mailbox not found")
        return {"message": "Mailbox sync triggered successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error syncing mailbox {mailbox_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to sync mailbox: {str(e)}")


@router.post("/{mailbox_id}/resync-metadata")
async def resync_metadata(mailbox_id: str, background_tasks: BackgroundTasks):
    """Re-extract emails from mail provider to backfill attachment names and provider web links."""
    try:
        sb = _get_supabase()
        mb_result = sb.table('mailboxes').select(
            'id, mailbox_type, connection_config'
        ).eq('id', mailbox_id).single().execute()

        if not mb_result.data:
            raise HTTPException(status_code=404, detail="Mailbox not found")

        mailbox = mb_result.data
        if mailbox.get('mailbox_type', '') not in ('outlook_live', 'outlook'):
            raise HTTPException(status_code=400, detail="Only Outlook mailboxes support metadata re-sync")

        job_data = {
            "job_type": "reprocessing",
            "mailbox_id": mailbox_id,
            "status": "pending",
            "total_records": 0,
            "processed_records": 0,
            "failed_records": 0,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        result = sb.table('processing_jobs').insert(job_data).execute()
        job_id = result.data[0]['id']

        if _run_reprocessing:
            background_tasks.add_task(_run_reprocessing, job_id, mailbox)
        return {"message": "Metadata re-sync started", "job_id": job_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start metadata re-sync for {mailbox_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Test Connection ────────────────────────────────────────────────────

@router.post("/test/test-connection")
async def test_connection_generic(connection_test: ConnectionTest):
    """Test mailbox connection based on type."""
    mailbox_type = connection_test.mailbox_type
    config = connection_test.connection_config

    try:
        processor = EmailProcessor(
            mailbox_id="test_connection",
            connection_config=config
        )

        if config.get('file_source', 'local') == 'local':
            validation_result = processor.validate_configuration(mailbox_type)
            if not validation_result['valid']:
                raise HTTPException(status_code=400, detail=validation_result['error'])
            return {
                "success": True,
                "message": f"{mailbox_type.upper()} connection test successful",
                "details": validation_result['details'],
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        else:
            try:
                if not processor.initialize_extractor(mailbox_type):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Failed to initialize {mailbox_type.upper()} extractor for Google Drive file"
                    )
                processor.disconnect()
                return {
                    "success": True,
                    "message": f"{mailbox_type.upper()} Google Drive connection test successful",
                    "details": {
                        "file_name": config.get('google_drive_file_name', 'Unknown file'),
                        "file_source": "google_drive",
                        "mailbox_type": mailbox_type
                    },
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Google Drive connection test failed: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Connection test failed: {str(e)}")


@router.post("/{mailbox_id}/test-connection")
async def test_connection(mailbox_id: str, connection_test: ConnectionTest):
    """Test mailbox connection based on type (delegates to generic handler)."""
    return await test_connection_generic(connection_test)


# ── Cached Downloads ───────────────────────────────────────────────────

@router.get("/{mailbox_id}/cached-download")
async def check_cached_download(mailbox_id: str):
    """Check if there's a cached download available for this mailbox's Google Drive file."""
    try:
        sb = _get_supabase()

        mailbox_result = sb.table('mailboxes').select('connection_config').eq('id', mailbox_id).single().execute()
        if not mailbox_result.data:
            raise HTTPException(status_code=404, detail="Mailbox not found")

        connection_config = mailbox_result.data.get('connection_config', {})
        if connection_config.get('file_source') != 'google_drive':
            return {"cached": False, "reason": "Not a Google Drive file"}

        google_drive_file_id = connection_config.get('google_drive_file_id')
        if not google_drive_file_id:
            return {"cached": False, "reason": "No Google Drive file ID"}

        cache_result = sb.table('downloaded_files').select('*').eq(
            'google_drive_file_id', google_drive_file_id
        ).eq('is_valid', True).execute()

        if not cache_result.data:
            return {"cached": False, "reason": "No cached download found"}

        cached = cache_result.data[0]

        if cached.get('storage_type') == 'local':
            if not os.path.exists(cached.get('storage_path', '')):
                sb.table('downloaded_files').update({'is_valid': False}).eq('id', cached['id']).execute()
                return {"cached": False, "reason": "Cached file no longer exists on disk"}

        downloaded_at = datetime.fromisoformat(cached['downloaded_at'].replace('Z', '+00:00'))
        age_hours = (datetime.now(timezone.utc) - downloaded_at).total_seconds() / 3600

        file_size = cached.get('file_size', 0)
        if file_size >= 1024 ** 3:
            size_str = f"{file_size / (1024 ** 3):.2f} GB"
        elif file_size >= 1024 ** 2:
            size_str = f"{file_size / (1024 ** 2):.1f} MB"
        else:
            size_str = f"{file_size / 1024:.1f} KB"

        return {
            "cached": True,
            "cache_id": cached['id'],
            "file_name": cached['file_name'],
            "file_size": file_size,
            "file_size_formatted": size_str,
            "storage_type": cached['storage_type'],
            "storage_path": cached['storage_path'],
            "downloaded_at": cached['downloaded_at'],
            "age_hours": round(age_hours, 1),
            "age_formatted": f"{int(age_hours)} hours ago" if age_hours < 24 else f"{int(age_hours / 24)} days ago",
            "last_used_at": cached.get('last_used_at')
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to check cached download: {e}")
        raise HTTPException(status_code=500, detail=str(e))