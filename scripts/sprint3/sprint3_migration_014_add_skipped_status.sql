-- Sprint 3 Migration 014: Add 'skipped' processing status
-- Purpose: Allow pre-filtered automated/auto-reply emails to be marked as skipped
--          instead of wasting AI credits on them.
-- Date: 2026-03-01

-- Drop the old constraint and re-create with 'skipped' added
ALTER TABLE ai_email_intelligence
DROP CONSTRAINT IF EXISTS ai_email_intelligence_processing_status_check;

ALTER TABLE ai_email_intelligence
ADD CONSTRAINT ai_email_intelligence_processing_status_check
CHECK (processing_status IN ('pending', 'processing', 'completed', 'failed', 'skipped'));

-- Verify
DO $$
DECLARE
    cnt INT;
BEGIN
    SELECT COUNT(*) INTO cnt FROM information_schema.check_constraints
    WHERE constraint_name = 'ai_email_intelligence_processing_status_check';
    RAISE NOTICE 'Migration 014 complete: constraint updated (% found)', cnt;
END $$;
