from typing import List, Dict, Optional, Set
import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class IndustryStandardCategorizer:
    """Email categorization using industry standards (Gmail-like)"""
    
    # Gmail-style categories (most widely adopted standard)
    CATEGORIES = {
        'primary': 'Personal conversations and important emails',
        'social': 'Social networks, media sharing, social updates', 
        'promotions': 'Deals, offers, marketing emails',
        'updates': 'Confirmations, receipts, bills, statements',
        'forums': 'Online groups, discussion boards, mailing lists'
    }
    
    def __init__(self):
        """Initialize with industry standard rules"""
        self.social_domains = self._load_social_domains()
        self.promotional_keywords = self._load_promotional_keywords()
        self.transactional_keywords = self._load_transactional_keywords()
        self.forum_indicators = self._load_forum_indicators()
    
    def categorize(self, email: Dict) -> str:
        """
        Categorize email using Gmail-style logic
        
        Returns single primary category (Gmail approach)
        """
        # Check in order of specificity (most specific first)
        
        # 1. Forums/Mailing Lists (highest specificity)
        if self._is_forum(email):
            return 'forums'
        
        # 2. Social Networks  
        if self._is_social(email):
            return 'social'
        
        # 3. Promotions/Marketing
        if self._is_promotional(email):
            return 'promotions'
        
        # 4. Updates/Transactional
        if self._is_update(email):
            return 'updates'
        
        # 5. Default to Primary (personal/conversation)
        return 'primary'
    
    def _is_social(self, email: Dict) -> bool:
        """Detect social network emails"""
        sender = email.get('sender_email', '').lower()
        subject = email.get('subject', '').lower()
        
        # Social media domains
        for domain in self.social_domains:
            if domain in sender:
                return True
        
        # Social keywords in subject
        social_keywords = [
            'notification', 'tagged you', 'mentioned you', 'friend request',
            'connection request', 'liked your', 'commented on', 'shared',
            'follow', 'message from', 'activity on'
        ]
        
        return any(keyword in subject for keyword in social_keywords)
    
    def _is_promotional(self, email: Dict) -> bool:
        """Detect promotional/marketing emails"""
        sender = email.get('sender_email', '').lower()
        subject = email.get('subject', '').lower()
        body = email.get('body_text', '').lower()
        
        # Check for unsubscribe link (strong indicator)
        if 'unsubscribe' in body:
            return True
        
        # Marketing keywords in subject
        for keyword in self.promotional_keywords:
            if keyword in subject:
                return True
        
        # Promotional sender patterns
        promo_senders = ['marketing@', 'promo@', 'offers@', 'deals@', 'newsletter@']
        if any(pattern in sender for pattern in promo_senders):
            return True
        
        return False
    
    def _is_update(self, email: Dict) -> bool:
        """Detect updates/transactional emails"""
        sender = email.get('sender_email', '').lower()
        subject = email.get('subject', '').lower()
        
        # No-reply senders (often transactional)
        if any(pattern in sender for pattern in ['noreply', 'no-reply', 'donotreply']):
            # Check if it's transactional, not promotional
            for keyword in self.transactional_keywords:
                if keyword in subject:
                    return True
        
        # Transactional keywords
        for keyword in self.transactional_keywords:
            if keyword in subject:
                return True
        
        return False
    
    def _is_forum(self, email: Dict) -> bool:
        """Detect forum/mailing list emails"""
        sender = email.get('sender_email', '').lower()
        subject = email.get('subject', '').lower()
        headers = email.get('raw_headers', {})
        
        # Mailing list headers
        list_headers = ['list-id', 'list-unsubscribe', 'mailing-list']
        if any(header in headers for header in list_headers):
            return True
        
        # Forum indicators
        for indicator in self.forum_indicators:
            if indicator in subject or indicator in sender:
                return True
        
        return False
    
    def _load_social_domains(self) -> Set[str]:
        """Load known social media domains"""
        return {
            'facebook.com', 'facebookmail.com',
            'twitter.com', 'x.com',
            'linkedin.com', 'linkedinmail.com',
            'instagram.com', 'instagrammail.com',
            'youtube.com', 'youtubemail.com',
            'tiktok.com', 'tiktokmail.com',
            'snapchat.com', 'snapchatmail.com',
            'discord.com', 'discordmail.com',
            'reddit.com', 'redditmail.com',
            'pinterest.com', 'pinterestmail.com',
            'whatsapp.com', 'telegram.org'
        }
    
    def _load_promotional_keywords(self) -> Set[str]:
        """Load promotional keywords (based on Gmail's filters)"""
        return {
            # Deals & Offers
            'sale', 'discount', 'offer', 'deal', 'promotion', 'promo',
            'special', 'limited time', 'exclusive', 'save', 'free',
            
            # Marketing terms
            'newsletter', 'marketing', 'campaign', 'announcement',
            'new product', 'launch', 'introducing',
            
            # Call to action
            'shop now', 'buy now', 'order now', 'click here',
            'learn more', 'get started', 'sign up',
            
            # Urgency
            'expires', 'hurry', 'act now', 'limited', 'today only',
            'don\'t miss', 'last chance'
        }
    
    def _load_transactional_keywords(self) -> Set[str]:
        """Load transactional/update keywords"""
        return {
            # Financial
            'receipt', 'invoice', 'payment', 'billing', 'statement',
            'charge', 'refund', 'transaction',
            
            # Orders & Shipping
            'order', 'shipping', 'delivery', 'tracking', 'shipped',
            'confirmed', 'confirmation', 'processed',
            
            # Account related
            'password', 'reset', 'verify', 'verification', 'activation',
            'account', 'security', 'login', 'sign in',
            
            # Service updates
            'alert', 'notification', 'update', 'reminder', 'due',
            'renewed', 'expired', 'subscription'
        }
    
    def _load_forum_indicators(self) -> Set[str]:
        """Load forum/mailing list indicators"""
        return {
            # Mailing list patterns
            '[list]', '[forum]', '[group]', '[community]',
            
            # Common forum subjects
            'digest', 'weekly digest', 'forum post', 'new topic',
            'reply to:', 'discussion', 'thread',
            
            # Mailing list domains
            'groups.google.com', 'yahoogroups.com', 'mailman',
            'listserv', 'majordomo'
        }


