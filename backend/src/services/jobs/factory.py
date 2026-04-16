"""
Job Factory — single entry point for creating processing_jobs rows.

Replaces 14 scattered .insert() callsites with a unified interface that
enforces schema, handles single-flight dedup (via partial unique indexes),
and populates the worker columns added in migration 083.

Usage:
    from src.services.jobs import create_job, JobSpec

    job_id = create_job(supabase_client, JobSpec(
        job_type="ai_analysis",
        mailbox_id=mailbox_id,
        client_id=client_id,
        parameters={"max_emails": 500},
        triggered_by="user",
    ))

Single-flight enforcement is database-level via partial unique indexes
(migrations 074, 083). The factory catches SQLSTATE 23505 (unique_violation)
and raises JobAlreadyActive with the existing job's record.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = ("pending", "running")


class JobAlreadyActive(Exception):
    """Raised when single-flight dedup rejects a new job."""
    def __init__(self, existing_job: dict):
        job_id = existing_job.get("id", "unknown")
        job_type = existing_job.get("job_type", "unknown")
        super().__init__(f"Active {job_type} job already exists: {job_id}")
        self.existing_job = existing_job


class JobSpec(BaseModel):
    """Specification for a new job. All callsites build one of these."""
    job_type: str
    mailbox_id: Optional[str] = None
    client_id: Optional[str] = None
    parameters: dict = Field(default_factory=dict)
    total_records: int = 0
    max_attempts: int = 3
    scheduled_for: Optional[datetime] = None
    triggered_by: str = "user"
    filter_start_date: Optional[str] = None
    filter_end_date: Optional[str] = None
    initial_status: str = "pending"


def create_job(sb, spec: JobSpec) -> str:
    """Insert a new processing_jobs row. Returns the job id (str).

    Args:
        sb: Supabase client (service role).
        spec: JobSpec describing the job.

    Returns:
        The UUID string of the created job.

    Raises:
        JobAlreadyActive: if a partial unique index rejects the insert
            (single-flight enforcement).
    """
    job_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()

    row: dict[str, Any] = {
        "id": job_id,
        "job_type": spec.job_type,
        "status": spec.initial_status,
        "total_records": spec.total_records,
        "processed_records": 0,
        "failed_records": 0,
        "filtered_records": 0,
        "parameters": spec.parameters,
        "max_attempts": spec.max_attempts,
        "attempts": 0,
        "scheduled_for": (spec.scheduled_for or datetime.now(timezone.utc)).isoformat(),
        "triggered_by": spec.triggered_by,
        "created_at": now,
    }

    if spec.initial_status == "running":
        row["started_at"] = now

    if spec.mailbox_id:
        row["mailbox_id"] = spec.mailbox_id
    if spec.client_id:
        row["client_id"] = spec.client_id
    if spec.filter_start_date:
        row["filter_start_date"] = spec.filter_start_date
    if spec.filter_end_date:
        row["filter_end_date"] = spec.filter_end_date

    try:
        resp = sb.table("processing_jobs").insert(row).execute()
    except Exception as e:
        err = str(e)
        if "23505" in err or "duplicate key" in err.lower():
            existing = _find_active_job(sb, spec)
            if existing:
                raise JobAlreadyActive(existing) from e
            raise
        raise

    if not resp.data:
        raise RuntimeError(f"create_job returned no data for {spec.job_type}")

    logger.info(
        f"[JobFactory] Created {spec.job_type} job {job_id} "
        f"(client={spec.client_id}, mailbox={spec.mailbox_id}, "
        f"triggered_by={spec.triggered_by})"
    )
    return job_id


def _find_active_job(sb, spec: JobSpec) -> Optional[dict]:
    """Look up the active job that caused the dedup collision."""
    query = (
        sb.table("processing_jobs")
        .select("*")
        .eq("job_type", spec.job_type)
        .in_("status", list(ACTIVE_STATUSES))
    )
    if spec.client_id:
        query = query.eq("client_id", spec.client_id)
    if spec.mailbox_id:
        query = query.eq("mailbox_id", spec.mailbox_id)

    resp = query.limit(1).execute()
    return resp.data[0] if resp.data else None
