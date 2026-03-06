"""
AI Intelligence Router — Sprint 3

9 initial endpoints for intelligence, buckets, feedback, and entities.
Digest, relationship, and usage endpoints added in Sessions 5, 8, 11.

Pattern: global _supabase, init_ai_router(supabase_client) function.
Router prefix: /ai, tags: ["ai-intelligence"]
"""

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks, Depends
from typing import Optional
from datetime import datetime, timedelta
import logging

from ..dependencies.auth import get_current_user, require_role, get_accessible_mailbox_ids

from ..models.ai import (
    # Request models
    AnalyzeRequest, ReanalyzeRequest, FeedbackRequest,
    # Response models
    AnalyzeResponse, ReanalyzeResponse, IntelligenceListResponse, IntelligenceStats,
    ActionItemsResponse, ActionItem, BucketSummary,
    FeedbackResponse,
    EntityListResponse, BusinessEntity, CompetitorLandscape,
    OpportunitySignalsResponse, OpportunitySignal,
    DailyDigest,
)
from ..services.ai_email_analyzer import init_email_analyzer, get_email_analyzer
from ..services.ai_action_bucket_engine import (
    init_bucket_engine, get_bucket_engine, BUCKET_CONFIG,
)
from ..services.ai_entity_aggregator import init_entity_aggregator, get_entity_aggregator
from ..services.ai_digest_generator import init_digest_generator, get_digest_generator
from ..services.ai_usage_tracker import init_usage_tracker, get_usage_tracker
from ..services.ai_client import get_ai_settings, update_ai_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai-intelligence"])

# Supabase client — injected from main.py
_supabase = None


def init_ai_router(supabase_client):
    """Initialize the AI router and all AI services with Supabase client."""
    global _supabase
    _supabase = supabase_client

    # Initialize all AI services
    init_email_analyzer(supabase_client)
    init_bucket_engine(supabase_client)
    init_entity_aggregator(supabase_client)
    init_usage_tracker(supabase_client)
    init_digest_generator(supabase_client)

    logger.info("AI router and services initialized")


# ============================================================================
# AUTH HELPERS
# ============================================================================

def _validate_mailbox_access(mailbox_id: str, accessible_ids: list):
    """Raise 403 if user doesn't have access to this mailbox."""
    if mailbox_id not in accessible_ids:
        raise HTTPException(status_code=403, detail="You don't have access to this mailbox")


def _validate_client_access(client_id: str, accessible_ids: list):
    """Raise 403 if user has no accessible mailboxes for this client."""
    if not accessible_ids:
        raise HTTPException(status_code=403, detail="You don't have access to any mailboxes")
    try:
        resp = _supabase.table("mailboxes").select("id") \
            .eq("client_id", client_id).in_("id", accessible_ids).limit(1).execute()
        if not resp.data:
            raise HTTPException(status_code=403, detail="You don't have access to this client's data")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Client access validation failed: {e}")
        raise HTTPException(status_code=500, detail="Access validation error")


# Default date range for read queries
DEFAULT_READ_LOOKBACK_DAYS = 30


def _default_date_range(date_from: str = None, date_to: str = None, lookback_days: int = DEFAULT_READ_LOOKBACK_DAYS):
    """Apply default 30-day lookback if no dates provided."""
    if not date_from:
        date_from = (datetime.utcnow() - timedelta(days=lookback_days)).isoformat()
    if not date_to:
        date_to = datetime.utcnow().isoformat()
    return date_from, date_to


# ============================================================================
# INTELLIGENCE ENDPOINTS (3)
# ============================================================================

