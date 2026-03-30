"""
Processing Jobs Router

Handles all processing job endpoints: listing, control (pause/resume/stop),
restart, delete, reprocess, error inspection, and retry.

Also exports standalone functions for endpoints that live under different
URL prefixes in main.py:
  - start_processing  (POST /api/mailboxes/{mailbox_id}/process)
  - invalidate_cached_download  (DELETE /api/cached-downloads/{cache_id})

Background helpers:
  - process_emails_real  (the big background processor)
  - update_job_status
  - cleanup_orphaned_jobs  (called during startup)
  - sync_redis_to_database  (called during shutdown)
"""

import os
import asyncio
import logging
import threading
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends

from ..models.api_models import ProcessingJobConfig
from ..dependencies.auth import get_current_user, get_accessible_mailbox_ids
from ..websocket.manager import get_connection_manager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level state (injected via init / setters)
# ---------------------------------------------------------------------------
_get_supabase = None          # callable -> supabase Client
_progress_manager = None      # JobProgressManager
_queue_manager = None          # JobQueueManager
_executor = None               # ThreadPoolExecutor
_download_dir = None           # str | None

_gmail_sync_service = None
_outlook_sync_service = None

_active_jobs: Dict[str, dict] = {}
_active_jobs_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Initialisation helpers
# ---------------------------------------------------------------------------

def init_processing_jobs_router(supabase_getter, progress_mgr, queue_mgr, thread_executor, download_dir):
    """
    Inject shared dependencies from main.py.

    Args:
        supabase_getter: callable that returns the Supabase client
        progress_mgr: JobProgressManager instance (may be None)
        queue_mgr: JobQueueManager instance (may be None)
        thread_executor: ThreadPoolExecutor for CPU work
        download_dir: persistent download directory (str or None)
    """
    global _get_supabase, _progress_manager, _queue_manager, _executor, _download_dir
    _get_supabase = supabase_getter
    _progress_manager = progress_mgr
    _queue_manager = queue_mgr
    _executor = thread_executor
    _download_dir = download_dir


def set_gmail_sync_service(svc):
    global _gmail_sync_service
    _gmail_sync_service = svc


def set_outlook_sync_service(svc):
    global _outlook_sync_service
    _outlook_sync_service = svc


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
router = APIRouter(prefix="/processing-jobs", tags=["processing_jobs"])


# ===== Router endpoints =====================================================

@router.get("")
async def get_processing_jobs(
    mailbox_id: str = None,
    current_user: dict = Depends(get_current_user),
    accessible_mailbox_ids: list = Depends(get_accessible_mailbox_ids),
):
    """Get processing jobs filtered by user's accessible mailboxes. Optionally filter by specific mailbox_id."""

    try:
        logger.info(
            f"[Processing Jobs] User {current_user['user_id']} accessing with "
            f"{len(accessible_mailbox_ids)} mailboxes, filter mailbox_id={mailbox_id}"
        )

        # If user has no accessible mailboxes, return empty list
        if not accessible_mailbox_ids:
            logger.warning("[Processing Jobs] User has no accessible mailboxes")
            return []

        # Determine which mailbox IDs to filter by
        if mailbox_id:
            # If specific mailbox requested, verify it's accessible
            if mailbox_id not in accessible_mailbox_ids:
                logger.warning(f"[Processing Jobs] Requested mailbox {mailbox_id} not in accessible list")
                return []
            filter_mailbox_ids = [mailbox_id]
        else:
            filter_mailbox_ids = accessible_mailbox_ids

        # Get processing jobs for the filtered mailboxes
        # Note: error_log excluded from list response (can be 100KB+ per job, use /processing-jobs/{id} for details)
        # Retry once on transient HTTP/2 connection errors (Supabase cold-start)
        for attempt in range(2):
            try:
                result = _get_supabase().table('processing_jobs').select(
                    'id, job_type, mailbox_id, status, total_records, processed_records, failed_records, filtered_records, started_at, completed_at, created_at, filter_start_date, filter_end_date, mailboxes(name)'
                ).in_('mailbox_id', filter_mailbox_ids).order('created_at', desc=True).limit(100).execute()
                break
            except Exception as retry_err:
                if attempt == 0 and 'ConnectionTerminated' in str(retry_err):
                    logger.warning(f"[Processing Jobs] Transient connection error, retrying: {retry_err}")
                    continue
                raise

        jobs = []
        for job in result.data:
            # Get real-time progress from Redis (faster than database)
            # Only use Redis data for actively running jobs — interrupted/failed/completed
            # jobs should use DB values (Redis may have stale "running" data)
            db_status = job.get('status')
            if db_status in ('running', 'pending', 'downloading'):
                redis_progress = get_job_progress(job['id'])
                if redis_progress['processed'] > job.get('processed_records', 0):
                    job['processed_records'] = redis_progress['processed']
                    job['failed_records'] = redis_progress['failed']
            else:
                redis_progress = {'processed': 0, 'failed': 0, 'emails_per_second': 0, 'estimated_seconds_remaining': 0}

            # Calculate progress safely, handling None and 0
            total = job.get('total_records') or 0
            processed = job.get('processed_records') or 0
            filtered = job.get('filtered_records') or 0

            # Progress calculation:
            # - If completed: always 100%
            # - If has total: (processed + filtered) / total (filtered emails count as processed for progress)
            # - Otherwise: 0%
            if job.get('status') == 'completed':
                progress = 100  # Completed jobs always show 100%
            elif total > 0:
                # Include filtered records in progress calculation
                effective_processed = processed + filtered
                progress = min(100, round((effective_processed / total) * 100))
            else:
                progress = 0  # Pending or running without total_records yet

            # Format ETA if available from Redis
            eta_str = None
            emails_per_second = redis_progress.get('emails_per_second', 0) or 0
            estimated_seconds = redis_progress.get('estimated_seconds_remaining', 0) or 0

            # Ensure values are numbers, not None
            try:
                emails_per_second = float(emails_per_second) if emails_per_second else 0
                estimated_seconds = float(estimated_seconds) if estimated_seconds else 0
            except (ValueError, TypeError):
                emails_per_second = 0
                estimated_seconds = 0

            if estimated_seconds > 0 and job.get('status') == 'running':
                if estimated_seconds < 60:
                    eta_str = f"{estimated_seconds:.0f}s"
                elif estimated_seconds < 3600:
                    eta_minutes = estimated_seconds / 60
                    eta_str = f"{eta_minutes:.1f}m"
                else:
                    eta_hours = estimated_seconds / 3600
                    eta_str = f"{eta_hours:.1f}h"

            # Get download progress if in downloading phase
            download_percent_raw = redis_progress.get('download_percent', 0)
            download_speed_raw = redis_progress.get('download_speed_mbps', 0)

            # Convert to numbers (Redis stores as strings)
            try:
                download_percent = float(download_percent_raw) if download_percent_raw else 0
            except (ValueError, TypeError):
                download_percent = 0

            try:
                download_speed_mbps = float(download_speed_raw) if download_speed_raw else 0
            except (ValueError, TypeError):
                download_speed_mbps = 0

            redis_status = redis_progress.get('status')

            # Override status if downloading
            effective_status = job.get('status')
            if redis_status == 'downloading' and effective_status == 'running':
                effective_status = 'downloading'
                logger.debug(
                    f"Job {job['id']} status overridden to 'downloading' - "
                    f"percent: {download_percent}, speed: {download_speed_mbps}"
                )

            # Calculate duration
            duration_str = None
            duration_seconds = None
            if job.get('started_at'):
                try:
                    started = datetime.fromisoformat(job['started_at'].replace('Z', '+00:00'))
                    if job.get('completed_at'):
                        # Completed job - calculate actual duration
                        completed = datetime.fromisoformat(job['completed_at'].replace('Z', '+00:00'))
                        duration_delta = completed - started
                        duration_seconds = duration_delta.total_seconds()
                    elif job.get('status') in ['running', 'downloading']:
                        # Running job - calculate elapsed time
                        now = datetime.now(timezone.utc)
                        duration_delta = now - started
                        duration_seconds = duration_delta.total_seconds()

                    # Format duration string
                    if duration_seconds:
                        if duration_seconds < 60:
                            duration_str = f"{duration_seconds:.0f}s"
                        elif duration_seconds < 3600:
                            duration_minutes = duration_seconds / 60
                            duration_str = f"{duration_minutes:.1f}m"
                        else:
                            duration_hours = duration_seconds / 3600
                            duration_str = f"{duration_hours:.1f}h"
                except (ValueError, TypeError) as e:
                    logger.debug(f"Error calculating duration for job {job['id']}: {e}")

            job_data = {
                **job,
                "mailbox_name": job.get('mailboxes', {}).get('name') if job.get('mailboxes') else 'Unknown Mailbox',
                "status": effective_status,
                "progress": progress,
                "total_records": total,  # Ensure it's not None
                "processed_records": processed,  # Ensure it's not None
                "emails_per_second": emails_per_second,
                "estimated_time_remaining": eta_str,
                "estimated_seconds_remaining": estimated_seconds,
                "download_percent": download_percent,
                "download_speed_mbps": download_speed_mbps,
                "duration": duration_str,
                "duration_seconds": duration_seconds,
            }
            # Remove the nested mailboxes object
            if 'mailboxes' in job_data:
                del job_data['mailboxes']
            jobs.append(job_data)

        return jobs

    except Exception as e:
        logger.error(f"Failed to get processing jobs from database: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch processing jobs")


