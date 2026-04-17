"""
AI Intelligence Router — Sprint 3

9 initial endpoints for intelligence, buckets, feedback, and entities.
Digest, relationship, and usage endpoints added in Sessions 5, 8, 11.

Pattern: global _supabase, init_ai_router(supabase_client) function.
Router prefix: /ai, tags: ["ai-intelligence"]
"""

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks, Depends, Request
from fastapi.responses import StreamingResponse
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import asyncio
import logging
import os
import time as _time

# ── In-memory progress / cancel stores (per client_id) ───────────────────────
# Safe for single-instance deployments (Railway / single Uvicorn worker).
_digest_progress: Dict[str, Dict[str, Any]] = {}
_digest_cancel: Dict[str, bool] = {}  # True = cancellation requested

from ..dependencies.auth import get_current_user, require_role, get_accessible_mailbox_ids
from ..utils.audit import log_audit, audit_from_user

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

    # Load persisted settings from DB (survives restarts)
    _load_persisted_api_keys()
    _load_persisted_model_settings()

    # AI settings are now per-tenant and loaded lazily via get_ai_settings(client_id).
    # No startup pre-load — the old single-client pre-load was the source of the
    # "whoever loaded last wins" multi-tenancy bug.

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
    current_user: dict = Depends(get_current_user),
    accessible_ids: list = Depends(get_accessible_mailbox_ids),
):
    """
    Trigger AI analysis on unanalyzed emails in a mailbox.

    Creates a pending job — execution happens on the worker process.
    """
    _validate_mailbox_access(mailbox_id, accessible_ids)

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

    from ..services.jobs import create_job, JobSpec, JobAlreadyActive
    try:
        job_id = create_job(_supabase, JobSpec(
            job_type="ai_analysis",
            mailbox_id=mailbox_id,
            client_id=client_id,
            initial_status="pending",
            parameters={
                "max_emails": data.max_emails,
                "date_from": data.date_from,
                "date_to": data.date_to,
            },
            triggered_by="user",
        ))
    except JobAlreadyActive as e:
        return AnalyzeResponse(
            status="already_running",
            message=str(e),
            mailbox_id=mailbox_id,
            max_emails=data.max_emails,
        )

    audit_from_user(current_user, "analyze", "mailbox", resource_id=mailbox_id, details={"max_emails": data.max_emails})

    return AnalyzeResponse(
        status="accepted",
        message=f"Analysis queued for up to {data.max_emails} emails — worker will pick it up shortly",
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
    from ..services.ai_prompt_loader import get_prompt_version, PROMPT_KEY_EMAIL_ANALYSIS_SYSTEM

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

    # Use the DB prompt's version as current (reflects playground edits)
    current_version = get_prompt_version(_supabase, PROMPT_KEY_EMAIL_ANALYSIS_SYSTEM, PROMPT_VERSION, client_id)

    # Don't allow re-analysis targeting the current prompt version
    if data.target_prompt_version == current_version:
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
            new_prompt_version=current_version,
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
        message=f"Re-analysis started: {reset_count} emails reset from {data.target_prompt_version} to {current_version}",
        mailbox_id=mailbox_id,
        emails_queued=reset_count,
        old_prompt_version=data.target_prompt_version,
        new_prompt_version=current_version,
    )


@router.post("/backfill-intent")
async def trigger_backfill_intent(
    client_id: Optional[str] = Query(default=None),
    mailbox_id: Optional[str] = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    """
    Backfill AI intent classification for unanalyzed emails.

    Analyzes ALL pending emails (no 7-day lookback limit).
    Can target a specific mailbox or all mailboxes for a client.
    Used by Data Health page to fill classification gaps.

    Creates a pending job — execution happens on the worker process.
    """
    # Determine which mailboxes to process
    if mailbox_id:
        mailbox_ids = [mailbox_id]
        # Get client_id from mailbox
        try:
            resp = _supabase.table("mailboxes").select("client_id").eq("id", mailbox_id).limit(1).execute()
            if resp.data:
                client_id = resp.data[0].get("client_id")
        except Exception:
            pass
    elif client_id:
        try:
            resp = _supabase.table("mailboxes").select("id").eq("client_id", client_id).execute()
            mailbox_ids = [m["id"] for m in (resp.data or [])]
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to get mailboxes: {str(e)[:200]}")
    else:
        raise HTTPException(status_code=400, detail="Provide client_id or mailbox_id")

    if not mailbox_ids:
        return {"status": "no_mailboxes", "message": "No mailboxes found", "mailboxes": []}

    from ..services.jobs import create_job, JobSpec, JobAlreadyActive
    try:
        job_id = create_job(_supabase, JobSpec(
            job_type="ai_backfill",
            mailbox_id=mailbox_ids[0] if len(mailbox_ids) == 1 else None,
            client_id=client_id,
            initial_status="pending",
            parameters={"mailbox_ids": mailbox_ids},
            triggered_by="user",
        ))
    except JobAlreadyActive as e:
        return {
            "status": "already_running",
            "message": str(e),
            "job_id": e.existing_job.get("id"),
        }

    audit_from_user(current_user, "backfill_intent", "client", resource_id=client_id or "unknown")

    return {
        "status": "accepted",
        "message": f"Backfill queued for {len(mailbox_ids)} mailbox(es) — worker will pick it up shortly",
        "job_id": job_id,
        "mailbox_count": len(mailbox_ids),
    }


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
    has_response_urgency: Optional[bool] = Query(default=None),
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
            has_response_urgency=has_response_urgency,
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
# ACTION BUCKET ENDPOINTS (3)
# ============================================================================

@router.post("/rebucket/{mailbox_id}")
async def rebucket_mailbox(
    mailbox_id: str,
    background_tasks: BackgroundTasks,
    accessible_ids: list = Depends(get_accessible_mailbox_ids),
    current_user: dict = Depends(get_current_user),
):
    """Force re-derive all action buckets using the latest bucket engine (v3). No LLM cost."""
    _validate_mailbox_access(mailbox_id, accessible_ids)
    engine = get_bucket_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="Bucket engine not initialized")

    def _run():
        try:
            result = engine.process_email_buckets(mailbox_id, force=True)
            logger.info(f"Rebucket complete for {mailbox_id}: {result}")
        except Exception as e:
            logger.error(f"Rebucket failed for {mailbox_id}: {e}")

    background_tasks.add_task(_run)
    return {"status": "accepted", "message": "Re-bucketing started (force=True, $0 cost)"}


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
    tz_offset: Optional[int] = Query(default=None, description="Client UTC offset in minutes (JS getTimezoneOffset). E.g. -330 for IST"),
    digest_type: str = Query(default="daily", description="Digest type: 'daily' (1 day) or 'weekly' (7 days)"),
    accessible_ids: list = Depends(get_accessible_mailbox_ids),
):
    """
    Get daily or weekly digest for a mailbox. Returns cached digest or generates new one.

    If no date provided, uses today in the user's timezone.
    digest_type: 'daily' = 1 day window, 'weekly' = 7 day window ending on target date.
    tz_offset is the browser's getTimezoneOffset() value (negative = east of UTC).
    Pass force=true to bypass cache and regenerate.
    """
    if digest_type not in ("daily", "weekly"):
        raise HTTPException(status_code=400, detail="digest_type must be 'daily' or 'weekly'")

    _validate_mailbox_access(mailbox_id, accessible_ids)
    from datetime import date as date_type, timezone as tz_mod, timedelta

    generator = get_digest_generator()
    if not generator:
        raise HTTPException(status_code=503, detail="Digest generator not initialized")

    # Determine user's timezone from offset (JS getTimezoneOffset returns negative for east)
    user_tz = tz_mod(timedelta(minutes=-(tz_offset or 0)))

    try:
        if date:
            target_date = date_type.fromisoformat(date)
        else:
            # Use "today" in the user's timezone, not the server's
            target_date = datetime.now(user_tz).date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    # Apply client's model preferences before generating
    if client_id:
        from ..services.ai_email_analyzer import _load_client_api_keys
        _load_client_api_keys(_supabase, client_id)
    elif mailbox_id:
        # Resolve client_id from mailbox if not provided
        try:
            mb_resp = _supabase.table("mailboxes").select("client_id").eq("id", mailbox_id).limit(1).execute()
            if mb_resp.data and mb_resp.data[0].get("client_id"):
                resolved_client = mb_resp.data[0]["client_id"]
                client_id = resolved_client
                from ..services.ai_email_analyzer import _load_client_api_keys
                _load_client_api_keys(_supabase, resolved_client)
        except Exception:
            pass

    tz_minutes = tz_offset or 0
    try:
        if force:
            result = generator.generate_digest(
                mailbox_id=mailbox_id,
                client_id=client_id,
                digest_date=target_date,
                tz_offset_minutes=tz_minutes,
                digest_type=digest_type,
            )
        else:
            result = generator.get_digest_or_generate(
                mailbox_id=mailbox_id,
                client_id=client_id,
                digest_date=target_date,
                tz_offset_minutes=tz_minutes,
                digest_type=digest_type,
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
    client_id: Optional[str] = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    """Get recent AI usage log entries for real-time monitoring."""
    tracker = get_usage_tracker()
    if not tracker:
        raise HTTPException(status_code=503, detail="Usage tracker not initialized")

    try:
        query = tracker.client.table("ai_usage_log").select(
            "id, operation, model, input_tokens, output_tokens, "
            "estimated_cost_usd, processing_time_ms, success, "
            "error_type, error_detail, created_at"
        )
        if client_id:
            query = query.eq("client_id", client_id)
        resp = tracker._execute_with_retry(
            query.order("created_at", desc=True).range(0, limit - 1)
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
    client_id: Optional[str] = Query(default=None),
    current_user: dict = Depends(require_role('admin')),
):
    """
    Get current AI control settings. All persisted to DB.

    Returns: kill switch, feature toggles, budget caps, batch settings,
    actual daily/monthly spend from ai_usage_log.
    """
    from ..services.ai_client import get_actual_spend

    if not client_id:
        raise HTTPException(status_code=400, detail="client_id required — AI settings are per-tenant")

    settings = get_ai_settings(client_id)

    # Per-tenant actual spend from DB
    daily_spend = get_actual_spend(client_id, 'daily')
    monthly_spend = get_actual_spend(client_id, 'monthly')

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
        # Actual spend (from ai_usage_log DB)
        "daily_spend_usd": daily_spend,
        "monthly_spend_usd": monthly_spend,
        # Batch controls
        "batch_size": settings.batch_size,
        "max_emails_per_run": settings.max_emails_per_run,
        # Rate controls
        "max_requests_per_second": settings.max_requests_per_second,
        # Model preferences (legacy)
        "cheap_model": settings.cheap_model,
        "strategic_model": settings.strategic_model,
    }


