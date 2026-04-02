-- Migration 052: RPC function for batch-propagating QB data to customer_companies
-- Replaces thousands of individual HTTP round-trips with a single DB call per batch.

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
    SET qb_customer_type          = COALESCE(d.qb_customer_type, cc.qb_customer_type),
        qb_tier                   = COALESCE(d.qb_tier, cc.qb_tier),
        qb_total_revenue          = COALESCE(d.qb_total_revenue::NUMERIC, cc.qb_total_revenue),
        qb_invoiced_ty            = COALESCE(d.qb_invoiced_ty::NUMERIC, cc.qb_invoiced_ty),
        qb_invoiced_ly            = COALESCE(d.qb_invoiced_ly::NUMERIC, cc.qb_invoiced_ly),
        qb_growth_90d             = COALESCE(d.qb_growth_90d::NUMERIC, cc.qb_growth_90d),
        qb_days_since_last_invoice = COALESCE(d.qb_days_since_last_invoice::INTEGER, cc.qb_days_since_last_invoice),
        qb_account_manager        = COALESCE(d.qb_account_manager, cc.qb_account_manager),
        qb_customer_id            = COALESCE(d.qb_customer_id, cc.qb_customer_id),
        qb_customer_code          = COALESCE(d.qb_customer_code, cc.qb_customer_code)
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
        qb_customer_code TEXT
    )
    WHERE cc.id = (d.company_id)::UUID
      AND cc.client_id = p_client_id;

    GET DIAGNOSTICS updated = ROW_COUNT;
    RETURN updated;
END;
$$;
