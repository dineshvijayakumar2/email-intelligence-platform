-- ============================================================================
-- Migration 035: Intelligence Config + Capability Tags on QB Operations
-- ============================================================================
-- Purpose:
--   1. client_taxonomy_config — generic per-client JSON config store
--      (capability tags list, classifier rules, rush thresholds, etc.)
--   2. customer_intelligence_cache — generic per-company cache for any
--      computed intelligence profile (capability_profile, rush_profile, etc.)
--   3. ALTER qb_operations — add capability_tags JSONB + 5 boolean flags
--      (has_coating, has_sewing, has_outsource_component, am_rush, factory_rush)
--      + row_type TEXT
-- Run After: 032_qb_operations.sql, 034_product_intelligence.sql
-- ============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- 1. client_taxonomy_config
--    Generic JSON config store — one row per (client_id, config_type).
--    config_type examples:
--      'capability_tags'  — ordered list of {tag_id, name, color, description}
--      'classifier_rules' — list of {dept, op, machine, tag, flags, row_type}
--      'rush_settings'    — {am_rush_threshold, factory_rush_threshold, ...}
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS client_taxonomy_config (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id   UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    config_type TEXT NOT NULL,          -- e.g. 'capability_tags', 'classifier_rules', 'rush_settings'
    config_data JSONB NOT NULL DEFAULT '{}',
    version     INTEGER NOT NULL DEFAULT 1,
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(client_id, config_type)
);

CREATE INDEX IF NOT EXISTS idx_taxonomy_config_client
    ON client_taxonomy_config(client_id, config_type);

