-- ============================================================================
-- Migration 125: platform-owned enriched industry layer on qb_customers
-- ============================================================================
-- QB's MKTG:Industry field (qb_customers.industry) is the read-only source of truth
-- but is "Not Selected" for ~84% of customers. Task 13.2 produced human-approved
-- industry labels for the active unlabelled tail. Store them BESIDE the QB field
-- (provenance pattern — never overwrite QB), so the deck / industry-fit filter can
-- read qb_customers.industry first, else industry_enriched.
--
--   industry_enriched     — the approved enriched label (one of the 13 buckets), NULL if none
--   industry_source       — provenance: human_corrected | human_promoted | llm_high_conf
--   industry_enriched_at  — when it was written
-- ============================================================================

ALTER TABLE qb_customers ADD COLUMN IF NOT EXISTS industry_enriched TEXT;
ALTER TABLE qb_customers ADD COLUMN IF NOT EXISTS industry_source TEXT;
ALTER TABLE qb_customers ADD COLUMN IF NOT EXISTS industry_enriched_at TIMESTAMPTZ;
