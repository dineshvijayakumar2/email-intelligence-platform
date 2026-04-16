"""
Event emission service.

Emits structured events into the events table for downstream notification
dispatch. Events are lightweight records — the notification dispatcher reads
undispatched events, routes them to recipients, and delivers via WebSocket.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def emit_event(
    sb,
    event_type: str,
    *,
    client_id: Optional[str] = None,
    source_type: Optional[str] = None,
    source_id: Optional[str] = None,
    payload: Optional[dict] = None,
) -> Optional[str]:
    """Insert an event row. Returns the event id or None on failure."""
    try:
        row = {
            "event_type": event_type,
            "payload": payload or {},
        }
        if client_id:
            row["client_id"] = client_id
        if source_type:
            row["source_type"] = source_type
        if source_id:
            row["source_id"] = source_id

        resp = sb.table("events").insert(row).execute()
        if resp.data:
            return resp.data[0]["id"]
        return None
    except Exception as e:
        logger.error(f"Failed to emit event {event_type}: {e}")
        return None


def emit_job_event(sb, job: dict, event_type: str, extra: Optional[dict] = None):
    """Convenience wrapper for job lifecycle events."""
    payload = {
        "job_id": job.get("id"),
        "job_type": job.get("job_type"),
        "status": event_type.split(".")[-1],
    }
    if extra:
        payload.update(extra)

    return emit_event(
        sb,
        event_type=event_type,
        client_id=job.get("client_id"),
        source_type="processing_job",
        source_id=job.get("id"),
        payload=payload,
    )
