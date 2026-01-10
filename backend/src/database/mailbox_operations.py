from typing import List, Dict, Optional
from datetime import datetime
import logging
from uuid import uuid4

from .supabase_client import SupabaseClient

logger = logging.getLogger(__name__)

class MailboxOperations:
    """Database operations for mailbox management"""
    
    def __init__(self, use_service_key: bool = True):
        """
        Initialize mailbox operations
        
        Args:
            use_service_key: Use service role key for write operations
        """
        self.client = SupabaseClient.get_client(use_service_key=use_service_key)
    
    def create_mailbox(
        self, 
        name: str, 
        email_address: str, 
        mailbox_type: str, 
        connection_config: Dict = None
    ) -> str:
        """
        Create a new mailbox
        
        Args:
            name: Display name for the mailbox
            email_address: Email address (must be unique)
            mailbox_type: Type of mailbox (outlook, mbox, imap, pop3)
            connection_config: Optional connection configuration
            
        Returns:
            Mailbox ID (UUID)
        """
        try:
            mailbox_id = str(uuid4())
            
            mailbox_data = {
                'id': mailbox_id,
                'name': name,
                'email_address': email_address.lower().strip(),
                'mailbox_type': mailbox_type,
                'connection_config': connection_config or {},
                'is_active': True,
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            
            result = self.client.table('mailboxes').insert(mailbox_data).execute()
            
            if result.data:
                logger.info(f"Created mailbox: {name} ({email_address}) with ID: {mailbox_id}")
                
                # Create default folders for this mailbox
                self.create_default_folders(mailbox_id)
                
                return mailbox_id
            else:
                raise RuntimeError("No data returned from mailbox creation")
                
        except Exception as e:
            logger.error(f"Failed to create mailbox {email_address}: {e}")
            raise
    
    def get_mailbox_by_email(self, email_address: str) -> Optional[Dict]:
        """
        Retrieve mailbox by email address
        
        Args:
            email_address: Email address to search for
            
        Returns:
            Mailbox data or None if not found
        """
        try:
            result = self.client.table('mailboxes')\
                .select('*')\
                .eq('email_address', email_address.lower().strip())\
                .execute()
            
            if result.data:
                return result.data[0]
            return None
            
        except Exception as e:
            logger.error(f"Failed to get mailbox {email_address}: {e}")
            return None
    
    def get_mailbox_by_id(self, mailbox_id: str) -> Optional[Dict]:
        """
        Retrieve mailbox by ID
        
        Args:
            mailbox_id: Mailbox UUID
            
        Returns:
            Mailbox data or None if not found
        """
        try:
            result = self.client.table('mailboxes')\
                .select('*')\
                .eq('id', mailbox_id)\
                .execute()
            
            if result.data:
                return result.data[0]
            return None
            
        except Exception as e:
            logger.error(f"Failed to get mailbox {mailbox_id}: {e}")
            return None
    
    def list_mailboxes(self, active_only: bool = True) -> List[Dict]:
        """
        List all mailboxes
        
        Args:
            active_only: Only return active mailboxes
            
        Returns:
            List of mailbox data
        """
        try:
            query = self.client.table('mailboxes').select('*')
            
            if active_only:
                query = query.eq('is_active', True)
            
            result = query.order('created_at').execute()
            
            return result.data or []
            
        except Exception as e:
            logger.error(f"Failed to list mailboxes: {e}")
            return []
    
    def update_mailbox_sync_time(self, mailbox_id: str):
        """
        Update the last sync time for a mailbox
        
        Args:
            mailbox_id: Mailbox UUID
        """
        try:
            update_data = {
                'last_sync_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            
            self.client.table('mailboxes')\
                .update(update_data)\
                .eq('id', mailbox_id)\
                .execute()
            
            logger.debug(f"Updated sync time for mailbox {mailbox_id}")
            
        except Exception as e:
            logger.error(f"Failed to update sync time for mailbox {mailbox_id}: {e}")
    
    def update_mailbox_email_count(self, mailbox_id: str, count: int):
        """
        Update the total email count for a mailbox
        
        Args:
            mailbox_id: Mailbox UUID
            count: Total email count
        """
        try:
            update_data = {
                'total_emails': count,
                'updated_at': datetime.now().isoformat()
            }
            
            self.client.table('mailboxes')\
                .update(update_data)\
                .eq('id', mailbox_id)\
                .execute()
            
            logger.debug(f"Updated email count for mailbox {mailbox_id}: {count}")
            
        except Exception as e:
            logger.error(f"Failed to update email count for mailbox {mailbox_id}: {e}")
    
    def deactivate_mailbox(self, mailbox_id: str):
        """
        Deactivate a mailbox (soft delete)
        
        Args:
            mailbox_id: Mailbox UUID
        """
        try:
            update_data = {
                'is_active': False,
                'updated_at': datetime.now().isoformat()
            }
            
            self.client.table('mailboxes')\
                .update(update_data)\
                .eq('id', mailbox_id)\
                .execute()
            
            logger.info(f"Deactivated mailbox {mailbox_id}")
            
        except Exception as e:
            logger.error(f"Failed to deactivate mailbox {mailbox_id}: {e}")
            raise
    
    def create_default_folders(self, mailbox_id: str):
        """
        Create default folders for a new mailbox
        
        Args:
            mailbox_id: Mailbox UUID
        """
        try:
            default_folders = [
                ('INBOX', 'inbox'),
                ('Sent', 'sent'),
                ('Drafts', 'drafts'),
                ('Trash', 'trash'),
                ('Spam', 'spam'),
                ('Archive', 'archive')
            ]
            
            folders_data = []
            for folder_path, folder_type in default_folders:
                folders_data.append({
                    'id': str(uuid4()),
                    'folder_path': folder_path,
                    'mailbox_id': mailbox_id,
                    'folder_type': folder_type,
                    'message_count': 0,
                    'created_at': datetime.now().isoformat()
                })
            
            result = self.client.table('folders').insert(folders_data).execute()
            
            if result.data:
                logger.info(f"Created {len(folders_data)} default folders for mailbox {mailbox_id}")
            else:
                logger.warning(f"Failed to create default folders for mailbox {mailbox_id}")
                
        except Exception as e:
            logger.error(f"Failed to create default folders for mailbox {mailbox_id}: {e}")
            raise
    
    def get_or_create_mailbox(
        self, 
        email_address: str, 
        mailbox_type: str, 
        name: str = None,
        connection_config: Dict = None
    ) -> str:
        """
        Get existing mailbox or create new one
        
        Args:
            email_address: Email address
            mailbox_type: Type of mailbox
            name: Optional display name (defaults to email)
            connection_config: Optional connection configuration
            
        Returns:
            Mailbox ID (UUID)
        """
        # Try to get existing mailbox
        existing = self.get_mailbox_by_email(email_address)
        
        if existing:
            logger.info(f"Using existing mailbox: {existing['name']} ({email_address})")
            return existing['id']
        
        # Create new mailbox
        display_name = name or email_address
        logger.info(f"Creating new mailbox: {display_name} ({email_address})")
        
        return self.create_mailbox(
            name=display_name,
            email_address=email_address,
            mailbox_type=mailbox_type,
            connection_config=connection_config
        )
    
    def get_mailbox_stats(self, mailbox_id: str) -> Dict:
        """
        Get statistics for a specific mailbox
        
        Args:
            mailbox_id: Mailbox UUID
            
        Returns:
            Dictionary with mailbox statistics
        """
        try:
            # Get basic mailbox info
            mailbox = self.get_mailbox_by_id(mailbox_id)
            if not mailbox:
                return {}
            
            # Get email count
            email_result = self.client.table('emails')\
                .select('count')\
                .eq('mailbox_id', mailbox_id)\
                .execute()
            
            email_count = email_result.count or 0
            
            # Get folder count
            folder_result = self.client.table('folders')\
                .select('count')\
                .eq('mailbox_id', mailbox_id)\
                .execute()
            
            folder_count = folder_result.count or 0
            
            # Get date range
            date_result = self.client.table('emails')\
                .select('sent_date')\
                .eq('mailbox_id', mailbox_id)\
                .order('sent_date', desc=False)\
                .limit(1)\
                .execute()
            
            earliest_date = None
            if date_result.data:
                earliest_date = date_result.data[0].get('sent_date')
            
            latest_result = self.client.table('emails')\
                .select('sent_date')\
                .eq('mailbox_id', mailbox_id)\
                .order('sent_date', desc=True)\
                .limit(1)\
                .execute()
            
            latest_date = None
            if latest_result.data:
                latest_date = latest_result.data[0].get('sent_date')
            
            return {
                'mailbox_id': mailbox_id,
                'name': mailbox['name'],
                'email_address': mailbox['email_address'],
                'mailbox_type': mailbox['mailbox_type'],
                'is_active': mailbox['is_active'],
                'total_emails': email_count,
                'folder_count': folder_count,
                'earliest_date': earliest_date,
                'latest_date': latest_date,
                'last_sync_at': mailbox.get('last_sync_at'),
                'created_at': mailbox.get('created_at')
            }
            
        except Exception as e:
            logger.error(f"Failed to get mailbox stats for {mailbox_id}: {e}")
            return {}