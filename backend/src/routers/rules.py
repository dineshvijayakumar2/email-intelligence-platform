"""
Email Rules Router — Unified rules view + cross-AM comparison

Endpoints for viewing, importing, and analyzing email rules across
Gmail filters and Outlook inbox rules. Admin/manager only.

Router prefix: /rules, tags: ["email-rules"]
"""

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks, Depends
from typing import Optional
import logging

from ..dependencies.auth import get_current_user, get_accessible_mailbox_ids

from ..models.rules import (
    UnifiedRule, RulesListResponse,
    RulesAnalyticsResponse, MailboxRulesMetrics,
    RulesInsightsResponse, RulesInsight,
    RulesFullAnalyticsResponse,
)
from ..services.email_rules_service import get_email_rules_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rules", tags=["email-rules"])

_supabase = None


def init_rules_router(supabase_client):
    """Initialize the rules router with Supabase client."""
    global _supabase
    _supabase = supabase_client

    from ..services.email_rules_service import init_email_rules_service
    init_email_rules_service(supabase_client)
    logger.info("Rules router and service initialized")


def _validate_mailbox_access(mailbox_id: str, accessible_ids: list):
    """Raise 403 if user doesn't have access to this mailbox."""
    if mailbox_id not in accessible_ids:
        raise HTTPException(status_code=403, detail="You don't have access to this mailbox")


def _validate_client_access(client_id: str, accessible_ids: list, user: dict = None):
    """Raise 403 if user has no accessible mailboxes for this client."""
    # Admin bypass — admins can access all clients
    if user and 'admin' in (user.get('roles') or []):
        return
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


# ============================================================================
# ANALYTICS ENDPOINT (must be before /{mailbox_id} to avoid route collision)
# ============================================================================

