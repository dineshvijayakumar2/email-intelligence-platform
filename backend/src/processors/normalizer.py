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

        # Determine is_outbound first (needed for folder inference)
        is_outbound = self._determine_outbound(raw_email)

        # Clean basic fields
        sender_email = self._clean_email(raw_email.get('sender_email', ''))
        recipients = self._clean_recipients(raw_email.get('recipients', []))
        subject = self._clean_subject(raw_email.get('subject', ''))
        body_text = self._clean_body_text(raw_email.get('body_text', ''))

        # Infer or normalize folder path
        folder_path = self._infer_folder_path(
            provided_folder=raw_email.get('folder_path'),
            is_outbound=is_outbound,
            sender_email=sender_email,
            recipients=recipients,
            subject=subject,
            body_text=body_text
        )

        normalized = {
            'message_id': self._clean_message_id(raw_email.get('message_id')),
            'thread_id': self._determine_thread_id(raw_email),
            'folder_path': folder_path,
            'sender_email': sender_email,
            'sender_name': self._clean_text(raw_email.get('sender_name', '')),
            'recipients': recipients,
            'cc_list': self._clean_recipients(raw_email.get('cc_list', [])),
            'bcc_list': self._clean_recipients(raw_email.get('bcc_list', [])),
            'subject': subject,
            'body_text': body_text,
            'body_html': raw_email.get('body_html', ''),
            'sent_date': raw_email.get('sent_date'),
            'received_date': raw_email.get('received_date'),
            'is_outbound': is_outbound,
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
        """
        Normalize folder path to consistent proper case

        Converts various folder name formats to standard names:
        - INBOX/inbox → Inbox
        - SENT/sent/Sent Items → Sent
        - SPAM/spam/Junk → Spam
        etc.
        """
        if not folder_path:
            return 'Inbox'

        # Handle common folder name variations (case-insensitive)
        folder_map = {
            # Inbox variations
            'inbox': 'Inbox',
            'mail': 'Inbox',

            # Sent variations
            'sent': 'Sent',
            'sent items': 'Sent',
            'sent mail': 'Sent',
            'outbox': 'Sent',

            # Archive variations
            'archive': 'Archive',
            'archived': 'Archive',
            'all mail': 'Archive',

            # Trash variations
            'trash': 'Trash',
            'deleted': 'Trash',
            'deleted items': 'Trash',

            # Spam variations
            'spam': 'Spam',
            'junk': 'Spam',
            'junk email': 'Spam',
            'junk e-mail': 'Spam',

            # Draft variations
            'draft': 'Drafts',
            'drafts': 'Drafts',

            # Other common Gmail labels
            'important': 'Important',
            'starred': 'Starred',
            'muted': 'Muted',
            'snoozed': 'Snoozed',
            'chats': 'Chats',
        }

        normalized = folder_path.strip()
        lower_folder = normalized.lower()

        # Return mapped folder or keep original with proper capitalization
        mapped = folder_map.get(lower_folder)
        if mapped:
            return mapped

        # If not in map, return original with first letter capitalized
        return normalized

    def _infer_folder_path(self, provided_folder: str, is_outbound: bool,
                           sender_email: str, recipients: List[Dict],
                           subject: str, body_text: str) -> str:
        """
        Universal folder inference for all mailbox formats

        Priority:
        1. If folder provided by extractor (PST/OLM/Gmail labels) → use it
        2. If no folder or generic placeholder → infer from email characteristics

        Args:
            provided_folder: Folder from extractor (may be None or generic)
            is_outbound: Whether email was sent by user
            sender_email: Sender email address
            recipients: List of recipients
            subject: Email subject
            body_text: Email body text

        Returns:
            Normalized folder path (never returns generic placeholders)
        """
        # Generic placeholders that should trigger inference
        generic_folders = ['MBOX Archive', 'Archive', 'Unknown', '', None, 'INBOX']

        # If extractor provided a real folder (not generic), normalize and use it
        if provided_folder and provided_folder not in generic_folders:
            normalized = self._normalize_folder_path(provided_folder)
            logger.debug(f"Using provided folder: {provided_folder} → {normalized}")
            return normalized

        # Otherwise, infer folder from email characteristics
        # This handles: generic MBOX, missing folder data, unknown sources
        logger.debug(f"Inferring folder for email (provided: {provided_folder}, outbound: {is_outbound})")

        # 1. Check if outbound (sent by user)
        if is_outbound:
            # Check if it's a draft (no recipients or very incomplete)
            if not recipients or len(recipients) == 0:
                logger.debug("  → Inferred: Drafts (no recipients)")
                return 'Drafts'
            else:
                logger.debug("  → Inferred: Sent (outbound email)")
                return 'Sent'

        # 2. Check for spam indicators
        spam_indicators = [
            'viagra', 'cialis', 'lottery', 'winner', 'nigerian prince',
            'click here now', 'limited time offer', 'act now',
            'you have won', 'claim your prize', 'free money'
        ]
        subject_lower = subject.lower() if subject else ''
        body_lower = body_text.lower()[:1000] if body_text else ''

        if any(indicator in subject_lower or indicator in body_lower
               for indicator in spam_indicators):
            logger.debug("  → Inferred: Spam (spam indicators found)")
            return 'Spam'

        # Check for all caps subject (common spam indicator)
        if subject and len(subject) > 10 and subject.isupper():
            logger.debug("  → Inferred: Spam (all caps subject)")
            return 'Spam'

        # 3. Check for system/automated emails → could be in Updates/Notifications
        system_senders = ['noreply@', 'no-reply@', 'donotreply@', 'automated@',
                         'system@', 'notification@']
        if sender_email and any(sender_email.startswith(sender) for sender in system_senders):
            logger.debug("  → Inferred: Inbox (system sender)")
            return 'Inbox'

        # 4. Default: Inbox for received emails
        logger.debug("  → Inferred: Inbox (default)")
        return 'Inbox'

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