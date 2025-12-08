from datetime import datetime
from typing import Dict, Optional, List
import logging
import re

logger = logging.getLogger(__name__)

class EmailNormalizer:
    """Normalize and clean email data"""
    
    def __init__(self, user_domains: List[str] = None, user_emails: List[str] = None):
        """
        Initialize normalizer
        
        Args:
            user_domains: List of user's domains for outbound detection
            user_emails: List of user's email addresses for outbound detection
        """
        self.user_domains = user_domains or []
        self.user_emails = [email.lower() for email in (user_emails or [])]
    
    def normalize(self, raw_email: Dict) -> Dict:
        """Normalize raw email data"""
        
        normalized = {
            'message_id': self._clean_message_id(raw_email.get('message_id')),
            'thread_id': self._determine_thread_id(raw_email),
            'folder_path': self._normalize_folder_path(raw_email.get('folder_path', 'INBOX')),
            'sender_email': self._clean_email(raw_email.get('sender_email', '')),
            'sender_name': self._clean_text(raw_email.get('sender_name', '')),
            'recipients': self._clean_recipients(raw_email.get('recipients', [])),
            'cc_list': self._clean_recipients(raw_email.get('cc_list', [])),
            'bcc_list': self._clean_recipients(raw_email.get('bcc_list', [])),
            'subject': self._clean_subject(raw_email.get('subject', '')),
            'body_text': self._clean_body_text(raw_email.get('body_text', '')),
            'body_html': raw_email.get('body_html', ''),
            'sent_date': raw_email.get('sent_date'),
            'received_date': raw_email.get('received_date'),
            'is_outbound': self._determine_outbound(raw_email),
            'is_reply': self._determine_reply(raw_email),
            'message_size': self._calculate_size(raw_email),
            'raw_headers': raw_email.get('raw_headers', {})
        }
        
        return normalized
    
    def _clean_message_id(self, message_id: str) -> str:
        """Clean and validate message ID"""
        if not message_id:
            return ''
        
        # Remove angle brackets and whitespace
        clean_id = message_id.strip('<>').strip()
        
        # Ensure UTF-8 compatibility
        try:
            clean_id.encode('utf-8')
            return clean_id
        except UnicodeEncodeError:
            # Replace problematic characters
            return clean_id.encode('utf-8', errors='replace').decode('utf-8')
    
    def _determine_thread_id(self, email: Dict) -> str:
        """Determine thread ID from message headers"""
        # Check References header first (most reliable)
        headers = email.get('raw_headers', {})
        references = headers.get('References', '')
        
        if references:
            # Get the first (root) message ID from references
            root_match = re.search(r'<([^>]+)>', references)
            if root_match:
                return root_match.group(1)
        
        # Fall back to In-Reply-To
        in_reply_to = headers.get('In-Reply-To', '')
        if in_reply_to:
            return in_reply_to.strip('<>')
        
        # This email starts a new thread
        return self._clean_message_id(email.get('message_id', ''))
    
    def _normalize_folder_path(self, folder_path: str) -> str:
        """Normalize folder path"""
        if not folder_path:
            return 'INBOX'
        
        # Handle common folder name variations
        folder_map = {
            'inbox': 'INBOX',
            'sent items': 'Sent',
            'sent mail': 'Sent', 
            'outbox': 'Sent',
            'deleted items': 'Trash',
            'junk email': 'Spam',
            'spam': 'Spam',
            'drafts': 'Drafts'
        }
        
        normalized = folder_path.strip()
        lower_folder = normalized.lower()
        
        return folder_map.get(lower_folder, normalized)
    
    def _clean_email(self, email: str) -> str:
        """Clean and validate email address"""
        if not email:
            return ''
        
        email = email.lower().strip()
        
        # Basic email validation
        if '@' not in email:
            return ''
        
        # Remove any surrounding quotes or brackets
        email = email.strip('"\'<>')
        
        # Ensure UTF-8 compatibility
        try:
            email.encode('utf-8')
            return email
        except UnicodeEncodeError:
            return email.encode('utf-8', errors='replace').decode('utf-8')
    
    def _clean_text(self, text: str) -> str:
        """Clean text field with UTF-8 preservation"""
        if not text:
            return ''
        
        # Remove excessive whitespace
        cleaned = re.sub(r'\s+', ' ', text.strip())
        
        # Ensure UTF-8 compatibility
        try:
            cleaned.encode('utf-8')
            return cleaned
        except UnicodeEncodeError:
            return cleaned.encode('utf-8', errors='replace').decode('utf-8')
    
    def _clean_recipients(self, recipients: List[Dict]) -> List[Dict]:
        """Clean recipient list"""
        cleaned = []
        
        for recipient in recipients:
            if not isinstance(recipient, dict):
                continue
            
            email = self._clean_email(recipient.get('email', ''))
            name = self._clean_text(recipient.get('name', ''))
            
            if email:  # Only include if email is valid
                cleaned.append({
                    'email': email,
                    'name': name
                })
        
        return cleaned
    
    def _clean_subject(self, subject: str) -> str:
        """Clean email subject"""
        if not subject:
            return ''
        
        # Remove excessive whitespace and line breaks
        cleaned = re.sub(r'\s+', ' ', subject.strip())
        cleaned = re.sub(r'[\r\n]+', ' ', cleaned)
        
        # Limit length for database storage
        if len(cleaned) > 998:  # Leave room for encoding
            cleaned = cleaned[:995] + '...'
        
        return self._clean_text(cleaned)
    
    def _clean_body_text(self, body: str) -> str:
        """Clean email body text"""
        if not body:
            return ''
        
        # Remove excessive whitespace but preserve structure
        cleaned = re.sub(r'\n{3,}', '\n\n', body)
        cleaned = re.sub(r'[ \t]{2,}', ' ', cleaned)
        cleaned = re.sub(r'[\r]+', '', cleaned)
        
        # Ensure UTF-8 compatibility
        try:
            cleaned.encode('utf-8')
            return cleaned.strip()
        except UnicodeEncodeError:
            return cleaned.encode('utf-8', errors='replace').decode('utf-8').strip()
    
    def _determine_outbound(self, email: Dict) -> bool:
        """Determine if email is outbound"""
        sender_email = email.get('sender_email', '').lower()
        folder_path = email.get('folder_path', '')
        
        # Check folder name first
        outbound_folders = ['sent', 'sent items', 'sent mail', 'outbox']
        if folder_path.lower() in outbound_folders:
            return True
        
        # Check if sender is user
        if sender_email in self.user_emails:
            return True
        
        # Check sender domain
        if self.user_domains:
            for domain in self.user_domains:
                if sender_email.endswith(f'@{domain.lower()}'):
                    return True
        
        return False
    
    def _determine_reply(self, email: Dict) -> bool:
        """Determine if email is a reply"""
        subject = email.get('subject', '').lower()
        headers = email.get('raw_headers', {})
        
        # Check subject prefixes
        reply_prefixes = ['re:', 're ', 'aw:', 'aw ', 'fwd:', 'fw:']
        if any(subject.startswith(prefix) for prefix in reply_prefixes):
            return True
        
        # Check for reply headers
        if headers.get('In-Reply-To') or headers.get('References'):
            return True
        
        return False
    
    def _calculate_size(self, email: Dict) -> int:
        """Calculate email size in bytes"""
        body_text = email.get('body_text', '')
        body_html = email.get('body_html', '')
        subject = email.get('subject', '')
        
        # Calculate UTF-8 encoded size
        try:
            size = len(body_text.encode('utf-8'))
            size += len(body_html.encode('utf-8'))
            size += len(subject.encode('utf-8'))
            return size
        except UnicodeEncodeError:
            # Fallback to character count
            return len(body_text) + len(body_html) + len(subject)
    
    def validate_normalized_email(self, email: Dict) -> bool:
        """Validate that normalized email has required fields"""
        required_fields = ['message_id', 'sender_email', 'subject']
        
        for field in required_fields:
            if not email.get(field):
                logger.warning(f"Missing required field: {field}")
                return False
        
        # Validate email format
        sender = email.get('sender_email', '')
        if sender and '@' not in sender:
            logger.warning(f"Invalid sender email: {sender}")
            return False
        
        return True