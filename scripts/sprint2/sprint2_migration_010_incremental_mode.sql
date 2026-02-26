-- ============================================================================
-- Sprint 2 Migration 010: Incremental Extraction Mode
-- ============================================================================
-- Purpose: Add support for incremental extraction (process only recent emails)
-- Run After: sprint2_migration_009_comm_pattern_calcs.sql
-- Duration: <1 minute
-- Dependencies: None
-- ============================================================================

BEGIN;

-- ============================================================================
-- PART 1: Add incremental tracking to mailboxes table
-- ============================================================================

-- Add columns for tracking extraction mode and scheduling
ALTER TABLE mailboxes
ADD COLUMN IF NOT EXISTS last_extraction_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS extraction_mode VARCHAR(20) DEFAULT 'full' CHECK (extraction_mode IN ('full', 'incremental')),
ADD COLUMN IF NOT EXISTS auto_extract_enabled BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS incremental_lookback_days INTEGER DEFAULT 7 CHECK (incremental_lookback_days >= 1 AND incremental_lookback_days <= 365);

-- Add column comments for documentation
COMMENT ON COLUMN mailboxes.last_extraction_at IS 'Timestamp of last successful extraction completion';
COMMENT ON COLUMN mailboxes.extraction_mode IS 'Extraction mode: full (all emails) or incremental (recent only)';
COMMENT ON COLUMN mailboxes.auto_extract_enabled IS 'Enable automatic scheduled extraction (future feature)';
COMMENT ON COLUMN mailboxes.incremental_lookback_days IS 'Days to look back for incremental mode (default 7, range 1-365)';

-- ============================================================================
-- PART 2: Add mode tracking to extraction_jobs table
-- ============================================================================

-- Add columns for tracking extraction scope
ALTER TABLE extraction_jobs
ADD COLUMN IF NOT EXISTS extraction_mode VARCHAR(20) DEFAULT 'full',
ADD COLUMN IF NOT EXISTS emails_in_scope INTEGER,
ADD COLUMN IF NOT EXISTS date_range_start TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS date_range_end TIMESTAMPTZ;

-- Add column comments
COMMENT ON COLUMN extraction_jobs.extraction_mode IS 'Mode used for this job: full or incremental';
COMMENT ON COLUMN extraction_jobs.emails_in_scope IS 'Number of emails included in this extraction scope';
COMMENT ON COLUMN extraction_jobs.date_range_start IS 'Start date for incremental extraction (NULL for full)';
COMMENT ON COLUMN extraction_jobs.date_range_end IS 'End date for incremental extraction (NULL for full)';

-- ============================================================================
-- PART 3: Create performance indexes for incremental queries
-- ============================================================================

-- Index for fast incremental email queries (mailbox + date range + status)
CREATE INDEX IF NOT EXISTS idx_emails_mailbox_sent_date
ON emails(mailbox_id, sent_date DESC)
WHERE processing_status = 'success';

-- Index for fast date-based queries regardless of mailbox
CREATE INDEX IF NOT EXISTS idx_emails_processing_status_sent_date
ON emails(processing_status, sent_date DESC)
WHERE processing_status = 'success';

-- Index for fast job lookups by completion time
CREATE INDEX IF NOT EXISTS idx_extraction_jobs_completed_at
ON extraction_jobs(client_id, completed_at DESC)
WHERE status = 'completed';

-- ============================================================================
-- PART 4: Backfill last_extraction_at for existing mailboxes
-- ============================================================================

-- Update mailboxes with their most recent successful extraction timestamp
UPDATE mailboxes m
SET last_extraction_at = (
    SELECT MAX(ej.completed_at)
    FROM extraction_jobs ej
    WHERE ej.mailbox_id = m.id
      AND ej.status = 'completed'
      AND ej.completed_at IS NOT NULL
)
WHERE EXISTS (
    SELECT 1
    FROM extraction_jobs ej
    WHERE ej.mailbox_id = m.id
      AND ej.status = 'completed'
      AND ej.completed_at IS NOT NULL
);

