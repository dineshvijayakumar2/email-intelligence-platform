"""
Extraction Orchestrator Service - Sprint 2 + Sprint 3 Surgery

Purpose: Coordinate the complete 13-step customer data extraction pipeline
Main entry point for extraction jobs

13-Step Pipeline:
1.  Validate prerequisites (tables, mailbox, permissions)
2.  Extract contacts from emails (contact_extractor)
3.  Deduplicate and filter contacts
4.  Resolve companies by domain (company_resolver)
5.  Upsert customer_contacts records
6.  Upsert customer_companies records + QB enrichment (Sprint 3)
7.  Classify roles from signatures (role_classifier)
8.  Update role information in customer_contacts
9.  Link emails to contacts/companies (email_linker)
10. Calculate initial engagement scores
11. Update company statistics
12. Generate extraction report
13. Mark job as complete

Features:
- Job tracking in extraction_jobs table
- Progress updates after each step
- Error handling and rollback on failures
- Detailed logging and metrics
- Resume capability for failed jobs

Author: Sprint 2 Implementation
"""

from typing import Dict, Optional, List, Any
import logging
import time
from datetime import datetime
from uuid import uuid4
import traceback

from ..database.supabase_client import SupabaseClient
from ..database.redis_client import JobProgressManager, RedisClient
from .contact_extractor import ContactExtractor
from .company_resolver import CompanyResolver
from .role_classifier import RoleClassifier
from .email_linker import EmailLinker

logger = logging.getLogger(__name__)