@router.put("/controls")
async def update_ai_controls(
    data: dict,
    current_user: dict = Depends(require_role('admin')),
):
    """
    Update AI control settings. Persists to system_settings DB table.
    Survives server restarts.
    """
    client_id = data.pop("client_id", None)
    if not client_id:
        raise HTTPException(status_code=400, detail="client_id required — AI settings are per-tenant")

    # Whitelist allowed fields
    allowed = {
        "ai_enabled", "email_analysis_enabled", "digest_enabled",
        "relationship_summary_enabled", "daily_budget_usd", "monthly_budget_usd",
        "batch_size", "max_emails_per_run", "max_requests_per_second",
        "cheap_model", "strategic_model",
    }
    updates = {k: v for k, v in data.items() if k in allowed}

    if not updates:
        raise HTTPException(status_code=400, detail="No valid fields provided")

    settings = update_ai_settings(client_id=client_id, **updates)
    logger.info(f"AI controls updated for client {client_id}: {list(updates.keys())}")

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
        },
    }


@router.get("/task-models")
async def get_task_models(
    client_id: Optional[str] = Query(default=None),
    current_user: dict = Depends(require_role('admin')),
):
    """Get current model assignment per AI task (DB > env > default)."""
    from ..services.langchain_core import get_all_task_models, get_available_models as _get_models
    task_models = get_all_task_models(client_id)
    models = _get_models()
    return {"task_models": task_models, "available_models": models}


@router.put("/task-models")
async def update_task_models(
    data: dict,
    current_user: dict = Depends(require_role('admin')),
):
    """Update model assignment for one or more AI tasks. Persists to DB."""
    from ..services.langchain_core import set_task_model, TASK_MODEL_DEFAULTS
    client_id = data.get("client_id")
    if not client_id:
        raise HTTPException(status_code=400, detail="client_id required")

    updated = []
    for task in TASK_MODEL_DEFAULTS:
        if task in data and data[task]:
            try:
                set_task_model(task, data[task], client_id)
                updated.append(f"{task}={data[task]}")
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

    return {"status": "ok", "updated": updated, "client_id": client_id}


@router.post("/controls/reset-session-spend")
async def reset_session_spend(
    current_user: dict = Depends(require_role('admin')),
):
    """Reset spend cache — forces next budget check to re-query the DB."""
    from ..services.ai_client import _spend_cache
    _spend_cache.clear()
    logger.info("Spend cache cleared — next budget check will re-query DB")
    return {"status": "reset", "message": "Spend cache cleared"}


# ============================================================================
# ON-DEMAND SUMMARIZE ENDPOINT
# ============================================================================

