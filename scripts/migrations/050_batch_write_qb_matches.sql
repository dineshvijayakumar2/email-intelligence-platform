-- Migration 050: RPC function for batch-writing QB matches
-- Replaces thousands of individual HTTP round-trips with a single DB call.
-- Accepts a JSONB array of matches and writes to both qb_customers and customer_companies.

CREATE OR REPLACE FUNCTION batch_write_qb_matches(
    p_client_id UUID,
    p_matches JSONB,
    p_now TIMESTAMPTZ DEFAULT NOW()
)
RETURNS INTEGER
LANGUAGE plpgsql AS $$
DECLARE
    written INTEGER := 0;
BEGIN
    -- Update qb_customers.matched_company_id
    UPDATE qb_customers qc
    SET matched_company_id = (m.company_id)::UUID
    FROM jsonb_to_recordset(p_matches) AS m(
        company_id TEXT,
        qb_customer_uuid TEXT,
        qb_record_id TEXT,
        qb_customer_code TEXT,
        match_method TEXT
    )
    WHERE qc.id = (m.qb_customer_uuid)::UUID
      AND qc.client_id = p_client_id;

    GET DIAGNOSTICS written = ROW_COUNT;

    -- Update customer_companies with QB match metadata
    -- Preserve email_lookup if already set (higher confidence than name-based)
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
        match_method TEXT
    )
    WHERE cc.id = (m.company_id)::UUID
      AND cc.client_id = p_client_id;

    RETURN written;
END;
$$;