@router.get("/analytics/{client_id}", response_model=RulesAnalyticsResponse)
async def get_rules_analytics(
    client_id: str,
    current_user: dict = Depends(get_current_user),
    accessible_ids: list = Depends(get_accessible_mailbox_ids),
):
    """
    Get cross-AM rules comparison analytics.

    Returns per-mailbox metrics: rule counts, signal distribution,
    covered domains, forwarding rules, etc.
    """
    _validate_client_access(client_id, accessible_ids, current_user)
    service = get_email_rules_service()
    if not service:
        raise HTTPException(status_code=503, detail="Rules service not initialized")

    try:
        analytics = service.get_rules_analytics(client_id)
        return RulesAnalyticsResponse(
            mailboxes=[MailboxRulesMetrics(**m) for m in analytics["mailboxes"]],
            total_mailboxes=analytics["total_mailboxes"],
            total_rules=analytics["total_rules"],
            avg_rules_per_mailbox=analytics["avg_rules_per_mailbox"],
            mailboxes_with_no_rules=analytics["mailboxes_with_no_rules"],
        )
    except Exception as e:
        logger.error(f"Failed to get rules analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e)[:200])


# ============================================================================
# FULL ANALYTICS ENDPOINT — combined analytics + insights + rules (1 call)
# ============================================================================

@router.get("/analytics/{client_id}/full", response_model=RulesFullAnalyticsResponse)
async def get_rules_full_analytics(
    client_id: str,
    current_user: dict = Depends(get_current_user),
    accessible_ids: list = Depends(get_accessible_mailbox_ids),
):
    """
    Combined endpoint: analytics + insights + all rules in one response.

    Optimized single-pass query (3 DB queries) that replaces 3 separate
    API calls + N per-mailbox rule fetches.
    """
    _validate_client_access(client_id, accessible_ids, current_user)
    service = get_email_rules_service()
    if not service:
        raise HTTPException(status_code=503, detail="Rules service not initialized")

    try:
        result = service.get_full_analytics(client_id)
        return RulesFullAnalyticsResponse(
            analytics=RulesAnalyticsResponse(
                mailboxes=[MailboxRulesMetrics(**m) for m in result["analytics"]["mailboxes"]],
                total_mailboxes=result["analytics"]["total_mailboxes"],
                total_rules=result["analytics"]["total_rules"],
                avg_rules_per_mailbox=result["analytics"]["avg_rules_per_mailbox"],
                mailboxes_with_no_rules=result["analytics"]["mailboxes_with_no_rules"],
            ),
            insights=RulesInsightsResponse(
                insights=[RulesInsight(**i) for i in result["insights"]],
                total=len(result["insights"]),
            ),
            rules=[UnifiedRule(**r) for r in result["rules"]],
            total_rules=len(result["rules"]),
            last_rules_import_at=result.get("last_rules_import_at"),
        )
    except Exception as e:
        logger.error(f"Failed to get full rules analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e)[:200])


# ============================================================================
# INSIGHTS ENDPOINT (must be before /{mailbox_id} to avoid route collision)
# ============================================================================

@router.get("/analytics/{client_id}/insights", response_model=RulesInsightsResponse)
async def get_rules_insights(
    client_id: str,
    current_user: dict = Depends(get_current_user),
    accessible_ids: list = Depends(get_accessible_mailbox_ids),
):
    """
    Get derived improvement insights from cross-AM rules comparison.

    Returns actionable recommendations: missing escalation rules,
    heavy mark-as-read usage, partial domain coverage, best practices.
    """
    _validate_client_access(client_id, accessible_ids, current_user)
    service = get_email_rules_service()
    if not service:
        raise HTTPException(status_code=503, detail="Rules service not initialized")

    try:
        insights = service.get_rules_insights(client_id)
        return RulesInsightsResponse(
            insights=[RulesInsight(**i) for i in insights],
            total=len(insights),
        )
    except Exception as e:
        logger.error(f"Failed to get rules insights: {e}")
        raise HTTPException(status_code=500, detail=str(e)[:200])


# ============================================================================
# RULES LIST ENDPOINT
# ============================================================================

@router.get("/{mailbox_id}", response_model=RulesListResponse)
async def get_rules(
    mailbox_id: str,
    accessible_ids: list = Depends(get_accessible_mailbox_ids),
):
    """
    Get unified email rules for a mailbox.

    Normalizes Gmail filters and Outlook rules into a common format.
    """
    _validate_mailbox_access(mailbox_id, accessible_ids)
    service = get_email_rules_service()
    if not service:
        raise HTTPException(status_code=503, detail="Rules service not initialized")

    try:
        rules = service.get_unified_rules(mailbox_id)
        mailbox_email = rules[0]["mailbox_email"] if rules else ""
        source_type = rules[0]["source_type"] if rules else ""

        return RulesListResponse(
            items=[UnifiedRule(**r) for r in rules],
            total=len(rules),
            mailbox_email=mailbox_email,
            source_type=source_type,
        )
    except Exception as e:
        logger.error(f"Failed to get rules for mailbox {mailbox_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e)[:200])


# ============================================================================
# IMPORT ENDPOINT
# ============================================================================

@router.post("/{mailbox_id}/import")
async def import_rules(
    mailbox_id: str,
    background_tasks: BackgroundTasks,
    accessible_ids: list = Depends(get_accessible_mailbox_ids),
):
    """
    Import email rules from the mail server for a mailbox.

    Auto-detects Gmail vs Outlook and calls the appropriate sync service.
    """
    _validate_mailbox_access(mailbox_id, accessible_ids)
    try:
        # Get mailbox info and detect LIVE connection type
        from ..services.email_rules_service import get_email_rules_service as _get_svc
        from ..services.email_rules_service import EmailRulesService

        resp = _supabase.table("mailboxes").select(
            "id,mailbox_type,connection_config,user_id"
        ).eq("id", mailbox_id).execute()

        if not resp.data:
            raise HTTPException(status_code=404, detail=f"Mailbox {mailbox_id} not found")

        mailbox = resp.data[0]
        config = mailbox.get("connection_config") or {}
        live_type = EmailRulesService.get_live_connection_type(mailbox)

        if live_type == "gmail":
            # Import Gmail filters
            from ..services.gmail_sync_service import get_gmail_sync_service
            sync_service = get_gmail_sync_service()
            if not sync_service:
                raise HTTPException(status_code=503, detail="Gmail sync service not available")

            user_id = config.get("gmail_user_id") or mailbox.get("user_id", "")
            if not user_id:
                raise HTTPException(status_code=400, detail="No user_id found for Gmail mailbox")

            try:
                filters = await sync_service.import_filters(
                    user_id,
                    access_token=config.get("gmail_access_token"),
                    refresh_token=config.get("gmail_refresh_token"),
                    mailbox_id=mailbox_id,
                )
            except (ValueError, ConnectionError) as e:
                logger.warning(f"Gmail import skipped for mailbox {mailbox_id}: {e}")
                return {"status": "skipped", "source": "gmail", "imported_count": 0, "reason": str(e)}

            return {
                "status": "success",
                "source": "gmail",
                "imported_count": len(filters),
            }

        elif live_type == "outlook":
            # Import Outlook rules
            from ..services.outlook_sync_service import get_outlook_sync_service
            sync_service = get_outlook_sync_service()
            if not sync_service:
                raise HTTPException(status_code=503, detail="Outlook sync service not available")

            try:
                rules = await sync_service.import_rules(mailbox_id=mailbox_id)
            except (ValueError, ConnectionError) as e:
                logger.warning(f"Outlook import skipped for mailbox {mailbox_id}: {e}")
                return {"status": "skipped", "source": "outlook", "imported_count": 0, "reason": str(e)}

            return {
                "status": "success",
                "source": "outlook",
                "imported_count": len(rules),
            }

        else:
            return {"status": "skipped", "source": "none", "imported_count": 0,
                    "reason": "No LIVE email connection found"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to import rules for mailbox {mailbox_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e)[:200])
