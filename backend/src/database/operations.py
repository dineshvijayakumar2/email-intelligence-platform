from typing import List, Dict, Optional, Tuple, Iterator, Union
from datetime import datetime, timezone
import logging
from uuid import uuid4
import json
import time

from .supabase_client import SupabaseClient

logger = logging.getLogger(__name__)

class EmailOperations:
    """Database operations for emails with UTF-8 preservation"""
    
    def __init__(self, mailbox_id: str = None, use_service_key: bool = True):
        """
        Initialize email operations

        Args:
            mailbox_id: Default mailbox ID for operations
            use_service_key: Use service role key for write operations
        """
        self.client = SupabaseClient.get_client(use_service_key=use_service_key)
        self.mailbox_id = mailbox_id

    def should_stop_job(self, job_id: str) -> bool:
        """
        Check if a job should be stopped

        Args:
            job_id: Job ID to check

        Returns:
            True if job status is 'stopped', 'cancelled', or 'failed'
        """
        try:
            result = self.client.table('processing_jobs').select('status').eq('id', job_id).execute()
            if result.data and len(result.data) > 0:
                status = result.data[0]['status']
                return status in ['stopped', 'cancelled', 'failed']
            return False
        except Exception as e:
            logger.warning(f"Failed to check job status: {e}")
            return False

    def get_job_status(self, job_id: str) -> str:
        """
        Get the current status of a job

        Args:
            job_id: Job ID to check

        Returns:
            Job status string or 'unknown' if not found
        """
        try:
            result = self.client.table('processing_jobs').select('status').eq('id', job_id).execute()
            if result.data and len(result.data) > 0:
                return result.data[0]['status']
            return 'unknown'
        except Exception as e:
            logger.warning(f"Failed to get job status: {e}")
            return 'unknown'

    def wait_while_paused(self, job_id: str) -> bool:
        """
        Wait while job is paused, checking every 5 seconds for status changes

        Args:
            job_id: Job ID to check

        Returns:
            True if resumed (status changed to 'running'), False if stopped/cancelled/failed
        """
        import time

        logger.info(f"Job {job_id} is paused, entering wait state...")
        check_count = 0

        while True:
            check_count += 1
            status = self.get_job_status(job_id)

            if status == 'running':
                logger.info(f"Job {job_id} resumed from pause after {check_count} checks")
                return True
            elif status in ['stopped', 'cancelled', 'failed']:
                logger.info(f"Job {job_id} stopped while paused (status: {status})")
                return False
            elif status == 'paused':
                # Still paused, wait before checking again
                # Log less frequently to avoid spam (every 6th check = every 30 seconds)
                if check_count % 6 == 1:
                    logger.info(f"Job {job_id} still paused (waited {check_count * 5} seconds)...")
                time.sleep(5)  # Check every 5 seconds instead of 2
            else:
                # Unknown status, treat as stopped
                logger.warning(f"Job {job_id} has unexpected status while paused: {status}")
                return False

    def batch_insert_emails(self, emails: List[Dict], mailbox_id: str = None, batch_size: int = 100) -> Dict:
        """
        Insert emails in batches with error handling
        
        Args:
            emails: List of normalized email dictionaries
            mailbox_id: Mailbox ID (uses instance default if not provided)
            batch_size: Number of emails per batch
            
        Returns:
            Dict with processing statistics
        """
        mailbox_id = mailbox_id or self.mailbox_id
        if not mailbox_id:
            raise ValueError("mailbox_id is required")
        total = len(emails)
        success = 0
        failed = 0
        errors = []
        
        for i in range(0, total, batch_size):
            batch = emails[i:i + batch_size]
            batch_num = i // batch_size + 1

            try:
                # Prepare batch data
                prepared_batch = []
                for email in batch:
                    prepared_email = self._prepare_email_for_insert(email, mailbox_id)
                    if prepared_email:
                        prepared_batch.append(prepared_email)

                if not prepared_batch:
                    logger.warning(f"Batch {batch_num}: No valid emails to insert")
                    failed += len(batch)
                    continue

                # Deduplicate within batch to prevent PostgreSQL error 21000
                # "ON CONFLICT DO UPDATE command cannot affect row a second time"
                seen_keys = {}
                deduped = []
                for row in prepared_batch:
                    key = (row.get('message_id'), row.get('mailbox_id'))
                    if key in seen_keys:
                        deduped[seen_keys[key]] = row  # keep latest
                    else:
                        seen_keys[key] = len(deduped)
                        deduped.append(row)
                if len(deduped) < len(prepared_batch):
                    logger.info(f"Batch {batch_num}: Removed {len(prepared_batch) - len(deduped)} duplicates within batch")
                prepared_batch = deduped

                # Use upsert to handle duplicates gracefully
                result = self.client.table('emails').upsert(
                    prepared_batch,
                    on_conflict='message_id,mailbox_id'
                ).execute()

                if result.data:
                    success += len(prepared_batch)
                    logger.info(f"Batch {batch_num}: Upserted {len(prepared_batch)} emails")
                else:
                    failed += len(batch)
                    errors.append(f"Batch {batch_num}: No data returned from upsert")

            except Exception as e:
                failed += len(batch)
                error_msg = f"Batch {batch_num} failed: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)
        
        # Update folder counts after batch insert
        try:
            self.update_folder_counts()
        except Exception as e:
            logger.warning(f"Failed to update folder counts: {e}")
        
        return {
            'total': total,
            'success': success,
            'failed': failed,
            'errors': errors,
            'failed_message_ids': []  # batch_insert_emails doesn't track individual failed IDs
        }

    def stream_insert_emails(
        self,
        emails: Union[Iterator[Dict], List[Dict]],
        mailbox_id: str = None,
        batch_size: int = 5000,
        checkpoint_callback=None,
        skip_duplicates: bool = True,  # Now handled by database upsert
        job_id: str = None
    ) -> Dict:
        """
        Insert emails from an iterator/generator with streaming support.
        Memory-efficient for large datasets (millions of emails).

        Args:
            emails: Iterator or generator yielding normalized email dictionaries
            mailbox_id: Mailbox ID (uses instance default if not provided)
            batch_size: Number of emails per batch (default 5000 for large files)
            checkpoint_callback: Optional callback(processed_count, last_message_id) for progress tracking
            skip_duplicates: Skip emails that already exist in database (now handled by database upsert)
            job_id: Optional job ID for cancellation checks

        Returns:
            Dict with processing statistics including 'stopped' flag
        """
        mailbox_id = mailbox_id or self.mailbox_id
        if not mailbox_id:
            raise ValueError("mailbox_id is required")

        total = 0
        success = 0
        failed = 0
        skipped = 0
        errors = []
        failed_message_ids = []  # Track which specific emails failed
        current_batch = []
        last_message_id = None
        was_stopped = False

        logger.info(f"Starting streaming insert with batch_size={batch_size} (using database upsert for deduplication)")
        
        # Performance tracking for time estimation
        start_time = time.time()
        emails_per_second = 0

        try:
            for email in emails:
                # Check if job should be stopped or paused (check every 5 emails for quick responsiveness)
                # Also check at start (total=0) for immediate response
                if job_id and (total == 0 or total % 5 == 0):
                    if self.should_stop_job(job_id):
                        logger.warning(f"Job {job_id} stopped by user at email {total}")
                        was_stopped = True
                        break

                    # Check if job is paused
                    status = self.get_job_status(job_id)
                    if status == 'paused':
                        logger.info(f"Job {job_id} paused at email {total}, waiting for resume...")

                        if not self.wait_while_paused(job_id):
                            # Job was stopped/cancelled while paused
                            logger.warning(f"Job {job_id} stopped while paused")
                            was_stopped = True
                            break

                        # Job resumed, continue processing
                        logger.info(f"Job {job_id} resumed, continuing from email {total}...")

                total += 1
                last_message_id = email.get('message_id', f'unknown_{total}')

                # Add email directly to batch - duplicates handled by database upsert
                current_batch.append(email)
                
                # Calculate and update ETA in Redis (for frontend) every 10 emails
                # But only LOG to terminal every 100 emails to reduce noise
                if total % 10 == 0:
                    elapsed = time.time() - start_time
                    emails_per_second = total / elapsed if elapsed > 0 else 0

                    # Calculate estimated time remaining
                    from .redis_client import JobProgressManager
                    progress_manager = JobProgressManager()

                    # Get total emails expected (from Redis or estimate) with robust null handling
                    if job_id:
                        try:
                            progress_data = progress_manager.get_progress(job_id)
                            total_expected = 0  # Default safe value

                            if progress_data and isinstance(progress_data, dict):
                                total_records_raw = progress_data.get('total_records', 0)
                                if total_records_raw is not None:
                                    try:
                                        total_expected = int(total_records_raw)
                                    except (ValueError, TypeError):
                                        total_expected = 0

                            # Calculate ETA if we know total, otherwise just update speed
                            estimated_seconds_remaining = 0
                            eta_str = None

                            if isinstance(total_expected, int) and total_expected > 0 and isinstance(emails_per_second, (int, float)) and emails_per_second > 0:
                                remaining_emails = max(0, total_expected - total)
                                estimated_seconds_remaining = remaining_emails / emails_per_second
                                estimated_minutes = estimated_seconds_remaining / 60

                                if estimated_minutes < 1:
                                    eta_str = f"{estimated_seconds_remaining:.0f}s"
                                elif estimated_minutes < 60:
                                    eta_str = f"{estimated_minutes:.1f}m"
                                else:
                                    eta_hours = estimated_minutes / 60
                                    eta_str = f"{eta_hours:.1f}h"

                            # ALWAYS store processing speed in Redis for frontend (even without ETA)
                            progress_manager.update_progress(
                                job_id, total, failed,
                                emails_per_second=emails_per_second,
                                estimated_seconds_remaining=estimated_seconds_remaining
                            )

                            # Only log to terminal every 100 emails (or first 10)
                            if total <= 10 or total % 100 == 0:
                                if eta_str:
                                    logger.info(f"[STATS] Processed {total}/{total_expected} emails - {emails_per_second:.1f} emails/sec - ETA: {eta_str}")
                                else:
                                    logger.info(f"[STATS] Processed {total} emails - {emails_per_second:.1f} emails/sec")

                        except Exception as e:
                            logger.debug(f"Failed to calculate ETA: {e}")

                # Update progress more frequently for better UX
                # - First email: immediate update
                # - First 100 emails: every 5 emails
                # - After 100: every 10 emails
                # Send total examined count (includes processed, skipped, and pending batch)
                if checkpoint_callback:
                    should_update = (total == 1) or \
                                    (total <= 100 and total % 5 == 0) or \
                                    (total > 100 and total % 10 == 0)
                    if should_update:
                        # Use 'total' which includes all emails examined (new, skipped, batched)
                        checkpoint_callback(total, last_message_id)

                # Insert when batch is full
                if len(current_batch) >= batch_size:
                    # Check one more time before expensive batch insert
                    if job_id and self.should_stop_job(job_id):
                        logger.warning(f"Job {job_id} stopped before batch insert at email {total}")
                        was_stopped = True
                        break

                    # Check if paused before batch insert
                    if job_id:
                        status = self.get_job_status(job_id)
                        if status == 'paused':
                            logger.info(f"Job {job_id} paused before batch insert, waiting...")
                            if not self.wait_while_paused(job_id):
                                logger.warning(f"Job {job_id} stopped while paused before batch insert")
                                was_stopped = True
                                break

                    result = self._insert_batch(current_batch, mailbox_id, total // batch_size)
                    success += result['success']
                    failed += result['failed']
                    errors.extend(result['errors'])
                    failed_message_ids.extend(result.get('failed_message_ids', []))

                    # Checkpoint callback for resumability
                    if checkpoint_callback:
                        checkpoint_callback(total, last_message_id)

                    # Clear batch to free memory
                    current_batch = []

                    # Force garbage collection every 10 batches to reduce memory footprint
                    # Critical for processing 100k+ emails with limited RAM
                    if (total // batch_size) % 10 == 0:
                        import gc
                        gc.collect()
                        logger.debug(f"Garbage collected after {total} emails")

                    logger.info(f"Progress: {total} emails processed ({success} inserted, {failed} failed)")

            # Insert remaining emails in final batch
            logger.info(f"[DB-INSERT] Final batch check: {len(current_batch)} emails in batch, {total} total processed")
            if current_batch:
                logger.info(f"[DB-INSERT] Inserting final batch of {len(current_batch)} emails to mailbox {mailbox_id}")
                result = self._insert_batch(current_batch, mailbox_id, (total // batch_size) + 1)
                logger.info(f"[DB-INSERT] Final batch result: success={result['success']}, failed={result['failed']}")
                success += result['success']
                failed += result['failed']
                errors.extend(result['errors'])
                failed_message_ids.extend(result.get('failed_message_ids', []))

                if checkpoint_callback:
                    checkpoint_callback(total, last_message_id)
            else:
                logger.warning(f"[DB-INSERT] No emails in final batch! Total processed: {total}")

            # Update folder counts after all inserts
            try:
                self.update_folder_counts()
            except Exception as e:
                logger.warning(f"Failed to update folder counts: {e}")

            if was_stopped:
                logger.info(f"Streaming insert STOPPED by user: {total} total, {success} inserted, {failed} failed (duplicates handled by database)")
            else:
                logger.info(f"Streaming insert completed: {total} total, {success} inserted, {failed} failed (duplicates handled by database)")

            # Log failed message_ids summary if any failures occurred
            if failed_message_ids:
                logger.warning(f"Failed to insert {len(failed_message_ids)} emails. Sample message_ids: {failed_message_ids[:10]}")

            return {
                'total': total,
                'success': success,
                'failed': failed,
                'skipped': 0,  # Duplicates now handled by database upsert
                'stopped': was_stopped,
                'errors': errors[:100],  # Limit errors to first 100 to avoid memory issues
                'failed_message_ids': failed_message_ids[:500]  # Limit to 500 for memory
            }

        except Exception as e:
            logger.error(f"Streaming insert failed at email {total}: {e}")
            raise

    def _insert_batch(self, batch: List[Dict], mailbox_id: str, batch_num: int) -> Dict:
        """
        Insert a batch of emails with adaptive retry and automatic batch splitting.

        Design principles:
        1. Start with optimal batch size (250 emails)
        2. On timeout, automatically split batch and retry smaller chunks
        3. Progressive backoff with jitter to avoid thundering herd
        4. Fail gracefully - never lose the entire batch on transient errors
        5. Deduplicate within batch to avoid PostgreSQL 21000 error

        Returns:
            Dict with success, failed counts and errors
        """
        success = 0
        failed = 0
        errors = []

        # Prepare all emails first
        prepared_batch = []
        original_emails_prepared = []

        for email in batch:
            prepared_email = self._prepare_email_for_insert(email, mailbox_id)
            if prepared_email:
                prepared_batch.append(prepared_email)
                original_emails_prepared.append(email)
            else:
                failed += 1

        if not prepared_batch:
            return {'success': 0, 'failed': len(batch), 'errors': ['All emails failed validation']}

        # CRITICAL: Deduplicate within batch to prevent PostgreSQL error 21000
        # "ON CONFLICT DO UPDATE command cannot affect row a second time"
        # Keep only the last occurrence of each message_id (most complete version)
        seen_message_ids = {}
        deduplicated_batch = []
        deduplicated_originals = []
        duplicates_in_batch = 0

        for i, prepared_email in enumerate(prepared_batch):
            message_id = prepared_email.get('message_id')
            if message_id in seen_message_ids:
                # Duplicate found - replace with newer version
                old_idx = seen_message_ids[message_id]
                deduplicated_batch[old_idx] = prepared_email
                deduplicated_originals[old_idx] = original_emails_prepared[i]
                duplicates_in_batch += 1
            else:
                seen_message_ids[message_id] = len(deduplicated_batch)
                deduplicated_batch.append(prepared_email)
                deduplicated_originals.append(original_emails_prepared[i])

        if duplicates_in_batch > 0:
            logger.info(f"Batch {batch_num}: Removed {duplicates_in_batch} duplicates within batch ({len(prepared_batch)} -> {len(deduplicated_batch)})")

        prepared_batch = deduplicated_batch
        original_emails_prepared = deduplicated_originals

        # Use adaptive upsert for resilient insertion
        result = self._adaptive_upsert(
            prepared_batch,
            original_emails_prepared,
            mailbox_id,
            batch_num
        )

        return {
            'success': result['success'],
            'failed': failed + result['failed'],
            'errors': result['errors'],
            'failed_message_ids': result.get('failed_message_ids', [])
        }

    def _adaptive_upsert(
        self,
        prepared_batch: List[Dict],
        original_emails: List[Dict],
        mailbox_id: str,
        batch_num: int,
        min_batch_size: int = 25,
        depth: int = 0
    ) -> Dict:
        """
        Adaptive upsert with automatic batch splitting on failure.

        Strategy:
        - Try full batch first (fast path)
        - On timeout/failure, split in half and retry each
        - Continue until success or minimum batch size reached
        - This ensures ~97%+ success rate even with network issues

        Args:
            prepared_batch: Emails ready for DB insertion
            original_emails: Original emails (for tag insertion)
            mailbox_id: Target mailbox
            batch_num: For logging
            min_batch_size: Stop splitting below this (default 25)
            depth: Recursion depth for logging
        """
        import random

        batch_size = len(prepared_batch)
        indent = "  " * depth  # Visual indication of split depth

        # Configuration
        max_retries = 4
        base_wait = 1.5  # Start with 1.5s wait

        for attempt in range(max_retries):
            try:
                result = self.client.table('emails').upsert(
                    prepared_batch,
                    on_conflict='message_id,mailbox_id'
                ).execute()

                if result.data:
                    success_count = len(result.data)

                    # Insert tags for successful emails
                    if result.data and original_emails:
                        self._insert_email_tags(original_emails, result.data)
                        self._ensure_folders_exist(original_emails, mailbox_id)

                    if depth == 0:
                        logger.info(f"Batch {batch_num}: Inserted {success_count} emails")

                    return {'success': success_count, 'failed': 0, 'errors': [], 'failed_message_ids': []}

            except Exception as e:
                error_str = str(e).lower()
                is_timeout = 'timeout' in error_str or 'timed out' in error_str

                # If timeout and batch is splittable, split immediately
                if is_timeout and batch_size > min_batch_size:
                    logger.warning(f"{indent}Batch {batch_num}: Timeout at {batch_size} emails, splitting...")
                    break  # Exit retry loop to split

                # For other errors or if we can still retry
                if attempt < max_retries - 1:
                    # Exponential backoff with jitter
                    wait_time = base_wait * (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(f"{indent}Batch {batch_num} attempt {attempt + 1} failed, waiting {wait_time:.1f}s")
                    time.sleep(wait_time)
                else:
                    # Final attempt failed
                    if batch_size > min_batch_size:
                        break  # Try splitting
                    else:
                        # At minimum size, mark as failed and log message_ids for debugging
                        failed_message_ids = [email.get('message_id', 'unknown')[:50] for email in prepared_batch[:5]]
                        logger.error(f"{indent}Batch {batch_num} failed at min size ({batch_size}): {str(e)[:100]}")
                        logger.error(f"{indent}Failed message_ids (sample): {failed_message_ids}")
                        return {
                            'success': 0,
                            'failed': batch_size,
                            'errors': [f"Batch {batch_num}: {str(e)[:200]}"],
                            'failed_message_ids': [email.get('message_id') for email in prepared_batch]
                        }

        # Split and retry each half
        if batch_size > min_batch_size:
            mid = batch_size // 2

            logger.info(f"{indent}Splitting batch {batch_num}: {batch_size} -> {mid} + {batch_size - mid}")

            # Process first half
            result1 = self._adaptive_upsert(
                prepared_batch[:mid],
                original_emails[:mid],
                mailbox_id,
                f"{batch_num}a",
                min_batch_size,
                depth + 1
            )

            # Process second half
            result2 = self._adaptive_upsert(
                prepared_batch[mid:],
                original_emails[mid:],
                mailbox_id,
                f"{batch_num}b",
                min_batch_size,
                depth + 1
            )

            # Merge failed_message_ids from both halves
            failed_ids = result1.get('failed_message_ids', []) + result2.get('failed_message_ids', [])
            return {
                'success': result1['success'] + result2['success'],
                'failed': result1['failed'] + result2['failed'],
                'errors': result1['errors'] + result2['errors'],
                'failed_message_ids': failed_ids if failed_ids else []
            }

        # Shouldn't reach here, but handle gracefully
        return {'success': 0, 'failed': batch_size, 'errors': [f"Batch {batch_num} failed"], 'failed_message_ids': []}

    def _prepare_email_for_insert(self, email: Dict, mailbox_id: str) -> Optional[Dict]:
        """
        Prepare email data for database insertion
        
        Args:
            email: Normalized email dictionary
            mailbox_id: Mailbox ID for the email
            
        Returns:
            Prepared email dict or None if invalid
        """
        try:
            # Required fields validation
            if not email.get('message_id') or not email.get('sender_email'):
                logger.warning("Email missing required fields: message_id or sender_email")
                return None
            
            # Ensure UTF-8 encoding for text fields
            prepared = {
                'message_id': self._ensure_utf8(email.get('message_id', '')),
                'mailbox_id': mailbox_id,
                'thread_id': self._ensure_utf8(email.get('thread_id', '')),
                'folder_path': self._ensure_utf8(email.get('folder_path', 'Inbox')),
                'sender_email': self._ensure_utf8(email.get('sender_email', '')),
                'sender_name': self._ensure_utf8(email.get('sender_name', '')),
                'subject': self._ensure_utf8(email.get('subject', '')),
                'body_text': self._ensure_utf8(email.get('body_text', '')),
                'body_html': self._ensure_utf8(email.get('body_html', '')),
                'sent_date': self._format_datetime(email.get('sent_date')),
                'received_date': self._format_datetime(email.get('received_date')),
                'is_outbound': bool(email.get('is_outbound', False)),
                'is_reply': bool(email.get('is_reply', False)),
                'message_size': int(email.get('message_size', 0)),
                'recipients': email.get('recipients', []),
                'cc_list': email.get('cc_list', []),
                'bcc_list': email.get('bcc_list', []),
                'raw_headers': email.get('raw_headers', {}),
                'processing_status': email.get('processing_status', 'success')
            }
            
            # Validate JSON fields
            for json_field in ['recipients', 'cc_list', 'bcc_list', 'raw_headers']:
                if not isinstance(prepared[json_field], (list, dict)):
                    prepared[json_field] = []
            
            return prepared
            
        except Exception as e:
            logger.error(f"Failed to prepare email for insert: {e}")
            return None
    
    def _insert_email_tags(self, original_emails: List[Dict], inserted_emails: List[Dict]):
        """
        Insert email tags into email_categories table

        Args:
            original_emails: Original email dicts with tags
            inserted_emails: Emails returned from database insert (with email_id)
        """
        try:
            category_inserts = []

            # Build lookup map from message_id to inserted email (with database ID)
            inserted_by_message_id = {
                email.get('message_id'): email
                for email in inserted_emails
                if email.get('message_id')
            }

            # Match original emails with inserted emails by message_id (not position)
            for orig_email in original_emails:
                message_id = orig_email.get('message_id')
                if not message_id:
                    continue

                inserted_email = inserted_by_message_id.get(message_id)
                if not inserted_email:
                    continue

                email_id = inserted_email.get('id')
                if not email_id:
                    continue

                # Get tags from original email
                tags = orig_email.get('tags', [])
                is_spam = orig_email.get('is_spam', False)
                is_marketing = orig_email.get('is_marketing', False)
                priority_score = orig_email.get('priority_score', 5)
                sender_type = orig_email.get('sender_type', 'unknown')

                # Insert each tag as a category
                for tag in tags:
                    category_inserts.append({
                        'email_id': email_id,
                        'category': tag,
                        'confidence': 1.0,  # Rule-based tags have 100% confidence
                        'detection_method': 'rule_based',
                    })

                # Insert special metadata tags
                if is_spam:
                    category_inserts.append({
                        'email_id': email_id,
                        'category': '_meta_spam',
                        'confidence': 1.0,
                        'detection_method': 'rule_based',
                    })

                if is_marketing:
                    category_inserts.append({
                        'email_id': email_id,
                        'category': '_meta_marketing',
                        'confidence': 1.0,
                        'detection_method': 'rule_based',
                    })

                # Insert priority as metadata
                category_inserts.append({
                    'email_id': email_id,
                    'category': f'_meta_priority_{priority_score}',
                    'confidence': 1.0,
                    'detection_method': 'rule_based',
                })

                # Insert sender type
                if sender_type:
                    category_inserts.append({
                        'email_id': email_id,
                        'category': f'_meta_sender_{sender_type}',
                        'confidence': 1.0,
                        'detection_method': 'rule_based',
                    })

            # Batch insert all categories
            if not category_inserts:
                logger.warning(f"No tags to insert for {len(original_emails)} emails - check if emails have tags")
                return

            if category_inserts:
                # Insert in chunks of 1000
                chunk_size = 1000
                for i in range(0, len(category_inserts), chunk_size):
                    chunk = category_inserts[i:i + chunk_size]
                    try:
                        self.client.table('email_categories').insert(chunk).execute()
                    except Exception as e:
                        # Duplicate key errors are expected for re-processed emails - ignore silently
                        error_str = str(e)
                        if '23505' in error_str or 'duplicate key' in error_str.lower():
                            logger.debug(f"Tag chunk had duplicates (expected): {len(chunk)} entries")
                        else:
                            logger.warning(f"Failed to insert tag chunk: {e}")

                logger.info(f"Inserted {len(category_inserts)} tag entries for {len(inserted_emails)} emails into email_categories")

        except Exception as e:
            logger.error(f"Failed to insert email tags: {e}")
            # Don't raise - tags are non-critical

    def _ensure_folders_exist(self, emails: List[Dict], mailbox_id: str):
        """
        Ensure folder entries exist in folders table for all unique folders in emails

        Args:
            emails: List of email dicts with folder_path
            mailbox_id: Mailbox ID
        """
        try:
            # Collect unique folder paths from emails
            folder_paths = set()
            for email in emails:
                folder_path = email.get('folder_path')
                if folder_path:
                    folder_paths.add(folder_path)

            if not folder_paths:
                return

            # Map folder names to folder types
            folder_type_map = {
                'Inbox': 'inbox',
                'INBOX': 'inbox',
                'Sent': 'sent',
                'Sent Items': 'sent',
                'Spam': 'spam',
                'Junk': 'spam',
                'Trash': 'trash',
                'Deleted Items': 'trash',
                'Drafts': 'drafts',
                'Archive': 'archive',
                'Archived': 'archive'
            }

            # Check which folders already exist
            existing_folders = set()
            try:
                result = self.client.table('folders').select('folder_path').eq('mailbox_id', mailbox_id).execute()
                if result.data:
                    existing_folders = {f['folder_path'] for f in result.data}
            except Exception as e:
                logger.warning(f"Failed to check existing folders: {e}")

            # Create missing folders
            new_folders = []
            for folder_path in folder_paths:
                if folder_path not in existing_folders:
                    folder_type = folder_type_map.get(folder_path, 'user')
                    new_folders.append({
                        'folder_path': folder_path,
                        'mailbox_id': mailbox_id,
                        'folder_type': folder_type,
                        'message_count': 0
                    })

            if new_folders:
                try:
                    self.client.table('folders').insert(new_folders).execute()
                    logger.info(f"Created {len(new_folders)} folder entries")
                except Exception as e:
                    logger.warning(f"Failed to create folders: {e}")

        except Exception as e:
            logger.error(f"Failed to ensure folders exist: {e}")
            # Don't raise - folder creation is non-critical

    def _ensure_utf8(self, text: str) -> str:
        """Ensure text is valid UTF-8"""
        if not isinstance(text, str):
            return str(text) if text is not None else ''

        try:
            # Test if already valid UTF-8
            text.encode('utf-8')
            return text
        except UnicodeEncodeError:
            # Fix encoding issues
            return text.encode('utf-8', errors='replace').decode('utf-8')
    
    def _format_datetime(self, dt) -> Optional[str]:
        """Convert datetime to ISO format string for JSON serialization"""
        if dt is None:
            return None
        
        if isinstance(dt, datetime):
            return dt.isoformat()
        
        if isinstance(dt, str):
            return dt
        
        return None
    
    def get_email_by_message_id(self, message_id: str) -> Optional[Dict]:
        """Retrieve email by message_id"""
        try:
            result = self.client.table('emails')\
                .select('*')\
                .eq('message_id', message_id)\
                .execute()
            
            if result.data:
                return result.data[0]
            return None
            
        except Exception as e:
            logger.error(f"Failed to get email {message_id}: {e}")
            return None
    
    def email_exists(self, message_id: str, mailbox_id: str = None) -> bool:
        """Check if email already exists in database (single email check)"""
        try:
            mailbox_id = mailbox_id or self.mailbox_id
            if not mailbox_id:
                raise ValueError("mailbox_id is required")
                
            result = self.client.table('emails')\
                .select('id')\
                .eq('message_id', message_id)\
                .eq('mailbox_id', mailbox_id)\
                .limit(1)\
                .execute()
            
            return len(result.data) > 0
        except Exception as e:
            logger.warning(f"Failed to check email existence: {e}")
            return False
    
    def batch_check_emails_exist(self, message_ids: List[str], mailbox_id: str = None) -> set:
        """
        Check which emails already exist in database (optimized batch check)
        
        Args:
            message_ids: List of message IDs to check
            mailbox_id: Mailbox ID to check within
            
        Returns:
            Set of message IDs that already exist
        """
        try:
            mailbox_id = mailbox_id or self.mailbox_id
            if not mailbox_id:
                raise ValueError("mailbox_id is required")
            
            if not message_ids:
                return set()
            
            # Use 'in' operator for batch lookup - much more efficient
            result = self.client.table('emails')\
                .select('message_id')\
                .eq('mailbox_id', mailbox_id)\
                .in_('message_id', message_ids)\
                .execute()
            
            # Return set of existing message IDs
            return {row['message_id'] for row in result.data}
            
        except Exception as e:
            logger.warning(f"Failed batch email existence check: {e}")
            return set()  # Conservative fallback
    
    def search_emails(
        self,
        query: str = None,
        sender: str = None,
        date_from: datetime = None,
        date_to: datetime = None,
        folder: str = None,
        is_outbound: bool = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict], int]:
        """
        Search emails with filters
        
        Returns:
            Tuple of (emails list, total count)
        """
        try:
            # Build base query
            query_builder = self.client.table('emails').select('*', count='exact')
            
            # Apply filters
            if sender:
                query_builder = query_builder.ilike('sender_email', f'%{sender}%')
            
            if date_from:
                query_builder = query_builder.gte('sent_date', date_from.isoformat())
            
            if date_to:
                query_builder = query_builder.lte('sent_date', date_to.isoformat())
            
            if folder:
                query_builder = query_builder.eq('folder_path', folder)
            
            if is_outbound is not None:
                query_builder = query_builder.eq('is_outbound', is_outbound)
            
            # For full-text search, use the database function
            if query:
                # Note: This requires the search_emails function to be created in the database
                search_result = self.client.rpc('search_emails', {
                    'search_query': query,
                    'limit_count': limit
                }).execute()
                
                if search_result.data:
                    return search_result.data, len(search_result.data)
                else:
                    return [], 0
            
            # Apply pagination and ordering
            query_builder = query_builder.order('sent_date', desc=True)\
                                       .range(offset, offset + limit - 1)
            
            result = query_builder.execute()
            
            return result.data or [], result.count or 0
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return [], 0
    
    def get_folder_stats(self) -> List[Dict]:
        """Get email statistics by folder"""
        try:
            result = self.client.table('folder_stats').select('*').execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Failed to get folder stats: {e}")
            return []
    
    def get_daily_volume(self, days: int = 30) -> List[Dict]:
        """Get daily email volume statistics"""
        try:
            result = self.client.table('daily_email_volume')\
                .select('*')\
                .order('date', desc=True)\
                .limit(days)\
                .execute()
            
            return result.data or []
        except Exception as e:
            logger.error(f"Failed to get daily volume: {e}")
            return []
    
    def get_top_correspondents(self, limit: int = 20) -> List[Dict]:
        """Get top email correspondents"""
        try:
            result = self.client.table('top_correspondents')\
                .select('*')\
                .limit(limit)\
                .execute()
            
            return result.data or []
        except Exception as e:
            logger.error(f"Failed to get top correspondents: {e}")
            return []
    
    def update_folder_counts(self):
        """Update message counts in folders table"""
        try:
            self.client.rpc('update_folder_counts', {}).execute()
            logger.info("Folder counts updated")
        except Exception as e:
            logger.error(f"Failed to update folder counts: {e}")
    
    def create_processing_job(self, job_type: str, mailbox_id: str = None, total_records: int = 0) -> str:
        """Create a new processing job record"""
        try:
            mailbox_id = mailbox_id or self.mailbox_id
            
            job_id = str(uuid4())
            
            job_data = {
                'id': job_id,
                'job_type': job_type,
                'status': 'pending',
                'total_records': total_records,
                'started_at': datetime.now(timezone.utc).isoformat()
            }
            
            if mailbox_id:
                job_data['mailbox_id'] = mailbox_id
            
            result = self.client.table('processing_jobs').insert(job_data).execute()
            
            logger.info(f"Created processing job: {job_id} for mailbox: {mailbox_id}")
            return job_id
            
        except Exception as e:
            logger.error(f"Failed to create processing job: {e}")
            raise
    
    def update_job_progress(
        self,
        job_id: str,
        processed_records: int,
        failed_records: int = 0,
        filtered_records: int = 0,
        status: str = 'running',
        error_log: List[str] = None,
        update_status: bool = True
    ):
        """Update processing job progress

        Args:
            job_id: Job ID to update
            processed_records: Number of records processed
            failed_records: Number of failed records
            filtered_records: Number of records filtered by date range (Stage 2)
            status: Job status (only used if update_status=True)
            error_log: List of error messages
            update_status: If False, only update counts, preserve current status
        """
        try:
            update_data = {
                'processed_records': processed_records,
                'failed_records': failed_records,
                'filtered_records': filtered_records
            }

            # Only update status if requested
            if update_status:
                # CRITICAL SAFEGUARD: Never override 'stopped' or 'cancelled' status with 'failed'
                # Check current status before attempting to set to 'failed'
                if status == 'failed':
                    current_job = self.client.table('processing_jobs').select('status').eq('id', job_id).execute()
                    if current_job.data and current_job.data[0].get('status') in ['stopped', 'cancelled']:
                        logger.warning(f"Prevented overriding '{current_job.data[0]['status']}' status with 'failed' for job {job_id}")
                        # Don't update status to failed, just update the records and error log
                        status = current_job.data[0]['status']  # Keep the current status

                update_data['status'] = status

            if error_log:
                update_data['error_log'] = error_log

            # Set started_at when job first transitions to running (only if updating status)
            if update_status and status == 'running':
                # Check if started_at is not already set
                existing_job = self.client.table('processing_jobs').select('started_at').eq('id', job_id).execute()
                if existing_job.data and not existing_job.data[0].get('started_at'):
                    update_data['started_at'] = datetime.now(timezone.utc).isoformat()
                    logger.info(f"Job {job_id} started at {update_data['started_at']}")

            # Set completed_at when job finishes (only if updating status)
            if update_status and status in ['completed', 'failed', 'stopped']:
                update_data['completed_at'] = datetime.now(timezone.utc).isoformat()
                logger.info(f"Job {job_id} finished with status {status} at {update_data['completed_at']}")

            self.client.table('processing_jobs')\
                .update(update_data)\
                .eq('id', job_id)\
                .execute()

            if update_status:
                logger.debug(f"Updated job {job_id}: status={status}, processed={processed_records}, failed={failed_records}, filtered={filtered_records}")
            else:
                logger.info(f"Progress: Job {job_id} - {processed_records} processed, {failed_records} failed, {filtered_records} filtered")

        except Exception as e:
            logger.error(f"Failed to update job progress: {e}")
    
    def get_database_stats(self) -> Dict:
        """Get overall database statistics"""
        try:
            # Get total email count
            total_result = self.client.table('emails')\
                .select('count')\
                .execute()
            
            total_emails = total_result.count or 0
            
            # Get date range
            date_result = self.client.table('emails')\
                .select('sent_date')\
                .order('sent_date', desc=False)\
                .limit(1)\
                .execute()
            
            earliest_date = None
            if date_result.data:
                earliest_date = date_result.data[0].get('sent_date')
            
            latest_result = self.client.table('emails')\
                .select('sent_date')\
                .order('sent_date', desc=True)\
                .limit(1)\
                .execute()
            
            latest_date = None
            if latest_result.data:
                latest_date = latest_result.data[0].get('sent_date')
            
            # Get folder count
            folder_result = self.client.table('folders')\
                .select('count')\
                .execute()
            
            folder_count = folder_result.count or 0
            
            return {
                'total_emails': total_emails,
                'earliest_date': earliest_date,
                'latest_date': latest_date,
                'folder_count': folder_count,
                'last_updated': datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get database stats: {e}")
            return {}
    
    def cleanup_duplicate_emails(self) -> int:
        """Remove duplicate emails based on message_id"""
        try:
            # This is a complex operation that should be done carefully
            # For now, just return 0 and implement later if needed
            logger.info("Duplicate cleanup not implemented yet")
            return 0

        except Exception as e:
            logger.error(f"Failed to cleanup duplicates: {e}")
            return 0

    # =========================================================================
    # Error Tracking Methods (Stage 2)
    # =========================================================================

    def update_email_processing_status(
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
                'last_processing_attempt': datetime.now(timezone.utc).isoformat()
            }

            if error_message:
                update_data['processing_error'] = error_message[:1000]  # Limit size

            if status == 'success':
                update_data['processing_error'] = None  # Clear error on success

            self.client.table('emails').update(update_data).eq('id', email_id).execute()

            # Increment attempts using raw SQL if needed
            if increment_attempts:
                # Use a separate update to increment
                try:
                    self.client.rpc('increment_processing_attempts', {'p_email_id': email_id}).execute()
                except Exception:
                    # If RPC doesn't exist, do manual increment
                    current = self.client.table('emails').select('processing_attempts').eq('id', email_id).execute()
                    if current.data:
                        current_attempts = current.data[0].get('processing_attempts', 0) or 0
                        self.client.table('emails').update({
                            'processing_attempts': current_attempts + 1
                        }).eq('id', email_id).execute()

            return True

        except Exception as e:
            logger.error(f"Failed to update email processing status: {e}")
            return False

    def batch_update_email_status(
        self,
        email_ids: List[str],
        status: str,
        error_message: Optional[str] = None
    ) -> int:
        """
        Update processing status for multiple emails at once.

        Args:
            email_ids: List of email UUIDs
            status: New status to set
            error_message: Optional error message (for failed status)

        Returns:
            Number of emails updated
        """
        if not email_ids:
            return 0

        try:
            update_data = {
                'processing_status': status,
                'last_processing_attempt': datetime.now(timezone.utc).isoformat()
            }

            if error_message:
                update_data['processing_error'] = error_message[:1000]

            if status == 'success':
                update_data['processing_error'] = None

            result = self.client.table('emails').update(update_data).in_('id', email_ids).execute()

            return len(result.data) if result.data else 0

        except Exception as e:
            logger.error(f"Failed to batch update email status: {e}")
            return 0

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
            result = self.client.table('emails').select(
                'id, message_id, subject, sender_email, sent_date, '
                'processing_error, processing_attempts, last_processing_attempt'
            ).eq(
                'mailbox_id', mailbox_id
            ).eq(
                'processing_status', 'failed'
            ).order(
                'last_processing_attempt', desc=True
            ).range(offset, offset + limit - 1).execute()

            return result.data or []

        except Exception as e:
            logger.error(f"Failed to get failed emails: {e}")
            return []

    def get_error_counts_by_type(self, mailbox_id: str) -> Dict[str, int]:
        """
        Get counts of failed emails grouped by error type.

        Args:
            mailbox_id: UUID of the mailbox

        Returns:
            Dictionary with error type as key and count as value
        """
        try:
            # Get all failed emails and classify them
            result = self.client.table('emails').select(
                'processing_error'
            ).eq(
                'mailbox_id', mailbox_id
            ).eq(
                'processing_status', 'failed'
            ).execute()

            if not result.data:
                return {}

            # Classify errors
            error_counts = {}
            for row in result.data:
                error_msg = (row.get('processing_error') or '').lower()

                if 'encoding' in error_msg or 'decode' in error_msg or 'codec' in error_msg:
                    error_type = 'encoding_error'
                elif 'parse' in error_msg:
                    error_type = 'parse_error'
                elif 'timeout' in error_msg:
                    error_type = 'timeout_error'
                elif 'connection' in error_msg:
                    error_type = 'connection_error'
                elif 'duplicate' in error_msg or 'unique' in error_msg:
                    error_type = 'duplicate_error'
                else:
                    error_type = 'other_error'

                error_counts[error_type] = error_counts.get(error_type, 0) + 1

            return error_counts

        except Exception as e:
            logger.error(f"Failed to get error counts: {e}")
            return {}

    def reset_failed_emails_for_retry(
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
            # Get emails that can be retried
            emails_to_reset = self.client.table('emails').select('id').eq(
                'mailbox_id', mailbox_id
            ).eq(
                'processing_status', 'failed'
            ).lt(
                'processing_attempts', max_attempts
            ).execute()

            if not emails_to_reset.data:
                return 0

            email_ids = [e['id'] for e in emails_to_reset.data]

            # Reset them to pending
            self.client.table('emails').update({
                'processing_status': 'pending',
                'processing_error': None
            }).in_('id', email_ids).execute()

            logger.info(f"Reset {len(email_ids)} failed emails for retry in mailbox {mailbox_id}")
            return len(email_ids)

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
            self.client.table('processing_jobs').update({
                'error_summary': error_summary
            }).eq('id', job_id).execute()

            logger.info(f"Saved error summary for job {job_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to save job error summary: {e}")
            return False

    def get_processing_stats(self, mailbox_id: str) -> Dict:
        """
        Get processing statistics for a mailbox.

        Args:
            mailbox_id: UUID of the mailbox

        Returns:
            Dictionary with processing stats
        """
        try:
            # Count by status
            result = self.client.table('emails').select(
                'processing_status'
            ).eq('mailbox_id', mailbox_id).execute()

            stats = {
                'total': 0,
                'pending': 0,
                'processing': 0,
                'success': 0,
                'failed': 0,
                'skipped': 0
            }

            for row in (result.data or []):
                status = row.get('processing_status', 'pending')
                stats['total'] += 1
                if status in stats:
                    stats[status] += 1

            return stats

        except Exception as e:
            logger.error(f"Failed to get processing stats: {e}")
            return {}