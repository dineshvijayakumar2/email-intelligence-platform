-- Migration 114: Enforce 1:1 QB-to-SB company matching via unique index
--
-- Atomically: clean up existing contamination, then create unique partial index.
-- The index physically prevents multiple QB customers from matching to the same company.

CREATE OR REPLACE FUNCTION _enforce_1to1_matches(p_client_id UUID)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    cleaned INTEGER := 0;
BEGIN
    -- Step 1: For each contaminated company, keep the highest-revenue QB customer,
    -- unmatch the rest
    WITH ranked AS (
        SELECT
            qc.id,
            qc.matched_company_id,
            ROW_NUMBER() OVER (
                PARTITION BY qc.matched_company_id
                ORDER BY qc.total_invoiced DESC NULLS LAST, qc.id
            ) AS rn
        FROM qb_customers qc
        WHERE qc.client_id = p_client_id
          AND qc.matched_company_id IS NOT NULL
    )
    UPDATE qb_customers qc
    SET matched_company_id = NULL
    FROM ranked r
    WHERE qc.id = r.id
      AND r.rn > 1;

    GET DIAGNOSTICS cleaned = ROW_COUNT;

    RETURN cleaned;
END;
$$;

GRANT EXECUTE ON FUNCTION _enforce_1to1_matches(UUID) TO anon, authenticated;

-- Step 2: Unique partial index — physically prevents contamination
-- Run _enforce_1to1_matches() first to clean up existing duplicates
CREATE UNIQUE INDEX IF NOT EXISTS idx_qb_customers_unique_match
ON qb_customers (client_id, matched_company_id)
WHERE matched_company_id IS NOT NULL;
