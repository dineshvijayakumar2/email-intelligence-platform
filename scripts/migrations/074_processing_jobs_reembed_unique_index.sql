-- ============================================================================
-- Migration 074: Partial unique index for reembed single-flight enforcement
-- ============================================================================
--
-- ⚠️  REQUIRES HUMAN REVIEW BEFORE EXECUTION.
-- ⚠️  MUST RUN OUTSIDE A TRANSACTION (CREATE INDEX CONCURRENTLY).
--
-- Reviewer checklist:
--   [ ] This file MUST NOT be executed inside a transaction. If the migration
--       framework wraps every file in BEGIN/COMMIT, run this manually via
--       psql or via the Python autocommit pattern in scripts/db/.
--   [ ] Migration 073 has been applied first (this depends on the client_id
--       column added there).
--   [ ] No reembed jobs are currently in 'pending' or 'running' status that
--       would violate the constraint. Check with:
--         SELECT client_id, COUNT(*) FROM processing_jobs
--         WHERE job_type = 'reembed' AND status IN ('pending', 'running')
--         GROUP BY client_id HAVING COUNT(*) > 1;
--       If any group has count > 1, resolve those before running this.
--
-- This index is the single-flight enforcement mechanism for reembed:
--   - At most one (client_id) row can exist with status IN ('pending','running')
--     AND job_type = 'reembed'.
--   - A second concurrent INSERT for the same client gets unique_violation (23505),
--     which the application catches and translates to HTTP 409.
--
-- NOTE: The partial unique index treats NULL client_id rows as distinct, so this
-- does NOT prevent multiple jobs with NULL client_id. The reembed_job_state
-- helper rejects null client_id at the application layer as a defense-in-depth
-- guard; reembed jobs MUST have a non-null client_id.
--
-- ROLLBACK:
--   DROP INDEX CONCURRENTLY IF EXISTS uq_processing_jobs_one_active_reembed_per_client;
-- ============================================================================

CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS
  uq_processing_jobs_one_active_reembed_per_client
ON processing_jobs(client_id)
WHERE status IN ('pending', 'running') AND job_type = 'reembed';

COMMENT ON INDEX uq_processing_jobs_one_active_reembed_per_client IS
  'Single-flight: at most one active (pending|running) reembed job per client. '
  'A second concurrent INSERT raises unique_violation (SQLSTATE 23505), caught '
  'by the application and translated to HTTP 409 with the existing job_id.';