@router.post("/analyze/{mailbox_id}", response_model=AnalyzeResponse)
async def trigger_analysis(
    mailbox_id: str,
    data: AnalyzeRequest,
    background_tasks: BackgroundTasks,
    accessible_ids: list = Depends(get_accessible_mailbox_ids),
):
    """
    Trigger AI analysis on unanalyzed emails in a mailbox.

    Runs in background — returns immediately with accepted status.
    """
    _validate_mailbox_access(mailbox_id, accessible_ids)
    analyzer = get_email_analyzer()
    if not analyzer:
        raise HTTPException(status_code=503, detail="AI analyzer not initialized")

    # Validate mailbox exists
    try:
        resp = _supabase.table("mailboxes").select("id,client_id").eq("id", mailbox_id).execute()
        if not resp.data:
            raise HTTPException(status_code=404, detail=f"Mailbox {mailbox_id} not found")
        client_id = data.client_id or resp.data[0].get("client_id")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to validate mailbox: {str(e)[:200]}")

    def run_analysis():
        try:
            result = analyzer.analyze_all_unanalyzed(
                mailbox_id=mailbox_id,
                client_id=client_id,
                max_emails=data.max_emails,
                date_from=data.date_from,
                date_to=data.date_to,
            )
            logger.info(f"Analysis complete for {mailbox_id}: {result}")

            # Auto-run bucket engine after analysis
            bucket_engine = get_bucket_engine()
            if bucket_engine:
                bucket_result = bucket_engine.process_email_buckets(mailbox_id)
                logger.info(f"Bucket processing complete: {bucket_result}")

            # Auto-run entity aggregation
            entity_agg = get_entity_aggregator()
            if entity_agg:
                entity_result = entity_agg.aggregate_entities(mailbox_id, client_id)
                logger.info(f"Entity aggregation complete: {entity_result}")

        except Exception as e:
            logger.error(f"Background analysis failed for {mailbox_id}: {e}")

    background_tasks.add_task(run_analysis)

    return AnalyzeResponse(
        status="accepted",
        message=f"Analysis started for up to {data.max_emails} emails",
        mailbox_id=mailbox_id,
        max_emails=data.max_emails,
    )


@router.post("/reanalyze/{mailbox_id}", response_model=ReanalyzeResponse)
async def trigger_reanalysis(
    mailbox_id: str,
    data: ReanalyzeRequest,
    background_tasks: BackgroundTasks,
    accessible_ids: list = Depends(get_accessible_mailbox_ids),
):
    """
    Re-analyze emails that were processed with an older prompt version.

    Finds candidates with the specified prompt version, resets them to 'pending',
    then triggers analyze_all_unanalyzed() which picks them up naturally.
    """
    _validate_mailbox_access(mailbox_id, accessible_ids)
    from ..services.ai_email_analyzer import PROMPT_VERSION

    analyzer = get_email_analyzer()
    if not analyzer:
        raise HTTPException(status_code=503, detail="AI analyzer not initialized")

    # Validate mailbox exists
    try:
        resp = _supabase.table("mailboxes").select("id,client_id").eq("id", mailbox_id).execute()
        if not resp.data:
            raise HTTPException(status_code=404, detail=f"Mailbox {mailbox_id} not found")
        client_id = data.client_id or resp.data[0].get("client_id")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to validate mailbox: {str(e)[:200]}")

    # Don't allow re-analysis targeting the current prompt version
    if data.target_prompt_version == PROMPT_VERSION:
        raise HTTPException(
            status_code=400,
            detail=f"Target version {data.target_prompt_version} is the current version. Nothing to re-analyze."
        )

    # Find candidates
    candidates = analyzer.get_reanalysis_candidates(
        mailbox_id=mailbox_id,
        target_prompt_version=data.target_prompt_version,
        include_failed=data.include_failed,
        limit=data.max_emails,
    )

    if not candidates:
        return ReanalyzeResponse(
            status="no_candidates",
            message=f"No emails found with prompt_version={data.target_prompt_version}",
            mailbox_id=mailbox_id,
            emails_queued=0,
            old_prompt_version=data.target_prompt_version,
            new_prompt_version=PROMPT_VERSION,
        )

    # Reset candidates to pending
    email_ids = [c["email_id"] for c in candidates]
    reset_count = analyzer.reset_for_reanalysis(email_ids, mailbox_id)

    # Trigger analysis in background (same code path as normal analysis)
    def run_reanalysis():
        try:
            result = analyzer.analyze_all_unanalyzed(
                mailbox_id=mailbox_id,
                client_id=client_id,
                max_emails=reset_count,
            )
            logger.info(f"Re-analysis complete for {mailbox_id}: {result}")

            # Auto-run bucket engine after re-analysis
            bucket_engine = get_bucket_engine()
            if bucket_engine:
                bucket_engine.process_email_buckets(mailbox_id)

            # Auto-run entity aggregation
            entity_agg = get_entity_aggregator()
            if entity_agg:
                entity_agg.aggregate_entities(mailbox_id, client_id)

        except Exception as e:
            logger.error(f"Background re-analysis failed for {mailbox_id}: {e}")

    background_tasks.add_task(run_reanalysis)

    return ReanalyzeResponse(
        status="accepted",
        message=f"Re-analysis started: {reset_count} emails reset from {data.target_prompt_version} to {PROMPT_VERSION}",
        mailbox_id=mailbox_id,
        emails_queued=reset_count,
        old_prompt_version=data.target_prompt_version,
        new_prompt_version=PROMPT_VERSION,
    )


