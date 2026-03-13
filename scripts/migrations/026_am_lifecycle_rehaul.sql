-- ============================================================================
-- Migration 026: AM Efficiency + Customer Lifecycle Rehaul
-- ============================================================================
-- Purpose: Replace old vague bucket signals with precise AM-centric signals.
--          Add customer lifecycle tiers, timezone config, and AM identity
--          resolution from mailbox → user.
--
-- Changes:
--   1. clients              — add timezone (default AEST)
--   2. ai_email_intelligence — add customer_lifecycle_tier, drop has_buying_signal,
--                              rename primary_bucket index
--   3. relationship_context_cache — add lifecycle_tier, am_user_id, am_name,
--                                    primary_mailbox_id
--   4. am_performance_snapshots   — add response_rate, after_hours_pct,
--                                    mailbox_id, user_id
-- ============================================================================

-- 1. Timezone per client (same tz applies to all mailboxes of that client)
ALTER TABLE clients
    ADD COLUMN IF NOT EXISTS timezone TEXT NOT NULL DEFAULT 'Australia/Sydney';

-- 2a. Lifecycle tier on ai_email_intelligence (computed at analysis time)
ALTER TABLE ai_email_intelligence
    ADD COLUMN IF NOT EXISTS customer_lifecycle_tier TEXT
        CHECK (customer_lifecycle_tier IN (
            'prospect', 'new_customer', 'active_customer',
            'at_risk', 'dormant', 'champion'
        ));

-- 2b. Replace has_buying_signal (too vague) with has_response_urgency
--     We keep the column but repurpose the semantics via a new index name.
--     The old index is dropped and replaced so queries on urgency still fast.
ALTER TABLE ai_email_intelligence
    ADD COLUMN IF NOT EXISTS has_response_urgency BOOLEAN DEFAULT FALSE;

DROP INDEX IF EXISTS idx_ai_intel_buying;
CREATE INDEX IF NOT EXISTS idx_ai_intel_response_urgency
    ON ai_email_intelligence(has_response_urgency)
    WHERE has_response_urgency = TRUE;

CREATE INDEX IF NOT EXISTS idx_ai_intel_lifecycle_tier
    ON ai_email_intelligence(customer_lifecycle_tier)
    WHERE customer_lifecycle_tier IS NOT NULL;

-- 3. relationship_context_cache — AM identity + lifecycle tier
ALTER TABLE relationship_context_cache
    ADD COLUMN IF NOT EXISTS lifecycle_tier TEXT
        CHECK (lifecycle_tier IN (
            'prospect', 'new_customer', 'active_customer',
            'at_risk', 'dormant', 'champion'
        )),
    ADD COLUMN IF NOT EXISTS primary_mailbox_id UUID REFERENCES mailboxes(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS am_user_id UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS am_name TEXT;

CREATE INDEX IF NOT EXISTS idx_rel_cache_am ON relationship_context_cache(am_user_id)
    WHERE am_user_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_rel_cache_lifecycle ON relationship_context_cache(lifecycle_tier)
    WHERE lifecycle_tier IS NOT NULL;

-- 4. am_performance_snapshots — add response rate, after-hours pct, user linkage
ALTER TABLE am_performance_snapshots
    ADD COLUMN IF NOT EXISTS response_rate DECIMAL(5,2),
    ADD COLUMN IF NOT EXISTS after_hours_email_pct DECIMAL(5,2),
    ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS mailbox_ids JSONB DEFAULT '[]';

CREATE INDEX IF NOT EXISTS idx_am_perf_user ON am_performance_snapshots(user_id)
    WHERE user_id IS NOT NULL;
