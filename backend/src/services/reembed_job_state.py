"""
ReembedJobState — persistent state management for reembed jobs in processing_jobs.

Owns ALL read/write to processing_jobs for reembed jobs specifically. The
reembed router and worker call into this module rather than touching the
processing_jobs table directly.

This module is intentionally narrow:
  - No business logic. Only persistence + state transitions.
  - No DDL. Schema lives in scripts/migrations/073 and 074.
  - No new infrastructure. Uses existing supabase client.

Single-flight is enforced at the DB level via the partial unique index
created in migration 074. The application layer attempts INSERT and
catches the resulting unique_violation (SQLSTATE 23505), translating it
to a 409 at the router boundary.

Cancellation pattern mirrors the existing processing_jobs convention
(routers/processing_jobs.py:889): request_cancel sets status='stopped'
immediately. The worker's check_cancelled sees this on its next poll and
exits, allowing the BulkIndexManager finally block to recreate indexes.

Known limitation: there is a small window between cancellation request and
the worker's finally block completing where status='stopped' but indexes
are still dropped. A second reembed triggered in this window would race
with the first reembed's index recreation. Documented for human review.
See FLAG comment at the bottom of this file.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

# The job_type value used to identify reembed jobs in the shared processing_jobs table.
JOB_TYPE = "reembed"

# Statuses indicating an in-flight job for single-flight enforcement.
ACTIVE_STATUSES = ("pending", "running")

# Statuses that the worker should treat as a cancellation signal.
CANCELLED_STATUSES = ("stopped", "cancelled")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ActiveJobExists(Exception):
    """Raised by create_job when single-flight is violated.

    Carries the existing job's record so the caller can return it in the 409.
    """
    def __init__(self, existing_job: dict):
        super().__init__(f"Active reembed job already exists: {existing_job.get('id')}")
        self.existing_job = existing_job


class ReembedJobState:
    """Persistence helper for reembed jobs. One instance per request is fine."""

    def __init__(self, supabase_client):
        self._sb = supabase_client

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def create_job(
        self,
        client_id: str,
        tables: list[str],
        limit: Optional[int],
        triggered_by_user_id: Optional[str],
    ) -> str:
        """Insert a new pending reembed job. Returns the job id.

        Raises ActiveJobExists if the partial unique index rejects the insert
        because another active reembed exists for this client.
        """
        # Defense-in-depth: the partial unique index treats NULL client_id rows as
        # distinct, so it does not block multiple null-client jobs. Reject at the
        # application layer to make this constraint explicit.
        if client_id is None:
            raise ValueError("reembed jobs require a non-null client_id")

        params = {
            "tables": tables,
            "limit": limit,
            "triggered_by_user_id": triggered_by_user_id,
        }
        row = {
            "job_type": JOB_TYPE,
            "client_id": client_id,
            "status": "pending",
            "total_records": 0,
            "processed_records": 0,
            "failed_records": 0,
            "parameters": params,
        }
        try:
            resp = self._sb.table("processing_jobs").insert(row).execute()
        except Exception as e:
            err = str(e)
            # Match SQLSTATE 23505 (unique_violation) — the established pattern in
            # this codebase (operations.py:799, clients.py:442).
            if "23505" in err or "duplicate key" in err.lower():
                existing = self.get_active_job_for_client(client_id)
                if existing:
                    raise ActiveJobExists(existing) from e
                # Constraint fired but no active job? Race with cleanup; surface real error.
                raise
            raise

        if not resp.data:
            raise RuntimeError(f"create_job returned no data: {resp}")
        job_id = resp.data[0]["id"]
        logger.info(f"[ReembedJob] Created job {job_id} for client {client_id}, tables={tables}")
        return job_id

    def mark_running(self, job_id: str) -> None:
        """Transition pending -> running, stamp started_at."""
        self._sb.table("processing_jobs").update({
            "status": "running",
            "started_at": _now_iso(),
        }).eq("id", job_id).execute()

    def mark_completed(self, job_id: str) -> None:
        """Transition to completed, stamp completed_at, summarize errors."""
        # Fetch error_log to compute summary atomically with the status flip.
        # NOTE: tiny race here — if append_error fires between this SELECT and the
        # UPDATE below, that error is excluded from error_summary. Acceptable for
        # the completion path (worker is single-threaded per job).
        resp = self._sb.table("processing_jobs").select(
            "error_log"
        ).eq("id", job_id).single().execute()
        error_log = (resp.data or {}).get("error_log") or []
        summary = self._compute_error_summary(error_log)
        self._sb.table("processing_jobs").update({
            "status": "completed",
            "completed_at": _now_iso(),
            "error_summary": summary,
            "current_stage": "completed",
        }).eq("id", job_id).execute()

    def mark_failed(self, job_id: str, error: dict) -> None:
        """Transition to failed, stamp completed_at, preserve error context."""
        self.append_error(job_id, error)
        # Re-fetch to compute summary from the updated error_log.
        resp = self._sb.table("processing_jobs").select(
            "error_log"
        ).eq("id", job_id).single().execute()
        error_log = (resp.data or {}).get("error_log") or []
        summary = self._compute_error_summary(error_log)
        self._sb.table("processing_jobs").update({
            "status": "failed",
            "completed_at": _now_iso(),
            "error_summary": summary,
        }).eq("id", job_id).execute()

    def mark_stopped(self, job_id: str) -> None:
        """Transition to stopped (cancelled). Idempotent — safe to call after request_cancel.

        Sets completed_at if not already set. Status update is a no-op if already 'stopped'.
        """
        self._sb.table("processing_jobs").update({
            "status": "stopped",
            "completed_at": _now_iso(),
        }).eq("id", job_id).execute()

    # ── Progress (atomic via RPC) ─────────────────────────────────────────

    def update_progress(
        self,
        job_id: str,
        delta_processed: int = 0,
        delta_failed: int = 0,
        current_stage: Optional[str] = None,
    ) -> None:
        """Atomic counter increment via the increment_job_progress RPC.

        Multiple concurrent calls compose correctly: deltas of 5 and 3 leave
        processed_records at +8, never at +5 or +3. This is the key reason for
        the RPC — read-modify-write would clobber.
        """
        self._sb.rpc("increment_job_progress", {
            "p_job_id": str(job_id),
            "p_delta_processed": int(delta_processed),
            "p_delta_failed": int(delta_failed),
            "p_stage": current_stage,
        }).execute()

    def append_error(self, job_id: str, error: dict) -> None:
        """Append to error_log JSONB. Read-modify-write is acceptable here because
        errors are appended at most once per fatal exception — not per batch.
        """
        resp = self._sb.table("processing_jobs").select(
            "error_log"
        ).eq("id", job_id).single().execute()
        log = (resp.data or {}).get("error_log") or []
        log.append({**error, "ts": _now_iso()})
        self._sb.table("processing_jobs").update({
            "error_log": log,
        }).eq("id", job_id).execute()

    # ── Cancellation ──────────────────────────────────────────────────────

    def request_cancel(self, job_id: str) -> None:
        """Mark the job as stopped immediately. The worker's check_cancelled
        will see this on its next poll and exit gracefully.

        See module docstring for the known race window between this call and
        the worker's BulkIndexManager finally block completing.
        """
        self._sb.table("processing_jobs").update({
            "status": "stopped",
            "completed_at": _now_iso(),
        }).eq("id", job_id).execute()
        logger.info(f"[ReembedJob] Cancellation requested for {job_id}")

    def check_cancelled(self, job_id: str) -> bool:
        """One DB lookup — returns True if status indicates cancellation.

        Worker should call this between batches (or at table boundaries given
        the existing reembed_all loop structure — see FLAG below).
        """
        try:
            resp = self._sb.table("processing_jobs").select("status").eq(
                "id", job_id
            ).single().execute()
        except Exception as e:
            logger.warning(f"[ReembedJob] check_cancelled lookup failed for {job_id}: {e}")
            return False
        status = (resp.data or {}).get("status")
        return status in CANCELLED_STATUSES

    # ── Reads ─────────────────────────────────────────────────────────────

    def get_job(self, job_id: str) -> Optional[dict]:
        """Single-row fetch for the polling endpoint and SSE initial event."""
        try:
            resp = self._sb.table("processing_jobs").select("*").eq(
                "id", job_id
            ).single().execute()
        except Exception:
            return None
        return resp.data

    def get_active_job_for_client(self, client_id: str) -> Optional[dict]:
        """Returns a single active (pending|running) reembed job for this client,
        or None. The partial unique index in migration 074 guarantees there is
        at most one such row.
        """
        resp = self._sb.table("processing_jobs").select("*").eq(
            "client_id", client_id
        ).eq("job_type", JOB_TYPE).in_(
            "status", list(ACTIVE_STATUSES)
        ).limit(1).execute()
        rows = resp.data or []
        return rows[0] if rows else None

    def get_latest_job_for_client(self, client_id: str) -> Optional[dict]:
        """Returns the most recent reembed job for a client, regardless of status.

        Used by the polling endpoint when no job_id is specified, to preserve
        the legacy 'latest job' semantics of /vector/reembed/status.
        """
        resp = self._sb.table("processing_jobs").select("*").eq(
            "client_id", client_id
        ).eq("job_type", JOB_TYPE).order(
            "created_at", desc=True
        ).limit(1).execute()
        rows = resp.data or []
        return rows[0] if rows else None

    # ── Internal ──────────────────────────────────────────────────────────

    @staticmethod
    def _compute_error_summary(error_log: list) -> dict:
        """Compress error_log into a small summary for UI display."""
        if not error_log:
            return {"total_errors": 0, "error_types": {}, "sample_errors": []}
        types: dict[str, int] = {}
        for entry in error_log:
            t = entry.get("type") or entry.get("error") or "unknown"
            types[t] = types.get(t, 0) + 1
        return {
            "total_errors": len(error_log),
            "error_types": types,
            "sample_errors": error_log[:3],
        }


# ─────────────────────────────────────────────────────────────────────────────
# FLAG for human review:
#
# 1. CANCELLATION RACE (documented above): request_cancel sets status='stopped'
#    immediately. There is a window where status='stopped' but the worker's
#    BulkIndexManager finally block has not yet finished recreating dropped
#    HNSW indexes. A second POST /vector/reembed during this window would
#    pass the single-flight check (no active job by status) and start a new
#    reembed concurrently with the first one's index recreation. Mitigations:
#       (a) accept and document — reembed cancellation is rare; window is
#           seconds-to-minutes for HNSW.
#       (b) introduce a 'cancelling' intermediate status (schema change to
#           include 'cancelling' in the unique-index WHERE clause).
#       (c) Move the request_cancel status flip to the END of the worker's
#           finally block, with a separate cancel signal mechanism in between.
#    Recommended: (a) for now, with (b) as a follow-up if the race ever bites.
#
# 2. PROGRESS GRANULARITY: vector_service.reembed_all does NOT expose a
#    progress callback. Per the task spec ("do not change inner reembed
#    logic"), update_progress is wired in at table boundaries only — not per
#    batch. UI shows 3 steps (emails → companies → operations) rather than
#    smooth incremental progress. To get per-batch granularity, a follow-up
#    task must add a progress_callback parameter to reembed_all.
#
# 3. SECURITY MODEL OF increment_job_progress: declared SECURITY INVOKER by
#    default in migration 073. The service role must already have UPDATE
#    rights on processing_jobs for this to work. Verify before deploying.
# ─────────────────────────────────────────────────────────────────────────────