class ExtractionOrchestrator:
    """
    Orchestrate the complete customer data extraction pipeline

    Usage:
        orchestrator = ExtractionOrchestrator(mailbox_id="uuid-here")

        # Run full extraction
        result = orchestrator.run_extraction()

        # Run with specific options
        result = orchestrator.run_extraction(
            exclude_mailing_lists=True,
            exclude_noreply=True,
            force_relink=False
        )

        # Resume failed job
        result = orchestrator.resume_extraction(job_id="uuid-here")
    """

    TOTAL_STEPS = 13

    def __init__(
        self,
        mailbox_id: str,
        client_id: Optional[str] = None,
        use_redis: bool = True,
        extraction_mode: str = 'full',
        lookback_days: int = 7
    ):
        """
        Initialize extraction orchestrator

        Args:
            mailbox_id: Mailbox UUID to process
            client_id: Optional client UUID (auto-fetched if not provided)
            use_redis: Enable Redis progress tracking (default True)
            extraction_mode: 'full' or 'incremental' (default 'full')
            lookback_days: Days to look back for incremental mode (default 7)
        """
        self.mailbox_id = mailbox_id
        self.extraction_mode = extraction_mode
        self.lookback_days = lookback_days
        self.client = SupabaseClient.get_client(use_service_key=True)

        # Fetch client_id if not provided
        if not client_id:
            self.client_id = self._fetch_client_id()
        else:
            self.client_id = client_id

        # Job tracking
        self.job_id: Optional[str] = None
        self.current_step: int = 0

        # Cancellation callback — set by pipeline handler to check stop_event
        self._stop_check = None

        # Step results storage
        self.step_results: Dict[int, Any] = {}

        # Redis progress tracking
        self.use_redis = use_redis
        self.redis_manager: Optional[JobProgressManager] = None
        if use_redis:
            try:
                self.redis_manager = JobProgressManager()
                logger.info("Redis progress tracking enabled")
            except Exception as e:
                logger.warning(f"Failed to initialize Redis, progress tracking disabled: {e}")
                self.use_redis = False

        logger.info(f"ExtractionOrchestrator initialized for mailbox {mailbox_id}, client {self.client_id}")

    def _fetch_client_id(self) -> str:
        """
        Fetch client_id from mailbox

        Returns:
            Client UUID
        """
        try:
            response = (
                self.client.table('mailboxes')
                .select('client_id')
                .eq('id', self.mailbox_id)
                .execute()
            )

            if not response.data:
                raise ValueError(f"Mailbox {self.mailbox_id} not found")

            client_id = response.data[0].get('client_id')
            if not client_id:
                raise ValueError(f"Mailbox {self.mailbox_id} has no client_id")

            return client_id

        except Exception as e:
            logger.error(f"Failed to fetch client_id: {e}")
            raise

    @staticmethod
    def _execute_with_retry(query_builder, max_retries: int = 3, base_delay: float = 2.0):
        """
        Execute a Supabase query with retry for transient errors (SSL, network, 5xx).

        Args:
            query_builder: A Supabase query builder ready to .execute()
            max_retries: Maximum retry attempts (default 3)
            base_delay: Base delay in seconds, doubles each retry (2s, 4s, 8s)

        Returns:
            The query response

        Raises:
            The last exception if all retries exhausted
        """
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                return query_builder.execute()
            except Exception as e:
                last_error = e
                error_str = str(e)
                # Retry on transient errors: SSL, network, 5xx, socket exhaustion
                is_transient = isinstance(e, OSError) or any(keyword in error_str for keyword in [
                    'SSL handshake failed', '525', '502', '503', '504',
                    'Connection reset', 'Connection refused', 'timed out',
                    'JSON could not be generated', 'ECONNRESET', 'ETIMEDOUT',
                    'Resource temporarily unavailable', 'ConnectionTerminated',
                    'PROTOCOL_ERROR',
                ])
                if is_transient and attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"Transient Supabase error (attempt {attempt + 1}/{max_retries + 1}), retrying in {delay}s: {error_str[:200]}")
                    time.sleep(delay)
                    continue
                raise
        raise last_error

    def _get_emails_in_scope(self) -> tuple[List[str], Optional[str], Optional[str]]:
        """
        Get email IDs to process based on extraction mode.

        Paginates in batches of 500 to avoid Supabase row limits.
        Results are cached after the first call to avoid redundant 143K-row scans.

        Returns:
            Tuple of (email_ids, date_range_start, date_range_end)
        """
        if hasattr(self, '_cached_scope'):
            return self._cached_scope
        PAGE_SIZE = 500
        try:
            if self.extraction_mode == 'full':
                # Get total count first for visibility
                count_resp = self._execute_with_retry(
                    self.client.table('emails')
                    .select('id', count='exact')
                    .eq('mailbox_id', self.mailbox_id)
                )
                total_in_db = count_resp.count or 0
                estimated_pages = (total_in_db + PAGE_SIZE - 1) // PAGE_SIZE
                logger.debug(f"Full mode: {total_in_db} emails, ~{estimated_pages} pages of {PAGE_SIZE}")

                all_rows = []
                offset = 0
                page = 0

                while True:
                    page += 1
                    response = self._execute_with_retry(
                        self.client.table('emails')
                        .select('id, processing_status')
                        .eq('mailbox_id', self.mailbox_id)
                        .order('created_at')
                        .range(offset, offset + PAGE_SIZE - 1)
                    )
                    raw_batch = response.data or []
                    filtered = [e for e in raw_batch if e.get('processing_status') != 'failed']
                    all_rows.extend(filtered)
                    logger.debug(f"Full mode page {page}/{estimated_pages}: raw={len(raw_batch)}, kept={len(filtered)}")

                    if len(raw_batch) == 0:
                        break
                    offset += len(raw_batch)  # Use actual count returned, not PAGE_SIZE

                logger.info(f"Full extraction mode: Processing {len(all_rows)} emails (from {total_in_db} total)")
                self._cached_scope = ([email['id'] for email in all_rows], None, None)
                return self._cached_scope

            else:  # incremental
                from datetime import timedelta
                date_range_end = datetime.utcnow()
                date_range_start = date_range_end - timedelta(days=self.lookback_days)

                logger.debug(f"Incremental mode: {self.lookback_days}d lookback, {date_range_start.date()} → {date_range_end.date()}")

                # Get total count for date range (only unextracted emails)
                count_resp = self._execute_with_retry(
                    self.client.table('emails')
                    .select('id', count='exact')
                    .eq('mailbox_id', self.mailbox_id)
                    .gte('sent_date', date_range_start.isoformat())
                    .lte('sent_date', date_range_end.isoformat())
                    .is_('extracted_at', 'null')
                )
                total_in_range = count_resp.count or 0
                estimated_pages = (total_in_range + PAGE_SIZE - 1) // PAGE_SIZE
                logger.debug(f"Incremental mode: {total_in_range} emails in range, ~{estimated_pages} pages")

                all_rows = []
                offset = 0
                page = 0

                while True:
                    page += 1
                    response = self._execute_with_retry(
                        self.client.table('emails')
                        .select('id, processing_status')
                        .eq('mailbox_id', self.mailbox_id)
                        .gte('sent_date', date_range_start.isoformat())
                        .lte('sent_date', date_range_end.isoformat())
                        .is_('extracted_at', 'null')
                        .order('sent_date')
                        .range(offset, offset + PAGE_SIZE - 1)
                    )
                    raw_batch = response.data or []
                    filtered = [e for e in raw_batch if e.get('processing_status') != 'failed']
                    all_rows.extend(filtered)
                    logger.debug(f"Incremental page {page}/{estimated_pages}: raw={len(raw_batch)}, kept={len(filtered)}")

                    if len(raw_batch) == 0:
                        break
                    offset += len(raw_batch)

                logger.info(f"Incremental mode: Processing {len(all_rows)} emails (from {total_in_range} in range)")
                self._cached_scope = (
                    [email['id'] for email in all_rows],
                    date_range_start.isoformat(),
                    date_range_end.isoformat()
                )
                return self._cached_scope

        except Exception as e:
            logger.error(f"Failed to get emails in scope: {e}")
            raise

    def run_extraction(
        self,
        exclude_mailing_lists: bool = True,
        exclude_noreply: bool = True,
        exclude_shared: bool = True,
        exclude_internal: bool = True,
        force_relink: bool = False,
        skip_role_classification: bool = False,
        lightweight: bool = False,
    ) -> Dict:
        """
        Run the extraction pipeline.

        Args:
            exclude_mailing_lists: Skip mailing list emails in contact extraction
            exclude_noreply: Skip no-reply addresses
            exclude_shared: Skip shared addresses (info@, sales@, etc.)
            exclude_internal: Skip internal domain contacts
            force_relink: Force relink even if emails already linked
            skip_role_classification: Skip role classification step (faster)
            lightweight: If True, only run steps 1-9 (contact/company extraction + email linking).
                        Skips heavy steps 10-13 (engagement scoring, response times, company stats).
                        Use for auto-sync; run full extraction manually when needed.

        Returns:
            Dictionary with extraction results and statistics
        """
        # Set thread-local context so ALL sub-service logs inherit mailbox/client
        from ..utils.log_stream import set_log_context, clear_log_context
        set_log_context(mailbox_id=self.mailbox_id, client_id=self.client_id)

        logger.info(f"Pipeline start: mode={self.extraction_mode}",
                     extra={'mailbox_id': self.mailbox_id, 'client_id': self.client_id})

        start_time = datetime.utcnow()

        try:
            # Create extraction job
            self.job_id = self._create_job()
            logger.info(f"Created extraction job: {self.job_id}")

            # Store options
            options = {
                'exclude_mailing_lists': exclude_mailing_lists,
                'exclude_noreply': exclude_noreply,
                'exclude_shared': exclude_shared,
                'exclude_internal': exclude_internal,
                'force_relink': force_relink,
                'skip_role_classification': skip_role_classification,
            }

            # ============================================================
            # STEP 1: Validate Prerequisites
            # ============================================================
            self._run_step(1, "Validate prerequisites", self._step_validate)

            if self.step_results.get(1, {}).get('skipped'):
                logger.info("Incremental extraction: no new emails — completing early")
                if self.job_id:
                    self._update_job_status('completed')
                from ..utils.log_stream import clear_log_context
                clear_log_context()
                return {
                    'success': True,
                    'job_id': self.job_id,
                    'duration_seconds': (datetime.utcnow() - start_time).total_seconds(),
                    'steps_completed': 1,
                    'results': self.step_results,
                }

            # ============================================================
            # STEP 2: Extract Contacts
            # ============================================================
            self._run_step(2, "Extract contacts from emails",
                          lambda: self._step_extract_contacts(
                              exclude_mailing_lists,
                              exclude_noreply,
                              exclude_shared
                          ))

            # ============================================================
            # STEP 3: Deduplicate Contacts
            # ============================================================
            self._run_step(3, "Deduplicate and filter contacts",
                          self._step_deduplicate_contacts)

            # ============================================================
            # STEP 4: Resolve Companies
            # ============================================================
            self._run_step(4, "Resolve companies by domain",
                          lambda: self._step_resolve_companies(exclude_internal))

            # ============================================================
            # STEP 5: Upsert Companies (BEFORE contacts so company IDs exist)
            # ============================================================
            self._run_step(5, "Create/update customer_companies",
                          self._step_upsert_companies)

            # ============================================================
            # STEP 6: Upsert Contacts (companies already have DB IDs)
            # ============================================================
            self._run_step(6, "Create/update customer_contacts",
                          self._step_upsert_contacts)

            # ============================================================
            # STEP 7: Classify Roles
            # ============================================================
            if not skip_role_classification:
                self._run_step(7, "Classify roles from signatures",
                              self._step_classify_roles)

                # ============================================================
                # STEP 8: Update Role Information
                # ============================================================
                self._run_step(8, "Update role information",
                              self._step_update_roles)
            else:
                logger.info("Skipping steps 7-8 (role classification)")
                self.current_step = 8

            # ============================================================
            # STEP 9: Link Emails
            # ============================================================
            self._run_step(9, "Link emails to contacts/companies",
                          lambda: self._step_link_emails(force_relink))

            # Stamp extracted_at on all emails in scope so incremental mode skips them next run
            email_ids_in_scope, _, _ = self._get_emails_in_scope()
            if email_ids_in_scope:
                timestamp = datetime.utcnow().isoformat()
                for i in range(0, len(email_ids_in_scope), 500):
                    batch = email_ids_in_scope[i:i + 500]
                    try:
                        self._execute_with_retry(
                            self.client.table('emails')
                            .update({'extracted_at': timestamp})
                            .in_('id', batch)
                        )
                    except Exception as e:
                        logger.warning(f"Failed to set extracted_at for batch {i // 500}: {e}")
                logger.info(f"Stamped extracted_at on {len(email_ids_in_scope)} emails")
                if hasattr(self, '_cached_scope'):
                    del self._cached_scope

            # Assign canonical_thread_id to new emails + update affected threads
            # Runs in both full and lightweight mode
            self._check_stop("assign_threads")
            self._assign_canonical_threads()
            self._check_stop("evaluate_threads")
            self._update_affected_threads()

            # Update email counts on contacts + companies from junction table
            self._check_stop("refresh_counts")
            self._refresh_email_counts()

            if lightweight:
                # Lightweight mode: skip heavy analytics steps (10-12)
                logger.info("Lightweight mode: skipping steps 10-12 (engagement, stats, report)")
                self.current_step = 12

                # ============================================================
                # STEP 13: Complete Job (still finalize)
                # ============================================================
                self._run_step(13, "Finalize extraction job",
                              self._step_complete_job)
            else:
                # ============================================================
                # STEP 10: Calculate Engagement Scores
                # ============================================================
                self._run_step(10, "Calculate engagement scores",
                              self._step_calculate_engagement)

                # ============================================================
                # STEP 11: Update Company Statistics
                # ============================================================
                self._run_step(11, "Update company statistics",
                              self._step_update_company_stats)

                # ============================================================
                # STEP 12: Generate Report
                # ============================================================
                self._run_step(12, "Generate extraction report",
                              self._step_generate_report)

                # ============================================================
                # STEP 13: Complete Job
                # ============================================================
                self._run_step(13, "Finalize extraction job",
                              self._step_complete_job)

            # Embed newly extracted emails (runs on un-embedded records only)
            self._check_stop("embed_emails")
            self._embed_new_emails()

            # Auto-trigger AI classification for unanalyzed emails.
            self._check_stop("ai_classify")
            self._auto_trigger_ai_analysis()

            # Re-evaluate affected threads now that AI intent is available.
            self._check_stop("evaluate_threads_final")
            try:
                self._update_affected_threads()
            except Exception as e:
                logger.warning(f"Post-AI thread re-evaluation failed (non-critical): {e}")

            # Calculate duration
            duration = (datetime.utcnow() - start_time).total_seconds()

            logger.info(f"Pipeline complete: {duration:.1f}s, {self.current_step} steps",
                        extra={'mailbox_id': self.mailbox_id, 'client_id': self.client_id})

            clear_log_context()
            return {
                'success': True,
                'job_id': self.job_id,
                'duration_seconds': duration,
                'steps_completed': self.current_step,
                'results': self.step_results
            }

        except InterruptedError:
            logger.info(f"Extraction pipeline stopped at step {self.current_step}",
                        extra={'mailbox_id': self.mailbox_id, 'client_id': self.client_id})
            if self.job_id:
                self._update_job_status('interrupted')
            clear_log_context()
            raise  # Let the pipeline handler catch this cleanly

        except Exception as e:
            logger.error(f"Extraction pipeline failed: {e}",
                        extra={'mailbox_id': self.mailbox_id, 'client_id': self.client_id})
            logger.error(traceback.format_exc())

            # Mark job as failed
            if self.job_id:
                self._update_job_status('failed', error=str(e))

            clear_log_context()
            return {
                'success': False,
                'job_id': self.job_id,
                'error': str(e),
                'failed_at_step': self.current_step,
                'results': self.step_results
            }

    def _check_stop(self, label: str = ""):
        """Raise InterruptedError if the caller has requested a stop."""
        if self._stop_check and self._stop_check():
            logger.info(f"Stop requested before {label} — aborting extraction")
            raise InterruptedError(f"Stop requested before {label}")

    def _run_step(self, step_num: int, description: str, step_function):
        """
        Run a single pipeline step with error handling and tracking

        Args:
            step_num: Step number (1-13)
            description: Step description
            step_function: Function to execute
        """
        self.current_step = step_num
        _ctx = {'mailbox_id': self.mailbox_id, 'client_id': self.client_id, 'step': step_num}

        if self._stop_check and self._stop_check():
            logger.info(f"── Step {step_num}/{self.TOTAL_STEPS}: {description} — SKIPPED (stop requested)", extra=_ctx)
            raise InterruptedError(f"Stop requested before step {step_num}")

        logger.info(f"── Step {step_num}/{self.TOTAL_STEPS}: {description}", extra=_ctx)

        step_start = datetime.utcnow()

        try:
            # Update job progress
            self._update_job_progress(step_num, description)

            # Execute step
            result = step_function()

            # Store result
            self.step_results[step_num] = result

            # Calculate step duration
            step_duration = (datetime.utcnow() - step_start).total_seconds()

            summary_str = ""
            if isinstance(result, dict):
                # Only log scalar values — skip lists/dicts (they contain full data payloads)
                parts = [
                    f"{k}={v}" for k, v in result.items()
                    if k != 'errors' and not isinstance(v, (list, dict))
                ]
                if parts:
                    summary_str = " | " + ", ".join(parts)
            logger.info(f"Step {step_num} done in {step_duration:.1f}s{summary_str}", extra=_ctx)

        except Exception as e:
            logger.error(f"Step {step_num} failed: {e}")
            # Steps 1-8 are critical (data extraction) — must abort on failure
            # Steps 9-12 are enrichment/analytics — log and continue
            if step_num <= 8:
                raise
            logger.warning(f"Step {step_num} is non-critical — continuing pipeline")
            self.step_results[step_num] = {'error': str(e)}

    def _create_job(self) -> str:
        """
        Create extraction_jobs record in database and Redis

        Returns:
            Job UUID
        """
        # Get emails in scope and date range
        email_ids, date_start, date_end = self._get_emails_in_scope()

        job_data = {
            'id': str(uuid4()),
            'client_id': self.client_id,
            'mailbox_id': self.mailbox_id,
            'status': 'processing',
            'extraction_mode': self.extraction_mode,
            'emails_in_scope': len(email_ids),
            'date_range_start': date_start,
            'date_range_end': date_end,
            'current_step': 'Starting pipeline',
            'current_step_number': 0,
            'total_steps': self.TOTAL_STEPS,
            'started_at': datetime.utcnow().isoformat(),
            'errors': []
        }

        response = (
            self.client.table('extraction_jobs')
            .insert(job_data)
            .execute()
        )

        # Initialize Redis tracking
        if self.use_redis and self.redis_manager:
            self.redis_manager.update_progress(
                job_data['id'],
                processed=0,
                failed=0,
                status='processing',
                current_step='Starting pipeline',
                current_step_number=0,
                total_steps=self.TOTAL_STEPS,
                mailbox_id=self.mailbox_id,
                client_id=self.client_id
            )

        return job_data['id']

    def _update_job_progress(self, step_num: int, description: str):
        """
        Update job progress in database and Redis

        Args:
            step_num: Current step number
            description: Step description
        """
        if not self.job_id:
            return

        try:
            update_data = {
                'current_step': description,
                'current_step_number': step_num,
                'updated_at': datetime.utcnow().isoformat()
            }

            # Retry once on transient Cloudflare/Supabase errors
            for attempt in range(2):
                try:
                    self.client.table('extraction_jobs').update(update_data).eq('id', self.job_id).execute()
                    break
                except Exception as db_err:
                    if attempt == 0 and ('400' in str(db_err) or 'Bad Request' in str(db_err)):
                        import time; time.sleep(1)
                    else:
                        raise db_err

            # Update Redis
            if self.use_redis and self.redis_manager:
                self.redis_manager.update_progress(
                    self.job_id,
                    processed=step_num,
                    failed=0,
                    status='processing',
                    current_step=description,
                    current_step_number=step_num,
                    total_steps=self.TOTAL_STEPS
                )

        except Exception as e:
            logger.warning(f"Failed to update job progress: {e}")

    def _update_job_status(self, status: str, error: Optional[str] = None):
        """
        Update job status in database and Redis

        Args:
            status: Job status (running, completed, failed)
            error: Optional error message
        """
        if not self.job_id:
            return

        try:
            update_data = {
                'status': status,
                'updated_at': datetime.utcnow().isoformat()
            }

            if status == 'completed':
                update_data['completed_at'] = datetime.utcnow().isoformat()

            if error:
                update_data['errors'] = [error]

            self.client.table('extraction_jobs').update(update_data).eq('id', self.job_id).execute()

            # Update Redis
            if self.use_redis and self.redis_manager:
                redis_update = {
                    'status': status,
                    'current_step_number': self.current_step,
                    'total_steps': self.TOTAL_STEPS
                }

                if error:
                    redis_update['error'] = error

                self.redis_manager.update_progress(
                    self.job_id,
                    processed=self.current_step,
                    failed=1 if error else 0,
                    **redis_update
                )

        except Exception as e:
            logger.warning(f"Failed to update job status: {e}")

    def get_progress(self, job_id: str) -> Optional[Dict]:
        """
        Get job progress from Redis (fast) or database (fallback)

        Args:
            job_id: Job ID to check

        Returns:
            Dictionary with progress information or None
        """
        # Try Redis first (much faster)
        if self.use_redis and self.redis_manager:
            progress = self.redis_manager.get_progress(job_id)
            if progress:
                return progress

        # Fallback to database
        try:
            response = (
                self.client.table('extraction_jobs')
                .select('status, current_step, current_step_number, total_steps')
                .eq('id', job_id)
                .execute()
            )

            if response.data:
                return response.data[0]

            return None

        except Exception as e:
            logger.error(f"Failed to get progress for job {job_id}: {e}")
            return None

    # ========================================================================
    # PIPELINE STEPS
    # ========================================================================

    def _step_validate(self) -> Dict:
        """
        Step 1: Validate prerequisites

        Returns:
            Validation results
        """
        logger.info("Validating database tables, mailbox, and permissions")

        # Check required tables exist
        required_tables = [
            'emails', 'customer_contacts', 'customer_companies',
            'internal_domains', 'free_email_providers', 'extraction_jobs'
        ]

        # Check mailbox exists and get email count
        mailbox_response = (
            self.client.table('mailboxes')
            .select('id, email_address, mailbox_type')
            .eq('id', self.mailbox_id)
            .execute()
        )

        if not mailbox_response.data:
            raise ValueError(f"Mailbox {self.mailbox_id} not found")

        mailbox = mailbox_response.data[0]

        # Get emails in scope based on extraction mode
        email_ids, date_start, date_end = self._get_emails_in_scope()

        emails_in_scope = len(email_ids)

        if emails_in_scope == 0:
            if self.extraction_mode == 'incremental':
                logger.info(f"No new emails in scope for incremental extraction — nothing to do")
                return {'emails_in_scope': 0, 'skipped': True}
            raise ValueError(f"No emails in scope for {self.extraction_mode} extraction")

        logger.info(f"Mailbox validated: {mailbox['email_address']} ({mailbox['mailbox_type']})")
        logger.info(f"Extraction mode: {self.extraction_mode}")
        if self.extraction_mode == 'incremental':
            logger.info(f"Date range: {date_start} to {date_end}")
            logger.info(f"Lookback days: {self.lookback_days}")
        logger.info(f"Emails in scope: {emails_in_scope}")

        return {
            'mailbox': mailbox,
            'extraction_mode': self.extraction_mode,
            'emails_in_scope': emails_in_scope,
            'date_range_start': date_start,
            'date_range_end': date_end,
            'required_tables': required_tables
        }

    def _step_extract_contacts(
        self,
        exclude_mailing_lists: bool,
        exclude_noreply: bool,
        exclude_shared: bool
    ) -> Dict:
        """
        Step 2: Extract contacts from emails

        Returns:
            Extraction results with contact list
        """
        extractor = ContactExtractor(mailbox_id=self.mailbox_id, client_id=self.client_id)

        # In incremental mode, only extract contacts from scoped emails
        scoped_ids = None
        if self.extraction_mode != 'full':
            email_ids, _, _ = self._get_emails_in_scope()
            if email_ids:
                scoped_ids = email_ids

        contacts = extractor.extract_contacts(
            exclude_mailing_lists=exclude_mailing_lists,
            exclude_noreply=exclude_noreply,
            exclude_shared=exclude_shared,
            email_ids=scoped_ids,
        )

        summary = extractor.get_contact_summary()

        logger.info(f"Extracted {len(contacts)} contacts")

        return {
            'contacts': contacts,
            'summary': summary,
            'total_contacts': len(contacts)
        }

    def _step_deduplicate_contacts(self) -> Dict:
        """
        Step 3: Deduplicate contacts (already done by contact_extractor)

        Returns:
            Deduplication results
        """
        contacts = self.step_results[2]['contacts']

        # Contacts are already deduplicated by email address
        # This step is a placeholder for future enhancements
        # (e.g., fuzzy matching, merge similar names, etc.)

        logger.info(f"Contacts already deduplicated: {len(contacts)} unique emails")

        return {
            'unique_contacts': len(contacts),
            'duplicates_removed': 0
        }

    def _step_resolve_companies(self, exclude_internal: bool) -> Dict:
        """
        Step 4: Resolve companies by domain

        Returns:
            Company resolution results
        """
        contacts = self.step_results[2]['contacts']

        resolver = CompanyResolver(client_id=self.client_id)

        companies = resolver.resolve_companies(
            contacts=contacts,
            exclude_internal=exclude_internal,
            group_free_providers=False
        )

        summary = resolver.get_resolution_summary(companies)

        logger.info(f"Resolved {len(companies)} companies")

        return {
            'companies': companies,
            'summary': summary,
            'total_companies': len(companies)
        }

    def _step_upsert_contacts(self) -> Dict:
        """
        Step 5: Create/update customer_contacts records (batch insert)

        Returns:
            Upsert results
        """
        contacts = self.step_results[2]['contacts']
        companies = self.step_results[4]['companies']

        # Build email → company_id mapping from the database (definitive source)
        # The in-memory company.company_id may be NULL if the upsert response didn't match
        email_to_company: dict = {}

        # First try in-memory mapping (fast)
        for company in companies:
            if company.company_id:
                for email in company.contact_emails:
                    email_to_company[email.lower()] = company.company_id

        # If most are NULL, rebuild from DB (domain → company lookup)
        null_count = sum(1 for c in companies if not c.company_id)
        if null_count > len(companies) * 0.3:
            logger.warning(f"{null_count}/{len(companies)} companies have NULL IDs — rebuilding from DB")
            # Fetch all companies for this client → build domain → company_id map
            db_companies: list = []
            offset = 0
            while True:
                resp = self.client.table('customer_companies').select(
                    'id, email_domains'
                ).eq('client_id', self.client_id).range(offset, offset + 999).execute()
                rows = resp.data or []
                db_companies.extend(rows)
                if len(rows) == 0:
                    break
                offset += len(rows)

            domain_to_company = {}
            for c in db_companies:
                for d in (c.get('email_domains') or []):
                    domain_to_company[d.lower()] = c['id']

            # Map contact emails → company via domain
            for contact in contacts:
                email_lower = contact['email'].lower()
                if email_lower not in email_to_company:
                    domain = email_lower.split('@')[1] if '@' in email_lower else None
                    if domain and domain in domain_to_company:
                        email_to_company[email_lower] = domain_to_company[domain]

            logger.info(f"Rebuilt email→company mapping: {len(email_to_company)} emails mapped to companies")

        mapped_count = sum(1 for v in email_to_company.values() if v)
        logger.info(f"Upserting {len(contacts)} contacts — {mapped_count} have company links")

        # First, fetch ALL existing contacts for this client (paginated)
        existing_emails = {}
        offset = 0
        PAGE_SIZE = 1000
        while True:
            batch_resp = (
                self.client.table('customer_contacts')
                .select('id, email_address')
                .eq('client_id', self.client_id)
                .range(offset, offset + PAGE_SIZE - 1)
                .execute()
            )
            rows = batch_resp.data or []
            for row in rows:
                existing_emails[row['email_address'].lower()] = row['id']
            if len(rows) == 0:
                break
            offset += len(rows)
        logger.info(f"Found {len(existing_emails)} existing contacts for this client")

        # Separate contacts into INSERT and UPDATE lists
        to_insert = []
        to_update = []
        timestamp = datetime.utcnow().isoformat()

        for contact in contacts:
            company_id = email_to_company.get(contact['email'].lower())
            email_lower = contact['email'].lower()

            contact_data = {
                'email_address': contact['email'],
                'first_name': contact.get('first_name'),
                'last_name': contact.get('last_name'),
                'full_name': contact.get('display_name'),
                'customer_company_id': company_id,
                'client_id': self.client_id,
                'contact_type': contact.get('contact_type', 'person'),  # New field
                'updated_at': timestamp
            }

            if email_lower in existing_emails:
                # Update existing
                contact_data['id'] = existing_emails[email_lower]
                to_update.append(contact_data)
            else:
                # Insert new
                contact_data['created_at'] = timestamp
                to_insert.append(contact_data)

        logger.info(f"Prepared: {len(to_insert)} to insert, {len(to_update)} to update")

        created_count = 0
        updated_count = 0
        errors = []

        # Batch INSERT new contacts
        batch_size = 100
        for i in range(0, len(to_insert), batch_size):
            batch = to_insert[i:i + batch_size]
            try:
                self.client.table('customer_contacts').upsert(
                    batch, on_conflict="client_id,email_address"
                ).execute()
                created_count += len(batch)
                logger.debug(f"Inserted batch {i//batch_size + 1}: {len(batch)} contacts")
            except Exception as e:
                logger.error(f"Failed to insert batch {i//batch_size + 1}: {e}")
                errors.append({'batch': i//batch_size + 1, 'error': str(e)})

        # Batch UPDATE existing contacts using PostgreSQL function
        if len(to_update) > 0:
            try:
                # Prepare JSONB array for batch update
                update_payload = [
                    {
                        'email_address': contact['email_address'],
                        'client_id': str(self.client_id),
                        'customer_company_id': str(contact['customer_company_id']) if contact.get('customer_company_id') else None,
                        'first_name': contact.get('first_name'),
                        'last_name': contact.get('last_name'),
                        'full_name': contact.get('full_name'),
                        'contact_type': contact.get('contact_type', 'person')
                    }
                    for contact in to_update
                ]

                # Call PostgreSQL batch update function
                response = self.client.rpc('batch_update_contact_companies', {
                    'updates': update_payload
                }).execute()

                if response.data and len(response.data) > 0:
                    updated_count = response.data[0].get('updated_count', 0)
                    error_count = response.data[0].get('error_count', 0)

                    logger.info(f"Batch updated {updated_count} existing contacts, {error_count} errors")

                    if error_count > 0:
                        errors.append({'type': 'batch_update', 'error_count': error_count})
                else:
                    logger.warning("Batch update returned no data")
                    updated_count = 0

            except Exception as e:
                logger.error(f"Failed to batch update contacts: {e}")
                errors.append({'type': 'batch_update', 'error': str(e)})
                updated_count = 0
        else:
            logger.info("No existing contacts to update")
            updated_count = 0

        logger.info(f"Contact upsert complete: {created_count} created, {updated_count} updated, {len(errors)} errors")

        # ── Link orphan contacts to companies by domain ─────────────────
        orphan_linked = self._link_orphan_contacts()

        return {
            'total_contacts': len(contacts),
            'created': created_count,
            'updated': updated_count,
            'orphan_linked': orphan_linked,
            'errors': errors
        }

    def _link_orphan_contacts(self) -> int:
        """Link contacts with NULL customer_company_id to companies by email domain.

        Skips free email providers (gmail.com, yahoo.com, etc.) to prevent
        bulk-linking unrelated contacts to a single catch-all company.
        """
        try:
            # Load free email providers
            free_providers: set = set()
            try:
                resp = self.client.table('free_email_providers').select('domain').execute()
                free_providers = {r['domain'].lower() for r in (resp.data or [])}
            except Exception:
                pass

            # Build domain → company_id map from existing companies
            domain_to_company: dict = {}
            offset = 0
            while True:
                resp = self.client.table('customer_companies').select(
                    'id, email_domains'
                ).eq('client_id', self.client_id).range(offset, offset + 999).execute()
                rows = resp.data or []
                for c in rows:
                    for d in (c.get('email_domains') or []):
                        dl = d.lower()
                        if dl not in free_providers and dl not in domain_to_company:
                            domain_to_company[dl] = c['id']
                if len(rows) == 0:
                    break
                offset += len(rows)

            # Fetch orphan contacts (NULL company_id)
            orphans: list = []
            offset = 0
            while True:
                resp = self.client.table('customer_contacts').select(
                    'id, email_address'
                ).eq('client_id', self.client_id).is_(
                    'customer_company_id', 'null'
                ).range(offset, offset + 999).execute()
                rows = resp.data or []
                orphans.extend(rows)
                if len(rows) == 0:
                    break
                offset += len(rows)

            if not orphans:
                logger.info("No orphan contacts to link")
                return 0

            # Match orphans to companies by domain
            to_update: list = []
            skipped_free = 0
            no_match = 0
            for contact in orphans:
                email = (contact.get('email_address') or '').lower()
                if '@' not in email:
                    continue
                domain = email.split('@')[1]
                if domain in free_providers:
                    skipped_free += 1
                    continue
                company_id = domain_to_company.get(domain)
                if company_id:
                    to_update.append({'id': contact['id'], 'company_id': company_id})
                else:
                    no_match += 1

            linked = 0
            by_company: dict[str, list[str]] = {}
            for item in to_update:
                by_company.setdefault(item['company_id'], []).append(item['id'])

            for company_id, contact_ids in by_company.items():
                for i in range(0, len(contact_ids), 200):
                    chunk = contact_ids[i:i + 200]
                    try:
                        self._execute_with_retry(
                            self.client.table('customer_contacts')
                            .update({'customer_company_id': company_id})
                            .in_('id', chunk)
                        )
                        linked += len(chunk)
                    except Exception as e:
                        logger.warning(f"Orphan linking batch failed: {e}")

            logger.info(
                f"Orphan contact linking: {linked} linked by domain, "
                f"{skipped_free} skipped (free provider), {no_match} no company match, "
                f"{len(orphans)} total orphans scanned"
            )
            return linked

        except Exception as e:
            logger.warning(f"Orphan contact linking failed (non-fatal): {e}")
            return 0

    def _step_upsert_companies(self) -> Dict:
        """
        Step 6: Create/update customer_companies records

        Returns:
            Upsert results
        """
        companies = self.step_results[4]['companies']

        resolver = CompanyResolver(client_id=self.client_id)
        result = resolver.upsert_companies(companies)

        logger.info(f"Company upsert complete: {result['created']} created, {result['updated']} updated")

        # Sprint 3: QB re-match + enrichment (new companies/contacts may match QB records)
        qb_matched = self._rematch_quickbase()
        result['qb_new_matches'] = qb_matched
        qb_enriched = self._enrich_from_quickbase()
        result['qb_companies_enriched'] = qb_enriched.get('companies', 0)
        result['qb_contacts_enriched'] = qb_enriched.get('contacts', 0)

        return result

    def _refresh_email_counts(self):
        """Update email counts on contacts + companies from junction table.

        Calls the RPCs that recompute total_emails_sent/received on contacts
        and total_emails/inbound/outbound/first_contact/last_contact on companies.
        Runs after every extraction so counts stay current with CC/BCC data.
        """
        try:
            try:
                result = self.client.rpc('update_contact_email_counts_from_junction', {
                    'p_client_id': self.client_id,
                }).execute()
                logger.info(f"Contact email counts refreshed: {result.data}")
            except Exception as e:
                logger.warning(f"Contact count refresh failed (non-critical): {e}")

            try:
                result = self.client.rpc('update_company_email_counts_from_junction', {
                    'p_client_id': self.client_id,
                }).execute()
                logger.info(f"Company email counts refreshed: {result.data}")
            except Exception as e:
                logger.warning(f"Company count refresh failed (non-critical): {e}")

        except Exception as e:
            logger.warning(f"Email count refresh failed (non-critical): {e}")

    def _embed_new_emails(self):
        """Vectorize newly extracted emails that don't have embeddings yet.

        Runs at the end of the extraction pipeline so new emails are immediately
        searchable via semantic search. Non-blocking — failures don't affect the
        extraction result.

        Uses asyncio.run() which safely creates a new event loop in the current
        thread — works correctly from ThreadPoolExecutor threads (sync-to-async
        bridge) unlike get_event_loop().run_until_complete() which fails on
        Python 3.12+ in non-main threads.
        """
        try:
            import asyncio
            from .vector_service import VectorService
            vs = VectorService(self.client)
            # Limit to 500 per extraction run to avoid long-running embedding jobs
            result = asyncio.run(
                vs.embed_emails_batch(self.client_id, batch_size=200, limit=500)
            )
            embedded = result.get('embedded', 0)
            if embedded > 0:
                logger.info(f"Auto-embedded {embedded} new emails for client {self.client_id}")
        except Exception as e:
            logger.warning(f"Auto-embed emails failed (non-critical): {e}")

    def _auto_trigger_ai_analysis(self):
        """Auto-trigger AI email classification for unanalyzed emails.

        Runs at the end of the extraction pipeline so newly imported emails get
        intent/urgency/sentiment classification without manual user action.
        Non-blocking — failures don't affect the extraction result.

        Uses date_from="all" to analyze ALL unanalyzed emails (not just last 7 days),
        ensuring historical imports also get classified.
        """
        try:
            from .ai_email_analyzer import get_email_analyzer
            analyzer = get_email_analyzer()
            if not analyzer:
                logger.info("AI analyzer not initialized — skipping auto-analysis")
                return

            result = analyzer.analyze_all_unanalyzed(
                mailbox_id=self.mailbox_id,
                client_id=self.client_id,
                max_emails=5000,
                date_from="all",  # Analyze ALL unanalyzed, not just last 7 days
            )
            analyzed = result.get("total_analyzed", 0)
            failed = result.get("total_failed", 0)
            if analyzed > 0 or failed > 0:
                logger.info(
                    f"Auto AI analysis: {analyzed} classified, {failed} failed "
                    f"for mailbox {self.mailbox_id}"
                )

            # Auto-run bucket engine after analysis
            if analyzed > 0:
                from .ai_action_bucket_engine import get_bucket_engine
                bucket_engine = get_bucket_engine()
                if bucket_engine:
                    bucket_engine.process_email_buckets(self.mailbox_id)
                    logger.info("Auto bucket derivation complete")

        except Exception as e:
            logger.warning(f"Auto AI analysis failed (non-critical): {e}")

    def _assign_canonical_threads(self):
        """Assign canonical_thread_id to emails that don't have one yet.

        Lightweight — only processes new emails (canonical_thread_id IS NULL).
        Uses In-Reply-To / References headers to find existing canonical threads,
        or creates new ones via subject+participant matching.
        Runs in both full and lightweight extraction modes.
        """
        try:
            # Count emails without canonical_thread_id in this mailbox
            count_resp = self._execute_with_retry(
                self.client.table('emails').select('id', count='exact')
                .eq('mailbox_id', self.mailbox_id)
                .is_('canonical_thread_id', 'null')
                .not_.is_('thread_id', 'null')
            )
            unresolved = count_resp.count or 0

            if unresolved == 0:
                logger.info("All emails have canonical_thread_id — skipping")
                return

            logger.info(f"Assigning canonical_thread_id to {unresolved} new emails")

            from .canonical_thread_resolver import CanonicalThreadResolver
            resolver = CanonicalThreadResolver(
                client_id=self.client_id,
                mailbox_id=self.mailbox_id,
            )

            # Pre-seed the resolver's Message-ID index from existing resolved emails
            # so new emails can find their parent threads
            offset = 0
            while True:
                resp = self._execute_with_retry(
                    self.client.table('emails').select(
                        'internet_message_id, canonical_thread_id'
                    ).eq('mailbox_id', self.mailbox_id)
                    .not_.is_('canonical_thread_id', 'null')
                    .not_.is_('internet_message_id', 'null')
                    .range(offset, offset + 999)
                )
                rows = resp.data or []
                if not rows:
                    break
                for r in rows:
                    mid = (r.get('internet_message_id') or '').strip().strip('<>')
                    cid = r.get('canonical_thread_id')
                    if mid and mid != '__none__' and cid:
                        resolver._msg_id_to_canonical[mid] = cid
                offset += len(rows)

            logger.info(f"Pre-seeded Message-ID index with {len(resolver._msg_id_to_canonical)} entries")

            # Also seed from other mailboxes (cross-mailbox resolution)
            other_mb_resp = self.client.table('mailboxes').select('id').eq(
                'client_id', self.client_id
            ).neq('id', self.mailbox_id).execute()
            for mb in (other_mb_resp.data or []):
                mb_offset = 0
                while True:
                    resp = self._execute_with_retry(
                        self.client.table('emails').select(
                            'internet_message_id, canonical_thread_id'
                        ).eq('mailbox_id', mb['id'])
                        .not_.is_('canonical_thread_id', 'null')
                        .not_.is_('internet_message_id', 'null')
                        .range(mb_offset, mb_offset + 999)
                    )
                    rows = resp.data or []
                    if not rows:
                        break
                    for r in rows:
                        mid = (r.get('internet_message_id') or '').strip().strip('<>')
                        cid = r.get('canonical_thread_id')
                        if mid and mid != '__none__' and cid:
                            resolver._msg_id_to_canonical[mid] = cid
                    mb_offset += len(rows)

            logger.info(f"Cross-mailbox index: {len(resolver._msg_id_to_canonical)} total Message-IDs")

            # Now resolve only unresolved emails
            resolver.resolve_all()

            logger.info("Canonical thread assignment complete for new emails")

        except Exception as e:
            logger.warning(f"Canonical thread assignment failed (non-critical): {e}")

    def _update_affected_threads(self):
        """Incrementally update thread_status for threads that received new emails.

        Instead of recomputing all 70K+ threads, only re-evaluates threads where
        emails were recently added (based on extraction lookback window).
        Runs in both full and lightweight mode.
        """
        try:
            from .thread_tracker import ThreadTracker
            from datetime import timedelta

            # Find canonical_thread_ids of recently modified emails in this mailbox
            lookback = datetime.utcnow() - timedelta(days=max(self.lookback_days, 7))
            lookback_iso = lookback.isoformat() + 'Z'

            affected_threads: set = set()
            offset = 0
            while True:
                resp = self._execute_with_retry(
                    self.client.table('emails').select('canonical_thread_id')
                    .eq('mailbox_id', self.mailbox_id)
                    .not_.is_('canonical_thread_id', 'null')
                    .gte('sent_date', lookback_iso)
                    .range(offset, offset + 999)
                )
                rows = resp.data or []
                if not rows:
                    break
                for r in rows:
                    cid = r.get('canonical_thread_id')
                    if cid:
                        affected_threads.add(cid)
                offset += len(rows)

            if not affected_threads:
                logger.info("No affected threads to update")
                return

            logger.info(f"Updating {len(affected_threads)} affected threads")

            # Fetch all emails for these threads (across all mailboxes)
            threads: dict = {}
            thread_list = list(affected_threads)

            for i in range(0, len(thread_list), 50):
                batch_tids = thread_list[i:i + 50]
                offset = 0
                while True:
                    resp = self._execute_with_retry(
                        self.client.table('emails').select(
                            'id, canonical_thread_id, subject, sent_date, is_outbound, '
                            'customer_contact_id, customer_company_id'
                        ).in_('canonical_thread_id', batch_tids)
                        .order('sent_date', desc=False)
                        .range(offset, offset + 999)
                    )
                    rows = resp.data or []
                    if not rows:
                        break
                    for e in rows:
                        tid = e.get('canonical_thread_id')
                        if tid:
                            if tid not in threads:
                                threads[tid] = []
                            threads[tid].append(e)
                    offset += len(rows)

            if not threads:
                return

            # Evaluate and save using the thread tracker (reuses junction cache if loaded)
            tracker = ThreadTracker(client_id=self.client_id)
            tracker._junction_cache = {}  # Skip junction preload for incremental
            # Use email FK fallback since we're not preloading full cache

            # Targeted intent preload — only for emails actually being evaluated.
            # WHY: previously the incremental path didn't load AI intent at all,
            # so override rules (urgent / closing / etc.) never fired during
            # in-pipeline thread eval. Loading targeted intent here means
            # threads get effective_status correctly when AI data is available.
            all_email_ids = [e['id'] for emails in threads.values() for e in emails]
            tracker._preload_intent_for_emails(all_email_ids)

            statuses = []
            for tid, emails in threads.items():
                emails.sort(key=lambda e: e.get('sent_date', ''))
                if len(emails) > 200:
                    continue
                status = tracker._evaluate_thread_status(tid, emails)
                statuses.append(status)

            if statuses:
                result = tracker.save_thread_statuses(statuses)
                logger.info(f"Updated {result.get('created_count', 0)} thread statuses (incremental)")

        except Exception as e:
            logger.warning(f"Incremental thread update failed (non-critical): {e}")

    def _rematch_quickbase(self) -> int:
        """QB email-based matching after extraction.

        Uses qb_unique_emails to link SB companies to QB customers, then matches
        contacts by name against QB contacts for the linked customer. Finally
        propagates QB enrichment data.

        Flow:
        1. Contact email → qb_unique_emails → qb_customer_id → link SB company
        2. Contact name → qb_contacts (filtered by qb_customer_id) → link SB contact
        3. Propagate QB data to enrichment columns
        """
        try:
            # Check if QB is configured
            qb_config_resp = self.client.table('qb_sync_config').select('*').eq(
                'client_id', self.client_id
            ).execute()
            if not qb_config_resp.data or not qb_config_resp.data[0].get('is_active'):
                return 0

            matched = 0
            now_iso = datetime.utcnow().isoformat() + 'Z'

            # ── Step 1: Build email → qb_customer_id lookup from qb_unique_emails ──
            email_to_qb: dict = {}  # email → {qb_customer_id, customer_name}
            offset = 0
            while True:
                ue_resp = self._execute_with_retry(
                    self.client.table('qb_unique_emails').select(
                        'email, qb_customer_id, customer_name'
                    ).eq('client_id', self.client_id).eq(
                        'hide', False
                    ).eq(
                        'email_invalid', False
                    ).not_.is_(
                        'qb_customer_id', 'null'
                    ).range(offset, offset + 999)
                )
                rows = ue_resp.data or []
                for r in rows:
                    email = (r.get('email') or '').strip().lower()
                    if email:
                        email_to_qb[email] = {
                            'qb_customer_id': str(r['qb_customer_id']).strip(),
                            'customer_name': r.get('customer_name'),
                        }
                if len(rows) == 0:
                    break
                offset += len(rows)

            if not email_to_qb:
                logger.info("Step 6 QB email match: No unique emails available — skipping")
                return 0
            logger.info(f"Step 6 QB email match: {len(email_to_qb)} unique emails loaded")

            # ── Step 2: Build qb_record_id → qb_customers row lookup ──
            qb_cust_map: dict = {}  # qb_record_id → {id, customer_code}
            offset = 0
            while True:
                cust_resp = self._execute_with_retry(
                    self.client.table('qb_customers').select(
                        'id, qb_record_id, customer_code'
                    ).eq('client_id', self.client_id).range(offset, offset + 999)
                )
                rows = cust_resp.data or []
                for r in rows:
                    if r.get('qb_record_id'):
                        qb_cust_map[str(r['qb_record_id'])] = r
                if len(rows) == 0:
                    break
                offset += len(rows)

            # ── Step 3: Get contacts touched in this extraction with company links ──
            contacts_with_companies: list = []
            offset = 0
            while True:
                ct_resp = self._execute_with_retry(
                    self.client.table('customer_contacts').select(
                        'id, email_address, customer_company_id, full_name, first_name, last_name'
                    ).eq('client_id', self.client_id).not_.is_(
                        'customer_company_id', 'null'
                    ).range(offset, offset + 999)
                )
                rows = ct_resp.data or []
                contacts_with_companies.extend(rows)
                if len(rows) == 0:
                    break
                offset += len(rows)

            # ── Step 3b: Load internal domains to exclude from matching ──
            internal_domains: set[str] = set()
            try:
                id_resp = self._execute_with_retry(
                    self.client.table('internal_domains').select('domain').eq('client_id', self.client_id)
                )
                internal_domains = {(r['domain'] or '').strip().lower() for r in (id_resp.data or [])}
                if internal_domains:
                    logger.info(f"Step 6 QB email match: excluding internal domains: {internal_domains}")
            except Exception as e:
                logger.warning(f"Step 6: could not load internal_domains: {e}")

            # ── Step 4: Match companies via email lookup ──
            # company_id → {qb_customer_id: count} (majority vote for conflicts)
            company_votes: dict = {}
            for ct in contacts_with_companies:
                email = (ct.get('email_address') or '').strip().lower()
                company_id = ct.get('customer_company_id')
                if not email or not company_id:
                    continue
                if email.split('@')[-1] in internal_domains:
                    continue
                qb_info = email_to_qb.get(email)
                if not qb_info:
                    continue
                qb_cid = qb_info['qb_customer_id']
                if company_id not in company_votes:
                    company_votes[company_id] = {}
                company_votes[company_id][qb_cid] = company_votes[company_id].get(qb_cid, 0) + 1

            # Resolve: pick QB customer with most votes per company
            company_to_qb: dict = {}  # company_id → qb_customer_id
            for company_id, votes in company_votes.items():
                best = max(votes, key=votes.get)
                company_to_qb[company_id] = best

            logger.info(f"Step 6 QB email match: {len(company_to_qb)} companies resolved from email lookup")

            # ── Step 5: Write company matches (only for unlinked companies) ──
            for company_id, qb_customer_id in company_to_qb.items():
                try:
                    normalized_id = str(int(float(qb_customer_id)))
                except (ValueError, TypeError):
                    normalized_id = str(qb_customer_id)

                qb_cust = qb_cust_map.get(normalized_id)
                if not qb_cust:
                    continue

                for write_attempt in range(3):
                    try:
                        # Link qb_customers → company
                        self._execute_with_retry(
                            self.client.table('qb_customers').update({
                                'matched_company_id': company_id
                            }).eq('id', qb_cust['id'])
                        )
                        # Write match metadata on company
                        self._execute_with_retry(
                            self.client.table('customer_companies').update({
                                'qb_customer_id': qb_cust.get('qb_record_id'),
                                'qb_customer_code': qb_cust.get('customer_code'),
                                'qb_match_method': 'email_lookup',
                                'qb_matched_at': now_iso,
                            }).eq('id', company_id)
                        )
                        matched += 1
                        break
                    except OSError as e:
                        # Socket exhaustion (errno 11) — back off and retry
                        if write_attempt < 2:
                            time.sleep(2 * (write_attempt + 1))
                            logger.info(f"Step 6 socket pressure, retrying company {company_id} (attempt {write_attempt + 2}/3)")
                        else:
                            logger.warning(f"Step 6 QB match write failed for company {company_id} after 3 attempts: {e}")
                    except Exception as e:
                        logger.warning(f"Step 6 QB match write failed for company {company_id}: {e}")
                        break

            # ── Step 6: Match contacts by name against QB contacts ──
            # For each matched company, find its QB contacts and match by name
            contacts_matched = 0
            if company_to_qb:
                # Build qb_customer_id → list of QB contacts
                qb_contacts_by_customer: dict = {}
                offset = 0
                while True:
                    qbc_resp = self._execute_with_retry(
                        self.client.table('qb_contacts').select(
                            'id, qb_customer_id, first_name, surname, email'
                        ).eq('client_id', self.client_id).is_(
                            'matched_contact_id', 'null'
                        ).range(offset, offset + 999)
                    )
                    rows = qbc_resp.data or []
                    for r in rows:
                        cid = str(r.get('qb_customer_id') or '').strip()
                        if cid:
                            if cid not in qb_contacts_by_customer:
                                qb_contacts_by_customer[cid] = []
                            qb_contacts_by_customer[cid].append(r)
                    if len(rows) == 0:
                        break
                    offset += len(rows)

                # For SB contacts in matched companies, try name-based match to QB contacts
                for ct in contacts_with_companies:
                    company_id = ct.get('customer_company_id')
                    qb_customer_id = company_to_qb.get(company_id)
                    if not qb_customer_id:
                        continue

                    try:
                        normalized_qb_cid = str(int(float(qb_customer_id)))
                    except (ValueError, TypeError):
                        normalized_qb_cid = str(qb_customer_id)

                    qb_contacts_for_cust = qb_contacts_by_customer.get(normalized_qb_cid, [])
                    if not qb_contacts_for_cust:
                        continue

                    # Match by name (first+last or full_name)
                    sb_first = (ct.get('first_name') or '').strip().lower()
                    sb_last = (ct.get('last_name') or '').strip().lower()
                    sb_full = (ct.get('full_name') or '').strip().lower()

                    best_match = None
                    for qbc in qb_contacts_for_cust:
                        qb_first = (qbc.get('first_name') or '').strip().lower()
                        qb_last = (qbc.get('surname') or '').strip().lower()
                        # Exact first+last match
                        if sb_first and sb_last and qb_first == sb_first and qb_last == sb_last:
                            best_match = qbc
                            break
                        # Email match as fallback
                        qb_email = (qbc.get('email') or '').strip().lower()
                        sb_email = (ct.get('email_address') or '').strip().lower()
                        if qb_email and sb_email and qb_email == sb_email:
                            best_match = qbc
                            break

                    if best_match:
                        try:
                            self._execute_with_retry(
                                self.client.table('qb_contacts').update({
                                    'matched_contact_id': ct['id']
                                }).eq('id', best_match['id'])
                            )
                            contacts_matched += 1
                        except Exception:
                            pass

            logger.info(
                f"Step 6 QB email match complete: {matched} companies linked, "
                f"{contacts_matched} contacts matched by name"
            )

            # ── Step 7: Propagate QB data to enrichment columns ──
            try:
                import asyncio
                from .quickbase_sync import QuickbaseSync
                syncer = QuickbaseSync(self.client, qb_config_resp.data[0])

                async def _propagate_both():
                    await syncer.backfill_contacts_after_match()
                    companies = await syncer.propagate_qb_data_to_companies()
                    contacts = await syncer.propagate_qb_data_to_contacts()
                    return companies, contacts

                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                            future = pool.submit(lambda: asyncio.run(_propagate_both()))
                            propagated, propagated_contacts = future.result(timeout=180)
                    else:
                        propagated, propagated_contacts = loop.run_until_complete(_propagate_both())
                except RuntimeError:
                    propagated, propagated_contacts = asyncio.run(_propagate_both())
                if propagated > 0 or propagated_contacts > 0:
                    logger.info(
                        f"Step 6 QB propagation: refreshed {propagated} companies, "
                        f"{propagated_contacts} contact rows"
                    )
            except Exception as e:
                logger.warning(f"Step 6 QB propagation failed (non-critical): {e}")

            return matched
        except Exception as e:
            logger.warning(f"Step 6 QB email match failed (non-critical): {e}")
            return 0

    def _enrich_from_quickbase(self) -> Dict:
        """
        Sprint 3 sub-step: Enrich companies and contacts with Quickbase data.

        Uses SQL UPDATE...FROM joins instead of per-row HTTP calls.
        """
        result = {'companies': 0, 'contacts': 0}

        try:
            qb_config = self.client.table('qb_sync_config').select(
                'is_active'
            ).eq('client_id', self.client_id).execute()

            if not qb_config.data or not qb_config.data[0].get('is_active'):
                logger.info("Step 6 QB enrichment: No active QB config — skipping")
                return result

            companies_sql = f"""
                UPDATE customer_companies cc SET
                    qb_customer_type = COALESCE(qc.customer_status, cc.qb_customer_type),
                    qb_tier = COALESCE(qc.customer_tier, cc.qb_tier),
                    qb_account_manager = COALESCE(qc.account_manager, cc.qb_account_manager),
                    qb_total_revenue = COALESCE(qc.total_invoiced, cc.qb_total_revenue),
                    qb_invoiced_ty = COALESCE(qc.invoiced_ty, cc.qb_invoiced_ty),
                    qb_invoiced_ly = COALESCE(qc.invoiced_ly, cc.qb_invoiced_ly),
                    qb_growth_90d = COALESCE(qc.growth_90d, cc.qb_growth_90d),
                    qb_days_since_last_invoice = COALESCE(qc.days_since_last_invoice, cc.qb_days_since_last_invoice)
                FROM qb_customers qc
                WHERE qc.matched_company_id = cc.id
                  AND qc.client_id = '{self.client_id}';
            """
            resp = self.client.rpc("exec_sql", {"query": companies_sql}).execute()
            raw = (resp.data or '') if isinstance(resp.data, str) else str(resp.data)
            import re
            m = re.search(r'(\d+)', raw)
            result['companies'] = int(m.group(1)) if m else 0

            contacts_sql = f"""
                UPDATE customer_contacts cc SET
                    qb_quotes_count = COALESCE(qc.quotes_accepted_count, cc.qb_quotes_count),
                    qb_last_quote_date = COALESCE(qc.most_recent_quote_date, cc.qb_last_quote_date),
                    qb_contact_recency_days = COALESCE(qc.contact_recency_days, cc.qb_contact_recency_days)
                FROM qb_contacts qc
                WHERE qc.matched_contact_id = cc.id
                  AND qc.client_id = '{self.client_id}';
            """
            resp = self.client.rpc("exec_sql", {"query": contacts_sql}).execute()
            raw = (resp.data or '') if isinstance(resp.data, str) else str(resp.data)
            m = re.search(r'(\d+)', raw)
            result['contacts'] = int(m.group(1)) if m else 0

            logger.info(
                f"Step 6 QB enrichment: {result['companies']} companies, "
                f"{result['contacts']} contacts enriched from Quickbase"
            )

        except Exception as e:
            logger.warning(f"Step 6 QB enrichment failed (non-critical): {e}")

        return result

    def _step_classify_roles(self) -> Dict:
        """
        Step 7: Classify roles from email signatures

        Returns:
            Role classification results
        """
        contacts = self.step_results[2]['contacts']

        classifier = RoleClassifier(mailbox_id=self.mailbox_id, client_id=self.client_id)

        roles = classifier.classify_roles(contacts, extract_from_signatures=True)

        summary = classifier.get_role_summary(roles)

        logger.info(f"Classified {len(roles)} contact roles")

        return {
            'roles': roles,
            'summary': summary,
            'total_roles': len(roles)
        }

    def _step_update_roles(self) -> Dict:
        """
        Step 8: Update role information in customer_contacts using batch operations

        Returns:
            Update results
        """
        roles = self.step_results[7]['roles']

        classifier = RoleClassifier(mailbox_id=self.mailbox_id, client_id=self.client_id)
        # Use batch update function for performance
        result = classifier.update_contact_roles(roles)

        logger.info(f"Role update complete: {result['updated']} contacts updated, "
                   f"{result['with_titles']} with titles, {result['decision_makers']} decision makers")

        return result

    def _step_link_emails(self, force_relink: bool) -> Dict:
        """
        Step 9: Link emails to contacts/companies

        Returns:
            Linking results
        """
        linker = EmailLinker(mailbox_id=self.mailbox_id, client_id=self.client_id)

        # In incremental mode, only link scoped emails
        scoped_ids = None
        if self.extraction_mode != 'full':
            email_ids, _, _ = self._get_emails_in_scope()
            if email_ids:
                scoped_ids = email_ids

        result = linker.link_emails(email_ids=scoped_ids, force_relink=force_relink)

        logger.info(f"Email linking complete: {result['linked']} emails linked")

        # Get updated stats
        stats = linker.get_linking_stats()
        result['stats'] = stats

        return result

    def _step_calculate_engagement(self) -> Dict:
        """
        Step 10: Calculate engagement analytics (Phase 4)

        Runs 4 analytics services:
        1. Response time tracker
        2. Thread tracker
        3. Communication pattern analyzer
        4. Engagement scorer

        Returns:
            Engagement calculation results
        """
        logger.info("=" * 80)
        logger.info("Step 10: Calculating engagement analytics (4 services)")
        logger.info("=" * 80)

        try:
            from .response_time_tracker import ResponseTimeTracker
            from .thread_tracker import ThreadTracker
            from .comm_pattern_analyzer import CommunicationPatternAnalyzer
            from .engagement_scorer import EngagementScorer

            # Sub-step 10.1: Calculate response times
            logger.info("\n[10.1] Calculating response times...")
            response_tracker = ResponseTimeTracker(
                mailbox_id=self.mailbox_id,
                client_id=self.client_id
            )
            response_metrics = response_tracker.calculate_response_times()
            response_tracker.save_metrics(response_metrics)
            response_tracker.update_contact_averages()
            logger.info(f"✅ Response times calculated: {len(response_metrics)} pairs")

            # Sub-step 10.2: Evaluate thread status
            logger.info("\n[10.2] Evaluating thread status...")
            thread_tracker = ThreadTracker(
                mailbox_id=self.mailbox_id,
                client_id=self.client_id
            )
            thread_statuses = thread_tracker.evaluate_threads()
            thread_tracker.save_thread_statuses(thread_statuses)
            thread_counts = thread_tracker.update_thread_counts()
            logger.info(f"✅ Thread status evaluated: {len(thread_statuses)} threads")

            # Sub-step 10.3: Analyze communication patterns
            logger.info("\n[10.3] Analyzing communication patterns...")
            pattern_analyzer = CommunicationPatternAnalyzer(
                mailbox_id=self.mailbox_id,
                client_id=self.client_id
            )
            patterns = pattern_analyzer.analyze_patterns()
            pattern_results = pattern_analyzer.save_patterns(patterns)
            logger.info(f"✅ Patterns analyzed: {len(patterns)} contacts")

            # Sub-step 10.4: Calculate engagement scores
            logger.info("\n[10.4] Calculating engagement scores...")
            scorer = EngagementScorer(client_id=self.client_id)
            contact_scores = scorer.score_contacts()
            company_scores = scorer.score_companies()
            score_results = scorer.save_scores(contact_scores, company_scores)
            logger.info(f"✅ Engagement scores calculated: {len(contact_scores)} contacts, {len(company_scores)} companies")

            logger.info("\n" + "=" * 80)
            logger.info("Step 10 complete: Engagement analytics calculated")
            logger.info("=" * 80)

            return {
                'status': 'success',
                'response_pairs': len(response_metrics),
                'threads_evaluated': len(thread_statuses),
                'patterns_analyzed': len(patterns),
                'contacts_scored': len(contact_scores),
                'companies_scored': len(company_scores),
                'contacts_updated': score_results['contacts_updated'],
                'companies_updated': score_results['companies_updated']
            }

        except Exception as e:
            logger.error(f"Failed to calculate engagement analytics: {e}")
            logger.error(traceback.format_exc())
            return {'status': 'failed', 'error': str(e)}

    def _step_update_company_stats(self) -> Dict:
        """
        Step 11: Update company statistics (batch mode)

        Computes per-company:
          - contact_count (from customer_contacts)
          - total_emails, total_inbound, total_outbound (from emails via contact chain)

        Returns:
            Update results
        """
        logger.info("Updating company statistics (batch mode)")

        try:
            from collections import Counter, defaultdict

            # ── 1. Fetch ALL companies for this client (paginated) ──────────
            company_ids: list = []
            offset = 0
            while True:
                co_page = self.client.table('customer_companies').select(
                    'id'
                ).eq('client_id', self.client_id).range(offset, offset + 999).execute()
                rows = co_page.data or []
                company_ids.extend(c['id'] for c in rows)
                if len(rows) == 0:
                    break
                offset += len(rows)
            logger.info(f"Found {len(company_ids)} companies to update")

            if not company_ids:
                return {'companies_updated': 0}

            # ── 2. Fetch all contacts → build contact_id → company_id map ────
            all_contacts: list = []
            offset = 0
            while True:
                contacts_page = (
                    self.client.table('customer_contacts')
                    .select('id, customer_company_id')
                    .eq('client_id', self.client_id)
                    .not_.is_('customer_company_id', 'null')
                    .range(offset, offset + 999)
                    .execute()
                )
                rows = contacts_page.data or []
                all_contacts.extend(rows)
                if len(rows) == 0:
                    break
                offset += len(rows)

            contact_to_company: dict = {}
            company_contact_counts = Counter()
            for contact in all_contacts:
                cid = contact.get('customer_company_id')
                if cid:
                    contact_to_company[contact['id']] = cid
                    company_contact_counts[cid] += 1

            logger.info(f"Mapped {len(contact_to_company)} contacts to {len(company_contact_counts)} companies")

            # ── 3. Count emails per company via email_contact_links (includes CC/BCC) ──
            # Try junction table first; fall back to old contact chain if table doesn't exist
            company_email_stats: dict = defaultdict(lambda: {'total': 0, 'inbound': 0, 'outbound': 0})
            emails_scanned = 0
            use_junction = True

            try:
                # Check if junction table has data for this client
                check = self.client.table('email_contact_links').select(
                    'id', count='exact'
                ).eq('client_id', self.client_id).limit(0).execute()
                use_junction = (check.count or 0) > 0
            except Exception:
                use_junction = False

            if use_junction:
                logger.info("Counting emails per company via email_contact_links (includes CC/BCC)")
                # Get distinct (email_id, company_id) pairs from junction table
                # Then join with emails for is_outbound
                offset = 0
                while True:
                    ecl_page = self._execute_with_retry(
                        self.client.table('email_contact_links')
                        .select('email_id, company_id')
                        .eq('client_id', self.client_id)
                        .not_.is_('company_id', 'null')
                        .range(offset, offset + 999)
                    )
                    rows = ecl_page.data or []
                    if not rows:
                        break

                    # Collect email IDs for this batch to look up is_outbound
                    email_ids = list({r['email_id'] for r in rows})
                    outbound_set = set()
                    for i in range(0, len(email_ids), 500):
                        batch = email_ids[i:i + 500]
                        ob_resp = self._execute_with_retry(
                            self.client.table('emails')
                            .select('id, is_outbound')
                            .in_('id', batch)
                        )
                        for e in (ob_resp.data or []):
                            if e.get('is_outbound'):
                                outbound_set.add(e['id'])

                    # Count per company (deduplicate email_id per company)
                    seen = set()
                    for r in rows:
                        key = (r['email_id'], r['company_id'])
                        if key in seen:
                            continue
                        seen.add(key)
                        cid = r['company_id']
                        company_email_stats[cid]['total'] += 1
                        if r['email_id'] in outbound_set:
                            company_email_stats[cid]['outbound'] += 1
                        else:
                            company_email_stats[cid]['inbound'] += 1

                    emails_scanned += len(rows)
                    offset += len(rows)
                    if emails_scanned % 10000 == 0:
                        logger.info(f"Junction scan progress: {emails_scanned} links, {len(company_email_stats)} companies")
            else:
                logger.info("Counting emails per company via contact chain (junction table empty)")
                offset = 0
                while True:
                    emails_page = (
                        self.client.table('emails')
                        .select('customer_contact_id, is_outbound')
                        .eq('mailbox_id', self.mailbox_id)
                        .not_.is_('customer_contact_id', 'null')
                        .range(offset, offset + 999)
                        .execute()
                    )
                    rows = emails_page.data or []
                    if not rows:
                        break

                    for email in rows:
                        contact_id = email.get('customer_contact_id')
                        company_id = contact_to_company.get(contact_id)
                        if company_id:
                            company_email_stats[company_id]['total'] += 1
                            if email.get('is_outbound'):
                                company_email_stats[company_id]['outbound'] += 1
                            else:
                                company_email_stats[company_id]['inbound'] += 1

                    emails_scanned += len(rows)
                    offset += len(rows)
                    if emails_scanned % 5000 == 0:
                        logger.info(f"Email scan progress: {emails_scanned} scanned, {len(company_email_stats)} companies")

            logger.info(f"Scanned {emails_scanned} entries → email stats for {len(company_email_stats)} companies")

            # ── 4. Batch update companies via SQL ────────────────────────────
            timestamp = datetime.utcnow().isoformat()
            values_rows = []
            for cid in company_ids:
                contact_count = company_contact_counts.get(cid, 0)
                stats = company_email_stats.get(cid)
                if contact_count > 0 or stats:
                    total = stats['total'] if stats else 0
                    inbound = stats['inbound'] if stats else 0
                    outbound = stats['outbound'] if stats else 0
                    values_rows.append(
                        f"('{cid}'::uuid, {contact_count}, {total}, {inbound}, {outbound})"
                    )

            updated_count = 0
            CHUNK_SIZE = 500
            for i in range(0, len(values_rows), CHUNK_SIZE):
                chunk = values_rows[i:i + CHUNK_SIZE]
                values_sql = ", ".join(chunk)
                sql = f"""
                    UPDATE customer_companies cc SET
                        contact_count = v.contact_count,
                        total_emails = v.total_emails,
                        total_inbound = v.total_inbound,
                        total_outbound = v.total_outbound,
                        updated_at = '{timestamp}'::timestamptz
                    FROM (VALUES {values_sql})
                        AS v(id, contact_count, total_emails, total_inbound, total_outbound)
                    WHERE cc.id = v.id;
                """
                try:
                    self.client.rpc("exec_sql", {"query": sql}).execute()
                    updated_count += len(chunk)
                except Exception as e:
                    logger.error(f"Batch company stats update failed: {e}")

            logger.info(f"Updated statistics for {updated_count} companies")

            return {
                'companies_updated': updated_count,
                'emails_scanned': emails_scanned,
                'companies_with_emails': len(company_email_stats),
            }

        except Exception as e:
            logger.error(f"Failed to update company stats: {e}")
            return {'status': 'failed', 'error': str(e)}

    def _step_generate_report(self) -> Dict:
        """
        Step 12: Generate extraction report

        Returns:
            Report summary
        """
        logger.info("Generating extraction report")

        # Compile summary from all steps
        report = {
            'job_id': self.job_id,
            'mailbox_id': self.mailbox_id,
            'client_id': self.client_id,
            'completed_at': datetime.utcnow().isoformat(),
            'steps_completed': self.current_step,
            'summary': {
                'emails_processed': self.step_results[1]['emails_in_scope'],
                'contacts_extracted': self.step_results[2]['total_contacts'],
                'contacts_created': self.step_results[5]['created'],
                'contacts_updated': self.step_results[5]['updated'],
                'companies_resolved': self.step_results[4]['total_companies'],
                'companies_created': self.step_results[6]['created'],
                'companies_updated': self.step_results[6]['updated'],
                'emails_linked': self.step_results[9]['linked'],
                'link_rate': self.step_results[9].get('stats', {}).get('contact_link_rate', 0),
            }
        }

        # Add role classification if not skipped
        if 7 in self.step_results:
            report['summary']['roles_classified'] = self.step_results[7]['total_roles']
            report['summary']['decision_makers'] = self.step_results[7]['summary']['decision_makers']

        # Add engagement analytics if calculated
        if 10 in self.step_results and self.step_results[10].get('status') == 'success':
            report['summary']['analytics'] = {
                'response_pairs': self.step_results[10]['response_pairs'],
                'threads_evaluated': self.step_results[10]['threads_evaluated'],
                'patterns_analyzed': self.step_results[10]['patterns_analyzed'],
                'contacts_scored': self.step_results[10]['contacts_scored'],
                'companies_scored': self.step_results[10]['companies_scored']
            }

        logger.info("Extraction report:")
        for key, value in report['summary'].items():
            logger.info(f"  {key}: {value}")

        return report

    def _step_complete_job(self) -> Dict:
        """
        Step 13: Complete extraction job

        Returns:
            Completion status
        """
        logger.info("Finalizing extraction job")

        # Update job status to completed
        self._update_job_status('completed')

        # Update mailbox last_extraction_at timestamp
        try:
            self.client.table('mailboxes').update({
                'last_extraction_at': datetime.utcnow().isoformat()
            }).eq('id', self.mailbox_id).execute()
            logger.info(f"Updated mailbox last_extraction_at timestamp")
        except Exception as e:
            logger.warning(f"Failed to update mailbox last_extraction_at: {e}")

        logger.info(f"Extraction job {self.job_id} completed successfully")

        return {
            'status': 'completed',
            'job_id': self.job_id
        }


# Example usage
if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m backend.src.services.extraction_orchestrator <mailbox_id> [--skip-roles] [--force-relink]")
        sys.exit(1)

    mailbox_id = sys.argv[1]
    skip_roles = '--skip-roles' in sys.argv
    force_relink = '--force-relink' in sys.argv

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Run extraction
    orchestrator = ExtractionOrchestrator(mailbox_id=mailbox_id)

    result = orchestrator.run_extraction(
        exclude_mailing_lists=True,
        exclude_noreply=True,
        exclude_shared=True,
        exclude_internal=True,
        force_relink=force_relink,
        skip_role_classification=skip_roles
    )

    # Print results
    print("\n" + "=" * 80)
    print("EXTRACTION PIPELINE RESULTS")
    print("=" * 80)

    if result['success']:
        print(f"✓ SUCCESS - Completed in {result['duration_seconds']:.2f}s")
        print(f"\nJob ID: {result['job_id']}")

        if 12 in result['results']:
            report = result['results'][12]
            print("\nSummary:")
            for key, value in report['summary'].items():
                print(f"  {key}: {value}")
    else:
        print(f"✗ FAILED at step {result['failed_at_step']}")
        print(f"Error: {result['error']}")
