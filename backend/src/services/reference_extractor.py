"""
Reference number extraction from emails.

Scans email subjects and bodies for QB reference patterns (quote numbers,
job numbers) and validates them against the QB database. Creates
thread_qb_links records for validated matches.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

PATTERNS = {
    "quote": [
        re.compile(r'\b(Q\d{4,6})\b', re.IGNORECASE),
        re.compile(r'\bQuote\s*#?\s*(\d{4,6})\b', re.IGNORECASE),
        re.compile(r'\bQT\s*(\d{4,6})\b', re.IGNORECASE),
    ],
    "job": [
        re.compile(r'\b(J\d{5,7})\b', re.IGNORECASE),
        re.compile(r'\bJob\s*#?\s*(\d{5,7})\b', re.IGNORECASE),
        re.compile(r'\bJB\s*(\d{5,7})\b', re.IGNORECASE),
    ],
}


def extract_references(text: str) -> dict[str, set[str]]:
    """Extract potential QB references from text.

    Returns dict of {link_type: set of reference strings}.
    Quote refs are normalised to Q-prefixed, job refs to J-prefixed.
    """
    refs: dict[str, set[str]] = {"quote": set(), "job": set()}

    for link_type, patterns in PATTERNS.items():
        prefix = "Q" if link_type == "quote" else "J"
        for pat in patterns:
            for match in pat.finditer(text):
                raw = match.group(1)
                digits = re.sub(r'[^0-9]', '', raw)
                refs[link_type].add(f"{prefix}{digits}")

    return {k: v for k, v in refs.items() if v}


def _validate_refs(sb, client_id: str, refs: dict[str, set[str]]) -> dict[str, dict[str, str]]:
    """Validate extracted refs against QB tables.

    Returns {link_type: {ref_string: qb_record_id}} for validated matches.
    """
    validated: dict[str, dict[str, str]] = {}

    quote_refs = refs.get("quote", set())
    if quote_refs:
        resp = sb.table("qb_quotes").select("quote_no, qb_record_id").eq(
            "client_id", client_id
        ).in_("quote_no", list(quote_refs)).execute()
        if resp.data:
            validated["quote"] = {
                r["quote_no"]: str(r["qb_record_id"]) for r in resp.data
            }

    job_refs = refs.get("job", set())
    if job_refs:
        resp = sb.table("qb_jobs").select("job_no, qb_record_id").eq(
            "client_id", client_id
        ).in_("job_no", list(job_refs)).execute()
        if resp.data:
            validated["job"] = {
                r["job_no"]: str(r["qb_record_id"]) for r in resp.data
            }

    return validated


def _upsert_links(
    sb,
    client_id: str,
    thread_id: str,
    validated: dict[str, dict[str, str]],
    source: str = "regex",
    confidence: float = 1.0,
):
    """Create thread_qb_links for validated refs. Skips duplicates."""
    rows = []
    for link_type, ref_map in validated.items():
        for ref_str, record_id in ref_map.items():
            rows.append({
                "client_id": client_id,
                "canonical_thread_id": thread_id,
                "link_type": link_type,
                "qb_record_id": record_id,
                "qb_reference": ref_str,
                "confidence": confidence,
                "source": source,
                "verified": confidence >= 1.0,
            })

    if not rows:
        return 0

    try:
        sb.table("thread_qb_links").upsert(
            rows,
            on_conflict="client_id,canonical_thread_id,link_type,qb_record_id",
        ).execute()
        _sync_qb_link_count(sb, client_id, thread_id)
        return len(rows)
    except Exception as e:
        logger.error(f"Failed to upsert thread_qb_links: {e}")
        return 0


def _sync_qb_link_count(sb, client_id: str, canonical_thread_id: str):
    """Update thread_status.qb_link_count after link changes."""
    try:
        cnt_r = sb.table("thread_qb_links").select(
            "id", count="exact"
        ).eq("client_id", client_id).eq(
            "canonical_thread_id", canonical_thread_id
        ).execute()
        count = cnt_r.count if cnt_r.count is not None else len(cnt_r.data or [])
        sb.table("thread_status").update(
            {"qb_link_count": count}
        ).eq("canonical_thread_id", canonical_thread_id).execute()
    except Exception as e:
        logger.warning(f"Failed to sync qb_link_count for {canonical_thread_id[:16]}: {e}")


def extract_and_link_email(
    sb,
    client_id: str,
    email: dict,
    source: str = "regex",
) -> int:
    """Extract references from a single email and create links.

    Returns the number of links created.
    """
    text_parts = []
    if email.get("subject"):
        text_parts.append(email["subject"])
    if email.get("body_text"):
        text_parts.append(email["body_text"][:5000])
    if email.get("body_html") and not email.get("body_text"):
        text_parts.append(email["body_html"][:5000])

    text = "\n".join(text_parts)
    if not text.strip():
        return 0

    refs = extract_references(text)
    if not refs:
        return 0

    thread_id = email.get("canonical_thread_id") or email.get("thread_id")
    if not thread_id:
        return 0

    validated = _validate_refs(sb, client_id, refs)
    if not validated:
        return 0

    return _upsert_links(sb, client_id, thread_id, validated, source)


def batch_extract_for_client(
    sb,
    client_id: str,
    batch_size: int = 500,
    on_progress: Optional[callable] = None,
) -> dict:
    """Scan all emails for a client and extract references.

    Returns stats dict with total_scanned, total_links, elapsed_s.
    """
    import time
    start = time.time()
    total_scanned = 0
    total_links = 0
    offset = 0

    while True:
        resp = sb.table("emails").select(
            "id, subject, body_text, body_html, canonical_thread_id, thread_id"
        ).eq("client_id", client_id).range(offset, offset + batch_size - 1).execute()

        batch = resp.data or []
        if not batch:
            break

        for email in batch:
            links = extract_and_link_email(sb, client_id, email)
            total_links += links
            total_scanned += 1

        offset += len(batch)

        if on_progress:
            on_progress("extracting_references", len(batch), 0)

        if len(batch) < batch_size:
            break

    return {
        "total_scanned": total_scanned,
        "total_links": total_links,
        "elapsed_s": round(time.time() - start, 1),
    }
