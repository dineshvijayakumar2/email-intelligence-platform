from typing import List, Dict, Optional, Tuple
from datetime import datetime
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
                'started_at': datetime.now().isoformat()
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
            
            if status in ['completed', 'failed']:
                update_data['completed_at'] = datetime.now().isoformat()
            
            self.client.table('processing_jobs')\
                .update(update_data)\
                .eq('id', job_id)\
                .execute()
            
            logger.debug(f"Updated job {job_id}: {processed_records} processed")
            
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
                'last_updated': datetime.now().isoformat()
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