@router.post("/summarize/{email_id}")
async def summarize_email(email_id: str):
    """Generate an on-demand AI summary for a single email using Haiku.
    client_id is derived from the email row so budget enforcement resolves
    against the email's tenant, not the ambient process state."""
    try:
        result = _supabase.table('emails').select(
            'id, client_id, subject, sender_email, sender_name, body_text, body_html, sent_date, is_outbound'
        ).eq('id', email_id).single().execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Email not found")

        email = result.data
        client_id = email.get('client_id')
        if not client_id:
            raise HTTPException(status_code=500, detail="Email has no client_id — cannot resolve AI settings")

        body = email.get('body_text') or ''
        if not body and email.get('body_html'):
            import re
            body = re.sub(r'<[^>]+>', ' ', email['body_html'])
            body = re.sub(r'\s+', ' ', body).strip()

        if not body or len(body.strip()) < 20:
            return {"summary": "Email has insufficient content to summarize."}

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

        response = ai.call_cheap(client_id, system_prompt, user_message, max_tokens=300)
        if not response:
            return {"summary": "Unable to generate summary at this time."}
        return {"summary": response.content}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to summarize email {email_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# STRATEGIC DIGEST ENDPOINTS (Sprint 3)
# ============================================================================

@router.get("/strategic-digest/{client_id}")
async def get_strategic_digest(
    client_id: str,
    period_type: str = Query(default="monthly"),
    date: Optional[str] = Query(default=None),
):
    """Get cached strategic digest or return null if not generated yet."""
    try:
        query = _supabase.table('ai_strategic_digests').select('*').eq(
            'client_id', client_id
        ).eq('period_type', period_type).order('digest_date', desc=True).limit(1)

        if date:
            query = query.eq('digest_date', date)

        result = query.execute()
        if not result.data:
            return {"digest": None, "message": "No digest found. Generate one first."}

        return {"digest": result.data[0]}
    except Exception as e:
        logger.error(f"Failed to get strategic digest: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/strategic-digest/{client_id}/generate")
async def generate_strategic_digest(
    client_id: str,
    background_tasks: BackgroundTasks,
    period_type: str = Query(default="monthly"),
    period_start: Optional[str] = Query(default=None),
    period_end: Optional[str] = Query(default=None),
):
    """Generate a new strategic digest (runs in background)."""
    try:
        from ..services.strategic_digest_pipeline import StrategicDigestPipeline
        from datetime import date as date_type, timedelta

        # Parse dates or default to last 30 days
        today = date_type.today()
        try:
            end_date = date_type.fromisoformat(period_end) if period_end else today
            start_date = date_type.fromisoformat(period_start) if period_start else (today - timedelta(days=30))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")

        pipeline = StrategicDigestPipeline(_supabase, client_id)

        # Create a processing job for persistent progress tracking
        from ..services.jobs import create_job, JobSpec
        started_at = datetime.utcnow().isoformat()
        try:
            job_id = create_job(_supabase, JobSpec(
                job_type="strategic_digest",
                client_id=client_id,
                initial_status="running",
                parameters={"period_type": period_type, "client_id": client_id},
                triggered_by="user",
            ))
        except Exception as job_err:
            logger.warning(f"Could not create processing job: {job_err}")
            job_id = None

        # Also keep in-memory for fast polling
        _digest_progress[client_id] = {
            "phase": "starting", "current": 0, "total": 0, "pct": 0,
            "message": "Initialising…", "started_at": started_at, "job_id": job_id,
        }

        def _update_job(pct: int, msg: str, status: str = "running"):
            if not job_id:
                return
            try:
                update: dict = {
                    "status": status,
                    "error_summary": {"progress_pct": pct, "progress_message": msg, "client_id": client_id},
                }
                if status in ("completed", "failed", "cancelled"):
                    update["completed_at"] = datetime.utcnow().isoformat()
                _supabase.table("processing_jobs").update(update).eq("id", job_id).execute()
            except Exception:
                pass

        def _on_progress(phase: str, current: int, total: int, message: str = ""):
            pct = round(current / total * 100) if total else 0
            msg = message or f"{phase.replace('_', ' ').title()} ({current}/{total})"
            elapsed = round(_time.time() - _digest_progress.get(client_id, {}).get("_t0", _time.time()), 1)
            _digest_progress[client_id] = {
                "phase": phase, "current": current, "total": total, "pct": pct,
                "message": msg, "started_at": started_at, "elapsed_s": elapsed, "job_id": job_id,
            }
            _update_job(pct, msg)

        _digest_progress[client_id]["_t0"] = _time.time()
        _digest_cancel[client_id] = False

        def _cancel_check() -> bool:
            return _digest_cancel.get(client_id, False)

        async def _run():
            try:
                await pipeline.generate(
                    period_type=period_type,
                    period_start=start_date,
                    period_end=end_date,
                    on_progress=_on_progress,
                    cancel_check=_cancel_check,
                )
                if _cancel_check():
                    _digest_progress[client_id] = {
                        "phase": "cancelled", "pct": 0, "message": "Generation cancelled by user", "job_id": job_id,
                    }
                    _update_job(0, "Cancelled by user", "cancelled")
                else:
                    _digest_progress[client_id] = {
                        "phase": "completed", "pct": 100, "message": "Digest generated successfully", "job_id": job_id,
                    }
                    _update_job(100, "Digest generated successfully", "completed")
            except Exception as e:
                _digest_progress[client_id] = {
                    "phase": "failed", "pct": 0, "message": f"Generation failed: {str(e)[:200]}", "job_id": job_id,
                }
                _update_job(0, f"Failed: {str(e)[:200]}", "failed")
                logger.error(f"Strategic digest generation failed: {e}")

        background_tasks.add_task(_run)

        return {
            "status": "generating",
            "message": "Strategic digest generation started",
            "period_start": start_date.isoformat(),
            "period_end": end_date.isoformat(),
            "job_id": job_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start strategic digest: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/strategic-digest/{client_id}/progress")
async def get_digest_progress(client_id: str):
    """Return current generation progress. Checks in-memory first, falls back to DB."""
    entry = _digest_progress.get(client_id)
    if entry and entry.get("phase") not in (None, "idle"):
        return {k: v for k, v in entry.items() if k != "_t0"}

    # Check DB for a running job (survives page navigation and server restarts)
    try:
        resp = _supabase.table("processing_jobs").select(
            "id,status,error_summary,created_at"
        ).eq("job_type", "strategic_digest").eq(
            "status", "running"
        ).order("created_at", desc=True).limit(1).execute()

        if resp.data:
            job = resp.data[0]
            summary = job.get("error_summary") or {}
            if isinstance(summary, str):
                import json as _json
                summary = _json.loads(summary)
            # Only return if this job belongs to the requested client
            if summary.get("client_id") == client_id or not summary.get("client_id"):
                return {
                    "phase": "running",
                    "pct": summary.get("progress_pct", 0),
                    "message": summary.get("progress_message", "Generating..."),
                    "job_id": job["id"],
                    "started_at": job.get("created_at"),
                }
    except Exception:
        pass

    return {"phase": "idle", "pct": 0, "message": "No generation in progress"}


@router.post("/strategic-digest/{client_id}/cancel")
async def cancel_digest_generation(client_id: str):
    """Signal an in-progress generation to stop gracefully."""
    if _digest_progress.get(client_id, {}).get("phase") not in (
        "starting", "building_context", "am_performance", "ai_analysis"
    ):
        return {"status": "no_op", "message": "No active generation to cancel"}
    _digest_cancel[client_id] = True
    _digest_progress[client_id] = {
        **_digest_progress.get(client_id, {}),
        "phase": "cancelling",
        "message": "Cancelling — waiting for current batch to finish…",
    }
    return {"status": "ok", "message": "Cancellation requested"}


@router.post("/strategic-digest/{client_id}/stream")
async def stream_digest_generation(
    client_id: str,
    request: Request,
    period_type: str = Query(default="monthly"),
    period_start: Optional[str] = Query(default=None),
    period_end: Optional[str] = Query(default=None),
):
    """
    Generate a strategic digest with real-time SSE progress events.
    Replaces the generate + poll pattern with a single streaming connection.

    Events:
        event: progress  — {phase, pct, message}
        event: complete  — {digest: {...}}
        event: error     — {detail: "..."}
        event: cancelled — {}
    """
    import json as _json
    from ..services.strategic_digest_pipeline import StrategicDigestPipeline
    from datetime import date as date_type

    today = date_type.today()
    try:
        end_date = date_type.fromisoformat(period_end) if period_end else today
        start_date = date_type.fromisoformat(period_start) if period_start else (today - timedelta(days=30))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")

    # Apply client model settings
    try:
        from ..services.ai_email_analyzer import _load_client_api_keys
        _load_client_api_keys(_supabase, client_id)
    except Exception:
        pass

    pipeline = StrategicDigestPipeline(_supabase, client_id)
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    cancelled = False

    def _on_progress(phase: str, current: int, total: int, message: str = ""):
        pct = round(current / total * 100) if total else 0
        msg = message or f"{phase.replace('_', ' ').title()} ({current}/{total})"
        # Also update in-memory store so the polling endpoint stays in sync
        _digest_progress[client_id] = {
            "phase": phase, "current": current, "total": total, "pct": pct, "message": msg,
        }
        try:
            queue.put_nowait({"event": "progress", "phase": phase, "pct": pct, "message": msg})
        except asyncio.QueueFull:
            pass  # Drop stale progress events if consumer disconnected

    def _cancel_check() -> bool:
        return cancelled or _digest_cancel.get(client_id, False)

    async def _run_pipeline():
        nonlocal cancelled
        try:
            await pipeline.generate(
                period_type=period_type,
                period_start=start_date,
                period_end=end_date,
                on_progress=_on_progress,
                cancel_check=_cancel_check,
            )
            if _cancel_check():
                _digest_progress[client_id] = {"phase": "cancelled", "pct": 0, "message": "Cancelled"}
                queue.put_nowait({"event": "cancelled"})
            else:
                # Fetch the freshly generated digest
                try:
                    resp = _supabase.table("ai_strategic_digests").select("*").eq(
                        "client_id", client_id
                    ).order("created_at", desc=True).limit(1).execute()
                    digest_data = resp.data[0] if resp.data else None
                except Exception:
                    digest_data = None
                _digest_progress[client_id] = {"phase": "completed", "pct": 100, "message": "Done"}
                queue.put_nowait({"event": "complete", "digest": digest_data})
        except Exception as e:
            _digest_progress[client_id] = {"phase": "failed", "pct": 0, "message": str(e)[:200]}
            queue.put_nowait({"event": "error", "detail": str(e)[:300]})
            logger.error(f"Streaming digest generation failed: {e}")
        finally:
            queue.put_nowait(None)  # sentinel

    async def _generator():
        nonlocal cancelled
        _digest_cancel[client_id] = False
        task = asyncio.create_task(_run_pipeline())
        try:
            while True:
                if await request.is_disconnected():
                    cancelled = True
                    _digest_cancel[client_id] = True
                    break
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=2.0)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if item is None:
                    break
                event_type = item.pop("event")
                yield f"event: {event_type}\ndata: {_json.dumps(item)}\n\n"
        finally:
            if not task.done():
                cancelled = True
                _digest_cancel[client_id] = True
            # Drain remaining queue items to unblock pipeline callbacks
            while not queue.empty():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

    return StreamingResponse(
        _generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@router.get("/strategic-digest/{client_id}/history")
async def get_strategic_digest_history(
    client_id: str,
    limit: int = Query(default=10, ge=1, le=50),
):
    """Get past strategic digests for a client."""
    try:
        result = _supabase.table('ai_strategic_digests').select(
            'id, digest_date, period_type, period_start, period_end, '
            'companies_analyzed, emails_analyzed, total_cost_usd, created_at'
        ).eq('client_id', client_id).order('digest_date', desc=True).limit(limit).execute()

        return {"digests": result.data or []}
    except Exception as e:
        logger.error(f"Failed to get digest history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/am-performance/{client_id}")
async def get_am_performance(
    client_id: str,
    period_start: Optional[str] = Query(default=None),
    period_end: Optional[str] = Query(default=None),
):
    """Get AM performance snapshots for a client."""
    try:
        query = _supabase.table('am_performance_snapshots').select('*').eq(
            'client_id', client_id
        ).order('total_revenue', desc=True)

        if period_start:
            query = query.gte('period_start', period_start)
        if period_end:
            query = query.lte('period_end', period_end)

        result = query.execute()
        return {"snapshots": result.data or []}
    except Exception as e:
        logger.error(f"Failed to get AM performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# AI INSIGHTS ENDPOINTS (Sprint 3 — per-page "Analyze" button)
# ============================================================================

@router.get("/insights/company/{company_id}")
async def get_company_insight(
    company_id: str,
    force: bool = Query(default=False),
    client_id: Optional[str] = Query(default=None),
):
    """Generate AI insight for a company (cached 24h)."""
    try:
        # Apply client's model preferences so insights use the right model
        if client_id:
            from ..services.ai_email_analyzer import _load_client_api_keys
            _load_client_api_keys(_supabase, client_id)
        from ..services.ai_insights_engine import AIInsightsEngine
        engine = AIInsightsEngine(_supabase, client_id=client_id)
        result = await engine.get_company_insight(company_id, force=force)
        return {"insight": result}
    except Exception as e:
        logger.error(f"Failed to get company insight: {e}")
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/insights/contact/{contact_id}")
async def get_contact_insight(
    contact_id: str,
    force: bool = Query(default=False),
    client_id: Optional[str] = Query(default=None),
):
    """Generate AI insight for a contact (cached 24h)."""
    try:
        if client_id:
            from ..services.ai_email_analyzer import _load_client_api_keys
            _load_client_api_keys(_supabase, client_id)
        from ..services.ai_insights_engine import AIInsightsEngine
        engine = AIInsightsEngine(_supabase, client_id=client_id)
        result = await engine.get_contact_insight(contact_id, force=force)
        return {"insight": result}
    except Exception as e:
        logger.error(f"Failed to get contact insight: {e}")
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/insights/thread/{thread_id}")
async def get_thread_insight(
    thread_id: str,
    force: bool = Query(default=False),
    client_id: Optional[str] = Query(default=None),
):
    """Generate AI insight for a thread (cached 24h)."""
    try:
        if client_id:
            from ..services.ai_email_analyzer import _load_client_api_keys
            _load_client_api_keys(_supabase, client_id)
        from ..services.ai_insights_engine import AIInsightsEngine
        engine = AIInsightsEngine(_supabase, client_id=client_id)
        result = await engine.get_thread_insight(thread_id, force=force)
        return {"insight": result}
    except Exception as e:
        logger.error(f"Failed to get thread insight: {e}")
        raise HTTPException(status_code=500, detail=str(e)[:300])


# ============================================================================
# MODEL MANAGEMENT ENDPOINTS (Sprint 3 — multi-model support)
# ============================================================================

@router.get("/models")
async def get_available_models():
    """Get list of available AI models with their costs."""
    try:
        from ..services.langchain_core import get_available_models as _get_models
        return {"models": _get_models()}
    except Exception as e:
        logger.error(f"Failed to get models: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/client-settings")
async def get_client_settings(
    client_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    """Get all system_settings for a specific client."""
    try:
        resp = _supabase.table("system_settings").select("key,value").eq(
            "client_id", client_id
        ).execute()
        return resp.data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200])


def _get_client_setting(key: str, client_id: Optional[str] = None) -> Optional[str]:
    """Load a setting for a specific client. No global fallback."""
    if not _supabase or not client_id:
        return None
    try:
        resp = _supabase.table('system_settings').select('value').eq(
            'key', key
        ).eq('client_id', client_id).limit(1).execute()
        if resp.data:
            return resp.data[0]['value']
    except Exception:
        pass
    return None


def _upsert_client_setting(key: str, value: str, client_id: str):
    """Save a setting for a specific client."""
    if not _supabase or not client_id:
        return
    try:
        existing = _supabase.table('system_settings').select('id').eq(
            'key', key
        ).eq('client_id', client_id).limit(1).execute()

        row = {'key': key, 'value': value, 'client_id': client_id, 'updated_at': datetime.utcnow().isoformat()}

        if existing.data:
            _supabase.table('system_settings').update(row).eq('id', existing.data[0]['id']).execute()
        else:
            _supabase.table('system_settings').insert(row).execute()
    except Exception as e:
        logger.warning(f"Failed to save setting {key} for client {client_id}: {e}")


def _upsert_global_setting(key: str, value: str, client_id: str):
    """Save a global-scoped setting using client_id (system_settings.client_id is NOT NULL)."""
    _upsert_client_setting(key, value, client_id)


def _get_global_setting(key: str, client_id: str) -> Optional[str]:
    """Read a global-scoped setting by client_id."""
    return _get_client_setting(key, client_id)


@router.get("/api-keys")
async def get_api_keys(
    client_id: Optional[str] = Query(default=None),
    current_user: dict = Depends(require_role('admin')),
):
    """Get API key status. Client-specific → global → env fallback."""
    import os, base64

    def mask(k: str) -> str:
        return k[:4] + "****" + k[-4:] if len(k) > 8 else ("****" if k else "")

    def _decode_db_key(db_value: Optional[str]) -> Optional[str]:
        """Safely decode a base64-encoded API key from DB."""
        if not db_value:
            return None
        try:
            return base64.b64decode(db_value).decode()
        except Exception:
            return None

    # Load from DB (client → global) then env
    anthropic = ""
    anthropic_source = "none"
    db_val = _decode_db_key(_get_client_setting('api_key_anthropic', client_id))
    if db_val:
        anthropic = db_val
        anthropic_source = "db"
    elif os.environ.get("ANTHROPIC_API_KEY"):
        anthropic = os.environ["ANTHROPIC_API_KEY"]
        anthropic_source = "env"

    google = ""
    google_source = "none"
    db_val = _decode_db_key(_get_client_setting('api_key_google', client_id))
    if db_val:
        google = db_val
        google_source = "db"
    elif os.environ.get("GOOGLE_GENAI_API_KEY") or os.environ.get("GEMINI_API_KEY"):
        google = os.environ.get("GOOGLE_GENAI_API_KEY") or os.environ.get("GEMINI_API_KEY") or ""
        google_source = "env"

    openai_key = ""
    openai_source = "none"
    db_val = _decode_db_key(_get_client_setting('api_key_openai', client_id))
    if db_val:
        openai_key = db_val
        openai_source = "db"
    elif os.environ.get("OPENAI_API_KEY"):
        openai_key = os.environ["OPENAI_API_KEY"]
        openai_source = "env"

    logger.debug(f"API keys status: anthropic={anthropic_source}, google={google_source}, openai={openai_source} (client_id={client_id})")

    return {
        "anthropic_set": bool(anthropic),
        "anthropic_masked": mask(anthropic),
        "anthropic_source": anthropic_source,
        "google_set": bool(google),
        "google_masked": mask(google),
        "google_source": google_source,
        "openai_set": bool(openai_key),
        "openai_masked": mask(openai_key),
        "openai_source": openai_source,
        "providers_ready": {
            "anthropic": bool(anthropic),
            "google": bool(google),
            "openai": bool(openai_key),
        },
    }


@router.put("/api-keys")
async def update_api_keys(
    data: dict,
    current_user: dict = Depends(require_role('admin')),
):
    """Update API keys. Saves per-client if client_id provided, otherwise global."""
    import os, base64
    client_id = data.get("client_id")
    updated = []

    if data.get("anthropic_api_key"):
        encoded = base64.b64encode(data["anthropic_api_key"].encode()).decode()
        _upsert_client_setting('api_key_anthropic', encoded, client_id)
        # Also set in env for immediate use
        os.environ["ANTHROPIC_API_KEY"] = data["anthropic_api_key"]
        updated.append("anthropic")

    if data.get("google_api_key"):
        encoded = base64.b64encode(data["google_api_key"].encode()).decode()
        _upsert_client_setting('api_key_google', encoded, client_id)
        os.environ["GOOGLE_GENAI_API_KEY"] = data["google_api_key"]
        updated.append("google")

    if data.get("openai_api_key"):
        encoded = base64.b64encode(data["openai_api_key"].encode()).decode()
        _upsert_client_setting('api_key_openai', encoded, client_id)
        os.environ["OPENAI_API_KEY"] = data["openai_api_key"]
        updated.append("openai")

    return {"status": "ok", "updated": updated, "client_id": client_id}


@router.put("/models/defaults")
async def update_default_models(
    cheap_model: str = Query(default="haiku"),
    strategic_model: str = Query(default="sonnet"),
    client_id: Optional[str] = Query(default=None),
):
    """Update default model preferences. client_id is required so the change
    is scoped to one tenant's system_settings row + settings cache."""
    if not client_id:
        raise HTTPException(status_code=400, detail="client_id required — model defaults are per-tenant")
    from ..services.langchain_core import set_default_models
    try:
        set_default_models(cheap=cheap_model, strategic=strategic_model)
        update_ai_settings(client_id=client_id, cheap_model=cheap_model, strategic_model=strategic_model)
        return {"status": "ok", "cheap": cheap_model, "strategic": strategic_model, "client_id": client_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/embedding-config")
async def get_embedding_config(
    client_id: Optional[str] = Query(default=None),
    current_user: dict = Depends(require_role('admin')),
):
    """Get current embedding provider configuration. DB > 'google' default."""
    db_provider = _get_global_setting('embedding_provider', client_id)
    db_model = _get_global_setting('embedding_model', client_id)

    provider = db_provider or "google"
    model = db_model or ("text-embedding-3-small" if provider == "openai" else "models/gemini-embedding-001")

    return {
        "provider": provider,
        "provider_source": "db" if db_provider else "default",
        "model": model,
        "model_source": "db" if db_model else "default",
        "available_providers": [
            {"value": "google", "label": "Google Gemini (gemini-embedding-001)", "requires": "Google API Key"},
            {"value": "openai", "label": "OpenAI (text-embedding-3-small)", "requires": "OpenAI API Key"},
        ],
    }


@router.put("/embedding-config")
async def update_embedding_config(
    data: dict,
    current_user: dict = Depends(require_role('admin')),
):
    """Update embedding provider. Clears model cache so next embed call uses new provider."""
    client_id = data.get("client_id")
    provider = data.get("provider", "").lower()

    if provider not in ("google", "openai"):
        raise HTTPException(status_code=400, detail=f"Invalid provider: {provider}. Must be 'google' or 'openai'.")

    _upsert_global_setting('embedding_provider', provider, client_id)

    model = data.get("model")
    if model:
        _upsert_global_setting('embedding_model', model, client_id)

    # Clear the cached model and pass the new provider explicitly
    from ..services.vector_service import reset_embedding_model
    reset_embedding_model(provider=provider)

    return {"status": "ok", "provider": provider, "model": model, "client_id": client_id}


def _load_persisted_api_keys():
    """No-op: API keys are per-client now. Env vars serve as baseline."""
    logger.info("API keys are per-client (system_settings). Env vars used as baseline.")


def _load_persisted_model_settings():
    """No-op: Model settings are per-client now. Env vars serve as baseline."""
    logger.info("Model settings are per-client (system_settings). Env defaults used as baseline.")


# ============================================================================
# PROMPT CONFIGURATION ENDPOINTS
# ============================================================================

@router.get("/prompts")
async def list_prompts(
    client_id: Optional[str] = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    """List all configurable prompts (global + client-specific)."""
    try:
        query = _supabase.table("ai_prompt_config").select("*").order("prompt_key")
        if client_id:
            # Return client-specific + global defaults
            resp = query.or_(f"client_id.eq.{client_id},client_id.is.null").execute()
        else:
            resp = query.execute()
        return {"prompts": resp.data or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.get("/prompts/defaults")
async def get_prompt_defaults(
    current_user: dict = Depends(get_current_user),
):
    """Return all hardcoded default prompts (for reference when editing)."""
    from ..services.ai_email_analyzer import SYSTEM_PROMPT as EMAIL_SYSTEM, USER_PROMPT_TEMPLATE as EMAIL_USER
    from ..services.strategic_digest_pipeline import STRATEGIC_DIGEST_SYSTEM_PROMPT
    from ..services.ai_digest_generator import DIGEST_SYSTEM_PROMPT, WEEKLY_DIGEST_SYSTEM_PROMPT
    from ..services.ai_insights_engine import COMPANY_INSIGHT_PROMPT, CONTACT_INSIGHT_PROMPT, THREAD_INSIGHT_PROMPT

    return {
        "defaults": [
            {"prompt_key": "email_analysis_system", "description": "System prompt for per-email AI classification", "prompt_text": EMAIL_SYSTEM},
            {"prompt_key": "email_analysis_user", "description": "User prompt template for email batch (use {emails_json})", "prompt_text": EMAIL_USER},
            {"prompt_key": "strategic_digest", "description": "System prompt for strategic digest LangGraph agent", "prompt_text": STRATEGIC_DIGEST_SYSTEM_PROMPT},
            {"prompt_key": "daily_digest", "description": "System prompt for daily digest generation", "prompt_text": DIGEST_SYSTEM_PROMPT},
            {"prompt_key": "weekly_digest", "description": "System prompt for weekly strategic review (trends, patterns, pipeline)", "prompt_text": WEEKLY_DIGEST_SYSTEM_PROMPT},
            {"prompt_key": "insight_company", "description": "System prompt for company AI insights", "prompt_text": COMPANY_INSIGHT_PROMPT},
            {"prompt_key": "insight_contact", "description": "System prompt for contact AI insights", "prompt_text": CONTACT_INSIGHT_PROMPT},
            {"prompt_key": "insight_thread", "description": "System prompt for thread AI insights", "prompt_text": THREAD_INSIGHT_PROMPT},
        ]
    }


@router.put("/prompts")
async def upsert_prompt(
    data: dict,
    current_user: dict = Depends(get_current_user),
):
    """Create or update a prompt. Body: {client_id, prompt_key, prompt_text, description?}"""
    import hashlib

    prompt_key = data.get("prompt_key")
    prompt_text = data.get("prompt_text")
    client_id = data.get("client_id")
    if not prompt_key or not prompt_text:
        raise HTTPException(status_code=400, detail="prompt_key and prompt_text are required")
    if not client_id:
        raise HTTPException(status_code=400, detail="client_id is required")

    # Auto-compute content hash as version — no manual versioning
    content_hash = hashlib.sha256(prompt_text.encode()).hexdigest()[:8]

    try:
        # Check if row already exists for this client + key
        existing = _supabase.table("ai_prompt_config").select("id").eq(
            "client_id", client_id
        ).eq("prompt_key", prompt_key).execute()

        row = {
            "client_id": client_id,
            "prompt_key": prompt_key,
            "prompt_text": prompt_text,
            "is_active": True,
            "description": data.get("description", ""),
            "version": content_hash,
            "updated_at": datetime.utcnow().isoformat(),
        }

        if existing.data:
            # Update existing
            resp = _supabase.table("ai_prompt_config").update(row).eq(
                "id", existing.data[0]["id"]
            ).execute()
        else:
            # Insert new
            resp = _supabase.table("ai_prompt_config").insert(row).execute()

        from ..services.ai_prompt_loader import invalidate_cache
        invalidate_cache(client_id, prompt_key)
        return {"status": "saved", "prompt": (resp.data or [None])[0]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.delete("/prompts/{prompt_id}")
async def delete_prompt(
    prompt_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete a prompt override (reverts to hardcoded default)."""
    try:
        _supabase.table("ai_prompt_config").delete().eq("id", prompt_id).execute()
        from ..services.ai_prompt_loader import invalidate_cache
        invalidate_cache()
        return {"status": "deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200])


# ===========================================================================
# Vector / Semantic Search Endpoints (Sprint 4 S4.4)
# ===========================================================================

_vector_service = None

def _get_vector_service():
    global _vector_service
    if _vector_service is None:
        from ..services.vector_service import VectorService
        _vector_service = VectorService(_supabase)
    return _vector_service


# ── Reembed: persistent state via processing_jobs ────────────────────────────
# Module dicts (_reembed_progress, _reembed_cancel) removed in migration 073/074.
# State now lives in processing_jobs; helper at services/reembed_job_state.py.

def _reembed_state_for(sb):
    """Construct a fresh ReembedJobState bound to the given supabase client."""
    from ..services.reembed_job_state import ReembedJobState
    return ReembedJobState(sb)


def _serialize_reembed_job(job: dict) -> dict:
    """Shape a processing_jobs row into the response contract for the polling and
    SSE endpoints. Designed as a SUPERSET of the legacy ReembedStatus shape so
    existing frontend clients keep working.
    """
    if not job:
        return {"status": "idle"}
    params = job.get("parameters") or {}
    return {
        # legacy fields (kept for frontend compatibility)
        "status": job.get("status"),
        "started_at": job.get("started_at"),
        "completed_at": job.get("completed_at"),
        "error": (job.get("error_summary") or {}).get("sample_errors"),
        # new fields added by the migration to processing_jobs
        "job_id": job.get("id"),
        "client_id": job.get("client_id"),
        "current_stage": job.get("current_stage"),
        "tables": params.get("tables"),
        "limit": params.get("limit"),
        "processed_records": job.get("processed_records"),
        "failed_records": job.get("failed_records"),
        "total_records": job.get("total_records"),
        "error_summary": job.get("error_summary"),
    }


@router.post("/vector/reembed")
async def trigger_reembed(
    background_tasks: BackgroundTasks,
    client_id: Optional[str] = Query(None),
    limit: Optional[int] = Query(None, description="Max records to embed per table (for testing)"),
    tables: Optional[str] = Query(None, description="Comma-separated tables to embed: emails,companies,operations. Default: all."),
    current_user: dict = Depends(require_role("admin")),
):
    """Bootstrap or re-embed entities. Optionally specify which tables.

    Persists job state to processing_jobs. Subscribe to
    GET /ai/vector/reembed/stream/{job_id} for live progress (SSE), or poll
    GET /ai/vector/reembed/status?job_id=... as a fallback.
    """
    if not client_id:
        client_id = current_user.get("client_id")
    if not client_id:
        raise HTTPException(status_code=400, detail="client_id required")

    # Respect this tenant's master AI kill switch — embedding is an AI operation
    settings = get_ai_settings(client_id)
    if not settings.ai_enabled:
        raise HTTPException(status_code=409, detail="AI is disabled via kill switch. Enable AI first.")

    table_list = [t.strip() for t in tables.split(",")] if tables else ["emails", "companies", "operations"]
    triggered_by = current_user.get("user_id") or current_user.get("id") or current_user.get("sub")

    state = _reembed_state_for(_supabase)

    # Single-flight: the partial unique index in migration 074 is the actual
    # enforcement; ActiveJobExists wraps the unique-violation translation.
    from ..services.reembed_job_state import ActiveJobExists
    try:
        job_id = state.create_job(
            client_id=client_id,
            tables=table_list,
            limit=limit,
            triggered_by_user_id=triggered_by,
        )
    except ActiveJobExists as e:
        existing = e.existing_job
        raise HTTPException(
            status_code=409,
            detail={
                "status": "already_running",
                "job_id": existing.get("id"),
                "current_status": existing.get("status"),
                "started_at": existing.get("started_at"),
            },
        )

    async def _run():
        # Worker task. Two invariants must hold across any restructure here:
        #
        #   (1) vs.reembed_all() owns the BulkIndexManager.async_bulk_operation
        #       context manager. Its finally block recreates HNSW indexes. We
        #       MUST NOT short-circuit around it. Letting exceptions propagate
        #       through reembed_all() so the context manager exits cleanly is
        #       what guarantees indexes get recreated.
        #
        #   (2) On any exit path (success, exception, cancel), the job must end
        #       in a terminal status (completed | failed | stopped). Otherwise
        #       single-flight blocks the next reembed indefinitely.
        worker_state = _reembed_state_for(_supabase)

        def _on_progress(stage: str, delta_processed: int = 0, delta_failed: int = 0):
            """Thin adapter so vector_service can report progress without knowing
            anything about processing_jobs. Called from reembed_all at table
            boundaries and from embed_emails_batch after each DB chunk.
            """
            try:
                worker_state.update_progress(
                    job_id,
                    delta_processed=delta_processed,
                    delta_failed=delta_failed,
                    current_stage=stage,
                )
            except Exception as pe:
                # Progress updates must never crash the worker. Log and continue.
                logger.warning(f"[Vector] Progress update failed for {job_id}: {pe}")

        try:
            worker_state.mark_running(job_id)
            _on_progress("starting")

            vs = _get_vector_service()
            result = await vs.reembed_all(
                client_id, limit=limit, tables=table_list,
                cancel_check=lambda: worker_state.check_cancelled(job_id),
                on_progress=_on_progress,
            )
            # Progress counters are incremented incrementally via _on_progress
            # from inside reembed_all / embed_emails_batch. No final delta here.
            if worker_state.check_cancelled(job_id):
                _on_progress("stopped")
                worker_state.mark_stopped(job_id)
                logger.info(f"[Vector] Reembed job {job_id} stopped: {result}")
            else:
                _on_progress("completed")
                worker_state.mark_completed(job_id)
                logger.info(f"[Vector] Reembed job {job_id} completed: {result}")
        except Exception as e:
            logger.error(f"Reembed job {job_id} failed: {e}", exc_info=True)
            try:
                worker_state.mark_failed(job_id, {
                    "type": e.__class__.__name__,
                    "error": str(e)[:500],
                })
            except Exception as inner:
                logger.error(f"Failed to mark job {job_id} failed: {inner}")

    # Detached asyncio task — same pattern as before; survives request lifecycle
    # for the duration of the in-process worker.
    asyncio.create_task(_run())
    return {
        "status": "started",
        "job_id": job_id,
        "client_id": client_id,
        "tables": table_list,
        "limit": limit,
    }


@router.get("/vector/reembed/status")
async def get_reembed_status(
    client_id: Optional[str] = Query(None),
    job_id: Optional[str] = Query(None, description="Specific job to fetch; defaults to latest for the client"),
    current_user: dict = Depends(get_current_user),
):
    """Poll reembed job status. Reads from processing_jobs.

    Backward compatible: if no job_id is provided, returns the latest reembed
    job for the client (matches legacy semantics). Response shape is a
    superset of the legacy ReembedStatus contract.
    """
    state = _reembed_state_for(_supabase)
    if job_id:
        job = state.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
    else:
        if not client_id:
            client_id = current_user.get("client_id")
        if not client_id:
            raise HTTPException(status_code=400, detail="client_id required when job_id is not provided")
        job = state.get_latest_job_for_client(client_id)

    if not job:
        return {"status": "idle"}
    return _serialize_reembed_job(job)


@router.post("/vector/reembed/stop")
async def stop_reembed(
    client_id: Optional[str] = Query(None),
    job_id: Optional[str] = Query(None),
    current_user: dict = Depends(require_role("admin")),
):
    """Request cancellation of a running reembed job.

    Returns immediately. The worker picks up the cancel signal on its next
    check_cancelled poll and exits cleanly, allowing the BulkIndexManager
    finally block to recreate dropped HNSW indexes.
    """
    state = _reembed_state_for(_supabase)
    if job_id:
        job = state.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job not found")
    else:
        if not client_id:
            client_id = current_user.get("client_id")
        if not client_id:
            raise HTTPException(status_code=400, detail="client_id or job_id required")
        job = state.get_active_job_for_client(client_id)
        if not job:
            return {"status": "not_running"}

    state.request_cancel(job["id"])
    return {"status": "cancellation_requested", "job_id": job["id"]}


@router.get("/vector/reembed/stream/{job_id}")
async def stream_reembed(
    job_id: str,
    request: Request,
    current_user: dict = Depends(require_role("admin")),
):
    """SSE stream for live reembed progress. Mirrors the digest streaming
    pattern (ai.py:1410) — queue + generator + disconnect detection.

    Polls processing_jobs at ~750ms; emits an event whenever processed_records,
    status, or current_stage changes. Terminates with a final event when the
    job reaches a terminal status (completed | failed | stopped).
    """
    import json as _json

    state = _reembed_state_for(_supabase)
    initial = state.get_job(job_id)
    if initial is None:
        raise HTTPException(status_code=404, detail="job not found")

    # Authorization: an admin from another client should not be able to
    # subscribe to someone else's job stream. Allow if same client_id, OR if
    # the user is platform-level admin (no client scoping). Match this to the
    # project's existing access pattern if there is a stricter convention.
    user_client = current_user.get("client_id")
    if user_client and initial.get("client_id") and user_client != initial.get("client_id"):
        raise HTTPException(status_code=403, detail="forbidden")

    # 2s matches the digest SSE keepalive convention and is gentle on the
    # connection pool. At ~266K emails with ~10ms reembed batches, polling
    # faster than this doesn't buy meaningful UI responsiveness.
    POLL_INTERVAL_S = 2.0
    TERMINAL = {"completed", "failed", "stopped"}

    async def _generator():
        last_snapshot = None
        # Initial snapshot event so the client gets the current state immediately.
        snap = _serialize_reembed_job(initial)
        yield f"event: snapshot\ndata: {_json.dumps(snap)}\n\n"
        last_snapshot = (
            snap.get("status"),
            snap.get("processed_records"),
            snap.get("current_stage"),
        )

        terminal_status = snap.get("status") if snap.get("status") in TERMINAL else None
        try:
            while terminal_status is None:
                if await request.is_disconnected():
                    # Client gone. The polling task we are IS this generator —
                    # so simply returning ends the stream cleanly. No leaked task.
                    return
                await asyncio.sleep(POLL_INTERVAL_S)

                job = state.get_job(job_id)
                if job is None:
                    yield f"event: error\ndata: {_json.dumps({'detail': 'job disappeared'})}\n\n"
                    return

                snap = _serialize_reembed_job(job)
                key = (snap.get("status"), snap.get("processed_records"), snap.get("current_stage"))

                if key != last_snapshot:
                    yield f"event: progress\ndata: {_json.dumps(snap)}\n\n"
                    last_snapshot = key
                else:
                    # Quiet keepalive every poll where nothing changed —
                    # mirrors the digest endpoint's keepalive convention.
                    yield ": keepalive\n\n"

                if snap.get("status") in TERMINAL:
                    terminal_status = snap.get("status")

            # Emit a final event with the terminal state and close.
            final = state.get_job(job_id) or {}
            yield f"event: {terminal_status}\ndata: {_json.dumps(_serialize_reembed_job(final))}\n\n"
        except asyncio.CancelledError:
            # Server-side cancellation (shutdown, client disconnect surfaced as
            # cancel). Just exit — no leaked work.
            raise

    return StreamingResponse(
        _generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/vector/backfill-search-text")
async def backfill_search_text(
    batch_size: int = Query(default=500, ge=100, le=5000),
    current_user: dict = Depends(require_role("admin")),
):
    """Backfill tsvector search_text on emails in small batches to stay under statement timeout."""
    try:
        # Find emails missing search_text
        batch = _supabase.table("emails").select("id").is_(
            "search_text", "null"
        ).limit(batch_size).execute()
        ids = [r["id"] for r in (batch.data or [])]

        if not ids:
            return {"updated": 0, "batch_size": batch_size, "done": True}

        # Process in small chunks via RPC to stay under Supabase statement timeout
        updated = 0
        chunk_size = 100
        for i in range(0, len(ids), chunk_size):
            chunk = ids[i:i + chunk_size]
            try:
                result = _supabase.rpc("backfill_search_text_by_ids", {
                    "p_ids": chunk,
                }).execute()
                data = result.data
                if isinstance(data, list) and data and isinstance(data[0], dict):
                    updated += data[0].get("updated_count", len(chunk))
                else:
                    updated += len(chunk)
            except Exception as chunk_err:
                logger.warning(f"Backfill chunk {i} failed: {chunk_err}")

        logger.info(f"search_text backfill: {updated}/{len(ids)} rows")
        return {"updated": updated, "batch_size": batch_size, "done": updated == 0}
    except Exception as e:
        logger.error(f"search_text backfill failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/vector/search/emails")
async def search_emails_semantic(
    q: str = Query(..., min_length=3, description="Search query"),
    client_id: Optional[str] = Query(None),
    threshold: float = Query(0.65, ge=0.0, le=1.0),
    limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(get_current_user),
):
    """Semantic search over email intelligence records."""
    if not client_id:
        client_id = current_user.get("client_id")
    try:
        vs = _get_vector_service()
        results = await vs.search_emails(q, client_id, threshold, limit)
        return {"query": q, "results": results, "count": len(results)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.get("/vector/search/companies")
async def search_companies_semantic(
    q: str = Query(..., min_length=3, description="Search query"),
    client_id: Optional[str] = Query(None),
    threshold: float = Query(0.65, ge=0.0, le=1.0),
    limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(get_current_user),
):
    """Semantic search over companies."""
    if not client_id:
        client_id = current_user.get("client_id")
    try:
        vs = _get_vector_service()
        results = await vs.search_companies(q, client_id, threshold, limit)
        return {"query": q, "results": results, "count": len(results)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.get("/vector/search/operations")
async def search_operations_semantic(
    q: str = Query(..., min_length=3, description="Search query"),
    client_id: Optional[str] = Query(None),
    threshold: float = Query(0.65, ge=0.0, le=1.0),
    limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(get_current_user),
):
    """Semantic search over QB operations."""
    if not client_id:
        client_id = current_user.get("client_id")
    try:
        vs = _get_vector_service()
        results = await vs.search_operations(q, client_id, threshold, limit)
        return {"query": q, "results": results, "count": len(results)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.get("/vector/search")
async def search_all_semantic(
    q: str = Query(..., min_length=3, description="Search query"),
    client_id: Optional[str] = Query(None),
    threshold: float = Query(0.65, ge=0.0, le=1.0),
    limit: int = Query(5, ge=1, le=20),
    current_user: dict = Depends(get_current_user),
):
    """Unified semantic search across emails, companies, and operations."""
    if not client_id:
        client_id = current_user.get("client_id")
    try:
        vs = _get_vector_service()

        # Search each table independently — don't fail all if one table has no embeddings
        emails, companies, operations = [], [], []
        for label, search_fn, result_list in [
            ("emails", vs.search_emails, emails),
            ("companies", vs.search_companies, companies),
            ("operations", vs.search_operations, operations),
        ]:
            try:
                res = await search_fn(q, client_id, threshold, limit)
                result_list.extend(res)
            except Exception as table_err:
                logger.warning(f"Vector search failed for {label}: {table_err}")

        return {
            "query": q,
            "emails": emails,
            "companies": companies,
            "operations": operations,
            "total": len(emails) + len(companies) + len(operations),
        }
    except Exception as e:
        logger.error(f"Vector search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.get("/vector/hybrid-search")
async def hybrid_search(
    q: str = Query(..., min_length=3, description="Natural language search query"),
    client_id: Optional[str] = Query(None),
    sources: Optional[str] = Query(None, description="Comma-separated: emails,companies,operations"),
    limit: int = Query(20, ge=1, le=100),
    threshold: float = Query(0.55, ge=0.0, le=1.0),
    current_user: dict = Depends(get_current_user),
):
    """
    Hybrid search with vector + keyword + temporal parsing + RRF fusion.
    Understands natural language dates like "last quarter", "since January".
    """
    if not client_id:
        client_id = current_user.get("client_id")
    try:
        from ..services.hybrid_retriever import HybridRetriever
        retriever = HybridRetriever(_supabase)
        source_list = [s.strip() for s in sources.split(",")] if sources else None
        response = await retriever.retrieve(
            query=q,
            client_id=client_id,
            sources=source_list,
            limit=limit,
            vector_threshold=threshold,
        )
        # Group email results by canonical thread
        email_results = [r for r in response.results if r.source_type == "email"]
        non_email_results = [r for r in response.results if r.source_type != "email"]

        threads: list[dict] = []
        if email_results:
            email_ids = [r.id for r in email_results]
            # Look up canonical_thread_id for matched emails
            try:
                thread_lookup = _supabase.table("emails").select(
                    "id, canonical_thread_id"
                ).in_("id", email_ids[:200]).execute()
                email_thread_map = {
                    r["id"]: r.get("canonical_thread_id")
                    for r in (thread_lookup.data or [])
                }
            except Exception:
                email_thread_map = {}

            # Group by thread — emails without a thread become their own group
            from collections import OrderedDict
            thread_groups: OrderedDict[str, list] = OrderedDict()
            for r in email_results:
                tid = email_thread_map.get(r.id) or r.id  # fallback: email as its own thread
                if tid not in thread_groups:
                    thread_groups[tid] = []
                thread_groups[tid].append(r)

            # For each thread, fetch full thread emails for context
            for thread_id, matched_emails in thread_groups.items():
                best_score = max(r.score for r in matched_emails)
                best_result = max(matched_emails, key=lambda r: r.score)

                # Fetch all emails in this thread (up to 20)
                thread_emails = []
                try:
                    te_result = _supabase.table("emails").select(
                        "id, subject, sender_email, sender_name, sent_date, is_outbound"
                    ).eq("canonical_thread_id", thread_id).order(
                        "sent_date", desc=False
                    ).limit(20).execute()
                    thread_emails = te_result.data or []
                except Exception:
                    # Fallback: just use the matched email
                    thread_emails = [{
                        "id": best_result.id,
                        "subject": best_result.title,
                        "sender_name": best_result.metadata.get("sender_name"),
                        "sender_email": best_result.metadata.get("sender_email"),
                        "sent_date": best_result.metadata.get("sent_date"),
                        "is_outbound": best_result.metadata.get("is_outbound"),
                    }]

                threads.append({
                    "thread_id": thread_id,
                    "subject": best_result.title,
                    "score": round(best_score, 4),
                    "matched_count": len(matched_emails),
                    "total_emails": len(thread_emails),
                    "matched_email_ids": [r.id for r in matched_emails],
                    "emails": [
                        {
                            "id": e.get("id"),
                            "subject": e.get("subject"),
                            "sender_name": e.get("sender_name"),
                            "sender_email": e.get("sender_email"),
                            "sent_date": e.get("sent_date"),
                            "is_outbound": e.get("is_outbound", False),
                            "is_match": e.get("id") in {r.id for r in matched_emails},
                        }
                        for e in thread_emails
                    ],
                    "vector_score": round(best_result.vector_score, 3),
                    "keyword_score": round(best_result.keyword_score, 3),
                    "recency_score": round(best_result.recency_score, 3),
                })

        return {
            "query": response.query,
            "cleaned_query": response.cleaned_query,
            "date_from": response.date_from,
            "date_to": response.date_to,
            "threads": threads,
            "other_results": [
                {
                    "id": r.id,
                    "source_type": r.source_type,
                    "score": round(r.score, 4),
                    "title": r.title,
                    "snippet": r.snippet,
                    "metadata": r.metadata,
                    "vector_score": round(r.vector_score, 3),
                    "keyword_score": round(r.keyword_score, 3),
                    "recency_score": round(r.recency_score, 3),
                }
                for r in non_email_results
            ],
            "total": len(threads) + len(non_email_results),
            "total_vector_hits": response.total_vector_hits,
            "total_keyword_hits": response.total_keyword_hits,
        }
    except Exception as e:
        logger.error(f"Hybrid search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)[:300])


_EMPTY_VECTOR_STATS = {
    "emails": {"total": 0, "embedded": 0},
    "companies": {"total": 0, "embedded": 0},
    "operations": {"total": 0, "embedded": 0},
}


def _vector_stats_cache_key(client_id: str) -> str:
    return f"vector_stats:{client_id}"


def _get_redis_client():
    """Lazy Redis connection matching the project's existing pattern
    (see routers/analytics.py:202). Returns None if Redis is unavailable.
    """
    try:
        import redis
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        return redis.from_url(redis_url, decode_responses=True)
    except Exception as e:
        logger.debug(f"Redis unavailable for vector_stats cache: {e}")
        return None


@router.get("/vector/stats")
async def get_vector_stats(
    client_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """Get embedding coverage stats — how many records have embeddings.

    Backed by a stale-while-revalidate cache because the underlying RPC does
    COUNT(*) queries that can take >8s on large tables under memory pressure
    (see migration 075 for the partial-index fix that addresses the root
    cause; this cache is the application-layer safety net).

    Behavior:
      - Fresh cache hit (<60s old) → return from cache, no DB call
      - Cache miss or expired → try RPC. On success: update cache.
      - RPC timeout/error → return last known value from cache if any,
        else empty zeros. The UI sees recent-but-stale data rather than zeros.
    """
    import json as _json

    if not client_id:
        client_id = current_user.get("client_id")

    logger.info(f"Vector stats requested for client_id={client_id}")

    if not client_id:
        logger.warning("Vector stats: no client_id available")
        return dict(_EMPTY_VECTOR_STATS)

    r = _get_redis_client()
    fresh_key = _vector_stats_cache_key(client_id)
    stale_key = f"{fresh_key}:last_known"

    # 1. Fast path: fresh cached value
    if r is not None:
        try:
            cached = r.get(fresh_key)
            if cached:
                stats = _json.loads(cached)
                logger.debug(f"Vector stats cache hit for {client_id}")
                return stats
        except Exception as e:
            logger.debug(f"Vector stats cache read failed (continuing to RPC): {e}")

    # 2. Call the RPC
    try:
        resp = _supabase.rpc("get_vector_stats", {"p_client_id": client_id}).execute()
        raw = resp.data
        if isinstance(raw, list) and len(raw) > 0:
            raw = raw[0]
        if isinstance(raw, dict) and "emails" in raw:
            stats = raw
        else:
            stats = dict(_EMPTY_VECTOR_STATS)

        # 3. Cache on success — both short-TTL fresh + long-TTL stale fallback
        if r is not None:
            try:
                payload = _json.dumps(stats)
                r.setex(fresh_key, 60, payload)           # 60s fresh window
                r.setex(stale_key, 24 * 3600, payload)    # 24h stale fallback
            except Exception as e:
                logger.debug(f"Vector stats cache write failed (non-fatal): {e}")

        logger.info(f"Vector stats result: {stats}")
        return stats
    except Exception as e:
        logger.warning(f"Vector stats RPC failed: {e}")

        # 4. Fallback: serve last known value if we have one
        if r is not None:
            try:
                cached = r.get(stale_key)
                if cached:
                    stats = _json.loads(cached)
                    stats["_stale"] = True  # advisory flag for UI
                    logger.info(f"Vector stats serving stale cache for {client_id}: {stats}")
                    return stats
            except Exception as inner:
                logger.debug(f"Stale cache read failed: {inner}")

        logger.info("Vector stats result: empty zeros (RPC failed + no cache)")
        return dict(_EMPTY_VECTOR_STATS)


# ============================================================================
# AI CHAT AGENT
# ============================================================================

from pydantic import BaseModel, Field
from typing import List


class AgentChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    client_id: str
    conversation_history: List[dict] = Field(default_factory=list)


class AgentChatResponse(BaseModel):
    response: str
    tools_used: List[dict] = []
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    processing_time_ms: int = 0


@router.post("/agent/chat", response_model=AgentChatResponse)
async def agent_chat(
    data: AgentChatRequest,
    current_user: dict = Depends(get_current_user),
):
    """Conversational AI agent with access to company, contact, email, and operations data."""
    try:
        from ..services.ai_agent_service import agent_chat as _agent_chat

        result = await _agent_chat(
            supabase_client=_supabase,
            client_id=data.client_id,
            message=data.message,
            conversation_history=data.conversation_history,
        )
        return AgentChatResponse(**result)

    except Exception as e:
        logger.error(f"Agent chat failed: {e}")
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/agent/chat/stream")
async def agent_chat_stream(
    data: AgentChatRequest,
    current_user: dict = Depends(get_current_user),
):
    """Streaming AI agent chat via Server-Sent Events.

    Streams token-by-token as the LLM generates, plus tool call events.
    Client consumes via EventSource or fetch + ReadableStream.

    Event types:
      - token: {content: "partial text"}
      - tool_start: {tool: "tool_name", input: "..."}
      - tool_end: {tool: "tool_name", output: "..."}
      - done: {response: "full text", tools_used: [...], model: "...", ...}
      - error: {detail: "..."}
    """
    import json

    async def event_generator():
        try:
            from ..services.ai_agent_service import (
                ALL_TOOLS, AGENT_SYSTEM_PROMPT, PROMPT_KEY_AGENT_CHAT, MAX_HISTORY,
            )
            from ..services.langchain_tools import init_langchain_tools
            from ..services.langchain_core import get_strategic_llm
            from langgraph.prebuilt import create_react_agent
            from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

            t0 = _time.time()

            init_langchain_tools(_supabase)

            from ..services.ai_email_analyzer import _load_client_api_keys
            _load_client_api_keys(_supabase, data.client_id)

            from ..services.ai_prompt_loader import get_prompt
            system_prompt = get_prompt(_supabase, PROMPT_KEY_AGENT_CHAT,
                                       AGENT_SYSTEM_PROMPT, data.client_id)

            messages = []
            history = data.conversation_history[-MAX_HISTORY:] if len(data.conversation_history) > MAX_HISTORY else data.conversation_history
            for entry in history:
                role = entry.get("role", "user")
                content = entry.get("content", "")
                if role == "user":
                    messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    messages.append(AIMessage(content=content))
            messages.append(HumanMessage(content=data.message))

            llm = get_strategic_llm(temperature=0.2)
            agent = create_react_agent(
                model=llm,
                tools=ALL_TOOLS,
                prompt=system_prompt,
            )

            full_response = ""
            tools_used = []

            async for event in agent.astream_events(
                {"messages": messages},
                version="v2",
            ):
                kind = event.get("event", "")
                event_data = event.get("data", {})

                if kind == "on_chat_model_stream":
                    chunk = event_data.get("chunk")
                    if chunk and hasattr(chunk, "content"):
                        content = chunk.content
                        if isinstance(content, str) and content:
                            full_response += content
                            yield f"event: token\ndata: {json.dumps({'content': content})}\n\n"

                elif kind == "on_tool_start":
                    tool_name = event.get("name", "")
                    tool_input = str(event_data.get("input", ""))[:200]
                    tools_used.append(tool_name)
                    yield f"event: tool_start\ndata: {json.dumps({'tool': tool_name, 'input': tool_input})}\n\n"

                elif kind == "on_tool_end":
                    tool_name = event.get("name", "")
                    tool_output = str(event_data.get("output", ""))[:500]
                    yield f"event: tool_end\ndata: {json.dumps({'tool': tool_name, 'output': tool_output})}\n\n"

            elapsed_ms = int((_time.time() - t0) * 1000)
            yield f"event: done\ndata: {json.dumps({'response': full_response, 'tools_used': tools_used, 'processing_time_ms': elapsed_ms})}\n\n"

        except Exception as e:
            logger.error(f"Agent stream failed: {e}")
            yield f"event: error\ndata: {json.dumps({'detail': str(e)[:300]})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
