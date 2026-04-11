-- ============================================================================
-- Migration 068: Seasonality Engine — DB-side aggregation + indexes
-- ============================================================================
-- Replaces Python pagination loop in get_seasonality() with a single RPC
-- that returns year-over-year monthly revenue and order counts.
-- ============================================================================

-- 1. Index for fast monthly aggregation by company
CREATE INDEX IF NOT EXISTS idx_qb_operations_company_date
    ON qb_operations(matched_company_id, date_accepted)
    WHERE date_accepted IS NOT NULL;

-- 2. RPC: Monthly revenue by year for a company
CREATE OR REPLACE FUNCTION get_company_seasonality(
    p_company_id UUID,
    p_client_id UUID DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    result JSONB;
BEGIN
    SELECT COALESCE(jsonb_agg(row_data ORDER BY yr DESC, mo), '[]'::jsonb)
    INTO result
    FROM (
        SELECT jsonb_build_object(
            'year',        EXTRACT(YEAR FROM date_accepted)::int,
            'month',       EXTRACT(MONTH FROM date_accepted)::int,
            'order_count', COUNT(*),
            'revenue',     ROUND(COALESCE(SUM(cost_plus_price), 0)::numeric, 2)
        ) AS row_data,
        EXTRACT(YEAR FROM date_accepted) AS yr,
        EXTRACT(MONTH FROM date_accepted) AS mo
        FROM qb_operations
        WHERE matched_company_id = p_company_id
          AND date_accepted IS NOT NULL
          AND (p_client_id IS NULL OR client_id = p_client_id)
        GROUP BY EXTRACT(YEAR FROM date_accepted), EXTRACT(MONTH FROM date_accepted)
    ) sub;

    RETURN result;
END;
$$;

GRANT EXECUTE ON FUNCTION get_company_seasonality(UUID, UUID) TO anon, authenticated;

-- 3. RPC: Industry-level monthly seasonality (aggregate across all companies in an industry)
CREATE OR REPLACE FUNCTION get_industry_seasonality(
    p_industry TEXT,
    p_client_id UUID DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    result JSONB;
BEGIN
    SELECT COALESCE(jsonb_agg(row_data ORDER BY mo), '[]'::jsonb)
    INTO result
    FROM (
        SELECT jsonb_build_object(
            'month',          EXTRACT(MONTH FROM o.date_accepted)::int,
            'order_count',    COUNT(*),
            'revenue',        ROUND(COALESCE(SUM(o.cost_plus_price), 0)::numeric, 2),
            'company_count',  COUNT(DISTINCT o.matched_company_id),
            'year_count',     COUNT(DISTINCT EXTRACT(YEAR FROM o.date_accepted))
        ) AS row_data,
        EXTRACT(MONTH FROM o.date_accepted) AS mo
        FROM qb_operations o
        JOIN customer_companies c ON c.id = o.matched_company_id
        WHERE LOWER(c.industry) = LOWER(p_industry)
          AND o.date_accepted IS NOT NULL
          AND (p_client_id IS NULL OR o.client_id = p_client_id)
        GROUP BY EXTRACT(MONTH FROM o.date_accepted)
    ) sub;

    RETURN result;
END;
$$;

GRANT EXECUTE ON FUNCTION get_industry_seasonality(TEXT, UUID) TO anon, authenticated;

-- 4. RPC: Upcoming outreach windows across all companies
--    Returns companies with historical peak months approaching in the next 8 weeks
CREATE OR REPLACE FUNCTION get_outreach_windows(
    p_client_id UUID,
    p_weeks_ahead INTEGER DEFAULT 8
)
RETURNS JSONB
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    result JSONB;
    current_month INTEGER;
    window_months INTEGER[];
BEGIN
    current_month := EXTRACT(MONTH FROM NOW())::int;
    -- Build array of months in the window (current + next p_weeks_ahead/4 months)
    window_months := ARRAY(
        SELECT ((current_month - 1 + g) % 12) + 1
        FROM generate_series(1, GREATEST(p_weeks_ahead / 4, 2)) g
    );

    SELECT COALESCE(jsonb_agg(row_data ORDER BY revenue_in_peak DESC), '[]'::jsonb)
    INTO result
    FROM (
        SELECT jsonb_build_object(
            'company_id',       o.matched_company_id,
            'company_name',     c.company_name,
            'industry',         c.industry,
            'qb_tier',          c.qb_tier,
            'peak_month',       EXTRACT(MONTH FROM o.date_accepted)::int,
            'revenue_in_peak',  ROUND(SUM(o.cost_plus_price)::numeric, 2),
            'order_count',      COUNT(*),
            'years_active',     COUNT(DISTINCT EXTRACT(YEAR FROM o.date_accepted)),
            'avg_annual_peak',  ROUND((SUM(o.cost_plus_price) /
                                 NULLIF(COUNT(DISTINCT EXTRACT(YEAR FROM o.date_accepted)), 0))::numeric, 2),
            'days_since_last_invoice', c.qb_days_since_last_invoice
        ) AS row_data,
        SUM(o.cost_plus_price) AS revenue_in_peak
        FROM qb_operations o
        JOIN customer_companies c ON c.id = o.matched_company_id
        WHERE o.client_id = p_client_id
          AND o.date_accepted IS NOT NULL
          AND EXTRACT(MONTH FROM o.date_accepted)::int = ANY(window_months)
        GROUP BY o.matched_company_id, c.company_name, c.industry, c.qb_tier,
                 c.qb_days_since_last_invoice, EXTRACT(MONTH FROM o.date_accepted)
        HAVING COUNT(*) >= 2  -- At least 2 orders in this month historically
    ) sub;

    RETURN result;
END;
$$;

GRANT EXECUTE ON FUNCTION get_outreach_windows(UUID, INTEGER) TO anon, authenticated;
