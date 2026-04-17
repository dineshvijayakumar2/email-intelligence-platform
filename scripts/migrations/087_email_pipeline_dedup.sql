-- Migration 087: Email pipeline single-flight dedup per mailbox
-- Prevents two concurrent pipeline runs for the same mailbox.
--
-- NOTE: CREATE INDEX CONCURRENTLY cannot run inside a transaction block.
-- On Railway SQL runner, run this statement directly (not wrapped in BEGIN/COMMIT).

CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS uq_email_pipeline_per_mailbox
ON processing_jobs(mailbox_id)
WHERE job_type = 'email_pipeline' AND status IN ('pending', 'running');

COMMENT ON INDEX uq_email_pipeline_per_mailbox IS
  'Single-flight: only one active email_pipeline job per mailbox. Factory raises JobAlreadyActive on collision.';
