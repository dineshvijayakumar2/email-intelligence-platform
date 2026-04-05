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
    current_user: dict = Depends(get_current_user),
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
        import uuid
        job_id = str(uuid.uuid4())
        # Create a processing job for visibility
        try:
            _supabase.table("processing_jobs").insert({
                "id": job_id,
                "mailbox_id": mailbox_id,
                "job_type": "ai_analysis",
                "status": "running",
                "started_at": datetime.utcnow().isoformat(),
                "error_summary": {"progress_pct": 0, "progress_message": "Starting AI email analysis..."},
            }).execute()
        except Exception as job_err:
            logger.warning(f"Could not create processing job: {job_err}")
            job_id = None

        def _update_job(status: str, pct: int, msg: str, error_log_text: str = None):
            if not job_id:
                return
            try:
                summary = {"progress_pct": pct, "progress_message": msg}
                update: dict = {"status": status, "error_summary": summary}
                if error_log_text:
                    update["error_log"] = [{"message": line} for line in error_log_text.split("\n") if line.strip()]
                if status in ("completed", "failed"):
                    update["completed_at"] = datetime.utcnow().isoformat()
                _supabase.table("processing_jobs").update(update).eq("id", job_id).execute()
            except Exception:
                pass

        try:
            result = analyzer.analyze_all_unanalyzed(
                mailbox_id=mailbox_id,
                client_id=client_id,
                max_emails=data.max_emails,
                date_from=data.date_from,
                job_id=job_id,
                date_to=data.date_to,
            )
            logger.info(f"Analysis complete for {mailbox_id}: {result}")

            analyzed = result.get("total_analyzed", 0)
            failed = result.get("total_failed", 0)
            batches = result.get("batches", 0)
            _update_job("running", 60, f"Analysis done: {analyzed} analyzed, {failed} failed in {batches} batches. Running bucket engine...")

            # If all failed, log the errors for troubleshooting
            error_log = None
            if failed > 0:
                try:
                    err_resp = _supabase.table("ai_email_intelligence").select(
                        "email_id,error_message,model_used"
                    ).eq("mailbox_id", mailbox_id).eq(
                        "processing_status", "failed"
                    ).order("processed_at", desc=True).range(0, 19).execute()
                    if err_resp.data:
                        error_log = "\n".join(
                            f"- {r.get('email_id', '?')[:8]}...: {r.get('error_message', 'unknown')}"
                            for r in err_resp.data
                        )
                except Exception:
                    pass

            # Auto-run bucket engine after analysis
            bucket_engine = get_bucket_engine()
            if bucket_engine:
                bucket_result = bucket_engine.process_email_buckets(mailbox_id)
                logger.info(f"Bucket processing complete: {bucket_result}")

            _update_job("running", 80, "Running entity aggregation...")

            # Auto-run entity aggregation
            entity_agg = get_entity_aggregator()
            if entity_agg:
                entity_result = entity_agg.aggregate_entities(mailbox_id, client_id)
                logger.info(f"Entity aggregation complete: {entity_result}")

            summary = f"Done: {analyzed} analyzed, {failed} failed, {batches} batches"
            final_status = "completed" if failed == 0 else ("completed" if analyzed > 0 else "failed")
            _update_job(final_status, 100, summary, error_log)

        except Exception as e:
            logger.error(f"Background analysis failed for {mailbox_id}: {e}")
            _update_job("failed", 0, f"Analysis failed: {str(e)[:300]}", str(e))

    background_tasks.add_task(run_analysis)
    audit_from_user(current_user, "analyze", "mailbox", resource_id=mailbox_id, details={"max_emails": data.max_emails})

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
        from ..services.ai_email_analyzer import _apply_client_model_settings
        _apply_client_model_settings(_supabase, client_id)
    elif mailbox_id:
        # Resolve client_id from mailbox if not provided
        try:
            mb_resp = _supabase.table("mailboxes").select("client_id").eq("id", mailbox_id).limit(1).execute()
            if mb_resp.data and mb_resp.data[0].get("client_id"):
                resolved_client = mb_resp.data[0]["client_id"]
                client_id = resolved_client
                from ..services.ai_email_analyzer import _apply_client_model_settings
                _apply_client_model_settings(_supabase, resolved_client)
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
        # Model preferences
        "cheap_model": settings.cheap_model,
        "strategic_model": settings.strategic_model,
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
        "cheap_model", "strategic_model",
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
        import uuid
        job_id = str(uuid.uuid4())
        started_at = datetime.utcnow().isoformat()
        try:
            _supabase.table("processing_jobs").insert({
                "id": job_id,
                "job_type": "strategic_digest",
                "status": "running",
                "started_at": datetime.utcnow().isoformat(),
                "error_summary": {"progress_pct": 0, "progress_message": "Starting strategic digest generation...",
                                  "client_id": client_id, "period_type": period_type},
            }).execute()
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
        from ..services.ai_email_analyzer import _apply_client_model_settings
        _apply_client_model_settings(_supabase, client_id)
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
            from ..services.ai_email_analyzer import _apply_client_model_settings
            _apply_client_model_settings(_supabase, client_id)
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
            from ..services.ai_email_analyzer import _apply_client_model_settings
            _apply_client_model_settings(_supabase, client_id)
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
            from ..services.ai_email_analyzer import _apply_client_model_settings
            _apply_client_model_settings(_supabase, client_id)
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


