from typing import List, Dict, Optional, Set, Tuple
import re
import logging
from datetime import datetime

from ..utils.domain_parser import is_noreply_address

logger = logging.getLogger(__name__)

class EmailAutomationCategorizer:
    """
    Email categorization using automation/business intelligence standards
    Based on popular tools like Mailchimp, HubSpot, Salesforce, etc.
    """
    
    # Standard automation categories used across platforms
    AUTOMATION_CATEGORIES = {
        # Engagement-based categories
        'transactional': 'System-generated emails (receipts, confirmations, alerts)',
        'promotional': 'Marketing campaigns and promotional content',
        'behavioral': 'Triggered by user actions (abandoned cart, welcome series)',
        'nurture': 'Educational content and relationship building',
        'retention': 'Re-engagement and win-back campaigns',
        
        # Business function categories  
        'sales': 'Sales outreach, proposals, follow-ups',
        'support': 'Customer service and technical support',
        'onboarding': 'User activation and getting-started sequences',
        'announcement': 'Company news, product updates, policy changes',
        'survey': 'Feedback requests and research',
        
        # Relationship categories
        'cold_outreach': 'First-time contact with prospects',
        'warm_outreach': 'Follow-up with engaged prospects', 
        'customer_communication': 'Ongoing communication with existing customers',
        'internal': 'Team and organizational communication',
        'partner': 'B2B partner and vendor communication'
    }
    
    def __init__(self):
        """Initialize with automation-focused rules"""
        self.transactional_indicators = self._load_transactional_indicators()
        self.promotional_indicators = self._load_promotional_indicators()
        self.behavioral_triggers = self._load_behavioral_triggers()
        self.sales_patterns = self._load_sales_patterns()
        self.support_patterns = self._load_support_patterns()
    
    def categorize(self, email: Dict, context: Dict = None) -> Dict:
        """
        Categorize email for automation/business intelligence
        
        Args:
            email: Email data
            context: Additional context (sender history, campaign data, etc.)
            
        Returns:
            Dict with primary category, subcategory, confidence, and tags
        """
        context = context or {}
        
        # Analyze email characteristics
        analysis = self._analyze_email(email, context)
        
        # Determine primary category
        primary_category = self._determine_primary_category(analysis)
        
        # Determine subcategory
        subcategory = self._determine_subcategory(primary_category, analysis)
        
        # Calculate confidence
        confidence = self._calculate_confidence(analysis)
        
        # Extract automation tags
        tags = self._extract_automation_tags(email, analysis)
        
        return {
            'primary_category': primary_category,
            'subcategory': subcategory,
            'confidence': confidence,
            'tags': tags,
            'automation_score': analysis.get('automation_score', 0),
            'engagement_potential': analysis.get('engagement_potential', 'medium'),
            'business_value': analysis.get('business_value', 'medium')
        }
    
    def _analyze_email(self, email: Dict, context: Dict) -> Dict:
        """Comprehensive email analysis for automation categorization"""
        
        sender = email.get('sender_email', '').lower()
        subject = email.get('subject', '').lower()
        body = email.get('body_text', '').lower()
        headers = email.get('raw_headers', {})
        
        analysis = {
            'sender_type': self._classify_sender_type(sender, headers),
            'content_type': self._classify_content_type(subject, body),
            'automation_indicators': self._detect_automation_indicators(email),
            'business_intent': self._classify_business_intent(subject, body),
            'engagement_signals': self._detect_engagement_signals(email),
            'urgency_level': self._assess_urgency(subject, body),
            'personalization_level': self._assess_personalization(email),
            'campaign_indicators': self._detect_campaign_indicators(email, headers)
        }
        
        # Calculate derived scores
        analysis['automation_score'] = self._calculate_automation_score(analysis)
        analysis['engagement_potential'] = self._assess_engagement_potential(analysis)
        analysis['business_value'] = self._assess_business_value(analysis, context)
        
        return analysis
    
    def _classify_sender_type(self, sender: str, headers: Dict) -> str:
        """Classify the type of sender"""

        # System/automated senders
        if is_noreply_address(sender):
            return 'system'
        
        # Marketing automation platforms
        automation_platforms = [
            'mailchimp', 'constantcontact', 'sendinblue', 'hubspot',
            'salesforce', 'marketo', 'pardot', 'eloqua', 'mailgun',
            'sendgrid', 'mandrill', 'postmark'
        ]
        
        for platform in automation_platforms:
            if platform in sender or platform in headers.get('Return-Path', ''):
                return 'marketing_automation'
        
        # Support/service senders
        if any(pattern in sender for pattern in ['support', 'help', 'service', 'tickets']):
            return 'customer_service'
        
        # Sales senders  
        if any(pattern in sender for pattern in ['sales', 'business', 'partnerships']):
            return 'sales'
        
        # Default to human sender
        return 'human'
    
    def _classify_content_type(self, subject: str, body: str) -> str:
        """Classify the content type of the email"""
        
        combined_text = f"{subject} {body}"
        
        # Transactional content
        if any(keyword in combined_text for keyword in self.transactional_indicators):
            return 'transactional'
        
        # Promotional content
        if any(keyword in combined_text for keyword in self.promotional_indicators):
            return 'promotional'
        
        # Educational/nurture content
        educational_keywords = [
            'how to', 'guide', 'tips', 'best practices', 'learn',
            'tutorial', 'webinar', 'ebook', 'whitepaper', 'case study'
        ]
        if any(keyword in combined_text for keyword in educational_keywords):
            return 'educational'
        
        # Survey/feedback
        feedback_keywords = ['survey', 'feedback', 'review', 'rate us', 'tell us']
        if any(keyword in combined_text for keyword in feedback_keywords):
            return 'feedback'
        
        return 'conversational'
    
    def _detect_automation_indicators(self, email: Dict) -> List[str]:
        """Detect indicators that email is automated"""
        
        indicators = []
        sender = email.get('sender_email', '').lower()
        subject = email.get('subject', '').lower()
        body = email.get('body_text', '').lower()
        headers = email.get('raw_headers', {})
        
        # Sender indicators
        if is_noreply_address(sender):
            indicators.append('noreply_sender')
        
        # Template indicators
        template_patterns = [
            r'\{\{.*\}\}',  # Handlebars
            r'\[.*\]',      # Square brackets
            r'%%.*%%',      # Percentage signs
            'dear [first name]', 'hello [name]'
        ]
        
        for pattern in template_patterns:
            if re.search(pattern, body, re.IGNORECASE):
                indicators.append('template_syntax')
                break
        
        # Automation headers
        automation_headers = [
            'x-mailer', 'x-campaign', 'x-mailgun', 'x-sendgrid',
            'list-unsubscribe', 'precedence'
        ]
        
        for header in automation_headers:
            if header.lower() in [h.lower() for h in headers.keys()]:
                indicators.append('automation_headers')
                break
        
        # Bulk email indicators
        if 'unsubscribe' in body:
            indicators.append('unsubscribe_link')
        
        return indicators
    
    def _classify_business_intent(self, subject: str, body: str) -> str:
        """Classify the business intent of the email"""
        
        combined_text = f"{subject} {body}"
        
        # Sales intent
        sales_keywords = [
            'demo', 'proposal', 'quote', 'pricing', 'trial',
            'consultation', 'meeting', 'call', 'opportunity'
        ]
        if any(keyword in combined_text for keyword in sales_keywords):
            return 'sales'
        
        # Support intent
        support_keywords = [
            'issue', 'problem', 'help', 'support', 'ticket',
            'bug', 'error', 'troubleshoot'
        ]
        if any(keyword in combined_text for keyword in support_keywords):
            return 'support'
        
        # Onboarding intent
        onboarding_keywords = [
            'welcome', 'getting started', 'setup', 'activate',
            'first steps', 'quick start'
        ]
        if any(keyword in combined_text for keyword in onboarding_keywords):
            return 'onboarding'
        
        # Retention intent
        retention_keywords = [
            'miss you', 'come back', 'special offer', 'win back',
            'we noticed', 'inactive'
        ]
        if any(keyword in combined_text for keyword in retention_keywords):
            return 'retention'
        
        return 'general'
    
    def _determine_primary_category(self, analysis: Dict) -> str:
        """Determine the primary automation category"""
        
        sender_type = analysis['sender_type']
        content_type = analysis['content_type']
        business_intent = analysis['business_intent']
        automation_score = analysis['automation_score']
        
        # High automation score = likely automated campaign
        if automation_score > 0.7:
            if content_type == 'transactional':
                return 'transactional'
            elif content_type == 'promotional':
                return 'promotional'
            elif business_intent == 'onboarding':
                return 'onboarding'
            elif business_intent == 'retention':
                return 'retention'
            else:
                return 'behavioral'
        
        # Business intent-based categorization
        if business_intent == 'sales':
            return 'sales'
        elif business_intent == 'support':
            return 'support'
        elif business_intent == 'onboarding':
            return 'onboarding'
        
        # Content-based fallback
        if content_type == 'transactional':
            return 'transactional'
        elif content_type == 'promotional':
            return 'promotional'
        elif content_type == 'educational':
            return 'nurture'
        elif content_type == 'feedback':
            return 'survey'
        
        # Default based on sender type
        if sender_type == 'system':
            return 'transactional'
        elif sender_type == 'marketing_automation':
            return 'promotional'
        elif sender_type == 'customer_service':
            return 'support'
        elif sender_type == 'sales':
            return 'sales'
        
        return 'customer_communication'
    
    def _determine_subcategory(self, primary_category: str, analysis: Dict) -> Optional[str]:
        """Determine subcategory based on primary category"""
        
        subcategories = {
            'transactional': [
                'receipt', 'confirmation', 'shipping', 'password_reset',
                'account_alert', 'system_notification'
            ],
            'promotional': [
                'product_announcement', 'sale', 'newsletter',
                'event_invitation', 'content_promotion'
            ],
            'behavioral': [
                'abandoned_cart', 'browse_abandonment', 'welcome_series',
                'milestone', 'usage_trigger'
            ],
            'sales': [
                'cold_outreach', 'follow_up', 'proposal',
                'demo_request', 'closing'
            ],
            'support': [
                'ticket_response', 'knowledge_base', 'status_update',
                'escalation', 'resolution'
            ]
        }
        
        # Use business intent and content analysis to determine subcategory
        # This would involve more detailed pattern matching
        # For brevity, returning None here
        return None
    
    def _calculate_automation_score(self, analysis: Dict) -> float:
        """Calculate how likely this email is automated (0-1 scale)"""
        
        score = 0.0
        
        # Sender type contributes to score
        sender_scores = {
            'system': 0.9,
            'marketing_automation': 0.8,
            'customer_service': 0.4,
            'sales': 0.3,
            'human': 0.1
        }
        score += sender_scores.get(analysis['sender_type'], 0.1) * 0.4
        
        # Automation indicators
        automation_indicators = analysis.get('automation_indicators', [])
        score += min(len(automation_indicators) * 0.2, 0.4)
        
        # Content type
        if analysis['content_type'] in ['transactional', 'promotional']:
            score += 0.2
        
        return min(score, 1.0)
    
    def _calculate_confidence(self, analysis: Dict) -> float:
        """Calculate confidence in categorization"""
        
        # Higher confidence for clear automation indicators
        confidence = 0.5
        
        if analysis['automation_score'] > 0.8:
            confidence += 0.3
        elif analysis['automation_score'] > 0.5:
            confidence += 0.2
        
        # Clear business intent increases confidence
        if analysis['business_intent'] != 'general':
            confidence += 0.15
        
        # System senders are usually clear
        if analysis['sender_type'] == 'system':
            confidence += 0.15
        
        return min(confidence, 1.0)
    
    def _extract_automation_tags(self, email: Dict, analysis: Dict) -> List[str]:
        """Extract automation-relevant tags"""
        
        tags = []
        
        # Automation platform tags
        if analysis['sender_type'] == 'marketing_automation':
            tags.append('automated')
        
        # Campaign tags
        if 'campaign_indicators' in analysis:
            tags.extend(analysis['campaign_indicators'])
        
        # Engagement tags
        if analysis.get('engagement_potential') == 'high':
            tags.append('high_engagement')
        
        # Business value tags
        if analysis.get('business_value') == 'high':
            tags.append('high_value')
        
        return tags
    
    # Load various indicator sets
    def _load_transactional_indicators(self) -> Set[str]:
        return {
            'receipt', 'invoice', 'payment', 'confirmation', 'order',
            'shipping', 'delivery', 'password', 'reset', 'verify',
            'account', 'security', 'alert', 'notification', 'reminder'
        }
    
    def _load_promotional_indicators(self) -> Set[str]:
        return {
            'sale', 'discount', 'offer', 'deal', 'promotion',
            'free', 'limited', 'exclusive', 'special', 'save',
            'buy now', 'shop now', 'newsletter', 'announcement'
        }
    
    def _load_behavioral_triggers(self) -> Set[str]:
        return {
            'abandoned', 'cart', 'browse', 'welcome', 'thank you',
            'milestone', 'anniversary', 'usage', 'inactive', 'return'
        }
    
    def _load_sales_patterns(self) -> Set[str]:
        return {
            'demo', 'consultation', 'proposal', 'quote', 'meeting',
            'call', 'follow up', 'opportunity', 'interested', 'pricing'
        }
    
    def _load_support_patterns(self) -> Set[str]:
        return {
            'ticket', 'issue', 'problem', 'help', 'support',
            'resolved', 'solution', 'troubleshoot', 'error', 'bug'
        }
    
    # Placeholder methods for comprehensive analysis
    def _detect_engagement_signals(self, email: Dict) -> List[str]:
        """Detect signals that predict user engagement"""
        # Would analyze personalization, relevance, timing, etc.
        return []
    
    def _assess_urgency(self, subject: str, body: str) -> str:
        """Assess urgency level (high/medium/low)"""
        urgent_keywords = ['urgent', 'asap', 'immediate', 'critical', 'emergency']
        if any(keyword in f"{subject} {body}".lower() for keyword in urgent_keywords):
            return 'high'
        return 'medium'
    
    def _assess_personalization(self, email: Dict) -> str:
        """Assess personalization level"""
        # Would check for dynamic content, personal details, etc.
        return 'medium'
    
    def _detect_campaign_indicators(self, email: Dict, headers: Dict) -> List[str]:
        """Detect campaign-related indicators"""
        # Would analyze campaign headers, UTM parameters, etc.
        return []
    
    def _assess_engagement_potential(self, analysis: Dict) -> str:
        """Assess potential for user engagement"""
        # Would use ML models or scoring algorithms
        return 'medium'
    
    def _assess_business_value(self, analysis: Dict, context: Dict) -> str:
        """Assess business value of the email"""
        # Would consider sender importance, content relevance, etc.
        return 'medium'


# Integration function for automation categorization
def categorize_for_automation(email: Dict, context: Dict = None) -> Dict:
    """
    Categorize email for automation/business intelligence purposes
    
    Returns comprehensive categorization data for automation tools
    """
    categorizer = EmailAutomationCategorizer()
    result = categorizer.categorize(email, context)
    
    return {
        'system': 'automation',
        'category': result['primary_category'],
        'primary_category': result['primary_category'],
        'subcategory': result['subcategory'],
        'confidence': result['confidence'],
        'automation_score': result['automation_score'],
        'business_value': result['business_value'],
        'engagement_potential': result['engagement_potential'],
        'tags': result['tags']
    }