@router.post("/{job_id}/pause")
async def pause_job(job_id: str):
    """Pause a processing job"""
    return await control_job_action(job_id, "pause")


@router.post("/{job_id}/resume")
async def resume_job(job_id: str):
    """Resume a processing job"""
    return await control_job_action(job_id, "resume")


@router.post("/{job_id}/stop")
async def stop_job(job_id: str):
    """Stop a processing job"""
    return await control_job_action(job_id, "stop")


@router.post("/{job_id}/restart")
async def restart_interrupted_job(job_id: str, background_tasks: BackgroundTasks):
    """
    Restart an interrupted job.

    This will:
    1. Check if there's a cached download available (reuse it)
    2. Create a new job with same configuration
    3. Start processing (with fresh download if needed)
    """
    try:
        sb = _get_supabase()

        # Get the original job details
        job_result = sb.table('processing_jobs').select('*').eq('id', job_id).execute()
        if not job_result.data:
            raise HTTPException(status_code=404, detail="Job not found")

        original_job = job_result.data[0]

        # Only allow restarting interrupted/failed/stopped jobs
        if original_job['status'] not in ['interrupted', 'failed', 'stopped']:
            raise HTTPException(
                status_code=400,
                detail=f"Can only restart interrupted, failed, or stopped jobs. Current status: {original_job['status']}"
            )

        mailbox_id = original_job['mailbox_id']

        # Get mailbox details
        mailbox_result = sb.table('mailboxes').select('*').eq('id', mailbox_id).execute()
        if not mailbox_result.data:
            raise HTTPException(status_code=404, detail="Associated mailbox not found")

        mailbox = mailbox_result.data[0]
        connection_config = mailbox.get('connection_config', {})
        google_drive_file_id = connection_config.get('google_drive_file_id')

        # Check for cached download
        cached_file = None
        if google_drive_file_id:
            cache_result = sb.table('downloaded_files').select('*').eq(
                'google_drive_file_id', google_drive_file_id
            ).eq('is_valid', True).execute()

            if cache_result.data:
                cached = cache_result.data[0]
                cached_path = cached.get('storage_path', '')

                if os.path.exists(cached_path):
                    cached_file = cached_path
                    logger.info(f"Found cached download for restart: {cached_path}")
                else:
                    # Invalidate the cache entry since file doesn't exist
                    sb.table('downloaded_files').update({'is_valid': False}).eq('id', cached['id']).execute()
                    logger.info(f"Cached file not found, will re-download: {cached_path}")

        # Create new job
        new_job_data = {
            "job_type": original_job['job_type'],
            "mailbox_id": mailbox_id,
            "status": "pending",
            "total_records": 0,
            "processed_records": 0,
            "failed_records": 0,
            "filtered_records": 0,
            "filter_start_date": original_job.get('filter_start_date'),
            "filter_end_date": original_job.get('filter_end_date'),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        result = sb.table('processing_jobs').insert(new_job_data).execute()
        new_job_id = result.data[0]['id']

        # Mark old job as superseded
        sb.table('processing_jobs').update({
            'error_log': f'Job restarted. New job ID: {new_job_id}'
        }).eq('id', job_id).execute()

        # Build config for the new job
        config = ProcessingJobConfig(
            mailbox_id=mailbox_id,
            job_type=original_job['job_type'],
            download_first=True,
            download_threads=8,
            keep_downloaded_file=True,
            use_cached_file=True,  # Will use the cached file if available
        )

        if original_job.get('filter_start_date'):
            config.start_date = original_job['filter_start_date'][:10]  # Extract date part
        if original_job.get('filter_end_date'):
            config.end_date = original_job['filter_end_date'][:10]

        # Add mailbox connection config to processing config (required by process_emails_real)
        config.connection_config = mailbox.get('connection_config', {})
        config.mailbox_type = mailbox.get('mailbox_type')

        # Start processing in background using the same function as start_processing
        background_tasks.add_task(process_emails_real, new_job_id, config)

        return {
            "message": "Job restarted successfully",
            "new_job_id": new_job_id,
            "original_job_id": job_id,
            "cached_file_available": cached_file is not None,
            "cached_file_path": cached_file,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to restart job {job_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to restart job: {str(e)}")


@router.delete("/{job_id}")
async def delete_job(job_id: str):
    """Delete a processing job"""

    try:
        _get_supabase().table('processing_jobs').delete().eq('id', job_id).execute()

        # Remove from memory if exists
        with _active_jobs_lock:
            _active_jobs.pop(job_id, None)

        return {"message": "Job deleted successfully"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete job: {str(e)}")


@router.post("/{job_id}/reprocess")
async def reprocess_emails(job_id: str, background_tasks: BackgroundTasks):
    """
    Re-sync a mailbox from the mail provider to backfill attachment names
    and provider web links for existing emails.  Uses the same upsert path
    as live sync so existing rows are updated in-place.
    """
    try:
        job_result = _get_supabase().table('processing_jobs').select('*').eq('id', job_id).execute()
        if not job_result.data:
            raise HTTPException(status_code=404, detail="Job not found")

        job = job_result.data[0]
        mailbox_id = job['mailbox_id']

        # Look up mailbox to get type + connection config
        mb_result = _get_supabase().table('mailboxes').select(
            'id, mailbox_type, connection_config'
        ).eq('id', mailbox_id).single().execute()

        if not mb_result.data:
            raise HTTPException(status_code=404, detail="Mailbox not found")

        mailbox = mb_result.data
        mailbox_type = mailbox.get('mailbox_type', '')

        if mailbox_type not in ('outlook_live', 'outlook'):
            raise HTTPException(
                status_code=400,
                detail=f"Reprocess not supported for mailbox type '{mailbox_type}'. Only Outlook mailboxes can be re-synced.",
            )

        # Create a tracking job
        reprocess_job = {
            "job_type": "reprocessing",
            "mailbox_id": mailbox_id,
            "status": "pending",
            "total_records": 0,
            "processed_records": 0,
            "failed_records": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        result = _get_supabase().table('processing_jobs').insert(reprocess_job).execute()
        new_job_id = result.data[0]['id']

        background_tasks.add_task(run_reprocessing, new_job_id, mailbox)
        return {"message": "Reprocessing started — re-syncing from mail provider", "job_id": new_job_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start reprocessing: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{job_id}/errors")
async def get_processing_errors(
    job_id: str,
    limit: int = 50,
    offset: int = 0,
):
    """
    Get errors for a specific processing job.

    Returns both Redis-cached errors (for active jobs) and
    database-persisted errors (for completed jobs).
    """
    try:
        # Get mailbox_id from job
        job_result = _get_supabase().table('processing_jobs').select('mailbox_id').eq('id', job_id).single().execute()
        if not job_result.data:
            raise HTTPException(status_code=404, detail="Job not found")

        mailbox_id = job_result.data.get('mailbox_id')
        if not mailbox_id:
            raise HTTPException(status_code=400, detail="Job has no associated mailbox")

        # Get errors from Redis (for active jobs)
        redis_errors = []
        redis_total = 0
        if _progress_manager:
            redis_errors = _progress_manager.get_errors(job_id, limit, offset)
            error_counts = _progress_manager.get_error_counts(job_id)
            redis_total = error_counts.get('total', 0)

        # Get failed emails from database (for persistence and completed jobs)
        db_result = _get_supabase().table('emails').select(
            'id, message_id, subject, sender_email, sent_date, '
            'processing_error, processing_attempts, last_processing_attempt'
        ).eq(
            'mailbox_id', mailbox_id
        ).eq(
            'processing_status', 'failed'
        ).order(
            'last_processing_attempt', desc=True
        ).range(offset, offset + limit - 1).execute()

        db_errors = db_result.data or []

        # Get total failed count
        count_result = _get_supabase().table('emails').select(
            'id', count='exact'
        ).eq('mailbox_id', mailbox_id).eq('processing_status', 'failed').execute()
        db_total = count_result.count or 0

        # Use the higher count between Redis and DB
        total_failed = max(redis_total, db_total)

        # Format response - prefer DB records as they have email IDs
        emails = []
        seen_message_ids = set()

        for err in db_errors:
            emails.append({
                'id': err.get('id', ''),
                'message_id': err.get('message_id'),
                'subject': err.get('subject'),
                'sender_email': err.get('sender_email'),
                'sent_date': err.get('sent_date'),
                'processing_error': err.get('processing_error'),
                'processing_attempts': err.get('processing_attempts', 1),
                'last_processing_attempt': err.get('last_processing_attempt'),
            })
            if err.get('message_id'):
                seen_message_ids.add(err.get('message_id'))

        # Add Redis errors that aren't in DB yet (from active processing)
        for err in redis_errors:
            if err.get('message_id') and err.get('message_id') not in seen_message_ids:
                emails.append({
                    'id': err.get('email_id', ''),
                    'message_id': err.get('message_id'),
                    'subject': err.get('subject'),
                    'sender_email': err.get('sender_email'),
                    'sent_date': None,
                    'processing_error': err.get('error_message'),
                    'processing_attempts': err.get('attempt_number', 1),
                    'last_processing_attempt': err.get('timestamp'),
                })

        return {
            'job_id': job_id,
            'mailbox_id': mailbox_id,
            'total_failed': total_failed,
            'emails': emails[:limit],
            'has_more': total_failed > offset + limit,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get processing errors: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{job_id}/errors/summary")
async def get_error_summary(job_id: str):
    """Get aggregated error summary for a processing job."""
    try:
        # Get mailbox_id from job
        job_result = _get_supabase().table('processing_jobs').select(
            'mailbox_id, error_summary, failed_records'
        ).eq('id', job_id).single().execute()

        if not job_result.data:
            raise HTTPException(status_code=404, detail="Job not found")

        job = job_result.data
        mailbox_id = job.get('mailbox_id')

        # Try Redis first for active jobs
        if _progress_manager:
            summary = _progress_manager.get_error_summary(job_id)
            if summary.get('total_errors', 0) > 0:
                return summary

        # Check stored error_summary in processing_jobs
        if job.get('error_summary'):
            error_summary = job.get('error_summary')
            return {
                'total_errors': error_summary.get('total_errors', job.get('failed_records', 0)),
                'error_types': error_summary.get('error_types', {}),
                'sample_errors': error_summary.get('sample_errors', []),
                'has_more_errors': False,
            }

        # Return basic summary from failed_records count
        return {
            'total_errors': job.get('failed_records', 0),
            'error_types': {},
            'sample_errors': [],
            'has_more_errors': False,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get error summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{job_id}/retry-failed")
async def retry_failed_emails(job_id: str, max_attempts: int = 3):
    """Reset failed emails to pending status for retry processing."""
    try:
        # Get mailbox_id from job
        job_result = _get_supabase().table('processing_jobs').select('mailbox_id').eq('id', job_id).single().execute()
        if not job_result.data:
            raise HTTPException(status_code=404, detail="Job not found")

        mailbox_id = job_result.data.get('mailbox_id')
        if not mailbox_id:
            raise HTTPException(status_code=400, detail="Job has no associated mailbox")

        # Get emails that can be retried
        emails_to_reset = _get_supabase().table('emails').select('id').eq(
            'mailbox_id', mailbox_id
        ).eq(
            'processing_status', 'failed'
        ).lt(
            'processing_attempts', max_attempts
        ).execute()

        if not emails_to_reset.data:
            return {
                'job_id': job_id,
                'mailbox_id': mailbox_id,
                'emails_reset': 0,
                'message': 'No emails to retry (all have exceeded max attempts or none failed)',
            }

        email_ids = [e['id'] for e in emails_to_reset.data]

        # Reset them to pending
        _get_supabase().table('emails').update({
            'processing_status': 'pending',
            'processing_error': None,
        }).in_('id', email_ids).execute()

        # Clear Redis error cache for this job
        if _progress_manager:
            _progress_manager.clear_errors(job_id)

        # Update job status to allow reprocessing
        _get_supabase().table('processing_jobs').update({
            'status': 'pending'
        }).eq('id', job_id).eq('status', 'completed').execute()

        logger.info(f"Reset {len(email_ids)} failed emails for retry in job {job_id}")

        return {
            'job_id': job_id,
            'mailbox_id': mailbox_id,
            'emails_reset': len(email_ids),
            'message': f'Reset {len(email_ids)} failed emails for retry',
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retry failed emails: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== Standalone endpoint functions (mounted separately in main.py) ========

async def start_processing(mailbox_id: str, config: ProcessingJobConfig, background_tasks: BackgroundTasks):
    """Start email processing for a mailbox.

    Mounted at POST /api/mailboxes/{mailbox_id}/process in main.py.
    """

    try:
        # Get mailbox info
        mailbox_result = _get_supabase().table('mailboxes').select('*').eq('id', mailbox_id).execute()
        if not mailbox_result.data:
            raise HTTPException(status_code=404, detail="Mailbox not found")

        mailbox = mailbox_result.data[0]

        # Check for existing active jobs for this mailbox
        existing_jobs = _get_supabase().table('processing_jobs').select('id, status').eq(
            'mailbox_id', mailbox_id
        ).in_('status', ['pending', 'running']).execute()

        if existing_jobs.data:
            active_job = existing_jobs.data[0]
            raise HTTPException(
                status_code=409,  # Conflict
                detail=f"A job is already {active_job['status']} for this mailbox. "
                       f"Please wait for it to complete or stop it first. "
                       f"Job ID: {active_job['id']}"
            )

        # Create processing job with filter parameters for audit trail
        job_data = {
            "job_type": config.job_type,
            "mailbox_id": mailbox_id,
            "status": "pending",
            "total_records": config.total_records,
            "processed_records": 0,
            "failed_records": 0,
            "filtered_records": 0,  # Track emails skipped by date filter
            "created_at": datetime.now(timezone.utc).isoformat(),
            "started_at": None,
            "completed_at": None,
            "error_log": [],
            # Stage 2: Store date filter parameters for visibility/audit
            "filter_start_date": config.start_date if config.start_date else None,
            "filter_end_date": config.end_date if config.end_date else None,
        }

        # Insert job into database
        result = _get_supabase().table('processing_jobs').insert(job_data).execute()
        job = result.data[0]

        # Store job in memory for tracking
        with _active_jobs_lock:
            _active_jobs[job['id']] = {
                **job,
                "mailbox_name": mailbox['name'],
                "mailbox_type": mailbox['mailbox_type'],
            }

        # Add mailbox connection config to processing config
        config.connection_config = mailbox['connection_config']
        config.mailbox_type = mailbox['mailbox_type']
        config.mailbox_id = mailbox_id

        # Start REAL background processing (not simulated)
        background_tasks.add_task(process_emails_real, job['id'], config)

        logger.info(f"Started processing job {job['id']} for mailbox {mailbox['name']}")

        return job

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start processing: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start processing: {str(e)}")


async def invalidate_cached_download(cache_id: str):
    """Invalidate (mark as invalid) a cached download.

    Mounted at DELETE /api/cached-downloads/{cache_id} in main.py.
    """
    try:
        sb = _get_supabase()
        result = sb.table('downloaded_files').update({'is_valid': False}).eq('id', cache_id).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Cache entry not found")

        return {"success": True, "message": "Cache invalidated"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to invalidate cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== Background / helper functions ========================================

def get_job_progress(job_id: str) -> dict:
    """Get progress from Redis (fast) or database (fallback)"""
    if _progress_manager:
        progress = _progress_manager.get_progress(job_id)
        if progress:
            return progress

    # Fallback to database
    return {
        "processed": 0,
        "failed": 0,
        "total_records": 0,
        "emails_per_second": 0,
        "estimated_seconds_remaining": 0,
    }


def update_job_progress_redis(job_id: str, processed: int, failed: int = 0, sync_to_db: bool = False):
    """
    Update job progress in Redis.

    Args:
        job_id: Job ID
        processed: Number of emails processed
        failed: Number of failed emails
        sync_to_db: If True, also sync to database immediately

    Returns:
        True if should sync to database (every 100 emails or 30 seconds)

    Note: WebSocket broadcasts are handled by the shared progress_tracker module.
    """
    if not _progress_manager:
        # Redis not available, always sync to DB
        return True

    # Update Redis
    _progress_manager.update_progress(job_id, processed, failed)

    # Determine if we should sync to database
    # Sync every 100 emails to reduce DB load but ensure persistence
    should_sync = sync_to_db or (processed > 0 and processed % 100 == 0)

    return should_sync


async def update_job_status(job_id: str, status: str, updates: Dict[str, Any]):
    """Update job status in database and memory"""

    update_data = {"status": status, **updates}

    # Update database
    _get_supabase().table('processing_jobs').update(update_data).eq('id', job_id).execute()

    # Update in-memory job
    with _active_jobs_lock:
        if job_id in _active_jobs:
            _active_jobs[job_id].update(update_data)

    # Broadcast status update via WebSocket
    try:
        manager = get_connection_manager()
        if manager:
            # Get mailbox_id for the job
            mailbox_id = None
            with _active_jobs_lock:
                if job_id in _active_jobs:
                    mailbox_id = _active_jobs[job_id].get('mailbox_id')

            if not mailbox_id:
                job_result = _get_supabase().table('processing_jobs').select('mailbox_id').eq('id', job_id).execute()
                if job_result.data:
                    mailbox_id = job_result.data[0].get('mailbox_id')

            if mailbox_id:
                # Get current progress from Redis for complete update
                progress = get_job_progress(job_id)
                await manager.broadcast_job_update(job_id, mailbox_id, {
                    'status': status,
                    'processed_records': progress.get('processed', 0),
                    'failed_records': progress.get('failed', 0),
                    'total_records': progress.get('total_records', 0),
                    **updates,
                })
    except Exception as e:
        logger.debug(f"WebSocket broadcast failed (non-critical): {e}")


async def control_job_action(job_id: str, action: str):
    """Control processing job (pause, resume, stop)"""

    valid_actions = ["pause", "resume", "stop"]
    if action not in valid_actions:
        raise HTTPException(status_code=400, detail=f"Invalid action. Must be one of: {valid_actions}")

    try:
        status_map = {
            "pause": "paused",
            "resume": "running",
            "stop": "stopped",
        }

        new_status = status_map[action]
        update_data = {"status": new_status}

        if action == "stop":
            update_data["completed_at"] = datetime.now(timezone.utc).isoformat()

        _get_supabase().table('processing_jobs').update(update_data).eq('id', job_id).execute()

        return {"message": f"Job {action}d successfully", "status": new_status}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to {action} job: {str(e)}")


async def process_emails_real(job_id: str, config: ProcessingJobConfig):
    """
    REAL email processing (replaces simulate_processing)
    Processes actual emails from MBOX/IMAP/POP3/Outlook sources

    Note: Gmail/Outlook LIVE jobs are handled by their own background tasks
    (_run_date_range_fetch in gmail.py/outlook.py) and should skip this function.
    """

    downloaded_file_path = None  # Track downloaded file for cleanup
    cache_entry_id = None  # Track cache entry for updating last_used_at
    google_drive_file_id = None  # Track for cache registration

    try:
        logger.info(f"Starting REAL email processing for job {job_id}")

        # Handle Gmail/Outlook LIVE jobs - trigger their sync services instead
        if config.mailbox_type in ['gmail', 'outlook_live']:
            logger.info(f"Job {job_id} is for {config.mailbox_type} LIVE mailbox - triggering sync service")

            # Update job status to running
            await update_job_status(job_id, "running", {
                "started_at": datetime.now(timezone.utc).isoformat()
            })

            try:
                if config.mailbox_type == 'outlook_live' and _outlook_sync_service:
                    # Trigger Outlook sync for this mailbox
                    await _outlook_sync_service.trigger_mailbox_sync(config.mailbox_id)
                    await update_job_status(job_id, "completed", {
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                        "error_log": ["Outlook LIVE sync triggered successfully. Emails will sync in background."],
                    })
                elif config.mailbox_type == 'gmail' and _gmail_sync_service:
                    # Trigger Gmail sync for this mailbox
                    await _gmail_sync_service.trigger_mailbox_sync(config.mailbox_id)
                    await update_job_status(job_id, "completed", {
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                        "error_log": ["Gmail LIVE sync triggered successfully. Emails will sync in background."],
                    })
                else:
                    await update_job_status(job_id, "failed", {
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                        "error_log": [f"{config.mailbox_type} sync service not available. Please check server configuration."],
                    })
            except Exception as sync_error:
                logger.error(f"Failed to trigger {config.mailbox_type} sync: {sync_error}")
                await update_job_status(job_id, "failed", {
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "error_log": [f"Failed to trigger sync: {str(sync_error)}"],
                })
            return

        # Register job-mailbox mapping for WebSocket broadcasts
        try:
            from ..utils.progress_tracker import register_job_mailbox
            register_job_mailbox(job_id, config.mailbox_id)
        except Exception:
            pass  # Non-critical

        # Immediately update status to 'running' so user sees it's active
        await update_job_status(job_id, "running", {
            "started_at": datetime.now(timezone.utc).isoformat()
        })

        # Check if parallel download is requested for Google Drive files
        connection_config = config.connection_config.copy() if config.connection_config else {}

        if (config.download_first and
                connection_config.get('file_source') == 'google_drive' and
                connection_config.get('google_drive_file_id')):

            google_drive_file_id = connection_config.get('google_drive_file_id')
            file_name = connection_config.get('google_drive_file_name', 'download')

            # Check for cached download if use_cached_file is enabled (default: True)
            use_cached = config.use_cached_file if config.use_cached_file is not None else True

            if use_cached:
                logger.info(f"Checking for cached download of {google_drive_file_id}")
                sb = _get_supabase()
                cache_result = sb.table('downloaded_files').select('*').eq(
                    'google_drive_file_id', google_drive_file_id
                ).eq('is_valid', True).execute()

                if cache_result.data:
                    cached = cache_result.data[0]
                    cached_path = cached.get('storage_path', '')

                    # For local storage, verify file still exists
                    if cached.get('storage_type') == 'local' and os.path.exists(cached_path):
                        logger.info(f"Using cached download: {cached_path}")

                        # Update last_used_at
                        cache_entry_id = cached['id']
                        sb.table('downloaded_files').update({
                            'last_used_at': datetime.now(timezone.utc).isoformat(),
                            'last_job_id': job_id,
                        }).eq('id', cache_entry_id).execute()

                        # Use cached file instead of downloading
                        downloaded_file_path = cached_path
                        connection_config['file_source'] = 'local'
                        connection_config['file_path'] = cached_path
                        connection_config.pop('google_drive_file_id', None)
                        connection_config.pop('google_drive_file_name', None)

                        # Update job status to indicate cache was used
                        if _progress_manager:
                            _progress_manager.update_progress(
                                job_id, 0, 0,
                                status='running',
                                download_percent=100,
                                using_cache=True,
                            )
                    else:
                        # Cached file doesn't exist - mark as invalid
                        logger.warning(f"Cached file no longer exists: {cached_path}")
                        sb.table('downloaded_files').update({'is_valid': False}).eq('id', cached['id']).execute()

            # If no cached file was found/used, proceed with download
            if not downloaded_file_path:
                logger.info(f"Parallel download requested for job {job_id} with {config.download_threads} threads")

                # Import parallel downloader
                from ..storage.parallel_downloader import ParallelDownloader

                # Get access token from stored credentials and refresh if needed
                user_id = connection_config.get('user_id', 'default')
                tokens_result = _get_supabase().table('user_integrations').select(
                    'access_token,refresh_token'
                ).eq('user_id', user_id).eq('provider', 'google_drive').execute()

                if not tokens_result.data:
                    raise Exception("No Google Drive credentials found. Please re-authenticate.")

                access_token = tokens_result.data[0].get('access_token')
                refresh_token = tokens_result.data[0].get('refresh_token')

                if not access_token:
                    raise Exception("Invalid Google Drive access token")

                # Refresh the access token to ensure it's valid
                if refresh_token:
                    try:
                        from google.oauth2.credentials import Credentials
                        from google.auth.transport.requests import Request

                        credentials = Credentials(
                            token=access_token,
                            refresh_token=refresh_token,
                            token_uri="https://oauth2.googleapis.com/token",
                            client_id=os.getenv("GOOGLE_CLIENT_ID"),
                            client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
                        )

                        # Force refresh the token
                        credentials.refresh(Request())
                        access_token = credentials.token

                        # Store the new access token
                        _update_user_access_token(user_id, access_token)
                        logger.info(f"Refreshed Google Drive access token for parallel download")
                    except Exception as refresh_error:
                        logger.warning(f"Token refresh failed, using existing token: {refresh_error}")

                # Progress callback to update Redis
                def download_progress_callback(downloaded: int, total: int, speed_mbps: float):
                    if _progress_manager and total > 0:
                        percent = int(downloaded / total * 100)
                        # Store download progress in Redis (using negative values to indicate download phase)
                        _progress_manager.update_progress(
                            job_id, 0, 0,
                            status='downloading',
                            download_percent=percent,
                            download_speed_mbps=round(speed_mbps, 1),
                        )

                # Perform parallel download with error logging
                logger.info(f"Starting parallel download: {file_name} ({google_drive_file_id})")
                from ..services.job_error_logger import get_error_logger
                error_logger = get_error_logger()
                downloader = ParallelDownloader(
                    access_token=access_token,
                    num_threads=config.download_threads or 8,
                    progress_callback=download_progress_callback,
                    job_id=job_id,
                    mailbox_id=str(config.mailbox_id) if config.mailbox_id else None,
                    error_logger=error_logger,
                )

                # Run download in thread pool - use persistent directory if configured
                loop = asyncio.get_running_loop()
                downloaded_file_path = await loop.run_in_executor(
                    _executor,
                    lambda: downloader.download(google_drive_file_id, file_name, output_dir=_download_dir),
                )

                if not downloaded_file_path:
                    raise Exception("Parallel download failed")

                logger.info(f"Parallel download complete: {downloaded_file_path}")

                # Register downloaded file in cache for future reuse
                keep_file = config.keep_downloaded_file if config.keep_downloaded_file is not None else True
                if keep_file:
                    try:
                        file_size = os.path.getsize(downloaded_file_path) if os.path.exists(downloaded_file_path) else 0
                        sb = _get_supabase()
                        cache_insert = sb.table('downloaded_files').upsert({
                            'google_drive_file_id': google_drive_file_id,
                            'file_name': file_name,
                            'file_size': file_size,
                            'storage_type': 'local',
                            'storage_path': downloaded_file_path,
                            'mailbox_id': str(config.mailbox_id) if config.mailbox_id else None,
                            'last_job_id': job_id,
                            'downloaded_at': datetime.now(timezone.utc).isoformat(),
                            'last_used_at': datetime.now(timezone.utc).isoformat(),
                            'is_valid': True,
                        }, on_conflict='google_drive_file_id').execute()

                        if cache_insert.data:
                            cache_entry_id = cache_insert.data[0]['id']
                            logger.info(f"Registered download in cache: {cache_entry_id}")
                    except Exception as cache_error:
                        logger.warning(f"Failed to register download in cache: {cache_error}")

                # Update connection config to use local file instead of streaming
                connection_config['file_source'] = 'local'
                connection_config['file_path'] = downloaded_file_path
                # Remove Google Drive specific fields
                connection_config.pop('google_drive_file_id', None)
                connection_config.pop('google_drive_file_name', None)

            # Download complete (either from cache or fresh download) - update status to 'running'
            logger.info(f"Download phase complete for job {job_id}, transitioning to processing phase")

            # Update database status to 'running'
            await update_job_status(job_id, "running", {})

            # Update Redis to clear download state and show processing phase
            if _progress_manager:
                _progress_manager.update_progress(
                    job_id, 0, 0,
                    status='running',
                    download_percent=100,  # Keep at 100 to show download completed
                    download_complete=True,  # Flag to indicate download phase is done
                )

        # Initialize processor with actual configuration (may be modified for local file)
        from ..services.job_error_logger import get_error_logger
        from ..processors.email_processor import EmailProcessor

        error_logger = get_error_logger()
        processor = EmailProcessor(
            mailbox_id=config.mailbox_id,
            connection_config=connection_config,
            error_logger=error_logger,
        )

        # Initialize the extractor
        logger.info(f"Initializing {config.mailbox_type} extractor for job {job_id}...")
        if not processor.initialize_extractor(config.mailbox_type):
            error_msg = f"Failed to initialize {config.mailbox_type} extractor"
            logger.error(error_msg)

            # Check if job was already stopped (don't override stopped status)
            job_result = _get_supabase().table('processing_jobs').select('status').eq('id', job_id).execute()
            if job_result.data and job_result.data[0].get('status') not in ['stopped', 'cancelled']:
                await update_job_status(job_id, "failed", {
                    "error_log": [error_msg],
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                })
            else:
                logger.warning(f"Extractor initialization failed after job was stopped: {error_msg}")

            return

        # Get total email count for progress estimation (fast, doesn't process emails)
        try:
            total_emails = processor.extractor.get_email_count()
            if total_emails:
                logger.info(f"Estimated total emails in mailbox: {total_emails}")
                # Update job with accurate total_records
                _get_supabase().table('processing_jobs').update({
                    'total_records': total_emails
                }).eq('id', job_id).execute()
                # Update Redis cache too
                if _progress_manager:
                    _progress_manager.update_progress(job_id, 0, 0, total_records=total_emails)
            else:
                logger.warning("Could not estimate total email count - using config value or None")
        except Exception as e:
            logger.warning(f"Failed to get email count (will proceed without estimate): {e}")

        # Determine max_emails: prefer new max_emails field, fallback to deprecated total_records
        effective_max_emails = config.max_emails or config.total_records  # None means process all

        # Parse date filters
        date_filter = None
        if config.start_date or config.end_date:
            date_filter = {}
            if config.start_date:
                try:
                    date_filter['start_date'] = datetime.fromisoformat(config.start_date).replace(tzinfo=timezone.utc)
                    logger.info(f"Date filter: start_date = {config.start_date}")
                except ValueError:
                    logger.warning(f"Invalid start_date format: {config.start_date}, expected YYYY-MM-DD")
            if config.end_date:
                try:
                    # End date should include the entire day
                    date_filter['end_date'] = datetime.fromisoformat(config.end_date).replace(
                        hour=23, minute=59, second=59, tzinfo=timezone.utc
                    )
                    logger.info(f"Date filter: end_date = {config.end_date}")
                except ValueError:
                    logger.warning(f"Invalid end_date format: {config.end_date}, expected YYYY-MM-DD")

        logger.info(
            f"Processing config: max_emails={effective_max_emails}, "
            f"batch_size={config.batch_size or 250}, date_filter={date_filter}"
        )

        # Process emails with streaming
        # Run in dedicated thread pool to avoid blocking event loop
        # Using custom executor allows multiple concurrent jobs
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            _executor,  # Custom thread pool with 20 workers
            lambda: processor.process_emails(
                job_id=job_id,
                max_emails=effective_max_emails,  # max_emails (None for all)
                batch_size=config.batch_size or 250,  # batch_size for DB inserts (auto-splits on timeout)
                skip_duplicates=True,  # skip_duplicates
                enable_categorization=config.enable_categorization,  # enable_categorization
                date_filter=date_filter,  # NEW: date-based filtering
            )
        )

        logger.info(f"Processing completed for job {job_id}: {result}")

        # Cleanup
        processor.disconnect()

        # Cleanup downloaded file if parallel download was used AND keep_downloaded_file is False
        keep_file = config.keep_downloaded_file if config.keep_downloaded_file is not None else True
        if downloaded_file_path and not keep_file:
            try:
                if os.path.exists(downloaded_file_path):
                    os.remove(downloaded_file_path)
                    logger.info(f"Cleaned up downloaded file: {downloaded_file_path}")

                    # Mark cache entry as invalid since file is deleted
                    if cache_entry_id:
                        try:
                            _get_supabase().table('downloaded_files').update({
                                'is_valid': False
                            }).eq('id', cache_entry_id).execute()
                        except Exception:
                            pass

                # Also try to remove the temp directory
                parent_dir = os.path.dirname(downloaded_file_path)
                if parent_dir and os.path.exists(parent_dir) and not os.listdir(parent_dir):
                    os.rmdir(parent_dir)
            except Exception as cleanup_error:
                logger.warning(f"Failed to cleanup downloaded file: {cleanup_error}")
        elif downloaded_file_path and keep_file:
            logger.info(f"Keeping downloaded file for future reuse: {downloaded_file_path}")

    except Exception as e:
        error_msg = f"Processing error: {str(e)}"
        logger.error(error_msg, exc_info=True)

        # Decide whether to keep file on error
        # If keep_downloaded_file is True (default), keep it for debugging/retry
        # If file was from cache, always keep it
        keep_file = config.keep_downloaded_file if config.keep_downloaded_file is not None else True

        if downloaded_file_path and not keep_file and not cache_entry_id:
            # Only cleanup if explicitly told not to keep AND it's not a cached file
            try:
                if os.path.exists(downloaded_file_path):
                    os.remove(downloaded_file_path)
                    logger.info(f"Cleaned up downloaded file after error: {downloaded_file_path}")
                parent_dir = os.path.dirname(downloaded_file_path)
                if parent_dir and os.path.exists(parent_dir) and not os.listdir(parent_dir):
                    os.rmdir(parent_dir)
            except Exception as cleanup_error:
                logger.warning(f"Failed to cleanup downloaded file: {cleanup_error}")
        elif downloaded_file_path:
            logger.info(f"Keeping downloaded file after error for debugging/retry: {downloaded_file_path}")

        # Check if job was already stopped (don't override stopped status)
        job_result = _get_supabase().table('processing_jobs').select('status').eq('id', job_id).execute()
        if job_result.data and job_result.data[0].get('status') in ['stopped', 'cancelled']:
            logger.warning(f"Exception occurred after job was stopped: {error_msg}")
        else:
            # Not stopped - genuine failure
            await update_job_status(job_id, "failed", {
                "error_log": [error_msg],
                "completed_at": datetime.now(timezone.utc).isoformat(),
            })


async def run_reprocessing(job_id: str, mailbox: dict):
    """
    Re-extract emails from the mail provider (Outlook Graph API) and upsert
    them into the DB.  This backfills attachment filenames, sizes, and
    provider_web_link for all existing emails.
    """
    mailbox_id = mailbox['id']
    config = mailbox.get('connection_config') or {}

    try:
        from ..extractors.outlook_extractor import OutlookExtractor
        from ..database.operations import EmailOperations

        logger.info(f"Reprocessing job {job_id}: re-syncing mailbox {mailbox_id} from Outlook Graph API")

        await update_job_status(job_id, "running", {
            "started_at": datetime.now(timezone.utc).isoformat()
        })

        # Connect to Outlook
        extractor = OutlookExtractor({
            'access_token': config.get('outlook_access_token') or config.get('access_token', ''),
            'refresh_token': config.get('outlook_refresh_token') or config.get('refresh_token'),
            'mailbox_id': mailbox_id,
            # Intentionally omit delta_links -> full re-fetch, not incremental
        })

        if not extractor.connect():
            error = extractor.auth_error or 'Failed to connect to Outlook API'
            await update_job_status(job_id, "failed", {"error_log": [error]})
            return

        email_ops = EmailOperations()
        success = 0
        failed = 0
        batch = []
        batch_size = 100

        for email in extractor.extract_emails():
            batch.append(email)
            if len(batch) >= batch_size:
                result = email_ops.batch_insert_emails(batch, mailbox_id)
                success += result.get('success', 0)
                failed += result.get('failed', 0)
                batch = []

                await update_job_status(job_id, "running", {
                    "processed_records": success,
                    "failed_records": failed,
                })
                logger.info(f"Reprocess progress: {success} upserted, {failed} failed")

                # Check for stop/cancel
                job_check = _get_supabase().table('processing_jobs').select('status').eq('id', job_id).execute()
                if job_check.data and job_check.data[0]['status'] in ('stopped', 'cancelled'):
                    logger.info(f"Reprocessing job {job_id} stopped by user")
                    break

        # Flush remaining
        if batch:
            result = email_ops.batch_insert_emails(batch, mailbox_id)
            success += result.get('success', 0)
            failed += result.get('failed', 0)

        extractor.disconnect()

        await update_job_status(job_id, "completed", {
            "processed_records": success,
            "failed_records": failed,
            "total_records": success + failed,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
        logger.info(f"Reprocessing job {job_id} done: {success} upserted, {failed} failed")

    except Exception as e:
        error_msg = f"Reprocessing error: {e}"
        logger.error(error_msg, exc_info=True)
        job_result = _get_supabase().table('processing_jobs').select('status').eq('id', job_id).execute()
        if job_result.data and job_result.data[0].get('status') in ['stopped', 'cancelled']:
            logger.warning(f"Reprocessing exception after stop: {error_msg}")
        else:
            await update_job_status(job_id, "failed", {
                "error_log": [error_msg],
                "completed_at": datetime.now(timezone.utc).isoformat(),
            })


async def cleanup_orphaned_jobs():
    """
    Mark any jobs that were running/pending/downloading when server restarted as 'interrupted'.
    This prevents the frontend from spinning forever waiting for a dead job.
    """
    try:
        sb = _get_supabase()

        # Find jobs that are stuck in running/pending/downloading status
        result = sb.table('processing_jobs').select('id, status, mailbox_id').in_(
            'status', ['running', 'pending', 'downloading']
        ).execute()

        orphaned_jobs = result.data or []

        if orphaned_jobs:
            logger.info(f"Found {len(orphaned_jobs)} orphaned jobs from previous session, marking as interrupted")

            for job in orphaned_jobs:
                job_id = job['id']
                try:
                    sb.table('processing_jobs').update({
                        'status': 'interrupted',
                        'error_log': 'Job was interrupted by server restart. You can restart this job.',
                        'completed_at': datetime.now(timezone.utc).isoformat(),
                    }).eq('id', job_id).execute()

                    # Clear stale Redis progress so frontend doesn't see
                    # old "running" data overriding the DB "interrupted" status
                    if _progress_manager:
                        _progress_manager.delete_progress(job_id)

                    logger.info(f"Marked job {job_id} as interrupted (DB + Redis cleared)")
                except Exception as e:
                    logger.warning(f"Failed to update job {job_id}: {e}")

            logger.info(f"Cleanup complete: {len(orphaned_jobs)} jobs marked as interrupted")
        else:
            logger.info("No orphaned jobs found during startup")

    except Exception as e:
        logger.error(f"Error during orphaned job cleanup: {e}")


def sync_redis_to_database():
    """Sync all Redis progress to database before shutdown"""
    if not _progress_manager:
        return

    try:
        active_jobs = _progress_manager.get_all_active_jobs()
        logger.info(f"Syncing {len(active_jobs)} jobs from Redis to database...")

        for job_id in active_jobs:
            try:
                progress = _progress_manager.get_progress(job_id)
                if progress:
                    _get_supabase().table('processing_jobs').update({
                        'processed_records': progress['processed'],
                        'failed_records': progress['failed'],
                    }).eq('id', job_id).execute()
                    logger.info(f"Synced job {job_id}: {progress['processed']} processed")
            except Exception as e:
                logger.error(f"Failed to sync job {job_id} to database: {e}")
    except Exception as e:
        logger.error(f"Failed to sync Redis to database: {e}")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _update_user_access_token(user_id: str, new_access_token: str) -> bool:
    """Update user's access token after refresh"""
    try:
        _get_supabase().table('user_integrations').update({
            'access_token': new_access_token,
            'updated_at': datetime.now(timezone.utc).isoformat(),
        }).eq('user_id', user_id).eq('provider', 'google_drive').execute()

        return True

    except Exception as e:
        logger.error(f"Failed to update access token for user {user_id}: {e}")
        return False
