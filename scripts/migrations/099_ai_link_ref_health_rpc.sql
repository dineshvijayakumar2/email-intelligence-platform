-- ============================================================================
-- Migration 099: AI Link Reference Health RPC
-- ============================================================================
-- Single-query aggregation for AI-extracted QB reference linking stats.
-- Shows per-mailbox: emails with refs, refs found, refs linked to QB,
-- unmatched refs, and link coverage percentage.
-- ============================================================================

CREATE OR REPLACE FUNCTION get_ai_link_ref_health(
    p_client_id UUID DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    mb_data JSONB;
    link_totals JSONB;
BEGIN
    -- Per-mailbox extraction stats + link stats
    SELECT jsonb_agg(row_data)
    INTO mb_data
    FROM (
        SELECT jsonb_build_object(
            'mailbox_id',          m.id,
            'email_address',       COALESCE(m.email_address, m.name, 'Unknown'),
            'total_classified',    COALESCE(cls.total, 0),
            'emails_with_refs',    COALESCE(ref_stats.with_refs, 0),
            'total_refs_found',    COALESCE(ref_stats.total_refs, 0),
            'total_quote_refs',    COALESCE(ref_stats.quote_refs, 0),
            'total_job_refs',      COALESCE(ref_stats.job_refs, 0),
            'total_links',         COALESCE(lk.total_links, 0),
            'quote_links',         COALESCE(lk.quote_links, 0),
            'job_links',           COALESCE(lk.job_links, 0),
            'threads_linked',      COALESCE(lk.threads_linked, 0),
            'link_rate_pct',       CASE WHEN COALESCE(ref_stats.total_refs, 0) > 0
                                        THEN ROUND(COALESCE(lk.total_links, 0)::numeric / ref_stats.total_refs * 100, 1)
                                        ELSE 0 END
        ) AS row_data
        FROM mailboxes m
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS total
            FROM ai_email_intelligence ai
            WHERE ai.mailbox_id = m.id
              AND ai.processing_status = 'completed'
        ) cls ON TRUE
        LEFT JOIN LATERAL (
            SELECT
                COUNT(*) AS with_refs,
                COALESCE(SUM(jsonb_array_length(ai.extracted_references)), 0) AS total_refs,
                COALESCE(SUM(
                    (SELECT COUNT(*) FROM jsonb_array_elements(ai.extracted_references) elem
                     WHERE elem->>'type' = 'quote')
                ), 0) AS quote_refs,
                COALESCE(SUM(
                    (SELECT COUNT(*) FROM jsonb_array_elements(ai.extracted_references) elem
                     WHERE elem->>'type' = 'job')
                ), 0) AS job_refs
            FROM ai_email_intelligence ai
            WHERE ai.mailbox_id = m.id
              AND ai.processing_status = 'completed'
              AND ai.extracted_references IS NOT NULL
              AND jsonb_array_length(ai.extracted_references) > 0
        ) ref_stats ON TRUE
        LEFT JOIN LATERAL (
            SELECT
                COUNT(*)                              AS total_links,
                COUNT(*) FILTER (WHERE tql.link_type = 'quote') AS quote_links,
                COUNT(*) FILTER (WHERE tql.link_type = 'job')   AS job_links,
                COUNT(DISTINCT tql.canonical_thread_id)          AS threads_linked
            FROM thread_qb_links tql
            WHERE tql.source = 'ai'
              AND tql.canonical_thread_id IN (
                  SELECT DISTINCT e.canonical_thread_id::text
                  FROM emails e
                  WHERE e.mailbox_id = m.id
                    AND e.canonical_thread_id IS NOT NULL
              )
              AND (p_client_id IS NULL OR tql.client_id = p_client_id)
        ) lk ON TRUE
        WHERE (p_client_id IS NULL OR m.client_id = p_client_id)
          AND COALESCE(cls.total, 0) > 0
        ORDER BY COALESCE(ref_stats.with_refs, 0) DESC
    ) sub;

    -- Client-wide link totals (from thread_qb_links, no thread_status join)
    SELECT jsonb_build_object(
        'threads_linked',  COUNT(DISTINCT canonical_thread_id),
        'total_links',     COUNT(*),
        'quote_links',     COUNT(*) FILTER (WHERE link_type = 'quote'),
        'job_links',       COUNT(*) FILTER (WHERE link_type = 'job'),
        'last_link_at',    MAX(created_at)
    )
    INTO link_totals
    FROM thread_qb_links
    WHERE source = 'ai'
      AND (p_client_id IS NULL OR client_id = p_client_id);

    RETURN jsonb_build_object(
        'mailboxes',    COALESCE(mb_data, '[]'::jsonb),
        'link_totals',  COALESCE(link_totals, '{}'::jsonb)
    );
END;
$$;