COMMENT ON TABLE client_taxonomy_config IS 'Generic per-client JSON configuration store for intelligence taxonomy (capability tags, classifier rules, rush settings). One row per (client, config_type). Editable via the Intelligence Config frontend.';
COMMENT ON COLUMN client_taxonomy_config.config_type IS 'Config namespace: capability_tags | classifier_rules | rush_settings';
COMMENT ON COLUMN client_taxonomy_config.version IS 'Incremented on each update — used to detect stale cached classifier in capability_classifier.py';


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. customer_intelligence_cache
--    Generic per-company computed profile cache. One row per (client, company, cache_type).
--    cache_type examples:
--      'capability_profile' — {tags: {tag_name: {count, revenue, last_date}}}
--      'rush_profile'       — {am_rush_count, factory_rush_count, ...}
--      'recommendations'    — cross_contact + related_product recs (replaces customer_recommendations)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS customer_intelligence_cache (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id   UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    company_id  UUID NOT NULL REFERENCES customer_companies(id) ON DELETE CASCADE,
    -- contact_id NULL = company-level profile; non-NULL = contact-level profile (Phase 2B)
    contact_id  UUID REFERENCES customer_contacts(id) ON DELETE CASCADE,
    cache_type  TEXT NOT NULL,          -- e.g. 'capability_profile', 'rush_profile'
    data        JSONB NOT NULL DEFAULT '{}',
    computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- If table was created in an earlier run without contact_id, add it now
ALTER TABLE customer_intelligence_cache
    ADD COLUMN IF NOT EXISTS contact_id UUID REFERENCES customer_contacts(id) ON DELETE CASCADE;

-- Drop old inline UNIQUE constraint if it exists from a previous run
DO $$ BEGIN
    ALTER TABLE customer_intelligence_cache
        DROP CONSTRAINT IF EXISTS customer_intelligence_cache_client_id_company_id_cache_type_key;
EXCEPTION WHEN others THEN NULL;
END $$;

-- Partial unique indexes: NULL != NULL in Postgres UNIQUE constraints,
-- so we use two partial indexes to enforce uniqueness correctly.
-- Company-level (contact_id IS NULL):
CREATE UNIQUE INDEX IF NOT EXISTS uq_intel_cache_company
    ON customer_intelligence_cache(client_id, company_id, cache_type)
    WHERE contact_id IS NULL;

-- Contact-level (contact_id IS NOT NULL):
CREATE UNIQUE INDEX IF NOT EXISTS uq_intel_cache_contact
    ON customer_intelligence_cache(client_id, company_id, contact_id, cache_type)
    WHERE contact_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_intelligence_cache_lookup
    ON customer_intelligence_cache(client_id, company_id, cache_type);

CREATE INDEX IF NOT EXISTS idx_intelligence_cache_type
    ON customer_intelligence_cache(client_id, cache_type, computed_at DESC);

COMMENT ON TABLE customer_intelligence_cache IS 'Generic computed intelligence cache. contact_id=NULL → company-level; contact_id set → contact-level (Phase 2B). TTL enforced in application code (24h). Upserted on recompute.';
COMMENT ON COLUMN customer_intelligence_cache.contact_id IS 'NULL for company-level profiles. Set for contact-level profiles (Phase 2B: per-contact capability tags, recency, value score).';
COMMENT ON COLUMN customer_intelligence_cache.cache_type IS 'Profile namespace: capability_profile | rush_profile | recommendations | contact_capability_profile';


-- ─────────────────────────────────────────────────────────────────────────────
-- 3. ALTER qb_operations — add intelligence columns
-- ─────────────────────────────────────────────────────────────────────────────

-- Capability tags (array of tag names matched by classifier)
ALTER TABLE qb_operations
    ADD COLUMN IF NOT EXISTS capability_tags JSONB DEFAULT '[]';

-- Operation flags (derived from dept/op/machine via classifier + QB data)
ALTER TABLE qb_operations
    ADD COLUMN IF NOT EXISTS has_coating              BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS has_sewing               BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS has_outsource_component  BOOLEAN DEFAULT FALSE;

-- contact_email: derived via job_no → qb_quotes.contact_email (enrichment join, no QB admin needed)
ALTER TABLE qb_operations
    ADD COLUMN IF NOT EXISTS contact_email TEXT;

-- Rush flags (sourced from existing synced data, not classifier)
-- am_rush:      operation_name ILIKE 'RUSH: Approx%' (pattern match during enrichment)
-- factory_rush: qb_operations.job_no → qb_jobs.factory_rush_level IS NOT NULL (enrichment join)
--               factory_rush_level is already synced as field 21 on qb_jobs
ALTER TABLE qb_operations
    ADD COLUMN IF NOT EXISTS am_rush       BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS factory_rush  BOOLEAN DEFAULT FALSE;

-- Row type from classifier (e.g. 'outsource', 'internal', 'cost_recovery')
ALTER TABLE qb_operations
    ADD COLUMN IF NOT EXISTS row_type      VARCHAR(20);

-- GIN index for tag membership queries: capability_tags @> '["Wide Format"]'
CREATE INDEX IF NOT EXISTS idx_qb_operations_capability_tags
    ON qb_operations USING GIN (capability_tags);

-- Index for rush flag queries (find all rush jobs for a client)
CREATE INDEX IF NOT EXISTS idx_qb_operations_rush
    ON qb_operations(client_id, am_rush, factory_rush)
    WHERE am_rush = TRUE OR factory_rush = TRUE;

COMMENT ON COLUMN qb_operations.capability_tags IS 'Array of MVP capability tag names matched by classifier (e.g. ["Wide Format", "Soft Cover Books"]). GIN indexed for fast membership queries.';
COMMENT ON COLUMN qb_operations.am_rush IS 'True when operation_name starts with ''RUSH: Approx'' — customer-acknowledged rush. Set during QB operations sync.';
COMMENT ON COLUMN qb_operations.contact_email IS 'Contact email derived via job_no → qb_quotes.contact_email join. Populated during enrichment. Used for cross-contact recommendation (Level 1).';
COMMENT ON COLUMN qb_operations.factory_rush IS 'True when qb_jobs.factory_rush_level IS NOT NULL for the linked job. Joined via job_no during enrichment. factory_rush_level is already synced (qb_jobs field 21). Indicates factory absorbed rush cost — customer got rush service, may not have been charged.';
COMMENT ON COLUMN qb_operations.row_type IS 'Classifier-derived row type: outsource | internal | cost_recovery | null (unclassified)';
