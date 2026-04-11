-- ============================================================================
-- Migration 065: DB-side aggregation for data-health endpoints
-- ============================================================================
-- Problem: classification_health does 5 queries per mailbox (N+1).
--          thread_health does 2 queries per mailbox + pagination loop.
--          Combined: ~30-50 queries per page load on 6 mailboxes.
-- Fix:    Single-query RPC functions with GROUP BY.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. RPC: get_classification_health — one query replaces N+1 loop
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION get_classification_health(
    p_client_id UUID DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    result JSONB;
BEGIN
    SELECT jsonb_agg(row_data)
    INTO result
    FROM (
        SELECT jsonb_build_object(
            'mailbox_id',     m.id,
            'email_address',  COALESCE(m.email_address, m.name, 'Unknown'),
            'total_emails',   COALESCE(ec.cnt, 0),
            'classified',     COALESCE(sc.completed, 0),
            'failed',         COALESCE(sc.failed, 0),
            'skipped',        COALESCE(sc.skipped, 0),
            'pending',        GREATEST(0, COALESCE(ec.cnt, 0)
                                - COALESCE(sc.completed, 0)
                                - COALESCE(sc.failed, 0)
                                - COALESCE(sc.skipped, 0)),
            'last_analysis_at', sc.last_completed
        ) AS row_data
        FROM mailboxes m
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS cnt
            FROM emails e
            WHERE e.mailbox_id = m.id
        ) ec ON TRUE
        LEFT JOIN LATERAL (
            SELECT
                COUNT(*) FILTER (WHERE processing_status = 'completed') AS completed,
                COUNT(*) FILTER (WHERE processing_status = 'failed')    AS failed,
                COUNT(*) FILTER (WHERE processing_status = 'skipped')   AS skipped,
                MAX(processed_at) FILTER (WHERE processing_status = 'completed') AS last_completed
            FROM ai_email_intelligence ai
            WHERE ai.mailbox_id = m.id
        ) sc ON TRUE
        WHERE (p_client_id IS NULL OR m.client_id = p_client_id)
        ORDER BY COALESCE(ec.cnt, 0) DESC
    ) sub;

    RETURN COALESCE(result, '[]'::jsonb);
END;
$$;

GRANT EXECUTE ON FUNCTION get_classification_health(UUID) TO anon, authenticated;

-- ---------------------------------------------------------------------------
-- 2. RPC: get_thread_health — one query replaces N+1 + pagination loop
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION get_thread_health(
    p_client_id UUID DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    mb_data JSONB;
    null_data JSONB;
    status_dist JSONB;
    intent_dist JSONB;
BEGIN
    -- Per-mailbox thread counts + intent coverage
    SELECT COALESCE(jsonb_agg(row_data), '[]'::jsonb)
    INTO mb_data
    FROM (
        SELECT jsonb_build_object(
            'mailbox_id',         m.id,
            'email_address',      COALESCE(m.email_address, m.name, 'Unknown'),
            'thread_count',       COALESCE(tc.cnt, 0),
            'with_intent',        COALESCE(tc.with_intent, 0),
            'intent_coverage_pct', CASE WHEN COALESCE(tc.cnt, 0) > 0
                                        THEN ROUND((COALESCE(tc.with_intent, 0)::numeric / tc.cnt) * 100, 1)
                                        ELSE 0 END,
            'status',             'success'
        ) AS row_data
        FROM mailboxes m
        LEFT JOIN LATERAL (
            SELECT
                COUNT(*) AS cnt,
                COUNT(*) FILTER (WHERE last_email_intent IS NOT NULL) AS with_intent
            FROM thread_status ts
            WHERE ts.mailbox_id = m.id
        ) tc ON TRUE
        WHERE (p_client_id IS NULL OR m.client_id = p_client_id)
        ORDER BY COALESCE(tc.cnt, 0) DESC
    ) sub;

    -- Client-wide threads (mailbox_id IS NULL)
    SELECT jsonb_build_object(
        'mailbox_id',         NULL,
        'email_address',      'Client-wide threads',
        'thread_count',       COUNT(*),
        'with_intent',        COUNT(*) FILTER (WHERE last_email_intent IS NOT NULL),
        'intent_coverage_pct', CASE WHEN COUNT(*) > 0
                                    THEN ROUND((COUNT(*) FILTER (WHERE last_email_intent IS NOT NULL)::numeric / COUNT(*)) * 100, 1)
                                    ELSE 0 END,
        'status',             'success'
    )
    INTO null_data
    FROM thread_status
    WHERE mailbox_id IS NULL;

    -- Status distribution (all threads for this client's mailboxes + null)
    SELECT COALESCE(jsonb_object_agg(s, c), '{}'::jsonb)
    INTO status_dist
    FROM (
        SELECT
            COALESCE(ts.status, 'unknown') AS s,
            COUNT(*) AS c
        FROM thread_status ts
        LEFT JOIN mailboxes m ON ts.mailbox_id = m.id
        WHERE ts.mailbox_id IS NULL
           OR (p_client_id IS NULL OR m.client_id = p_client_id)
        GROUP BY COALESCE(ts.status, 'unknown')
    ) sub;

    -- Intent status distribution
    SELECT COALESCE(jsonb_object_agg(s, c), '{}'::jsonb)
    INTO intent_dist
    FROM (
        SELECT
            ts.intent_status AS s,
            COUNT(*) AS c
        FROM thread_status ts
        LEFT JOIN mailboxes m ON ts.mailbox_id = m.id
        WHERE ts.intent_status IS NOT NULL
          AND (ts.mailbox_id IS NULL
               OR (p_client_id IS NULL OR m.client_id = p_client_id))
        GROUP BY ts.intent_status
    ) sub;

    RETURN jsonb_build_object(
        'mailboxes',          mb_data || CASE WHEN (null_data->>'thread_count')::int > 0
                                              THEN jsonb_build_array(null_data)
                                              ELSE '[]'::jsonb END,
        'status_distribution', status_dist,
        'intent_distribution', intent_dist
    );
END;
$$;

GRANT EXECUTE ON FUNCTION get_thread_health(UUID) TO anon, authenticated;
