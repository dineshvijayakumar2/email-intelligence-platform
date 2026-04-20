"""
Worker handler for ai_analysis jobs.

Runs AI classification on unanalyzed emails for a single mailbox,
followed by bucket engine and entity aggregation.
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger("worker.ai_analysis")


async def ai_analysis_handler(sb, job: dict, stop_event: asyncio.Event):
    """Classify unanalyzed emails in a mailbox.

    Parameters (from job["parameters"]):
        max_emails: int — cap on emails to process
        date_from: str | None — earliest date filter
        date_to: str | None — latest date filter
    """
    from src.services.ai_email_analyzer import AIEmailAnalyzer
    from src.services.ai_action_bucket_engine import ActionBucketEngine
    from src.services.ai_entity_aggregator import AIEntityAggregator

    job_id = job["id"]
    mailbox_id = job.get("mailbox_id")
    client_id = job.get("client_id")
    params = job.get("parameters") or {}
    max_emails = params.get("max_emails", 500)
    date_from = params.get("date_from")
    date_to = params.get("date_to")

    if not mailbox_id:
        raise ValueError("ai_analysis job requires mailbox_id")

    analyzer = AIEmailAnalyzer(sb)
    bucket_engine = ActionBucketEngine(sb)
    entity_agg = AIEntityAggregator(sb)

    _update_progress(sb, job_id, "Analyzing emails...", pct=10)

    # Run analysis in thread so heartbeat stays alive
    result = await asyncio.to_thread(
        analyzer.analyze_all_unanalyzed,
        mailbox_id=mailbox_id,
        client_id=client_id,
        max_emails=max_emails,
        date_from=date_from,
        job_id=job_id,
        date_to=date_to,
    )

    analyzed = result.get("total_analyzed", 0)
    failed = result.get("total_failed", 0)
    batches = result.get("batches", 0)

    logger.info(f"ai_analysis {job_id}: {analyzed} analyzed, {failed} failed, {batches} batches")

    if stop_event.is_set():
        return

    # Collect error log if any failures
    error_log = None
    if failed > 0:
        try:
            err_resp = sb.table("ai_email_intelligence").select(
                "email_id,error_message,model_used"
            ).eq("mailbox_id", mailbox_id).eq(
                "processing_status", "failed"
            ).order("processed_at", desc=True).range(0, 19).execute()
            if err_resp.data:
                error_log = [
                    {"message": f"{r.get('email_id', '?')[:8]}...: {r.get('error_message', 'unknown')}"}
                    for r in err_resp.data
                ]
        except Exception as e:
            logger.warning(f"ai_analysis {job_id}: failed to collect error samples: {e}")

    # Bucket engine
    _update_progress(sb, job_id, "Running bucket engine...", pct=60, processed=analyzed, failed=failed)
    if analyzed > 0:
        try:
            await asyncio.to_thread(bucket_engine.process_email_buckets, mailbox_id)
        except Exception as e:
            logger.warning(f"Bucket engine failed for {mailbox_id}: {e}")

    if stop_event.is_set():
        return

    # Entity aggregation
    _update_progress(sb, job_id, "Running entity aggregation...", pct=80)
    try:
        await asyncio.to_thread(entity_agg.aggregate_entities, mailbox_id, client_id)
    except Exception as e:
        logger.warning(f"Entity aggregation failed for {mailbox_id}: {e}")

    if stop_event.is_set():
        return

    # AI-extracted QB reference linking
    if analyzed > 0 and client_id:
        _update_progress(sb, job_id, "Linking AI-extracted QB references...", pct=90)
        try:
            linked = await asyncio.to_thread(
                _link_ai_extracted_refs, sb, client_id, mailbox_id
            )
            if linked:
                logger.info(f"ai_analysis {job_id}: linked {linked} AI-extracted QB refs")
        except Exception as e:
            logger.warning(f"AI ref linking failed for {mailbox_id}: {e}")

    # Final progress — runner handles status=completed
    summary = f"Done: {analyzed} analyzed, {failed} failed, {batches} batches"
    update: dict = {
        "processed_records": analyzed,
        "failed_records": failed,
        "error_summary": {"progress_pct": 100, "progress_message": summary},
    }
    if error_log:
        update["error_log"] = error_log
    try:
        sb.table("processing_jobs").update(update).eq("id", job_id).execute()
    except Exception as e:
        logger.error(f"ai_analysis {job_id}: final summary persist failed: {e}")

    logger.info(f"ai_analysis {job_id}: completed — {summary}")


def _link_ai_extracted_refs(sb, client_id: str, mailbox_id: str) -> int:
    """Validate AI-extracted QB references and write to thread_qb_links.

    Reads recently-completed emails with non-null extracted_references,
    validates each ref against qb_quotes/qb_jobs, and upserts links
    with source='ai' and confidence=0.9.
    """
    import re
    from src.services.reference_extractor import _validate_refs, _upsert_links

    # Fetch emails with AI-extracted refs (completed in this run)
    resp = sb.table("ai_email_intelligence").select(
        "email_id, extracted_references"
    ).eq("mailbox_id", mailbox_id).eq(
        "processing_status", "completed"
    ).not_.is_("extracted_references", "null").execute()

    if not resp.data:
        return 0

    # Build email_id -> thread_id lookup
    email_ids = [r["email_id"] for r in resp.data]
    thread_resp = sb.table("emails").select(
        "id, canonical_thread_id"
    ).in_("id", email_ids).execute()
    thread_map = {
        r["id"]: r.get("canonical_thread_id")
        for r in (thread_resp.data or [])
    }

    total_linked = 0
    for row in resp.data:
        refs_raw = row.get("extracted_references") or []
        if not refs_raw:
            continue

        thread_id = thread_map.get(row["email_id"])
        if not thread_id:
            continue

        # Convert AI output [{type, number}] into {link_type: set(ref_string)}
        # Normalize to Q/J prefix format to match regex extractor and qb_quotes/qb_jobs
        refs: dict[str, set[str]] = {}
        for ref in refs_raw:
            ref_type = ref.get("type")  # "quote" or "job"
            ref_number = ref.get("number")  # e.g. "Q20334"
            if ref_type and ref_number:
                digits = re.sub(r'[^0-9]', '', str(ref_number))
                if not digits:
                    continue
                prefix = "Q" if ref_type == "quote" else "J"
                refs.setdefault(ref_type, set()).add(f"{prefix}{digits}")

        if not refs:
            continue

        validated = _validate_refs(sb, client_id, refs)
        if validated:
            count = _upsert_links(
                sb, client_id, thread_id, validated,
                source="ai", confidence=0.9,
            )
            total_linked += count

    return total_linked


def _update_progress(
    sb, job_id: str, message: str,
    pct: int = None, processed: int = None, failed: int = None,
):
    """Update job progress fields. Non-fatal on failure."""
    try:
        update: dict = {
            "error_summary": {
                "progress_message": message,
                **({"progress_pct": pct} if pct is not None else {}),
            },
        }
        if processed is not None:
            update["processed_records"] = processed
        if failed is not None:
            update["failed_records"] = failed
        sb.table("processing_jobs").update(update).eq("id", job_id).execute()
    except Exception as e:
        logger.error(f"ai_analysis progress update failed for {job_id}: {e}")
