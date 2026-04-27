"""
Worker handler for ai_backfill jobs.

Processes mailboxes concurrently (up to CONCURRENCY slots) to maximise
throughput during bulk backfills. Each slot gets its own AIEmailAnalyzer
instance to avoid shared cursor/state issues.
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger("worker.ai_backfill")

CONCURRENCY = 3
CHUNK = 10_000


async def ai_backfill_handler(sb, job: dict, stop_event: asyncio.Event):
    """Backfill AI intent classification for unanalyzed emails.

    Processes mailboxes concurrently (up to CONCURRENCY at a time).
    Each mailbox gets its own AIEmailAnalyzer to avoid shared state.

    Parameters (from job["parameters"]):
        mailbox_ids: list[str] — mailboxes to process
    """
    job_id = job["id"]
    params = job.get("parameters") or {}
    mailbox_ids = params.get("mailbox_ids", [])
    client_id = job.get("client_id")

    if not mailbox_ids:
        raise ValueError("No mailbox_ids provided in job parameters")

    progress = {"analyzed": 0, "failed": 0, "done_mailboxes": 0}
    total_mailboxes = len(mailbox_ids)
    sem = asyncio.Semaphore(CONCURRENCY)

    async def _process_mailbox(mb_id: str, idx: int):
        from src.services.ai_email_analyzer import AIEmailAnalyzer
        from src.services.ai_action_bucket_engine import ActionBucketEngine

        async with sem:
            if stop_event.is_set():
                return

            if idx > 0:
                await asyncio.sleep(idx * 10)

            analyzer = AIEmailAnalyzer(sb)
            mb_analyzed = 0
            mb_failed = 0

            try:
                while not stop_event.is_set():
                    result = await asyncio.to_thread(
                        analyzer.analyze_all_unanalyzed,
                        mailbox_id=mb_id,
                        client_id=client_id,
                        max_emails=CHUNK,
                        date_from="all",
                    )
                    chunk_ok = result.get("total_analyzed", 0)
                    chunk_fail = result.get("total_failed", 0)
                    mb_analyzed += chunk_ok
                    mb_failed += chunk_fail

                    progress["analyzed"] += chunk_ok
                    progress["failed"] += chunk_fail

                    _update_progress(
                        sb, job_id,
                        f"{CONCURRENCY} concurrent | "
                        f"{progress['analyzed']} classified, "
                        f"{progress['done_mailboxes']}/{total_mailboxes} mailboxes done",
                        processed=progress["analyzed"],
                        failed=progress["failed"],
                    )

                    if chunk_ok + chunk_fail < CHUNK:
                        break

                logger.info(
                    f"ai_backfill {job_id}: mailbox {idx + 1}/{total_mailboxes} "
                    f"({mb_id}): {mb_analyzed} classified"
                )

                if mb_analyzed > 0:
                    try:
                        bucket_engine = ActionBucketEngine(sb)
                        await asyncio.to_thread(
                            bucket_engine.process_email_buckets, mb_id
                        )
                    except Exception as be:
                        logger.warning(f"Bucket engine failed for {mb_id}: {be}")

            except Exception as e:
                logger.error(f"ai_backfill {job_id}: failed for mailbox {mb_id}: {e}")
                progress["failed"] += 1

            progress["done_mailboxes"] += 1

    await asyncio.gather(
        *[_process_mailbox(mb_id, i) for i, mb_id in enumerate(mailbox_ids)]
    )

    _update_progress(
        sb, job_id,
        f"Done: {progress['analyzed']} classified, {progress['failed']} failed "
        f"across {total_mailboxes} mailboxes",
        pct=100,
        processed=progress["analyzed"],
        failed=progress["failed"],
    )

    logger.info(
        f"ai_backfill {job_id}: completed — {progress['analyzed']} classified, "
        f"{progress['failed']} failed across {total_mailboxes} mailboxes"
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
