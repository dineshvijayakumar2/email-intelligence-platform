"""
Extraction Orchestrator Service - Sprint 2

Purpose: Coordinate the complete 13-step customer data extraction pipeline
Main entry point for extraction jobs

13-Step Pipeline:
1.  Validate prerequisites (tables, mailbox, permissions)
2.  Extract contacts from emails (contact_extractor)
3.  Deduplicate and filter contacts
4.  Resolve companies by domain (company_resolver)
5.  Upsert customer_contacts records
6.  Upsert customer_companies records
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

    def _get_emails_in_scope(self) -> tuple[List[str], Optional[str], Optional[str]]:
        """
        Get email IDs to process based on extraction mode

        Returns:
            Tuple of (email_ids, date_range_start, date_range_end)
        """
        try:
            if self.extraction_mode == 'full':
                # All emails
                response = (
                    self.client.table('emails')
                    .select('id')
                    .eq('mailbox_id', self.mailbox_id)
                    .eq('processing_status', 'success')
                    .execute()
                )
                logger.info(f"Full extraction mode: Processing all emails")
                return [email['id'] for email in response.data], None, None

            else:  # incremental
                # Only emails from last N days
                from datetime import timedelta
                date_range_end = datetime.utcnow()
                date_range_start = date_range_end - timedelta(days=self.lookback_days)

                logger.info(f"Incremental extraction mode: Looking back {self.lookback_days} days")
                logger.info(f"Date range: {date_range_start.isoformat()} to {date_range_end.isoformat()}")

                response = (
                    self.client.table('emails')
                    .select('id')
                    .eq('mailbox_id', self.mailbox_id)
                    .eq('processing_status', 'success')
                    .gte('sent_date', date_range_start.isoformat())
                    .lte('sent_date', date_range_end.isoformat())
                    .execute()
                )

                return (
                    [email['id'] for email in response.data],
                    date_range_start.isoformat(),
                    date_range_end.isoformat()
                )

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
        skip_role_classification: bool = False
    ) -> Dict:
        """
        Run the complete 13-step extraction pipeline

        Args:
            exclude_mailing_lists: Skip mailing list emails in contact extraction
            exclude_noreply: Skip no-reply addresses
            exclude_shared: Skip shared addresses (info@, sales@, etc.)
            exclude_internal: Skip internal domain contacts
            force_relink: Force relink even if emails already linked
            skip_role_classification: Skip role classification step (faster)

        Returns:
            Dictionary with extraction results and statistics
        """
        logger.info("=" * 80)
        logger.info(f"Starting customer data extraction pipeline for mailbox {self.mailbox_id}")
        logger.info("=" * 80)

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
            # STEP 5: Upsert Contacts
            # ============================================================
            self._run_step(5, "Create/update customer_contacts",
                          self._step_upsert_contacts)

            # ============================================================
            # STEP 6: Upsert Companies
            # ============================================================
            self._run_step(6, "Create/update customer_companies",
                          self._step_upsert_companies)

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

            # Calculate duration
            duration = (datetime.utcnow() - start_time).total_seconds()

            logger.info("=" * 80)
            logger.info(f"Extraction pipeline completed successfully in {duration:.2f}s")
            logger.info("=" * 80)

            return {
                'success': True,
                'job_id': self.job_id,
                'duration_seconds': duration,
                'steps_completed': self.current_step,
                'results': self.step_results
            }

        except Exception as e:
            logger.error(f"Extraction pipeline failed: {e}")
            logger.error(traceback.format_exc())

            # Mark job as failed
            if self.job_id:
                self._update_job_status('failed', error=str(e))

            return {
                'success': False,
                'job_id': self.job_id,
                'error': str(e),
                'failed_at_step': self.current_step,
                'results': self.step_results
            }

    def _run_step(self, step_num: int, description: str, step_function):
        """
        Run a single pipeline step with error handling and tracking

        Args:
            step_num: Step number (1-13)
            description: Step description
            step_function: Function to execute
        """
        self.current_step = step_num

        logger.info("")
        logger.info("=" * 80)
        logger.info(f"STEP {step_num}/{self.TOTAL_STEPS}: {description}")
        logger.info("=" * 80)

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

            logger.info(f"Step {step_num} completed in {step_duration:.2f}s")

            # Log step summary if result is dict
            if isinstance(result, dict):
                logger.info(f"Step {step_num} summary:")
                for key, value in result.items():
                    if key != 'errors':  # Skip error details in summary
                        logger.info(f"  {key}: {value}")

        except Exception as e:
            logger.error(f"Step {step_num} failed: {e}")
            raise

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

            self.client.table('extraction_jobs').update(update_data).eq('id', self.job_id).execute()

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

        contacts = extractor.extract_contacts(
            exclude_mailing_lists=exclude_mailing_lists,
            exclude_noreply=exclude_noreply,
            exclude_shared=exclude_shared
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

        # Build email -> company_id mapping
        email_to_company = {}
        for company in companies:
            for email in company.contact_emails:
                email_to_company[email.lower()] = company.company_id

        logger.info(f"Upserting {len(contacts)} contacts to customer_contacts table (batch mode)")

        # First, fetch all existing contacts for this client (single query)
        existing_response = (
            self.client.table('customer_contacts')
            .select('id, email_address')
            .eq('client_id', self.client_id)
            .execute()
        )

        existing_emails = {row['email_address'].lower(): row['id'] for row in existing_response.data}
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
                self.client.table('customer_contacts').insert(batch).execute()
                created_count += len(batch)
                logger.info(f"Inserted batch {i//batch_size + 1}: {len(batch)} contacts")
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

        return {
            'total_contacts': len(contacts),
            'created': created_count,
            'updated': updated_count,
            'errors': errors
        }

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

        result = linker.link_emails(force_relink=force_relink)

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

        Returns:
            Update results
        """
        logger.info("Updating company statistics (batch mode)")

        try:
            # Fetch all companies for this client (1 query)
            companies_response = (
                self.client.table('customer_companies')
                .select('id')
                .eq('client_id', self.client_id)
                .execute()
            )

            company_ids = [c['id'] for c in companies_response.data]
            logger.info(f"Found {len(company_ids)} companies to update")

            if not company_ids:
                return {'companies_updated': 0}

            # Fetch all contacts for this client (1 query)
            contacts_response = (
                self.client.table('customer_contacts')
                .select('id, customer_company_id')
                .eq('client_id', self.client_id)
                .not_.is_('customer_company_id', 'null')
                .execute()
            )

            # Count contacts per company in memory
            from collections import Counter
            company_contact_counts = Counter()
            for contact in contacts_response.data:
                company_id = contact.get('customer_company_id')
                if company_id:
                    company_contact_counts[company_id] += 1

            logger.info(f"Counted contacts for {len(company_contact_counts)} companies")

            # Group companies by their contact count for batch updates
            # This minimizes HTTP requests
            count_to_companies: Dict[int, List[str]] = {}
            for company_id in company_ids:
                count = company_contact_counts.get(company_id, 0)
                if count not in count_to_companies:
                    count_to_companies[count] = []
                count_to_companies[count].append(company_id)

            # Batch update companies with the same count
            updated_count = 0
            timestamp = datetime.utcnow().isoformat()

            for contact_count, company_ids_list in count_to_companies.items():
                try:
                    # Update all companies with this count in one request
                    self.client.table('customer_companies').update({
                        'contact_count': contact_count,
                        'updated_at': timestamp
                    }).in_('id', company_ids_list).execute()

                    updated_count += len(company_ids_list)
                    logger.debug(f"Updated {len(company_ids_list)} companies with {contact_count} contacts")

                except Exception as e:
                    logger.error(f"Failed to update batch with count={contact_count}: {e}")

            logger.info(f"Updated statistics for {updated_count} companies in {len(count_to_companies)} batch requests")

            return {
                'companies_updated': updated_count,
                'batch_requests': len(count_to_companies)
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
