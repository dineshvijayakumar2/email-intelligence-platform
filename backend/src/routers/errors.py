"""
Error Handling API Router

Provides endpoints for viewing and managing processing errors.

Stage 2 Phase 1 - Error Handling Implementation
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/processing-jobs", tags=["errors"])


# Pydantic models for request/response
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


# These will be injected from main.py
_error_tracker = None
_db_error_tracker = None
_supabase = None
_redis = None


def init_error_router(error_tracker, db_error_tracker, supabase_client, redis_client):
    """Initialize the router with dependencies"""
    global _error_tracker, _db_error_tracker, _supabase, _redis
    _error_tracker = error_tracker
    _db_error_tracker = db_error_tracker
    _supabase = supabase_client
    _redis = redis_client


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
        raise HTTPException(status_code=404, detail="Job not found")

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
    if not mailbox_id:
        raise HTTPException(status_code=404, detail="Job not found")

    try:
        # Try Redis first for active jobs
        if _error_tracker:
            summary = _error_tracker.get_error_summary(job_id)
            if summary.get('total_errors', 0) > 0:
                return ErrorSummary(**summary)

        # Fall back to database for completed jobs
        if _db_error_tracker:
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
            error_summary = result.data.get('error_summary', {})
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
