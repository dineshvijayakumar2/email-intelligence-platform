-- ============================================================================
-- Sprint 3 Migration 013: AI Intelligence Layer
-- ============================================================================
-- Purpose: Create all tables for the AI semantic intelligence system
--
-- Tables:
--   1. ai_email_intelligence   — Per-email classification + entities + buckets + feedback
--   2. ai_business_entities    — Aggregate entity tracking (competitors, products, people)
--   3. ai_relationship_summaries — Company-level AI summaries with bucket context
--   4. ai_usage_log            — AI API cost tracking per operation/model/mailbox
--   5. ai_daily_digests        — Cached daily briefings with bucket summaries
--
-- Run After: sprint2_migration_012_backfill_scoring_fields.sql
-- Duration: < 30 seconds
-- ============================================================================


-- =========================================================================
-- TABLE 1: ai_email_intelligence
-- =========================================================================
-- Combined classification + entity extraction + action buckets (ONE AI pass)
-- Production additions: processing_status, versioning, raw_ai_response, structured feedback

CREATE TABLE IF NOT EXISTS ai_email_intelligence (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email_id UUID REFERENCES emails(id) ON DELETE CASCADE,
    mailbox_id UUID REFERENCES mailboxes(id) ON DELETE CASCADE,
    client_id UUID REFERENCES clients(id) ON DELETE SET NULL,

    -- === CLASSIFICATION ===
    intent TEXT CHECK (intent IN (
        'action_required', 'fyi_update', 'meeting_scheduling',
        'question', 'complaint', 'positive_feedback',
        'pricing_inquiry', 'feature_request', 'expansion_signal',
        'churn_risk', 'follow_up', 'introduction', 'other'
    )),
    urgency TEXT CHECK (urgency IN ('critical', 'high', 'medium', 'low', 'none')),
    sentiment TEXT CHECK (sentiment IN (
        'very_positive', 'positive', 'neutral', 'negative', 'very_negative'
    )),
    sentiment_score DECIMAL(3,2),        -- -1.0 to 1.0
    summary TEXT,                         -- 1-2 sentence summary
    suggested_action TEXT,                -- What the AM should do
    key_topics TEXT[],                    -- Themes
    confidence DECIMAL(3,2),              -- 0.0-1.0
    justification TEXT,                   -- WHY this classification (from AI)

    -- === MULTI-AXIS CLASSIFICATION (v3.2) ===
    action_type TEXT,                     -- respond_to_inquiry, provide_quote, schedule_meeting,
                                          -- escalate_internally, send_follow_up, resolve_issue,
                                          -- acknowledge_receipt, no_action, delegate, prepare_document
    business_signal TEXT,                 -- buying_intent, renewal_intent, expansion_interest,
                                          -- churn_signal, competitive_evaluation, budget_discussion,
                                          -- escalation, positive_feedback, negative_feedback,
                                          -- contract_activity, neutral
    thread_role TEXT,                     -- initial, reply, forward, auto_reply, cc_addition, internal

    -- === ENTITY EXTRACTION (same API call, nested in AI response) ===
    competitors_mentioned TEXT[],
    products_mentioned TEXT[],
    budget_signals JSONB,                -- {amount, timeframe, context}
    buying_signals TEXT[],
    people_mentioned JSONB,              -- [{name, role, context}]
    dates_mentioned JSONB,               -- [{date, context}]
    action_items_extracted TEXT[],

    -- === BUSINESS SIGNAL FLAGS (computed in Python post-processing) ===
    has_budget_signal BOOLEAN DEFAULT FALSE,
    has_buying_signal BOOLEAN DEFAULT FALSE,
    has_competitor_mention BOOLEAN DEFAULT FALSE,
    has_deadline BOOLEAN DEFAULT FALSE,
    business_signal_score INTEGER DEFAULT 0,  -- 0-100

    -- === ACTION BUCKETS (derived by Python engine, stored for fast queries) ===
    action_buckets JSONB DEFAULT '[]',   -- [{bucket, confidence, justification}]
    primary_bucket TEXT,                  -- Highest-confidence bucket for filtering/sorting

    -- === HUMAN FEEDBACK (structured — know what was wrong) ===
    human_feedback TEXT CHECK (human_feedback IN ('correct', 'incorrect')),
    feedback_field TEXT,                  -- Which field was wrong: 'intent', 'bucket', 'sentiment', 'urgency'
    human_override_intent TEXT,
    human_override_bucket TEXT,
    human_override_sentiment TEXT,
    feedback_note TEXT,                   -- Free-text user explanation
    feedback_at TIMESTAMPTZ,
    feedback_by UUID,

    -- === PROCESSING METADATA ===
    model_used TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    processing_time_ms INTEGER,

    -- === IDEMPOTENT PROCESSING (safe re-runs) ===
    processing_status TEXT DEFAULT 'pending' CHECK (processing_status IN (
        'pending', 'processing', 'completed', 'failed', 'skipped'
    )),
    processed_at TIMESTAMPTZ,
    error_message TEXT,                   -- Why it failed (if failed)

    -- === VERSION TRACKING (full traceability) ===
    prompt_version TEXT,                  -- e.g., 'v1.0' — know which prompt produced this
    scoring_version TEXT,                 -- business_signal_score algorithm version
    bucket_engine_version TEXT,           -- bucket derivation logic version

    -- === RAW AI OUTPUT (debugging + compliance) ===
    raw_ai_response JSONB,               -- Full Claude response, never modified

    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(email_id)
);

