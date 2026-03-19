-- ============================================================================
-- Migration 034: Product Intelligence Tables
-- ============================================================================
-- Purpose: Cache recommendation engine outputs (cross-contact gaps + related
--          product affinities) so recommendations are instant on page load.
--
-- customer_recommendations — per-company, 24h TTL
-- product_affinities       — client-wide market basket analysis results
-- ============================================================================

-- 1. Per-company recommendation cache
CREATE TABLE IF NOT EXISTS customer_recommendations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id           UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    company_id          UUID NOT NULL REFERENCES customer_companies(id) ON DELETE CASCADE,
    cross_contact_recs  JSONB NOT NULL DEFAULT '[]',
    related_product_recs JSONB NOT NULL DEFAULT '[]',
    product_profile     JSONB NOT NULL DEFAULT '{}',
    computed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (client_id, company_id)
);

CREATE INDEX IF NOT EXISTS idx_customer_recs_company
    ON customer_recommendations (client_id, company_id);
CREATE INDEX IF NOT EXISTS idx_customer_recs_computed
    ON customer_recommendations (computed_at DESC);

-- 2. Client-wide product affinity pairs (market basket analysis on qb_operations)
CREATE TABLE IF NOT EXISTS product_affinities (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id           UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    product_a           TEXT NOT NULL,
    product_b           TEXT NOT NULL,
    cooccurrence_count  INTEGER NOT NULL DEFAULT 0,
    confidence          DECIMAL(5,4),          -- P(product_b | product_a)
    computed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (client_id, product_a, product_b)
);

CREATE INDEX IF NOT EXISTS idx_product_affinities_lookup
    ON product_affinities (client_id, product_a, confidence DESC);
