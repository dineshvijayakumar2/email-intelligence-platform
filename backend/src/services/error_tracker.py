"""
Error Tracker Service for Email Processing

Tracks processing errors at both individual email level and job level.
Stores errors in Redis for real-time access and syncs to database for persistence.

Stage 2 Phase 1 - Error Handling Implementation
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import traceback

logger = logging.getLogger(__name__)


@dataclass
class ProcessingError:
    """Represents a single processing error"""
    email_id: Optional[str]
    message_id: Optional[str]
    subject: Optional[str]
    sender_email: Optional[str]
    error_type: str
    error_message: str
    stack_trace: Optional[str]
    timestamp: str
    attempt_number: int = 1

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_exception(
        cls,
        exception: Exception,
        email_id: Optional[str] = None,
        message_id: Optional[str] = None,
        subject: Optional[str] = None,
        sender_email: Optional[str] = None,
        attempt_number: int = 1
    ) -> 'ProcessingError':
        """Create a ProcessingError from an exception"""
        error_type = cls._classify_error(exception)
        return cls(
            email_id=email_id,
            message_id=message_id,
            subject=subject[:200] if subject else None,  # Truncate long subjects
            sender_email=sender_email,
            error_type=error_type,
            error_message=str(exception)[:500],  # Truncate long error messages
            stack_trace=traceback.format_exc()[:2000],  # Truncate stack trace
            timestamp=datetime.utcnow().isoformat(),
            attempt_number=attempt_number
        )

    @staticmethod
    def _classify_error(exception: Exception) -> str:
        """Classify error type from exception"""
        error_str = str(exception).lower()
        exception_name = type(exception).__name__.lower()

        if 'encoding' in error_str or 'decode' in error_str or 'codec' in error_str:
            return 'encoding_error'
        elif 'parse' in error_str or 'parsing' in exception_name:
            return 'parse_error'
        elif 'timeout' in error_str or 'timed out' in error_str:
            return 'timeout_error'
        elif 'connection' in error_str or 'connect' in error_str:
            return 'connection_error'
        elif 'duplicate' in error_str or 'unique' in error_str:
            return 'duplicate_error'
        elif 'memory' in error_str or 'oom' in error_str:
            return 'memory_error'
        elif 'permission' in error_str or 'access' in error_str:
            return 'permission_error'
        else:
            return 'other_error'


class ErrorTracker:
    """
    Tracks and manages processing errors for email jobs.

    Uses Redis for real-time error tracking and provides methods
    to sync errors to the database for persistence.
    """

    # Error type descriptions for UI display
    ERROR_TYPE_DESCRIPTIONS = {
        'encoding_error': 'Character encoding issues (UTF-8, ASCII, etc.)',
        'parse_error': 'Failed to parse email structure or headers',
        'timeout_error': 'Processing timed out',
        'connection_error': 'Database or network connection failed',
        'duplicate_error': 'Duplicate email detected',
        'memory_error': 'Insufficient memory to process',
        'permission_error': 'Access or permission denied',
        'other_error': 'Unclassified error'
    }

    def __init__(self, redis_client, max_sample_errors: int = 50):
        """
        Initialize error tracker.

        Args:
            redis_client: Redis client instance
            max_sample_errors: Maximum number of sample errors to store per job
        """
        self.redis = redis_client
        self.max_sample_errors = max_sample_errors

    def _get_errors_key(self, job_id: str) -> str:
        """Get Redis key for job errors list"""
        return f"job:{job_id}:errors"

    def _get_error_counts_key(self, job_id: str) -> str:
        """Get Redis key for error type counts"""
        return f"job:{job_id}:error_counts"

    def _get_error_summary_key(self, job_id: str) -> str:
        """Get Redis key for error summary"""
        return f"job:{job_id}:error_summary"

    def track_error(
        self,
        job_id: str,
        error: ProcessingError,
        ttl_seconds: int = 86400 * 7  # 7 days default
    ) -> None:
        """
        Track a processing error for a job.

        Args:
            job_id: The processing job ID
            error: ProcessingError instance
            ttl_seconds: Time to live for Redis data
        """
        try:
            errors_key = self._get_errors_key(job_id)
            counts_key = self._get_error_counts_key(job_id)

            # Store error in list (limited to max_sample_errors)
            error_json = json.dumps(error.to_dict())
            self.redis.lpush(errors_key, error_json)
            self.redis.ltrim(errors_key, 0, self.max_sample_errors - 1)
            self.redis.expire(errors_key, ttl_seconds)

            # Increment error type counter
            self.redis.hincrby(counts_key, error.error_type, 1)
            self.redis.hincrby(counts_key, 'total', 1)
            self.redis.expire(counts_key, ttl_seconds)

            logger.debug(f"Tracked error for job {job_id}: {error.error_type}")

        except Exception as e:
            logger.error(f"Failed to track error in Redis: {e}")

    def track_error_from_exception(
        self,
        job_id: str,
        exception: Exception,
        email_id: Optional[str] = None,
        message_id: Optional[str] = None,
        subject: Optional[str] = None,
        sender_email: Optional[str] = None,
        attempt_number: int = 1
    ) -> ProcessingError:
        """
        Convenience method to track an error directly from an exception.

        Returns the created ProcessingError for further use.
        """
        error = ProcessingError.from_exception(
            exception=exception,
            email_id=email_id,
            message_id=message_id,
            subject=subject,
            sender_email=sender_email,
            attempt_number=attempt_number
        )
        self.track_error(job_id, error)
        return error

    def get_errors(
        self,
        job_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict]:
        """
        Get recent errors for a job.

        Args:
            job_id: The processing job ID
            limit: Maximum number of errors to return
            offset: Offset for pagination

        Returns:
            List of error dictionaries
        """
        try:
            errors_key = self._get_errors_key(job_id)
            errors_raw = self.redis.lrange(errors_key, offset, offset + limit - 1)
            return [json.loads(e) for e in errors_raw]
        except Exception as e:
            logger.error(f"Failed to get errors from Redis: {e}")
            return []

    def get_error_counts(self, job_id: str) -> Dict[str, int]:
        """
        Get error counts by type for a job.

        Returns:
            Dictionary with error type as key and count as value
        """
        try:
            counts_key = self._get_error_counts_key(job_id)
            counts = self.redis.hgetall(counts_key)
            return {k: int(v) for k, v in counts.items()}
        except Exception as e:
            logger.error(f"Failed to get error counts from Redis: {e}")
            return {}

    def get_error_summary(self, job_id: str) -> Dict[str, Any]:
        """
        Get comprehensive error summary for a job.

        Returns:
            Dictionary with total_errors, error_types breakdown, and sample_errors
        """
        counts = self.get_error_counts(job_id)
        sample_errors = self.get_errors(job_id, limit=10)

        total = counts.pop('total', 0)

        # Add descriptions to error types
        error_types_with_desc = {}
        for error_type, count in counts.items():
            error_types_with_desc[error_type] = {
                'count': count,
                'description': self.ERROR_TYPE_DESCRIPTIONS.get(
                    error_type, 'Unknown error type'
                )
            }

        return {
            'total_errors': total,
            'error_types': error_types_with_desc,
            'sample_errors': sample_errors,
            'has_more_errors': total > len(sample_errors)
        }

    def build_error_summary_json(self, job_id: str) -> Dict:
        """
        Build error summary JSON suitable for storing in database.

        This is called when a job completes to persist the error summary.
        """
        summary = self.get_error_summary(job_id)
        return {
            'total_errors': summary['total_errors'],
            'error_types': {
                k: v['count'] for k, v in summary['error_types'].items()
            },
            'sample_errors': summary['sample_errors'][:10],  # Store only 10 samples
            'generated_at': datetime.utcnow().isoformat()
        }

    def clear_errors(self, job_id: str) -> None:
        """Clear all errors for a job from Redis"""
        try:
            self.redis.delete(self._get_errors_key(job_id))
            self.redis.delete(self._get_error_counts_key(job_id))
            self.redis.delete(self._get_error_summary_key(job_id))
            logger.info(f"Cleared errors for job {job_id}")
        except Exception as e:
            logger.error(f"Failed to clear errors: {e}")


class DatabaseErrorTracker:
    """
    Database-side error tracking for persistence and querying.

    Works with the emails and processing_jobs tables to track errors.
    """

    def __init__(self, supabase_client):
        """
        Initialize database error tracker.

        Args:
            supabase_client: Supabase client instance
        """
        self.supabase = supabase_client

    def update_email_status(
        self,
        email_id: str,
        status: str,
        error_message: Optional[str] = None,
        increment_attempts: bool = True
    ) -> bool:
        """
        Update the processing status of an email.

        Args:
            email_id: UUID of the email
            status: New status (pending, processing, success, failed, skipped)
            error_message: Error message if status is 'failed'
            increment_attempts: Whether to increment the attempt counter

        Returns:
            True if update succeeded
        """
        try:
            update_data = {
                'processing_status': status,
                'last_processing_attempt': datetime.utcnow().isoformat()
            }

            if error_message:
                update_data['processing_error'] = error_message[:1000]  # Limit size

            result = self.supabase.table('emails').update(update_data).eq(
                'id', email_id
            ).execute()

            # Increment attempts separately using RPC if needed
            if increment_attempts:
                self.supabase.rpc(
                    'increment_processing_attempts',
                    {'p_email_id': email_id}
                ).execute()

            return True

        except Exception as e:
            logger.error(f"Failed to update email status: {e}")
            return False

    def get_failed_emails(
        self,
        mailbox_id: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict]:
        """
        Get failed emails for a mailbox.

        Args:
            mailbox_id: UUID of the mailbox
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of failed email records
        """
        try:
            result = self.supabase.table('emails').select(
                'id, message_id, subject, sender_email, sent_date, '
                'processing_error, processing_attempts, last_processing_attempt'
            ).eq(
                'mailbox_id', mailbox_id
            ).eq(
                'processing_status', 'failed'
            ).order(
                'last_processing_attempt', desc=True
            ).range(offset, offset + limit - 1).execute()

            return result.data

        except Exception as e:
            logger.error(f"Failed to get failed emails: {e}")
            return []

    def get_error_summary_from_db(self, mailbox_id: str) -> Dict:
        """
        Get error summary directly from database.

        Uses the get_job_error_summary SQL function.
        """
        try:
            result = self.supabase.rpc(
                'get_job_error_summary',
                {'p_mailbox_id': mailbox_id}
            ).execute()

            return result.data if result.data else {}

        except Exception as e:
            logger.error(f"Failed to get error summary from DB: {e}")
            return {}

    def reset_failed_emails(
        self,
        mailbox_id: str,
        max_attempts: int = 3
    ) -> int:
        """
        Reset failed emails to pending status for retry.

        Args:
            mailbox_id: UUID of the mailbox
            max_attempts: Only reset emails with fewer attempts than this

        Returns:
            Number of emails reset
        """
        try:
            result = self.supabase.rpc(
                'reset_failed_emails_for_retry',
                {'p_mailbox_id': mailbox_id, 'p_max_attempts': max_attempts}
            ).execute()

            return result.data if result.data else 0

        except Exception as e:
            logger.error(f"Failed to reset failed emails: {e}")
            return 0

    def save_job_error_summary(self, job_id: str, error_summary: Dict) -> bool:
        """
        Save error summary to the processing_jobs table.

        Args:
            job_id: UUID of the processing job
            error_summary: Error summary dictionary

        Returns:
            True if save succeeded
        """
        try:
            self.supabase.table('processing_jobs').update({
                'error_summary': error_summary
            }).eq('id', job_id).execute()

            return True

        except Exception as e:
            logger.error(f"Failed to save job error summary: {e}")
            return False
