-- ============================================================================
-- Sprint 2 Migration 005: Fix Analytics Tables Schema
-- ============================================================================
-- Purpose: Update email_response_metrics table to match Phase 4 services
-- Run After: sprint2_migration_004_contact_classification.sql
-- Duration: ~2 minutes
-- ============================================================================

-- PART 1: Drop and recreate email_response_metrics with correct schema
-- ============================================================================

-- Drop existing table (safe since Phase 4 just started)
DROP TABLE IF EXISTS email_response_metrics CASCADE;

-- Create email_response_metrics with schema matching response_time_tracker.py
CREATE TABLE email_response_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Email pair references
    email_id UUID NOT NULL REFERENCES emails(id) ON DELETE CASCADE,
    responding_to_email_id UUID NOT NULL REFERENCES emails(id) ON DELETE CASCADE,

    -- Contact/Company references (denormalized for performance)
    responder_contact_id UUID REFERENCES customer_contacts(id) ON DELETE SET NULL,
    responder_company_id UUID REFERENCES customer_companies(id) ON DELETE SET NULL,

    -- Response time metrics
    response_time_seconds INTEGER NOT NULL,
    is_auto_reply BOOLEAN NOT NULL DEFAULT FALSE,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT unique_email_response UNIQUE (email_id),
    CONSTRAINT positive_response_time CHECK (response_time_seconds > 0)
);

-- Create indexes for performance
CREATE INDEX idx_email_response_metrics_email_id ON email_response_metrics(email_id);
CREATE INDEX idx_email_response_metrics_responding_to ON email_response_metrics(responding_to_email_id);
CREATE INDEX idx_email_response_metrics_responder_contact ON email_response_metrics(responder_contact_id);
CREATE INDEX idx_email_response_metrics_responder_company ON email_response_metrics(responder_company_id);
CREATE INDEX idx_email_response_metrics_is_auto_reply ON email_response_metrics(is_auto_reply);

-- Add RLS (Row Level Security)
ALTER TABLE email_response_metrics ENABLE ROW LEVEL SECURITY;

-- RLS Policy: Users can only access metrics for their client's emails
CREATE POLICY email_response_metrics_client_isolation ON email_response_metrics
    FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM emails e
            JOIN mailboxes m ON e.mailbox_id = m.id
            WHERE e.id = email_response_metrics.email_id
              AND m.client_id = (current_setting('app.current_client_id', TRUE))::UUID
        )
    );

-- Grant permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON email_response_metrics TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON email_response_metrics TO service_role;

DO $$
BEGIN
    RAISE NOTICE '✅ email_response_metrics table recreated with correct schema';
END $$;

-- ============================================================================
-- PART 2: Verify table structure
-- ============================================================================

DO $$
DECLARE
    v_column_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_column_count
    FROM information_schema.columns
    WHERE table_name = 'email_response_metrics'
      AND column_name IN ('email_id', 'responding_to_email_id', 'is_auto_reply',
                         'responder_contact_id', 'response_time_seconds');

    IF v_column_count = 5 THEN
        RAISE NOTICE '✅ All required columns present in email_response_metrics';
    ELSE
        RAISE WARNING '⚠️ Missing columns in email_response_metrics (found: %)', v_column_count;
    END IF;
END $$;

-- ============================================================================
-- PART 3: Verification Queries
-- ============================================================================

-- Check table structure
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'email_response_metrics'
ORDER BY ordinal_position;

-- Check indexes
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'email_response_metrics';

-- ============================================================================
-- Migration 005 Complete
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE '====================================';
    RAISE NOTICE '✅ Migration 005 completed successfully';
    RAISE NOTICE '====================================';
    RAISE NOTICE 'email_response_metrics schema updated';
    RAISE NOTICE 'Ready for Phase 4 analytics pipeline';
    RAISE NOTICE '====================================';
END $$;
