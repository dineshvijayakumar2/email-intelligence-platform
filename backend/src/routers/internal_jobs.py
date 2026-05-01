"""
Internal job scheduler endpoints.

Called by external cron (Railway cron / cron-job.org) to trigger scheduled work.
Auth: CRON_SECRET token via Authorization header.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from ..dependencies.auth import verify_cron_secret, require_role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/jobs", tags=["internal"])

_supabase = None


def init_internal_jobs_router(supabase_client):
    global _supabase
    _supabase = supabase_client


@router.post("/qb-sync")
async def cron_qb_sync(
    background_tasks: BackgroundTasks,
    _: None = Depends(verify_cron_secret),
):
    """QB sync for active auto-sync clients. Respects per-client sync_interval_hours."""
    from ..services.quickbase_sync import QuickbaseSync

    configs = _supabase.table("qb_sync_config").select("*").eq(
        "is_active", True
    ).execute()

    if not configs.data:
        return {"status": "skipped", "reason": "no active QB configs"}

    now = datetime.now(timezone.utc)
    triggered = []
    skipped = []

    for config in configs.data:
        client_id = config["client_id"]
        interval_hours = config.get("sync_interval_hours")

        if interval_hours is None:
            skipped.append({"client_id": client_id, "reason": "manual_mode"})
            continue

        last_sync = config.get("last_sync_at")
        if last_sync:
            last_sync_dt = datetime.fromisoformat(last_sync.replace("Z", "+00:00"))
            next_due = last_sync_dt + timedelta(hours=interval_hours)
            if now < next_due:
                skipped.append({
                    "client_id": client_id,
                    "reason": "not_due",
                    "next_due": next_due.isoformat(),
                })
                continue

        def _run(cfg=config, cid=client_id):
            from supabase import create_client
            sb = create_client(
                os.environ["SUPABASE_URL"],
                os.environ["SUPABASE_SERVICE_KEY"],
            )
            loop = asyncio.new_event_loop()
            try:
                syncer = QuickbaseSync(sb, cfg)
                loop.run_until_complete(syncer.sync_all())
                loop.run_until_complete(syncer.propagate_qb_data_to_companies())
                loop.run_until_complete(syncer.propagate_qb_data_to_contacts())
            except Exception as e:
                logger.error(f"Cron QB sync failed for {cid}: {e}")
            finally:
                loop.close()

        background_tasks.add_task(_run)
        triggered.append(client_id)

    if skipped:
        logger.info(f"QB sync skipped {len(skipped)} client(s): {skipped}")

    return {"status": "triggered", "clients": triggered, "skipped": skipped}


@router.post("/gmail-sync")
async def cron_gmail_sync(
    _: None = Depends(verify_cron_secret),
):
    """Sync all due Gmail mailboxes. Called by Railway cron (e.g. every 15 min)."""
    from ..services.gmail_sync_service import get_gmail_sync_service

    svc = get_gmail_sync_service()
    try:
        await svc.run_cron_sync()
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Gmail cron sync error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/outlook-sync")
async def cron_outlook_sync(
    _: None = Depends(verify_cron_secret),
):
    """Sync all due Outlook mailboxes. Called by Railway cron (e.g. every 15 min)."""
    from ..services.outlook_sync_service import get_outlook_sync_service

    svc = get_outlook_sync_service()
    try:
        await svc.run_cron_sync()
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Outlook cron sync error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stuck-reconciler")
async def cron_stuck_reconciler(
    _: None = Depends(verify_cron_secret),
):
    """Mark stuck jobs (expired leases) as interrupted. Belt-and-suspenders
    backup for the reconciler loop that runs inside each worker process."""
    try:
        resp = _supabase.rpc("reconcile_stuck_jobs", {}).execute()
        count = resp.data if resp.data else 0
        return {"status": "ok", "interrupted_count": count}
    except Exception as e:
        logger.error(f"Stuck reconciler failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analytics-rollup")
async def cron_analytics_rollup(
    _: None = Depends(verify_cron_secret),
):
    """Daily analytics rollup placeholder. Will create a processing_job
    when the analytics_rollup handler is implemented."""
    from ..services.jobs import create_job, JobSpec, JobAlreadyActive
    try:
        job_id = create_job(_supabase, JobSpec(
            job_type="analytics_rollup_daily",
            initial_status="running",  # No worker handler yet — prevent worker claiming
            triggered_by="cron",
        ))
        return {"status": "created", "job_id": job_id}
    except JobAlreadyActive as e:
        return {"status": "skipped", "reason": "already running", "existing_job": e.existing_job}
    except Exception as e:
        logger.error(f"Failed to create analytics rollup job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/notification-dispatch")
async def cron_notification_dispatch(
    _: None = Depends(verify_cron_secret),
):
    """Dispatch pending notifications from undispatched events.

    Creates a notification_dispatch processing job that the worker picks up.
    Called every 2 minutes by external cron.
    """
    from ..services.jobs import create_job, JobSpec, JobAlreadyActive
    try:
        job_id = create_job(_supabase, JobSpec(
            job_type="notification_dispatch",
            triggered_by="cron",
            max_attempts=1,
        ))
        return {"status": "created", "job_id": job_id}
    except JobAlreadyActive as e:
        return {"status": "skipped", "reason": "already running", "existing_job": e.existing_job}
    except Exception as e:
        logger.error(f"Failed to create notification dispatch job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def worker_health(
    _: None = Depends(verify_cron_secret),
):
    """Diagnostic: are all workers and jobs healthy?

    Returns zero issues if everything is fine. Non-empty issues array
    means something needs attention.
    """
    issues = []

    try:
        stuck = _supabase.rpc("exec_sql", {"query": """
            SELECT count(*) AS cnt
            FROM processing_jobs
            WHERE status = 'running'
              AND lease_expires_at IS NOT NULL
              AND lease_expires_at < NOW();
        """}).execute()
        stuck_count = 0
        if stuck.data and isinstance(stuck.data, list) and stuck.data:
            stuck_count = stuck.data[0].get("cnt", 0)
        if stuck_count:
            issues.append(f"{stuck_count} stuck job(s) with expired leases")
    except Exception as e:
        issues.append(f"Health check query failed: {e}")

    try:
        pending = _supabase.table("processing_jobs").select(
            "id", count="exact"
        ).eq("status", "pending").execute()
        pending_count = pending.count or 0
        if pending_count > 20:
            issues.append(f"{pending_count} pending jobs (possible worker stall)")
    except Exception:
        pass

    try:
        undispatched = _supabase.table("events").select(
            "id", count="exact"
        ).is_("dispatched_at", "null").execute()
        undisp_count = undispatched.count or 0
        if undisp_count > 50:
            issues.append(f"{undisp_count} undispatched events (notification backlog)")
    except Exception:
        pass

    status = "healthy" if not issues else "degraded"
    return {"status": status, "issues": issues}


# ── Persona Metrics Refresh ────────────────────────────────────────────────


@router.post("/refresh-persona-metrics")
async def refresh_persona_metrics(
    _: None = Depends(verify_cron_secret),
):
    """Refresh the contact_email_metrics materialized view.

    Called by external cron (daily) and after QB sync completes.
    Uses REFRESH MATERIALIZED VIEW CONCURRENTLY so reads are not blocked.
    """
    import time as _time

    t0 = _time.monotonic()
    try:
        _supabase.rpc("refresh_contact_email_metrics", {}).execute()
        elapsed = round(_time.monotonic() - t0, 2)
        logger.info(f"Persona metrics refreshed in {elapsed}s")
        return {"status": "ok", "elapsed_seconds": elapsed}
    except Exception as e:
        elapsed = round(_time.monotonic() - t0, 2)
        logger.error(f"Persona metrics refresh failed after {elapsed}s: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Email Pipeline endpoints (admin-facing) ──────────────────────────────


@router.post("/mailboxes/{mailbox_id}/run-pipeline")
async def trigger_pipeline(
    mailbox_id: str,
    current_user: dict = Depends(require_role("admin")),
):
    """Manually trigger the email pipeline for a mailbox.

    Returns 200 with job_id if created, or status='already_running' if
    a pipeline is already active for this mailbox.
    """
    from ..services.jobs import create_job, JobSpec, JobAlreadyActive

    try:
        job_id = create_job(_supabase, JobSpec(
            job_type="email_pipeline",
            mailbox_id=mailbox_id,
            parameters={"trigger_source": "manual"},
            triggered_by="user",
            max_attempts=1,
        ))
        return {"job_id": job_id, "status": "queued"}
    except JobAlreadyActive as e:
        return {"job_id": e.existing_job.get("id"), "status": "already_running"}
    except Exception as e:
        logger.error(f"Failed to create pipeline job for mailbox {mailbox_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/jobs/{job_id}/resume-pipeline")
async def resume_pipeline(
    job_id: str,
    current_user: dict = Depends(require_role("admin")),
):
    """Resume a failed or interrupted pipeline from where it stopped.

    Creates a new pipeline job with completed_steps pre-populated from
    the previous run's parameters.
    """
    from ..services.jobs import create_job, JobSpec, JobAlreadyActive
    from ..workers.handlers.email_pipeline import PIPELINE_STAGES

    # Fetch the failed/interrupted job
    try:
        resp = _supabase.table("processing_jobs").select("*").eq("id", job_id).single().execute()
    except Exception:
        raise HTTPException(status_code=404, detail="Job not found")

    failed_job = resp.data
    if not failed_job:
        raise HTTPException(status_code=404, detail="Job not found")

    if failed_job["job_type"] != "email_pipeline":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot resume job of type {failed_job['job_type']}",
        )

    if failed_job["status"] not in ("failed", "interrupted"):
        raise HTTPException(
            status_code=400,
            detail=f"Can only resume failed or interrupted pipelines, got status={failed_job['status']}",
        )

    # Preserve completed_steps from the failed run
    prev_params = failed_job.get("parameters") or {}
    completed_steps = prev_params.get("completed_steps") or []

    resume_params = {
        "trigger_source": "resume",
        "resumed_from": job_id,
        "completed_steps": completed_steps,
    }
    if prev_params.get("extraction_mode"):
        resume_params["extraction_mode"] = prev_params["extraction_mode"]
    try:
        new_job_id = create_job(_supabase, JobSpec(
            job_type="email_pipeline",
            mailbox_id=failed_job["mailbox_id"],
            parameters=resume_params,
            triggered_by="user",
            max_attempts=1,
        ))
        return {
            "job_id": new_job_id,
            "status": "queued",
            "resumed_from_step": completed_steps[-1] if completed_steps else None,
            "remaining_steps": [s for s in PIPELINE_STAGES if s not in completed_steps],
        }
    except JobAlreadyActive as e:
        return {"job_id": e.existing_job.get("id"), "status": "already_running"}
    except Exception as e:
        logger.error(f"Failed to resume pipeline job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
