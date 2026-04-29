"""
Worker handler for ai_backfill jobs.

Processes mailboxes concurrently (up to CONCURRENCY slots) to maximise
throughput during bulk backfills. Large mailboxes get multiple slots
since each AIEmailAnalyzer marks emails as 'processing' before the LLM
call, preventing duplicate work after the staggered start window.
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger("worker.ai_backfill")

CONCURRENCY = 5
CHUNK = 10_000
SLOTS_PER_MAILBOX = 2
STAGGER_SECONDS = 15


async def ai_backfill_handler(sb, job: dict, stop_event: asyncio.Event):
    """Backfill AI intent classification for unanalyzed emails.

    Each mailbox gets SLOTS_PER_MAILBOX concurrent analyzer instances.
    Staggered starts prevent Supabase connection exhaustion.

    Parameters (from job["parameters"]):
        mailbox_ids: list[str] — mailboxes to process
    """
    job_id = job["id"]
    params = job.get("parameters") or {}
    mailbox_ids = params.get("mailbox_ids", [])
    client_id = job.get("client_id")

    if not mailbox_ids:
        raise ValueError("No mailbox_ids provided in job parameters")

    slots: list[tuple[str, int]] = []
    for mb_id in mailbox_ids:
        for s in range(SLOTS_PER_MAILBOX):
            slots.append((mb_id, s))

    progress = {"analyzed": 0, "failed": 0, "done_slots": 0}
    total_slots = len(slots)
    sem = asyncio.Semaphore(CONCURRENCY)

    async def _process_slot(mb_id: str, slot_idx: int, global_idx: int):
        from src.services.ai_email_analyzer import AIEmailAnalyzer
        from src.services.ai_action_bucket_engine import ActionBucketEngine

        async with sem:
            if stop_event.is_set():
                return

            if global_idx > 0:
                await asyncio.sleep(global_idx * STAGGER_SECONDS)

            slot_analyzed = 0
            slot_failed = 0
            max_retries = 3

            for attempt in range(max_retries):
                try:
                    analyzer = AIEmailAnalyzer(sb)
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
                        slot_analyzed += chunk_ok
                        slot_failed += chunk_fail

                        progress["analyzed"] += chunk_ok
                        progress["failed"] += chunk_fail

                        _update_progress(
                            sb, job_id,
                            f"{CONCURRENCY} slots | "
                            f"{progress['analyzed']} classified, "
                            f"{progress['done_slots']}/{total_slots} slots done",
                            processed=progress["analyzed"],
                            failed=progress["failed"],
                        )

                        if chunk_ok + chunk_fail < CHUNK:
                            break

                    logger.info(
                        f"ai_backfill {job_id}: slot {global_idx + 1}/{total_slots} "
                        f"({mb_id} #{slot_idx}): {slot_analyzed} classified"
                    )

                    if slot_analyzed > 0 and slot_idx == 0:
                        try:
                            bucket_engine = ActionBucketEngine(sb)
                            await asyncio.to_thread(
                                bucket_engine.process_email_buckets, mb_id
                            )
                        except Exception as be:
                            logger.warning(f"Bucket engine failed for {mb_id}: {be}")

                    break

                except Exception as e:
                    if attempt < max_retries - 1:
                        delay = 15 * (attempt + 1)
                        logger.warning(
                            f"ai_backfill {job_id}: slot {mb_id}#{slot_idx} attempt "
                            f"{attempt + 1}/{max_retries} failed: {e} — "
                            f"retrying in {delay}s"
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"ai_backfill {job_id}: failed slot {mb_id}#{slot_idx}: {e}"
                        )
                        progress["failed"] += 1

            progress["done_slots"] += 1

    await asyncio.gather(
        *[_process_slot(mb_id, slot_idx, i)
          for i, (mb_id, slot_idx) in enumerate(slots)]
    )

    _update_progress(
        sb, job_id,
        f"Done: {progress['analyzed']} classified, {progress['failed']} failed "
        f"across {len(mailbox_ids)} mailboxes ({total_slots} slots)",
        pct=100,
        processed=progress["analyzed"],
        failed=progress["failed"],
    )

    logger.info(
        f"ai_backfill {job_id}: completed — {progress['analyzed']} classified, "
        f"{progress['failed']} failed across {len(mailbox_ids)} mailboxes"
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
