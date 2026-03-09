"""
Analytics API Router - Sprint 2 Phase 5A

Comprehensive analytics endpoints for:
- Extraction job control (5 endpoints)
- Contact analytics (6 endpoints)
- Company analytics (5 endpoints)
- Thread analytics (4 endpoints)
- Response time analytics (4 endpoints)
- Communication patterns (4 endpoints)
- Dashboard summaries (2 endpoints)

Total: ~30 endpoints

Author: Sprint 2 Phase 5A Implementation
"""

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from typing import List, Optional
from datetime import datetime, timedelta
import logging

from ..models.analytics import (
    # Enums
    ExtractionStatus, ExtractionMode, ThreadStatus, ContactType, EngagementStatus,
    # Extraction models
    ExtractionJobCreate, ExtractionJobResponse, ExtractionJobDetail,
    ExtractionJobListResponse, ExtractionProgressResponse,
    # Contact models
    ContactAnalytics, ContactAnalyticsListResponse, TopEngagedContact,
    AtRiskContact, ContactTypeGrouping,
    # Company models
    CompanyAnalytics, CompanyAnalyticsListResponse, TopEngagedCompany,
    AtRiskCompany, EngagementStatusGrouping,
    # Thread models
    ThreadStatusSummary, ThreadStatusListResponse, OverdueThread, ThreadStatusCount,
    # Response time models
    ResponseTimeMetric, ResponseTimeListResponse, ResponseTimeStats, SlowestResponder,
    # Communication pattern models
    InitiationPattern, FrequencyPattern, EngagementTrend, CommunicationPattern,
    # Dashboard models
    DashboardSummary, ClientSummary,
)
from ..services.extraction_orchestrator import ExtractionOrchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])

# Supabase client will be injected from main.py
_supabase = None


def init_analytics_router(supabase_client):
    """Initialize the router with Supabase client"""
    global _supabase
    _supabase = supabase_client


# ============================================================================
# EXTRACTION CONTROL ENDPOINTS (5 endpoints)
# ============================================================================

