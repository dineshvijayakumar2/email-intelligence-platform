-- ============================================================================
-- Migration 073: Extend processing_jobs to support reembed
-- ============================================================================
--
-- ⚠️  REQUIRES HUMAN REVIEW BEFORE EXECUTION.
--
-- Reviewer checklist (per the authorization for this work):
--   [ ] Migration framework does not wrap individual files in transactions
--       OR each ALTER TABLE here will run in its own implicit txn (PG default,
--       fine — nothing here uses CONCURRENTLY).
--   [ ] The clients(id) FK target table is correct (verified: scripts/create_tables.sql:652).
--   [ ] Service role grants for increment_job_progress are correct for this
--       project's role setup (default SECURITY INVOKER assumed; reviewer must
--       confirm service role can UPDATE processing_jobs directly — if not,
--       consider switching to SECURITY DEFINER but only after auditing why).
--   [ ] The companion CONCURRENTLY index migration (074) will be run separately
--       and outside any transaction wrapper.
--
-- This migration is transactional and fast (no large data movement).
-- New columns are nullable OR have a NOT NULL DEFAULT, so existing rows are
-- not affected and no backfill is required.
--
-- ROLLBACK:
--   ALTER TABLE processing_jobs DROP COLUMN IF EXISTS client_id;
--   ALTER TABLE processing_jobs DROP COLUMN IF EXISTS parameters;
--   ALTER TABLE processing_jobs DROP COLUMN IF EXISTS current_stage;
--   DROP FUNCTION IF EXISTS increment_job_progress(UUID, INT, INT, TEXT);
--   (The CONCURRENTLY index from 074 must be rolled back via 074's rollback.)
-- ============================================================================

-- ── 1. Columns ─────────────────────────────────────────────────────────────

-- client_id: required by reembed (per-client scope), NULL acceptable for
-- legacy extraction/enrichment rows that predate this column.
ALTER TABLE processing_jobs
  ADD COLUMN IF NOT EXISTS client_id UUID REFERENCES clients(id);

-- parameters: stores reembed-specific args (tables list, limit, etc.).
-- NOT NULL DEFAULT '{}' so existing rows get an empty object without backfill
-- and no caller has to handle a null/missing field.
ALTER TABLE processing_jobs
  ADD COLUMN IF NOT EXISTS parameters JSONB NOT NULL DEFAULT '{}'::jsonb;

-- current_stage: free-form short string for UI display
-- (e.g. 'embedding_emails', 'recreating_indexes'). NULL = no stage reported.
ALTER TABLE processing_jobs
  ADD COLUMN IF NOT EXISTS current_stage TEXT;

COMMENT ON COLUMN processing_jobs.client_id IS
  'Owning client. NULL allowed for legacy extraction/enrichment jobs that predate this column.';
COMMENT ON COLUMN processing_jobs.parameters IS
  'Job-type-specific input parameters as JSON (e.g. {tables: [...], limit: N} for reembed).';
COMMENT ON COLUMN processing_jobs.current_stage IS
  'Free-form stage indicator for UI display (e.g. embedding_emails, recreating_indexes).';

-- Supporting btree index for "active job for client" lookups by the helper.
-- This is a regular btree (not partial unique — that one is in migration 074).
CREATE INDEX IF NOT EXISTS idx_processing_jobs_client_type_status
  ON processing_jobs(client_id, job_type, status);

-- ── 2. Atomic progress increment RPC ───────────────────────────────────────
--
-- Purpose-built, typed RPC for atomic counter updates.
-- This is intentionally narrow: it accepts only typed scalars (UUID, INT, TEXT),
-- never SQL fragments. This is the key distinction from exec_sql / exec_sql_extended:
-- a constrained operation, not arbitrary DDL execution.
--
-- SECURITY INVOKER (default — no clause specified) means the function runs with
-- the caller's privileges. The service role must already have UPDATE privileges
-- on processing_jobs for this to work. If the caller cannot UPDATE
-- processing_jobs directly, this RPC will fail too — by design. Do NOT
-- escalate to SECURITY DEFINER without auditing why the caller lacks the grant.
--
-- DO NOT extend this function to accept additional query fragments, dynamic
-- column names, or anything that could turn it into a mini-exec_sql.

CREATE OR REPLACE FUNCTION increment_job_progress(
    p_job_id UUID,
    p_delta_processed INT DEFAULT 0,
    p_delta_failed INT DEFAULT 0,
    p_stage TEXT DEFAULT NULL
) RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE processing_jobs
    SET
        processed_records = COALESCE(processed_records, 0) + p_delta_processed,
        failed_records    = COALESCE(failed_records, 0)    + p_delta_failed,
        current_stage     = COALESCE(p_stage, current_stage)
    WHERE id = p_job_id;
END;
$$;

-- Admin-only RPC. Reembed is gated on require_role('admin') in the router;
-- only the service role calls this from the server. Do NOT grant to anon
-- or authenticated roles.
GRANT EXECUTE ON FUNCTION increment_job_progress(UUID, INT, INT, TEXT) TO service_role;

COMMENT ON FUNCTION increment_job_progress(UUID, INT, INT, TEXT) IS
  'Atomic progress counter increment for processing_jobs. Used by reembed worker. '
  'Typed parameters only — never accepts SQL fragments. SECURITY INVOKER by default.';
