"""
Notifications API — in-app notification feed for users.

GET  /notifications          — list notifications (unread or all)
POST /notifications/{id}/read — mark a notification as read
POST /notifications/read-all  — mark all as read
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..dependencies.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])

_supabase = None


def init_notifications_router(supabase_client):
    global _supabase
    _supabase = supabase_client


@router.get("")
async def list_notifications(
    unread: bool = Query(False, description="Only unread notifications"),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    """List notifications for the current user."""
    user_id = current_user["user_id"]
    query = _supabase.table("notifications").select("*").eq(
        "recipient_user_id", user_id
    ).order("created_at", desc=True).limit(limit)

    if unread:
        query = query.neq("status", "read")

    resp = query.execute()
    return {"notifications": resp.data or [], "count": len(resp.data or [])}


@router.get("/unread-count")
async def unread_count(
    current_user: dict = Depends(get_current_user),
):
    """Get unread notification count."""
    user_id = current_user["user_id"]
    resp = _supabase.table("notifications").select(
        "id", count="exact"
    ).eq("recipient_user_id", user_id).neq("status", "read").execute()

    return {"count": resp.count or 0}


@router.post("/{notification_id}/read")
async def mark_read(
    notification_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Mark a single notification as read."""
    user_id = current_user["user_id"]
    now = datetime.now(timezone.utc).isoformat()

    resp = _supabase.table("notifications").update({
        "status": "read",
        "read_at": now,
    }).eq("id", notification_id).eq("recipient_user_id", user_id).execute()

    if not resp.data:
        raise HTTPException(status_code=404, detail="Notification not found")

    return {"status": "ok"}


@router.post("/read-all")
async def mark_all_read(
    current_user: dict = Depends(get_current_user),
):
    """Mark all unread notifications as read."""
    user_id = current_user["user_id"]
    now = datetime.now(timezone.utc).isoformat()

    _supabase.table("notifications").update({
        "status": "read",
        "read_at": now,
    }).eq("recipient_user_id", user_id).neq("status", "read").execute()

    return {"status": "ok"}
