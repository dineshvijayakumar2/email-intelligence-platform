-- Migration 089: Rewrite get_classification_health for performance
--
-- Problem: LATERAL subqueries execute per-mailbox scans on emails and
-- ai_email_intelligence, timing out at ~21K+ emails (Supabase 8s limit).
--
-- Fix: Replace LATERAL with pre-aggregated GROUP BY subqueries joined once.
-- Pushes client_id filter into subqueries so only relevant rows are scanned.
-- Changes O(mailboxes × rows) → O(rows) — single pass per table.

CREATE OR REPLACE FUNCTION get_classification_health(
    p_client_id UUID DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
STABLE
SET statement_timeout = '60s'
AS $$
DECLARE
    result JSONB;
BEGIN
    SELECT jsonb_agg(row_data)
    INTO result
    FROM (
        SELECT jsonb_build_object(
            'mailbox_id',       m.id,
            'email_address',    COALESCE(m.email_address, m.name, 'Unknown'),
            'total_emails',     COALESCE(ec.cnt, 0),
            'classified',       COALESCE(sc.completed, 0),
            'failed',           COALESCE(sc.failed, 0),
            'skipped',          COALESCE(sc.skipped, 0),
            'pending',          GREATEST(0, COALESCE(ec.cnt, 0)
                                    - COALESCE(sc.completed, 0)
                                    - COALESCE(sc.failed, 0)
                                    - COALESCE(sc.skipped, 0)),
            'last_analysis_at', sc.last_completed
        ) AS row_data
        FROM mailboxes m
        LEFT JOIN (
            SELECT mailbox_id, COUNT(*) AS cnt
            FROM emails
            WHERE (p_client_id IS NULL OR client_id = p_client_id)
            GROUP BY mailbox_id
        ) ec ON ec.mailbox_id = m.id
        LEFT JOIN (
            SELECT
                mailbox_id,
                COUNT(*) FILTER (WHERE processing_status = 'completed') AS completed,
                COUNT(*) FILTER (WHERE processing_status = 'failed')    AS failed,
                COUNT(*) FILTER (WHERE processing_status = 'skipped')   AS skipped,
                MAX(processed_at) FILTER (WHERE processing_status = 'completed') AS last_completed
            FROM ai_email_intelligence
            WHERE (p_client_id IS NULL OR client_id = p_client_id)
            GROUP BY mailbox_id
        ) sc ON sc.mailbox_id = m.id
        WHERE (p_client_id IS NULL OR m.client_id = p_client_id)
        ORDER BY COALESCE(ec.cnt, 0) DESC
    ) sub;

    RETURN COALESCE(result, '[]'::jsonb);
END;
$$;

GRANT EXECUTE ON FUNCTION get_classification_health(UUID) TO anon, authenticated;
