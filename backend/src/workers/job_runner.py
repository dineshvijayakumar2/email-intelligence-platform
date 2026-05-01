"""
Worker process — claims and executes jobs from processing_jobs.

Entry point: python -m src.workers.job_runner

Claims jobs via the claim_next_job RPC (SELECT FOR UPDATE SKIP LOCKED).
Runs a heartbeat task in parallel to extend the lease every 30s.
Handles graceful shutdown on SIGTERM/SIGINT.
Runs a stuck-job reconciler every 10 minutes.

See docs/background-work-rfc.md for full design.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket
import sys
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

# Load env before any other imports
_env = os.path.join(os.path.dirname(__file__), '..', '..', '.env.production')
if not os.path.exists(_env):
    _env = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
load_dotenv(_env)

from supabase import create_client

from .handlers import JOB_HANDLERS
from ..services.events import emit_job_event

logger = logging.getLogger("worker")

POLL_INTERVAL = float(os.environ.get("WORKER_POLL_INTERVAL", "2"))
HEARTBEAT_INTERVAL = 30
RECONCILE_INTERVAL = 600  # 10 minutes
WORKER_ID = os.environ.get(
    "WORKER_ID",
    f"{socket.gethostname()}-{os.getpid()}"
)

_shutdown_requested = False


def _handle_signal(signum, frame):
    global _shutdown_requested
    logger.info(f"Worker {WORKER_ID}: received signal {signum}, requesting shutdown")
    _shutdown_requested = True


def _setup_signals():
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)


def _create_supabase():
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    return create_client(url, key)


async def _claim_job(sb) -> dict | None:
    """Claim the next available job. Returns the job row or None."""
    try:
        resp = sb.rpc("claim_next_job", {"p_worker_id": WORKER_ID}).execute()
        if resp.data and len(resp.data) > 0:
            return resp.data[0]
        return None
    except Exception as e:
        logger.error(f"Failed to claim job: {e}")
        return None


async def _heartbeat_loop(sb, job_id: str, stop_event: asyncio.Event):
    """Extend the lease every HEARTBEAT_INTERVAL seconds until stopped."""
    while not stop_event.is_set():
        try:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            if stop_event.is_set():
                break
            resp = sb.rpc("heartbeat_job", {
                "p_job_id": job_id,
                "p_worker_id": WORKER_ID,
            }).execute()
            still_owned = resp.data
            if not still_owned:
                logger.warning(f"Lost lease on job {job_id} — another worker reclaimed it")
                stop_event.set()
                break
        except Exception as e:
            logger.error(f"Heartbeat failed for {job_id}: {e}")


async def _mark_completed(sb, job_id: str):
    """Fallback completion — only fires if the handler didn't manage its own status."""
    try:
        sb.table("processing_jobs").update({
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", job_id).eq("status", "running").execute()
    except Exception as e:
        logger.error(f"Failed to mark job {job_id} completed: {e}")


async def _mark_failed(sb, job_id: str, error: str):
    """Fallback failure — only fires if the handler didn't manage its own status."""
    try:
        sb.table("processing_jobs").update({
            "status": "failed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "error_log": [{"type": "worker_error", "message": error[:2000]}],
        }).eq("id", job_id).eq("status", "running").execute()
    except Exception as e:
        logger.error(f"Failed to mark job {job_id} failed: {e}")


async def _execute_job(sb, job: dict):
    """Run the handler for a job with heartbeat supervision."""
    job_id = job["id"]
    job_type = job["job_type"]

    handler = JOB_HANDLERS.get(job_type)
    if not handler:
        logger.error(f"No handler registered for job_type={job_type}")
        await _mark_failed(sb, job_id, f"Unknown job_type: {job_type}")
        return

    logger.info(f"Executing job {job_id} (type={job_type}, attempt={job.get('attempts', 1)})")
    emit_job_event(sb, job, "job.started")

    stop_event = asyncio.Event()
    heartbeat_task = asyncio.create_task(_heartbeat_loop(sb, job_id, stop_event))

    try:
        await handler(sb, job, stop_event)

        if not stop_event.is_set():
            await _mark_completed(sb, job_id)
            emit_job_event(sb, job, "job.completed")
            logger.info(f"Job {job_id} completed successfully")
        else:
            emit_job_event(sb, job, "job.stopped")
            logger.warning(f"Job {job_id} aborted (lease lost or shutdown)")
    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}", exc_info=True)
        await _mark_failed(sb, job_id, str(e))
        emit_job_event(sb, job, "job.failed", {"error": str(e)[:500]})
    finally:
        stop_event.set()
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass


async def _reconcile_stuck_jobs(sb):
    """Mark jobs with expired leases as 'interrupted'.

    Idempotent — safe to run from every worker concurrently.
    """
    try:
        resp = sb.rpc("reconcile_stuck_jobs", {}).execute()
        count = resp.data if resp.data else 0
        if count:
            logger.info(f"Reconciler: marked {count} stuck job(s) as interrupted")
    except Exception as e:
        logger.error(f"Stuck-job reconciliation failed: {e}")


async def _reconciler_loop(sb):
    """Background task: reconcile stuck jobs every RECONCILE_INTERVAL seconds."""
    while not _shutdown_requested:
        await asyncio.sleep(RECONCILE_INTERVAL)
        if _shutdown_requested:
            break
        await _reconcile_stuck_jobs(sb)


def _has_existing_resume(sb, interrupted_id: str) -> bool:
    """Check if a resume job already exists for this interrupted job.

    Prevents duplicate resume creation when the worker restarts multiple times.
    """
    try:
        resp = (
            sb.table("processing_jobs")
            .select("id", count="exact")
            .eq("job_type", "email_pipeline")
            .contains("parameters", {"resumed_from": interrupted_id})
            .execute()
        )
        return (resp.count or 0) > 0
    except Exception as e:
        logger.warning(f"Resume dedup check failed for {interrupted_id}: {e}")
        return True  # err on the side of caution — don't create duplicates


def _has_zombie_extraction(sb, mailbox_id: str) -> bool:
    """Check if a zombie extraction thread is still running for this mailbox.

    A zombie is an extraction_jobs row with status='processing' and
    updated_at within the last 10 minutes — the thread is alive in a
    previous worker process even though the pipeline job is interrupted.
    """
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        resp = (
            sb.table("extraction_jobs")
            .select("id", count="exact")
            .eq("mailbox_id", mailbox_id)
            .eq("status", "processing")
            .gte("updated_at", cutoff)
            .execute()
        )
        return (resp.count or 0) > 0
    except Exception as e:
        logger.warning(f"Zombie check failed for mailbox {mailbox_id}: {e}")
        return True  # err on the side of caution


async def _resume_interrupted_pipelines(sb):
    """On boot, find recently-interrupted pipeline jobs and auto-resume them.

    Only resumes jobs that have completed_steps (progress data we can trust).
    Leaves the interrupted job untouched as a historical record.
    """
    from ..services.jobs import create_job, JobSpec, JobAlreadyActive

    try:
        resp = (
            sb.table("processing_jobs")
            .select("id, mailbox_id, parameters, created_at")
            .eq("job_type", "email_pipeline")
            .eq("status", "interrupted")
            .gte("created_at", (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat())
            .execute()
        )
    except Exception as e:
        logger.error(f"Startup sweep query failed: {e}")
        return

    if not resp.data:
        logger.info("Startup sweep: no interrupted pipelines to resume")
        return

    resumed = 0
    for job in resp.data:
        params = job.get("parameters") or {}
        completed_steps = params.get("completed_steps")
        if not completed_steps:
            logger.info(f"Startup sweep: skipping {job['id']} — no completed_steps")
            continue

        mailbox_id = job["mailbox_id"]
        interrupted_id = job["id"]

        # Guard: skip if a resume job already exists for this interrupted job
        if _has_existing_resume(sb, interrupted_id):
            logger.info(
                f"Startup sweep: skipping {interrupted_id} — resume job already exists"
            )
            continue

        # Guard: skip if a zombie extraction thread is still running for this mailbox
        if _has_zombie_extraction(sb, mailbox_id):
            logger.info(
                f"Startup sweep: skipping {interrupted_id} — zombie extraction "
                f"still active for mailbox {mailbox_id}"
            )
            continue

        try:
            resume_params = {
                    "trigger_source": "resume_after_deploy",
                    "resumed_from": job["id"],
                    "completed_steps": completed_steps,
            }
            if params.get("extraction_mode"):
                resume_params["extraction_mode"] = params["extraction_mode"]
            new_id = create_job(sb, JobSpec(
                job_type="email_pipeline",
                mailbox_id=mailbox_id,
                parameters=resume_params,
                triggered_by="worker_startup",
                max_attempts=1,
            ))
            resumed += 1
            logger.info(
                f"Startup sweep: resumed {job['id']} → {new_id} "
                f"(skipping {len(completed_steps)} completed stages)"
            )
        except JobAlreadyActive:
            logger.info(f"Startup sweep: pipeline already active for mailbox {mailbox_id}, skipping")
        except Exception as e:
            logger.error(f"Startup sweep: failed to resume {job['id']}: {e}")

    logger.info(f"Startup sweep complete: {resumed} pipeline(s) auto-resumed")


async def main():
    """Main worker loop: claim -> execute -> repeat."""
    _setup_signals()
    logging.basicConfig(
        level=logging.INFO,
        format=f"%(asctime)s [{WORKER_ID}] %(name)s %(levelname)s: %(message)s",
    )
    # Suppress noisy per-request HTTP logs
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    logger.info(f"Worker {WORKER_ID} starting (poll={POLL_INTERVAL}s, heartbeat={HEARTBEAT_INTERVAL}s)")
    logger.info(f"Registered handlers: {list(JOB_HANDLERS.keys())}")

    sb = _create_supabase()

    await _resume_interrupted_pipelines(sb)

    reconciler_task = asyncio.create_task(_reconciler_loop(sb))

    try:
        while not _shutdown_requested:
            job = await _claim_job(sb)
            if not job:
                await asyncio.sleep(POLL_INTERVAL)
                continue

            await _execute_job(sb, job)

            if _shutdown_requested:
                break
    finally:
        reconciler_task.cancel()
        try:
            await reconciler_task
        except asyncio.CancelledError:
            pass

    logger.info(f"Worker {WORKER_ID} shutting down cleanly")


if __name__ == "__main__":
    asyncio.run(main())
