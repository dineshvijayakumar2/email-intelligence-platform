-- ============================================================================
-- Sprint 2 Migration 009: Communication Pattern Calculations
-- ============================================================================
-- Purpose: Move communication pattern calculations to database for performance
-- Run After: sprint2_migration_008_fix_thread_status.sql
-- Duration: <1 minute
-- ============================================================================

-- PART 1: Calculate all contact communication patterns in one query
-- ============================================================================

CREATE OR REPLACE FUNCTION calculate_all_contact_comm_patterns(
    p_client_id UUID
) RETURNS TABLE (
    contact_id UUID,
    total_inbound_emails INTEGER,
    total_outbound_emails INTEGER,
    emails_per_month NUMERIC,
    avg_thread_depth NUMERIC,
    last_inbound_date TIMESTAMPTZ,
    last_outbound_date TIMESTAMPTZ,
    days_since_last_contact INTEGER
) AS $$
BEGIN
    RETURN QUERY
    WITH contact_emails AS (
        -- Get all emails grouped by contact
        SELECT
            e.customer_contact_id,
            COUNT(*) FILTER (WHERE e.is_outbound = FALSE) as inbound_count,
            COUNT(*) FILTER (WHERE e.is_outbound = TRUE) as outbound_count,
            MAX(e.sent_date) FILTER (WHERE e.is_outbound = FALSE) as last_inbound,
            MAX(e.sent_date) FILTER (WHERE e.is_outbound = TRUE) as last_outbound,
            MIN(e.sent_date) as first_email,
            MAX(e.sent_date) as last_email
        FROM emails e
        JOIN customer_contacts cc ON cc.id = e.customer_contact_id
        WHERE cc.client_id = p_client_id
          AND e.processing_status = 'success'
        GROUP BY e.customer_contact_id
    ),
    thread_depths AS (
        -- Calculate average thread depth per contact
        SELECT
            COALESCE(ts.primary_contact_id, ts.customer_contact_id) as contact_id,
            AVG(ts.thread_depth)::NUMERIC as avg_depth
        FROM thread_status ts
        JOIN customer_contacts cc ON cc.id = COALESCE(ts.primary_contact_id, ts.customer_contact_id)
        WHERE cc.client_id = p_client_id
        GROUP BY COALESCE(ts.primary_contact_id, ts.customer_contact_id)
    )
    SELECT
        ce.customer_contact_id,
        ce.inbound_count::INTEGER,
        ce.outbound_count::INTEGER,
        -- Calculate emails per month (total emails / months active)
        CASE
            WHEN EXTRACT(EPOCH FROM (ce.last_email - ce.first_email)) > 0 THEN
                ROUND(
                    (ce.inbound_count + ce.outbound_count)::NUMERIC /
                    GREATEST(EXTRACT(EPOCH FROM (ce.last_email - ce.first_email)) / 2592000, 1),
                    2
                )
            ELSE 0
        END as emails_per_month,
        COALESCE(td.avg_depth, 0) as avg_thread_depth,
        ce.last_inbound,
        ce.last_outbound,
        EXTRACT(DAYS FROM (NOW() - GREATEST(ce.last_inbound, ce.last_outbound)))::INTEGER as days_since_last
    FROM contact_emails ce
    LEFT JOIN thread_depths td ON td.contact_id = ce.customer_contact_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION calculate_all_contact_comm_patterns(UUID)
IS 'Calculate communication pattern metrics for all contacts in one query';

