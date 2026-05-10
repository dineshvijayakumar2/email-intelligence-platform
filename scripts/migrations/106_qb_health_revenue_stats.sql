-- Migration 106: RPC for QB health revenue stats
-- Returns revenue totals, match rate, method breakdown, and bucket analysis
-- in a single DB round-trip for the Match Review dashboard.

CREATE OR REPLACE FUNCTION qb_health_revenue_stats(p_client_id UUID)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_total_revenue NUMERIC;
    v_matched_revenue NUMERIC;
    v_unmatched_revenue NUMERIC;
    v_method_revenue JSONB;
    v_email_linked_count INTEGER;
    v_email_linked_revenue NUMERIC;
    v_staged_count INTEGER;
    v_staged_revenue NUMERIC;
    v_total_unmatched INTEGER;
BEGIN
    -- Revenue totals (fast: single scan of qb_customers)
    SELECT
        COALESCE(SUM(total_invoiced), 0),
        COALESCE(SUM(CASE WHEN matched_company_id IS NOT NULL
                     THEN total_invoiced ELSE 0 END), 0)
    INTO v_total_revenue, v_matched_revenue
    FROM qb_customers
    WHERE client_id = p_client_id;

    v_unmatched_revenue := v_total_revenue - v_matched_revenue;

    -- Method revenue breakdown (fast: join on matched companies only)
    SELECT COALESCE(jsonb_object_agg(method, stats), '{}'::jsonb)
    INTO v_method_revenue
    FROM (
        SELECT
            COALESCE(cc.qb_match_method, 'unknown') AS method,
            jsonb_build_object(
                'revenue', COALESCE(SUM(qc.total_invoiced), 0),
                'count', COUNT(*)
            ) AS stats
        FROM qb_customers qc
        JOIN customer_companies cc ON qc.matched_company_id = cc.id
        WHERE qc.client_id = p_client_id
          AND qc.matched_company_id IS NOT NULL
        GROUP BY cc.qb_match_method
    ) sub;

    -- Bucket: staged for review (fast: uses idx_qmc_client_reviewed)
    SELECT COUNT(DISTINCT qc.id),
           COALESCE(SUM(DISTINCT qc.total_invoiced), 0)
    INTO v_staged_count, v_staged_revenue
    FROM qb_customers qc
    JOIN qb_match_candidates mc
        ON mc.qb_record_id = qc.qb_record_id
       AND mc.client_id = qc.client_id
       AND mc.reviewed = false
    WHERE qc.client_id = p_client_id
      AND qc.matched_company_id IS NULL;

    -- Bucket: email-linked unmatched (uses direct join, no LOWER/TRIM)
    -- Emails are pre-normalized to lowercase by the Python sync code
    SELECT COUNT(DISTINCT qc.id),
           COALESCE(SUM(DISTINCT qc.total_invoiced), 0)
    INTO v_email_linked_count, v_email_linked_revenue
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
      AND qc.matched_company_id IS NULL;

    -- Total unmatched count
    SELECT COUNT(*)
    INTO v_total_unmatched
    FROM qb_customers
    WHERE client_id = p_client_id
      AND matched_company_id IS NULL;

    RETURN jsonb_build_object(
        'total_revenue', v_total_revenue,
        'matched_revenue', v_matched_revenue,
        'unmatched_revenue', v_unmatched_revenue,
        'revenue_match_rate_pct', CASE
            WHEN v_total_revenue > 0
            THEN ROUND(v_matched_revenue / v_total_revenue * 100, 1)
            ELSE 0
        END,
        'revenue_target_pct', 95,
        'method_revenue', v_method_revenue,
        'buckets', jsonb_build_object(
            'email_linked', jsonb_build_object(
                'count', v_email_linked_count,
                'revenue', v_email_linked_revenue
            ),
            'staged', jsonb_build_object(
                'count', v_staged_count,
                'revenue', v_staged_revenue
            ),
            'no_link', jsonb_build_object(
                'count', GREATEST(v_total_unmatched - v_email_linked_count - v_staged_count, 0),
                'revenue', GREATEST(v_unmatched_revenue - v_email_linked_revenue - v_staged_revenue, 0)
            )
        )
    );
END;
$$;