-- Classification indexes
CREATE INDEX IF NOT EXISTS idx_ai_intel_mailbox ON ai_email_intelligence(mailbox_id);
CREATE INDEX IF NOT EXISTS idx_ai_intel_client ON ai_email_intelligence(client_id);
CREATE INDEX IF NOT EXISTS idx_ai_intel_intent ON ai_email_intelligence(intent);
CREATE INDEX IF NOT EXISTS idx_ai_intel_urgency ON ai_email_intelligence(urgency)
    WHERE urgency IN ('critical', 'high');
CREATE INDEX IF NOT EXISTS idx_ai_intel_sentiment ON ai_email_intelligence(sentiment);
CREATE INDEX IF NOT EXISTS idx_ai_intel_created ON ai_email_intelligence(created_at DESC);

-- Entity/signal indexes
CREATE INDEX IF NOT EXISTS idx_ai_intel_budget ON ai_email_intelligence(has_budget_signal)
    WHERE has_budget_signal = TRUE;
CREATE INDEX IF NOT EXISTS idx_ai_intel_buying ON ai_email_intelligence(has_buying_signal)
    WHERE has_buying_signal = TRUE;
CREATE INDEX IF NOT EXISTS idx_ai_intel_competitor ON ai_email_intelligence(has_competitor_mention)
    WHERE has_competitor_mention = TRUE;
CREATE INDEX IF NOT EXISTS idx_ai_intel_deadline ON ai_email_intelligence(has_deadline)
    WHERE has_deadline = TRUE;
CREATE INDEX IF NOT EXISTS idx_ai_intel_signal_score ON ai_email_intelligence(business_signal_score DESC)
    WHERE business_signal_score > 0;

-- Action bucket indexes
CREATE INDEX IF NOT EXISTS idx_ai_intel_primary_bucket ON ai_email_intelligence(primary_bucket)
    WHERE primary_bucket IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ai_intel_feedback ON ai_email_intelligence(human_feedback)
    WHERE human_feedback IS NOT NULL;

-- Multi-axis classification indexes
CREATE INDEX IF NOT EXISTS idx_ai_intel_business_signal ON ai_email_intelligence(business_signal)
    WHERE business_signal IS NOT NULL AND business_signal != 'neutral';
CREATE INDEX IF NOT EXISTS idx_ai_intel_action_type ON ai_email_intelligence(action_type)
    WHERE action_type IS NOT NULL AND action_type != 'no_action';
CREATE INDEX IF NOT EXISTS idx_ai_intel_thread_role ON ai_email_intelligence(thread_role)
    WHERE thread_role = 'auto_reply';

-- Processing status index (for re-processing failed items)
CREATE INDEX IF NOT EXISTS idx_ai_intel_processing_status ON ai_email_intelligence(processing_status)
    WHERE processing_status IN ('pending', 'failed');

GRANT SELECT, INSERT, UPDATE, DELETE ON ai_email_intelligence TO anon, authenticated;


-- =========================================================================
-- TABLE 2: ai_business_entities
-- =========================================================================
-- Aggregate entity tracking across emails (competitors, products, people)

CREATE TABLE IF NOT EXISTS ai_business_entities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    mailbox_id UUID REFERENCES mailboxes(id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL CHECK (entity_type IN (
        'competitor', 'product', 'person', 'company', 'technology'
    )),
    entity_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    mention_count INTEGER DEFAULT 1,
    first_seen_at TIMESTAMPTZ,
    last_seen_at TIMESTAMPTZ,
    associated_company_ids UUID[],
    context_snippets JSONB DEFAULT '[]',   -- Last 10 context strings
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(client_id, entity_type, normalized_name)
);

CREATE INDEX IF NOT EXISTS idx_ai_entities_client ON ai_business_entities(client_id);
CREATE INDEX IF NOT EXISTS idx_ai_entities_type ON ai_business_entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_ai_entities_mentions ON ai_business_entities(mention_count DESC);

