"""
Journey API — track emails/threads through to QB quotes, jobs, operations,
invoices, and status transitions.

GET /journey/threads/{thread_id}  — thread journey with linked QB records
GET /journey/jobs/{job_no}        — job journey with linked threads
GET /journey/companies/{id}/timeline — all journeys for a company
POST /journey/links               — manually link a thread to a QB record
DELETE /journey/links/{link_id}   — remove a manual link
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..dependencies.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/journey", tags=["journey"])

_supabase = None


def init_journey_router(supabase_client):
    global _supabase
    _supabase = supabase_client


def _sync_qb_link_count(client_id: str, canonical_thread_id: str):
    """Update thread_status.qb_link_count after link create/delete."""
    try:
        cnt_r = _supabase.table("thread_qb_links").select(
            "id", count="exact"
        ).eq("client_id", client_id).eq(
            "canonical_thread_id", canonical_thread_id
        ).execute()
        count = cnt_r.count if cnt_r.count is not None else len(cnt_r.data or [])
        _supabase.table("thread_status").update(
            {"qb_link_count": count}
        ).eq("canonical_thread_id", canonical_thread_id).execute()
    except Exception as e:
        logger.warning(f"Failed to sync qb_link_count for thread {canonical_thread_id[:16]}: {e}")


@router.get("/threads/{thread_id}")
async def get_thread_journey(
    thread_id: str,
    client_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    """Get the full journey for a thread: emails + linked quotes + jobs + ops + invoices."""
    links = _supabase.table("thread_qb_links").select("*").eq(
        "client_id", client_id
    ).eq("canonical_thread_id", thread_id).order("created_at").execute()

    link_data = links.data or []

    # Deduplicate links by (qb_reference, link_type): keep verified > unverified,
    # manual > ai > regex, newest first.
    _SOURCE_RANK = {"manual": 3, "ai": 2, "regex": 1}
    seen: dict[tuple[str, str], dict] = {}
    for lnk in link_data:
        key = (lnk.get("qb_reference") or lnk["qb_record_id"], lnk["link_type"])
        existing = seen.get(key)
        if existing is None:
            seen[key] = lnk
        else:
            new_rank = (lnk.get("verified", False), _SOURCE_RANK.get(lnk.get("source", ""), 0))
            old_rank = (existing.get("verified", False), _SOURCE_RANK.get(existing.get("source", ""), 0))
            if new_rank > old_rank:
                seen[key] = lnk
    link_data = list(seen.values())

    quote_refs = [l for l in link_data if l["link_type"] == "quote"]
    job_refs = [l for l in link_data if l["link_type"] == "job"]

    quotes = []
    if quote_refs:
        qb_ids = [l["qb_record_id"] for l in quote_refs]
        resp = _supabase.table("qb_quotes").select("*").eq(
            "client_id", client_id
        ).in_("qb_record_id", qb_ids).execute()
        quotes = resp.data or []

    jobs = []
    job_nos = set()
    if job_refs:
        qb_ids = [l["qb_record_id"] for l in job_refs]
        resp = _supabase.table("qb_jobs").select("*").eq(
            "client_id", client_id
        ).in_("qb_record_id", qb_ids).execute()
        jobs = resp.data or []
        job_nos.update(j["job_no"] for j in jobs if j.get("job_no"))

    for q in quotes:
        if q.get("job_no"):
            job_nos.add(q["job_no"])

    operations = []
    sales_lines = []
    status_log = []

    if job_nos:
        jn_list = list(job_nos)
        ops = _supabase.table("qb_operations").select("*").eq(
            "client_id", client_id
        ).in_("job_no", jn_list).execute()
        operations = ops.data or []

        sli = _supabase.table("qb_sales_line_items").select("*").eq(
            "client_id", client_id
        ).in_("job_no", jn_list).execute()
        sales_lines = sli.data or []

        try:
            sl = _supabase.table("qb_job_status_log").select("*").eq(
                "client_id", client_id
            ).in_("job_no", jn_list).order("changed_at").execute()
            status_log = sl.data or []
        except Exception:
            pass

    emails = _supabase.table("emails").select(
        "id, subject, sender_email, sender_name, sent_date, canonical_thread_id"
    ).eq(
        "canonical_thread_id", thread_id
    ).order("sent_date").execute()

    return {
        "thread_id": thread_id,
        "emails": emails.data or [],
        "links": link_data,
        "quotes": quotes,
        "jobs": jobs,
        "operations": operations,
        "sales_line_items": sales_lines,
        "status_log": status_log,
    }


@router.get("/jobs/{job_no}")
async def get_job_journey(
    job_no: str,
    client_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    """Get the journey for a job: linked threads + quote + operations + invoices + status."""
    job_resp = _supabase.table("qb_jobs").select("*").eq(
        "client_id", client_id
    ).eq("job_no", job_no).execute()
    job = (job_resp.data or [None])[0]

    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_no} not found")

    links = _supabase.table("thread_qb_links").select("*").eq(
        "client_id", client_id
    ).eq("link_type", "job").eq("qb_record_id", str(job["qb_record_id"])).execute()
    link_data = links.data or []

    quote_links = _supabase.table("thread_qb_links").select("*").eq(
        "client_id", client_id
    ).eq("link_type", "quote").execute()
    for ql in (quote_links.data or []):
        q_resp = _supabase.table("qb_quotes").select("job_no").eq(
            "qb_record_id", ql["qb_record_id"]
        ).limit(1).execute()
        if q_resp.data and q_resp.data[0].get("job_no") == job_no:
            link_data.append(ql)

    thread_ids = list({l["canonical_thread_id"] for l in link_data})

    emails = []
    if thread_ids:
        for tid in thread_ids[:10]:
            e_resp = _supabase.table("emails").select(
                "id, subject, sender_email, sender_name, date_sent, canonical_thread_id"
            ).eq("client_id", client_id).eq(
                "canonical_thread_id", tid
            ).order("date_sent").execute()
            emails.extend(e_resp.data or [])

    quote = _supabase.table("qb_quotes").select("*").eq(
        "client_id", client_id
    ).eq("job_no", job_no).execute()

    operations = _supabase.table("qb_operations").select("*").eq(
        "client_id", client_id
    ).eq("job_no", job_no).execute()

    sales_lines = _supabase.table("qb_sales_line_items").select("*").eq(
        "client_id", client_id
    ).eq("job_no", job_no).execute()

    status_log = []
    try:
        sl = _supabase.table("qb_job_status_log").select("*").eq(
            "client_id", client_id
        ).eq("job_no", job_no).order("changed_at").execute()
        status_log = sl.data or []
    except Exception:
        pass

    return {
        "job": job,
        "links": link_data,
        "emails": emails,
        "quotes": quote.data or [],
        "operations": operations.data or [],
        "sales_line_items": sales_lines.data or [],
        "status_log": status_log,
    }


@router.get("/companies/{company_id}/timeline")
async def get_company_timeline(
    company_id: str,
    client_id: str = Query(...),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    """Get all journeys for a company, sorted by most recent activity."""
    threads = _supabase.table("emails").select(
        "canonical_thread_id"
    ).eq("client_id", client_id).eq(
        "company_id", company_id
    ).not_.is_("canonical_thread_id", "null").execute()

    thread_ids = list({e["canonical_thread_id"] for e in (threads.data or [])})
    if not thread_ids:
        return {"company_id": company_id, "journeys": []}

    all_links = []
    for batch_start in range(0, len(thread_ids), 50):
        batch = thread_ids[batch_start:batch_start + 50]
        resp = _supabase.table("thread_qb_links").select("*").eq(
            "client_id", client_id
        ).in_("canonical_thread_id", batch).execute()
        all_links.extend(resp.data or [])

    linked_threads = {l["canonical_thread_id"] for l in all_links}
    journeys = []
    for tid in list(linked_threads)[:limit]:
        tid_links = [l for l in all_links if l["canonical_thread_id"] == tid]
        journeys.append({
            "thread_id": tid,
            "links": tid_links,
            "qb_references": [l.get("qb_reference") for l in tid_links if l.get("qb_reference")],
        })

    return {
        "company_id": company_id,
        "total_threads": len(thread_ids),
        "linked_threads": len(linked_threads),
        "journeys": journeys,
    }


class ManualLinkRequest(BaseModel):
    client_id: str
    canonical_thread_id: str
    link_type: str
    qb_reference: str


@router.post("/links")
async def create_manual_link(
    req: ManualLinkRequest,
    current_user: dict = Depends(get_current_user),
):
    """Manually link a thread to a QB record."""
    if req.link_type == "quote":
        resp = _supabase.table("qb_quotes").select("qb_record_id, quote_no").eq(
            "client_id", req.client_id
        ).eq("quote_no", req.qb_reference).limit(1).execute()
    elif req.link_type == "job":
        resp = _supabase.table("qb_jobs").select("qb_record_id, job_no").eq(
            "client_id", req.client_id
        ).eq("job_no", req.qb_reference).limit(1).execute()
    else:
        raise HTTPException(status_code=400, detail=f"Invalid link_type: {req.link_type}")

    if not resp.data:
        raise HTTPException(status_code=404, detail=f"{req.link_type} {req.qb_reference} not found")

    record = resp.data[0]
    row = {
        "client_id": req.client_id,
        "canonical_thread_id": req.canonical_thread_id,
        "link_type": req.link_type,
        "qb_record_id": str(record["qb_record_id"]),
        "qb_reference": req.qb_reference,
        "confidence": 1.0,
        "source": "manual",
        "verified": True,
    }

    try:
        result = _supabase.table("thread_qb_links").upsert(
            row,
            on_conflict="client_id,canonical_thread_id,link_type,qb_record_id",
        ).execute()
        _sync_qb_link_count(req.client_id, req.canonical_thread_id)
        return {"status": "created", "link": result.data[0] if result.data else row}
    except Exception as e:
        logger.error(f"Failed to create manual link: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/links/{link_id}")
async def delete_link(
    link_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete a thread-QB link."""
    try:
        link_row = _supabase.table("thread_qb_links").select(
            "client_id, canonical_thread_id"
        ).eq("id", link_id).limit(1).execute()
        _supabase.table("thread_qb_links").delete().eq("id", link_id).execute()
        if link_row.data:
            _sync_qb_link_count(link_row.data[0]["client_id"], link_row.data[0]["canonical_thread_id"])
        return {"status": "deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
