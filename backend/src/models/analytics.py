"""
Analytics API Models - Sprint 2 Phase 5A

Pydantic models for analytics endpoints including:
- Extraction jobs
- Contact analytics
- Company analytics
- Thread analytics
- Response time metrics
- Communication patterns
- Dashboard summaries

Author: Sprint 2 Phase 5A Implementation
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


# ============================================================================
# ENUMS
# ============================================================================

class ExtractionStatus(str, Enum):
    """Extraction job status"""
    PENDING = 'pending'
    PROCESSING = 'processing'
    COMPLETED = 'completed'
    FAILED = 'failed'


class ExtractionMode(str, Enum):
    """Extraction mode"""
    FULL = 'full'
    INCREMENTAL = 'incremental'


class ThreadStatus(str, Enum):
    """Thread status"""
    COMPLETE = 'complete'
    AWAITING_RESPONSE = 'awaiting_response'
    AWAITING_OUR_RESPONSE = 'awaiting_our_response'
    OVERDUE = 'overdue'
    DROPPED = 'dropped'
    ONGOING = 'ongoing'


class ContactType(str, Enum):
    """Contact type classification"""
    PERSON = 'person'
    AUTOMATED = 'automated'
    SHARED = 'shared'
    MAILING_LIST = 'mailing_list'
    INTERNAL = 'internal'
    UNKNOWN = 'unknown'


class EngagementStatus(str, Enum):
    """Engagement status"""
    ACTIVE = 'active'
    QUIET = 'quiet'
    AT_RISK = 'at_risk'
    UNKNOWN = 'unknown'


# ============================================================================
# EXTRACTION JOB MODELS
# ============================================================================

class ExtractionJobCreate(BaseModel):
    """Request to create extraction job"""
    mailbox_id: str = Field(..., description="Mailbox UUID to extract from")
    mode: ExtractionMode = Field(default=ExtractionMode.FULL, description="Extraction mode")
    lookback_days: int = Field(default=7, ge=1, le=365, description="Days to look back for incremental mode")
    exclude_mailing_lists: bool = Field(default=True, description="Exclude mailing list emails")
    exclude_noreply: bool = Field(default=True, description="Exclude no-reply addresses")
    exclude_shared: bool = Field(default=True, description="Exclude shared addresses")
    exclude_internal: bool = Field(default=True, description="Exclude internal contacts")
    force_relink: bool = Field(default=False, description="Force relink all emails")
    skip_role_classification: bool = Field(default=False, description="Skip role classification step")


class ExtractionJobResponse(BaseModel):
    """Basic extraction job response"""
    id: str
    client_id: str
    mailbox_id: str
    status: ExtractionStatus
    extraction_mode: Optional[str] = None
    emails_in_scope: Optional[int] = None
    date_range_start: Optional[datetime] = None
    date_range_end: Optional[datetime] = None
    current_step: Optional[str] = None
    current_step_number: Optional[int] = None
    total_steps: Optional[int] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    errors: Optional[List[str]] = None

    class Config:
        from_attributes = True


class ExtractionJobDetail(ExtractionJobResponse):
    """Detailed extraction job with results"""
    results: Optional[Dict[str, Any]] = None
    duration_seconds: Optional[float] = None


class ExtractionJobListResponse(BaseModel):
    """List of extraction jobs"""
    jobs: List[ExtractionJobResponse]
    total: int


class ExtractionProgressResponse(BaseModel):
    """Real-time progress from Redis"""
    job_id: str
    status: str
    current_step: Optional[str] = None
    current_step_number: Optional[int] = None
    total_steps: Optional[int] = None
    processed: Optional[int] = None
    failed: Optional[int] = None
    mailbox_id: Optional[str] = None
    client_id: Optional[str] = None
    error: Optional[str] = None


# ============================================================================
# CONTACT ANALYTICS MODELS
# ============================================================================

class ContactAnalytics(BaseModel):
    """Contact with engagement analytics"""
    id: str
    email_address: str
    full_name: Optional[str] = None
    job_title: Optional[str] = None
    company_name: Optional[str] = None
    customer_company_id: Optional[str] = None
    customer_company_name: Optional[str] = None
    client_id: str
    contact_type: Optional[ContactType] = None

    # Role classification
    is_decision_maker: Optional[bool] = None
    seniority_level: Optional[str] = None

    # Engagement metrics
    engagement_score: Optional[float] = None
    total_emails_sent: Optional[int] = None
    total_emails_received: Optional[int] = None
    first_contacted_at: Optional[datetime] = None
    last_contacted_at: Optional[datetime] = None

    # Communication patterns
    initiation_ratio: Optional[float] = None
    reply_rate: Optional[float] = None
    avg_response_time_seconds: Optional[int] = None
    avg_thread_depth: Optional[float] = None

    # QB business context (Sprint 3)
    qb_contact_id: Optional[str] = None
    qb_customer_type: Optional[str] = None
    qb_tier: Optional[str] = None
    qb_quotes_count: Optional[int] = None
    qb_last_quote_date: Optional[str] = None

    # Computed field for convenience
    @property
    def avg_response_time_hours(self) -> Optional[float]:
        if self.avg_response_time_seconds:
            return self.avg_response_time_seconds / 3600.0
        return None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ContactAnalyticsListResponse(BaseModel):
    """List of contacts with analytics"""
    contacts: List[ContactAnalytics]
    total: int


class TopEngagedContact(BaseModel):
    """Top engaged contact summary"""
    id: str
    email_address: str
    full_name: Optional[str] = None
    company_name: Optional[str] = None
    engagement_score: float
    total_emails: int
    last_contacted_at: Optional[datetime] = None
    qb_customer_type: Optional[str] = None
    qb_tier: Optional[str] = None

    class Config:
        from_attributes = True


class AtRiskContact(BaseModel):
    """At-risk contact summary"""
    id: str
    email_address: str
    full_name: Optional[str] = None
    company_name: Optional[str] = None
    last_contacted_at: Optional[datetime] = None
    days_since_contact: int
    engagement_score: Optional[float] = None
    qb_total_revenue: Optional[float] = None
    qb_tier: Optional[str] = None

    class Config:
        from_attributes = True


class ContactTypeGrouping(BaseModel):
    """Contacts grouped by type"""
    contact_type: ContactType
    count: int
    avg_engagement_score: Optional[float] = None


# ============================================================================
# COMPANY ANALYTICS MODELS
# ============================================================================

class CompanyAnalytics(BaseModel):
    """Company with engagement analytics"""
    id: str
    company_name: str
    client_id: str
    client_name: Optional[str] = None
    email_domains: Optional[List[str]] = None
    industry: Optional[str] = None

    # Engagement metrics
    engagement_score: Optional[float] = None
    engagement_status: Optional[EngagementStatus] = None
    total_emails: Optional[int] = None
    total_inbound: Optional[int] = None
    total_outbound: Optional[int] = None
    first_contact_date: Optional[datetime] = None
    last_contact_date: Optional[datetime] = None

    # Contact counts
    contact_count: Optional[int] = None
    decision_maker_count: Optional[int] = None

    # Thread metrics
    active_threads: Optional[int] = None
    overdue_threads: Optional[int] = None

    # QB business context (Sprint 3) + matching metadata (Sprint 4)
    qb_customer_id: Optional[str] = None
    qb_customer_code: Optional[str] = None
    qb_match_method: Optional[str] = None
    qb_matched_at: Optional[datetime] = None
    qb_customer_type: Optional[str] = None
    qb_tier: Optional[str] = None
    qb_total_revenue: Optional[float] = None
    qb_invoiced_ty: Optional[float] = None
    qb_invoiced_ly: Optional[float] = None
    qb_growth_90d: Optional[float] = None
    qb_days_since_last_invoice: Optional[int] = None
    qb_account_manager: Optional[str] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CompanyAnalyticsListResponse(BaseModel):
    """List of companies with analytics"""
    companies: List[CompanyAnalytics]
    total: int


class TopEngagedCompany(BaseModel):
    """Top engaged company summary"""
    id: str
    company_name: str
    engagement_score: float
    total_emails: int
    contact_count: int
    last_contact_date: Optional[datetime] = None
    qb_tier: Optional[str] = None
    qb_total_revenue: Optional[float] = None

    class Config:
        from_attributes = True


class AtRiskCompany(BaseModel):
    """At-risk company summary"""
    id: str
    company_name: str
    last_contact_date: Optional[datetime] = None
    days_since_contact: int
    contact_count: int
    engagement_score: Optional[float] = None
    qb_total_revenue: Optional[float] = None
    qb_days_since_last_invoice: Optional[int] = None
    qb_tier: Optional[str] = None

    class Config:
        from_attributes = True


class EngagementStatusGrouping(BaseModel):
    """Companies grouped by engagement status"""
    engagement_status: EngagementStatus
    count: int
    avg_engagement_score: Optional[float] = None


# ============================================================================
# THREAD ANALYTICS MODELS
# ============================================================================

class ThreadStatusSummary(BaseModel):
    """Thread with status information"""
    thread_id: str
    subject: Optional[str] = None
    contact_id: Optional[str] = None
    contact_email: Optional[str] = None
    contact_name: Optional[str] = None
    company_id: Optional[str] = None
    company_name: Optional[str] = None

    status: ThreadStatus
    total_messages: Optional[int] = None
    last_message_date: Optional[datetime] = None
    last_sender_type: Optional[str] = None  # 'us' or 'them'
    days_since_last_message: Optional[int] = None

    # QB context (Sprint 3)
    qb_customer_type: Optional[str] = None
    qb_customer_tier: Optional[str] = None

    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ThreadStatusListResponse(BaseModel):
    """List of thread statuses"""
    threads: List[ThreadStatusSummary]
    total: int


class OverdueThread(BaseModel):
    """Overdue thread summary"""
    thread_id: str
    subject: Optional[str] = None
    contact_email: Optional[str] = None
    contact_name: Optional[str] = None
    company_name: Optional[str] = None
    last_message_date: Optional[datetime] = None
    days_overdue: int
    qb_customer_type: Optional[str] = None
    qb_customer_tier: Optional[str] = None

    class Config:
        from_attributes = True


class ThreadStatusCount(BaseModel):
    """Count by thread status"""
    status: ThreadStatus
    count: int


class ThreadEmail(BaseModel):
    """Email within a thread"""
    id: str
    subject: Optional[str] = None
    sender_email: Optional[str] = None
    sender_name: Optional[str] = None
    recipients: Optional[list] = None
    sent_date: Optional[datetime] = None
    is_outbound: Optional[bool] = None
    body_text: Optional[str] = None
    folder_path: Optional[str] = None

    class Config:
        from_attributes = True


class ThreadDetail(BaseModel):
    """Full thread detail with emails"""
    thread_id: str
    subject: Optional[str] = None
    status: ThreadStatus
    total_messages: int = 0
    last_message_date: Optional[datetime] = None
    days_since_last_message: Optional[int] = None
    contact_id: Optional[str] = None
    contact_email: Optional[str] = None
    contact_name: Optional[str] = None
    company_id: Optional[str] = None
    company_name: Optional[str] = None
    thread_depth: Optional[int] = None
    created_at: Optional[datetime] = None
    emails: List[ThreadEmail] = []

    class Config:
        from_attributes = True


# ============================================================================
# RESPONSE TIME MODELS
# ============================================================================

class ResponseTimeMetric(BaseModel):
    """Response time metric"""
    id: str
    email_id: str
    responding_to_email_id: str
    responder_contact_id: Optional[str] = None
    responder_company_id: Optional[str] = None
    contact_email: Optional[str] = None

    response_time_seconds: int
    business_hours_response_time_seconds: Optional[int] = None
    is_auto_reply: Optional[bool] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # Computed field for convenience (seconds to hours)
    @property
    def response_time_hours(self) -> float:
        return self.response_time_seconds / 3600.0

    class Config:
        from_attributes = True


class ResponseTimeListResponse(BaseModel):
    """List of response time metrics"""
    metrics: List[ResponseTimeMetric]
    total: int


class ResponseTimeStats(BaseModel):
    """Aggregate response time statistics"""
    total_responses: int
    avg_response_time_hours: float
    median_response_time_hours: Optional[float] = None
    min_response_time_hours: float
    max_response_time_hours: float

    # Business hours equivalents
    avg_business_hours_response_time_hours: Optional[float] = None
    median_business_hours_response_time_hours: Optional[float] = None

    # Breakdown by responder
    our_avg_response_time: Optional[float] = None
    their_avg_response_time: Optional[float] = None

    # Auto-reply detection
    auto_reply_count: Optional[int] = None
    auto_reply_percentage: Optional[float] = None


class SlowestResponder(BaseModel):
    """Slowest responder summary"""
    contact_id: str
    contact_email: str
    contact_name: Optional[str] = None
    company_name: Optional[str] = None
    avg_response_time_hours: float
    response_count: int

    class Config:
        from_attributes = True


# ============================================================================
# COMMUNICATION PATTERN MODELS
# ============================================================================

class InitiationPattern(BaseModel):
    """Thread initiation pattern"""
    contact_id: str
    contact_email: str
    contact_name: Optional[str] = None
    company_name: Optional[str] = None

    total_threads: int
    threads_initiated_by_us: int
    threads_initiated_by_them: int
    initiation_ratio: float  # Our initiations / total

    class Config:
        from_attributes = True


class FrequencyPattern(BaseModel):
    """Communication frequency pattern"""
    contact_id: str
    contact_email: str
    contact_name: Optional[str] = None
    company_name: Optional[str] = None

    total_emails: int
    emails_per_week: Optional[float] = None
    emails_per_month: Optional[float] = None
    first_contact_date: Optional[datetime] = None
    last_contact_date: Optional[datetime] = None
    days_active: Optional[int] = None

    class Config:
        from_attributes = True


class EngagementTrend(BaseModel):
    """Engagement trend over time"""
    contact_id: str
    contact_email: str
    contact_name: Optional[str] = None
    company_name: Optional[str] = None

    current_engagement_score: float
    trend: str  # 'increasing', 'stable', 'decreasing'
    last_30_days_emails: int
    previous_30_days_emails: int
    change_percentage: float

    class Config:
        from_attributes = True


class CommunicationPattern(BaseModel):
    """Complete communication pattern for a contact"""
    contact_id: str
    contact_email: str
    contact_name: Optional[str] = None
    company_name: Optional[str] = None

    # Initiation
    thread_initiation_ratio: Optional[float] = None
    total_threads: Optional[int] = None

    # Response behavior
    reply_rate: Optional[float] = None
    avg_response_time_hours: Optional[float] = None  # Our avg response time (how long we take to reply)
    their_avg_response_time_hours: Optional[float] = None  # Their avg response time (how long they take to reply)

    # Frequency
    emails_per_week: Optional[float] = None
    total_emails: Optional[int] = None

    # Thread depth
    avg_thread_depth: Optional[float] = None

    class Config:
        from_attributes = True


# ============================================================================
# DASHBOARD MODELS
# ============================================================================

class DashboardSummary(BaseModel):
    """Complete dashboard summary"""
    client_id: str

    # Overview metrics
    total_contacts: int
    total_companies: int
    total_emails: int

    # Engagement overview
    active_contacts: int
    quiet_contacts: int
    at_risk_contacts: int
    avg_engagement_score: Optional[float] = None

    # Thread status
    total_threads: int
    active_threads: int
    overdue_threads: int
    awaiting_response_threads: int

    # Response times
    avg_response_time_hours: Optional[float] = None

    # Top performers
    top_engaged_contacts: List[TopEngagedContact]
    top_engaged_companies: List[TopEngagedCompany]

    # At-risk items
    at_risk_contacts_list: List[AtRiskContact]
    at_risk_companies_list: List[AtRiskCompany]

    # Recent activity
    last_extraction_date: Optional[datetime] = None
    last_contact_date: Optional[datetime] = None


class ClientSummary(BaseModel):
    """Client-specific summary"""
    client_id: str
    client_name: Optional[str] = None

    # Counts
    mailbox_count: int
    contact_count: int
    company_count: int
    total_emails: int

    # Engagement
    avg_engagement_score: Optional[float] = None
    active_contacts: int
    at_risk_contacts: int

    # Recent activity
    last_extraction_date: Optional[datetime] = None
    last_contact_date: Optional[datetime] = None


# ============================================================================
# FILTER/QUERY MODELS
# ============================================================================

class DateRangeFilter(BaseModel):
    """Date range filter"""
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class EngagementFilter(BaseModel):
    """Engagement filter"""
    min_engagement_score: Optional[float] = Field(None, ge=0, le=100)
    max_engagement_score: Optional[float] = Field(None, ge=0, le=100)
    engagement_status: Optional[EngagementStatus] = None


class ContactFilter(BaseModel):
    """Contact filter parameters"""
    client_id: Optional[str] = None
    company_id: Optional[str] = None
    contact_type: Optional[ContactType] = None
    is_decision_maker: Optional[bool] = None
    engagement: Optional[EngagementFilter] = None
    date_range: Optional[DateRangeFilter] = None