-- ============================================================================
-- PART 5: Migration completion report
-- ============================================================================

DO $$
DECLARE
    mailbox_count INTEGER;
    backfilled_count INTEGER;
    index_count INTEGER;
BEGIN
    -- Count mailboxes
    SELECT COUNT(*) INTO mailbox_count FROM mailboxes;

    -- Count mailboxes with extraction history
    SELECT COUNT(*) INTO backfilled_count
    FROM mailboxes
    WHERE last_extraction_at IS NOT NULL;

    -- Count new indexes
    SELECT COUNT(*) INTO index_count
    FROM pg_indexes
    WHERE indexname IN (
        'idx_emails_mailbox_sent_date',
        'idx_emails_processing_status_sent_date',
        'idx_extraction_jobs_completed_at'
    );

    RAISE NOTICE '';
    RAISE NOTICE '====================================================================';
    RAISE NOTICE 'Migration 010: Incremental Extraction Mode - COMPLETED';
    RAISE NOTICE '====================================================================';
    RAISE NOTICE '';
    RAISE NOTICE 'Schema Changes:';
    RAISE NOTICE '  ✓ Added 4 columns to mailboxes table';
    RAISE NOTICE '  ✓ Added 4 columns to extraction_jobs table';
    RAISE NOTICE '  ✓ Created % performance indexes', index_count;
    RAISE NOTICE '';
    RAISE NOTICE 'Data Migration:';
    RAISE NOTICE '  ✓ Total mailboxes: %', mailbox_count;
    RAISE NOTICE '  ✓ Backfilled last_extraction_at: %', backfilled_count;
    RAISE NOTICE '';
    RAISE NOTICE 'Features Enabled:';
    RAISE NOTICE '  ✓ Incremental extraction mode (process only recent emails)';
    RAISE NOTICE '  ✓ Configurable lookback days (default: 7 days)';
    RAISE NOTICE '  ✓ Extraction mode tracking per job';
    RAISE NOTICE '  ✓ Date range filtering for incremental jobs';
    RAISE NOTICE '';
    RAISE NOTICE 'Usage:';
    RAISE NOTICE '  • Set mailbox extraction_mode to ''incremental'' for partial extraction';
    RAISE NOTICE '  • Adjust incremental_lookback_days (1-365) for time window';
    RAISE NOTICE '  • API will track date ranges for each incremental job';
    RAISE NOTICE '  • last_extraction_at updates on successful completion';
    RAISE NOTICE '';
    RAISE NOTICE 'Next Steps:';
    RAISE NOTICE '  1. Update ExtractionOrchestrator to support mode parameter';
    RAISE NOTICE '  2. Update analytics API to accept mode in job creation';
    RAISE NOTICE '  3. Test incremental mode on production-size dataset';
    RAISE NOTICE '';
    RAISE NOTICE '====================================================================';
    RAISE NOTICE '';
END $$;

COMMIT;

-- ============================================================================
-- Migration 010 Complete
-- ============================================================================

-- Verification queries (commented out - run manually if needed)
-- SELECT
--     COUNT(*) as total_mailboxes,
--     COUNT(last_extraction_at) as with_extraction_history,
--     COUNT(*) FILTER (WHERE extraction_mode = 'full') as full_mode,
--     COUNT(*) FILTER (WHERE extraction_mode = 'incremental') as incremental_mode
-- FROM mailboxes;

-- SELECT
--     extraction_mode,
--     COUNT(*) as job_count,
--     AVG(emails_in_scope) as avg_emails_processed,
--     MIN(date_range_start) as earliest_range,
--     MAX(date_range_end) as latest_range
-- FROM extraction_jobs
-- WHERE extraction_mode IS NOT NULL
-- GROUP BY extraction_mode;
