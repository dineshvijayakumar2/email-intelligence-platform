-- Migration 107: Comprehensive QB cleanup dashboard stats
-- Single RPC returning ALL stats for the QB cleanup dashboard:
--   Revenue matching, contact anchoring, email coverage, data quality
-- Replaces 12+ separate REST queries with one DB round-trip.

CREATE OR REPLACE FUNCTION qb_cleanup_dashboard_stats(p_client_id UUID)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_result JSONB;
BEGIN
    WITH
    -- QB customers: single scan
    qb_agg AS (
        SELECT
            COUNT(*)::int AS total,
            COUNT(matched_company_id)::int AS matched,
            (COUNT(*) - COUNT(matched_company_id))::int AS unmatched,
            COALESCE(SUM(total_invoiced), 0) AS total_revenue,
            COALESCE(SUM(CASE WHEN matched_company_id IS NOT NULL THEN total_invoiced ELSE 0 END), 0) AS matched_revenue
        FROM qb_customers
        WHERE client_id = p_client_id
    ),

    -- Match method + revenue breakdown (matched QB joined to companies)
    method_agg AS (
        SELECT
            COALESCE(jsonb_object_agg(method, stats), '{}'::jsonb) AS data
        FROM (
            SELECT
                COALESCE(cc.qb_match_method, 'unknown') AS method,
                jsonb_build_object('count', COUNT(*)::int, 'revenue', COALESCE(SUM(qc.total_invoiced), 0)) AS stats
            FROM qb_customers qc
            JOIN customer_companies cc ON qc.matched_company_id = cc.id
            WHERE qc.client_id = p_client_id AND qc.matched_company_id IS NOT NULL
            GROUP BY cc.qb_match_method
        ) sub
    ),

    -- Staged candidates (unmatched QB with pending match candidates)
    staged AS (
        SELECT
            COUNT(DISTINCT qc.id)::int AS cnt,
            COALESCE(SUM(DISTINCT qc.total_invoiced), 0) AS revenue
        FROM qb_customers qc
        JOIN qb_match_candidates mc
            ON mc.qb_record_id = qc.qb_record_id
           AND mc.client_id = qc.client_id
           AND mc.reviewed = false
        WHERE qc.client_id = p_client_id
          AND qc.matched_company_id IS NULL
    ),

    -- Email-linked unmatched (QB has email -> contact -> company chain)
    email_linked AS (
        SELECT
            COUNT(DISTINCT qc.id)::int AS cnt,
            COALESCE(SUM(DISTINCT qc.total_invoiced), 0) AS revenue
        FROM qb_customers qc
        JOIN qb_unique_emails ue
            ON ue.client_id = qc.client_id
           AND ue.qb_customer_id = qc.customer_key_id::TEXT
           AND ue.hide = false
           AND ue.email_invalid = false
        JOIN customer_contacts cc2
            ON cc2.email_address = ue.email
           AND cc2.client_id = qc.client_id
           AND cc2.customer_company_id IS NOT NULL
        WHERE qc.client_id = p_client_id
          AND qc.matched_company_id IS NULL
    ),

    -- QB-anchored company IDs (source of truth: qb_customers.matched_company_id)
    qb_anchored_set AS (
        SELECT DISTINCT matched_company_id AS company_id
        FROM qb_customers
        WHERE client_id = p_client_id AND matched_company_id IS NOT NULL
    ),

    -- Company stats: single scan
    company_agg AS (
        SELECT
            COUNT(*)::int AS total_sb,
            (SELECT COUNT(*)::int FROM qb_anchored_set) AS qb_anchored
        FROM customer_companies
        WHERE client_id = p_client_id
    ),

    -- Contaminated: SB companies with >1 QB customer matched
    contaminated AS (
        SELECT COUNT(*)::int AS cnt
        FROM (
            SELECT matched_company_id
            FROM qb_customers
            WHERE client_id = p_client_id AND matched_company_id IS NOT NULL
            GROUP BY matched_company_id
            HAVING COUNT(*) > 1
        ) sub
    ),

    -- Contact stats: single scan with LEFT JOIN to QB-anchored set
    contact_agg AS (
        SELECT
            COUNT(*)::int AS total,
            COUNT(ct.customer_company_id)::int AS with_company,
            COUNT(CASE WHEN qa.company_id IS NOT NULL THEN 1 END)::int AS with_qb_company
        FROM customer_contacts ct
        LEFT JOIN qb_anchored_set qa ON ct.customer_company_id = qa.company_id
        WHERE ct.client_id = p_client_id
    ),

    -- Email stats: single scan with LEFT JOIN to QB-anchored set
    email_agg AS (
        SELECT
            COUNT(*)::int AS total,
            COUNT(e.customer_company_id)::int AS with_company,
            COUNT(CASE WHEN qa.company_id IS NOT NULL THEN 1 END)::int AS with_qb_company
        FROM emails e
        LEFT JOIN qb_anchored_set qa ON e.customer_company_id = qa.company_id
        WHERE e.client_id = p_client_id
    )

    SELECT jsonb_build_object(
        'revenue', jsonb_build_object(
            'total', q.total_revenue,
            'matched', q.matched_revenue,
            'unmatched', q.total_revenue - q.matched_revenue,
            'match_rate_pct', CASE WHEN q.total_revenue > 0
                THEN ROUND(q.matched_revenue / q.total_revenue * 100, 1) ELSE 0 END,
            'method_breakdown', m.data,
            'buckets', jsonb_build_object(
                'email_linked', jsonb_build_object('count', el.cnt, 'revenue', el.revenue),
                'staged', jsonb_build_object('count', s.cnt, 'revenue', s.revenue),
                'no_link', jsonb_build_object(
                    'count', GREATEST(q.unmatched - el.cnt - s.cnt, 0),
                    'revenue', GREATEST((q.total_revenue - q.matched_revenue) - el.revenue - s.revenue, 0)
                )
            )
        ),
        'companies', jsonb_build_object(
            'total_qb_customers', q.total,
            'matched_qb_customers', q.matched,
            'unmatched_qb_customers', q.unmatched,
            'total_sb_companies', ca.total_sb,
            'qb_anchored_sb', ca.qb_anchored,
            'contaminated_sb', cont.cnt
        ),
        'contacts', jsonb_build_object(
            'total', ct.total,
            'with_qb_company', ct.with_qb_company,
            'with_non_qb_company', ct.with_company - ct.with_qb_company,
            'no_company', ct.total - ct.with_company
        ),
        'emails', jsonb_build_object(
            'total', em.total,
            'with_qb_company', em.with_qb_company,
            'with_non_qb_company', em.with_company - em.with_qb_company,
            'no_company', em.total - em.with_company
        )
    ) INTO v_result
    FROM qb_agg q, method_agg m, staged s, email_linked el,
         company_agg ca, contaminated cont, contact_agg ct, email_agg em;

    RETURN v_result;
END;
$$;
