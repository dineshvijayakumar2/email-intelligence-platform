"""
Worker handler for email_pipeline jobs.

Replaces the implicit post-sync chain (_trigger_post_sync_extraction) with an
explicit, observable, resumable pipeline. Each stage is executed in order;
completed_steps are persisted after every stage so the pipeline can be resumed
from the point of failure.

See docs/pipeline-design.md for the full design.
"""
from __future__ import annotations

import asyncio
import logging
import time

logger = logging.getLogger("worker.email_pipeline")

# ── Source of truth for step ordering ─────────────────────────────────────
PIPELINE_STAGES = [
    "extract_and_link",
    "assign_threads",
    "evaluate_threads",
    "refresh_counts",
    "embed_emails",
    "ai_classify",
    "bucket_engine",
    "evaluate_threads_final",
]


async def email_pipeline_handler(sb, job: dict, stop_event: asyncio.Event):
    """Run the full email pipeline for a single mailbox.

    Parameters (from job["parameters"]):
        trigger_source: str — "sync", "manual", or "resume"
        completed_steps: list[str] — stages already finished (for resume)
    """
    job_id = job["id"]
    mailbox_id = job.get("mailbox_id")
    params = job.get("parameters") or {}
    trigger_source = params.get("trigger_source", "unknown")
    completed_steps: list[str] = list(params.get("completed_steps") or [])

    if not mailbox_id:
        raise ValueError("email_pipeline job requires mailbox_id")

    logger.info(
        f"Pipeline {job_id} starting for mailbox {mailbox_id} "
        f"(trigger={trigger_source}, already_completed={completed_steps})"
    )

    # ── Resolve client_id ─────────────────────────────────────────────
    client_id = job.get("client_id")
    if not client_id:
        client_id = _resolve_client_id(sb, mailbox_id)

    # ── Create utility instances ──────────────────────────────────────
    from src.services.extraction_orchestrator import ExtractionOrchestrator
    from src.services.vector_service import VectorService
    from src.services.ai_email_analyzer import AIEmailAnalyzer
    from src.services.ai_action_bucket_engine import ActionBucketEngine

    orch = ExtractionOrchestrator(
        mailbox_id=mailbox_id,
        client_id=client_id,
        extraction_mode="full",
        use_redis=False,
    )
    orch.client = sb  # Use the worker's Supabase client
    orch._stop_check = stop_event.is_set

    vector_service = VectorService(sb)
    analyzer = AIEmailAnalyzer(sb)
    bucket_engine = ActionBucketEngine(sb)

    # ── Stage dispatch table ──────────────────────────────────────────
    # sync functions use asyncio.to_thread() to avoid blocking heartbeat;
    # embed_emails_batch is natively async.
    stage_handlers = {
        "extract_and_link": lambda: asyncio.to_thread(
            orch.run_extraction, lightweight=True
        ),
        "assign_threads": lambda: asyncio.to_thread(
            orch._assign_canonical_threads
        ),
        "evaluate_threads": lambda: asyncio.to_thread(
            orch._update_affected_threads
        ),
        "refresh_counts": lambda: asyncio.to_thread(
            orch._refresh_email_counts
        ),
        "embed_emails": lambda: vector_service.embed_emails_batch(
            client_id=client_id
        ),
        "ai_classify": lambda: asyncio.to_thread(
            analyzer.analyze_all_unanalyzed,
            mailbox_id=mailbox_id,
            client_id=client_id,
        ),
        "bucket_engine": lambda: asyncio.to_thread(
            bucket_engine.process_email_buckets,
            mailbox_id=mailbox_id,
        ),
        "evaluate_threads_final": lambda: asyncio.to_thread(
            orch._update_affected_threads
        ),
    }

    # ── Accumulated step results ──────────────────────────────────────
    step_results: dict = {}

    for idx, stage in enumerate(PIPELINE_STAGES):
        # Skip already-completed stages (resume path)
        if stage in completed_steps:
            logger.info(f"Pipeline {job_id}: skipping {stage} (already completed)")
            continue

        # Graceful shutdown check
        if stop_event.is_set():
            logger.warning(f"Pipeline {job_id}: stop requested before {stage}, persisting progress")
            _persist_progress(sb, job_id, completed_steps, step_results, stage=None)
            return  # Don't raise — worker sees clean return + stop_event set

        # Update current_stage for UI visibility
        pct = int((idx / len(PIPELINE_STAGES)) * 100)
        _update_stage(sb, job_id, stage, pct)

        step_start = time.monotonic()
        try:
            result = await stage_handlers[stage]()
            duration_s = round(time.monotonic() - step_start, 2)

            step_results[stage] = {
                "duration_s": duration_s,
                "status": "success",
                "data": _sanitize_result(result),
            }
            completed_steps.append(stage)

            logger.info(
                f"Pipeline {job_id}: {stage} completed in {duration_s}s"
            )

            # Persist after every step so resume knows where we left off
            _persist_progress(sb, job_id, completed_steps, step_results, stage)

        except InterruptedError:
            duration_s = round(time.monotonic() - step_start, 2)
            step_results[stage] = {
                "duration_s": duration_s,
                "status": "interrupted",
                "error": "stop requested",
            }
            logger.warning(
                f"Pipeline {job_id}: {stage} interrupted after {duration_s}s, persisting progress"
            )
            _persist_progress(sb, job_id, completed_steps, step_results, stage=None)
            return  # Clean exit — worker sees stop_event set

        except Exception as e:
            duration_s = round(time.monotonic() - step_start, 2)
            step_results[stage] = {
                "duration_s": duration_s,
                "status": "failed",
                "error": str(e)[:500],
            }
            # Persist what we have before re-raising
            _persist_progress(sb, job_id, completed_steps, step_results, stage)
            logger.error(
                f"Pipeline {job_id}: {stage} failed after {duration_s}s: {e}",
                exc_info=True,
            )
            raise

    # All stages done — final persist with 100%
    _update_stage(sb, job_id, "completed", 100)
    _persist_progress(sb, job_id, completed_steps, step_results, stage="completed")
    logger.info(f"Pipeline {job_id}: all {len(PIPELINE_STAGES)} stages completed")