class OutlookStyleCategorizer:
    """Outlook-style focused inbox categorization"""
    
    def categorize(self, email: Dict, user_contacts: Set[str] = None) -> Dict:
        """
        Categorize using Outlook's Focused/Other approach
        
        Returns:
            Dict with 'focused' boolean and reasoning
        """
        user_contacts = user_contacts or set()
        
        sender = email.get('sender_email', '').lower()
        subject = email.get('subject', '').lower()
        body = email.get('body_text', '').lower()
        
        # Focused if from known contacts
        if sender in user_contacts:
            return {'focused': True, 'reason': 'known_contact'}
        
        # Not focused if obviously promotional
        if 'unsubscribe' in body:
            return {'focused': False, 'reason': 'promotional'}
        
        # Not focused if automated
        if any(term in sender for term in ['noreply', 'no-reply', 'automated']):
            return {'focused': False, 'reason': 'automated'}
        
        # Focused if personal conversation indicators
        personal_indicators = ['re:', 'fwd:', 'thanks', 'please', 'question']
        if any(indicator in subject for indicator in personal_indicators):
            return {'focused': True, 'reason': 'personal_conversation'}
        
        # Default to Other (not focused)
        return {'focused': False, 'reason': 'default'}


class AppleMailCategorizer:
    """Apple Mail VIP/Priority categorization"""
    
    def __init__(self, vip_contacts: Set[str] = None):
        """Initialize with VIP contact list"""
        self.vip_contacts = vip_contacts or set()
    
    def categorize(self, email: Dict) -> Dict:
        """
        Categorize using Apple Mail approach
        
        Returns:
            Dict with priority level and VIP status
        """
        sender = email.get('sender_email', '').lower()
        
        # VIP status
        is_vip = sender in self.vip_contacts
        
        # Priority based on content
        priority = self._calculate_priority(email)
        
        return {
            'is_vip': is_vip,
            'priority': priority,
            'flagged': False  # Would be set by user action
        }
    
    def _calculate_priority(self, email: Dict) -> str:
        """Calculate email priority (high/normal/low)"""
        subject = email.get('subject', '').lower()
        
        # High priority indicators
        high_priority = ['urgent', 'asap', 'important', 'critical', 'emergency']
        if any(term in subject for term in high_priority):
            return 'high'
        
        # Low priority indicators  
        low_priority = ['newsletter', 'digest', 'notification', 'automated']
        if any(term in subject for term in low_priority):
            return 'low'
        
        return 'normal'


# Usage example:
def categorize_with_industry_standards(email: Dict, style: str = 'gmail') -> Dict:
    """
    Categorize email using specified industry standard
    
    Args:
        email: Email data
        style: 'gmail', 'outlook', 'apple', or 'automation'
    """
    if style == 'gmail':
        categorizer = IndustryStandardCategorizer()
        category = categorizer.categorize(email)
        return {
            'category': category,
            'system': 'gmail',
            'confidence': 0.8
        }
    
    elif style == 'outlook':
        categorizer = OutlookStyleCategorizer()
        result = categorizer.categorize(email)
        return {
            'category': 'focused' if result['focused'] else 'other',
            'system': 'outlook',
            'reason': result['reason'],
            'confidence': 0.85
        }
    
    elif style == 'apple':
        categorizer = AppleMailCategorizer()
        result = categorizer.categorize(email)
        return {
            'category': 'vip' if result['is_vip'] else result['priority'],
            'system': 'apple',
            'is_vip': result['is_vip'],
            'priority': result['priority'],
            'confidence': 0.9 if result['is_vip'] else 0.7
        }
    
    elif style == 'automation':
        from .automation_categorizer import categorize_for_automation
        return categorize_for_automation(email)
    
    else:
        raise ValueError(f"Unknown categorization style: {style}")