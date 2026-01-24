"""
Job Error Logger Service

Centralized error logging for all processing job errors.
Persists errors to the job_errors table with comprehensive context.

Error Phases:
- download: File download from Google Drive or other sources
- extraction: Extracting emails from archive files (MBOX, PST, OLM)
- normalization: Converting raw email to standard format
- tagging: Applying tags/categories to emails
- database: Database insertion/update errors
- categorization: AI categorization errors (Stage 2)

Error Types:
- encoding_error: Character encoding issues
- parse_error: Failed to parse email/file structure
- network_error: Network connectivity issues
- timeout_error: Operation timed out
- auth_error: Authentication/authorization failure
- connection_error: Database/service connection failure
- duplicate_error: Duplicate record detected
- permission_error: Access denied
- memory_error: Out of memory
- validation_error: Data validation failure
- file_error: File read/write error
- chunk_error: Chunk download/processing error
- other_error: Unclassified errors
"""

import logging
import traceback
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from enum import Enum

logger = logging.getLogger(__name__)


class ErrorPhase(str, Enum):
    """Processing phases where errors can occur"""
    DOWNLOAD = "download"
    EXTRACTION = "extraction"
    NORMALIZATION = "normalization"
    TAGGING = "tagging"
    DATABASE = "database"
    CATEGORIZATION = "categorization"


class ErrorType(str, Enum):
    """Error type classifications"""
    ENCODING_ERROR = "encoding_error"
    PARSE_ERROR = "parse_error"
    NETWORK_ERROR = "network_error"
    TIMEOUT_ERROR = "timeout_error"
    AUTH_ERROR = "auth_error"
    CONNECTION_ERROR = "connection_error"
    DUPLICATE_ERROR = "duplicate_error"
    PERMISSION_ERROR = "permission_error"
    MEMORY_ERROR = "memory_error"
    VALIDATION_ERROR = "validation_error"
    FILE_ERROR = "file_error"
    CHUNK_ERROR = "chunk_error"
    OTHER_ERROR = "other_error"


class ErrorSeverity(str, Enum):
    """Error severity levels"""
    WARNING = "warning"    # Non-critical, processing can continue
    ERROR = "error"        # Error occurred, item skipped
    CRITICAL = "critical"  # Critical error, job may fail


class ContextType(str, Enum):
    """What was being processed when error occurred"""
    FILE = "file"
    CHUNK = "chunk"
    EMAIL = "email"
    BATCH = "batch"


