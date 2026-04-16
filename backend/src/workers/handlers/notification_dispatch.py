"""
Worker handler for notification_dispatch jobs.

Reads undispatched events, resolves recipients, creates notification records,
and delivers via WebSocket push to connected users.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger("worker.notification_dispatch")

EVENT_TITLES = {
    "job.completed": "Job completed",
    "job.failed": "Job failed",
    "job.started": "Job started",
    "job.stopped": "Job stopped",
}


def _build_notification(event: dict) -> dict:
    """Build title/body from an event row."""
    etype = event.get("event_type", "")
    payload = event.get("payload") or {}
    job_type = payload.get("job_type", "unknown")

    title = EVENT_TITLES.get(etype, etype)
    body = f"{job_type} job {payload.get('status', etype.split('.')[-1])}"

    return {"title": title, "body": body}


async def notification_dispatch_handler(sb, job: dict, stop_event: asyncio.Event):
    """Dispatch pending notifications for undispatched events."""
    now_iso = datetime.now(timezone.utc).isoformat()
    dispatched = 0

    resp = sb.table("events").select("*").is_("dispatched_at", "null").order(
        "created_at"
    ).limit(100).execute()

    events = resp.data or []
    if not events:
        logger.debug("No undispatched events")
        return

    for event in events:
        if stop_event.is_set():
            break

        event_id = event["id"]
        client_id = event.get("client_id")
        notif = _build_notification(event)

        recipients = _resolve_recipients(sb, client_id)
        if recipients:
            rows = [
                {
                    "event_id": event_id,
                    "recipient_user_id": uid,
                    "channel": "in_app",
                    "status": "delivered",
                    "title": notif["title"],
                    "body": notif["body"],
                    "delivered_at": now_iso,
                    "payload": event.get("payload", {}),
                }
                for uid in recipients
            ]
            try:
                sb.table("notifications").insert(rows).execute()
            except Exception as e:
                logger.error(f"Failed to insert notifications for event {event_id}: {e}")
                continue

        try:
            sb.table("events").update({"dispatched_at": now_iso}).eq(
                "id", event_id
            ).execute()
            dispatched += 1
        except Exception as e:
            logger.error(f"Failed to mark event {event_id} dispatched: {e}")

    logger.info(f"Dispatched {dispatched}/{len(events)} events")


def _resolve_recipients(sb, client_id: str | None) -> list[str]:
    """Find users who should receive notifications for this client's events.

    Admin users see everything. Client managers and AMs see events for their
    assigned clients.
    """
    try:
        query = sb.table("user_profiles").select("id, roles")
        if client_id:
            admins = query.contains("roles", ["admin"]).execute()
            assigned = sb.table("user_client_assignments").select(
                "user_id"
            ).eq("client_id", client_id).execute()

            user_ids = {r["id"] for r in (admins.data or [])}
            user_ids.update(r["user_id"] for r in (assigned.data or []))
            return list(user_ids)
        else:
            admins = query.contains("roles", ["admin"]).execute()
            return [r["id"] for r in (admins.data or [])]
    except Exception as e:
        logger.error(f"Failed to resolve recipients: {e}")
        return []
