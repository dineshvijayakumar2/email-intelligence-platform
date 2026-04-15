-- ============================================================================
-- Migration 082: QB Job Status Log (Audit Logs filtered to Job Status changes)
-- ============================================================================
--
-- Transactional — safe to run in Supabase SQL Editor.
--
-- ─── Purpose ────────────────────────────────────────────────────────────────
-- Sync the QB "Audit Logs" child table (bu9yjc3ne), filtered to rows where
-- Field Name = 'Job Status', into qb_job_status_log. Each row records one
-- job-status transition (old → new, at a timestamp, by a user).
--
-- Unblocks Phase 4 of contact-intelligence-design.md (Status Transition
-- Analytics): time-in-phase, bottleneck detection, per-contact production
-- cycle metrics.
--
-- Note on historical data: Carbon8 turned on this audit log TODAY
-- (2026-04-15). There is no backfill to do — incremental sync from the
-- first run captures everything that exists.
--
-- ─── What this migration does ───────────────────────────────────────────────
-- 1. Add audit_logs_table_id to qb_sync_config (pre-seeded)
-- 2. Create qb_job_status_log table with (client_id, qb_record_id) unique key
-- 3. Indexes for the expected query pattern (per-job history, recency)
-- ============================================================================

BEGIN;

-- ─── 1. Config column (pre-seeded with known DBID) ──────────────────────────
ALTER TABLE qb_sync_config
    ADD COLUMN IF NOT EXISTS audit_logs_table_id TEXT DEFAULT 'bu9yjc3ne';

-- Backfill the default for any existing rows so sync picks up immediately.
UPDATE qb_sync_config
   SET audit_logs_table_id = 'bu9yjc3ne'
 WHERE audit_logs_table_id IS NULL;

-- ─── 2. qb_job_status_log ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS qb_job_status_log (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id           UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,

    -- QB identifiers
    qb_record_id        TEXT NOT NULL,   -- fid 3: Record ID# (QB internal)
    job_no              TEXT,            -- fid 16: Related Job (FK to qb_jobs.job_no via masterTableKeyFid=7)

    -- Status transition
    old_status          TEXT,            -- fid 8: Old Value
    new_status          TEXT,            -- fid 9: New Value
    changed_at          TIMESTAMPTZ,     -- fid 1: Date Created (when the audit row was written = when the change happened)
    changed_by          TEXT,            -- fid 10: Changed by (user display name, e.g. "Smith, John")

    -- Sync metadata
    qb_last_modified    TIMESTAMPTZ,
    synced_at           TIMESTAMPTZ DEFAULT NOW(),
    created_at          TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(client_id, qb_record_id)
);

-- Per-job history, newest first (primary query: "show status timeline for job X")
CREATE INDEX IF NOT EXISTS idx_qb_job_status_log_job_time
    ON qb_job_status_log(client_id, job_no, changed_at DESC);

-- Recent transitions across all jobs (for dashboards / alerts)
CREATE INDEX IF NOT EXISTS idx_qb_job_status_log_recent
    ON qb_job_status_log(client_id, changed_at DESC);

COMMENT ON TABLE qb_job_status_log IS
  'Filtered subset of QB Audit Logs (bu9yjc3ne) where Field Name = ''Job Status''. '
  'One row per status transition. Feeds Phase 4 status-transition analytics.';
COMMENT ON COLUMN qb_job_status_log.changed_at IS
  'When the status change occurred. QB fid 1 (Date Created) on the audit row = the moment of change.';
COMMENT ON COLUMN qb_job_status_log.changed_by IS
  'QB user who made the change — stored as display name. Nullable for system changes.';

COMMIT;

-- ─── ROLLBACK ───────────────────────────────────────────────────────────────
-- DROP TABLE IF EXISTS qb_job_status_log;
-- ALTER TABLE qb_sync_config DROP COLUMN IF EXISTS audit_logs_table_id;
