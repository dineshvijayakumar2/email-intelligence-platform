from typing import List, Dict, Optional, Tuple, Iterator, Union
from datetime import datetime, timezone
import logging
from uuid import uuid4
import json

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
                
                # Insert batch
                result = self.client.table('emails').insert(prepared_batch).execute()
                
                if result.data:
                    success += len(prepared_batch)
                    logger.info(f"Batch {batch_num}: Inserted {len(prepared_batch)} emails")
                else:
                    failed += len(batch)
                    errors.append(f"Batch {batch_num}: No data returned from insert")
                
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
            'errors': errors
        }

    def stream_insert_emails(
        self,
        emails: Union[Iterator[Dict], List[Dict]],
        mailbox_id: str = None,
        batch_size: int = 5000,
        checkpoint_callback=None,
        skip_duplicates: bool = True,
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
            skip_duplicates: Skip emails that already exist in database
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
        current_batch = []
        last_message_id = None
        was_stopped = False

        logger.info(f"Starting streaming insert with batch_size={batch_size}, skip_duplicates={skip_duplicates}")

        try:
            for email in emails:
                # Check if job should be stopped (check every 10 emails for responsiveness)
                # Also check at start (total=0) for immediate response
                if job_id and (total == 0 or total % 10 == 0):
                    if self.should_stop_job(job_id):
                        logger.warning(f"Job {job_id} stopped by user at email {total}")
                        was_stopped = True
                        break
                total += 1
                last_message_id = email.get('message_id', f'unknown_{total}')

                # Skip duplicates if enabled
                if skip_duplicates and email.get('message_id'):
                    if self.email_exists(email['message_id'], mailbox_id):
                        skipped += 1
                        if total % 100 == 0:  # Log more frequently
                            logger.info(f"📊 Processed {total} emails ({skipped} skipped duplicates)")
                        continue

                current_batch.append(email)

                # Log progress for every email during small tests
                if total <= 20:
                    logger.info(f"📧 Email {total}: {email.get('subject', 'No subject')[:60]}")

                # Update progress periodically (every 10 emails) for better UX on small jobs
                if checkpoint_callback and total % 10 == 0:
                    checkpoint_callback(total, last_message_id)

                # Insert when batch is full
                if len(current_batch) >= batch_size:
                    result = self._insert_batch(current_batch, mailbox_id, total // batch_size)
                    success += result['success']
                    failed += result['failed']
                    errors.extend(result['errors'])

                    # Checkpoint callback for resumability
                    if checkpoint_callback:
                        checkpoint_callback(total, last_message_id)

                    # Clear batch to free memory
                    current_batch = []

                    logger.info(f"Progress: {total} emails processed ({success} inserted, {failed} failed, {skipped} skipped)")

            # Insert remaining emails in final batch
            if current_batch:
                result = self._insert_batch(current_batch, mailbox_id, (total // batch_size) + 1)
                success += result['success']
                failed += result['failed']
                errors.extend(result['errors'])

                if checkpoint_callback:
                    checkpoint_callback(total, last_message_id)

            # Update folder counts after all inserts
            try:
                self.update_folder_counts()
            except Exception as e:
                logger.warning(f"Failed to update folder counts: {e}")

            if was_stopped:
                logger.info(f"Streaming insert STOPPED by user: {total} total, {success} inserted, {failed} failed, {skipped} skipped")
            else:
                logger.info(f"Streaming insert completed: {total} total, {success} inserted, {failed} failed, {skipped} skipped")

            return {
                'total': total,
                'success': success,
                'failed': failed,
                'skipped': skipped,
                'stopped': was_stopped,
                'errors': errors[:100]  # Limit errors to first 100 to avoid memory issues
            }

        except Exception as e:
            logger.error(f"Streaming insert failed at email {total}: {e}")
            raise

    def _insert_batch(self, batch: List[Dict], mailbox_id: str, batch_num: int) -> Dict:
        """
        Internal method to insert a single batch

        Returns:
            Dict with success, failed counts and errors
        """
        success = 0
        failed = 0
        errors = []

        try:
            # Prepare batch data
            prepared_batch = []
            for email in batch:
                prepared_email = self._prepare_email_for_insert(email, mailbox_id)
                if prepared_email:
                    prepared_batch.append(prepared_email)
                else:
                    failed += 1

            if not prepared_batch:
                logger.warning(f"Batch {batch_num}: No valid emails to insert")
                return {'success': 0, 'failed': len(batch), 'errors': [f"Batch {batch_num}: No valid emails"]}

            # Insert batch with retry logic
            max_retries = 3
            inserted_emails = []
            for attempt in range(max_retries):
                try:
                    result = self.client.table('emails').insert(prepared_batch).execute()

                    if result.data:
                        success = len(prepared_batch)
                        inserted_emails = result.data
                        logger.debug(f"Batch {batch_num}: Inserted {success} emails")
                        break
                    else:
                        if attempt == max_retries - 1:
                            failed = len(batch)
                            errors.append(f"Batch {batch_num}: No data returned from insert")

                except Exception as e:
                    if attempt == max_retries - 1:
                        failed = len(batch)
                        error_msg = f"Batch {batch_num} failed after {max_retries} attempts: {str(e)}"
                        errors.append(error_msg)
                        logger.error(error_msg)
                    else:
                        logger.warning(f"Batch {batch_num} attempt {attempt + 1} failed, retrying: {e}")
                        import time
                        time.sleep(1)  # Brief pause before retry

            # Insert tags into email_categories for successfully inserted emails
            if inserted_emails:
                self._insert_email_tags(batch, inserted_emails)
                # Ensure folder entries exist in folders table
                self._ensure_folders_exist(batch, mailbox_id)

        except Exception as e:
            failed = len(batch)
            error_msg = f"Batch {batch_num} preparation failed: {str(e)}"
            errors.append(error_msg)
            logger.error(error_msg)

        return {
            'success': success,
            'failed': failed,
            'errors': errors
        }

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
                'folder_path': self._ensure_utf8(email.get('folder_path', 'INBOX')),
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
                'raw_headers': email.get('raw_headers', {})
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

            # Match original emails with inserted emails by message_id
            for orig_email, inserted_email in zip(original_emails, inserted_emails):
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
                        'tag_type': self._classify_tag_type(tag),
                    })

                # Insert special metadata tags
                if is_spam:
                    category_inserts.append({
                        'email_id': email_id,
                        'category': '_meta_spam',
                        'confidence': 1.0,
                        'detection_method': 'rule_based',
                        'tag_type': 'metadata',
                    })

                if is_marketing:
                    category_inserts.append({
                        'email_id': email_id,
                        'category': '_meta_marketing',
                        'confidence': 1.0,
                        'detection_method': 'rule_based',
                        'tag_type': 'metadata',
                    })

                # Insert priority as metadata
                category_inserts.append({
                    'email_id': email_id,
                    'category': f'_meta_priority_{priority_score}',
                    'confidence': 1.0,
                    'detection_method': 'rule_based',
                    'tag_type': 'metadata',
                })

                # Insert sender type
                if sender_type:
                    category_inserts.append({
                        'email_id': email_id,
                        'category': f'_meta_sender_{sender_type}',
                        'confidence': 1.0,
                        'detection_method': 'rule_based',
                        'tag_type': 'metadata',
                    })

            # Batch insert all categories
            if category_inserts:
                # Insert in chunks of 1000
                chunk_size = 1000
                for i in range(0, len(category_inserts), chunk_size):
                    chunk = category_inserts[i:i + chunk_size]
                    try:
                        self.client.table('email_categories').insert(chunk).execute()
                    except Exception as e:
                        logger.warning(f"Failed to insert tag chunk: {e}")

                logger.debug(f"Inserted {len(category_inserts)} tag entries for {len(inserted_emails)} emails")

        except Exception as e:
            logger.error(f"Failed to insert email tags: {e}")
            # Don't raise - tags are non-critical

    def _classify_tag_type(self, tag: str) -> str:
        """Classify tag into type categories"""
        if tag in ['inbound', 'outbound']:
            return 'direction'
        elif tag in ['new_thread', 'reply', 'forward']:
            return 'thread_type'
        elif tag in ['inbox', 'sent', 'spam', 'trash', 'archive', 'drafts']:
            return 'folder'
        elif tag in ['spam', 'marketing', 'system', 'automated']:
            return 'classification'
        elif tag.startswith('sender_'):
            return 'sender_type'
        elif tag in ['high_priority', 'low_priority', 'urgent']:
            return 'priority'
        else:
            return 'content'

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
        """Check if email already exists in database"""
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
            logger.error(f"Failed to check email existence {message_id}: {e}")
            return False
    
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
        status: str = 'running',
        error_log: List[str] = None
    ):
        """Update processing job progress"""
        try:
            update_data = {
                'processed_records': processed_records,
                'failed_records': failed_records,
                'status': status
            }

            if error_log:
                update_data['error_log'] = error_log

            # Set started_at when job first transitions to running
            if status == 'running':
                # Check if started_at is not already set
                existing_job = self.client.table('processing_jobs').select('started_at').eq('id', job_id).execute()
                if existing_job.data and not existing_job.data[0].get('started_at'):
                    update_data['started_at'] = datetime.now(timezone.utc).isoformat()
                    logger.info(f"Job {job_id} started at {update_data['started_at']}")

            # Set completed_at when job finishes
            if status in ['completed', 'failed', 'stopped']:
                update_data['completed_at'] = datetime.now(timezone.utc).isoformat()
                logger.info(f"Job {job_id} finished with status {status} at {update_data['completed_at']}")

            self.client.table('processing_jobs')\
                .update(update_data)\
                .eq('id', job_id)\
                .execute()

            logger.debug(f"Updated job {job_id}: status={status}, processed={processed_records}, failed={failed_records}")

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