-- ============================================================================
-- Migration 015: Add digest_type to ai_daily_digests
-- ============================================================================
-- Adds support for weekly digests alongside daily digests.
-- The unique constraint is updated to (mailbox_id, digest_date, digest_type)
-- so both a daily and weekly digest can exist for the same date.
--
-- Run After: sprint3_migration_014_add_skipped_status.sql
-- Duration: < 5 seconds
-- ============================================================================

-- Add digest_type column (default 'daily' for backward compatibility)
ALTER TABLE ai_daily_digests
ADD COLUMN IF NOT EXISTS digest_type TEXT NOT NULL DEFAULT 'daily'
CHECK (digest_type IN ('daily', 'weekly'));

-- Drop old unique constraint and create new one that includes digest_type
ALTER TABLE ai_daily_digests DROP CONSTRAINT IF EXISTS ai_daily_digests_mailbox_id_digest_date_key;
ALTER TABLE ai_daily_digests ADD CONSTRAINT ai_daily_digests_mailbox_date_type_key
    UNIQUE (mailbox_id, digest_date, digest_type);

-- Update index to include digest_type
DROP INDEX IF EXISTS idx_digest_mailbox_date;
CREATE INDEX IF NOT EXISTS idx_digest_mailbox_date_type
    ON ai_daily_digests(mailbox_id, digest_date DESC, digest_type);

DO $$ BEGIN RAISE NOTICE 'Migration 015 complete: digest_type column added to ai_daily_digests'; END $$;
