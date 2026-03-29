"""
Live Log Monitoring Router — Serves recent structured logs from Redis ring buffer.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Query

from ..utils.log_stream import get_recent_logs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/logs", tags=["logs"])

_redis = None
_supabase = None


def init_logs_router(redis_client, supabase_client=None):
    global _redis, _supabase
    _redis = redis_client
    _supabase = supabase_client


@router.get("/recent")
async def recent_logs(
    limit: int = Query(100, ge=1, le=500),
    level: Optional[str] = Query(None, description="Filter by level: DEBUG, INFO, WARNING, ERROR"),
    service: Optional[str] = Query(None, description="Filter by service name"),
    search: Optional[str] = Query(None, description="Search in message text"),
    mailbox_id: Optional[str] = Query(None, description="Filter by mailbox UUID"),
    client_id: Optional[str] = Query(None, description="Filter by client UUID"),
):
    """Get recent log entries from the live stream."""
    if not _redis:
        return {"logs": [], "error": "Redis not available"}

    entries = get_recent_logs(
        _redis, limit=limit, level=level, service=service,
        search=search, mailbox_id=mailbox_id, client_id=client_id,
    )
    return {"logs": entries, "total": len(entries)}


@router.get("/services")
async def list_services():
    """List known service names for the filter dropdown."""
    from ..utils.log_stream import _SERVICE_MAP
    services = sorted(set(_SERVICE_MAP.values()))
    return {"services": services}


@router.get("/context")
async def get_context_names():
    """Resolve mailbox/client IDs to human-readable names for filter dropdowns."""
    if not _supabase:
        return {"mailboxes": {}, "clients": {}}

    try:
        mailboxes = {}
        mb_result = _supabase.table('mailboxes').select('id, email_address, mailbox_type, name').execute()
        for m in (mb_result.data or []):
            # Prefer: custom name > email local part > mailbox_type > truncated ID
            email = m.get('email_address') or ''
            local_part = email.split('@')[0] if '@' in email else ''
            domain_short = email.split('@')[1].split('.')[0] if '@' in email else ''
            name = m.get('name') or ''
            if name:
                label = name
            elif local_part:
                label = f"{local_part}@{domain_short}" if domain_short else local_part
            else:
                label = m.get('mailbox_type') or m['id'][:8]
            mailboxes[m['id']] = label

        clients = {}
        cl_result = _supabase.table('clients').select('id, client_name').execute()
        for c in (cl_result.data or []):
            clients[c['id']] = c.get('client_name') or c['id'][:8]

        return {"mailboxes": mailboxes, "clients": clients}
    except Exception as e:
        logger.warning(f"Failed to load log context names: {e}")
        return {"mailboxes": {}, "clients": {}}
