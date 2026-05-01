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
    -- Per-mailbox extraction stats (from ai_email_intelligence)
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
            'total_job_refs',      COALESCE(ref_stats.job_refs, 0)
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