@router.get("/intelligence/{mailbox_id}", response_model=IntelligenceListResponse)
async def get_intelligence(
    mailbox_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    intent: Optional[str] = Query(default=None),
    urgency: Optional[str] = Query(default=None),
    sentiment: Optional[str] = Query(default=None),
    primary_bucket: Optional[str] = Query(default=None),
    action_type: Optional[str] = Query(default=None),
    business_signal: Optional[str] = Query(default=None),
    has_budget_signal: Optional[bool] = Query(default=None),
    has_buying_signal: Optional[bool] = Query(default=None),
    has_competitor_mention: Optional[bool] = Query(default=None),
    min_confidence: Optional[float] = Query(default=None, ge=0.0, le=1.0),
    processing_status: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None, description="Filter by email sent_date >= (ISO). Default: 30 days ago"),
    date_to: Optional[str] = Query(default=None, description="Filter by email sent_date <= (ISO). Default: now"),
    accessible_ids: list = Depends(get_accessible_mailbox_ids),
):
    """
    List AI intelligence results for a mailbox with filters.

    Supports 12 filter dimensions + pagination + date range.
    """
    _validate_mailbox_access(mailbox_id, accessible_ids)
    analyzer = get_email_analyzer()
    if not analyzer:
        raise HTTPException(status_code=503, detail="AI analyzer not initialized")

    date_from, date_to = _default_date_range(date_from, date_to)
    try:
        result = analyzer.get_intelligence(
            mailbox_id=mailbox_id,
            page=page,
            page_size=page_size,
            intent=intent,
            urgency=urgency,
            sentiment=sentiment,
            primary_bucket=primary_bucket,
            action_type=action_type,
            business_signal=business_signal,
            has_budget_signal=has_budget_signal,
            has_buying_signal=has_buying_signal,
            has_competitor_mention=has_competitor_mention,
            min_confidence=min_confidence,
            processing_status=processing_status,
            date_from=date_from,
            date_to=date_to,
        )
        return IntelligenceListResponse(**result)
    except Exception as e:
        logger.error(f"Failed to get intelligence: {e}")
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.get("/intelligence/stats/{mailbox_id}", response_model=IntelligenceStats)
async def get_intelligence_stats(
    mailbox_id: str,
    accessible_ids: list = Depends(get_accessible_mailbox_ids),
):
    """Get intelligence stats breakdown for a mailbox."""
    _validate_mailbox_access(mailbox_id, accessible_ids)
    analyzer = get_email_analyzer()
    if not analyzer:
        raise HTTPException(status_code=503, detail="AI analyzer not initialized")

    try:
        stats = analyzer.get_stats(mailbox_id)
        return IntelligenceStats(**stats)
    except Exception as e:
        logger.error(f"Failed to get intelligence stats: {e}")
        raise HTTPException(status_code=500, detail=str(e)[:200])


# ============================================================================
# ACTION BUCKET ENDPOINTS (2)
# ============================================================================

