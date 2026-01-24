"""
Real email processing with streaming support for large files

Supports: MBOX, PST (Outlook Windows), OLM (Outlook Mac) files

Stage 2: Enhanced with error tracking for individual email failures
        - Redis tracking for real-time visibility
        - JobErrorLogger for persistent error storage in job_errors table
"""
import os
import logging
import traceback
from typing import Dict, Optional, Iterator, TYPE_CHECKING
from datetime import datetime

from ..extractors.file_extractor import FileExtractor
from ..extractors.base_extractor import BaseExtractor
from ..database.operations import EmailOperations
from ..database.redis_client import JobProgressManager
from .normalizer import EmailNormalizer
from .email_tagger import EmailTagger

if TYPE_CHECKING:
    from ..services.job_error_logger import JobErrorLogger

logger = logging.getLogger(__name__)


class EmailProcessor:
    """
    Processes emails from various sources with streaming support
    Handles extraction, normalization, and database insertion
    """

    def __init__(self, mailbox_id: str, connection_config: Dict, error_logger: Optional['JobErrorLogger'] = None):
        """
        Initialize email processor

        Args:
            mailbox_id: Database mailbox ID
            connection_config: Configuration dict with mailbox-specific settings
            error_logger: Optional JobErrorLogger for persistent error tracking
        """
        self.mailbox_id = mailbox_id
        self.connection_config = connection_config
        self.db_ops = EmailOperations(mailbox_id=mailbox_id)
        self.normalizer = EmailNormalizer()
        self.tagger = EmailTagger()
        self.extractor: Optional[BaseExtractor] = None
        self.date_filter: Optional[Dict] = None  # Date-based filtering
        self.filtered_count: int = 0  # Stage 2: Track emails filtered by date range
        # Stage 2: Error tracking - JobErrorLogger for persistent storage
        self.error_logger = error_logger
        # Stage 2: Redis for real-time visibility
        try:
            self.progress_manager = JobProgressManager()
        except Exception as e:
            logger.warning(f"Failed to initialize Redis progress manager: {e}")
            self.progress_manager = None

    def validate_configuration(self, mailbox_type: str) -> Dict:
        """
        Validate configuration and check file/connection accessibility

        Args:
            mailbox_type: Type of mailbox (mbox, pst, olm, imap, pop3, outlook)

        Returns:
            Dict with validation result and details
        """
        result = {
            'valid': False,
            'error': None,
            'details': {}
        }

        try:
            # File-based mailboxes (MBOX, PST, OLM)
            if mailbox_type in ["mbox", "pst", "olm"]:
                file_path = self.connection_config.get("file_path")

                if not file_path:
                    result['error'] = f"{mailbox_type.upper()} file path is required"
                    return result

                # Validate file extension (but don't enforce - FileExtractor will auto-detect)
                valid_extensions = {
                    'mbox': ['.mbox'],
                    'pst': ['.pst'],
                    'olm': ['.olm']
                }

                expected_exts = valid_extensions.get(mailbox_type, [])
                if expected_exts and not any(file_path.lower().endswith(ext) for ext in expected_exts):
                    logger.warning(f"File extension mismatch. Expected {expected_exts}, got: {file_path}")
                    # Continue anyway - FileExtractor will detect actual type

                # Expand user home directory
                file_path = os.path.expanduser(file_path)

                if not os.path.exists(file_path):
                    result['error'] = f"File not found: {file_path}"
                    return result

                if not os.path.isfile(file_path):
                    result['error'] = f"Path is not a file: {file_path}"
                    return result

                # Get file details
                file_size = os.path.getsize(file_path)
                result['details'] = {
                    'file_path': file_path,
                    'file_size': file_size,
                    'file_size_gb': round(file_size / (1024**3), 2),
                    'readable': os.access(file_path, os.R_OK),
                    'mailbox_type': mailbox_type
                }

                if not result['details']['readable']:
                    result['error'] = f"File is not readable: {file_path}"
                    return result

                logger.info(f"{mailbox_type.upper()} file validated: {file_path} ({result['details']['file_size_gb']} GB)")
                result['valid'] = True

            else:
                result['error'] = f"Unsupported mailbox type: {mailbox_type}. Supported types: mbox, pst, olm"

        except Exception as e:
            result['error'] = f"Validation error: {str(e)}"
            logger.error(f"Configuration validation failed: {e}")

        return result

    def initialize_extractor(self, mailbox_type: str) -> bool:
        """
        Initialize the appropriate extractor for the mailbox type

        Args:
            mailbox_type: Type of mailbox

        Returns:
            True if successful, False otherwise
        """
        try:
            # File-based extractors (MBOX, PST, OLM) - use unified FileExtractor for now
            if mailbox_type in ["mbox", "pst", "olm"]:
                file_source = self.connection_config.get("file_source", "local")
                
                if file_source == "google_drive":
                    # Google Drive file processing with streaming support
                    google_file_name = self.connection_config.get("google_drive_file_name", "Unknown file")
                    google_file_id = self.connection_config.get("google_drive_file_id")
                    
                    if not google_file_id:
                        raise ValueError(
                            f"Google Drive file ID is required for processing '{google_file_name}'."
                        )
                    
                    logger.info(f"Processing Google Drive file '{google_file_name}' with backend authentication")
                    
                    # Initialize FileExtractor with Google Drive config
                    self.extractor = FileExtractor()
                    # Store config and connect (will use service account authentication)
                    self.extractor.config = self.connection_config
                    self.extractor.connect()
                    
                    logger.info(f"Google Drive {mailbox_type.upper()} file extractor initialized: {google_file_name} (ID: {google_file_id})")
                    logger.info(f"Detected file type: {self.extractor.file_type}")
                    logger.info(f"Folder support: {self.extractor.get_capabilities().get('folder_support', False)}")
                    
                else:
                    # Local file processing
                    file_path = self.connection_config.get("file_path")
                    if not file_path:
                        raise ValueError("No file_path provided for local file processing")
                    
                    # Expand file path
                    file_path = os.path.expanduser(file_path)
                    self.extractor = FileExtractor()
                    self.extractor.connect(file_path)
                    logger.info(f"{mailbox_type.upper()} file extractor initialized: {file_path}")
                    logger.info(f"Detected file type: {self.extractor.file_type}")
                    logger.info(f"Folder support: {self.extractor.get_capabilities().get('folder_support', False)}")
                
                return True

            else:
                logger.error(f"Unsupported mailbox type: {mailbox_type}. Supported types: mbox, pst, olm")
                return False

        except Exception as e:
            logger.error(f"Failed to initialize extractor: {e}")
            logger.exception("Full traceback:")  # This will log the full stack trace
            return False

    def process_emails(
        self,
        job_id: str,
        max_emails: Optional[int] = None,
        batch_size: int = 5000,
        skip_duplicates: bool = True,
        enable_categorization: bool = False,
        date_filter: Optional[Dict] = None
    ) -> Dict:
        """
        Process emails from the configured source with streaming

        Args:
            job_id: Processing job ID for progress tracking
            max_emails: Maximum number of emails to process (None for all)
            batch_size: Number of emails per database batch
            skip_duplicates: Skip emails already in database
            enable_categorization: Enable email categorization (Stage 2)
            date_filter: Optional date range filter {'start_date': datetime, 'end_date': datetime}

        Returns:
            Dict with processing statistics
        """
        if not self.extractor:
            raise RuntimeError("Extractor not initialized. Call initialize_extractor() first.")

        self.date_filter = date_filter  # Store for use in normalization
        self.filtered_count = 0  # Reset filtered count for this job

        logger.info(f"Starting email processing for job {job_id}")
        logger.info(f"Config: max_emails={max_emails}, batch_size={batch_size}, skip_duplicates={skip_duplicates}, date_filter={date_filter}")

        # Note: Job status is already set to 'running' in process_emails_real before initialization
        # This ensures user sees the job is active immediately, not after initialization completes

        def checkpoint_callback(processed_count: int, last_message_id: str):
            """Callback for progress updates

            Uses shared progress tracker for Redis-based real-time tracking.
            Only syncs to database every 100 emails to reduce DB load.
            """
            try:
                # Use shared progress tracker (initialized by backend)
                from src.utils.progress_tracker import update_job_progress

                should_sync_db = update_job_progress(job_id, processed_count, 0)

                # Only write to database if Redis says it's time (every 100 emails)
                if should_sync_db:
                    self.db_ops.update_job_progress(
                        job_id=job_id,
                        processed_records=processed_count,
                        failed_records=0,
                        update_status=False
                    )
                    logger.info(f"[Progress] Synced {processed_count} emails to DB for job {job_id}")
                else:
                    logger.debug(f"[Progress] Redis updated: {processed_count} emails (no DB sync yet)")

            except ImportError as e:
                logger.warning(f"Shared progress tracker not available, using direct DB updates: {e}")
                # Fallback: direct database update (Redis not available)
                self.db_ops.update_job_progress(
                    job_id=job_id,
                    processed_records=processed_count,
                    failed_records=0,
                    update_status=False
                )
            except Exception as e:
                logger.warning(f"Failed to update progress (Redis or DB): {e}")
                # Try database as last resort
                try:
                    self.db_ops.update_job_progress(
                        job_id=job_id,
                        processed_records=processed_count,
                        failed_records=0,
                        update_status=False
                    )
                except Exception as db_error:
                    logger.error(f"Complete progress update failure: {db_error}")

        try:
            # Extract and normalize emails
            logger.info(f"[DB-INSERT] Starting email extraction for job {job_id}, mailbox_id={self.mailbox_id}")
            raw_emails = self.extractor.extract_emails(max_emails=max_emails)
            # Stage 2: Pass job_id for error tracking
            normalized_emails = self._normalize_email_stream(raw_emails, job_id=job_id)

            # Stream insert to database (with cancellation support)
            logger.info(f"[DB-INSERT] Starting database insert for job {job_id}, mailbox_id={self.mailbox_id}")
            result = self.db_ops.stream_insert_emails(
                emails=normalized_emails,
                mailbox_id=self.mailbox_id,
                batch_size=batch_size,
                checkpoint_callback=checkpoint_callback,
                skip_duplicates=skip_duplicates,
                job_id=job_id  # Pass job_id for cancellation checks
            )

            # Update job status based on result
            # Double-check current status - don't override if already stopped/cancelled
            current_status = None
            try:
                job_result = self.db_ops.client.table('processing_jobs').select('status').eq('id', job_id).execute()
                if job_result.data:
                    current_status = job_result.data[0].get('status')
            except Exception as e:
                logger.warning(f"Failed to check current job status: {e}")

            if current_status in ['stopped', 'cancelled']:
                # Job was already stopped - preserve that status
                logger.info(f"Job {job_id} already has status '{current_status}', preserving it")
                self.db_ops.update_job_progress(
                    job_id=job_id,
                    processed_records=result['total'],  # Total emails examined (includes new, skipped, failed)
                    failed_records=result['failed'],
                    filtered_records=self.filtered_count,  # Stage 2: Emails filtered by date range
                    status=current_status  # Keep current status
                )
            elif result.get('stopped', False):
                # Job was stopped by user
                self.db_ops.update_job_progress(
                    job_id=job_id,
                    processed_records=result['total'],  # Total emails examined (includes new, skipped, failed)
                    failed_records=result['failed'],
                    filtered_records=self.filtered_count,  # Stage 2: Emails filtered by date range
                    status='stopped'
                )
                logger.warning(f"Processing stopped by user for job {job_id}: {result}")
            else:
                # Job completed normally
                # Calculate effective total (examined + filtered)
                effective_total = result['total'] + self.filtered_count

                self.db_ops.update_job_progress(
                    job_id=job_id,
                    processed_records=result['total'],  # Total emails examined (includes new, skipped, failed)
                    failed_records=result['failed'],
                    filtered_records=self.filtered_count,  # Stage 2: Emails filtered by date range
                    status='completed',
                    error_log=result.get('errors', []) if result['failed'] > 0 else None
                )

                # Also update total_records to match effective total for accurate progress display
                # This ensures progress shows 100% when completed
                try:
                    self.db_ops.client.table('processing_jobs').update({
                        'total_records': effective_total
                    }).eq('id', job_id).execute()
                except Exception as e:
                    logger.warning(f"Failed to update total_records: {e}")

                logger.info(f"Processing completed for job {job_id}: {result['total']} examined ({result['success']} inserted, {result['skipped']} skipped duplicates, {result['failed']} failed, {self.filtered_count} filtered by date range)")
                if result['failed'] > 0 and result.get('errors'):
                    logger.warning(f"Job {job_id} had {result['failed']} failures. First few errors: {result['errors'][:3]}")

            # Stage 2: Save error summary to database for persistence
            if result['failed'] > 0 and self.progress_manager:
                try:
                    error_summary = self.progress_manager.build_error_summary_json(job_id)
                    self.db_ops.save_job_error_summary(job_id, error_summary)
                    logger.info(f"Saved error summary for job {job_id}: {error_summary.get('total_errors', 0)} errors")
                except Exception as e:
                    logger.warning(f"Failed to save error summary: {e}")

            # TODO: Implement categorization in Stage 2
            if enable_categorization:
                logger.info("Categorization requested but not yet implemented (Stage 2)")

            return result

        except Exception as e:
            error_msg = f"Processing failed: {str(e)}"
            logger.error(error_msg)

            # Check if job was already stopped (don't override stopped status)
            if self.db_ops.should_stop_job(job_id):
                # Job was stopped/cancelled - keep that status, just log the error
                logger.warning(f"Exception occurred after job was stopped: {error_msg}")
            else:
                # Job wasn't stopped - this is a genuine failure
                self.db_ops.update_job_progress(
                    job_id=job_id,
                    processed_records=0,
                    status='failed',
                    error_log=[error_msg]
                )

            raise

    def _normalize_email_stream(self, raw_emails: Iterator[Dict], job_id: str = None) -> Iterator[Dict]:
        """
        Generator that normalizes and tags emails one at a time

        Args:
            raw_emails: Iterator of raw email dicts from extractor
            job_id: Job ID for error tracking (Stage 2)

        Yields:
            Normalized and tagged email dicts
        """
        for raw_email in raw_emails:
            try:
                # Normalize email structure
                normalized = self.normalizer.normalize(raw_email)
                if normalized:
                    # Apply date filter if configured
                    if self.date_filter:
                        sent_date = normalized.get('sent_date')
                        if sent_date:
                            # Parse sent_date if it's a string
                            if isinstance(sent_date, str):
                                try:
                                    from datetime import datetime, timezone
                                    # Handle various date formats
                                    if 'T' in sent_date:
                                        sent_date = datetime.fromisoformat(sent_date.replace('Z', '+00:00'))
                                    else:
                                        sent_date = datetime.fromisoformat(sent_date)
                                    # Ensure timezone aware
                                    if sent_date.tzinfo is None:
                                        sent_date = sent_date.replace(tzinfo=timezone.utc)
                                except (ValueError, TypeError):
                                    sent_date = None

                            # Check date range
                            if sent_date:
                                start_date = self.date_filter.get('start_date')
                                end_date = self.date_filter.get('end_date')

                                if start_date and sent_date < start_date:
                                    self.filtered_count += 1
                                    continue  # Skip emails before start_date
                                if end_date and sent_date > end_date:
                                    self.filtered_count += 1
                                    continue  # Skip emails after end_date

                    # Tag email with basic attributes
                    tag_result = self.tagger.tag_email(normalized)

                    # Add tags to email
                    normalized['tags'] = tag_result.get('tags', [])
                    normalized['is_spam'] = tag_result.get('is_spam', False)
                    normalized['is_marketing'] = tag_result.get('is_marketing', False)
                    normalized['priority_score'] = tag_result.get('priority_score', 5)
                    normalized['sender_type'] = tag_result.get('sender_type', 'unknown')
                    # Stage 2: Mark as success initially (will be updated if DB insert fails)
                    normalized['processing_status'] = 'success'

                    yield normalized
            except Exception as e:
                error_msg = str(e)
                message_id = raw_email.get('message_id', 'unknown')
                subject = raw_email.get('subject', 'No subject')
                sender = raw_email.get('sender_email') or raw_email.get('from', 'Unknown')

                logger.warning(f"Failed to normalize email {message_id}: {e}")

                # Stage 2: Track error in Redis for real-time visibility
                if job_id and self.progress_manager:
                    try:
                        error_type = self._classify_error(e)
                        self.progress_manager.track_error(
                            job_id=job_id,
                            error_type=error_type,
                            error_message=error_msg[:500],
                            email_info={
                                'message_id': message_id,
                                'subject': subject[:200] if subject else None,
                                'sender_email': sender
                            }
                        )
                    except Exception as track_error:
                        logger.warning(f"Failed to track error in Redis: {track_error}")

                # Stage 2: Log error to job_errors table for persistence
                if job_id and self.error_logger:
                    try:
                        self.error_logger.log_email_error(
                            job_id=job_id,
                            error_message=error_msg,
                            mailbox_id=self.mailbox_id,
                            message_id=message_id if message_id != 'unknown' else None,
                            subject=subject[:200] if subject else None,
                            sender=sender,
                            phase="normalization",
                            exception=e
                        )
                    except Exception as log_error:
                        logger.debug(f"Failed to log error to job_errors: {log_error}")

                # Continue processing other emails

    def _classify_error(self, exception: Exception) -> str:
        """Classify error type from exception for reporting"""
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
        else:
            return 'other_error'

    def disconnect(self):
        """Disconnect from email source"""
        if self.extractor:
            try:
                self.extractor.disconnect()
                logger.info("Extractor disconnected")
            except Exception as e:
                logger.warning(f"Error disconnecting extractor: {e}")

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensure cleanup"""
        self.disconnect()
        return False
