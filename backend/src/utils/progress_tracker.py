"""
Shared progress tracking utilities

This module provides progress tracking functions that can be used by
both the backend API and the email processor without circular dependencies.

Stage 3: Includes WebSocket broadcast for real-time updates.
"""

import asyncio
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Global reference to progress manager (initialized by backend)
_progress_manager = None
_queue_manager = None

# Job to mailbox mapping (for WebSocket broadcasts)
_job_mailbox_map: Dict[str, str] = {}


def initialize_progress_managers(progress_mgr, queue_mgr):
    """
    Initialize global progress managers

    Called by backend/main.py during startup
    """
    global _progress_manager, _queue_manager
    _progress_manager = progress_mgr
    _queue_manager = queue_mgr

    if _progress_manager:
        logger.info("Progress tracker initialized with Redis")
    else:
        logger.warning("Progress tracker initialized in database-only mode")


def register_job_mailbox(job_id: str, mailbox_id: str):
    """
    Register the mailbox ID for a job (needed for WebSocket broadcasts).

    Args:
        job_id: Job ID
        mailbox_id: Mailbox ID
    """
    _job_mailbox_map[job_id] = mailbox_id


def unregister_job(job_id: str):
    """
    Unregister a job when it completes.

    Args:
        job_id: Job ID
    """
    _job_mailbox_map.pop(job_id, None)


def update_job_progress(job_id: str, processed: int, failed: int = 0) -> bool:
    """
    Update job progress in Redis (if available) and broadcast via WebSocket.

    Args:
        job_id: Job ID
        processed: Number of emails processed
        failed: Number of failed emails

    Returns:
        True if should sync to database (every 100 emails or Redis unavailable)
    """
    if not _progress_manager:
        # Redis not available, always sync to DB
        logger.debug(f"Redis unavailable, triggering DB sync for job {job_id}")
        return True

    try:
        # Update Redis
        _progress_manager.update_progress(job_id, processed, failed)

        # Determine if we should sync to database
        # Sync every 100 emails to reduce DB load but ensure persistence
        should_sync = (processed > 0 and processed % 100 == 0)

        if should_sync:
            logger.debug(f"Redis checkpoint reached ({processed} emails), triggering DB sync for job {job_id}")

        # Broadcast via WebSocket every 10 emails (throttled)
        if processed > 0 and processed % 10 == 0:
            _broadcast_progress_update(job_id, processed, failed)

        return should_sync

    except Exception as e:
        logger.error(f"Failed to update Redis progress for job {job_id}: {e}")
        # If Redis fails, fall back to database
        return True


def _broadcast_progress_update(job_id: str, processed: int, failed: int):
    """
    Broadcast progress update via WebSocket (non-blocking).

    Args:
        job_id: Job ID
        processed: Number of emails processed
        failed: Number of failed emails
    """
    try:
        # Lazy import to avoid circular dependencies
        from src.websocket.manager import get_connection_manager

        manager = get_connection_manager()
        if not manager:
            return

        mailbox_id = _job_mailbox_map.get(job_id)
        if not mailbox_id:
            return

        # Get full progress data from Redis
        progress = _progress_manager.get_progress(job_id) if _progress_manager else {}

        # Create async task for broadcast (non-blocking)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(manager.broadcast_job_update(job_id, mailbox_id, {
                    'status': progress.get('status', 'running'),
                    'processed_records': processed,
                    'failed_records': failed,
                    'total_records': progress.get('total_records', 0),
                    'emails_per_second': progress.get('emails_per_second', 0),
                    'estimated_seconds_remaining': progress.get('estimated_seconds_remaining', 0),
                    'download_percent': progress.get('download_percent'),
                    'download_speed_mbps': progress.get('download_speed_mbps'),
                }))
        except RuntimeError:
            # No event loop running - skip broadcast
            pass

    except Exception as e:
        # Non-critical - don't break processing if WebSocket fails
        logger.debug(f"WebSocket broadcast failed (non-critical): {e}")


def get_job_progress(job_id: str) -> Dict[str, int]:
    """
    Get job progress from Redis (if available) or return empty dict

    Args:
        job_id: Job ID

    Returns:
        Dict with 'processed' and 'failed' counts, or empty dict
    """
    if not _progress_manager:
        return {}

    try:
        progress = _progress_manager.get_progress(job_id)
        if progress:
            return progress
    except Exception as e:
        logger.error(f"Failed to get Redis progress for job {job_id}: {e}")

    return {}


def set_total_records(job_id: str, total: int):
    """
    Set total record count in Redis

    Args:
        job_id: Job ID
        total: Total number of records to process
    """
    if not _progress_manager:
        return

    try:
        _progress_manager.update_progress(job_id, 0, 0, total_records=total)
        logger.info(f"Set total_records={total} in Redis for job {job_id}")
    except Exception as e:
        logger.error(f"Failed to set total records in Redis for job {job_id}: {e}")


def is_redis_available() -> bool:
    """Check if Redis is available"""
    return _progress_manager is not None
