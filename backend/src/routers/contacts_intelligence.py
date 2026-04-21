"""
Contact Intelligence API Router

Read-only endpoints that surface contact persona metrics, company summaries,
and industry benchmarks from the SQL views created in migration 088.

Auth: user-facing endpoints derive accessible client_ids from mailbox
assignments — never trust frontend-supplied client_id.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..dependencies.auth import get_current_user, get_accessible_mailbox_ids

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/contacts-intelligence", tags=["contacts-intelligence"])

_get_supabase = None


def init_contacts_intelligence_router(supabase_getter):
    """Initialize router with Supabase client getter callable."""
    global _get_supabase
    _get_supabase = supabase_getter


def _get_accessible_client_ids(sb, mailbox_ids: list) -> list:
    """Derive accessible client_ids from the user's mailbox assignments.

    This is the cross-tenant gate: we never trust a client_id from the
    frontend. Instead we look up which clients the user's mailboxes
    belong to.
    """
    if not mailbox_ids:
        return []
    result = sb.table("mailboxes").select("client_id").in_("id", mailbox_ids).execute()
    return list({r["client_id"] for r in (result.data or []) if r.get("client_id")})


# ─────────────────────────────────────────────────────────────────────
# Endpoint 1: GET /contacts-intelligence/{contact_id}/persona
# ─────────────────────────────────────────────────────────────────────

@router.get("/{contact_id}/persona")
async def get_contact_persona(
    contact_id: str,
    current_user: dict = Depends(get_current_user),
    accessible_mailbox_ids: list = Depends(get_accessible_mailbox_ids),
):
    """Return the full persona record for a single contact.

    Reads from the ``contact_persona`` view. Returns 404 if the contact
    does not exist or the user has no access to its client.
    """
    sb = _get_supabase()
    client_ids = _get_accessible_client_ids(sb, accessible_mailbox_ids)
    if not client_ids:
        raise HTTPException(status_code=403, detail="No accessible clients")

    result = (
        sb.table("contact_persona")
        .select("*")
        .eq("contact_id", contact_id)
        .in_("client_id", client_ids)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Contact not found")

    return result.data[0]


# ─────────────────────────────────────────────────────────────────────
# Endpoint 2: GET /contacts-intelligence/company/{company_id}/summary
# ─────────────────────────────────────────────────────────────────────

@router.get("/company/{company_id}/summary")
async def get_company_contact_summary(
    company_id: str,
    current_user: dict = Depends(get_current_user),
    accessible_mailbox_ids: list = Depends(get_accessible_mailbox_ids),
):
    """Return the rolled-up contact summary for a company.

    Reads from the ``company_contact_summary`` view.
    """
    sb = _get_supabase()
    client_ids = _get_accessible_client_ids(sb, accessible_mailbox_ids)
    if not client_ids:
        raise HTTPException(status_code=403, detail="No accessible clients")

    result = (
        sb.table("company_contact_summary")
        .select("*")
        .eq("company_id", company_id)
        .in_("client_id", client_ids)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Company not found")

    return result.data[0]


# ─────────────────────────────────────────────────────────────────────
# Endpoint 3: GET /contacts-intelligence/company/{company_id}/contacts
# ─────────────────────────────────────────────────────────────────────

@router.get("/company/{company_id}/contacts")
async def get_company_contacts(
    company_id: str,
    current_user: dict = Depends(get_current_user),
    accessible_mailbox_ids: list = Depends(get_accessible_mailbox_ids),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    sort_by: Optional[str] = Query(default="engagement_score", pattern="^(engagement_score|quote_count|email_total|name|strike_rate)$"),
    sort_order: Optional[str] = Query(default="desc", pattern="^(asc|desc)$"),
):
    """Return paginated list of contacts for a company with persona data.

    Reads from the ``contact_persona`` view filtered by company_id.
    Supports pagination (limit/offset) and sorting.
    """
    sb = _get_supabase()
    client_ids = _get_accessible_client_ids(sb, accessible_mailbox_ids)
    if not client_ids:
        raise HTTPException(status_code=403, detail="No accessible clients")

    # Total count
    count_result = (
        sb.table("contact_persona")
        .select("contact_id", count="exact")
        .eq("company_id", company_id)
        .in_("client_id", client_ids)
        .execute()
    )
    total = count_result.count or 0

    # Paginated data
    query = (
        sb.table("contact_persona")
        .select("*")
        .eq("company_id", company_id)
        .in_("client_id", client_ids)
    )

    desc = sort_order == "desc"
    query = query.order(sort_by, desc=desc)
    query = query.range(offset, offset + limit - 1)

    result = query.execute()

    return {
        "contacts": result.data or [],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# ─────────────────────────────────────────────────────────────────────
# Endpoint 4: GET /contacts-intelligence/industry/{industry}/benchmarks
# ─────────────────────────────────────────────────────────────────────

@router.get("/industry/{industry}/benchmarks")
async def get_industry_benchmarks(
    industry: str,
    current_user: dict = Depends(get_current_user),
    accessible_mailbox_ids: list = Depends(get_accessible_mailbox_ids),
):
    """Return industry benchmarks for comparison.

    Reads from the ``industry_benchmarks`` view. Scoped to the user's
    accessible clients.
    """
    sb = _get_supabase()
    client_ids = _get_accessible_client_ids(sb, accessible_mailbox_ids)
    if not client_ids:
        raise HTTPException(status_code=403, detail="No accessible clients")

    result = (
        sb.table("industry_benchmarks")
        .select("*")
        .eq("industry", industry)
        .in_("client_id", client_ids)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Industry not found or insufficient data")

    return result.data[0]


# ─────────────────────────────────────────────────────────────────────
# Endpoint 5: GET /contacts-intelligence/industries
# List all industries with benchmarks (for dropdown / comparison picker)
# ─────────────────────────────────────────────────────────────────────

@router.get("/industries")
async def list_industry_benchmarks(
    current_user: dict = Depends(get_current_user),
    accessible_mailbox_ids: list = Depends(get_accessible_mailbox_ids),
):
    """Return all industry benchmarks the user has access to.

    Useful for populating an industry picker or comparison table.
    """
    sb = _get_supabase()
    client_ids = _get_accessible_client_ids(sb, accessible_mailbox_ids)
    if not client_ids:
        return []

    result = (
        sb.table("industry_benchmarks")
        .select("*")
        .in_("client_id", client_ids)
        .order("contact_count", desc=True)
        .execute()
    )

    return result.data or []


# ─────────────────────────────────────────────────────────────────────
# Endpoint 6: GET /contacts-intelligence/{contact_id}/deal-activity
# ─────────────────────────────────────────────────────────────────────

@router.get("/{contact_id}/deal-activity")
async def get_contact_deal_activity(
    contact_id: str,
    current_user: dict = Depends(get_current_user),
    accessible_mailbox_ids: list = Depends(get_accessible_mailbox_ids),
):
    """Return deal activity for a contact: thread funnel, quote pipeline,
    job outcomes — derived from thread_qb_links.

    Also returns the 5 most recent individual links for display.
    """
    sb = _get_supabase()
    client_ids = _get_accessible_client_ids(sb, accessible_mailbox_ids)
    if not client_ids:
        raise HTTPException(status_code=403, detail="No accessible clients")

    # Aggregate from the view
    result = (
        sb.table("contact_deal_activity")
        .select("*")
        .eq("contact_id", contact_id)
        .in_("client_id", client_ids)
        .execute()
    )

    summary = result.data[0] if result.data else {
        "contact_id": contact_id,
        "total_threads": 0,
        "linked_threads": 0,
        "linked_quotes": 0,
        "converted_quotes": 0,
        "open_quotes": 0,
        "open_pipeline_value": 0,
        "converted_value": 0,
        "linked_jobs": 0,
        "linked_job_revenue": 0,
        "linked_margin": 0,
    }

    # Recent individual links: last 5 thread_qb_links for this contact's threads
    recent_links: list[dict] = []
    try:
        # Get this contact's canonical_thread_ids from thread_status
        threads_resp = (
            sb.table("thread_status")
            .select("canonical_thread_id")
            .eq("customer_contact_id", contact_id)
            .not_.is_("canonical_thread_id", "null")
            .limit(200)
            .execute()
        )
        thread_ids = [
            str(t["canonical_thread_id"])
            for t in (threads_resp.data or [])
            if t.get("canonical_thread_id")
        ]
        if thread_ids:
            links_resp = (
                sb.table("thread_qb_links")
                .select("id, canonical_thread_id, link_type, qb_reference, confidence, source, verified, created_at")
                .in_("canonical_thread_id", thread_ids[:50])
                .in_("client_id", client_ids)
                .order("created_at", desc=True)
                .limit(5)
                .execute()
            )
            recent_links = links_resp.data or []
    except Exception as e:
        logger.error(f"Failed to fetch recent links for contact {contact_id}: {e}")

    summary["recent_links"] = recent_links
    return summary
