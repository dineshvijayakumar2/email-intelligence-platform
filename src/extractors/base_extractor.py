from abc import ABC, abstractmethod
from typing import Iterator, Dict, Optional, List
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class BaseExtractor(ABC):
    """Abstract base class for email extractors"""
    
    def __init__(self, connection_config: Dict):
        """
        Initialize extractor with connection configuration
        
        Args:
            connection_config: Configuration for connecting to email source
        """
        self.config = connection_config
        self.stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'start_time': None,
            'end_time': None
        }
    
    @abstractmethod
    def connect(self) -> bool:
        """Connect to email source"""
        pass
    
    @abstractmethod
    def extract_emails(
        self, 
        folder_name: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        max_emails: Optional[int] = None
    ) -> Iterator[Dict]:
        """
        Extract emails and yield as dictionaries
        
        Args:
            folder_name: Specific folder to extract from (None for all)
            date_from: Extract emails from this date
            date_to: Extract emails until this date
            max_emails: Maximum number of emails to extract
            
        Yields:
            Dict: Email data in standardized format
        """
        pass
    
    @abstractmethod
    def get_folders(self) -> List[Dict]:
        """Get list of available folders"""
        pass
    
    @abstractmethod
    def disconnect(self):
        """Clean up connection"""
        pass
    
    def get_stats(self) -> Dict:
        """Return extraction statistics"""
        return self.stats
    
    def _standardize_email(self, raw_email: Dict) -> Dict:
        """
        Standardize email format across different extractors
        
        Returns standardized email dict with fields:
        - message_id, subject, sender_email, sender_name
        - recipients, cc_list, bcc_list
        - sent_date, received_date
        - body_text, body_html
        - folder_path, is_outbound, is_reply
        - raw_headers, message_size
        """
        return {
            'message_id': raw_email.get('message_id', ''),
            'subject': raw_email.get('subject', ''),
            'sender_email': self._clean_email(raw_email.get('sender_email', '')),
            'sender_name': raw_email.get('sender_name', ''),
            'recipients': self._normalize_recipients(raw_email.get('recipients', [])),
            'cc_list': self._normalize_recipients(raw_email.get('cc_list', [])),
            'bcc_list': self._normalize_recipients(raw_email.get('bcc_list', [])),
            'sent_date': raw_email.get('sent_date'),
            'received_date': raw_email.get('received_date'),
            'body_text': raw_email.get('body_text', ''),
            'body_html': raw_email.get('body_html', ''),
            'folder_path': raw_email.get('folder_path', 'INBOX'),
            'is_outbound': raw_email.get('is_outbound', False),
            'is_reply': raw_email.get('is_reply', False),
            'raw_headers': raw_email.get('raw_headers', {}),
            'message_size': len(raw_email.get('body_text', ''))
        }
    
    def _clean_email(self, email: str) -> str:
        """Clean and normalize email address"""
        return email.lower().strip() if email else ''
    
    def _normalize_recipients(self, recipients) -> List[Dict]:
        """Normalize recipients to standard format"""
        if not recipients:
            return []
        
        if isinstance(recipients, str):
            return [{'email': self._clean_email(recipients), 'name': ''}]
        
        normalized = []
        for recipient in recipients:
            if isinstance(recipient, str):
                normalized.append({
                    'email': self._clean_email(recipient),
                    'name': ''
                })
            elif isinstance(recipient, dict):
                normalized.append({
                    'email': self._clean_email(recipient.get('email', '')),
                    'name': recipient.get('name', '')
                })
        
        return normalized
    
    def _update_stats(self, success: bool, error: str = None):
        """Update extraction statistics"""
        self.stats['total'] += 1
        if success:
            self.stats['success'] += 1
        else:
            self.stats['failed'] += 1
            if error:
                logger.error(f"Extraction error: {error}")