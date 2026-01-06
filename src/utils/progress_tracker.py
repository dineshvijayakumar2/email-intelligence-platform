"""
Shared progress tracking utilities

This module provides progress tracking functions that can be used by
both the backend API and the email processor without circular dependencies.
"""

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Global reference to progress manager (initialized by backend)
_progress_manager = None
_queue_manager = None


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


def update_job_progress(job_id: str, processed: int, failed: int = 0) -> bool:
    """
    Update job progress in Redis (if available)

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

        return should_sync

    except Exception as e:
        logger.error(f"Failed to update Redis progress for job {job_id}: {e}")
        # If Redis fails, fall back to database
        return True


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
