-- ============================================================================
-- Migration 091: Rewrite company count refresh to bulk CTE, add timeouts
-- ============================================================================
-- Problem: update_company_email_counts_from_junction loops per-company
-- (11K+ individual SELECT+UPDATE pairs), hits 8s statement_timeout.
-- Fix: single CTE + bulk UPDATE (same pattern as contact version).
-- Also adds SECURITY DEFINER + 30s timeout to both count refresh RPCs.
-- ============================================================================

-- 1. Contact count refresh — add timeout + SECURITY DEFINER (query is already efficient)
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
            COUNT(DISTINCT ecl.email_id) FILTER (WHERE e.is_outbound = false OR e.is_outbound IS NULL) AS received
        FROM email_contact_links ecl
        JOIN emails e ON e.id = ecl.email_id
        WHERE ecl.client_id = p_client_id
          AND ecl.contact_id IS NOT NULL
        GROUP BY ecl.contact_id
    )
    UPDATE customer_contacts cc
    SET total_emails_sent = cc2.sent,
        total_emails_received = cc2.received
    FROM contact_counts cc2
    WHERE cc.id = cc2.contact_id
      AND cc.client_id = p_client_id;

    GET DIAGNOSTICS updated = ROW_COUNT;
    RETURN updated;
END;
$$;

-- 2. Company count refresh — rewrite from per-company loop to bulk CTE
CREATE OR REPLACE FUNCTION update_company_email_counts_from_junction(p_client_id UUID)
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

    WITH company_counts AS (
        SELECT
            ecl.company_id,
            COUNT(DISTINCT ecl.email_id) AS total_emails,
            COUNT(DISTINCT ecl.email_id) FILTER (WHERE e.is_outbound = true) AS total_outbound,
            COUNT(DISTINCT ecl.contact_id) AS contact_cnt,
            MIN(e.sent_date) AS first_dt,
            MAX(e.sent_date) AS last_dt
        FROM email_contact_links ecl
        JOIN emails e ON e.id = ecl.email_id
        WHERE ecl.client_id = p_client_id
          AND ecl.company_id IS NOT NULL
        GROUP BY ecl.company_id
    )
    UPDATE customer_companies cc
    SET total_emails    = co.total_emails,
        total_outbound  = co.total_outbound,
        total_inbound   = co.total_emails - co.total_outbound,
        contact_count   = co.contact_cnt,
        first_contact_date = co.first_dt,
        last_contact_date  = co.last_dt
    FROM company_counts co
    WHERE cc.id = co.company_id
      AND cc.client_id = p_client_id;

    GET DIAGNOSTICS updated = ROW_COUNT;
    RETURN updated;
END;
$$;

GRANT EXECUTE ON FUNCTION update_contact_email_counts_from_junction(UUID) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION update_company_email_counts_from_junction(UUID) TO anon, authenticated;
