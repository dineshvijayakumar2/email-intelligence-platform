"""
AI Intelligence Models — Sprint 3

Pydantic request/response models for AI intelligence endpoints:
- Intelligence results (classification, entities, buckets)
- Action bucket items
- Entity aggregation
- Human feedback
- Digest (Session 5)
- Relationship summaries (Session 8)
- Usage stats (Session 11)

Follows analytics.py patterns: enums + typed models.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from enum import Enum


# ============================================================================
# ENUMS
# ============================================================================

class IntentType(str, Enum):
    ACTION_REQUIRED = "action_required"
    FYI_UPDATE = "fyi_update"
    MEETING_SCHEDULING = "meeting_scheduling"
    QUESTION = "question"
    COMPLAINT = "complaint"
    POSITIVE_FEEDBACK = "positive_feedback"
    PRICING_INQUIRY = "pricing_inquiry"
    FEATURE_REQUEST = "feature_request"
    EXPANSION_SIGNAL = "expansion_signal"
    CHURN_RISK = "churn_risk"
    FOLLOW_UP = "follow_up"
    INTRODUCTION = "introduction"
    OTHER = "other"


class UrgencyLevel(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


class SentimentType(str, Enum):
    VERY_POSITIVE = "very_positive"
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    VERY_NEGATIVE = "very_negative"


class ActionType(str, Enum):
    RESPOND_TO_INQUIRY = "respond_to_inquiry"
    PROVIDE_QUOTE = "provide_quote"
    SCHEDULE_MEETING = "schedule_meeting"
    ESCALATE_INTERNALLY = "escalate_internally"
    SEND_FOLLOW_UP = "send_follow_up"
    RESOLVE_ISSUE = "resolve_issue"
    ACKNOWLEDGE_RECEIPT = "acknowledge_receipt"
    NO_ACTION = "no_action"
    DELEGATE = "delegate"
    PREPARE_DOCUMENT = "prepare_document"


class BusinessSignalType(str, Enum):
    BUYING_INTENT = "buying_intent"
    RENEWAL_INTENT = "renewal_intent"
    EXPANSION_INTEREST = "expansion_interest"
    CHURN_SIGNAL = "churn_signal"
    COMPETITIVE_EVALUATION = "competitive_evaluation"
    BUDGET_DISCUSSION = "budget_discussion"
    ESCALATION = "escalation"
    POSITIVE_FEEDBACK = "positive_feedback"
    NEGATIVE_FEEDBACK = "negative_feedback"
    CONTRACT_ACTIVITY = "contract_activity"
    NEUTRAL = "neutral"


class BucketType(str, Enum):
    BUYING_SIGNAL = "buying_signal"
    EXPANSION_SIGNAL = "expansion_signal"
    CHURN_RISK = "churn_risk"
    COMPETITOR_THREAT = "competitor_threat"
    MISSED_OPPORTUNITY = "missed_opportunity"
    STAKEHOLDER_ENTRY = "stakeholder_entry"
    SILENT_CHAMPION = "silent_champion"
    UNRESOLVED_BLOCK = "unresolved_block"


class ProcessingStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class FeedbackType(str, Enum):
    CORRECT = "correct"
    INCORRECT = "incorrect"


class EntityType(str, Enum):
    COMPETITOR = "competitor"
    PRODUCT = "product"
    PERSON = "person"
    COMPANY = "company"
    TECHNOLOGY = "technology"


# ============================================================================
# REQUEST MODELS
# ============================================================================

class AnalyzeRequest(BaseModel):
    """Request to trigger AI analysis on a mailbox."""
    max_emails: int = Field(default=500, ge=1, le=5000, description="Max emails to analyze")
    client_id: Optional[str] = Field(default=None, description="Client UUID for scoping")
    date_from: Optional[str] = Field(default=None, description="ISO date — only analyze emails after this (default: 7 days ago)")
    date_to: Optional[str] = Field(default=None, description="ISO date — only analyze emails before this (default: now)")


class ReanalyzeRequest(BaseModel):
    """Request to re-analyze emails with an older prompt version."""
    target_prompt_version: str = Field(..., description="Prompt version to find and re-analyze (e.g. 'v1.0')")
    max_emails: int = Field(default=500, ge=1, le=5000, description="Max emails to re-analyze")
    client_id: Optional[str] = Field(default=None, description="Client UUID for scoping")
    include_failed: bool = Field(default=False, description="Also re-analyze failed rows")


class ReanalyzeResponse(BaseModel):
    """Response from triggering re-analysis."""
    status: str = "accepted"
    message: str = ""
    mailbox_id: str = ""
    emails_queued: int = 0
    old_prompt_version: str = ""
    new_prompt_version: str = ""


class FeedbackRequest(BaseModel):
    """Structured human feedback on an AI classification."""
    feedback: FeedbackType = Field(..., description="Was the classification correct or incorrect?")
    feedback_field: Optional[str] = Field(
        default=None,
        description="Which field was wrong: intent, bucket, sentiment, urgency"
    )
    override_intent: Optional[str] = Field(default=None, description="Corrected intent value")
    override_bucket: Optional[str] = Field(default=None, description="Corrected bucket value")
    override_sentiment: Optional[str] = Field(default=None, description="Corrected sentiment value")
    note: Optional[str] = Field(default=None, max_length=500, description="Free-text explanation")


# ============================================================================
# INTELLIGENCE RESULT MODELS
# ============================================================================

class BucketEntry(BaseModel):
    """Single action bucket assignment."""
    bucket: str
    confidence: float
    justification: str = ""


class IntelligenceResult(BaseModel):
    """AI intelligence result for a single email."""
    id: Optional[str] = None
    email_id: Optional[str] = None

    # Email display fields (joined)
    email_subject: str = ""
    email_sender: str = ""
    email_sender_name: str = ""
    email_date: Optional[str] = None
    email_direction: str = ""

    # Classification
    intent: Optional[str] = None
    urgency: Optional[str] = None
    sentiment: Optional[str] = None
    sentiment_score: Optional[float] = None
    summary: str = ""
    suggested_action: str = ""
    key_topics: List[str] = []
    confidence: Optional[float] = None
    justification: str = ""

    # Multi-axis
    action_type: Optional[str] = None
    business_signal: Optional[str] = None
    thread_role: Optional[str] = None

    # Entities
    competitors_mentioned: List[str] = []
    products_mentioned: List[str] = []
    budget_signals: Optional[Dict] = None
    buying_signals: List[str] = []
    people_mentioned: List[Dict] = []
    dates_mentioned: List[Dict] = []
    action_items_extracted: List[str] = []

    # Business signal flags
    has_budget_signal: bool = False
    has_buying_signal: bool = False
    has_competitor_mention: bool = False
    has_deadline: bool = False
    business_signal_score: int = 0

    # Buckets
    action_buckets: List[Any] = []
    primary_bucket: Optional[str] = None

    # Feedback
    human_feedback: Optional[str] = None
    feedback_field: Optional[str] = None
    feedback_note: Optional[str] = None

    # Processing
    processing_status: Optional[str] = None
    processed_at: Optional[str] = None
    model_used: Optional[str] = None
    prompt_version: Optional[str] = None


class IntelligenceListResponse(BaseModel):
    """Paginated intelligence results."""
    items: List[IntelligenceResult] = []
    page: int = 1
    page_size: int = 25


class IntelligenceStats(BaseModel):
    """Stats breakdown for intelligence results."""
    total: int = 0
    by_status: Dict[str, int] = {}
    by_intent: Dict[str, int] = {}
    by_urgency: Dict[str, int] = {}
    by_sentiment: Dict[str, int] = {}
    by_bucket: Dict[str, int] = {}
    by_business_signal: Dict[str, int] = {}
    avg_confidence: float = 0.0


# ============================================================================
# ACTION BUCKET MODELS
# ============================================================================

class ActionItem(BaseModel):
    """Prioritized action item from bucket engine."""
    email_id: Optional[str] = None
    bucket: str
    bucket_label: str = ""
    bucket_color: str = ""
    severity: str = ""
    recommended_action: str = ""
    confidence: float = 0.0
    justification: str = ""
    email_summary: str = ""
    email_suggested_action: str = ""
    intent: Optional[str] = None
    urgency: Optional[str] = None
    business_signal_score: int = 0


class ActionItemsResponse(BaseModel):
    """List of prioritized action items."""
    items: List[ActionItem] = []
    total: int = 0


class BucketSummary(BaseModel):
    """Bucket counts summary."""
    buying_signal: int = 0
    expansion_signal: int = 0
    churn_risk: int = 0
    competitor_threat: int = 0
    missed_opportunity: int = 0
    stakeholder_entry: int = 0
    silent_champion: int = 0
    unresolved_block: int = 0
    total: int = 0


# ============================================================================
# ENTITY MODELS
# ============================================================================

class BusinessEntity(BaseModel):
    """Aggregated business entity."""
    id: Optional[str] = None
    entity_type: str
    entity_name: str
    normalized_name: str = ""
    mention_count: int = 0
    first_seen_at: Optional[str] = None
    last_seen_at: Optional[str] = None
    context_snippets: List[str] = []


class EntityListResponse(BaseModel):
    """List of business entities."""
    items: List[BusinessEntity] = []
    total: int = 0


class CompetitorLandscape(BaseModel):
    """Competitor analysis summary."""
    competitors: List[BusinessEntity] = []
    total_mentions: int = 0
    accounts_affected: int = 0


class OpportunitySignal(BaseModel):
    """Opportunity signal item."""
    email_id: Optional[str] = None
    email_subject: str = ""
    email_sender: str = ""
    email_date: Optional[str] = None
    signal_type: str = ""
    confidence: float = 0.0
    summary: str = ""
    budget_signal: Optional[Dict] = None
    buying_signals: List[str] = []
    business_signal_score: int = 0


class OpportunitySignalsResponse(BaseModel):
    """Opportunity signals list."""
    items: List[OpportunitySignal] = []
    total: int = 0


# ============================================================================
# ANALYSIS TRIGGER RESPONSE
# ============================================================================

class AnalyzeResponse(BaseModel):
    """Response from triggering analysis."""
    status: str = "accepted"
    message: str = ""
    mailbox_id: str = ""
    max_emails: int = 0


class AnalysisProgress(BaseModel):
    """Analysis job progress."""
    total_analyzed: int = 0
    total_failed: int = 0
    batches: int = 0
    status: str = "running"


# ============================================================================
# FEEDBACK RESPONSE
# ============================================================================

class FeedbackResponse(BaseModel):
    """Response after submitting feedback."""
    status: str = "saved"
    email_id: str = ""
    feedback: str = ""
    feedback_field: Optional[str] = None


# ============================================================================
# DIGEST MODELS (Session 5)
# ============================================================================

class DigestActionItem(BaseModel):
    """Action item in a daily digest."""
    email_id: Optional[str] = None
    priority: int = 3
    bucket: Optional[str] = None
    action: str = ""
    contact_name: Optional[str] = None


class DigestHighlight(BaseModel):
    """Highlight item in a daily digest."""
    label: str = ""
    detail: str = ""


class DailyDigest(BaseModel):
    """Daily intelligence digest."""
    id: Optional[str] = None
    digest_date: Optional[str] = None
    summary: str = ""
    action_items: List[DigestActionItem] = []
    highlights: List[DigestHighlight] = []
    stats: Dict[str, Any] = {}
    bucket_summary: Dict[str, int] = {}
    emails_analyzed: int = 0
    model_used: Optional[str] = None
    created_at: Optional[str] = None


# ============================================================================
# RELATIONSHIP SUMMARY MODELS (Session 8)
# ============================================================================

class RelationshipSummary(BaseModel):
    """AI-generated relationship summary for a company."""
    id: Optional[str] = None
    company_id: Optional[str] = None
    summary: str = ""
    key_themes: List[str] = []
    risk_factors: List[str] = []
    opportunities: List[str] = []
    recommended_actions: List[str] = []
    competitors_in_play: List[str] = []
    active_buying_signals: List[str] = []
    upcoming_deadlines: Optional[Any] = None
    active_buckets: List[Any] = []
    emails_analyzed: int = 0
    model_used: Optional[str] = None
    created_at: Optional[str] = None


# ============================================================================
# USAGE MODELS (Session 11)
# ============================================================================

class UsageSummaryResponse(BaseModel):
    """AI usage summary."""
    total_cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_requests: int = 0
    by_operation: Dict[str, Any] = {}
    by_model: Dict[str, Any] = {}
    failure_rate: float = 0.0
    avg_latency_ms: float = 0.0


class MonitoringStatsResponse(BaseModel):
    """AI monitoring stats."""
    parse_failure_rate: float = 0.0
    api_failure_rate: float = 0.0
    avg_retry_count: float = 0.0
    cost_per_1000_emails: float = 0.0
    total_failures_24h: int = 0
    total_requests_24h: int = 0
