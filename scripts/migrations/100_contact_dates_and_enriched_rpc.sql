-- ============================================================================
-- Migration 100: Backfill contact dates + enriched company contacts RPC
-- ============================================================================
-- 1. Update contact count refresh RPC to also set first/last_contacted_at
-- 2. One-time backfill of first/last_contacted_at from email_contact_links
-- 3. New RPC: get_company_contacts_enriched — returns contacts with live
--    email stats + QB quote stats for the company profile page
-- ============================================================================

-- 1. Update contact count refresh to also set contact dates
CREATE OR REPLACE FUNCTION update_contact_email_counts_from_junction(p_client_id UUID)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET statement_timeout = '30s'
AS $$
DECLARE
    updated INTEGER := 0;
BEGIN
    PERFORM set_config('statement_timeout', '30000', true);

    WITH contact_counts AS (
        SELECT
            ecl.contact_id,
            COUNT(DISTINCT ecl.email_id) AS total_emails,
            COUNT(DISTINCT ecl.email_id) FILTER (WHERE e.is_outbound = true) AS sent,
            COUNT(DISTINCT ecl.email_id) FILTER (WHERE e.is_outbound = false OR e.is_outbound IS NULL) AS received,
            MIN(e.sent_date) AS first_email_at,
            MAX(e.sent_date) AS last_email_at
        FROM email_contact_links ecl
        JOIN emails e ON e.id = ecl.email_id
        WHERE ecl.client_id = p_client_id
          AND ecl.contact_id IS NOT NULL
        GROUP BY ecl.contact_id
    )
    UPDATE customer_contacts cc
    SET total_emails_sent = cc2.sent,
        total_emails_received = cc2.received,
        first_contacted_at = cc2.first_email_at,
        last_contacted_at = cc2.last_email_at
    FROM contact_counts cc2
    WHERE cc.id = cc2.contact_id
      AND cc.client_id = p_client_id;

    GET DIAGNOSTICS updated = ROW_COUNT;
    RETURN updated;
END;
$$;

GRANT EXECUTE ON FUNCTION update_contact_email_counts_from_junction(UUID) TO anon, authenticated;

-- 2. New RPC: enriched company contacts for profile page
CREATE OR REPLACE FUNCTION get_company_contacts_enriched(p_company_id UUID)
RETURNS TABLE (
    id UUID,
    email_address TEXT,
    full_name TEXT,
    job_title TEXT,
    contact_type TEXT,
    engagement_score INTEGER,
    is_decision_maker BOOLEAN,
    total_emails BIGINT,
    total_sent BIGINT,
    total_received BIGINT,
    recent_emails BIGINT,
    last_email_at TIMESTAMPTZ,
    first_email_at TIMESTAMPTZ,
    quotes_count BIGINT,
    converted_quotes BIGINT,
    converted_revenue NUMERIC,
    qb_customer_type TEXT,
    qb_tier TEXT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT
        cont.id,
        cont.email_address,
        cont.full_name,
        cont.job_title,
        cont.contact_type,
        cont.engagement_score,
        cont.is_decision_maker,
        COALESCE(ecl_stats.total_emails, 0)::BIGINT AS total_emails,
        COALESCE(ecl_stats.sent, 0)::BIGINT AS total_sent,
        COALESCE(ecl_stats.received, 0)::BIGINT AS total_received,
        COALESCE(ecl_stats.recent_emails, 0)::BIGINT AS recent_emails,
        ecl_stats.last_email_at,
        ecl_stats.first_email_at,
        COALESCE(qb_stats.quotes_count, 0)::BIGINT AS quotes_count,
        COALESCE(qb_stats.converted_quotes, 0)::BIGINT AS converted_quotes,
        qb_stats.converted_revenue,
        cont.qb_customer_type,
        cont.qb_tier
    FROM customer_contacts cont
    LEFT JOIN LATERAL (
        SELECT
            COUNT(DISTINCT ecl.email_id) AS total_emails,
            COUNT(DISTINCT ecl.email_id) FILTER (WHERE e.is_outbound = true) AS sent,
            COUNT(DISTINCT ecl.email_id) FILTER (WHERE e.is_outbound = false OR e.is_outbound IS NULL) AS received,
            COUNT(DISTINCT ecl.email_id) FILTER (WHERE e.sent_date > NOW() - INTERVAL '90 days') AS recent_emails,
            MAX(e.sent_date) AS last_email_at,
            MIN(e.sent_date) AS first_email_at
        FROM email_contact_links ecl
        JOIN emails e ON e.id = ecl.email_id
        WHERE ecl.contact_id = cont.id
    ) ecl_stats ON true
    LEFT JOIN LATERAL (
        SELECT
            COUNT(*) AS quotes_count,
            COUNT(*) FILTER (WHERE q.has_job = true) AS converted_quotes,
            SUM(q.sell_ex_tax) FILTER (WHERE q.has_job = true) AS converted_revenue
        FROM qb_quotes q
        WHERE q.contact_email = cont.email_address
    ) qb_stats ON true
    WHERE cont.customer_company_id = p_company_id
    ORDER BY COALESCE(ecl_stats.total_emails, 0) DESC;
END;
$$;

GRANT EXECUTE ON FUNCTION get_company_contacts_enriched(UUID) TO anon, authenticated;
