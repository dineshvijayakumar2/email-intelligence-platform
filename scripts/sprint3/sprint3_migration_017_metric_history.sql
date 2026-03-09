-- ============================================================================
-- Migration 017: Metric Versioning & History
-- ============================================================================
-- Creates metric_history table to store historical engagement scores and their
-- component factor scores.  Adds scoring_version to contacts/companies so we
-- can track which algorithm version produced the current score.
--
-- Run After: sprint3_migration_016_business_hours.sql
-- Duration: < 5 seconds
-- ============================================================================

-- 1. metric_history — append-only log of engagement scores
CREATE TABLE IF NOT EXISTS metric_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_id UUID NOT NULL,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('contact', 'company')),
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,

    -- Overall score
    engagement_score INTEGER NOT NULL,
    scoring_version INTEGER NOT NULL DEFAULT 1,

    -- Factor scores (0-100 each, stored for full transparency)
    response_time_score DECIMAL(5,2),
    thread_completeness_score DECIMAL(5,2),
    initiation_balance_score DECIMAL(5,2),
    reply_rate_score DECIMAL(5,2),
    frequency_score DECIMAL(5,2),
    recency_score DECIMAL(5,2),
    decision_maker_bonus DECIMAL(5,2),
    seniority_bonus DECIMAL(5,2),

    -- Context snapshot — key inputs at time of calculation
    emails_per_month_avg DECIMAL(8,2),
    avg_response_time_seconds INTEGER,
    reply_rate DECIMAL(3,2),

    calculated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_metric_history_entity
    ON metric_history(entity_id, entity_type, calculated_at DESC);
CREATE INDEX IF NOT EXISTS idx_metric_history_client
    ON metric_history(client_id, calculated_at DESC);

-- 2. Add scoring_version to contacts and companies
ALTER TABLE customer_contacts
ADD COLUMN IF NOT EXISTS scoring_version INTEGER NOT NULL DEFAULT 1;

ALTER TABLE customer_companies
ADD COLUMN IF NOT EXISTS scoring_version INTEGER NOT NULL DEFAULT 1;

DO $$ BEGIN RAISE NOTICE 'Migration 017 complete: metric_history table created, scoring_version added to contacts/companies'; END $$;
