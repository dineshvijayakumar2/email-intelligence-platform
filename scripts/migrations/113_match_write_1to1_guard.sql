-- Migration 113: Add 1:1 guard to batch_write_qb_matches
--
-- Prevents multiple QB customers from matching to the same SB company.
-- Uses a deduped CTE to pick one winner per company_id within the batch,
-- plus NOT EXISTS to skip companies already matched by a prior call.

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
    -- 1. Set matched_company_id on qb_customers
    --    Dedup: one winner per company_id (first in array order)
    --    Guard: skip if company already has a match from a prior batch
    WITH deduped AS (
        SELECT DISTINCT ON ((m.company_id)::UUID)
            (m.company_id)::UUID AS company_id,
            (m.qb_customer_uuid)::UUID AS qb_customer_uuid,
            m.qb_record_id,
            m.qb_customer_code,
            m.match_method,
            m.qb_customer_name
        FROM jsonb_to_recordset(p_matches) AS m(
            company_id TEXT,
            qb_customer_uuid TEXT,
            qb_record_id TEXT,
            qb_customer_code TEXT,
            match_method TEXT,
            qb_customer_name TEXT
        )
        ORDER BY (m.company_id)::UUID
    )
    UPDATE qb_customers qc
    SET matched_company_id = d.company_id
    FROM deduped d
    WHERE qc.id = d.qb_customer_uuid
      AND qc.client_id = p_client_id
      AND qc.matched_company_id IS NULL
      AND NOT EXISTS (
          SELECT 1 FROM qb_customers qc2
          WHERE qc2.client_id = p_client_id
            AND qc2.matched_company_id = d.company_id
      );

    GET DIAGNOSTICS written = ROW_COUNT;

    -- 2. Write match metadata on customer_companies
    WITH deduped AS (
        SELECT DISTINCT ON ((m.company_id)::UUID)
            (m.company_id)::UUID AS company_id,
            m.qb_record_id,
            m.qb_customer_code,
            m.match_method,
            m.qb_customer_name
        FROM jsonb_to_recordset(p_matches) AS m(
            company_id TEXT,
            qb_record_id TEXT,
            qb_customer_code TEXT,
            match_method TEXT,
            qb_customer_name TEXT
        )
        ORDER BY (m.company_id)::UUID
    )
    UPDATE customer_companies cc
    SET qb_customer_id  = COALESCE(cc.qb_customer_id, d.qb_record_id),
        qb_customer_code = COALESCE(cc.qb_customer_code, d.qb_customer_code),
        qb_match_method  = CASE
            WHEN cc.qb_match_method = 'email_lookup' THEN 'email_lookup'
            ELSE d.match_method
        END,
        qb_matched_at    = COALESCE(cc.qb_matched_at, p_now)
    FROM deduped d
    WHERE cc.id = d.company_id
      AND cc.client_id = p_client_id;

    -- 3. Rename SB company to QB customer name (if different and no conflict)
    WITH deduped AS (
        SELECT DISTINCT ON ((m.company_id)::UUID)
            (m.company_id)::UUID AS company_id,
            m.qb_customer_name
        FROM jsonb_to_recordset(p_matches) AS m(
            company_id TEXT,
            qb_customer_name TEXT
        )
        WHERE m.qb_customer_name IS NOT NULL AND m.qb_customer_name != ''
        ORDER BY (m.company_id)::UUID
    )
    UPDATE customer_companies cc
    SET company_name = d.qb_customer_name
    FROM deduped d
    WHERE cc.id = d.company_id
      AND cc.client_id = p_client_id
      AND d.qb_customer_name != cc.company_name
      AND NOT EXISTS (
          SELECT 1 FROM customer_companies cc2
          WHERE cc2.client_id = p_client_id
            AND cc2.company_name = d.qb_customer_name
            AND cc2.id != cc.id
      );

    RETURN written;
END;
$$;
