-- Migration 111: Auto-rename SB company to QB customer name at match-write time
--
-- When batch_write_qb_matches links a QB customer to an SB company,
-- rename the SB company if the QB name differs (e.g. "P.Johnson" → "6D VISION MIRANDA").
-- Avoids renaming if another company already has that name (prevents duplicates).

CREATE OR REPLACE FUNCTION batch_write_qb_matches(
    p_client_id UUID,
    p_matches JSONB,
    p_now TIMESTAMPTZ DEFAULT NOW()
)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    written INTEGER := 0;
BEGIN
    -- 1. Set matched_company_id on qb_customers (only if not already matched)
    UPDATE qb_customers qc
    SET matched_company_id = (m.company_id)::UUID
    FROM jsonb_to_recordset(p_matches) AS m(
        company_id TEXT,
        qb_customer_uuid TEXT,
        qb_record_id TEXT,
        qb_customer_code TEXT,
        match_method TEXT,
        qb_customer_name TEXT
    )
    WHERE qc.id = (m.qb_customer_uuid)::UUID
      AND qc.client_id = p_client_id
      AND qc.matched_company_id IS NULL;

    GET DIAGNOSTICS written = ROW_COUNT;

    -- 2. Write match metadata on customer_companies
    UPDATE customer_companies cc
    SET qb_customer_id  = COALESCE(cc.qb_customer_id, m.qb_record_id),
        qb_customer_code = COALESCE(cc.qb_customer_code, m.qb_customer_code),
        qb_match_method  = CASE
            WHEN cc.qb_match_method = 'email_lookup' THEN 'email_lookup'
            ELSE m.match_method
        END,
        qb_matched_at    = COALESCE(cc.qb_matched_at, p_now)
    FROM jsonb_to_recordset(p_matches) AS m(
        company_id TEXT,
        qb_customer_uuid TEXT,
        qb_record_id TEXT,
        qb_customer_code TEXT,
        match_method TEXT,
        qb_customer_name TEXT
    )
    WHERE cc.id = (m.company_id)::UUID
      AND cc.client_id = p_client_id;

    -- 3. Rename SB company to QB customer name (if different and no conflict)
    UPDATE customer_companies cc
    SET company_name = m.qb_customer_name
    FROM jsonb_to_recordset(p_matches) AS m(
        company_id TEXT,
        qb_customer_name TEXT
    )
    WHERE cc.id = (m.company_id)::UUID
      AND cc.client_id = p_client_id
      AND m.qb_customer_name IS NOT NULL
      AND m.qb_customer_name != ''
      AND m.qb_customer_name != cc.company_name
      AND NOT EXISTS (
          SELECT 1 FROM customer_companies cc2
          WHERE cc2.client_id = p_client_id
            AND cc2.company_name = m.qb_customer_name
            AND cc2.id != cc.id
      );

    RETURN written;
END;
$$;
