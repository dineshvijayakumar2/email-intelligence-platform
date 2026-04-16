-- ============================================================================
-- Migration 083: Worker infrastructure — lease, heartbeat, claim support
-- ============================================================================
--
-- Extends processing_jobs for external worker processes that claim jobs
-- via SELECT FOR UPDATE SKIP LOCKED.
--
-- Prerequisites: migrations 073 (client_id, parameters, current_stage)
--                and 074 (reembed single-flight index).
--
-- All new columns are nullable or have defaults, so existing rows are
-- unaffected and no backfill is required.
--
-- ROLLBACK:
--   ALTER TABLE processing_jobs DROP COLUMN IF EXISTS last_heartbeat_at;
--   ALTER TABLE processing_jobs DROP COLUMN IF EXISTS worker_id;
--   ALTER TABLE processing_jobs DROP COLUMN IF EXISTS lease_expires_at;
--   ALTER TABLE processing_jobs DROP COLUMN IF EXISTS attempts;
--   ALTER TABLE processing_jobs DROP COLUMN IF EXISTS max_attempts;
--   ALTER TABLE processing_jobs DROP COLUMN IF EXISTS scheduled_for;
--   ALTER TABLE processing_jobs DROP COLUMN IF EXISTS triggered_by;
--   DROP INDEX IF EXISTS idx_processing_jobs_pending_scheduled;
--   DROP INDEX IF EXISTS idx_processing_jobs_active_lease;
--   DROP FUNCTION IF EXISTS claim_next_job(TEXT);
--   DROP FUNCTION IF EXISTS heartbeat_job(UUID, TEXT);
-- ============================================================================

BEGIN;

-- ── 1. Worker columns ──────────────────────────────────────────────────────

ALTER TABLE processing_jobs
    ADD COLUMN IF NOT EXISTS last_heartbeat_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS worker_id TEXT,
    ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS attempts INT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS max_attempts INT NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS scheduled_for TIMESTAMPTZ DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS triggered_by TEXT;

COMMENT ON COLUMN processing_jobs.last_heartbeat_at IS
    'Last time the worker reported it is alive. Used for stale-worker detection.';
COMMENT ON COLUMN processing_jobs.worker_id IS
    'Identifier of the worker process currently owning this job (hostname-pid).';
COMMENT ON COLUMN processing_jobs.lease_expires_at IS
    'When the current lease expires. After this time another worker may reclaim the job.';
COMMENT ON COLUMN processing_jobs.attempts IS
    'Number of times this job has been claimed (incremented on each claim, including reclaims after lease expiry).';
COMMENT ON COLUMN processing_jobs.max_attempts IS
    'Maximum allowed attempts before the job is abandoned. Default 1 (no retry).';
COMMENT ON COLUMN processing_jobs.scheduled_for IS
    'Earliest time the job should be picked up. Defaults to NOW() for immediate execution.';
COMMENT ON COLUMN processing_jobs.triggered_by IS
    'Source of the job: user, cron, or event. Metadata for monitoring; does not change execution.';

-- Backfill scheduled_for for existing pending rows so they are claimable
UPDATE processing_jobs
   SET scheduled_for = COALESCE(created_at, NOW())
 WHERE scheduled_for IS NULL;

-- ── 2. Indexes for worker claim ────────────────────────────────────────────

-- Pending jobs ordered by schedule time (primary claim path)
CREATE INDEX IF NOT EXISTS idx_processing_jobs_pending_scheduled
    ON processing_jobs(scheduled_for, created_at)
    WHERE status = 'pending';

-- Active leases: for monitoring and stuck-job detection
CREATE INDEX IF NOT EXISTS idx_processing_jobs_active_lease
    ON processing_jobs(lease_expires_at)
    WHERE status = 'running';

-- ── 3. Claim RPC ───────────────────────────────────────────────────────────
--
-- Atomically claims the next available job for a worker.
-- Uses FOR UPDATE SKIP LOCKED to handle concurrent workers safely.
--
-- Returns the full job row or NULL if no claimable job exists.
-- The caller (worker process) provides its worker_id.
--
-- Lease duration: 5 minutes. Worker must heartbeat within this window.

CREATE OR REPLACE FUNCTION claim_next_job(
    p_worker_id TEXT
) RETURNS SETOF processing_jobs
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    WITH claimed AS (
        SELECT id
        FROM processing_jobs
        WHERE scheduled_for <= NOW()
          AND (
              status = 'pending'
              OR (status = 'running' AND lease_expires_at < NOW())
          )
          AND attempts < max_attempts
        ORDER BY scheduled_for, created_at
        LIMIT 1
        FOR UPDATE SKIP LOCKED
    )
    UPDATE processing_jobs pj
    SET status = 'running',
        worker_id = p_worker_id,
        started_at = COALESCE(pj.started_at, NOW()),
        last_heartbeat_at = NOW(),
        lease_expires_at = NOW() + INTERVAL '5 minutes',
        attempts = pj.attempts + 1
    FROM claimed
    WHERE pj.id = claimed.id
    RETURNING pj.*;
END;
$$;

GRANT EXECUTE ON FUNCTION claim_next_job(TEXT) TO service_role;

COMMENT ON FUNCTION claim_next_job(TEXT) IS
    'Atomically claim the next pending or lease-expired job. '
    'Uses SELECT FOR UPDATE SKIP LOCKED for safe concurrent access. '
    'Sets 5-minute lease; worker must heartbeat to extend.';

-- ── 4. Heartbeat RPC ───────────────────────────────────────────────────────
--
-- Extends the lease for a running job. Called every 30s by the worker.
-- Only succeeds if the calling worker still owns the lease.

CREATE OR REPLACE FUNCTION heartbeat_job(
    p_job_id UUID,
    p_worker_id TEXT
) RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    v_count INT;
BEGIN
    UPDATE processing_jobs
    SET last_heartbeat_at = NOW(),
        lease_expires_at = NOW() + INTERVAL '5 minutes'
    WHERE id = p_job_id
      AND worker_id = p_worker_id
      AND status = 'running';

    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count > 0;
END;
$$;

GRANT EXECUTE ON FUNCTION heartbeat_job(UUID, TEXT) TO service_role;

COMMENT ON FUNCTION heartbeat_job(UUID, TEXT) IS
    'Extend the lease for a running job. Returns false if the worker no longer '
    'owns the job (reclaimed by another worker or cancelled). Worker should '
    'abort execution when false is returned.';

-- ── 5. Per-job-type dedup indexes ──────────────────────────────────────────
--
-- Extend the reembed pattern (migration 074) to other job types that
-- need single-flight enforcement.
--
-- QB sync: one active sync globally (no per-client scope needed)
-- AI analysis: one active per mailbox (client_id + mailbox_id scope)

CREATE UNIQUE INDEX IF NOT EXISTS uq_jobs_active_qb_sync
    ON processing_jobs((1))
    WHERE status IN ('pending', 'running')
      AND job_type = 'qb_sync_scheduled';

CREATE UNIQUE INDEX IF NOT EXISTS uq_jobs_active_ai_analysis_per_mailbox
    ON processing_jobs(mailbox_id)
    WHERE status IN ('pending', 'running')
      AND job_type = 'ai_analysis';

COMMENT ON INDEX uq_jobs_active_qb_sync IS
    'Single-flight: at most one active QB sync globally. Uses constant expression (1) for global scope.';
COMMENT ON INDEX uq_jobs_active_ai_analysis_per_mailbox IS
    'Single-flight: at most one active AI analysis per mailbox.';

COMMIT;
