-- ============================================================================
-- Migration 081: QB Contact Linking + Industry Rollup
-- ============================================================================
--
-- REQUIRES HUMAN REVIEW BEFORE EXECUTION.
-- Transactional — safe to run in Supabase SQL Editor.
--
-- ─── Purpose ────────────────────────────────────────────────────────────────
-- Wire QB signals from qb_unique_emails + qb_contacts down to
-- customer_contacts so that AI thread-intelligence enrichment
-- (_enrich_with_sprint2_data) reads real values instead of NULL.
--
-- Also: propagate qb_customers.industry up to customer_companies.industry
-- (the column exists but no sync writes it) and expose an analytics view
-- for industry-level rollup.
--
-- ─── What this migration does ───────────────────────────────────────────────
-- 1a. Add new columns on customer_contacts + email lookup index
-- 1b. Extend batch_propagate_qb_data RPC — add `industry` with sentinel skip
-- 1c. New batch_propagate_qb_data_to_contacts RPC (two-pass update)
-- 1d. customer_industry_segments VIEW for analytics rollup
--
-- Backfill of the 20,449 matchable contacts runs via standalone script
-- (scripts/db/backfill_qb_contacts.py) so it can be monitored and re-run.
--
-- ROLLBACK: each section has an inverse below in comments.
-- ============================================================================

BEGIN;

-- ─── 1a. New columns + email index on customer_contacts ─────────────────────
ALTER TABLE customer_contacts
    ADD COLUMN IF NOT EXISTS qb_capabilities_used TEXT,
    ADD COLUMN IF NOT EXISTS qb_processes_used    TEXT,
    ADD COLUMN IF NOT EXISTS qb_linked_at         TIMESTAMPTZ;

-- Email lookup for case-insensitive join against qb_unique_emails.email
CREATE INDEX IF NOT EXISTS idx_contacts_email_lower
    ON customer_contacts (LOWER(email_address));

-- ─── 1b. Extend batch_propagate_qb_data — add industry ──────────────────────
-- Supersedes migration 052. Adds `industry` with a sentinel-skip guard:
-- QB's "Not Selected" placeholder must not overwrite a good tag.
CREATE OR REPLACE FUNCTION batch_propagate_qb_data(
    p_client_id UUID,
    p_data JSONB
)
RETURNS INTEGER
LANGUAGE plpgsql AS $$
DECLARE
    updated INTEGER := 0;
BEGIN
    UPDATE customer_companies cc
    SET qb_customer_type           = COALESCE(d.qb_customer_type, cc.qb_customer_type),
        qb_tier                    = COALESCE(d.qb_tier, cc.qb_tier),
        qb_total_revenue           = COALESCE(d.qb_total_revenue::NUMERIC, cc.qb_total_revenue),
        qb_invoiced_ty             = COALESCE(d.qb_invoiced_ty::NUMERIC, cc.qb_invoiced_ty),
        qb_invoiced_ly             = COALESCE(d.qb_invoiced_ly::NUMERIC, cc.qb_invoiced_ly),
        qb_growth_90d              = COALESCE(d.qb_growth_90d::NUMERIC, cc.qb_growth_90d),
        qb_days_since_last_invoice = COALESCE(d.qb_days_since_last_invoice::INTEGER, cc.qb_days_since_last_invoice),
        qb_account_manager         = COALESCE(d.qb_account_manager, cc.qb_account_manager),
        qb_customer_id             = COALESCE(d.qb_customer_id, cc.qb_customer_id),
        qb_customer_code           = COALESCE(d.qb_customer_code, cc.qb_customer_code),
        industry                   = COALESCE(NULLIF(NULLIF(d.industry, ''), 'Not Selected'), cc.industry)
    FROM jsonb_to_recordset(p_data) AS d(
        company_id TEXT,
        qb_customer_type TEXT,
        qb_tier TEXT,
        qb_total_revenue TEXT,
        qb_invoiced_ty TEXT,
        qb_invoiced_ly TEXT,
        qb_growth_90d TEXT,
        qb_days_since_last_invoice TEXT,
        qb_account_manager TEXT,
        qb_customer_id TEXT,
        qb_customer_code TEXT,
        industry TEXT
    )
    WHERE cc.id = (d.company_id)::UUID
      AND cc.client_id = p_client_id;

    GET DIAGNOSTICS updated = ROW_COUNT;
    RETURN updated;
END;
$$;

GRANT EXECUTE ON FUNCTION batch_propagate_qb_data(UUID, JSONB) TO anon, authenticated;

COMMENT ON FUNCTION batch_propagate_qb_data(UUID, JSONB) IS
  'Batch propagate QB customer fields to customer_companies. '
  'Extended in migration 081 to include industry (skips ''Not Selected'' sentinel).';

-- ─── 1c. New batch_propagate_qb_data_to_contacts RPC ────────────────────────
-- Two-pass DB-side update:
--   Pass 1: qb_unique_emails → customer_contacts (case-insensitive email join)
--   Pass 2: qb_contacts      → customer_contacts (FK via matched_contact_id)
-- Returns the SUM of row counts across both passes.
CREATE OR REPLACE FUNCTION batch_propagate_qb_data_to_contacts(
    p_client_id UUID
)
RETURNS INTEGER
LANGUAGE plpgsql AS $$
DECLARE
    pass1_count INTEGER := 0;
    pass2_count INTEGER := 0;
