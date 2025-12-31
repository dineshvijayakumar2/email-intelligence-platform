"""
Email Tagging System - Basic Attributes

Tags emails with fundamental attributes that are useful for filtering,
search, and analytics. These are fast, deterministic tags based on
email metadata and content patterns.
"""

from typing import Dict, List, Set
import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class EmailTagger:
    """
    Tag emails with basic attributes for filtering and analytics

    Tags are simpler than categories - they're binary attributes
    that can overlap (an email can have multiple tags).
    """

    def __init__(self):
        """Initialize tagging rules"""
        self.spam_indicators = self._load_spam_indicators()
        self.marketing_indicators = self._load_marketing_indicators()
        self.system_domains = self._load_system_domains()

    def tag_email(self, email: Dict) -> Dict[str, any]:
        """
        Tag email with basic attributes

        Args:
            email: Normalized email dict with standard fields

        Returns:
            Dict with tags and metadata:
            {
                'tags': ['inbound', 'new_thread', 'marketing', ...],
                'is_spam': bool,
                'is_marketing': bool,
                'is_system': bool,
                'is_automated': bool,
                'thread_type': 'new' | 'reply' | 'forward',
                'folder_category': 'inbox' | 'sent' | 'spam' | 'trash' | 'archive' | 'other',
                'sender_type': 'human' | 'system' | 'automated' | 'marketing',
                'priority_score': int (0-10)
            }
        """

        tags = []
        metadata = {}

        # Direction tags (inbound/outbound)
        direction_tag = self._tag_direction(email)
        tags.append(direction_tag)

        # Thread type tags (new/reply/forward)
        thread_type = self._tag_thread_type(email)
        tags.append(thread_type)
        metadata['thread_type'] = thread_type

        # Folder category
        folder_category = self._tag_folder(email)
        tags.append(folder_category)
        metadata['folder_category'] = folder_category

        # Spam detection
        is_spam, spam_reason = self._detect_spam(email)
        if is_spam:
            tags.append('spam')
        metadata['is_spam'] = is_spam
        metadata['spam_reason'] = spam_reason

        # Marketing detection
        is_marketing, marketing_signals = self._detect_marketing(email)
        if is_marketing:
            tags.append('marketing')
        metadata['is_marketing'] = is_marketing
        metadata['marketing_signals'] = marketing_signals

        # System/automated detection
        is_system = self._detect_system(email)
        if is_system:
            tags.append('system')
        metadata['is_system'] = is_system

        is_automated = self._detect_automated(email)
        if is_automated:
            tags.append('automated')
        metadata['is_automated'] = is_automated

        # Sender type classification
        sender_type = self._classify_sender_type(email, is_system, is_automated, is_marketing)
        tags.append(f'sender_{sender_type}')
        metadata['sender_type'] = sender_type

        # Additional useful tags
        additional_tags = self._extract_additional_tags(email)
        tags.extend(additional_tags)

        # Priority scoring (0-10)
        priority_score = self._calculate_priority_score(email, metadata)
        metadata['priority_score'] = priority_score
        if priority_score >= 7:
            tags.append('high_priority')
        elif priority_score <= 3:
            tags.append('low_priority')

        return {
            'tags': list(set(tags)),  # Remove duplicates
            **metadata
        }

    def _tag_direction(self, email: Dict) -> str:
        """Tag email direction (inbound/outbound)"""
        is_outbound = email.get('is_outbound', False)
        return 'outbound' if is_outbound else 'inbound'

    def _tag_thread_type(self, email: Dict) -> str:
        """
        Tag thread type based on subject and is_reply field

        Returns: 'new_thread', 'reply', or 'forward'
        """
        # Check is_reply field first (most reliable)
        if email.get('is_reply', False):
            return 'reply'

        # Check subject for reply/forward indicators
        subject = email.get('subject', '').strip()

        if subject.startswith('Re:') or subject.startswith('RE:'):
            return 'reply'

        if subject.startswith('Fwd:') or subject.startswith('FW:') or subject.startswith('Fw:'):
            return 'forward'

        return 'new_thread'

    def _tag_folder(self, email: Dict) -> str:
        """
        Categorize the folder where email was found

        Returns: 'inbox', 'sent', 'spam', 'trash', 'archive', 'drafts', or 'other'
        """
        folder_path = email.get('folder_path', '').lower()

        # Common folder patterns
        if 'inbox' in folder_path or folder_path == '':
            return 'inbox'
        elif 'sent' in folder_path:
            return 'sent'
        elif 'spam' in folder_path or 'junk' in folder_path:
            return 'spam'
        elif 'trash' in folder_path or 'deleted' in folder_path:
            return 'trash'
        elif 'archive' in folder_path:
            return 'archive'
        elif 'draft' in folder_path:
            return 'drafts'
        else:
            return 'other'

    def _detect_spam(self, email: Dict) -> tuple[bool, str]:
        """
        Detect if email is likely spam

        Returns: (is_spam: bool, reason: str)
        """
        sender = email.get('sender_email', '').lower()
        subject = email.get('subject', '').lower()
        body = email.get('body_text', '').lower()

        # Already in spam folder
        folder = email.get('folder_path', '').lower()
        if 'spam' in folder or 'junk' in folder:
            return (True, 'in_spam_folder')

        # Spam subject patterns
        spam_subject_patterns = [
            'congratulations! you won',
            'claim your prize',
            'nigerian prince',
            'enlarge your',
            'viagra',
            'cialis',
            'weight loss',
            'work from home',
            'make money fast',
            'click here now',
            'limited time offer',
            'act now',
            '!!!',  # Multiple exclamation marks
            '$$$'
        ]

        for pattern in spam_subject_patterns:
            if pattern in subject:
                return (True, f'spam_subject:{pattern}')

        # Suspicious sender patterns
        if re.search(r'\d{5,}', sender):  # Long numbers in sender
            return (True, 'suspicious_sender')

        # ALL CAPS subject (spam indicator)
        if subject and subject.isupper() and len(subject) > 10:
            return (True, 'all_caps_subject')

        # Excessive links in body (checking for URL patterns)
        url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
        urls = re.findall(url_pattern, body)
        if len(urls) > 10 and len(body) < 1000:  # Many links, short body
            return (True, 'excessive_links')

        # Phishing indicators
        phishing_keywords = [
            'verify your account',
            'confirm your password',
            'update your information',
            'suspend your account',
            'unusual activity',
            'click here to verify'
        ]

        for keyword in phishing_keywords:
            if keyword in body and 'unsubscribe' in body:
                # Likely phishing disguised as legitimate email
                return (True, f'phishing:{keyword}')

        return (False, None)

    def _detect_marketing(self, email: Dict) -> tuple[bool, List[str]]:
        """
        Detect marketing/promotional emails

        Returns: (is_marketing: bool, signals: List[str])
        """
        sender = email.get('sender_email', '').lower()
        subject = email.get('subject', '').lower()
        body = email.get('body_text', '').lower()

        signals = []

        # Unsubscribe link (strongest indicator)
        if 'unsubscribe' in body:
            signals.append('unsubscribe_link')

        # Marketing sender patterns
        marketing_senders = [
            'marketing@', 'promo@', 'offers@', 'deals@',
            'newsletter@', 'news@', 'hello@', 'hi@',
            'info@', 'updates@', 'notifications@'
        ]

        for pattern in marketing_senders:
            if sender.startswith(pattern):
                signals.append(f'sender:{pattern}')
                break

        # Marketing keywords in subject
        for keyword in self.marketing_indicators:
            if keyword in subject:
                signals.append(f'subject:{keyword}')

        # Marketing automation headers/footers
        footer_patterns = [
            'this email was sent to',
            'you received this email because',
            'manage your preferences',
            'update your email preferences',
            'view in browser'
        ]

        for pattern in footer_patterns:
            if pattern in body:
                signals.append(f'footer:{pattern}')
                break

        # Bulk email headers
        headers = email.get('raw_headers', {})
        if 'list-unsubscribe' in [h.lower() for h in headers.keys()]:
            signals.append('list_header')

        # Marketing = 2+ signals
        is_marketing = len(signals) >= 2

        return (is_marketing, signals)

    def _detect_system(self, email: Dict) -> bool:
        """Detect system-generated emails"""
        sender = email.get('sender_email', '').lower()
        sender_name = email.get('sender_name', '').lower()

        # System sender patterns
        system_patterns = [
            'noreply@', 'no-reply@', 'donotreply@', 'do-not-reply@',
            'system@', 'automated@', 'daemon@', 'mailer-daemon@',
            'postmaster@', 'root@'
        ]

        for pattern in system_patterns:
            if sender.startswith(pattern):
                return True

        # Known system domains
        for domain in self.system_domains:
            if domain in sender:
                return True

        # System sender names
        if 'system' in sender_name or 'automated' in sender_name:
            return True

        return False

    def _detect_automated(self, email: Dict) -> bool:
        """Detect automated emails (may not be system, but clearly automated)"""
        sender = email.get('sender_email', '').lower()
        body = email.get('body_text', '').lower()
        subject = email.get('subject', '').lower()

        # Template syntax in body (indication of automation platform)
        template_patterns = [
            r'\{\{[^}]+\}\}',  # Handlebars {{variable}}
            r'\[%[^%]+%\]',     # Liquid [% variable %]
            r'%%[^%]+%%',       # Custom %%variable%%
        ]

        for pattern in template_patterns:
            if re.search(pattern, body):
                return True

        # Common automation platform domains
        automation_platforms = [
            'mailchimp', 'constantcontact', 'sendinblue', 'sendgrid',
            'mailgun', 'mandrill', 'postmark', 'hubspot', 'salesforce',
            'marketo', 'pardot', 'eloqua'
        ]

        for platform in automation_platforms:
            if platform in sender:
                return True

        # Auto-reply indicators
        if 'auto-reply' in subject or 'automatic reply' in subject or 'out of office' in subject:
            return True

        return False

    def _classify_sender_type(self, email: Dict, is_system: bool,
                             is_automated: bool, is_marketing: bool) -> str:
        """
        Classify sender type

        Returns: 'system', 'automated', 'marketing', or 'human'
        """
        if is_system:
            return 'system'
        elif is_marketing:
            return 'marketing'
        elif is_automated:
            return 'automated'
        else:
            return 'human'

    def _extract_additional_tags(self, email: Dict) -> List[str]:
        """Extract additional useful tags"""
        tags = []

        subject = email.get('subject', '').lower()
        body = email.get('body_text', '').lower()

        # Attachments
        if email.get('has_attachments', False):
            tags.append('has_attachments')

        # Important/urgent indicators
        urgent_keywords = ['urgent', 'asap', 'important', 'critical', 'emergency', 'action required']
        if any(keyword in subject for keyword in urgent_keywords):
            tags.append('urgent')

        # Specific content types
        if 'invoice' in subject or 'receipt' in subject:
            tags.append('financial')

        if 'meeting' in subject or 'calendar' in subject or 'invite' in subject:
            tags.append('meeting')

        if 'password' in subject or 'reset' in subject or 'verify' in subject:
            tags.append('account_action')

        if 'order' in subject or 'shipping' in subject or 'delivery' in subject:
            tags.append('ecommerce')

        if 'newsletter' in subject:
            tags.append('newsletter')

        if 'notification' in subject or 'alert' in subject:
            tags.append('notification')

        # Social media indicators
        social_keywords = ['liked your', 'commented on', 'shared your', 'tagged you', 'mentioned you']
        if any(keyword in subject or keyword in body for keyword in social_keywords):
            tags.append('social_notification')

        # Size tags
        size = email.get('message_size', 0)
        if size > 1000000:  # > 1MB
            tags.append('large_email')
        elif size < 1000:  # < 1KB
            tags.append('small_email')

        return tags

    def _calculate_priority_score(self, email: Dict, metadata: Dict) -> int:
        """
        Calculate priority score (0-10)

        Higher score = higher priority
        """
        score = 5  # Start at medium priority

        subject = email.get('subject', '').lower()

        # Reduce priority for spam/marketing
        if metadata.get('is_spam'):
            score -= 5
        if metadata.get('is_marketing'):
            score -= 2

        # Reduce priority for automated/system
        if metadata.get('is_system'):
            score -= 1
        if metadata.get('is_automated'):
            score -= 1

        # Increase priority for urgent keywords
        urgent_keywords = ['urgent', 'asap', 'important', 'critical', 'emergency']
        if any(keyword in subject for keyword in urgent_keywords):
            score += 3

        # Increase priority for replies (ongoing conversation)
        if metadata.get('thread_type') == 'reply':
            score += 1

        # Increase priority for human senders
        if metadata.get('sender_type') == 'human':
            score += 2

        # Increase priority for personal (inbound, non-marketing)
        if not metadata.get('is_marketing') and not email.get('is_outbound'):
            score += 1

        # Clamp to 0-10 range
        return max(0, min(10, score))

    def _load_spam_indicators(self) -> Set[str]:
        """Load spam indicator keywords"""
        return {
            'free money', 'click here', 'act now', 'limited time',
            'congratulations', 'winner', 'prize', 'claim now',
            'risk free', 'no obligation', 'cancel anytime',
            'weight loss', 'lose weight', 'viagra', 'cialis'
        }

    def _load_marketing_indicators(self) -> Set[str]:
        """Load marketing indicator keywords"""
        return {
            'sale', 'discount', 'offer', 'deal', 'promo', 'promotion',
            'save', 'free', 'limited', 'exclusive', 'special',
            'newsletter', 'announcement', 'new product', 'launch',
            'shop now', 'buy now', 'order now', 'learn more'
        }

    def _load_system_domains(self) -> Set[str]:
        """Load known system/service domains"""
        return {
            'github.com', 'gitlab.com', 'bitbucket.org',  # Dev platforms
            'aws.amazon.com', 'azure.com', 'google.com',  # Cloud providers
            'stripe.com', 'paypal.com', 'square.com',     # Payment processors
            'slack.com', 'zoom.us', 'teams.microsoft.com', # Collaboration
            'atlassian.com', 'jira.com', 'asana.com'      # Project management
        }


# Convenience function
def tag_email(email: Dict) -> Dict[str, any]:
    """
    Quick function to tag a single email

    Usage:
        result = tag_email(email_dict)
        tags = result['tags']
        is_spam = result['is_spam']
    """
    tagger = EmailTagger()
    return tagger.tag_email(email)


# Batch tagging function
def tag_emails_batch(emails: List[Dict]) -> List[Dict]:
    """
    Tag multiple emails efficiently

    Returns list of tag results matching input order
    """
    tagger = EmailTagger()
    return [tagger.tag_email(email) for email in emails]
