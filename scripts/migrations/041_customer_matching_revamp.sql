-- Migration 041: Revamped QB ↔ Supabase Customer Matching
-- Adds tracking columns to customer_companies and creates staging table for fuzzy match review.

-- ── 1. New columns on customer_companies ─────────────────────────────────────
ALTER TABLE customer_companies
  ADD COLUMN IF NOT EXISTS qb_customer_id    TEXT,          -- QB "Customer ID (key)" e.g. "17541"
  ADD COLUMN IF NOT EXISTS qb_customer_code  TEXT,          -- QB "Code*" e.g. "C13039"
  ADD COLUMN IF NOT EXISTS qb_match_method   TEXT,          -- 'exact_name' | 'domain_root' | 'fuzzy' | 'manual'
  ADD COLUMN IF NOT EXISTS qb_matched_at     TIMESTAMPTZ;   -- when this link was written/last verified

-- Index for quick lookup by QB customer ID
CREATE INDEX IF NOT EXISTS idx_cc_qb_customer_id
  ON customer_companies(qb_customer_id) WHERE qb_customer_id IS NOT NULL;

-- ── 2. Staging table for fuzzy match candidates ──────────────────────────────
CREATE TABLE IF NOT EXISTS qb_match_candidates (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id       UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  sb_company_id   UUID NOT NULL REFERENCES customer_companies(id) ON DELETE CASCADE,
  sb_company_name TEXT,
  qb_record_id    TEXT,           -- qb_customers.qb_record_id
  qb_customer_id  TEXT,           -- QB "Customer ID (key)"
  qb_name         TEXT,
  match_score     NUMERIC(5,2),
  match_method    TEXT DEFAULT 'fuzzy',
  reviewed        BOOLEAN DEFAULT FALSE,
  accepted        BOOLEAN,
  reviewed_by     UUID REFERENCES user_profiles(id),
  reviewed_at     TIMESTAMPTZ,
  created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_qmc_client_reviewed
  ON qb_match_candidates(client_id, reviewed);

-- ── 3. RPC for batch-promoting accepted fuzzy matches ────────────────────────
CREATE OR REPLACE FUNCTION promote_accepted_matches(p_client_id UUID)
RETURNS INTEGER
LANGUAGE plpgsql AS $$
DECLARE
  promoted INTEGER := 0;
  rec RECORD;
BEGIN
  FOR rec IN
    SELECT mc.id AS candidate_id,
           mc.sb_company_id,
           mc.qb_record_id,
           mc.qb_customer_id
    FROM qb_match_candidates mc
    WHERE mc.client_id = p_client_id
      AND mc.reviewed = TRUE
      AND mc.accepted = TRUE
  LOOP
    -- Set matched_company_id on qb_customers
    UPDATE qb_customers
    SET matched_company_id = rec.sb_company_id
    WHERE client_id = p_client_id
      AND qb_record_id = rec.qb_record_id
      AND matched_company_id IS NULL;

    -- Write qb_customer_id + match metadata on customer_companies
    UPDATE customer_companies
    SET qb_customer_id  = rec.qb_customer_id,
        qb_match_method = 'fuzzy',
        qb_matched_at   = now()
    WHERE id = rec.sb_company_id
      AND qb_match_method IS NULL;

    promoted := promoted + 1;
  END LOOP;
  RETURN promoted;
END;
$$;