@router.get("/api-keys")
async def get_api_keys(
    client_id: Optional[str] = Query(default=None),
    current_user: dict = Depends(require_role('admin')),
):
    """Get API key status. Client-specific → global → env fallback."""
    import os, base64

    def mask(k: str) -> str:
        return k[:4] + "****" + k[-4:] if len(k) > 8 else ("****" if k else "")

    # Load from DB (client → global) then env
    db_anthropic = _get_client_setting('api_key_anthropic', client_id)
    db_google = _get_client_setting('api_key_google', client_id)

    anthropic = ""
    anthropic_source = "none"
    if db_anthropic:
        anthropic = base64.b64decode(db_anthropic).decode()
        anthropic_source = "db"
    elif os.environ.get("ANTHROPIC_API_KEY"):
        anthropic = os.environ["ANTHROPIC_API_KEY"]
        anthropic_source = "env"

    google = ""
    google_source = "none"
    if db_google:
        google = base64.b64decode(db_google).decode()
        google_source = "db"
    elif os.environ.get("GOOGLE_GENAI_API_KEY") or os.environ.get("GEMINI_API_KEY"):
        google = os.environ.get("GOOGLE_GENAI_API_KEY") or os.environ.get("GEMINI_API_KEY") or ""
        google_source = "env"

    db_openai = _get_client_setting('api_key_openai', client_id)
    openai_key = ""
    openai_source = "none"
    if db_openai:
        openai_key = base64.b64decode(db_openai).decode()
        openai_source = "db"
    elif os.environ.get("OPENAI_API_KEY"):
        openai_key = os.environ["OPENAI_API_KEY"]
        openai_source = "env"

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
    """Update default model preferences. Per-client if client_id provided."""
    from ..services.langchain_core import set_default_models
    try:
        set_default_models(cheap=cheap_model, strategic=strategic_model)
        update_ai_settings(cheap_model=cheap_model, strategic_model=strategic_model)
        _upsert_client_setting('ai_cheap_model', cheap_model, client_id)
        _upsert_client_setting('ai_strategic_model', strategic_model, client_id)
        return {"status": "ok", "cheap": cheap_model, "strategic": strategic_model, "client_id": client_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


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
    """Create or update a prompt. Body: {client_id, prompt_key, prompt_text, description?, version?}"""
    prompt_key = data.get("prompt_key")
    prompt_text = data.get("prompt_text")
    client_id = data.get("client_id")
    if not prompt_key or not prompt_text:
        raise HTTPException(status_code=400, detail="prompt_key and prompt_text are required")
    if not client_id:
        raise HTTPException(status_code=400, detail="client_id is required")

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
            "version": data.get("version", "v1.0"),
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


# ── In-memory reembed progress tracking ───────────────────────────────────
_reembed_progress: Dict[str, Dict[str, Any]] = {}
_reembed_cancel: Dict[str, bool] = {}  # client_id -> cancel flag


@router.post("/vector/reembed")
async def trigger_reembed(
    background_tasks: BackgroundTasks,
    client_id: Optional[str] = Query(None),
    limit: Optional[int] = Query(None, description="Max records to embed per table (for testing)"),
    tables: Optional[str] = Query(None, description="Comma-separated tables to embed: emails,companies,operations. Default: all."),
    current_user: dict = Depends(require_role("admin")),
):
    """Bootstrap or re-embed entities. Optionally specify which tables.

    Runs in background. Poll GET /ai/vector/reembed/status for progress.
    Pass ?limit=10 to test with a small batch locally.
    Pass ?tables=emails,companies to skip operations.
    """
    if not client_id:
        client_id = current_user.get("client_id")
    if not client_id:
        raise HTTPException(status_code=400, detail="client_id required")

    if _reembed_progress.get(client_id, {}).get("status") == "running":
        return {"status": "already_running", "progress": _reembed_progress[client_id]}

    table_list = [t.strip() for t in tables.split(",")] if tables else ["emails", "companies", "operations"]

    _reembed_progress[client_id] = {"status": "running", "started_at": _time.time(), "limit": limit, "tables": table_list}
    _reembed_cancel[client_id] = False

    async def _run():
        try:
            vs = _get_vector_service()
            result = await vs.reembed_all(
                client_id, limit=limit, tables=table_list,
                cancel_check=lambda: _reembed_cancel.get(client_id, False),
            )
            status = "stopped" if _reembed_cancel.get(client_id) else "complete"
            _reembed_progress[client_id] = {
                "status": status,
                "result": result,
                "completed_at": _time.time(),
            }
        except Exception as e:
            logger.error(f"Reembed failed for {client_id}: {e}")
            _reembed_progress[client_id] = {
                "status": "error",
                "error": str(e)[:500],
            }

    # Run in a detached asyncio task so it doesn't block BackgroundTasks
    # or compete with HTTP request handling
    asyncio.create_task(_run())
    return {"status": "started", "client_id": client_id, "limit": limit}


@router.get("/vector/reembed/status")
async def get_reembed_status(
    client_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """Poll reembed job status."""
    if not client_id:
        client_id = current_user.get("client_id")
    progress = _reembed_progress.get(client_id)
    if not progress:
        return {"status": "idle"}
    return progress


@router.post("/vector/reembed/stop")
async def stop_reembed(
    client_id: Optional[str] = Query(None),
    current_user: dict = Depends(require_role("admin")),
):
    """Stop a running reembed job. Already-embedded records are kept."""
    if not client_id:
        client_id = current_user.get("client_id")
    if not client_id:
        raise HTTPException(status_code=400, detail="client_id required")

    if _reembed_progress.get(client_id, {}).get("status") != "running":
        return {"status": "not_running"}

    _reembed_cancel[client_id] = True
    logger.info(f"[Vector] Stop requested for reembed job {client_id}")
    return {"status": "stopping"}


@router.post("/vector/backfill-search-text")
async def backfill_search_text(
    batch_size: int = Query(default=10000, ge=1000, le=50000),
    current_user: dict = Depends(require_role("admin")),
):
    """Backfill tsvector search_text on emails in batches. Call repeatedly until returns 0."""
    try:
        result = _supabase.rpc("backfill_search_text", {"p_batch_size": batch_size}).execute()
        # PostgREST returns scalar as the data directly, or wrapped in a list
        data = result.data
        if isinstance(data, list) and len(data) > 0:
            updated = data[0] if isinstance(data[0], int) else 0
        elif isinstance(data, int):
            updated = data
        else:
            updated = 0
            logger.warning(f"Unexpected backfill response type: {type(data)} = {data}")
        logger.info(f"search_text backfill: {updated} rows updated (batch_size={batch_size})")
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


@router.get("/vector/stats")
async def get_vector_stats(
    client_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """Get embedding coverage stats — how many records have embeddings."""
    if not client_id:
        client_id = current_user.get("client_id")

    logger.info(f"Vector stats requested for client_id={client_id}")

    if not client_id:
        logger.warning("Vector stats: no client_id available")
        return {"emails": {"total": 0, "embedded": 0}, "companies": {"total": 0, "embedded": 0}, "operations": {"total": 0, "embedded": 0}}

    stats = {}
    for table, label in [
        ("emails", "emails"),
        ("customer_companies", "companies"),
        ("qb_operations", "operations"),
    ]:
        try:
            total = _supabase.table(table).select(
                "id", count="exact"
            ).eq("client_id", client_id).execute()
            embedded = _supabase.table(table).select(
                "id", count="exact"
            ).eq("client_id", client_id).not_.is_("embedding", "null").execute()
            stats[label] = {
                "total": total.count or 0,
                "embedded": embedded.count or 0,
            }
        except Exception as e:
            logger.warning(f"Vector stats primary query failed for {table}: {e}")
            # embedding column may not exist yet — report total only
            try:
                total = _supabase.table(table).select(
                    "id", count="exact"
                ).eq("client_id", client_id).execute()
                stats[label] = {"total": total.count or 0, "embedded": 0}
            except Exception as e2:
                logger.warning(f"Vector stats fallback also failed for {table}: {e2}")
                stats[label] = {"total": 0, "embedded": 0}

    logger.info(f"Vector stats result: {stats}")
    return stats


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

            from ..services.ai_email_analyzer import _apply_client_model_settings
            _apply_client_model_settings(_supabase, data.client_id)

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