@router.get("/action-items/{mailbox_id}")
async def get_action_items(
    mailbox_id: str,
    client_id: Optional[str] = Query(default=None),
    min_confidence: float = Query(default=0.5, ge=0.0, le=1.0),
    limit: int = Query(default=50, ge=1, le=200),
    date_from: Optional[str] = Query(default=None, description="Filter by email sent_date >= (ISO). Default: 30 days ago"),
    date_to: Optional[str] = Query(default=None, description="Filter by email sent_date <= (ISO). Default: now"),
    accessible_ids: list = Depends(get_accessible_mailbox_ids),
):
    """
    Get prioritized action items from all buckets.

    Sorted by severity (critical > high > medium) then confidence.
    Date-scoped to last 30 days by default.
    """
    _validate_mailbox_access(mailbox_id, accessible_ids)
    engine = get_bucket_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="Bucket engine not initialized")

    date_from, date_to = _default_date_range(date_from, date_to)
    try:
        items = engine.get_action_items(
            client_id=client_id or "",
            mailbox_id=mailbox_id,
            min_confidence=min_confidence,
            limit=limit,
            date_from=date_from,
            date_to=date_to,
        )
        return ActionItemsResponse(
            items=[ActionItem(**item) for item in items],
            total=len(items),
        )
    except Exception as e:
        logger.error(f"Failed to get action items: {e}")
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.get("/action-items/{mailbox_id}/summary", response_model=BucketSummary)
async def get_bucket_summary(
    mailbox_id: str,
    client_id: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None, description="Filter by email sent_date >= (ISO). Default: 30 days ago"),
    date_to: Optional[str] = Query(default=None, description="Filter by email sent_date <= (ISO). Default: now"),
    accessible_ids: list = Depends(get_accessible_mailbox_ids),
):
    """Get bucket counts summary for a mailbox. Date-scoped to last 30 days by default."""
    _validate_mailbox_access(mailbox_id, accessible_ids)
    engine = get_bucket_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="Bucket engine not initialized")

    date_from, date_to = _default_date_range(date_from, date_to)
    try:
        summary = engine.get_bucket_summary(
            mailbox_id=mailbox_id,
            client_id=client_id,
            date_from=date_from,
            date_to=date_to,
        )
        total = sum(summary.values())
        return BucketSummary(**summary, total=total)
    except Exception as e:
        logger.error(f"Failed to get bucket summary: {e}")
        raise HTTPException(status_code=500, detail=str(e)[:200])


# ============================================================================
# HUMAN FEEDBACK ENDPOINT (1)
# ============================================================================

@router.post("/intelligence/{email_id}/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    email_id: str,
    data: FeedbackRequest,
    accessible_ids: list = Depends(get_accessible_mailbox_ids),
):
    """
    Submit structured human feedback on an AI classification.

    Stores what was wrong (intent/bucket/sentiment/urgency) + correct value.
    """
    try:
        # Find the intelligence row for this email and validate mailbox access
        resp = _supabase.table("ai_email_intelligence") \
            .select("id,mailbox_id") \
            .eq("email_id", email_id) \
            .execute()

        if not resp.data:
            raise HTTPException(status_code=404, detail=f"No intelligence found for email {email_id}")

        _validate_mailbox_access(resp.data[0].get("mailbox_id", ""), accessible_ids)
        intel_id = resp.data[0]["id"]

        # Build update
        update = {
            "human_feedback": data.feedback.value,
            "feedback_at": datetime.utcnow().isoformat(),
        }
        if data.feedback_field:
            update["feedback_field"] = data.feedback_field
        if data.override_intent:
            update["human_override_intent"] = data.override_intent
        if data.override_bucket:
            update["human_override_bucket"] = data.override_bucket
        if data.override_sentiment:
            update["human_override_sentiment"] = data.override_sentiment
        if data.note:
            update["feedback_note"] = data.note

        _supabase.table("ai_email_intelligence") \
            .update(update) \
            .eq("id", intel_id) \
            .execute()

        return FeedbackResponse(
            status="saved",
            email_id=email_id,
            feedback=data.feedback.value,
            feedback_field=data.feedback_field,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e)[:200])


# ============================================================================
# ENTITY ENDPOINTS (3)
# ============================================================================

