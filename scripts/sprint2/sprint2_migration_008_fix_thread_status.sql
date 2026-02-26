-- ============================================================================
-- Sprint 2 Migration 008: Fix Thread Status Schema
-- ============================================================================
-- Purpose: Add missing columns that thread_tracker service needs
-- Run After: sprint2_migration_007_analytics_calculations.sql
-- Duration: <1 minute
-- ============================================================================

-- Add missing columns to thread_status table
ALTER TABLE thread_status ADD COLUMN IF NOT EXISTS last_email_id UUID REFERENCES emails(id) ON DELETE SET NULL;
ALTER TABLE thread_status ADD COLUMN IF NOT EXISTS last_email_date TIMESTAMPTZ;
ALTER TABLE thread_status ADD COLUMN IF NOT EXISTS last_sender_is_outbound BOOLEAN;
ALTER TABLE thread_status ADD COLUMN IF NOT EXISTS thread_depth INTEGER DEFAULT 0;
ALTER TABLE thread_status ADD COLUMN IF NOT EXISTS days_since_last_email INTEGER;
ALTER TABLE thread_status ADD COLUMN IF NOT EXISTS is_overdue BOOLEAN DEFAULT FALSE;
ALTER TABLE thread_status ADD COLUMN IF NOT EXISTS primary_contact_id UUID REFERENCES customer_contacts(id) ON DELETE SET NULL;
ALTER TABLE thread_status ADD COLUMN IF NOT EXISTS primary_company_id UUID REFERENCES customer_companies(id) ON DELETE SET NULL;

-- Create indexes for new columns
CREATE INDEX IF NOT EXISTS idx_thread_status_last_email ON thread_status(last_email_id);
CREATE INDEX IF NOT EXISTS idx_thread_status_primary_contact ON thread_status(primary_contact_id);
CREATE INDEX IF NOT EXISTS idx_thread_status_primary_company ON thread_status(primary_company_id);
CREATE INDEX IF NOT EXISTS idx_thread_status_is_overdue ON thread_status(is_overdue) WHERE is_overdue = TRUE;

DO $$
BEGIN
    RAISE NOTICE '✅ thread_status table updated with Phase 4 analytics columns';
END $$;

-- ============================================================================
-- Migration 008 Complete
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE '====================================';
    RAISE NOTICE '✅ Migration 008 completed successfully';
    RAISE NOTICE '====================================';
    RAISE NOTICE 'thread_status table ready for Phase 4';
    RAISE NOTICE '====================================';
END $$;
