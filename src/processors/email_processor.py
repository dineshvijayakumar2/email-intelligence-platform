"""
Real email processing with streaming support for large files

Supports: MBOX, PST (Outlook Windows), OLM (Outlook Mac) files
"""
import os
import logging
from typing import Dict, Optional, Iterator
from datetime import datetime

from ..extractors.file_extractor import FileExtractor
from ..extractors.base_extractor import BaseExtractor
from ..database.operations import EmailOperations
from .normalizer import EmailNormalizer
from .email_tagger import EmailTagger

logger = logging.getLogger(__name__)


class EmailProcessor:
    """
    Processes emails from various sources with streaming support
    Handles extraction, normalization, and database insertion
    """

    def __init__(self, mailbox_id: str, connection_config: Dict):
        """
        Initialize email processor

        Args:
            mailbox_id: Database mailbox ID
            connection_config: Configuration dict with mailbox-specific settings
        """
        self.mailbox_id = mailbox_id
        self.connection_config = connection_config
        self.db_ops = EmailOperations(mailbox_id=mailbox_id)
        self.normalizer = EmailNormalizer()
        self.tagger = EmailTagger()
        self.extractor: Optional[BaseExtractor] = None

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
            # File-based extractors (MBOX, PST, OLM) - use unified FileExtractor
            if mailbox_type in ["mbox", "pst", "olm"]:
                # Expand file path
                file_path = os.path.expanduser(self.connection_config.get("file_path"))
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
        enable_categorization: bool = False
    ) -> Dict:
        """
        Process emails from the configured source with streaming

        Args:
            job_id: Processing job ID for progress tracking
            max_emails: Maximum number of emails to process (None for all)
            batch_size: Number of emails per database batch
            skip_duplicates: Skip emails already in database
            enable_categorization: Enable email categorization (Stage 2)

        Returns:
            Dict with processing statistics
        """
        if not self.extractor:
            raise RuntimeError("Extractor not initialized. Call initialize_extractor() first.")

        logger.info(f"Starting email processing for job {job_id}")
        logger.info(f"Config: max_emails={max_emails}, batch_size={batch_size}, skip_duplicates={skip_duplicates}")

        # Update job status to running
        self.db_ops.update_job_progress(
            job_id=job_id,
            processed_records=0,
            status='running'
        )

        def checkpoint_callback(processed_count: int, last_message_id: str):
            """Callback for progress updates"""
            self.db_ops.update_job_progress(
                job_id=job_id,
                processed_records=processed_count,
                status='running'
            )
            logger.debug(f"Checkpoint: {processed_count} emails processed, last: {last_message_id}")

        try:
            # Extract and normalize emails
            raw_emails = self.extractor.extract_emails(max_emails=max_emails)
            normalized_emails = self._normalize_email_stream(raw_emails)

            # Stream insert to database (with cancellation support)
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
                    processed_records=result['total'],
                    failed_records=result['failed'],
                    status=current_status  # Keep current status
                )
            elif result.get('stopped', False):
                # Job was stopped by user
                self.db_ops.update_job_progress(
                    job_id=job_id,
                    processed_records=result['total'],  # Total emails processed (not just inserted)
                    failed_records=result['failed'],
                    status='stopped'
                )
                logger.warning(f"Processing stopped by user for job {job_id}: {result}")
            else:
                # Job completed normally
                self.db_ops.update_job_progress(
                    job_id=job_id,
                    processed_records=result['total'],  # Total emails processed (not just inserted)
                    failed_records=result['failed'],
                    status='completed'
                )
                logger.info(f"Processing completed for job {job_id}: {result} ({result['skipped']} skipped as duplicates)")

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

    def _normalize_email_stream(self, raw_emails: Iterator[Dict]) -> Iterator[Dict]:
        """
        Generator that normalizes and tags emails one at a time

        Args:
            raw_emails: Iterator of raw email dicts from extractor

        Yields:
            Normalized and tagged email dicts
        """
        for raw_email in raw_emails:
            try:
                # Normalize email structure
                normalized = self.normalizer.normalize(raw_email)
                if normalized:
                    # Tag email with basic attributes
                    tag_result = self.tagger.tag_email(normalized)

                    # Add tags to email
                    normalized['tags'] = tag_result.get('tags', [])
                    normalized['is_spam'] = tag_result.get('is_spam', False)
                    normalized['is_marketing'] = tag_result.get('is_marketing', False)
                    normalized['priority_score'] = tag_result.get('priority_score', 5)
                    normalized['sender_type'] = tag_result.get('sender_type', 'unknown')

                    yield normalized
            except Exception as e:
                logger.warning(f"Failed to normalize email {raw_email.get('message_id', 'unknown')}: {e}")
                # Continue processing other emails

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
