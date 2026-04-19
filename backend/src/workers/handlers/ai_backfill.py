"""
Worker handler for ai_backfill jobs.

Extracts the run_backfill() closure from ai.py into a standalone handler
that runs under the worker's lease/heartbeat supervision.

This is the first job type migrated from BackgroundTasks → worker execution.
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger("worker.ai_backfill")


async def ai_backfill_handler(sb, job: dict, stop_event: asyncio.Event):
    """Backfill AI intent classification for unanalyzed emails.

    Processes all mailboxes specified in job parameters, running
    analyze_all_unanalyzed + bucket engine for each.

    Parameters (from job["parameters"]):
        mailbox_ids: list[str] — mailboxes to process
    """
    from src.services.ai_email_analyzer import AIEmailAnalyzer
    from src.services.ai_action_bucket_engine import ActionBucketEngine

    job_id = job["id"]
    params = job.get("parameters") or {}
    mailbox_ids = params.get("mailbox_ids", [])
    client_id = job.get("client_id")

    if not mailbox_ids:
        raise ValueError("No mailbox_ids provided in job parameters")

    analyzer = AIEmailAnalyzer(sb)
    bucket_engine = ActionBucketEngine(sb)

    total_analyzed = 0
    total_failed = 0

    for idx, mb_id in enumerate(mailbox_ids):
        if stop_event.is_set():
            logger.info(
                f"ai_backfill {job_id}: stopped before mailbox "
                f"{idx + 1}/{len(mailbox_ids)}"
            )
            break

        _update_progress(
            sb, job_id,
            f"Processing mailbox {idx + 1}/{len(mailbox_ids)}",
            processed=total_analyzed,
            failed=total_failed,
        )

        try:
            # Run in thread so the event loop stays free for heartbeat
            result = await asyncio.to_thread(
                analyzer.analyze_all_unanalyzed,
                mailbox_id=mb_id,
                client_id=client_id,
                max_emails=10000,
                date_from="all",
            )
            mb_analyzed = result.get("total_analyzed", 0)
            mb_failed = result.get("total_failed", 0)
            total_analyzed += mb_analyzed
            total_failed += mb_failed

            logger.info(
                f"ai_backfill {job_id}: mailbox {idx + 1}/{len(mailbox_ids)} "
                f"({mb_id}): {mb_analyzed} classified"
            )

            # Run bucket engine after each mailbox
            if mb_analyzed > 0:
                try:
                    await asyncio.to_thread(
                        bucket_engine.process_email_buckets, mb_id
                    )
                except Exception as be:
                    logger.warning(f"Bucket engine failed for {mb_id}: {be}")

        except Exception as e:
            logger.error(f"ai_backfill {job_id}: failed for mailbox {mb_id}: {e}")
            total_failed += 1

    # Write final progress — runner handles status=completed
    _update_progress(
        sb, job_id,
        f"Done: {total_analyzed} classified, {total_failed} failed "
        f"across {len(mailbox_ids)} mailboxes",
        pct=100,
        processed=total_analyzed,
        failed=total_failed,
    )

    logger.info(
        f"ai_backfill {job_id}: completed — {total_analyzed} classified, "
        f"{total_failed} failed across {len(mailbox_ids)} mailboxes"
    )


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
        logger.error(f"ai_backfill progress update failed for {job_id}: {e}")