-- Only create trigger if function exists (Sprint 2 should have created it)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'update_updated_at_column') THEN
        IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_ai_entities_updated_at') THEN
            CREATE TRIGGER update_ai_entities_updated_at BEFORE UPDATE
                ON ai_business_entities FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        END IF;
    END IF;
END $$;

GRANT SELECT, INSERT, UPDATE, DELETE ON ai_business_entities TO anon, authenticated;


-- =========================================================================
-- TABLE 3: ai_relationship_summaries
-- =========================================================================
-- Company-level AI summaries with bucket context

CREATE TABLE IF NOT EXISTS ai_relationship_summaries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID REFERENCES customer_companies(id) ON DELETE CASCADE,
    client_id UUID REFERENCES clients(id) ON DELETE SET NULL,
    mailbox_id UUID REFERENCES mailboxes(id) ON DELETE CASCADE,

    -- Summary content
    summary TEXT NOT NULL,
    key_themes TEXT[],
    risk_factors TEXT[],
    opportunities TEXT[],
    recommended_actions TEXT[],
    competitors_in_play TEXT[],
    active_buying_signals TEXT[],
    upcoming_deadlines JSONB,
    active_buckets JSONB DEFAULT '[]',   -- [{bucket, count, example}]

    -- Scope
    emails_analyzed INTEGER,
    date_range_start TIMESTAMPTZ,
    date_range_end TIMESTAMPTZ,

    -- Processing metadata
    model_used TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    prompt_version TEXT,
    raw_ai_response JSONB,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ai_rel_company ON ai_relationship_summaries(company_id);
CREATE INDEX IF NOT EXISTS idx_ai_rel_client ON ai_relationship_summaries(client_id);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'update_updated_at_column') THEN
        IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_ai_rel_summaries_updated_at') THEN
            CREATE TRIGGER update_ai_rel_summaries_updated_at BEFORE UPDATE
                ON ai_relationship_summaries FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        END IF;
    END IF;
END $$;

GRANT SELECT, INSERT, UPDATE, DELETE ON ai_relationship_summaries TO anon, authenticated;


-- =========================================================================
-- TABLE 4: ai_usage_log
-- =========================================================================
-- AI API cost tracking per operation/model/mailbox

CREATE TABLE IF NOT EXISTS ai_usage_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    operation TEXT NOT NULL,              -- 'email_intelligence', 'digest', 'relationship_summary'
    model TEXT NOT NULL,                  -- 'claude-haiku-4-5-20251001', 'claude-sonnet-4-6' etc.
    mailbox_id UUID REFERENCES mailboxes(id) ON DELETE SET NULL,
    client_id UUID REFERENCES clients(id) ON DELETE SET NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    estimated_cost_usd DECIMAL(10,6),
    processing_time_ms INTEGER,
    batch_size INTEGER DEFAULT 1,

    -- Error tracking
    error_type TEXT,                      -- 'json_parse', 'validation', 'api_timeout', 'rate_limit'
    retry_count INTEGER DEFAULT 0,
    success BOOLEAN DEFAULT TRUE,
    prompt_version TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ai_usage_date ON ai_usage_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_usage_operation ON ai_usage_log(operation);
CREATE INDEX IF NOT EXISTS idx_ai_usage_client ON ai_usage_log(client_id);
CREATE INDEX IF NOT EXISTS idx_ai_usage_success ON ai_usage_log(success)
    WHERE success = FALSE;

GRANT SELECT, INSERT ON ai_usage_log TO anon, authenticated;


-- =========================================================================
-- TABLE 5: ai_daily_digests
-- =========================================================================
-- Cached daily briefings with bucket summaries

CREATE TABLE IF NOT EXISTS ai_daily_digests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    mailbox_id UUID REFERENCES mailboxes(id) ON DELETE CASCADE,
    client_id UUID REFERENCES clients(id) ON DELETE SET NULL,
    digest_date DATE NOT NULL,

    -- Digest content
    summary TEXT NOT NULL,
    action_items JSONB DEFAULT '[]',
    highlights JSONB DEFAULT '[]',
    stats JSONB DEFAULT '{}',
    bucket_summary JSONB DEFAULT '{}',   -- {buying_signal: 2, churn_risk: 1, ...}
    emails_analyzed INTEGER,

    -- Processing metadata
    model_used TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    prompt_version TEXT,
    raw_ai_response JSONB,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(mailbox_id, digest_date)
);

CREATE INDEX IF NOT EXISTS idx_digest_mailbox_date ON ai_daily_digests(mailbox_id, digest_date DESC);

GRANT SELECT, INSERT, UPDATE, DELETE ON ai_daily_digests TO anon, authenticated;


-- =========================================================================
-- DONE
-- =========================================================================
DO $$ BEGIN RAISE NOTICE 'Migration 013 complete: AI Intelligence Layer — 5 tables created'; END $$;
