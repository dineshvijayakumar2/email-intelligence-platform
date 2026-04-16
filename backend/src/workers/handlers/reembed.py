"""
Worker handler for reembed jobs.

Extracts execution logic from the API process into a standalone handler
that runs under the worker's lease/heartbeat supervision.
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger("worker.reembed")


async def reembed_handler(sb, job: dict, stop_event: asyncio.Event):
    """Re-embed emails/companies/operations for a client.

    Two invariants (carried over from the in-process version):
      1. vs.reembed_all() owns BulkIndexManager — exceptions must propagate
         through it so the finally block recreates HNSW indexes.
      2. Every exit path must leave the job in a terminal status.
    """
    from src.services.reembed_job_state import ReembedJobState
    from src.services.vector_service import VectorService

    job_id = job["id"]
    client_id = job["client_id"]
    params = job.get("parameters") or {}
    table_list = params.get("tables", ["emails", "companies", "operations"])
    limit = params.get("limit")

    state = ReembedJobState(sb)
    vs = VectorService(sb)

    def _on_progress(stage: str, delta_processed: int = 0, delta_failed: int = 0):
        try:
            state.update_progress(
                job_id,
                delta_processed=delta_processed,
                delta_failed=delta_failed,
                current_stage=stage,
            )
        except Exception as pe:
            logger.warning(f"Progress update failed for {job_id}: {pe}")

    def _is_cancelled() -> bool:
        return stop_event.is_set() or state.check_cancelled(job_id)

    try:
        state.mark_running(job_id)
        _on_progress("starting")

        result = await vs.reembed_all(
            client_id,
            limit=limit,
            tables=table_list,
            cancel_check=_is_cancelled,
            on_progress=_on_progress,
        )

        if _is_cancelled():
            _on_progress("stopped")
            state.mark_stopped(job_id)
            stop_event.set()
            logger.info(f"Reembed job {job_id} stopped: {result}")
        else:
            _on_progress("completed")
            state.mark_completed(job_id)
            logger.info(f"Reembed job {job_id} completed: {result}")
    except Exception as e:
        logger.error(f"Reembed job {job_id} failed: {e}", exc_info=True)
        try:
            state.mark_failed(job_id, {
                "type": e.__class__.__name__,
                "error": str(e)[:500],
            })
        except Exception as inner:
            logger.error(f"Failed to mark job {job_id} failed: {inner}")
        raise