BEGIN
    -- Pass 1: qb_unique_emails → customer_contacts by email
    -- Filters out hidden/invalid/empty emails on the QB side.
    UPDATE customer_contacts cc
    SET qb_customer_type     = COALESCE(ue.customer_type, cc.qb_customer_type),
        qb_capabilities_used = COALESCE(NULLIF(NULLIF(ue.capabilities_used, ''), 'Not Selected'), cc.qb_capabilities_used),
        qb_processes_used    = COALESCE(NULLIF(NULLIF(ue.processes_used, ''), 'Not Selected'), cc.qb_processes_used),
        qb_linked_at         = NOW()
    FROM qb_unique_emails ue
    WHERE LOWER(cc.email_address) = LOWER(ue.email)
      AND cc.client_id = p_client_id
      AND ue.client_id = p_client_id
      AND ue.hide = FALSE
      AND ue.email_invalid = FALSE
      AND ue.email IS NOT NULL
      AND ue.email <> '';

    GET DIAGNOSTICS pass1_count = ROW_COUNT;

    -- Pass 2: qb_contacts → customer_contacts via matched_contact_id FK
    UPDATE customer_contacts cc
    SET qb_quotes_count         = COALESCE(qc.quotes_accepted_count, cc.qb_quotes_count),
        qb_last_quote_date      = COALESCE(qc.most_recent_quote_date, cc.qb_last_quote_date),
        qb_contact_recency_days = COALESCE(qc.contact_recency_days, cc.qb_contact_recency_days)
    FROM qb_contacts qc
    WHERE qc.matched_contact_id = cc.id
      AND qc.client_id = p_client_id
      AND qc.matched_contact_id IS NOT NULL;

    GET DIAGNOSTICS pass2_count = ROW_COUNT;

    RETURN pass1_count + pass2_count;
END;
$$;

GRANT EXECUTE ON FUNCTION batch_propagate_qb_data_to_contacts(UUID) TO anon, authenticated;

COMMENT ON FUNCTION batch_propagate_qb_data_to_contacts(UUID) IS
  'Propagate QB signals from qb_unique_emails + qb_contacts to customer_contacts. '
  'Two-pass UPDATE inside a single DB call. Feeds AI thread-intelligence enrichment.';

-- NOTE on Pass 1 capabilities/processes fields:
-- qb_unique_emails.capabilities_used/processes_used are QB rollup formula
-- fields added in migration 049 — comma-separated tag strings rolled up
-- from QB Operations via the Unique Emails table. Migration 081 persists
-- those strings directly onto customer_contacts as an enrichment signal.

-- ─── 1d. customer_industry_segments VIEW ────────────────────────────────────
-- Industry-level analytics rollup. View (not materialized) until industry
-- tag quality is verified in production.
CREATE OR REPLACE VIEW customer_industry_segments AS
SELECT
    cc.client_id,
    cc.industry,
    COUNT(DISTINCT cc.id)                                           AS company_count,
    COUNT(DISTINCT ct.id)                                           AS contact_count,
    COALESCE(SUM(cc.qb_total_revenue), 0)                           AS total_revenue,
    CASE WHEN COUNT(DISTINCT cc.id) > 0
         THEN COALESCE(SUM(cc.qb_total_revenue), 0) / COUNT(DISTINCT cc.id)
         ELSE 0
    END                                                             AS avg_revenue_per_company,
    COUNT(DISTINCT cc.id) FILTER (WHERE cc.qb_customer_type LIKE 'Active%')          AS active_companies,
    COUNT(DISTINCT cc.id) FILTER (WHERE cc.qb_tier IN ('Level 4 Enterprise', 'Level 3 Key Account')) AS enterprise_companies,
    COUNT(DISTINCT cc.id) FILTER (WHERE cc.qb_customer_type = 'Lapsed')              AS lapsed_companies
FROM customer_companies cc
LEFT JOIN customer_contacts ct ON ct.customer_company_id = cc.id
WHERE cc.industry IS NOT NULL
  AND cc.industry <> ''
  AND cc.industry <> 'Not Selected'
GROUP BY cc.client_id, cc.industry;

GRANT SELECT ON customer_industry_segments TO anon, authenticated;

COMMENT ON VIEW customer_industry_segments IS
  'Industry-level rollup of companies/contacts/revenue for analytics. '
  'Non-materialized — refresh is implicit on every query. Upgrade to '
  'MATERIALIZED VIEW once industry tag quality is verified.';

COMMIT;

-- ============================================================================
-- ROLLBACK (run to undo this migration)
-- ============================================================================
-- BEGIN;
-- DROP VIEW IF EXISTS customer_industry_segments;
-- DROP FUNCTION IF EXISTS batch_propagate_qb_data_to_contacts(UUID);
-- -- Restore migration 052 definition of batch_propagate_qb_data (without industry)
-- -- See scripts/migrations/052_batch_propagate_qb_data.sql
-- DROP INDEX IF EXISTS idx_contacts_email_lower;
-- ALTER TABLE customer_contacts
--     DROP COLUMN IF EXISTS qb_linked_at,
--     DROP COLUMN IF EXISTS qb_processes_used,
--     DROP COLUMN IF EXISTS qb_capabilities_used;
-- COMMIT;