# ── Helpers ───────────────────────────────────────────────────────────────


def _resolve_client_id(sb, mailbox_id: str) -> str:
    """Look up client_id from the mailboxes table."""
    resp = (
        sb.table("mailboxes")
        .select("client_id")
        .eq("id", mailbox_id)
        .limit(1)
        .execute()
    )
    if not resp.data:
        raise ValueError(f"Mailbox {mailbox_id} not found")
    client_id = resp.data[0].get("client_id")
    if not client_id:
        raise ValueError(f"Mailbox {mailbox_id} has no client_id")
    return client_id


def _update_stage(sb, job_id: str, stage: str, pct: int):
    """Update current_stage and progress percentage. Non-fatal on failure."""
    try:
        sb.table("processing_jobs").update({
            "current_stage": stage,
            "error_summary": {
                "progress_pct": pct,
                "progress_message": f"Running {stage}...",
            },
        }).eq("id", job_id).execute()
    except Exception as e:
        logger.error(f"Stage update failed for {job_id} (stage={stage}): {e}")


class ProgressPersistError(RuntimeError):
    """Raised when completed_steps cannot be saved after retries."""


def _persist_progress(
    sb,
    job_id: str,
    completed_steps: list[str],
    step_results: dict,
    stage: str | None,
):
    """Persist completed_steps into parameters and step_results into error_summary.

    Uses read-modify-write on parameters to preserve other fields.
    Retries up to 3 times; raises ProgressPersistError on exhaustion so the
    pipeline fails fast and preserves the last-known-good checkpoint.
    """
    import time as _time

    last_err = None
    for attempt in range(3):
        try:
            resp = (
                sb.table("processing_jobs")
                .select("parameters, error_summary")
                .eq("id", job_id)
                .single()
                .execute()
            )
            current_params = (resp.data or {}).get("parameters") or {}
            current_summary = (resp.data or {}).get("error_summary") or {}

            current_params["completed_steps"] = completed_steps

            current_summary["step_results"] = step_results
            if stage:
                pct = int(
                    (len(completed_steps) / len(PIPELINE_STAGES)) * 100
                )
                current_summary["progress_pct"] = pct
                current_summary["progress_message"] = (
                    f"Completed {stage}" if stage != "completed" else "Pipeline complete"
                )

            sb.table("processing_jobs").update({
                "parameters": current_params,
                "error_summary": current_summary,
            }).eq("id", job_id).execute()

            return  # success

        except Exception as e:
            last_err = e
            if attempt < 2:
                logger.warning(
                    f"Progress persist failed for {job_id} (attempt {attempt + 1}/3): {e}"
                )
                _time.sleep(1 * (attempt + 1))

    logger.error(
        f"Progress persist FAILED after 3 attempts for {job_id}: {last_err}"
    )
    raise ProgressPersistError(
        f"Cannot save completed_steps for {job_id}: {last_err}"
    ) from last_err


def _sanitize_result(result) -> dict | None:
    """Convert step result to a JSON-safe dict. Returns None for non-dict results."""
    if result is None:
        return None
    if isinstance(result, dict):
        sanitized = {}
        for k, v in result.items():
            sanitized[k] = _sanitize_value(v)
        return sanitized
    return {"raw": str(result)[:500]}


def _sanitize_value(v):
    """Make a single value JSON-serializable."""
    from datetime import datetime, date
    if v is None or isinstance(v, (bool, int, float)):
        return v
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, str):
        return v[:500] + "..." if len(v) > 500 else v
    if isinstance(v, list):
        return f"[{len(v)} items]" if len(v) > 20 else [_sanitize_value(i) for i in v]
    if isinstance(v, dict):
        return {k: _sanitize_value(val) for k, val in v.items()}
    return str(v)[:500]
