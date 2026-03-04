"""
Email Rules Models — Pydantic request/response models for unified email rules.

Normalizes Gmail filters and Outlook inbox rules into a common format
for cross-AM comparison and efficiency analysis.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum


# ============================================================================
# ENUMS
# ============================================================================

class EngagementSignal(str, Enum):
    HIGH_VALUE = "high_value"
    ESCALATION = "escalation"
    LOW_PRIORITY = "low_priority"
    SEGMENTATION = "segmentation"
    NEUTRAL = "neutral"


class RuleSourceType(str, Enum):
    GMAIL = "gmail"
    OUTLOOK = "outlook"


# ============================================================================
# RULE STRUCTURE MODELS
# ============================================================================

class RuleConditions(BaseModel):
    """Normalized rule conditions across Gmail/Outlook."""
    from_addresses: List[str] = []
    from_domains: List[str] = []
    to_addresses: List[str] = []
    subject_contains: List[str] = []
    body_contains: List[str] = []
    has_attachment: Optional[bool] = None


class RuleActions(BaseModel):
    """Normalized rule actions across Gmail/Outlook."""
    label: Optional[str] = None
    move_to_folder: Optional[str] = None
    forward_to: List[str] = []
    mark_important: bool = False
    mark_read: bool = False
    skip_inbox: bool = False
    delete: bool = False


class UnifiedRule(BaseModel):
    """Single email rule normalized from Gmail or Outlook."""
    id: Optional[str] = None
    mailbox_id: str = ""
    mailbox_email: str = ""
    source_type: str = ""
    source_rule_id: str = ""
    name: str = ""
    is_active: bool = True
    conditions: RuleConditions = RuleConditions()
    actions: RuleActions = RuleActions()
    engagement_signal: str = "neutral"
    imported_at: Optional[str] = None


# ============================================================================
# RESPONSE MODELS
# ============================================================================

class RulesListResponse(BaseModel):
    """List of unified rules for a mailbox."""
    items: List[UnifiedRule] = []
    total: int = 0
    mailbox_email: str = ""
    source_type: str = ""


class MailboxRulesMetrics(BaseModel):
    """Per-mailbox rules metrics for cross-AM comparison."""
    mailbox_id: str = ""
    mailbox_email: str = ""
    mailbox_type: str = ""
    live_connection: str = ""  # 'gmail', 'outlook', or '' (no LIVE connection)
    total_rules: int = 0
    active_rules: int = 0
    high_value_count: int = 0
    escalation_count: int = 0
    low_priority_count: int = 0
    segmentation_count: int = 0
    neutral_count: int = 0
    forward_count: int = 0
    covered_domains: List[str] = []
    covered_addresses: List[str] = []


class RulesAnalyticsResponse(BaseModel):
    """Cross-AM rules comparison analytics."""
    mailboxes: List[MailboxRulesMetrics] = []
    total_mailboxes: int = 0
    total_rules: int = 0
    avg_rules_per_mailbox: float = 0.0
    mailboxes_with_no_rules: int = 0


class RulesInsight(BaseModel):
    """A derived insight/recommendation about email rules."""
    insight_type: str = ""
    severity: str = "info"  # info, warning, critical
    description: str = ""
    affected_mailboxes: List[str] = []
    recommendation: str = ""


class RulesInsightsResponse(BaseModel):
    """List of derived insights."""
    insights: List[RulesInsight] = []
    total: int = 0