class JobErrorLogger:
    """
    Centralized error logger for processing jobs.
    Logs errors to the job_errors database table.
    """

    # Maximum lengths for truncation
    MAX_MESSAGE_LENGTH = 2000
    MAX_STACK_LENGTH = 4000
    MAX_CONTEXT_ID_LENGTH = 500

    def __init__(self, supabase_client):
        """
        Initialize the error logger.

        Args:
            supabase_client: Supabase client instance
        """
        self.client = supabase_client
        self._error_buffer: List[Dict] = []
        self._buffer_size = 50  # Flush after 50 errors

    def log_error(
        self,
        job_id: str,
        phase: ErrorPhase,
        error_type: ErrorType,
        error_message: str,
        mailbox_id: Optional[str] = None,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        error_stack: Optional[str] = None,
        context_type: Optional[ContextType] = None,
        context_id: Optional[str] = None,
        context_details: Optional[Dict[str, Any]] = None,
        is_retryable: bool = True,
        max_retries: int = 3
    ) -> Optional[str]:
        """
        Log an error to the job_errors table.

        Args:
            job_id: Processing job ID
            phase: Error phase (download, extraction, etc.)
            error_type: Error classification
            error_message: Error message/description
            mailbox_id: Optional mailbox ID
            severity: Error severity (warning, error, critical)
            error_stack: Optional stack trace
            context_type: What was being processed (file, chunk, email, batch)
            context_id: ID of the item being processed
            context_details: Additional context as JSON
            is_retryable: Whether this error can be retried
            max_retries: Maximum retry attempts

        Returns:
            Error record ID if successful, None otherwise
        """
        try:
            error_record = {
                "job_id": job_id,
                "mailbox_id": mailbox_id,
                "error_phase": phase.value if isinstance(phase, ErrorPhase) else phase,
                "error_type": error_type.value if isinstance(error_type, ErrorType) else error_type,
                "error_severity": severity.value if isinstance(severity, ErrorSeverity) else severity,
                "error_message": self._truncate(error_message, self.MAX_MESSAGE_LENGTH),
                "error_stack": self._truncate(error_stack, self.MAX_STACK_LENGTH) if error_stack else None,
                "context_type": context_type.value if isinstance(context_type, ContextType) else context_type,
                "context_id": self._truncate(context_id, self.MAX_CONTEXT_ID_LENGTH) if context_id else None,
                "context_details": context_details,
                "is_retryable": is_retryable,
                "max_retries": max_retries,
                "created_at": datetime.now(timezone.utc).isoformat()
            }

            result = self.client.table('job_errors').insert(error_record).execute()

            if result.data:
                error_id = result.data[0].get('id')
                logger.debug(f"Logged error {error_id} for job {job_id}: {phase}/{error_type}")
                return error_id

            return None

        except Exception as e:
            # Don't let error logging fail the main process
            logger.warning(f"Failed to log error to database: {e}")
            return None

    def log_error_from_exception(
        self,
        job_id: str,
        phase: ErrorPhase,
        exception: Exception,
        mailbox_id: Optional[str] = None,
        context_type: Optional[ContextType] = None,
        context_id: Optional[str] = None,
        context_details: Optional[Dict[str, Any]] = None,
        is_retryable: bool = True
    ) -> Optional[str]:
        """
        Log an error from an exception with automatic type classification.

        Args:
            job_id: Processing job ID
            phase: Error phase
            exception: The exception that occurred
            mailbox_id: Optional mailbox ID
            context_type: What was being processed
            context_id: ID of the item being processed
            context_details: Additional context
            is_retryable: Whether this error can be retried

        Returns:
            Error record ID if successful, None otherwise
        """
        error_type = self.classify_exception(exception)
        severity = self._determine_severity(error_type, exception)
        error_stack = traceback.format_exc()

        return self.log_error(
            job_id=job_id,
            phase=phase,
            error_type=error_type,
            error_message=str(exception),
            mailbox_id=mailbox_id,
            severity=severity,
            error_stack=error_stack,
            context_type=context_type,
            context_id=context_id,
            context_details=context_details,
            is_retryable=is_retryable
        )

    def log_download_error(
        self,
        job_id: str,
        error_message: str,
        mailbox_id: Optional[str] = None,
        file_id: Optional[str] = None,
        file_name: Optional[str] = None,
        chunk_index: Optional[int] = None,
        chunk_start: Optional[int] = None,
        chunk_end: Optional[int] = None,
        error_type: ErrorType = ErrorType.NETWORK_ERROR,
        is_retryable: bool = True,
        exception: Optional[Exception] = None
    ) -> Optional[str]:
        """
        Log a download-specific error with chunk details.

        Args:
            job_id: Processing job ID
            error_message: Error message
            mailbox_id: Optional mailbox ID
            file_id: Google Drive file ID
            file_name: File name being downloaded
            chunk_index: Chunk number (for parallel downloads)
            chunk_start: Chunk byte start position
            chunk_end: Chunk byte end position
            error_type: Error classification
            is_retryable: Whether this error can be retried
            exception: Optional exception for stack trace

        Returns:
            Error record ID if successful, None otherwise
        """
        context_type = ContextType.CHUNK if chunk_index is not None else ContextType.FILE
        context_id = f"chunk_{chunk_index}" if chunk_index is not None else file_id

        context_details = {}
        if file_id:
            context_details["file_id"] = file_id
        if file_name:
            context_details["file_name"] = file_name
        if chunk_index is not None:
            context_details["chunk_index"] = chunk_index
        if chunk_start is not None:
            context_details["chunk_start"] = chunk_start
        if chunk_end is not None:
            context_details["chunk_end"] = chunk_end

        error_stack = traceback.format_exc() if exception else None

        return self.log_error(
            job_id=job_id,
            phase=ErrorPhase.DOWNLOAD,
            error_type=error_type,
            error_message=error_message,
            mailbox_id=mailbox_id,
            severity=ErrorSeverity.ERROR,
            error_stack=error_stack,
            context_type=context_type,
            context_id=context_id,
            context_details=context_details if context_details else None,
            is_retryable=is_retryable
        )

    def log_extraction_error(
        self,
        job_id: str,
        error_message: str,
        mailbox_id: Optional[str] = None,
        file_name: Optional[str] = None,
        file_type: Optional[str] = None,
        position: Optional[int] = None,
        exception: Optional[Exception] = None
    ) -> Optional[str]:
        """Log an extraction error (MBOX, PST, OLM parsing)."""
        error_type = self.classify_exception(exception) if exception else ErrorType.PARSE_ERROR

        context_details = {}
        if file_name:
            context_details["file_name"] = file_name
        if file_type:
            context_details["file_type"] = file_type
        if position is not None:
            context_details["position"] = position

        return self.log_error(
            job_id=job_id,
            phase=ErrorPhase.EXTRACTION,
            error_type=error_type,
            error_message=error_message,
            mailbox_id=mailbox_id,
            severity=ErrorSeverity.ERROR,
            error_stack=traceback.format_exc() if exception else None,
            context_type=ContextType.FILE,
            context_id=file_name,
            context_details=context_details if context_details else None,
            is_retryable=True
        )

    def log_email_error(
        self,
        job_id: str,
        error_message: str,
        mailbox_id: Optional[str] = None,
        message_id: Optional[str] = None,
        subject: Optional[str] = None,
        sender: Optional[str] = None,
        phase: ErrorPhase = ErrorPhase.NORMALIZATION,
        exception: Optional[Exception] = None
    ) -> Optional[str]:
        """Log an email processing error."""
        error_type = self.classify_exception(exception) if exception else ErrorType.PARSE_ERROR

        context_details = {}
        if subject:
            context_details["subject"] = subject[:200]
        if sender:
            context_details["sender"] = sender

        return self.log_error(
            job_id=job_id,
            phase=phase,
            error_type=error_type,
            error_message=error_message,
            mailbox_id=mailbox_id,
            severity=ErrorSeverity.ERROR,
            error_stack=traceback.format_exc() if exception else None,
            context_type=ContextType.EMAIL,
            context_id=message_id,
            context_details=context_details if context_details else None,
            is_retryable=True
        )

    def log_batch_error(
        self,
        job_id: str,
        error_message: str,
        mailbox_id: Optional[str] = None,
        batch_number: Optional[int] = None,
        batch_size: Optional[int] = None,
        phase: ErrorPhase = ErrorPhase.DATABASE,
        exception: Optional[Exception] = None
    ) -> Optional[str]:
        """Log a batch processing error."""
        error_type = self.classify_exception(exception) if exception else ErrorType.CONNECTION_ERROR

        context_details = {}
        if batch_number is not None:
            context_details["batch_number"] = batch_number
        if batch_size is not None:
            context_details["batch_size"] = batch_size

        return self.log_error(
            job_id=job_id,
            phase=phase,
            error_type=error_type,
            error_message=error_message,
            mailbox_id=mailbox_id,
            severity=ErrorSeverity.ERROR,
            error_stack=traceback.format_exc() if exception else None,
            context_type=ContextType.BATCH,
            context_id=f"batch_{batch_number}" if batch_number is not None else None,
            context_details=context_details if context_details else None,
            is_retryable=True
        )

    def log_critical_error(
        self,
        job_id: str,
        phase: ErrorPhase,
        error_message: str,
        mailbox_id: Optional[str] = None,
        exception: Optional[Exception] = None,
        context_details: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """Log a critical error that causes job failure."""
        error_type = self.classify_exception(exception) if exception else ErrorType.OTHER_ERROR

        return self.log_error(
            job_id=job_id,
            phase=phase,
            error_type=error_type,
            error_message=error_message,
            mailbox_id=mailbox_id,
            severity=ErrorSeverity.CRITICAL,
            error_stack=traceback.format_exc() if exception else None,
            context_type=None,
            context_id=None,
            context_details=context_details,
            is_retryable=False
        )

    def get_job_errors(
        self,
        job_id: str,
        phase: Optional[str] = None,
        error_type: Optional[str] = None,
        unresolved_only: bool = False,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get errors for a job with optional filters.

        Args:
            job_id: Processing job ID
            phase: Filter by error phase
            error_type: Filter by error type
            unresolved_only: Only return unresolved errors
            limit: Maximum records to return
            offset: Pagination offset

        Returns:
            List of error records
        """
        try:
            query = self.client.table('job_errors').select('*').eq('job_id', job_id)

            if phase:
                query = query.eq('error_phase', phase)
            if error_type:
                query = query.eq('error_type', error_type)
            if unresolved_only:
                query = query.is_('resolved_at', 'null')

            query = query.order('created_at', desc=True).range(offset, offset + limit - 1)
            result = query.execute()

            return result.data if result.data else []

        except Exception as e:
            logger.error(f"Failed to get job errors: {e}")
            return []

    def get_job_error_summary(self, job_id: str) -> Dict[str, Any]:
        """
        Get error summary for a job.

        Args:
            job_id: Processing job ID

        Returns:
            Error summary dict with counts by phase, type, severity
        """
        try:
            result = self.client.rpc('get_job_errors_summary', {'p_job_id': job_id}).execute()
            return result.data if result.data else {}
        except Exception as e:
            logger.error(f"Failed to get job error summary: {e}")
            return {}

    def mark_error_resolved(
        self,
        error_id: str,
        resolution_type: str = "manual_fix"
    ) -> bool:
        """
        Mark an error as resolved.

        Args:
            error_id: Error record ID
            resolution_type: How it was resolved (auto_retry, manual_skip, manual_fix)

        Returns:
            True if successful
        """
        try:
            self.client.table('job_errors').update({
                "resolved_at": datetime.now(timezone.utc).isoformat(),
                "resolution_type": resolution_type
            }).eq('id', error_id).execute()
            return True
        except Exception as e:
            logger.error(f"Failed to mark error resolved: {e}")
            return False

    def increment_retry_count(self, error_id: str) -> bool:
        """Increment retry count for an error."""
        try:
            # Get current retry count
            result = self.client.table('job_errors').select('retry_count').eq('id', error_id).execute()
            if result.data:
                current_count = result.data[0].get('retry_count', 0)
                self.client.table('job_errors').update({
                    "retry_count": current_count + 1,
                    "last_retry_at": datetime.now(timezone.utc).isoformat()
                }).eq('id', error_id).execute()
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to increment retry count: {e}")
            return False

    @staticmethod
    def classify_exception(exception: Exception) -> ErrorType:
        """
        Classify an exception into an error type.

        Args:
            exception: The exception to classify

        Returns:
            ErrorType enum value
        """
        error_str = str(exception).lower()
        exception_name = type(exception).__name__.lower()

        # Check by exception type first
        if 'timeout' in exception_name or 'timedout' in exception_name:
            return ErrorType.TIMEOUT_ERROR
        if 'connection' in exception_name:
            return ErrorType.CONNECTION_ERROR
        if 'permission' in exception_name or 'access' in exception_name:
            return ErrorType.PERMISSION_ERROR
        if 'memory' in exception_name:
            return ErrorType.MEMORY_ERROR

        # Check by error message
        if 'encoding' in error_str or 'decode' in error_str or 'codec' in error_str:
            return ErrorType.ENCODING_ERROR
        if 'parse' in error_str or 'parsing' in error_str or 'invalid' in error_str:
            return ErrorType.PARSE_ERROR
        if 'timeout' in error_str or 'timed out' in error_str:
            return ErrorType.TIMEOUT_ERROR
        if 'network' in error_str or 'unreachable' in error_str or 'dns' in error_str:
            return ErrorType.NETWORK_ERROR
        if 'connection' in error_str or 'connect' in error_str or 'refused' in error_str:
            return ErrorType.CONNECTION_ERROR
        if 'auth' in error_str or 'unauthorized' in error_str or 'forbidden' in error_str:
            return ErrorType.AUTH_ERROR
        if 'duplicate' in error_str or 'unique' in error_str or 'already exists' in error_str:
            return ErrorType.DUPLICATE_ERROR
        if 'permission' in error_str or 'denied' in error_str or 'access' in error_str:
            return ErrorType.PERMISSION_ERROR
        if 'memory' in error_str or 'oom' in error_str or 'out of memory' in error_str:
            return ErrorType.MEMORY_ERROR
        if 'file' in error_str or 'read' in error_str or 'write' in error_str or 'open' in error_str:
            return ErrorType.FILE_ERROR
        if 'chunk' in error_str or 'range' in error_str:
            return ErrorType.CHUNK_ERROR
        if 'valid' in error_str or 'required' in error_str or 'missing' in error_str:
            return ErrorType.VALIDATION_ERROR

        return ErrorType.OTHER_ERROR

    @staticmethod
    def _determine_severity(error_type: ErrorType, exception: Exception) -> ErrorSeverity:
        """Determine error severity based on type and exception."""
        # Critical errors that typically cause job failure
        critical_types = {ErrorType.AUTH_ERROR, ErrorType.MEMORY_ERROR, ErrorType.PERMISSION_ERROR}
        if error_type in critical_types:
            return ErrorSeverity.CRITICAL

        # Warnings for transient/recoverable issues
        warning_types = {ErrorType.TIMEOUT_ERROR, ErrorType.NETWORK_ERROR, ErrorType.CONNECTION_ERROR}
        if error_type in warning_types:
            return ErrorSeverity.WARNING

        return ErrorSeverity.ERROR

    @staticmethod
    def _truncate(text: Optional[str], max_length: int) -> Optional[str]:
        """Truncate text to max length."""
        if text is None:
            return None
        if len(text) <= max_length:
            return text
        return text[:max_length - 3] + "..."


# Singleton instance for easy access
_error_logger: Optional[JobErrorLogger] = None


def get_error_logger(supabase_client=None) -> Optional[JobErrorLogger]:
    """
    Get the singleton JobErrorLogger instance.

    Args:
        supabase_client: Supabase client (required on first call)

    Returns:
        JobErrorLogger instance or None
    """
    global _error_logger
    if _error_logger is None and supabase_client is not None:
        _error_logger = JobErrorLogger(supabase_client)
    return _error_logger


def init_error_logger(supabase_client) -> JobErrorLogger:
    """
    Initialize the singleton JobErrorLogger.

    Args:
        supabase_client: Supabase client instance

    Returns:
        JobErrorLogger instance
    """
    global _error_logger
    _error_logger = JobErrorLogger(supabase_client)
    return _error_logger