@router.get("/entities/{client_id}")
async def get_entities(
    client_id: str,
    entity_type: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    accessible_ids: list = Depends(get_accessible_mailbox_ids),
):
    """Get aggregated business entities for a client."""
    _validate_client_access(client_id, accessible_ids)
    aggregator = get_entity_aggregator()
    if not aggregator:
        raise HTTPException(status_code=503, detail="Entity aggregator not initialized")

    try:
        entities = aggregator.get_entities(
            client_id=client_id,
            entity_type=entity_type,
            limit=limit,
        )
        return EntityListResponse(
            items=[BusinessEntity(**e) for e in entities],
            total=len(entities),
        )
    except Exception as e:
        logger.error(f"Failed to get entities: {e}")
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.get("/entities/{client_id}/competitors", response_model=CompetitorLandscape)
async def get_competitor_landscape(
    client_id: str,
    accessible_ids: list = Depends(get_accessible_mailbox_ids),
):
    """Get competitor analysis for a client."""
    _validate_client_access(client_id, accessible_ids)
    aggregator = get_entity_aggregator()
    if not aggregator:
        raise HTTPException(status_code=503, detail="Entity aggregator not initialized")

    try:
        landscape = aggregator.get_competitor_landscape(client_id)
        return CompetitorLandscape(
            competitors=[BusinessEntity(**c) for c in landscape["competitors"]],
            total_mentions=landscape["total_mentions"],
            accounts_affected=landscape["accounts_affected"],
        )
    except Exception as e:
        logger.error(f"Failed to get competitor landscape: {e}")
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.get("/entities/{client_id}/opportunities")
async def get_opportunity_signals(
    client_id: str,
    mailbox_id: str = Query(..., description="Mailbox UUID"),
    limit: int = Query(default=50, ge=1, le=200),
    date_from: Optional[str] = Query(default=None, description="Filter by email sent_date >= (ISO). Default: 30 days ago"),
    date_to: Optional[str] = Query(default=None, description="Filter by email sent_date <= (ISO). Default: now"),
    accessible_ids: list = Depends(get_accessible_mailbox_ids),
):
    """Get opportunity signals (emails with high business signals). Date-scoped to last 30 days by default."""
    _validate_mailbox_access(mailbox_id, accessible_ids)
    aggregator = get_entity_aggregator()
    if not aggregator:
        raise HTTPException(status_code=503, detail="Entity aggregator not initialized")

    date_from, date_to = _default_date_range(date_from, date_to)
    try:
        signals = aggregator.get_opportunity_signals(
            client_id=client_id,
            mailbox_id=mailbox_id,
            limit=limit,
            date_from=date_from,
            date_to=date_to,
        )
        return OpportunitySignalsResponse(
            items=[OpportunitySignal(**s) for s in signals],
            total=len(signals),
        )
    except Exception as e:
        logger.error(f"Failed to get opportunity signals: {e}")
        raise HTTPException(status_code=500, detail=str(e)[:200])


# ============================================================================
# BUCKET CONFIG ENDPOINT (utility)
# ============================================================================

@router.get("/buckets/config")
async def get_bucket_config(
    current_user: dict = Depends(get_current_user),
):
    """Get bucket configuration for frontend display (labels, colors, severity)."""
    return BUCKET_CONFIG


# ============================================================================
# DIGEST ENDPOINTS (2) — Session 5
# ============================================================================

