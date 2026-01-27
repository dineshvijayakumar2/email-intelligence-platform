"""
Error Handling API Router

Provides endpoints for viewing and managing processing errors.

Stage 2 Phase 1 - Error Handling Implementation

This router provides two types of error views:
1. Job Errors (job_errors table) - All errors: download, extraction, processing, etc.
2. Failed Emails (emails table) - Email-specific failures with retry capability
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/processing-jobs", tags=["errors"])


# =========================================================================
# Pydantic Models
# =========================================================================

class ErrorSummary(BaseModel):
    """Error summary response model"""
    total_errors: int
    error_types: Dict[str, Any]
    sample_errors: List[Dict]
    has_more_errors: bool = False


class FailedEmail(BaseModel):
    """Failed email record"""
    id: str
    message_id: Optional[str]
    subject: Optional[str]
    sender_email: Optional[str]
    sent_date: Optional[datetime]
    processing_error: Optional[str]
    processing_attempts: int
    last_processing_attempt: Optional[datetime]


class FailedEmailsResponse(BaseModel):
    """Response for failed emails list"""
    job_id: str
    mailbox_id: str
    total_failed: int
    emails: List[FailedEmail]
    has_more: bool


class RetryResponse(BaseModel):
    """Response for retry operation"""
    job_id: str
    mailbox_id: str
    emails_reset: int
    message: str


# New models for job_errors table
class JobError(BaseModel):
    """Single job error record from job_errors table"""
    id: str
    error_phase: str
    error_type: str
    error_severity: str
    error_message: str
    error_stack: Optional[str] = None
    context_type: Optional[str] = None
    context_id: Optional[str] = None
    context_details: Optional[Dict[str, Any]] = None
    is_retryable: bool = True
    retry_count: int = 0
    resolved_at: Optional[datetime] = None
    created_at: datetime


class JobErrorsResponse(BaseModel):
    """Response for job errors list"""
    job_id: str
    total_errors: int
    unresolved_errors: int
    errors: List[JobError]
    has_more: bool


class JobErrorsSummary(BaseModel):
    """Comprehensive error summary from job_errors table"""
    total_errors: int
    unresolved_errors: int
    retryable_errors: int
    by_phase: Dict[str, int]
    by_type: Dict[str, int]
    by_severity: Dict[str, int]
    recent_errors: List[Dict[str, Any]]


# These will be injected from main.py
_error_tracker = None
_db_error_tracker = None
_supabase = None
_redis = None
_job_error_logger = None


def init_error_router(error_tracker, db_error_tracker, supabase_client, redis_client, job_error_logger=None):
    """Initialize the router with dependencies"""
    global _error_tracker, _db_error_tracker, _supabase, _redis, _job_error_logger
    _error_tracker = error_tracker
    _db_error_tracker = db_error_tracker
    _supabase = supabase_client
    _redis = redis_client
    _job_error_logger = job_error_logger


def get_mailbox_id_for_job(job_id: str) -> Optional[str]:
    """Get mailbox_id from job_id"""
    try:
        result = _supabase.table('processing_jobs').select(
            'mailbox_id'
        ).eq('id', job_id).single().execute()
        return result.data.get('mailbox_id') if result.data else None
    except Exception as e:
        logger.error(f"Failed to get mailbox_id for job {job_id}: {e}")
        return None


@router.get("/{job_id}/errors", response_model=FailedEmailsResponse)
async def get_processing_errors(
    job_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0)
):
    """
    Get errors for a specific processing job.

    Returns both Redis-cached errors (for active jobs) and
    database-persisted errors (for completed jobs).

    Args:
        job_id: UUID of the processing job
        limit: Maximum number of errors to return (1-500)
        offset: Offset for pagination

    Returns:
        FailedEmailsResponse with error details
    """
    # Get mailbox_id from job
    mailbox_id = get_mailbox_id_for_job(job_id)
    if not mailbox_id:
        # Return empty response if job has no mailbox (e.g., file-based processing)
        return FailedEmailsResponse(
            job_id=job_id,
            mailbox_id='',
            total_failed=0,
            emails=[],
            has_more=False
        )

    try:
        # Try Redis first (for active jobs)
        redis_errors = []
        if _error_tracker:
            redis_errors = _error_tracker.get_errors(job_id, limit, offset)

        # Get from database (for persistence and completed jobs)
        db_errors = []
        if _db_error_tracker:
            db_errors = _db_error_tracker.get_failed_emails(mailbox_id, limit, offset)

        # Merge errors - prefer database records as they have email IDs
        # Use Redis errors for additional context during active processing
        emails = []
        seen_message_ids = set()

        for err in db_errors:
            emails.append(FailedEmail(
                id=err.get('id', ''),
                message_id=err.get('message_id'),
                subject=err.get('subject'),
                sender_email=err.get('sender_email'),
                sent_date=err.get('sent_date'),
                processing_error=err.get('processing_error'),
                processing_attempts=err.get('processing_attempts', 1),
                last_processing_attempt=err.get('last_processing_attempt')
            ))
            if err.get('message_id'):
                seen_message_ids.add(err.get('message_id'))

        # Add Redis errors that aren't in DB yet (from active processing)
        for err in redis_errors:
            if err.get('message_id') and err.get('message_id') not in seen_message_ids:
                emails.append(FailedEmail(
                    id=err.get('email_id', ''),
                    message_id=err.get('message_id'),
                    subject=err.get('subject'),
                    sender_email=err.get('sender_email'),
                    sent_date=None,
                    processing_error=err.get('error_message'),
                    processing_attempts=err.get('attempt_number', 1),
                    last_processing_attempt=datetime.fromisoformat(err.get('timestamp')) if err.get('timestamp') else None
                ))

        # Get total count
        total_failed = len(emails)
        if _error_tracker:
            counts = _error_tracker.get_error_counts(job_id)
            total_failed = max(total_failed, counts.get('total', 0))

        return FailedEmailsResponse(
            job_id=job_id,
            mailbox_id=mailbox_id,
            total_failed=total_failed,
            emails=emails[:limit],
            has_more=total_failed > offset + limit
        )

    except Exception as e:
        logger.error(f"Failed to get processing errors: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{job_id}/errors/summary", response_model=ErrorSummary)
async def get_error_summary(job_id: str):
    """
    Get aggregated error summary for a processing job.

    Returns error counts by type and sample error messages.

    Args:
        job_id: UUID of the processing job

    Returns:
        ErrorSummary with aggregated error information
    """
    mailbox_id = get_mailbox_id_for_job(job_id)
    # If no mailbox_id, we can still check processing_jobs.error_summary
    # Don't return 404 immediately

    try:
        # Try Redis first for active jobs
        if _error_tracker:
            summary = _error_tracker.get_error_summary(job_id)
            if summary.get('total_errors', 0) > 0:
                return ErrorSummary(**summary)

        # Fall back to database for completed jobs (only if mailbox_id exists)
        if _db_error_tracker and mailbox_id:
            db_summary = _db_error_tracker.get_error_summary_from_db(mailbox_id)
            if db_summary:
                return ErrorSummary(
                    total_errors=db_summary.get('total_errors', 0),
                    error_types=db_summary.get('error_types', {}),
                    sample_errors=[],
                    has_more_errors=False
                )

        # Check processing_jobs table for stored summary
        result = _supabase.table('processing_jobs').select(
            'error_summary, failed_records'
        ).eq('id', job_id).single().execute()

        if result.data:
            # Handle case where error_summary is None (not just missing)
            error_summary = result.data.get('error_summary') or {}
            return ErrorSummary(
                total_errors=error_summary.get('total_errors', result.data.get('failed_records', 0)),
                error_types=error_summary.get('error_types', {}),
                sample_errors=error_summary.get('sample_errors', []),
                has_more_errors=False
            )

        return ErrorSummary(
            total_errors=0,
            error_types={},
            sample_errors=[],
            has_more_errors=False
        )

    except Exception as e:
        logger.error(f"Failed to get error summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{job_id}/retry-failed", response_model=RetryResponse)
async def retry_failed_emails(
    job_id: str,
    max_attempts: int = Query(default=3, ge=1, le=10)
):
    """
    Reset failed emails to pending status for retry processing.

    Only resets emails that have fewer than max_attempts attempts.

    Args:
        job_id: UUID of the processing job
        max_attempts: Maximum attempts threshold (1-10)

    Returns:
        RetryResponse with number of emails reset
    """
    mailbox_id = get_mailbox_id_for_job(job_id)
    if not mailbox_id:
        raise HTTPException(status_code=404, detail="Job not found")

    try:
        emails_reset = 0

        if _db_error_tracker:
            emails_reset = _db_error_tracker.reset_failed_emails(
                mailbox_id, max_attempts
            )

        # Clear Redis error cache for this job
        if _error_tracker:
            _error_tracker.clear_errors(job_id)

        # Update job status to allow reprocessing
        _supabase.table('processing_jobs').update({
            'status': 'pending'
        }).eq('id', job_id).eq('status', 'completed').execute()

        message = f"Reset {emails_reset} failed emails for retry"
        if emails_reset == 0:
            message = "No emails to retry (all have exceeded max attempts or none failed)"

        logger.info(f"Retry failed emails for job {job_id}: {emails_reset} reset")

        return RetryResponse(
            job_id=job_id,
            mailbox_id=mailbox_id,
            emails_reset=emails_reset,
            message=message
        )

    except Exception as e:
        logger.error(f"Failed to retry failed emails: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Additional endpoint for getting all failed emails across all jobs
@router.get("/failed-emails", response_model=List[FailedEmail])
async def get_all_failed_emails(
    mailbox_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0)
):
    """
    Get failed emails across all jobs, optionally filtered by mailbox.

    Args:
        mailbox_id: Optional mailbox UUID to filter by
        limit: Maximum number of results (1-1000)
        offset: Offset for pagination

    Returns:
        List of failed email records
    """
    try:
        query = _supabase.table('emails').select(
            'id, message_id, subject, sender_email, sent_date, '
            'processing_error, processing_attempts, last_processing_attempt, mailbox_id'
        ).eq('processing_status', 'failed')

        if mailbox_id:
            query = query.eq('mailbox_id', mailbox_id)

        result = query.order(
            'last_processing_attempt', desc=True
        ).range(offset, offset + limit - 1).execute()

        return [
            FailedEmail(
                id=err.get('id', ''),
                message_id=err.get('message_id'),
                subject=err.get('subject'),
                sender_email=err.get('sender_email'),
                sent_date=err.get('sent_date'),
                processing_error=err.get('processing_error'),
                processing_attempts=err.get('processing_attempts', 1),
                last_processing_attempt=err.get('last_processing_attempt')
            )
            for err in result.data
        ]

    except Exception as e:
        logger.error(f"Failed to get all failed emails: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================================
# New Job Errors Endpoints (from job_errors table)
# These capture ALL errors: download, extraction, processing, etc.
# =========================================================================

@router.get("/{job_id}/job-errors", response_model=JobErrorsResponse)
async def get_job_errors(
    job_id: str,
    phase: Optional[str] = Query(default=None, description="Filter by phase: download, extraction, normalization, tagging, database, categorization"),
    error_type: Optional[str] = Query(default=None, description="Filter by type: encoding_error, parse_error, network_error, etc."),
    unresolved_only: bool = Query(default=False, description="Only show unresolved errors"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0)
):
    """
    Get all job errors from the job_errors table.

    This includes ALL error types: download errors, extraction errors,
    email processing errors, database errors, etc.

    Args:
        job_id: UUID of the processing job
        phase: Optional filter by error phase
        error_type: Optional filter by error type
        unresolved_only: Only return unresolved errors
        limit: Maximum number of errors to return
        offset: Pagination offset

    Returns:
        JobErrorsResponse with comprehensive error details
    """
    try:
        # Build query for job_errors table
        query = _supabase.table('job_errors').select('*').eq('job_id', job_id)

        if phase:
            query = query.eq('error_phase', phase)
        if error_type:
            query = query.eq('error_type', error_type)
        if unresolved_only:
            query = query.is_('resolved_at', 'null')

        # Get paginated errors first (simpler query)
        result = query.order('created_at', desc=True).range(offset, offset + limit - 1).execute()

        errors = []
        for err in result.data or []:
            errors.append(JobError(
                id=err.get('id', ''),
                error_phase=err.get('error_phase', 'unknown'),
                error_type=err.get('error_type', 'other_error'),
                error_severity=err.get('error_severity', 'error'),
                error_message=err.get('error_message', ''),
                error_stack=err.get('error_stack'),
                context_type=err.get('context_type'),
                context_id=err.get('context_id'),
                context_details=err.get('context_details'),
                is_retryable=err.get('is_retryable', True),
                retry_count=err.get('retry_count', 0),
                resolved_at=err.get('resolved_at'),
                created_at=err.get('created_at')
            ))

        # Get total count - use len if no filters, otherwise try count query
        total_errors = 0
        unresolved_errors = 0

        try:
            count_query = _supabase.table('job_errors').select('id', count='exact').eq('job_id', job_id)
            if phase:
                count_query = count_query.eq('error_phase', phase)
            if error_type:
                count_query = count_query.eq('error_type', error_type)
            if unresolved_only:
                count_query = count_query.is_('resolved_at', 'null')

            count_result = count_query.execute()
            total_errors = count_result.count if count_result.count is not None else len(result.data or [])

            # Get unresolved count
            unresolved_query = _supabase.table('job_errors').select('id', count='exact').eq('job_id', job_id).is_('resolved_at', 'null')
            unresolved_result = unresolved_query.execute()
            unresolved_errors = unresolved_result.count if unresolved_result.count is not None else 0
        except Exception as count_err:
            logger.warning(f"Count query failed, using result length: {count_err}")
            total_errors = len(errors)

        return JobErrorsResponse(
            job_id=job_id,
            total_errors=total_errors,
            unresolved_errors=unresolved_errors,
            errors=errors,
            has_more=total_errors > offset + limit
        )

    except Exception as e:
        logger.error(f"Failed to get job errors: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{job_id}/job-errors/summary", response_model=JobErrorsSummary)
async def get_job_errors_summary(job_id: str):
    """
    Get comprehensive error summary from job_errors table.

    Returns error counts grouped by phase, type, and severity,
    plus the most recent errors.

    Args:
        job_id: UUID of the processing job

    Returns:
        JobErrorsSummary with aggregated error statistics
    """
    try:
        # Try using the database function first
        try:
            result = _supabase.rpc('get_job_errors_summary', {'p_job_id': job_id}).execute()
            if result.data:
                data = result.data
                return JobErrorsSummary(
                    total_errors=data.get('total_errors', 0),
                    unresolved_errors=data.get('unresolved_errors', 0),
                    retryable_errors=data.get('retryable_errors', 0),
                    by_phase=data.get('by_phase', {}),
                    by_type=data.get('by_type', {}),
                    by_severity=data.get('by_severity', {}),
                    recent_errors=data.get('recent_errors', [])
                )
        except Exception as rpc_error:
            logger.warning(f"RPC call failed, using fallback query: {rpc_error}")

        # Fallback: manually aggregate
        errors_result = _supabase.table('job_errors').select('*').eq('job_id', job_id).execute()
        errors = errors_result.data or []

        total_errors = len(errors)
        unresolved_errors = sum(1 for e in errors if e.get('resolved_at') is None)
        retryable_errors = sum(1 for e in errors if e.get('is_retryable') and e.get('resolved_at') is None)

        # Group by phase
        by_phase = {}
        for e in errors:
            phase = e.get('error_phase', 'unknown')
            by_phase[phase] = by_phase.get(phase, 0) + 1

        # Group by type
        by_type = {}
        for e in errors:
            etype = e.get('error_type', 'other_error')
            by_type[etype] = by_type.get(etype, 0) + 1

        # Group by severity
        by_severity = {}
        for e in errors:
            sev = e.get('error_severity', 'error')
            by_severity[sev] = by_severity.get(sev, 0) + 1

        # Get recent errors (sorted by created_at desc)
        sorted_errors = sorted(errors, key=lambda x: x.get('created_at', ''), reverse=True)[:10]
        recent_errors = [
            {
                'id': e.get('id'),
                'phase': e.get('error_phase'),
                'type': e.get('error_type'),
                'severity': e.get('error_severity'),
                'message': (e.get('error_message', '') or '')[:200],
                'context_type': e.get('context_type'),
                'context_id': e.get('context_id'),
                'created_at': e.get('created_at')
            }
            for e in sorted_errors
        ]

        return JobErrorsSummary(
            total_errors=total_errors,
            unresolved_errors=unresolved_errors,
            retryable_errors=retryable_errors,
            by_phase=by_phase,
            by_type=by_type,
            by_severity=by_severity,
            recent_errors=recent_errors
        )

    except Exception as e:
        logger.error(f"Failed to get job errors summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{job_id}/error-log")
async def get_job_error_log(job_id: str):
    """
    Get the raw error_log from a processing job.

    This returns the errors array and failed_message_ids stored in the
    processing_jobs table after job completion. Useful for debugging
    batch insert failures.

    Args:
        job_id: UUID of the processing job

    Returns:
        Error log details including batch errors and failed message IDs
    """
    try:
        result = _supabase.table('processing_jobs').select(
            'id, status, job_type, mailbox_id, total_records, processed_records, '
            'failed_records, error_log, started_at, completed_at'
        ).eq('id', job_id).single().execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Job not found")

        job = result.data
        # Handle case where error_log is None (not just missing)
        error_log = job.get('error_log') or {}

        # Parse error_log - it could be a dict or list
        errors = []
        failed_message_ids = []

        if isinstance(error_log, dict):
            errors = error_log.get('errors', [])
            failed_message_ids = error_log.get('failed_message_ids', [])
            # If just a single error dict
            if 'error' in error_log and not errors:
                errors = [error_log.get('error')]
        elif isinstance(error_log, list):
            errors = error_log

        # Analyze error types
        error_analysis = {}
        for err in errors:
            if isinstance(err, str):
                if 'timeout' in err.lower():
                    error_type = 'timeout'
                elif '21000' in err or 'ON CONFLICT' in err:
                    error_type = 'duplicate_in_batch'
                elif 'duplicate key' in err.lower():
                    error_type = 'duplicate_key'
                elif 'connection' in err.lower():
                    error_type = 'connection'
                else:
                    error_type = 'other'

                error_analysis[error_type] = error_analysis.get(error_type, 0) + 1

        return {
            "job_id": job.get('id'),
            "status": job.get('status'),
            "job_type": job.get('job_type'),
            "mailbox_id": job.get('mailbox_id'),
            "total_records": job.get('total_records'),
            "processed_records": job.get('processed_records'),
            "failed_records": job.get('failed_records'),
            "started_at": job.get('started_at'),
            "completed_at": job.get('completed_at'),
            "error_count": len(errors),
            "error_analysis": error_analysis,
            "errors": errors[:100],  # First 100 errors
            "failed_message_ids_count": len(failed_message_ids),
            "failed_message_ids_sample": failed_message_ids[:50],  # First 50 message IDs
            "has_more_errors": len(errors) > 100,
            "has_more_message_ids": len(failed_message_ids) > 50
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get job error log: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{job_id}/job-errors/{error_id}/resolve")
async def resolve_job_error(
    job_id: str,
    error_id: str,
    resolution_type: str = Query(default="manual_fix", description="Resolution type: auto_retry, manual_skip, manual_fix")
):
    """
    Mark a job error as resolved.

    Args:
        job_id: UUID of the processing job
        error_id: UUID of the error record
        resolution_type: How the error was resolved

    Returns:
        Updated error record
    """
    try:
        # Verify error belongs to job
        check_result = _supabase.table('job_errors').select('id').eq('id', error_id).eq('job_id', job_id).execute()
        if not check_result.data:
            raise HTTPException(status_code=404, detail="Error not found for this job")

        # Update the error
        from datetime import datetime, timezone
        result = _supabase.table('job_errors').update({
            'resolved_at': datetime.now(timezone.utc).isoformat(),
            'resolution_type': resolution_type
        }).eq('id', error_id).execute()

        if result.data:
            return {"success": True, "error_id": error_id, "resolution_type": resolution_type}

        raise HTTPException(status_code=500, detail="Failed to update error")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resolve job error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