@router.post("/extraction/run", response_model=ExtractionJobResponse)
async def trigger_extraction_job(data: ExtractionJobCreate, background_tasks: BackgroundTasks):
    """
    Trigger a new extraction job.

    Args:
        data: Extraction job configuration
        background_tasks: FastAPI background tasks

    Returns:
        Created extraction job record
    """
    try:
        from ..services.extraction_orchestrator import ExtractionOrchestrator

        # Validate mailbox exists
        mailbox_check = _supabase.table('mailboxes').select('id, client_id').eq(
            'id', data.mailbox_id
        ).execute()

        if not mailbox_check.data:
            raise HTTPException(status_code=404, detail="Mailbox not found")

        client_id = mailbox_check.data[0]['client_id']

        # Create orchestrator with mode and lookback
        orchestrator = ExtractionOrchestrator(
            mailbox_id=data.mailbox_id,
            client_id=client_id,
            use_redis=True,
            extraction_mode=data.mode.value,
            lookback_days=data.lookback_days
        )

        # Run extraction in background
        def run_extraction():
            try:
                orchestrator.run_extraction(
                    exclude_mailing_lists=data.exclude_mailing_lists,
                    exclude_noreply=data.exclude_noreply,
                    exclude_shared=data.exclude_shared,
                    exclude_internal=data.exclude_internal,
                    force_relink=data.force_relink,
                    skip_role_classification=data.skip_role_classification
                )
            except Exception as e:
                logger.error(f"Background extraction failed: {e}")

        background_tasks.add_task(run_extraction)

        # Return initial job status (will be created by orchestrator)
        return {
            "id": "pending",  # Will be replaced by actual job_id
            "client_id": client_id,
            "mailbox_id": data.mailbox_id,
            "status": ExtractionStatus.PENDING,
            "extraction_mode": data.mode.value,
            "current_step": "Queued for processing",
            "current_step_number": 0,
            "total_steps": 13
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to trigger extraction job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/extraction/jobs/{job_id}", response_model=ExtractionJobDetail)
async def get_extraction_job(job_id: str):
    """
    Get extraction job details by ID.

    Args:
        job_id: Extraction job UUID

    Returns:
        Detailed extraction job record
    """
    try:
        result = _supabase.table('extraction_jobs').select('*').eq('id', job_id).single().execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Extraction job not found")

        job = result.data

        # Calculate duration if completed
        duration = None
        if job.get('completed_at') and job.get('started_at'):
            started = datetime.fromisoformat(job['started_at'].replace('Z', '+00:00'))
            completed = datetime.fromisoformat(job['completed_at'].replace('Z', '+00:00'))
            duration = (completed - started).total_seconds()

        return ExtractionJobDetail(
            **job,
            duration_seconds=duration
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get extraction job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/extraction/jobs", response_model=ExtractionJobListResponse)
async def list_extraction_jobs(
    client_id: Optional[str] = Query(default=None),
    mailbox_id: Optional[str] = Query(default=None),
    status: Optional[ExtractionStatus] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0)
):
    """
    List extraction jobs with filters.

    Args:
        client_id: Filter by client
        mailbox_id: Filter by mailbox
        status: Filter by status
        limit: Maximum number of results
        offset: Offset for pagination

    Returns:
        List of extraction jobs
    """
    try:
        query = _supabase.table('extraction_jobs').select('*')

        if client_id:
            query = query.eq('client_id', client_id)
        if mailbox_id:
            query = query.eq('mailbox_id', mailbox_id)
        if status:
            query = query.eq('status', status.value)

        result = query.order('started_at', desc=True).range(offset, offset + limit - 1).execute()

        # Get total count
        count_query = _supabase.table('extraction_jobs').select('id', count='exact')
        if client_id:
            count_query = count_query.eq('client_id', client_id)
        if mailbox_id:
            count_query = count_query.eq('mailbox_id', mailbox_id)
        if status:
            count_query = count_query.eq('status', status.value)
        count_result = count_query.execute()
        total = count_result.count if count_result.count else len(count_result.data)

        return ExtractionJobListResponse(
            jobs=[ExtractionJobResponse(**job) for job in result.data],
            total=total
        )

    except Exception as e:
        logger.error(f"Failed to list extraction jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/extraction/jobs/{job_id}/cancel")
async def cancel_extraction_job(job_id: str):
    """
    Cancel a running extraction job.

    Args:
        job_id: Extraction job UUID

    Returns:
        Success message
    """
    try:
        # Check if job exists and is cancellable
        job_check = _supabase.table('extraction_jobs').select('id, status').eq(
            'id', job_id
        ).single().execute()

        if not job_check.data:
            raise HTTPException(status_code=404, detail="Extraction job not found")

        if job_check.data['status'] not in ['pending', 'processing']:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot cancel job with status '{job_check.data['status']}'"
            )

        # Update status to failed with cancellation message
        _supabase.table('extraction_jobs').update({
            'status': 'failed',
            'errors': ['Job cancelled by user'],
            'updated_at': datetime.utcnow().isoformat()
        }).eq('id', job_id).execute()

        return {
            "message": "Extraction job cancelled successfully",
            "job_id": job_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel extraction job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/extraction/progress/{job_id}", response_model=ExtractionProgressResponse)
async def get_extraction_progress(job_id: str):
    """
    Get real-time extraction progress from Redis.

    Args:
        job_id: Extraction job UUID

    Returns:
        Real-time progress information
    """
    try:
        from ..database.redis_client import JobProgressManager

        # Try Redis first for real-time progress
        try:
            redis_manager = JobProgressManager()
            progress = redis_manager.get_progress(job_id)

            if progress:
                return ExtractionProgressResponse(
                    job_id=job_id,
                    **progress
                )
        except Exception as e:
            logger.warning(f"Redis unavailable, falling back to database: {e}")

        # Fallback to database
        result = _supabase.table('extraction_jobs').select(
            'status, current_step, current_step_number, total_steps, mailbox_id, client_id, errors'
        ).eq('id', job_id).single().execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Extraction job not found")

        job = result.data

        return ExtractionProgressResponse(
            job_id=job_id,
            status=job['status'],
            current_step=job.get('current_step'),
            current_step_number=job.get('current_step_number'),
            total_steps=job.get('total_steps'),
            mailbox_id=job.get('mailbox_id'),
            client_id=job.get('client_id'),
            error=job.get('errors', [None])[0] if job.get('errors') else None
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get extraction progress: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# CONTACT ANALYTICS ENDPOINTS (6 endpoints)
# ============================================================================

CONTACT_SORT_COLUMNS = {
    'engagement_score', 'full_name', 'email_address',
    'total_emails_sent', 'total_emails_received',
    'last_contacted_at', 'created_at', 'company_name',
}

COMPANY_SORT_COLUMNS = {
    'engagement_score', 'company_name', 'total_emails',
    'contact_count', 'decision_maker_count',
    'last_contact_date', 'created_at',
}

THREAD_SORT_COLUMNS = {
    'last_message_at', 'message_count', 'days_since_last_email',
    'status', 'created_at', 'subject',
}


@router.get("/contacts", response_model=ContactAnalyticsListResponse)
async def list_contact_analytics(
    client_id: Optional[str] = Query(default=None),
    company_id: Optional[str] = Query(default=None),
    contact_type: Optional[ContactType] = Query(default=None),
    is_decision_maker: Optional[bool] = Query(default=None),
    min_engagement_score: Optional[float] = Query(default=None, ge=0, le=100),
    search: Optional[str] = Query(default=None, description="Search by name, email, or company"),
    sort_by: Optional[str] = Query(default=None, description="Sort column"),
    sort_dir: str = Query(default="desc", description="asc or desc"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0)
):
    """
    List contacts with analytics data.

    Args:
        client_id: Filter by client
        company_id: Filter by company
        contact_type: Filter by contact type
        is_decision_maker: Filter decision makers only
        min_engagement_score: Minimum engagement score
        limit: Maximum number of results
        offset: Offset for pagination

    Returns:
        List of contacts with analytics
    """
    try:
        query = _supabase.table('customer_contacts').select(
            '''
            id, email_address, full_name, job_title, company_name,
            customer_company_id, client_id, contact_type,
            is_decision_maker, seniority_level,
            engagement_score, total_emails_sent, total_emails_received,
            first_contacted_at, last_contacted_at,
            initiation_ratio, reply_rate, avg_response_time_seconds, avg_thread_depth,
            created_at, updated_at,
            customer_companies!customer_contacts_customer_company_id_fkey(company_name)
            '''
        )

        if client_id:
            query = query.eq('client_id', client_id)
        if company_id:
            query = query.eq('customer_company_id', company_id)
        if contact_type:
            query = query.eq('contact_type', contact_type.value)
        if is_decision_maker is not None:
            # Use lowercase string for boolean filter (PostgREST requirement)
            query = query.eq('is_decision_maker', 'true' if is_decision_maker else 'false')
        if min_engagement_score is not None:
            query = query.gte('engagement_score', int(min_engagement_score))
        if search and search.strip():
            term = search.strip()
            query = query.or_(f"full_name.ilike.%{term}%,email_address.ilike.%{term}%,company_name.ilike.%{term}%")

        effective_sort = sort_by if sort_by in CONTACT_SORT_COLUMNS else 'engagement_score'
        desc = sort_dir.lower() != 'asc'
        result = query.order(effective_sort, desc=desc, nullsfirst=False).range(offset, offset + limit - 1).execute()

        contacts = []
        for c in result.data:
            customer_company_name = None
            if c.get('customer_companies'):
                customer_company_name = c['customer_companies'].get('company_name')

            contacts.append(ContactAnalytics(
                **c,
                customer_company_name=customer_company_name
            ))

        # Get total count
        count_query = _supabase.table('customer_contacts').select('id', count='exact')
        if client_id:
            count_query = count_query.eq('client_id', client_id)
        if company_id:
            count_query = count_query.eq('customer_company_id', company_id)
        if contact_type:
            count_query = count_query.eq('contact_type', contact_type.value)
        if is_decision_maker is not None:
            count_query = count_query.eq('is_decision_maker', 'true' if is_decision_maker else 'false')
        if min_engagement_score is not None:
            count_query = count_query.gte('engagement_score', int(min_engagement_score))
        if search and search.strip():
            term = search.strip()
            count_query = count_query.or_(f"full_name.ilike.%{term}%,email_address.ilike.%{term}%,company_name.ilike.%{term}%")

        count_result = count_query.execute()
        total = count_result.count if count_result.count else len(count_result.data)

        return ContactAnalyticsListResponse(contacts=contacts, total=total)

    except Exception as e:
        logger.error(f"Failed to list contact analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/contacts/top-engaged", response_model=List[TopEngagedContact])
async def get_top_engaged_contacts(
    client_id: Optional[str] = Query(default=None),
    limit: int = Query(default=10, ge=1, le=100)
):
    """
    Get top engaged contacts.

    Args:
        client_id: Filter by client
        limit: Number of results (default 10)

    Returns:
        List of top engaged contacts
    """
    try:
        query = _supabase.table('customer_contacts').select(
            'id, email_address, full_name, company_name, engagement_score, total_emails_sent, total_emails_received, last_contacted_at'
        ).not_.is_('engagement_score', 'null')

        if client_id:
            query = query.eq('client_id', client_id)

        result = query.order('engagement_score', desc=True).limit(limit).execute()

        return [
            TopEngagedContact(
                id=c['id'],
                email_address=c['email_address'],
                full_name=c.get('full_name'),
                company_name=c.get('company_name'),
                engagement_score=c['engagement_score'],
                total_emails=(c.get('total_emails_sent', 0) or 0) + (c.get('total_emails_received', 0) or 0),
                last_contacted_at=c.get('last_contacted_at')
            )
            for c in result.data
        ]

    except Exception as e:
        logger.error(f"Failed to get top engaged contacts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/contacts/at-risk", response_model=List[AtRiskContact])
async def get_at_risk_contacts(
    client_id: Optional[str] = Query(default=None),
    days_threshold: int = Query(default=60, ge=1),
    limit: int = Query(default=50, ge=1, le=500)
):
    """
    Get at-risk contacts (no contact in N days).

    Args:
        client_id: Filter by client
        days_threshold: Days since last contact (default 60)
        limit: Maximum number of results

    Returns:
        List of at-risk contacts
    """
    try:
        cutoff_date = (datetime.utcnow() - timedelta(days=days_threshold)).isoformat()
        now = datetime.utcnow()

        # Get contacts with old last_contacted_at
        query = _supabase.table('customer_contacts').select(
            'id, email_address, full_name, company_name, last_contacted_at, engagement_score'
        ).not_.is_('last_contacted_at', 'null').lte('last_contacted_at', cutoff_date)

        if client_id:
            query = query.eq('client_id', client_id)

        result = query.order('last_contacted_at').limit(limit).execute()

        # Also get contacts with NULL last_contacted_at (never contacted = at risk)
        null_query = _supabase.table('customer_contacts').select(
            'id, email_address, full_name, company_name, last_contacted_at, engagement_score'
        ).is_('last_contacted_at', 'null')

        if client_id:
            null_query = null_query.eq('client_id', client_id)

        null_result = null_query.limit(limit).execute()

        at_risk = []
        # Contacts with null last_contacted_at first (most at-risk)
        for c in (null_result.data or []):
            at_risk.append(AtRiskContact(
                id=c['id'],
                email_address=c['email_address'],
                full_name=c.get('full_name'),
                company_name=c.get('company_name'),
                last_contacted_at=None,
                days_since_contact=999,
                engagement_score=c.get('engagement_score')
            ))

        for c in (result.data or []):
            last_contact = datetime.fromisoformat(c['last_contacted_at'].replace('Z', '+00:00'))
            days_since = (now - last_contact.replace(tzinfo=None)).days

            at_risk.append(AtRiskContact(
                id=c['id'],
                email_address=c['email_address'],
                full_name=c.get('full_name'),
                company_name=c.get('company_name'),
                last_contacted_at=c['last_contacted_at'],
                days_since_contact=days_since,
                engagement_score=c.get('engagement_score')
            ))

        return at_risk[:limit]

    except Exception as e:
        logger.error(f"Failed to get at-risk contacts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/contacts/decision-makers", response_model=ContactAnalyticsListResponse)
async def get_decision_makers(
    client_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0)
):
    """
    Get decision makers only.

    Args:
        client_id: Filter by client
        limit: Maximum number of results
        offset: Offset for pagination

    Returns:
        List of decision maker contacts
    """
    try:
        query = _supabase.table('customer_contacts').select(
            '''
            id, email_address, full_name, job_title, company_name,
            customer_company_id, client_id, contact_type,
            is_decision_maker, seniority_level,
            engagement_score, total_emails_sent, total_emails_received,
            first_contacted_at, last_contacted_at,
            created_at, updated_at,
            customer_companies!customer_contacts_customer_company_id_fkey(company_name)
            '''
        ).eq('is_decision_maker', 'true')  # Use lowercase string

        if client_id:
            query = query.eq('client_id', client_id)

        result = query.order('engagement_score', desc=True).range(offset, offset + limit - 1).execute()

        contacts = []
        for c in result.data:
            customer_company_name = None
            if c.get('customer_companies'):
                customer_company_name = c['customer_companies'].get('company_name')

            contacts.append(ContactAnalytics(**c, customer_company_name=customer_company_name))

        # Get total count
        count_query = _supabase.table('customer_contacts').select('id', count='exact').eq('is_decision_maker', 'true')
        if client_id:
            count_query = count_query.eq('client_id', client_id)
        count_result = count_query.execute()
        total = count_result.count if count_result.count else len(count_result.data)

        return ContactAnalyticsListResponse(contacts=contacts, total=total)

    except Exception as e:
        logger.error(f"Failed to get decision makers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/contacts/by-type", response_model=List[ContactTypeGrouping])
async def group_contacts_by_type(client_id: Optional[str] = Query(default=None)):
    """
    Group contacts by contact type.

    Args:
        client_id: Filter by client

    Returns:
        Contact counts grouped by type
    """
    try:
        # Fetch all contacts for this client
        query = _supabase.table('customer_contacts').select('contact_type, engagement_score')

        if client_id:
            query = query.eq('client_id', client_id)

        result = query.execute()

        # Group by type in memory
        from collections import defaultdict
        type_groups = defaultdict(lambda: {'count': 0, 'scores': []})

        for c in result.data:
            contact_type = c.get('contact_type', 'unknown')
            type_groups[contact_type]['count'] += 1
            if c.get('engagement_score') is not None:
                type_groups[contact_type]['scores'].append(c['engagement_score'])

        # Calculate averages and build response
        groupings = []
        for contact_type, data in type_groups.items():
            avg_score = None
            if data['scores']:
                avg_score = sum(data['scores']) / len(data['scores'])

            groupings.append(ContactTypeGrouping(
                contact_type=ContactType(contact_type),
                count=data['count'],
                avg_engagement_score=avg_score
            ))

        return sorted(groupings, key=lambda x: x.count, reverse=True)

    except Exception as e:
        logger.error(f"Failed to group contacts by type: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# NOTE: Parameterized route MUST be after all static /contacts/* routes to avoid
# FastAPI matching "top-engaged", "at-risk", etc. as {contact_identifier}
@router.get("/contacts/{contact_identifier}", response_model=ContactAnalytics)
async def get_contact_analytics(contact_identifier: str):
    """
    Get single contact with full analytics.

    Args:
        contact_identifier: Contact UUID or email address

    Returns:
        Contact with analytics data
    """
    try:
        # Check if identifier is an email (contains @) or UUID
        if '@' in contact_identifier:
            # Query by email address
            filter_field = 'email_address'
            filter_value = contact_identifier
        else:
            # Query by UUID
            filter_field = 'id'
            filter_value = contact_identifier

        result = _supabase.table('customer_contacts').select(
            '''
            id, email_address, full_name, job_title, company_name,
            customer_company_id, client_id, contact_type,
            is_decision_maker, seniority_level,
            engagement_score, total_emails_sent, total_emails_received,
            first_contacted_at, last_contacted_at,
            initiation_ratio, reply_rate, avg_response_time_seconds, avg_thread_depth,
            created_at, updated_at,
            customer_companies!customer_contacts_customer_company_id_fkey(company_name)
            '''
        ).eq(filter_field, filter_value).single().execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Contact not found")

        c = result.data
        customer_company_name = None
        if c.get('customer_companies'):
            customer_company_name = c['customer_companies'].get('company_name')

        return ContactAnalytics(**c, customer_company_name=customer_company_name)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get contact analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/contacts/{contact_id}/emails")
async def get_contact_emails(contact_id: str, limit: int = 50, offset: int = 0):
    """Get emails linked to a contact via customer_contact_id."""
    try:
        # Get total count + sent count (outbound)
        count_result = _supabase.table('emails').select(
            'id', count='exact'
        ).eq('customer_contact_id', contact_id).execute()
        total = count_result.count or 0

        sent_result = _supabase.table('emails').select(
            'id', count='exact'
        ).eq('customer_contact_id', contact_id).eq('is_outbound', 'true').execute()
        total_sent = sent_result.count or 0
        total_received = total - total_sent

        # Paginated data
        result = _supabase.table('emails').select(
            'id, subject, sender_email, sender_name, sent_date, folder_path, is_outbound'
        ).eq('customer_contact_id', contact_id).order(
            'sent_date', desc=True
        ).range(offset, offset + limit - 1).execute()

        return {'emails': result.data or [], 'total': total, 'total_sent': total_sent, 'total_received': total_received}

    except Exception as e:
        logger.error(f"Failed to get contact emails: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# COMPANY ANALYTICS ENDPOINTS (5 endpoints)
# ============================================================================

@router.get("/companies", response_model=CompanyAnalyticsListResponse)
async def list_company_analytics(
    client_id: Optional[str] = Query(default=None),
    engagement_status: Optional[EngagementStatus] = Query(default=None),
    min_engagement_score: Optional[float] = Query(default=None, ge=0, le=100),
    sort_by: Optional[str] = Query(default=None, description="Sort column"),
    sort_dir: str = Query(default="desc", description="asc or desc"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0)
):
    """
    List companies with analytics data.

    Args:
        client_id: Filter by client
        engagement_status: Filter by engagement status
        min_engagement_score: Minimum engagement score
        limit: Maximum number of results
        offset: Offset for pagination

    Returns:
        List of companies with analytics
    """
    try:
        query = _supabase.table('customer_companies').select(
            '''
            id, company_name, client_id, email_domains, industry,
            engagement_score, total_emails, total_inbound, total_outbound,
            first_contact_date, last_contact_date,
            contact_count, decision_maker_count,
            created_at, updated_at,
            clients(client_name)
            '''
        )

        if client_id:
            query = query.eq('client_id', client_id)
        if min_engagement_score is not None:
            query = query.gte('engagement_score', int(min_engagement_score))

        effective_sort = sort_by if sort_by in COMPANY_SORT_COLUMNS else 'engagement_score'
        desc = sort_dir.lower() != 'asc'
        result = query.order(effective_sort, desc=desc, nullsfirst=False).range(offset, offset + limit - 1).execute()

        # Calculate engagement status for each company
        def calculate_engagement_status(last_contact_date):
            if not last_contact_date:
                return EngagementStatus.UNKNOWN

            if isinstance(last_contact_date, str):
                last_contact_date = datetime.fromisoformat(last_contact_date.replace('Z', '+00:00'))

            now = datetime.utcnow()
            days_since = (now - last_contact_date.replace(tzinfo=None)).days

            if days_since <= 30:
                return EngagementStatus.ACTIVE
            elif days_since <= 90:
                return EngagementStatus.QUIET
            else:
                return EngagementStatus.AT_RISK

        companies = []
        for comp in result.data:
            status = calculate_engagement_status(comp.get('last_contact_date'))

            # Apply engagement_status filter
            if engagement_status and status != engagement_status:
                continue

            client_name = None
            if comp.get('clients'):
                client_name = comp['clients'].get('client_name')

            companies.append(CompanyAnalytics(
                **comp,
                engagement_status=status,
                client_name=client_name
            ))

        # Get total count
        count_query = _supabase.table('customer_companies').select('id', count='exact')
        if client_id:
            count_query = count_query.eq('client_id', client_id)
        if min_engagement_score is not None:
            count_query = count_query.gte('engagement_score', int(min_engagement_score))
        count_result = count_query.execute()
        total = count_result.count if count_result.count else len(count_result.data)

        return CompanyAnalyticsListResponse(companies=companies, total=total)

    except Exception as e:
        logger.error(f"Failed to list company analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/companies/top-engaged", response_model=List[TopEngagedCompany])
async def get_top_engaged_companies(
    client_id: Optional[str] = Query(default=None),
    limit: int = Query(default=10, ge=1, le=100)
):
    """
    Get top engaged companies.

    Args:
        client_id: Filter by client
        limit: Number of results (default 10)

    Returns:
        List of top engaged companies
    """
    try:
        query = _supabase.table('customer_companies').select(
            'id, company_name, engagement_score, total_emails, contact_count, last_contact_date'
        ).not_.is_('engagement_score', 'null')

        if client_id:
            query = query.eq('client_id', client_id)

        result = query.order('engagement_score', desc=True).limit(limit).execute()

        return [
            TopEngagedCompany(
                id=comp['id'],
                company_name=comp['company_name'],
                engagement_score=comp['engagement_score'],
                total_emails=comp.get('total_emails', 0) or 0,
                contact_count=comp.get('contact_count', 0) or 0,
                last_contact_date=comp.get('last_contact_date')
            )
            for comp in result.data
        ]

    except Exception as e:
        logger.error(f"Failed to get top engaged companies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/companies/at-risk", response_model=List[AtRiskCompany])
async def get_at_risk_companies(
    client_id: Optional[str] = Query(default=None),
    days_threshold: int = Query(default=90, ge=1),
    limit: int = Query(default=50, ge=1, le=500)
):
    """
    Get at-risk companies (no contact in N days).

    Args:
        client_id: Filter by client
        days_threshold: Days since last contact (default 90)
        limit: Maximum number of results

    Returns:
        List of at-risk companies
    """
    try:
        cutoff_date = (datetime.utcnow() - timedelta(days=days_threshold)).isoformat()
        now = datetime.utcnow()

        # Companies with old last_contact_date
        query = _supabase.table('customer_companies').select(
            'id, company_name, last_contact_date, contact_count, engagement_score'
        ).not_.is_('last_contact_date', 'null').lte('last_contact_date', cutoff_date)

        if client_id:
            query = query.eq('client_id', client_id)

        result = query.order('last_contact_date').limit(limit).execute()

        # Also get companies with NULL last_contact_date (never contacted = at risk)
        null_query = _supabase.table('customer_companies').select(
            'id, company_name, last_contact_date, contact_count, engagement_score'
        ).is_('last_contact_date', 'null')

        if client_id:
            null_query = null_query.eq('client_id', client_id)

        null_result = null_query.limit(limit).execute()

        at_risk = []
        # Companies with null last_contact_date first (most at-risk)
        for comp in (null_result.data or []):
            at_risk.append(AtRiskCompany(
                id=comp['id'],
                company_name=comp['company_name'],
                last_contact_date=None,
                days_since_contact=999,
                contact_count=comp.get('contact_count', 0) or 0,
                engagement_score=comp.get('engagement_score')
            ))

        for comp in (result.data or []):
            last_contact = datetime.fromisoformat(comp['last_contact_date'].replace('Z', '+00:00'))
            days_since = (now - last_contact.replace(tzinfo=None)).days

            at_risk.append(AtRiskCompany(
                id=comp['id'],
                company_name=comp['company_name'],
                last_contact_date=comp['last_contact_date'],
                days_since_contact=days_since,
                contact_count=comp.get('contact_count', 0) or 0,
                engagement_score=comp.get('engagement_score')
            ))

        return at_risk[:limit]

    except Exception as e:
        logger.error(f"Failed to get at-risk companies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/companies/by-engagement", response_model=List[EngagementStatusGrouping])
async def group_companies_by_engagement(client_id: Optional[str] = Query(default=None)):
    """
    Group companies by engagement status.

    Args:
        client_id: Filter by client

    Returns:
        Company counts grouped by engagement status
    """
    try:
        query = _supabase.table('customer_companies').select('last_contact_date, engagement_score')

        if client_id:
            query = query.eq('client_id', client_id)

        result = query.execute()

        # Calculate engagement status and group
        from collections import defaultdict
        status_groups = defaultdict(lambda: {'count': 0, 'scores': []})

        def calculate_engagement_status(last_contact_date):
            if not last_contact_date:
                return EngagementStatus.UNKNOWN

            if isinstance(last_contact_date, str):
                last_contact_date = datetime.fromisoformat(last_contact_date.replace('Z', '+00:00'))

            now = datetime.utcnow()
            days_since = (now - last_contact_date.replace(tzinfo=None)).days

            if days_since <= 30:
                return EngagementStatus.ACTIVE
            elif days_since <= 90:
                return EngagementStatus.QUIET
            else:
                return EngagementStatus.AT_RISK

        for comp in result.data:
            status = calculate_engagement_status(comp.get('last_contact_date'))
            status_groups[status.value]['count'] += 1
            if comp.get('engagement_score') is not None:
                status_groups[status.value]['scores'].append(comp['engagement_score'])

        # Build response
        groupings = []
        for status, data in status_groups.items():
            avg_score = None
            if data['scores']:
                avg_score = sum(data['scores']) / len(data['scores'])

            groupings.append(EngagementStatusGrouping(
                engagement_status=EngagementStatus(status),
                count=data['count'],
                avg_engagement_score=avg_score
            ))

        return sorted(groupings, key=lambda x: x.count, reverse=True)

    except Exception as e:
        logger.error(f"Failed to group companies by engagement: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# NOTE: Parameterized route MUST be after all static /companies/* routes to avoid
# FastAPI matching "top-engaged", "at-risk", etc. as {company_id}
@router.get("/companies/{company_id}", response_model=CompanyAnalytics)
async def get_company_analytics(company_id: str):
    """
    Get single company with full analytics.

    Args:
        company_id: Company UUID

    Returns:
        Company with analytics data
    """
    try:
        result = _supabase.table('customer_companies').select(
            '''
            id, company_name, client_id, email_domains, industry,
            engagement_score, total_emails, total_inbound, total_outbound,
            first_contact_date, last_contact_date,
            contact_count, decision_maker_count,
            created_at, updated_at,
            clients(client_name)
            '''
        ).eq('id', company_id).single().execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Company not found")

        comp = result.data

        # Calculate engagement status
        def calculate_engagement_status(last_contact_date):
            if not last_contact_date:
                return EngagementStatus.UNKNOWN

            if isinstance(last_contact_date, str):
                last_contact_date = datetime.fromisoformat(last_contact_date.replace('Z', '+00:00'))

            now = datetime.utcnow()
            days_since = (now - last_contact_date.replace(tzinfo=None)).days

            if days_since <= 30:
                return EngagementStatus.ACTIVE
            elif days_since <= 90:
                return EngagementStatus.QUIET
            else:
                return EngagementStatus.AT_RISK

        status = calculate_engagement_status(comp.get('last_contact_date'))

        client_name = None
        if comp.get('clients'):
            client_name = comp['clients'].get('client_name')

        return CompanyAnalytics(**comp, engagement_status=status, client_name=client_name)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get company analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/companies/{company_id}/emails")
async def get_company_emails(company_id: str, limit: int = 50, offset: int = 0):
    """Get emails linked to contacts of a company."""
    try:
        # Get all contact IDs for this company
        contacts_result = _supabase.table('customer_contacts').select('id').eq(
            'customer_company_id', company_id
        ).execute()

        contact_ids = [c['id'] for c in (contacts_result.data or [])]
        if not contact_ids:
            return {'emails': [], 'total': 0}

        # Get total count + sent/received across all contacts
        total = 0
        total_sent = 0
        for i in range(0, len(contact_ids), 500):
            batch = contact_ids[i:i+500]
            count_result = _supabase.table('emails').select(
                'id', count='exact'
            ).in_('customer_contact_id', batch).execute()
            total += count_result.count or 0
            sent_result = _supabase.table('emails').select(
                'id', count='exact'
            ).in_('customer_contact_id', batch).eq('is_outbound', 'true').execute()
            total_sent += sent_result.count or 0
        total_received = total - total_sent

        # Fetch paginated emails — collect from all batches, then sort & slice
        all_emails = []
        for i in range(0, len(contact_ids), 500):
            batch = contact_ids[i:i+500]
            result = _supabase.table('emails').select(
                'id, subject, sender_email, sender_name, sent_date, folder_path, is_outbound'
            ).in_('customer_contact_id', batch).order(
                'sent_date', desc=True
            ).range(0, offset + limit - 1).execute()
            all_emails.extend(result.data or [])

        # Sort combined results and apply pagination
        all_emails.sort(key=lambda e: e.get('sent_date', ''), reverse=True)
        paginated = all_emails[offset:offset + limit]

        return {'emails': paginated, 'total': total, 'total_sent': total_sent, 'total_received': total_received}

    except Exception as e:
        logger.error(f"Failed to get company emails: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# THREAD ANALYTICS ENDPOINTS (4 endpoints)
# ============================================================================

# Map database thread status values to ThreadStatus enum
# DB: complete, awaiting_reply, overdue, dropped, outbound_pending, stale
# Enum: complete, awaiting_response, awaiting_our_response, overdue, dropped, ongoing
_THREAD_STATUS_MAP = {
    'complete': ThreadStatus.COMPLETE,
    'awaiting_reply': ThreadStatus.AWAITING_RESPONSE,
    'overdue': ThreadStatus.OVERDUE,
    'dropped': ThreadStatus.DROPPED,
    'outbound_pending': ThreadStatus.AWAITING_OUR_RESPONSE,
    'stale': ThreadStatus.DROPPED,
    'ongoing': ThreadStatus.ONGOING,
    # Also accept enum values directly
    'awaiting_response': ThreadStatus.AWAITING_RESPONSE,
    'awaiting_our_response': ThreadStatus.AWAITING_OUR_RESPONSE,
}

def _map_thread_status(db_status: str) -> ThreadStatus:
    return _THREAD_STATUS_MAP.get(db_status, ThreadStatus.COMPLETE)

@router.get("/threads/status", response_model=ThreadStatusListResponse)
async def list_thread_statuses(
    client_id: Optional[str] = Query(default=None),
    mailbox_id: Optional[str] = Query(default=None),
    status: Optional[ThreadStatus] = Query(default=None),
    sort_by: Optional[str] = Query(default=None, description="Sort column"),
    sort_dir: str = Query(default="desc", description="asc or desc"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0)
):
    """
    List thread statuses with filters.

    Args:
        client_id: Filter by client
        mailbox_id: Filter by mailbox
        status: Filter by thread status
        limit: Maximum number of results
        offset: Offset for pagination

    Returns:
        List of thread statuses
    """
    try:
        query = _supabase.table('thread_status').select(
            '''
            thread_id, subject, customer_contact_id, customer_company_id,
            status, message_count, last_message_at, last_sender_is_outbound, days_since_last_email,
            mailbox_id, created_at
            '''
        )

        # Apply client_id filter via mailbox_id lookup
        mailbox_ids = []
        if client_id:
            mailbox_result = _supabase.table('mailboxes').select('id').eq('client_id', client_id).execute()
            mailbox_ids = [m['id'] for m in (mailbox_result.data or [])]
            if mailbox_ids:
                query = query.in_('mailbox_id', mailbox_ids[:500])
            else:
                # No mailboxes for client → return empty
                return ThreadStatusListResponse(threads=[], total=0)
        elif mailbox_id:
            query = query.eq('mailbox_id', mailbox_id)

        if status:
            query = query.eq('status', status.value)

        effective_sort = sort_by if sort_by in THREAD_SORT_COLUMNS else 'last_message_at'
        desc = sort_dir.lower() != 'asc'
        result = query.order(effective_sort, desc=desc, nullsfirst=False).range(offset, offset + limit - 1).execute()

        # Fetch contact/company names for enrichment
        threads = []
        for t in result.data:
            # Map database column names to model field names
            thread_data = {
                'thread_id': t.get('thread_id'),
                'subject': t.get('subject'),
                'contact_id': t.get('customer_contact_id'),
                'company_id': t.get('customer_company_id'),
                'status': _map_thread_status(t.get('status', 'complete')),
                'total_messages': t.get('message_count', 0),
                'last_message_date': t.get('last_message_at'),
                'last_sender_type': 'outbound' if t.get('last_sender_is_outbound') else 'inbound',
                'days_since_last_message': t.get('days_since_last_email', 0),
                'created_at': t.get('created_at')
            }

            thread = ThreadStatusSummary(**thread_data)

            # Enrich with contact info if available
            if t.get('customer_contact_id'):
                contact_result = _supabase.table('customer_contacts').select(
                    'email_address, full_name'
                ).eq('id', t['customer_contact_id']).execute()
                if contact_result.data:
                    thread.contact_email = contact_result.data[0].get('email_address')
                    thread.contact_name = contact_result.data[0].get('full_name')

            # Enrich with company name if available
            if t.get('customer_company_id'):
                company_result = _supabase.table('customer_companies').select(
                    'company_name'
                ).eq('id', t['customer_company_id']).execute()
                if company_result.data:
                    thread.company_name = company_result.data[0].get('company_name')

            threads.append(thread)

        # Get total count (same filters)
        count_query = _supabase.table('thread_status').select('thread_id', count='exact')
        if client_id and mailbox_ids:
            count_query = count_query.in_('mailbox_id', mailbox_ids[:500])
        elif mailbox_id:
            count_query = count_query.eq('mailbox_id', mailbox_id)
        if status:
            count_query = count_query.eq('status', status.value)
        count_result = count_query.execute()
        total = count_result.count if count_result.count else len(count_result.data)

        return ThreadStatusListResponse(threads=threads, total=total)

    except Exception as e:
        logger.error(f"Failed to list thread statuses: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/threads/overdue", response_model=List[OverdueThread])
async def get_overdue_threads(
    client_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500)
):
    """
    Get overdue threads only.

    Args:
        client_id: Filter by client
        limit: Maximum number of results

    Returns:
        List of overdue threads
    """
    try:
        result = _supabase.table('thread_status').select(
            'thread_id, subject, customer_contact_id, customer_company_id, last_message_at, days_since_last_email'
        ).eq('status', ThreadStatus.OVERDUE.value).order(
            'days_since_last_email', desc=True
        ).limit(limit).execute()

        threads = []
        for t in result.data:
            contact_email = None
            contact_name = None
            company_name = None

            # Enrich with contact info
            if t.get('customer_contact_id'):
                contact_result = _supabase.table('customer_contacts').select(
                    'email_address, full_name'
                ).eq('id', t['customer_contact_id']).execute()
                if contact_result.data:
                    contact_email = contact_result.data[0].get('email_address')
                    contact_name = contact_result.data[0].get('full_name')

            # Enrich with company name
            if t.get('customer_company_id'):
                company_result = _supabase.table('customer_companies').select(
                    'company_name'
                ).eq('id', t['customer_company_id']).execute()
                if company_result.data:
                    company_name = company_result.data[0].get('company_name')

            threads.append(OverdueThread(
                thread_id=t['thread_id'],
                subject=t.get('subject'),
                contact_email=contact_email,
                contact_name=contact_name,
                company_name=company_name,
                last_message_date=t.get('last_message_at'),  # Map database column to model field
                days_overdue=t.get('days_since_last_email', 0)
            ))

        return threads

    except Exception as e:
        logger.error(f"Failed to get overdue threads: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/threads/by-status", response_model=List[ThreadStatusCount])
async def count_threads_by_status(client_id: Optional[str] = Query(default=None)):
    """
    Count threads by status.

    Args:
        client_id: Filter by client

    Returns:
        Thread counts grouped by status
    """
    try:
        result = _supabase.table('thread_status').select('status').execute()

        # Count by status in memory
        from collections import Counter
        status_counts = Counter()

        for t in result.data:
            status = t.get('status', 'unknown')
            status_counts[status] += 1

        result_list = []
        for status, count in status_counts.items():
            enum_val = _map_thread_status(status)
            result_list.append(ThreadStatusCount(status=enum_val, count=count))

        return result_list

    except Exception as e:
        logger.error(f"Failed to count threads by status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/threads/by-contact/{contact_id}", response_model=ThreadStatusListResponse)
async def get_contact_threads(
    contact_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0)
):
    """
    Get all threads for a specific contact.

    Args:
        contact_id: Contact UUID
        limit: Maximum number of results
        offset: Offset for pagination

    Returns:
        List of thread statuses for contact
    """
    try:
        result = _supabase.table('thread_status').select(
            '''
            thread_id, subject, customer_contact_id, customer_company_id,
            status, message_count, last_message_at, last_sender_is_outbound, days_since_last_email,
            created_at
            '''
        ).eq('customer_contact_id', contact_id).order(
            'last_message_at', desc=True
        ).range(offset, offset + limit - 1).execute()

        # Fetch contact/company info once
        contact_info = _supabase.table('customer_contacts').select(
            'email_address, full_name, customer_company_id, customer_companies!customer_contacts_customer_company_id_fkey(company_name)'
        ).eq('id', contact_id).single().execute()

        contact_email = None
        contact_name = None
        company_name = None

        if contact_info.data:
            contact_email = contact_info.data.get('email_address')
            contact_name = contact_info.data.get('full_name')
            if contact_info.data.get('customer_companies'):
                company_name = contact_info.data['customer_companies'].get('company_name')

        threads = []
        for t in result.data:
            # Map database column names to model field names
            thread_data = {
                'thread_id': t.get('thread_id'),
                'subject': t.get('subject'),
                'contact_id': t.get('customer_contact_id'),
                'company_id': t.get('customer_company_id'),
                'status': _map_thread_status(t.get('status', 'complete')),
                'total_messages': t.get('message_count', 0),
                'last_message_date': t.get('last_message_at'),
                'last_sender_type': 'outbound' if t.get('last_sender_is_outbound') else 'inbound',
                'days_since_last_message': t.get('days_since_last_email', 0),
                'created_at': t.get('created_at'),
                'contact_email': contact_email,
                'contact_name': contact_name,
                'company_name': company_name
            }
            threads.append(ThreadStatusSummary(**thread_data))

        # Get total count
        count_result = _supabase.table('thread_status').select(
            'thread_id', count='exact'
        ).eq('customer_contact_id', contact_id).execute()
        total = count_result.count if count_result.count else len(count_result.data)

        return ThreadStatusListResponse(threads=threads, total=total)

    except Exception as e:
        logger.error(f"Failed to get contact threads: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# RESPONSE TIME ANALYTICS ENDPOINTS (4 endpoints)
# ============================================================================

@router.get("/response-times", response_model=ResponseTimeListResponse)
async def list_response_times(
    client_id: Optional[str] = Query(default=None),
    contact_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0)
):
    """
    List response time metrics with filters.

    Args:
        client_id: Filter by client
        contact_id: Filter by contact
        limit: Maximum number of results
        offset: Offset for pagination

    Returns:
        List of response time metrics
    """
    try:
        query = _supabase.table('email_response_metrics').select(
            '''
            id, email_id, responding_to_email_id, responder_contact_id, responder_company_id,
            response_time_seconds, business_hours_response_time_seconds, is_auto_reply, created_at, updated_at
            '''
        )

        if contact_id:
            query = query.eq('responder_contact_id', contact_id)

        result = query.order('created_at', desc=True).range(offset, offset + limit - 1).execute()

        # Enrich with contact email
        metrics = []
        for m in result.data:
            contact_email = None
            if m.get('responder_contact_id'):
                contact_result = _supabase.table('customer_contacts').select(
                    'email_address'
                ).eq('id', m['responder_contact_id']).execute()
                if contact_result.data:
                    contact_email = contact_result.data[0].get('email_address')

            metrics.append(ResponseTimeMetric(**m, contact_email=contact_email))

        # Get total count
        count_query = _supabase.table('email_response_metrics').select('id', count='exact')
        if contact_id:
            count_query = count_query.eq('responder_contact_id', contact_id)
        count_result = count_query.execute()
        total = count_result.count if count_result.count else len(count_result.data)

        return ResponseTimeListResponse(metrics=metrics, total=total)

    except Exception as e:
        logger.error(f"Failed to list response times: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/response-times/stats", response_model=ResponseTimeStats)
async def get_response_time_stats(
    client_id: Optional[str] = Query(default=None),
    contact_id: Optional[str] = Query(default=None)
):
    """
    Get aggregate response time statistics.

    Args:
        client_id: Filter by client
        contact_id: Filter by contact

    Returns:
        Aggregate statistics
    """
    try:
        query = _supabase.table('email_response_metrics').select(
            'response_time_seconds, business_hours_response_time_seconds, is_auto_reply, email_id'
        )

        if contact_id:
            query = query.eq('responder_contact_id', contact_id)

        result = query.execute()

        if not result.data:
            return ResponseTimeStats(
                total_responses=0,
                avg_response_time_hours=0,
                median_response_time_hours=None,
                min_response_time_hours=0,
                max_response_time_hours=0,
                avg_business_hours_response_time_hours=None,
                median_business_hours_response_time_hours=None,
                our_avg_response_time=None,
                their_avg_response_time=None,
                auto_reply_count=0,
                auto_reply_percentage=0
            )

        # Convert seconds to hours
        response_times_hours = [m['response_time_seconds'] / 3600.0 for m in result.data if m.get('response_time_seconds')]
        bh_times_hours = [m['business_hours_response_time_seconds'] / 3600.0 for m in result.data if m.get('business_hours_response_time_seconds')]
        auto_replies = sum(1 for m in result.data if m.get('is_auto_reply') is True)

        import statistics

        # Separate by direction if contact_id provided
        our_avg = None
        their_avg = None
        if contact_id and result.data:
            email_ids = [m['email_id'] for m in result.data if m.get('email_id') and m.get('is_auto_reply') is not True]
            if email_ids:
                # Fetch direction for responding emails (batch 500)
                direction_map = {}
                for i in range(0, len(email_ids), 500):
                    batch_ids = email_ids[i:i+500]
                    dir_result = _supabase.table('emails').select('id, is_outbound').in_('id', batch_ids).execute()
                    for e in (dir_result.data or []):
                        direction_map[e['id']] = e.get('is_outbound', False)

                our_times = []
                their_times = []
                for m in result.data:
                    if m.get('is_auto_reply') is True or not m.get('response_time_seconds'):
                        continue
                    is_outbound = direction_map.get(m['email_id'])
                    if is_outbound is True:
                        our_times.append(m['response_time_seconds'] / 3600.0)
                    elif is_outbound is False:
                        their_times.append(m['response_time_seconds'] / 3600.0)

                our_avg = statistics.mean(our_times) if our_times else None
                their_avg = statistics.mean(their_times) if their_times else None

        return ResponseTimeStats(
            total_responses=len(result.data),
            avg_response_time_hours=statistics.mean(response_times_hours) if response_times_hours else 0,
            median_response_time_hours=statistics.median(response_times_hours) if response_times_hours else None,
            min_response_time_hours=min(response_times_hours) if response_times_hours else 0,
            max_response_time_hours=max(response_times_hours) if response_times_hours else 0,
            avg_business_hours_response_time_hours=statistics.mean(bh_times_hours) if bh_times_hours else None,
            median_business_hours_response_time_hours=statistics.median(bh_times_hours) if bh_times_hours else None,
            our_avg_response_time=our_avg,
            their_avg_response_time=their_avg,
            auto_reply_count=auto_replies,
            auto_reply_percentage=(auto_replies / len(result.data) * 100) if result.data else 0
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get response time stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/response-times/slowest", response_model=List[SlowestResponder])
async def get_slowest_responders(
    client_id: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100)
):
    """
    Get slowest responders.

    Args:
        client_id: Filter by client
        limit: Number of results

    Returns:
        List of slowest responders
    """
    try:
        # Fetch response metrics
        query = _supabase.table('email_response_metrics').select(
            'responder_contact_id, response_time_seconds'
        ).not_.is_('responder_contact_id', 'null')

        result = query.execute()

        # Group by contact and calculate average
        from collections import defaultdict
        contact_times = defaultdict(list)

        for m in result.data:
            if m.get('response_time_seconds'):
                # Convert seconds to hours
                contact_times[m['responder_contact_id']].append(m['response_time_seconds'] / 3600.0)

        # Calculate averages
        contact_avgs = []
        for contact_id, times in contact_times.items():
            avg_time = sum(times) / len(times)
            contact_avgs.append((contact_id, avg_time, len(times)))

        # Sort by slowest
        contact_avgs.sort(key=lambda x: x[1], reverse=True)

        # Enrich with contact info
        slowest = []
        for contact_id, avg_time, count in contact_avgs[:limit]:
            contact_result = _supabase.table('customer_contacts').select(
                'email_address, full_name, company_name'
            ).eq('id', contact_id).execute()

            if contact_result.data:
                c = contact_result.data[0]
                slowest.append(SlowestResponder(
                    contact_id=contact_id,
                    contact_email=c['email_address'],
                    contact_name=c.get('full_name'),
                    company_name=c.get('company_name'),
                    avg_response_time_hours=avg_time,
                    response_count=count
                ))

        return slowest

    except Exception as e:
        logger.error(f"Failed to get slowest responders: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/response-times/by-contact/{contact_id}", response_model=ResponseTimeListResponse)
async def get_contact_response_history(
    contact_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0)
):
    """
    Get response time history for a specific contact.

    Args:
        contact_id: Contact UUID
        limit: Maximum number of results
        offset: Offset for pagination

    Returns:
        List of response time metrics for contact
    """
    try:
        result = _supabase.table('email_response_metrics').select(
            '''
            id, email_id, responding_to_email_id, responder_contact_id, responder_company_id,
            response_time_seconds, business_hours_response_time_seconds, is_auto_reply, created_at, updated_at
            '''
        ).eq('responder_contact_id', contact_id).order(
            'created_at', desc=True
        ).range(offset, offset + limit - 1).execute()

        # Fetch contact email once
        contact_result = _supabase.table('customer_contacts').select(
            'email_address'
        ).eq('id', contact_id).single().execute()

        contact_email = None
        if contact_result.data:
            contact_email = contact_result.data.get('email_address')

        metrics = [ResponseTimeMetric(**m, contact_email=contact_email) for m in result.data]

        # Get total count
        count_result = _supabase.table('email_response_metrics').select(
            'id', count='exact'
        ).eq('responder_contact_id', contact_id).execute()
        total = count_result.count if count_result.count else len(count_result.data)

        return ResponseTimeListResponse(metrics=metrics, total=total)

    except Exception as e:
        logger.error(f"Failed to get contact response history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# COMMUNICATION PATTERN ENDPOINTS (4 endpoints)
# ============================================================================

@router.get("/patterns/initiation", response_model=List[InitiationPattern])
async def get_initiation_patterns(
    client_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500)
):
    """
    Get thread initiation patterns.

    Args:
        client_id: Filter by client
        limit: Maximum number of results

    Returns:
        List of initiation patterns
    """
    try:
        if not client_id:
            raise HTTPException(status_code=400, detail="client_id is required")

        # Call RPC function to get thread initiation data
        result = _supabase.rpc(
            'calculate_all_contact_initiation_ratios',
            {'p_client_id': client_id}
        ).execute()

        if not result.data:
            return []

        # Enrich with contact info
        patterns = []
        for item in result.data[:limit]:  # Limit in memory for simplicity
            contact_result = _supabase.table('customer_contacts').select(
                'email_address, full_name, company_name'
            ).eq('id', item['contact_id']).single().execute()

            if contact_result.data:
                c = contact_result.data
                patterns.append(InitiationPattern(
                    contact_id=item['contact_id'],
                    contact_email=c['email_address'],
                    contact_name=c.get('full_name'),
                    company_name=c.get('company_name'),
                    total_threads=item['threads_initiated_by_us'] + item['threads_initiated_by_them'],
                    threads_initiated_by_us=item['threads_initiated_by_us'],
                    threads_initiated_by_them=item['threads_initiated_by_them'],
                    initiation_ratio=float(item['initiation_ratio'])
                ))

        # Sort by initiation ratio descending
        patterns.sort(key=lambda x: x.initiation_ratio, reverse=True)

        return patterns

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get initiation patterns: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/patterns/frequency", response_model=List[FrequencyPattern])
async def get_frequency_patterns(
    client_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500)
):
    """
    Get communication frequency patterns.

    Args:
        client_id: Filter by client
        limit: Maximum number of results

    Returns:
        List of frequency patterns
    """
    try:
        query = _supabase.table('customer_contacts').select(
            '''
            id, email_address, full_name, company_name,
            total_emails_sent, total_emails_received,
            first_contacted_at, last_contacted_at
            '''
        ).not_.is_('first_contacted_at', 'null')

        if client_id:
            query = query.eq('client_id', client_id)

        result = query.order('total_emails_sent', desc=True).limit(limit).execute()

        patterns = []
        for c in result.data:
            total_emails = (c.get('total_emails_sent', 0) or 0) + (c.get('total_emails_received', 0) or 0)

            # Calculate frequency metrics
            emails_per_week = None
            emails_per_month = None
            days_active = None

            if c.get('first_contacted_at') and c.get('last_contacted_at'):
                first = datetime.fromisoformat(c['first_contacted_at'].replace('Z', '+00:00'))
                last = datetime.fromisoformat(c['last_contacted_at'].replace('Z', '+00:00'))
                days_active = (last - first).days + 1

                if days_active > 0:
                    emails_per_week = (total_emails / days_active) * 7
                    emails_per_month = (total_emails / days_active) * 30

            patterns.append(FrequencyPattern(
                contact_id=c['id'],
                contact_email=c['email_address'],
                contact_name=c.get('full_name'),
                company_name=c.get('company_name'),
                total_emails=total_emails,
                emails_per_week=emails_per_week,
                emails_per_month=emails_per_month,
                first_contact_date=c.get('first_contacted_at'),
                last_contact_date=c.get('last_contacted_at'),
                days_active=days_active
            ))

        return patterns

    except Exception as e:
        logger.error(f"Failed to get frequency patterns: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/patterns/engagement-trends", response_model=List[EngagementTrend])
async def get_engagement_trends(
    client_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500)
):
    """
    Get engagement trends over time.

    Args:
        client_id: Filter by client
        limit: Maximum number of results

    Returns:
        List of engagement trends
    """
    try:
        from collections import defaultdict

        now = datetime.utcnow()
        thirty_days_ago = (now - timedelta(days=30)).isoformat()
        sixty_days_ago = (now - timedelta(days=60)).isoformat()

        # Get contacts with engagement scores
        contacts_query = _supabase.table('customer_contacts').select(
            'id, email_address, full_name, company_name, engagement_score'
        ).not_.is_('engagement_score', 'null')

        if client_id:
            contacts_query = contacts_query.eq('client_id', client_id)

        contacts_result = contacts_query.order('engagement_score', desc=True).limit(limit).execute()

        if not contacts_result.data:
            return []

        contact_ids = [c['id'] for c in contacts_result.data]
        contact_map = {c['id']: c for c in contacts_result.data}

        # Get email counts for last 60 days in one query, then split by period
        last30 = defaultdict(int)
        prev30 = defaultdict(int)

        # Fetch all emails for these contacts from the last 60 days
        emails_result = _supabase.table('emails').select(
            'customer_contact_id, sent_date'
        ).in_('customer_contact_id', contact_ids).gte('sent_date', sixty_days_ago).execute()

        for e in (emails_result.data or []):
            cid = e.get('customer_contact_id')
            sd = e.get('sent_date', '')
            if not cid or not sd:
                continue
            if sd >= thirty_days_ago:
                last30[cid] += 1
            else:
                prev30[cid] += 1

        trends = []
        for cid, contact in contact_map.items():
            l30 = last30[cid]
            p30 = prev30[cid]

            if p30 > 0:
                change_pct = ((l30 - p30) / p30) * 100
            elif l30 > 0:
                change_pct = 100.0
            else:
                change_pct = 0.0

            if change_pct > 10:
                trend = 'increasing'
            elif change_pct < -10:
                trend = 'decreasing'
            else:
                trend = 'stable'

            trends.append(EngagementTrend(
                contact_id=cid,
                contact_email=contact['email_address'],
                contact_name=contact.get('full_name'),
                company_name=contact.get('company_name'),
                current_engagement_score=contact.get('engagement_score', 0),
                trend=trend,
                last_30_days_emails=l30,
                previous_30_days_emails=p30,
                change_percentage=round(change_pct, 1)
            ))

        # Sort: decreasing first (at-risk), then stable, then increasing
        trend_order = {'decreasing': 0, 'stable': 1, 'increasing': 2}
        trends.sort(key=lambda t: (trend_order.get(t.trend, 1), -abs(t.change_percentage)))

        return trends

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get engagement trends: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/patterns/by-contact/{contact_id}", response_model=CommunicationPattern)
async def get_contact_pattern(contact_id: str):
    """
    Get complete communication pattern for a contact.

    Args:
        contact_id: Contact UUID

    Returns:
        Complete communication pattern
    """
    try:
        result = _supabase.table('customer_contacts').select(
            '''
            id, email_address, full_name, company_name,
            initiation_ratio,
            reply_rate, avg_response_time_seconds, their_avg_response_time, avg_thread_depth,
            total_emails_sent, total_emails_received,
            first_contacted_at, last_contacted_at
            '''
        ).eq('id', contact_id).single().execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Contact not found")

        c = result.data

        total_emails = (c.get('total_emails_sent', 0) or 0) + (c.get('total_emails_received', 0) or 0)

        # Calculate emails per week
        emails_per_week = None
        if c.get('first_contacted_at') and c.get('last_contacted_at'):
            first = datetime.fromisoformat(c['first_contacted_at'].replace('Z', '+00:00'))
            last = datetime.fromisoformat(c['last_contacted_at'].replace('Z', '+00:00'))
            days_active = (last - first).days + 1

            if days_active > 0:
                emails_per_week = (total_emails / days_active) * 7

        # Convert response times from seconds to hours
        avg_response_time_hours = None
        if c.get('avg_response_time_seconds'):
            avg_response_time_hours = c['avg_response_time_seconds'] / 3600.0

        their_avg_response_time_hours = None
        if c.get('their_avg_response_time'):
            their_avg_response_time_hours = c['their_avg_response_time'] / 3600.0

        return CommunicationPattern(
            contact_id=c['id'],
            contact_email=c['email_address'],
            contact_name=c.get('full_name'),
            company_name=c.get('company_name'),
            thread_initiation_ratio=c.get('initiation_ratio'),
            total_threads=None,  # Not tracked separately in schema
            reply_rate=c.get('reply_rate'),
            avg_response_time_hours=avg_response_time_hours,
            their_avg_response_time_hours=their_avg_response_time_hours,
            emails_per_week=emails_per_week,
            total_emails=total_emails,
            avg_thread_depth=c.get('avg_thread_depth')
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get contact pattern: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# DASHBOARD ENDPOINTS (2 endpoints)
# ============================================================================

@router.get("/dashboard", response_model=DashboardSummary)
async def get_dashboard(client_id: str = Query(...)):
    """
    Get complete dashboard summary for a client.

    Args:
        client_id: Client UUID (required)

    Returns:
        Complete dashboard with all metrics
    """
    try:
        # Count totals
        contacts_result = _supabase.table('customer_contacts').select(
            'id, last_contacted_at, engagement_score', count='exact'
        ).eq('client_id', client_id).execute()

        companies_result = _supabase.table('customer_companies').select(
            'id', count='exact'
        ).eq('client_id', client_id).execute()

        emails_result = _supabase.table('emails').select(
            'id', count='exact'
        ).eq('client_id', client_id).execute()

        # Calculate engagement distribution
        active = 0
        quiet = 0
        at_risk = 0
        engagement_scores = []

        now = datetime.utcnow()
        for c in contacts_result.data:
            if c.get('engagement_score'):
                engagement_scores.append(c['engagement_score'])

            if c.get('last_contacted_at'):
                last = datetime.fromisoformat(c['last_contacted_at'].replace('Z', '+00:00'))
                days_since = (now - last.replace(tzinfo=None)).days

                if days_since <= 30:
                    active += 1
                elif days_since <= 90:
                    quiet += 1
                else:
                    at_risk += 1

        avg_score = sum(engagement_scores) / len(engagement_scores) if engagement_scores else None

        # Thread counts
        threads_result = _supabase.table('thread_status').select('status').execute()
        thread_counts = {'active': 0, 'overdue': 0, 'awaiting_response': 0}
        for t in threads_result.data:
            status = t.get('status', '')
            if 'ongoing' in status or 'awaiting_our_response' in status:
                thread_counts['active'] += 1
            if status == 'overdue':
                thread_counts['overdue'] += 1
            if status == 'awaiting_response':
                thread_counts['awaiting_response'] += 1

        # Response time average
        response_result = _supabase.table('email_response_metrics').select(
            'response_time_seconds'
        ).execute()
        avg_response = None
        if response_result.data:
            # Convert seconds to hours
            times = [r['response_time_seconds'] / 3600.0 for r in response_result.data if r.get('response_time_seconds')]
            if times:
                avg_response = sum(times) / len(times)

        # Get top engaged contacts/companies
        top_contacts_result = _supabase.table('customer_contacts').select(
            'id, email_address, full_name, company_name, engagement_score, total_emails_sent, total_emails_received, last_contacted_at'
        ).eq('client_id', client_id).not_.is_('engagement_score', 'null').order(
            'engagement_score', desc=True
        ).limit(5).execute()

        top_contacts = [
            TopEngagedContact(
                id=c['id'],
                email_address=c['email_address'],
                full_name=c.get('full_name'),
                company_name=c.get('company_name'),
                engagement_score=c['engagement_score'],
                total_emails=(c.get('total_emails_sent', 0) or 0) + (c.get('total_emails_received', 0) or 0),
                last_contacted_at=c.get('last_contacted_at')
            )
            for c in top_contacts_result.data
        ]

        top_companies_result = _supabase.table('customer_companies').select(
            'id, company_name, engagement_score, total_emails, contact_count, last_contact_date'
        ).eq('client_id', client_id).not_.is_('engagement_score', 'null').order(
            'engagement_score', desc=True
        ).limit(5).execute()

        top_companies = [
            TopEngagedCompany(
                id=comp['id'],
                company_name=comp['company_name'],
                engagement_score=comp['engagement_score'],
                total_emails=comp.get('total_emails', 0) or 0,
                contact_count=comp.get('contact_count', 0) or 0,
                last_contact_date=comp.get('last_contact_date')
            )
            for comp in top_companies_result.data
        ]

        # Get at-risk contacts/companies
        cutoff_date_contacts = (datetime.utcnow() - timedelta(days=60)).isoformat()
        at_risk_contacts_result = _supabase.table('customer_contacts').select(
            'id, email_address, full_name, company_name, last_contacted_at, engagement_score'
        ).eq('client_id', client_id).not_.is_('last_contacted_at', 'null').lte(
            'last_contacted_at', cutoff_date_contacts
        ).order('last_contacted_at').limit(10).execute()

        at_risk_contacts_list = []
        for c in at_risk_contacts_result.data:
            last = datetime.fromisoformat(c['last_contacted_at'].replace('Z', '+00:00'))
            days_since = (now - last.replace(tzinfo=None)).days
            at_risk_contacts_list.append(AtRiskContact(
                id=c['id'],
                email_address=c['email_address'],
                full_name=c.get('full_name'),
                company_name=c.get('company_name'),
                last_contacted_at=c['last_contacted_at'],
                days_since_contact=days_since,
                engagement_score=c.get('engagement_score')
            ))

        cutoff_date_companies = (datetime.utcnow() - timedelta(days=90)).isoformat()
        at_risk_companies_result = _supabase.table('customer_companies').select(
            'id, company_name, last_contact_date, contact_count, engagement_score'
        ).eq('client_id', client_id).not_.is_('last_contact_date', 'null').lte(
            'last_contact_date', cutoff_date_companies
        ).order('last_contact_date').limit(10).execute()

        at_risk_companies_list = []
        for comp in at_risk_companies_result.data:
            last = datetime.fromisoformat(comp['last_contact_date'].replace('Z', '+00:00'))
            days_since = (now - last.replace(tzinfo=None)).days
            at_risk_companies_list.append(AtRiskCompany(
                id=comp['id'],
                company_name=comp['company_name'],
                last_contact_date=comp['last_contact_date'],
                days_since_contact=days_since,
                contact_count=comp.get('contact_count', 0) or 0,
                engagement_score=comp.get('engagement_score')
            ))

        # Get last extraction date
        last_extraction = _supabase.table('extraction_jobs').select(
            'completed_at'
        ).eq('client_id', client_id).eq('status', 'completed').order(
            'completed_at', desc=True
        ).limit(1).execute()

        last_extraction_date = None
        if last_extraction.data:
            last_extraction_date = last_extraction.data[0].get('completed_at')

        # Get last contact date
        last_contact = None
        if contacts_result.data:
            contact_dates = [c.get('last_contacted_at') for c in contacts_result.data if c.get('last_contacted_at')]
            if contact_dates:
                last_contact = max(contact_dates)

        return DashboardSummary(
            client_id=client_id,
            total_contacts=contacts_result.count or 0,
            total_companies=companies_result.count or 0,
            total_emails=emails_result.count or 0,
            active_contacts=active,
            quiet_contacts=quiet,
            at_risk_contacts=at_risk,
            avg_engagement_score=avg_score,
            total_threads=len(threads_result.data),
            active_threads=thread_counts['active'],
            overdue_threads=thread_counts['overdue'],
            awaiting_response_threads=thread_counts['awaiting_response'],
            avg_response_time_hours=avg_response,
            top_engaged_contacts=top_contacts,
            top_engaged_companies=top_companies,
            at_risk_contacts_list=at_risk_contacts_list,
            at_risk_companies_list=at_risk_companies_list,
            last_extraction_date=last_extraction_date,
            last_contact_date=last_contact
        )

    except Exception as e:
        logger.error(f"Failed to get dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary/{client_id}", response_model=ClientSummary)
async def get_client_summary(client_id: str):
    """
    Get client-specific summary.

    Args:
        client_id: Client UUID

    Returns:
        Client summary with key metrics
    """
    try:
        # Get client info
        client_result = _supabase.table('clients').select('client_name').eq('id', client_id).single().execute()

        if not client_result.data:
            raise HTTPException(status_code=404, detail="Client not found")

        client_name = client_result.data.get('client_name')

        # Count mailboxes
        mailboxes_result = _supabase.table('mailboxes').select('id', count='exact').eq('client_id', client_id).execute()

        # Count contacts
        contacts_result = _supabase.table('customer_contacts').select(
            'id, engagement_score, last_contacted_at', count='exact'
        ).eq('client_id', client_id).execute()

        # Count companies
        companies_result = _supabase.table('customer_companies').select('id', count='exact').eq('client_id', client_id).execute()

        # Count emails
        emails_result = _supabase.table('emails').select('id', count='exact').eq('client_id', client_id).execute()

        # Calculate engagement metrics
        engagement_scores = [c.get('engagement_score') for c in contacts_result.data if c.get('engagement_score')]
        avg_score = sum(engagement_scores) / len(engagement_scores) if engagement_scores else None

        active = 0
        at_risk = 0
        now = datetime.utcnow()
        for c in contacts_result.data:
            if c.get('last_contacted_at'):
                last = datetime.fromisoformat(c['last_contacted_at'].replace('Z', '+00:00'))
                days_since = (now - last.replace(tzinfo=None)).days

                if days_since <= 30:
                    active += 1
                elif days_since > 90:
                    at_risk += 1

        # Get last extraction
        last_extraction = _supabase.table('extraction_jobs').select('completed_at').eq(
            'client_id', client_id
        ).eq('status', 'completed').order('completed_at', desc=True).limit(1).execute()

        last_extraction_date = None
        if last_extraction.data:
            last_extraction_date = last_extraction.data[0].get('completed_at')

        # Get last contact
        last_contact = None
        if contacts_result.data:
            contact_dates = [c.get('last_contacted_at') for c in contacts_result.data if c.get('last_contacted_at')]
            if contact_dates:
                last_contact = max(contact_dates)

        return ClientSummary(
            client_id=client_id,
            client_name=client_name,
            mailbox_count=mailboxes_result.count or 0,
            contact_count=contacts_result.count or 0,
            company_count=companies_result.count or 0,
            total_emails=emails_result.count or 0,
            avg_engagement_score=avg_score,
            active_contacts=active,
            at_risk_contacts=at_risk,
            last_extraction_date=last_extraction_date,
            last_contact_date=last_contact
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get client summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# EXTRACTION CONTROL ENDPOINTS (5 endpoints)
# ============================================================================

@router.post("/extraction/run", response_model=ExtractionJobResponse)
async def run_extraction(
    request: ExtractionJobCreate,
    background_tasks: BackgroundTasks
):
    """
    Trigger an extraction job (runs in background).

    Args:
        request: Extraction job configuration
        background_tasks: FastAPI background task handler

    Returns:
        Job info with job_id for tracking
    """
    try:
        # Validate mailbox exists
        mailbox_result = _supabase.table('mailboxes').select(
            'id, client_id, email_address'
        ).eq('id', request.mailbox_id).single().execute()

        if not mailbox_result.data:
            raise HTTPException(status_code=404, detail="Mailbox not found")

        mailbox = mailbox_result.data

        # Create orchestrator
        orchestrator = ExtractionOrchestrator(
            mailbox_id=request.mailbox_id,
            client_id=mailbox['client_id'],
            use_redis=True,
            extraction_mode=request.mode.value,
            lookback_days=request.lookback_days
        )

        # Run extraction in background
        def run_pipeline():
            try:
                orchestrator.run_extraction(
                    exclude_mailing_lists=request.exclude_mailing_lists,
                    exclude_noreply=request.exclude_noreply,
                    exclude_shared=request.exclude_shared,
                    exclude_internal=request.exclude_internal,
                    force_relink=request.force_relink,
                    skip_role_classification=request.skip_role_classification
                )
            except Exception as e:
                logger.error(f"Background extraction failed: {e}")

        background_tasks.add_task(run_pipeline)

        # Return job info immediately
        # The orchestrator creates the job in _create_job() when run_extraction() is called
        # For now, return pending status - the background task will update it
        return ExtractionJobResponse(
            id="pending",  # Will be created when background task starts
            client_id=mailbox['client_id'],
            mailbox_id=request.mailbox_id,
            status=ExtractionStatus.PENDING,
            extraction_mode=request.mode.value,
            current_step="Queued for processing",
            current_step_number=0,
            total_steps=13,
            started_at=None,
            completed_at=None,
            updated_at=datetime.utcnow(),
            errors=None
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to trigger extraction: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/extraction/jobs/{job_id}", response_model=ExtractionJobDetail)
async def get_extraction_job(job_id: str):
    """
    Get extraction job status and results.

    Args:
        job_id: Extraction job UUID

    Returns:
        Detailed job information with results
    """
    try:
        result = _supabase.table('extraction_jobs').select(
            '''
            id, client_id, mailbox_id, status, extraction_mode, emails_in_scope,
            date_range_start, date_range_end,
            current_step, current_step_number, total_steps,
            started_at, completed_at, updated_at, errors, results
            '''
        ).eq('id', job_id).single().execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Job not found")

        job = result.data

        # Calculate duration if completed
        duration_seconds = None
        if job.get('started_at') and job.get('completed_at'):
            started = datetime.fromisoformat(job['started_at'].replace('Z', '+00:00'))
            completed = datetime.fromisoformat(job['completed_at'].replace('Z', '+00:00'))
            duration_seconds = (completed - started).total_seconds()

        return ExtractionJobDetail(
            id=job['id'],
            client_id=job['client_id'],
            mailbox_id=job['mailbox_id'],
            status=job['status'],
            extraction_mode=job.get('extraction_mode'),
            emails_in_scope=job.get('emails_in_scope'),
            date_range_start=job.get('date_range_start'),
            date_range_end=job.get('date_range_end'),
            current_step=job.get('current_step'),
            current_step_number=job.get('current_step_number'),
            total_steps=job.get('total_steps'),
            started_at=job.get('started_at'),
            completed_at=job.get('completed_at'),
            updated_at=job.get('updated_at'),
            errors=job.get('errors'),
            results=job.get('results'),
            duration_seconds=duration_seconds
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get extraction job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/extraction/jobs", response_model=ExtractionJobListResponse)
async def list_extraction_jobs(
    client_id: Optional[str] = Query(default=None),
    mailbox_id: Optional[str] = Query(default=None),
    status: Optional[ExtractionStatus] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0)
):
    """
    List extraction jobs with filters.

    Args:
        client_id: Filter by client
        mailbox_id: Filter by mailbox
        status: Filter by status
        limit: Maximum number of results
        offset: Offset for pagination

    Returns:
        List of extraction jobs
    """
    try:
        query = _supabase.table('extraction_jobs').select(
            '''
            id, client_id, mailbox_id, status, extraction_mode, emails_in_scope,
            date_range_start, date_range_end,
            current_step, current_step_number, total_steps,
            started_at, completed_at, updated_at, errors
            ''',
            count='exact'
        )

        if client_id:
            query = query.eq('client_id', client_id)
        if mailbox_id:
            query = query.eq('mailbox_id', mailbox_id)
        if status:
            query = query.eq('status', status.value)

        result = query.order('started_at', desc=True).range(offset, offset + limit - 1).execute()

        jobs = [
            ExtractionJobResponse(
                id=job['id'],
                client_id=job['client_id'],
                mailbox_id=job['mailbox_id'],
                status=job['status'],
                extraction_mode=job.get('extraction_mode'),
                emails_in_scope=job.get('emails_in_scope'),
                date_range_start=job.get('date_range_start'),
                date_range_end=job.get('date_range_end'),
                current_step=job.get('current_step'),
                current_step_number=job.get('current_step_number'),
                total_steps=job.get('total_steps'),
                started_at=job.get('started_at'),
                completed_at=job.get('completed_at'),
                updated_at=job.get('updated_at'),
                errors=job.get('errors')
            )
            for job in result.data
        ]

        total = result.count if result.count else len(result.data)

        return ExtractionJobListResponse(jobs=jobs, total=total)

    except Exception as e:
        logger.error(f"Failed to list extraction jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/extraction/jobs/{job_id}/cancel")
async def cancel_extraction_job(job_id: str):
    """
    Cancel a running extraction job.

    Args:
        job_id: Extraction job UUID

    Returns:
        Success message
    """
    try:
        # Check if job exists and is running
        job_result = _supabase.table('extraction_jobs').select(
            'id, status'
        ).eq('id', job_id).single().execute()

        if not job_result.data:
            raise HTTPException(status_code=404, detail="Job not found")

        job = job_result.data

        if job['status'] not in ['pending', 'processing']:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot cancel job with status '{job['status']}'"
            )

        # Update job status to failed with cancellation message
        _supabase.table('extraction_jobs').update({
            'status': 'failed',
            'current_step': 'Cancelled by user',
            'errors': ['Job cancelled by user request'],
            'updated_at': datetime.utcnow().isoformat()
        }).eq('id', job_id).execute()

        return {"message": "Job cancelled successfully", "job_id": job_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel extraction job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/extraction/progress/{job_id}", response_model=ExtractionProgressResponse)
async def get_extraction_progress(job_id: str):
    """
    Get real-time extraction progress from Redis.

    Args:
        job_id: Extraction job UUID

    Returns:
        Real-time progress information
    """
    try:
        # For now, just query the database (Redis integration can be added later)
        # In production, this would check Redis first for real-time updates
        result = _supabase.table('extraction_jobs').select(
            '''
            id, status, current_step, current_step_number, total_steps,
            mailbox_id, client_id, errors
            '''
        ).eq('id', job_id).single().execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Job not found")

        job = result.data

        # Calculate processed/failed counts from results if available
        # This is a simplified version - full implementation would track these in Redis
        processed = None
        failed = None

        return ExtractionProgressResponse(
            job_id=job['id'],
            status=job['status'],
            current_step=job.get('current_step'),
            current_step_number=job.get('current_step_number'),
            total_steps=job.get('total_steps'),
            processed=processed,
            failed=failed,
            mailbox_id=job.get('mailbox_id'),
            client_id=job.get('client_id'),
            error=job.get('errors', [None])[0] if job.get('errors') else None
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get extraction progress: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# METRIC HISTORY ENDPOINTS
# ============================================================================

@router.get("/metric-history/{entity_type}/{entity_id}")
async def get_metric_history(
    entity_type: str,
    entity_id: str,
    limit: int = Query(default=30, ge=1, le=200),
):
    """
    Get engagement score history for a contact or company.

    Returns chronological list of scores with factor breakdowns for trend charts.
    """
    if entity_type not in ('contact', 'company'):
        raise HTTPException(status_code=400, detail="entity_type must be 'contact' or 'company'")

    try:
        result = (
            _supabase.table('metric_history')
            .select(
                'engagement_score, scoring_version, '
                'response_time_score, thread_completeness_score, '
                'initiation_balance_score, reply_rate_score, '
                'frequency_score, recency_score, '
                'decision_maker_bonus, seniority_bonus, '
                'emails_per_month_avg, avg_response_time_seconds, reply_rate, '
                'calculated_at'
            )
            .eq('entity_id', entity_id)
            .eq('entity_type', entity_type)
            .order('calculated_at', desc=True)
            .limit(limit)
            .execute()
        )

        # Return in chronological order (oldest first) for charts
        data = list(reversed(result.data or []))
        return {'history': data, 'total': len(data)}

    except Exception as e:
        logger.error(f"Failed to get metric history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# DATA HEALTH ENDPOINTS
# ============================================================================

@router.get("/data-health")
async def get_data_health(client_id: Optional[str] = Query(default=None)):
    """
    Data health dashboard — sync lag, identity resolution coverage,
    thread confidence distribution, and missing-day detection.
    """
    try:
        logger.info("data-health: starting step 1 - mailboxes")
        # ---------- 1. Sync lag per mailbox ----------
        mb_query = _supabase.table('mailboxes').select(
            'id, name, email_address, mailbox_type, is_active, last_sync_at, last_extraction_at'
        )
        if client_id:
            mb_query = mb_query.eq('client_id', client_id)
        mb_result = mb_query.execute()
        logger.info(f"data-health: step 1 done, {len(mb_result.data or [])} mailboxes")

        now = datetime.utcnow()
        mailbox_health = []
        for mb in (mb_result.data or []):
            sync_lag_hours = None
            extraction_lag_hours = None
            if mb.get('last_sync_at'):
                try:
                    last_sync = datetime.fromisoformat(mb['last_sync_at'].replace('Z', '+00:00')).replace(tzinfo=None)
                    sync_lag_hours = round((now - last_sync).total_seconds() / 3600, 1)
                except Exception:
                    pass
            if mb.get('last_extraction_at'):
                try:
                    last_ext = datetime.fromisoformat(mb['last_extraction_at'].replace('Z', '+00:00')).replace(tzinfo=None)
                    extraction_lag_hours = round((now - last_ext).total_seconds() / 3600, 1)
                except Exception:
                    pass

            mailbox_health.append({
                'mailbox_id': mb['id'],
                'email_address': mb.get('email_address') or mb.get('name', 'Unknown'),
                'provider': mb.get('mailbox_type'),
                'status': 'active' if mb.get('is_active') else 'inactive',
                'last_sync_at': mb.get('last_sync_at'),
                'last_extraction_at': mb.get('last_extraction_at'),
                'sync_lag_hours': sync_lag_hours,
                'extraction_lag_hours': extraction_lag_hours,
            })

        # ---------- 2. Identity resolution coverage ----------
        logger.info("data-health: step 2 - identity resolution")
        email_query = _supabase.table('emails').select('id', count='exact')
        if client_id:
            email_query = email_query.eq('client_id', client_id)
        total_emails_result = email_query.execute()
        total_emails = total_emails_result.count or 0

        # Count unresolved (customer_contact_id IS NULL), then subtract
        logger.info("data-health: step 2b - unresolved count")
        unresolved_query = _supabase.table('emails').select('id', count='exact').is_('customer_contact_id', 'null')
        if client_id:
            unresolved_query = unresolved_query.eq('client_id', client_id)
        unresolved_result = unresolved_query.execute()
        unresolved_emails = unresolved_result.count or 0
        resolved_emails = total_emails - unresolved_emails

        identity_resolution = {
            'total_emails': total_emails,
            'resolved_emails': resolved_emails,
            'unresolved_emails': unresolved_emails,
            'coverage_percent': round((resolved_emails / total_emails * 100), 1) if total_emails > 0 else 0,
        }

        # ---------- 3. Thread confidence distribution ----------
        logger.info("data-health: step 3 - thread distribution")
        # thread_status has no client_id — filter via mailbox_ids
        mailbox_ids = [m['mailbox_id'] for m in mailbox_health]
        thread_data = []
        if mailbox_ids:
            for i in range(0, len(mailbox_ids), 500):
                batch = mailbox_ids[i:i+500]
                thread_batch = _supabase.table('thread_status').select('status').in_('mailbox_id', batch).execute()
                thread_data.extend(thread_batch.data or [])
        else:
            thread_result = _supabase.table('thread_status').select('status').execute()
            thread_data = thread_result.data or []

        logger.info("data-health: step 3b - counting statuses")
        from collections import Counter
        status_counts = Counter(t.get('status', 'unknown') for t in thread_data)
        thread_total = sum(status_counts.values())
        thread_distribution = [
            {
                'status': status,
                'count': count,
                'percent': round(count / thread_total * 100, 1) if thread_total > 0 else 0,
            }
            for status, count in sorted(status_counts.items(), key=lambda x: -x[1])
        ]

        logger.info("data-health: step 4 - missing days")
        # ---------- 4. Missing days (gaps in email data, last 30 days) ----------
        thirty_days_ago = (now - timedelta(days=30)).isoformat()
        recent_query = _supabase.table('emails').select('sent_date')
        if client_id:
            recent_query = recent_query.eq('client_id', client_id)
        recent_query = recent_query.gte('sent_date', thirty_days_ago).order('sent_date', desc=False)

        # Paginate to get all dates
        all_dates = set()
        offset_val = 0
        while True:
            batch = recent_query.range(offset_val, offset_val + 499).execute()
            rows = batch.data or []
            if not rows:
                break
            for r in rows:
                if r.get('sent_date'):
                    try:
                        d = datetime.fromisoformat(r['sent_date'].replace('Z', '+00:00')).date()
                        all_dates.add(d)
                    except Exception:
                        pass
            offset_val += len(rows)
            if len(rows) < 500:
                break

        expected_dates = set()
        for i in range(30):
            expected_dates.add((now - timedelta(days=i)).date())

        missing_dates = sorted(expected_dates - all_dates)
        # Only flag weekdays as truly missing
        missing_weekdays = [d.isoformat() for d in missing_dates if d.isoweekday() <= 5]

        logger.info("data-health: step 5 - extraction jobs")
        # ---------- 5. Extraction jobs health ----------
        jobs_query = _supabase.table('extraction_jobs').select(
            'id, status, extraction_mode, started_at, completed_at, total_emails, processed_emails, errors'
        )
        if client_id:
            jobs_query = jobs_query.eq('client_id', client_id)
        jobs_result = jobs_query.order('started_at', desc=True).limit(10).execute()
        recent_jobs = jobs_result.data or []

        return {
            'mailbox_health': mailbox_health,
            'identity_resolution': identity_resolution,
            'thread_distribution': thread_distribution,
            'missing_weekdays': missing_weekdays,
            'missing_weekday_count': len(missing_weekdays),
            'recent_extraction_jobs': recent_jobs,
        }

    except Exception as e:
        logger.error(f"Failed to get data health: {e}")
        raise HTTPException(status_code=500, detail=str(e))
