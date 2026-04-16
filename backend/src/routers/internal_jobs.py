"""
Internal job scheduler endpoints.

Called by external cron (Railway cron / cron-job.org) to trigger scheduled work.
Auth: CRON_SECRET token via Authorization header.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from ..dependencies.auth import verify_cron_secret

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
    """Hourly QB sync for all active clients."""
    from ..services.quickbase_sync import QuickbaseSync

    configs = _supabase.table("qb_sync_config").select("*").eq(
        "is_active", True
    ).execute()

    if not configs.data:
        return {"status": "skipped", "reason": "no active QB configs"}

    triggered = []
    for config in configs.data:
        client_id = config["client_id"]

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

    return {"status": "triggered", "clients": triggered}


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
            triggered_by="cron",
        ))
        return {"status": "created", "job_id": job_id}
    except JobAlreadyActive as e:
        return {"status": "skipped", "reason": "already running", "existing_job": e.existing_job}
    except Exception as e:
        logger.error(f"Failed to create analytics rollup job: {e}")
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