GRANT EXECUTE ON FUNCTION calculate_all_contact_comm_patterns(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION calculate_all_contact_comm_patterns(UUID) TO service_role;

DO $$
BEGIN
    RAISE NOTICE '✅ calculate_all_contact_comm_patterns function created';
END $$;

-- ============================================================================
-- PART 2: Calculate thread initiation ratios for all contacts
-- ============================================================================

CREATE OR REPLACE FUNCTION calculate_all_contact_initiation_ratios(
    p_client_id UUID
) RETURNS TABLE (
    contact_id UUID,
    threads_initiated_by_us INTEGER,
    threads_initiated_by_them INTEGER,
    initiation_ratio NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    WITH thread_initiators AS (
        -- For each thread, find the first email to determine who initiated
        SELECT
            e.customer_contact_id,
            e.thread_id,
            (ARRAY_AGG(e.is_outbound ORDER BY e.sent_date ASC))[1] as first_is_outbound
        FROM emails e
        JOIN customer_contacts cc ON cc.id = e.customer_contact_id
        WHERE cc.client_id = p_client_id
          AND e.thread_id IS NOT NULL
          AND e.processing_status = 'success'
        GROUP BY e.customer_contact_id, e.thread_id
    )
    SELECT
        ti.customer_contact_id,
        COUNT(*) FILTER (WHERE ti.first_is_outbound = TRUE)::INTEGER as initiated_by_us,
        COUNT(*) FILTER (WHERE ti.first_is_outbound = FALSE)::INTEGER as initiated_by_them,
        CASE
            WHEN COUNT(*) > 0 THEN
                ROUND(
                    COUNT(*) FILTER (WHERE ti.first_is_outbound = TRUE)::NUMERIC / COUNT(*),
                    3
                )
            ELSE 0.5
        END as initiation_ratio
    FROM thread_initiators ti
    GROUP BY ti.customer_contact_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION calculate_all_contact_initiation_ratios(UUID)
IS 'Calculate thread initiation ratios for all contacts in one query';

GRANT EXECUTE ON FUNCTION calculate_all_contact_initiation_ratios(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION calculate_all_contact_initiation_ratios(UUID) TO service_role;

DO $$
BEGIN
    RAISE NOTICE '✅ calculate_all_contact_initiation_ratios function created';
END $$;

-- ============================================================================
-- PART 3: Calculate reply rates for all contacts
-- ============================================================================

CREATE OR REPLACE FUNCTION calculate_all_contact_reply_rates(
    p_client_id UUID
) RETURNS TABLE (
    contact_id UUID,
    reply_rate NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    WITH contact_responses AS (
        -- Count valid responses (non-auto-reply) per contact
        SELECT
            erm.responder_contact_id,
            COUNT(*) FILTER (WHERE erm.is_auto_reply = FALSE) as valid_responses
        FROM email_response_metrics erm
        JOIN customer_contacts cc ON cc.id = erm.responder_contact_id
        WHERE cc.client_id = p_client_id
        GROUP BY erm.responder_contact_id
    ),
    contact_inbound AS (
        -- Count total inbound emails per contact
        SELECT
            e.customer_contact_id,
            COUNT(*) as total_inbound
        FROM emails e
        JOIN customer_contacts cc ON cc.id = e.customer_contact_id
        WHERE cc.client_id = p_client_id
          AND e.is_outbound = FALSE
          AND e.processing_status = 'success'
        GROUP BY e.customer_contact_id
    )
    SELECT
        ci.customer_contact_id,
        CASE
            WHEN ci.total_inbound > 0 THEN
                ROUND(
                    COALESCE(cr.valid_responses, 0)::NUMERIC / ci.total_inbound,
                    3
                )
            ELSE 0
        END as reply_rate
    FROM contact_inbound ci
    LEFT JOIN contact_responses cr ON cr.responder_contact_id = ci.customer_contact_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION calculate_all_contact_reply_rates(UUID)
IS 'Calculate reply rates for all contacts in one query (excludes auto-replies)';

GRANT EXECUTE ON FUNCTION calculate_all_contact_reply_rates(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION calculate_all_contact_reply_rates(UUID) TO service_role;

DO $$
BEGIN
    RAISE NOTICE '✅ calculate_all_contact_reply_rates function created';
END $$;

-- ============================================================================
-- PART 4: Verify functions
-- ============================================================================

DO $$
DECLARE
    v_function_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_function_count
    FROM pg_proc
    WHERE proname IN (
        'calculate_all_contact_comm_patterns',
        'calculate_all_contact_initiation_ratios',
        'calculate_all_contact_reply_rates'
    );

    IF v_function_count = 3 THEN
        RAISE NOTICE '✅ All communication pattern calculation functions verified';
    ELSE
        RAISE WARNING '⚠️ Missing communication pattern functions (found: %)', v_function_count;
    END IF;
END $$;

-- ============================================================================
-- Migration 009 Complete
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE '====================================';
    RAISE NOTICE 'Migration 009 completed successfully';
    RAISE NOTICE '====================================';
    RAISE NOTICE 'Communication pattern calculations now run on database';
    RAISE NOTICE 'Expected: 744+ individual queries to 3 queries';
    RAISE NOTICE '====================================';
END $$;