@router.get("/digest/{mailbox_id}")
async def get_digest(
    mailbox_id: str,
    date: Optional[str] = Query(default=None, description="Date in YYYY-MM-DD format"),
    client_id: Optional[str] = Query(default=None),
    force: bool = Query(default=False, description="Force regeneration, bypassing cache"),
    accessible_ids: list = Depends(get_accessible_mailbox_ids),
):
    """
    Get daily digest for a mailbox. Returns cached digest or generates new one.

    If no date provided, uses today. Uses cache-first strategy.
    Pass force=true to bypass cache and regenerate.
    """
    _validate_mailbox_access(mailbox_id, accessible_ids)
    from datetime import date as date_type

    generator = get_digest_generator()
    if not generator:
        raise HTTPException(status_code=503, detail="Digest generator not initialized")

    try:
        target_date = date_type.fromisoformat(date) if date else date_type.today()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    try:
        if force:
            result = generator.generate_digest(
                mailbox_id=mailbox_id,
                client_id=client_id,
                digest_date=target_date,
            )
        else:
            result = generator.get_digest_or_generate(
                mailbox_id=mailbox_id,
                client_id=client_id,
                digest_date=target_date,
            )
        if result is None:
            raise HTTPException(
                status_code=503,
                detail="Failed to generate digest. AI service may be unavailable."
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get digest: {e}")
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.get("/digest/{mailbox_id}/history")
async def get_digest_history(
    mailbox_id: str,
    limit: int = Query(default=30, ge=1, le=90),
    accessible_ids: list = Depends(get_accessible_mailbox_ids),
):
    """Get past digests for a mailbox, newest first."""
    _validate_mailbox_access(mailbox_id, accessible_ids)
    generator = get_digest_generator()
    if not generator:
        raise HTTPException(status_code=503, detail="Digest generator not initialized")

    try:
        digests = generator.get_digest_history(mailbox_id=mailbox_id, limit=limit)
        return {"items": digests, "total": len(digests)}
    except Exception as e:
        logger.error(f"Failed to get digest history: {e}")
        raise HTTPException(status_code=500, detail=str(e)[:200])


# ============================================================================
# USAGE & MONITORING ENDPOINTS (Session 11 — moved up for urgency)
# ============================================================================

@router.get("/usage/costs")
async def get_usage_costs(
    client_id: Optional[str] = Query(default=None),
    days: int = Query(default=30, ge=1, le=365),
    current_user: dict = Depends(get_current_user),
):
    """
    Get AI usage cost summary.

    Returns total cost, cost by operation/model, failure rate, latency.
    """
    tracker = get_usage_tracker()
    if not tracker:
        raise HTTPException(status_code=503, detail="Usage tracker not initialized")

    try:
        summary = tracker.get_usage_summary(client_id=client_id, days=days)
        return {
            "total_cost_usd": summary.total_cost_usd,
            "total_input_tokens": summary.total_input_tokens,
            "total_output_tokens": summary.total_output_tokens,
            "total_requests": summary.total_requests,
            "by_operation": summary.by_operation,
            "by_model": summary.by_model,
            "failure_rate": summary.failure_rate,
            "avg_latency_ms": summary.avg_latency_ms,
        }
    except Exception as e:
        logger.error(f"Failed to get usage costs: {e}")
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.get("/usage/monitoring")
async def get_monitoring_stats(
    client_id: Optional[str] = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    """
    Get real-time monitoring metrics (last 24 hours).

    Returns failure rates, retry counts, cost per 1K emails.
    """
    tracker = get_usage_tracker()
    if not tracker:
        raise HTTPException(status_code=503, detail="Usage tracker not initialized")

    try:
        stats = tracker.get_monitoring_stats(client_id=client_id)
        return {
            "parse_failure_rate": stats.parse_failure_rate,
            "api_failure_rate": stats.api_failure_rate,
            "avg_retry_count": stats.avg_retry_count,
            "cost_per_1000_emails": stats.cost_per_1000_emails,
            "total_failures_24h": stats.total_failures_24h,
            "total_requests_24h": stats.total_requests_24h,
        }
    except Exception as e:
        logger.error(f"Failed to get monitoring stats: {e}")
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.get("/usage/recent")
async def get_recent_usage(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    """Get recent AI usage log entries for real-time monitoring."""
    tracker = get_usage_tracker()
    if not tracker:
        raise HTTPException(status_code=503, detail="Usage tracker not initialized")

    try:
        resp = tracker._execute_with_retry(
            tracker.client.table("ai_usage_log")
            .select("*")
            .order("created_at", desc=True)
            .range(0, limit - 1)
        )
        items = resp.data or []
        # Sanitize nulls
        for item in items:
            for key in ["operation", "model", "error_type", "prompt_version"]:
                if item.get(key) is None:
                    item[key] = ""
        return {"items": items, "total": len(items)}
    except Exception as e:
        logger.error(f"Failed to get recent usage: {e}")
        raise HTTPException(status_code=500, detail=str(e)[:200])


# ============================================================================
# AI CONTROL SWITCHES (admin-level)
# ============================================================================

@router.get("/controls")
async def get_ai_controls(
    current_user: dict = Depends(require_role('admin')),
):
    """
    Get current AI control settings. Admin only.

    Returns: kill switch, feature toggles, budget caps, batch settings,
    session spend tracking.
    """
    settings = get_ai_settings()
    return {
        # Master switch
        "ai_enabled": settings.ai_enabled,
        # Feature toggles
        "email_analysis_enabled": settings.email_analysis_enabled,
        "digest_enabled": settings.digest_enabled,
        "relationship_summary_enabled": settings.relationship_summary_enabled,
        # Budget controls
        "daily_budget_usd": settings.daily_budget_usd,
        "monthly_budget_usd": settings.monthly_budget_usd,
        # Batch controls
        "batch_size": settings.batch_size,
        "max_emails_per_run": settings.max_emails_per_run,
        # Rate controls
        "max_requests_per_second": settings.max_requests_per_second,
        # Session tracking (live)
        "session_spend_usd": round(settings.session_spend_usd, 6),
        "session_requests": settings.session_requests,
    }


@router.put("/controls")
async def update_ai_controls(
    data: dict,
    current_user: dict = Depends(require_role('admin')),
):
    """
    Update AI control settings. Admin only.

    Accepts any combination of:
    - ai_enabled: bool — master kill switch
    - email_analysis_enabled: bool
    - digest_enabled: bool
    - relationship_summary_enabled: bool
    - daily_budget_usd: float
    - monthly_budget_usd: float
    - batch_size: int
    - max_emails_per_run: int
    - max_requests_per_second: float
    """
    # Whitelist allowed fields
    allowed = {
        "ai_enabled", "email_analysis_enabled", "digest_enabled",
        "relationship_summary_enabled", "daily_budget_usd", "monthly_budget_usd",
        "batch_size", "max_emails_per_run", "max_requests_per_second",
    }
    updates = {k: v for k, v in data.items() if k in allowed}

    if not updates:
        raise HTTPException(status_code=400, detail="No valid fields provided")

    settings = update_ai_settings(**updates)
    logger.info(f"AI controls updated: {updates}")

    return {
        "status": "updated",
        "settings": {
            "ai_enabled": settings.ai_enabled,
            "email_analysis_enabled": settings.email_analysis_enabled,
            "digest_enabled": settings.digest_enabled,
            "relationship_summary_enabled": settings.relationship_summary_enabled,
            "daily_budget_usd": settings.daily_budget_usd,
            "monthly_budget_usd": settings.monthly_budget_usd,
            "batch_size": settings.batch_size,
            "max_emails_per_run": settings.max_emails_per_run,
            "max_requests_per_second": settings.max_requests_per_second,
            "session_spend_usd": round(settings.session_spend_usd, 6),
            "session_requests": settings.session_requests,
        },
    }


@router.post("/controls/reset-session-spend")
async def reset_session_spend(
    current_user: dict = Depends(require_role('admin')),
):
    """Reset the session spend counter (e.g., at start of new day). Admin only."""
    settings = get_ai_settings()
    old_spend = settings.session_spend_usd
    settings.session_spend_usd = 0.0
    settings.session_requests = 0
    logger.info(f"Session spend reset from ${old_spend:.6f} to $0.00")
    return {"status": "reset", "previous_spend_usd": round(old_spend, 6)}


# ============================================================================
# ON-DEMAND SUMMARIZE ENDPOINT
# ============================================================================

@router.post("/summarize/{email_id}")
async def summarize_email(email_id: str):
    """Generate an on-demand AI summary for a single email using Haiku."""
    try:
        # Fetch the email
        result = _supabase.table('emails').select(
            'id, subject, sender_email, sender_name, body_text, body_html, sent_date, is_outbound'
        ).eq('id', email_id).single().execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Email not found")

        email = result.data
        body = email.get('body_text') or ''
        if not body and email.get('body_html'):
            import re
            body = re.sub(r'<[^>]+>', ' ', email['body_html'])
            body = re.sub(r'\s+', ' ', body).strip()

        if not body or len(body.strip()) < 20:
            return {"summary": "Email has insufficient content to summarize."}

        # Truncate to 2000 chars for cost efficiency
        body_truncated = body[:2000]

        from ..services.ai_client import get_ai_client
        ai = get_ai_client()

        system_prompt = "You are an email summarizer. Provide concise, actionable summaries in 2-3 sentences."
        user_message = f"""Summarize this email. Focus on the key message, any action items, and important details.

Subject: {email.get('subject', '(No subject)')}
From: {email.get('sender_name', '')} <{email.get('sender_email', '')}>
Date: {email.get('sent_date', '')}
Direction: {'Outbound' if email.get('is_outbound') else 'Inbound'}

Body:
{body_truncated}"""

        response = ai.call_haiku(system_prompt, user_message, max_tokens=300)
        if not response:
            return {"summary": "Unable to generate summary at this time."}
        return {"summary": response.content}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to summarize email {email_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
