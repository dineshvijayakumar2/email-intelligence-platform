"""
Worker handler for reference_extraction jobs.

Scans emails for QB reference numbers and creates thread_qb_links.
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger("worker.reference_extraction")


async def reference_extraction_handler(sb, job: dict, stop_event: asyncio.Event):
    """Extract QB references from all emails for a client."""
    from src.services.reference_extractor import batch_extract_for_client

    client_id = job.get("client_id")
    if not client_id:
        raise ValueError("reference_extraction job requires client_id")

    def _on_progress(stage, delta_processed, delta_failed):
        if stop_event.is_set():
            return
        try:
            sb.rpc("increment_job_progress", {
                "p_job_id": str(job["id"]),
                "p_delta_processed": int(delta_processed),
                "p_delta_failed": int(delta_failed),
                "p_stage": stage,
            }).execute()
        except Exception:
            pass

    result = await asyncio.to_thread(
        batch_extract_for_client,
        sb,
        client_id,
        on_progress=_on_progress,
    )

    logger.info(
        f"Reference extraction for {client_id}: "
        f"scanned={result['total_scanned']}, links={result['total_links']}, "
        f"elapsed={result['elapsed_s']}s"
    )
