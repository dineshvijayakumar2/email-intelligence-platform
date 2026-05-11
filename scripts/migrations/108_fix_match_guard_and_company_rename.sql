-- Migration 108: Fix contamination root cause + company rename from QB
--
-- 1. batch_write_qb_matches: add WHERE matched_company_id IS NULL guard
--    so re-matches cannot overwrite existing clean links (prevents contamination)
--
-- 2. batch_propagate_qb_data: accept qb_customer_name and rename the SB
--    company when the QB name differs (fixes person-named companies like
--    "Daniel Bauer" → "Litera Design")

-- Fix 1: Guard against overwriting existing matches
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
      AND qc.client_id = p_client_id
      AND qc.matched_company_id IS NULL;

    GET DIAGNOSTICS written = ROW_COUNT;

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

-- Fix 2: Propagation now accepts qb_customer_name and renames SB company
CREATE OR REPLACE FUNCTION batch_propagate_qb_data(
    p_client_id UUID,
    p_data JSONB
)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    updated INTEGER := 0;
BEGIN
    UPDATE customer_companies cc
    SET company_name               = CASE
            WHEN d.qb_customer_name IS NOT NULL
             AND d.qb_customer_name != ''
             AND d.qb_customer_name != cc.company_name
             AND NOT EXISTS (
                 SELECT 1 FROM customer_companies cc2
                 WHERE cc2.client_id = p_client_id
                   AND cc2.company_name = d.qb_customer_name
                   AND cc2.id != cc.id
             )
            THEN d.qb_customer_name
            ELSE cc.company_name
        END,
        qb_customer_type          = COALESCE(d.qb_customer_type, cc.qb_customer_type),
        qb_tier                   = COALESCE(d.qb_tier, cc.qb_tier),
        qb_total_revenue          = COALESCE(d.qb_total_revenue::NUMERIC, cc.qb_total_revenue),
        qb_invoiced_ty            = COALESCE(d.qb_invoiced_ty::NUMERIC, cc.qb_invoiced_ty),
        qb_invoiced_ly            = COALESCE(d.qb_invoiced_ly::NUMERIC, cc.qb_invoiced_ly),
        qb_growth_90d             = COALESCE(d.qb_growth_90d::NUMERIC, cc.qb_growth_90d),
        qb_days_since_last_invoice = COALESCE(d.qb_days_since_last_invoice::INTEGER, cc.qb_days_since_last_invoice),
        qb_account_manager        = COALESCE(d.qb_account_manager, cc.qb_account_manager),
        qb_customer_id            = COALESCE(d.qb_customer_id, cc.qb_customer_id),
        qb_customer_code          = COALESCE(d.qb_customer_code, cc.qb_customer_code),
        industry                  = COALESCE(d.industry, cc.industry)
    FROM jsonb_to_recordset(p_data) AS d(
        company_id TEXT,
        qb_customer_name TEXT,
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
