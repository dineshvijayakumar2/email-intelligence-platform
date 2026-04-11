-- ============================================================================
-- Migration 064: DB-side aggregation RPCs to eliminate Python pagination loops
-- ============================================================================
-- Problem: Multiple endpoints paginate through ai_usage_log (hundreds of
--          batches of 500 rows) and aggregate in Python. This burns ~12GB/day
--          of Supabase Disk IO Budget.
-- Fix:    Move aggregation to PostgreSQL with RPC functions + add missing
--          composite indexes for the hottest query paths.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. Composite index for budget-check queries (runs on EVERY AI call)
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_ai_usage_spend_check
    ON ai_usage_log(client_id, created_at DESC)
    WHERE success = TRUE;

-- Composite for classification health per-mailbox lookups
CREATE INDEX IF NOT EXISTS idx_ai_intel_mailbox_status
    ON ai_email_intelligence(mailbox_id, processing_status);

-- ---------------------------------------------------------------------------
-- 2. RPC: get_spend_total — replaces get_actual_spend() pagination loop
--    Called on every AI call to enforce budget. Must be fast.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION get_spend_total(
    p_client_id UUID DEFAULT NULL,
    p_period TEXT DEFAULT 'daily'
)
RETURNS NUMERIC
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    since TIMESTAMPTZ;
    total NUMERIC;
BEGIN
    since := CASE
        WHEN p_period = 'daily'   THEN DATE_TRUNC('day',   NOW() AT TIME ZONE 'UTC')
        WHEN p_period = 'monthly' THEN DATE_TRUNC('month', NOW() AT TIME ZONE 'UTC')
        ELSE DATE_TRUNC('day', NOW() AT TIME ZONE 'UTC')
    END;

    IF p_client_id IS NOT NULL THEN
        SELECT COALESCE(SUM(estimated_cost_usd), 0)
        INTO total
        FROM ai_usage_log
        WHERE client_id = p_client_id
          AND created_at >= since
          AND success = TRUE;
    ELSE
        SELECT COALESCE(SUM(estimated_cost_usd), 0)
        INTO total
        FROM ai_usage_log
        WHERE created_at >= since
          AND success = TRUE;
    END IF;

    RETURN total;
END;
$$;

GRANT EXECUTE ON FUNCTION get_spend_total(UUID, TEXT) TO anon, authenticated;

-- ---------------------------------------------------------------------------
-- 3. RPC: get_usage_summary — replaces get_usage_summary() pagination loop
--    Returns aggregated cost/token/operation/model breakdown for N days.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION get_usage_summary(
    p_client_id UUID DEFAULT NULL,
    p_days INTEGER DEFAULT 30
)
RETURNS JSONB
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    since TIMESTAMPTZ;
    result JSONB;
    by_op JSONB;
    by_mdl JSONB;
    totals RECORD;
BEGIN
    since := NOW() - (p_days || ' days')::INTERVAL;

    -- Totals
    SELECT
        COALESCE(SUM(estimated_cost_usd), 0)    AS total_cost,
        COALESCE(SUM(input_tokens), 0)           AS total_input,
        COALESCE(SUM(output_tokens), 0)          AS total_output,
        COUNT(*)                                  AS total_requests,
        COUNT(*) FILTER (WHERE success = FALSE)   AS failures,
        COALESCE(AVG(processing_time_ms) FILTER (WHERE processing_time_ms > 0), 0) AS avg_latency
    INTO totals
    FROM ai_usage_log
    WHERE created_at >= since
      AND (p_client_id IS NULL OR client_id = p_client_id);

    -- By operation
    SELECT COALESCE(jsonb_object_agg(op, stats), '{}'::jsonb)
    INTO by_op
    FROM (
        SELECT
            COALESCE(operation, 'unknown') AS op,
            jsonb_build_object(
                'cost', ROUND(SUM(estimated_cost_usd)::numeric, 4),
                'count', COUNT(*)
            ) AS stats
        FROM ai_usage_log
        WHERE created_at >= since
          AND (p_client_id IS NULL OR client_id = p_client_id)
        GROUP BY COALESCE(operation, 'unknown')
    ) sub;

    -- By model
    SELECT COALESCE(jsonb_object_agg(mdl, stats), '{}'::jsonb)
    INTO by_mdl
    FROM (
        SELECT
            COALESCE(model, 'unknown') AS mdl,
            jsonb_build_object(
                'cost', ROUND(SUM(estimated_cost_usd)::numeric, 4),
                'count', COUNT(*)
            ) AS stats
        FROM ai_usage_log
        WHERE created_at >= since
          AND (p_client_id IS NULL OR client_id = p_client_id)
        GROUP BY COALESCE(model, 'unknown')
    ) sub;

    result := jsonb_build_object(
        'total_cost_usd',      ROUND(totals.total_cost::numeric, 4),
        'total_input_tokens',  totals.total_input,
        'total_output_tokens', totals.total_output,
        'total_requests',      totals.total_requests,
        'failure_rate',        CASE WHEN totals.total_requests > 0
                                    THEN ROUND((totals.failures::numeric / totals.total_requests), 4)
                                    ELSE 0 END,
        'avg_latency_ms',      ROUND(totals.avg_latency::numeric, 1),
        'by_operation',        by_op,
        'by_model',            by_mdl
    );

    RETURN result;
END;
$$;

GRANT EXECUTE ON FUNCTION get_usage_summary(UUID, INTEGER) TO anon, authenticated;

-- ---------------------------------------------------------------------------
-- 4. RPC: get_monitoring_stats — replaces get_monitoring_stats() pagination
--    Returns 24h health metrics in a single query.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION get_monitoring_stats(
    p_client_id UUID DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    since TIMESTAMPTZ;
    result JSONB;
    totals RECORD;
BEGIN
    since := NOW() - INTERVAL '24 hours';

    SELECT
        COUNT(*)                                                                    AS total,
        COUNT(*) FILTER (WHERE error_type IN ('json_parse', 'validation'))          AS parse_failures,
        COUNT(*) FILTER (WHERE error_type IN ('api_timeout', 'rate_limit', 'api_unavailable')) AS api_failures,
        COUNT(*) FILTER (WHERE success = FALSE)                                     AS total_failures,
        COALESCE(SUM(retry_count), 0)                                               AS total_retries,
        COALESCE(SUM(estimated_cost_usd), 0)                                        AS total_cost,
        COALESCE(SUM(batch_size), 0)                                                AS total_batch_size
    INTO totals
    FROM ai_usage_log
    WHERE created_at >= since
      AND (p_client_id IS NULL OR client_id = p_client_id);

    result := jsonb_build_object(
        'total_requests_24h', totals.total,
        'total_failures_24h', totals.total_failures,
        'parse_failure_rate', CASE WHEN totals.total > 0
                                   THEN ROUND((totals.parse_failures::numeric / totals.total), 4)
                                   ELSE 0 END,
        'api_failure_rate',   CASE WHEN totals.total > 0
                                   THEN ROUND((totals.api_failures::numeric / totals.total), 4)
                                   ELSE 0 END,
        'avg_retry_count',    CASE WHEN totals.total > 0
                                   THEN ROUND((totals.total_retries::numeric / totals.total), 2)
                                   ELSE 0 END,
        'cost_per_1000_emails', CASE WHEN totals.total_batch_size > 0
                                      THEN ROUND((totals.total_cost / totals.total_batch_size * 1000)::numeric, 4)
                                      ELSE 0 END
    );

    RETURN result;
END;
$$;

GRANT EXECUTE ON FUNCTION get_monitoring_stats(UUID) TO anon, authenticated;

-- ---------------------------------------------------------------------------
-- 5. RPC: get_distinct_folders_for_mailbox — per-mailbox folder names
--    Eliminates the 245K-row pagination loop in get_folder_names()
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION get_distinct_folders_for_mailbox(
    p_mailbox_id UUID
)
RETURNS TABLE(folder_path TEXT)
LANGUAGE sql
STABLE
AS $$
    SELECT DISTINCT e.folder_path
    FROM emails e
    WHERE e.mailbox_id = p_mailbox_id
      AND e.folder_path IS NOT NULL
    ORDER BY e.folder_path;
$$;

GRANT EXECUTE ON FUNCTION get_distinct_folders_for_mailbox(UUID) TO anon, authenticated;
