-- ============================================================================
-- Sprint 2 Migration 007: Analytics Calculation Functions
-- ============================================================================
-- Purpose: Move analytics calculations to database for maximum performance
-- Run After: sprint2_migration_006_analytics_batch_ops.sql
-- Duration: <1 minute
-- ============================================================================

-- PART 1: Calculate all contact response time averages in one query
-- ============================================================================

CREATE OR REPLACE FUNCTION calculate_all_contact_response_times(
    p_client_id UUID
) RETURNS TABLE (
    contact_id UUID,
    avg_response_time_seconds INTEGER,
    their_avg_response_time INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        erm.responder_contact_id,
        AVG(erm.response_time_seconds)::INTEGER as avg_response_time,
        AVG(erm.response_time_seconds)::INTEGER as their_avg_response_time
    FROM email_response_metrics erm
    JOIN customer_contacts cc ON cc.id = erm.responder_contact_id
    WHERE cc.client_id = p_client_id
      AND erm.is_auto_reply = FALSE
      AND erm.responder_contact_id IS NOT NULL
    GROUP BY erm.responder_contact_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION calculate_all_contact_response_times(UUID)
IS 'Calculate average response times for all contacts in one query (excludes auto-replies)';

GRANT EXECUTE ON FUNCTION calculate_all_contact_response_times(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION calculate_all_contact_response_times(UUID) TO service_role;

DO $$
BEGIN
    RAISE NOTICE '✅ calculate_all_contact_response_times function created';
END $$;

-- ============================================================================
-- PART 2: Calculate all contact thread counts in one query
-- ============================================================================

CREATE OR REPLACE FUNCTION calculate_all_contact_thread_counts(
    p_client_id UUID
) RETURNS TABLE (
    contact_id UUID,
    open_thread_count INTEGER,
    dropped_thread_count INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        cc.id,
        COUNT(CASE WHEN ts.status IN ('awaiting_response', 'awaiting_our_response', 'overdue', 'ongoing') THEN 1 END)::INTEGER as open_count,
        COUNT(CASE WHEN ts.status = 'dropped' THEN 1 END)::INTEGER as dropped_count
    FROM customer_contacts cc
    LEFT JOIN thread_status ts ON COALESCE(ts.primary_contact_id, ts.customer_contact_id) = cc.id
    WHERE cc.client_id = p_client_id
    GROUP BY cc.id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION calculate_all_contact_thread_counts(UUID)
IS 'Calculate thread counts for all contacts in one query';

GRANT EXECUTE ON FUNCTION calculate_all_contact_thread_counts(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION calculate_all_contact_thread_counts(UUID) TO service_role;

DO $$
BEGIN
    RAISE NOTICE '✅ calculate_all_contact_thread_counts function created';
END $$;

-- ============================================================================
-- PART 3: Calculate all company thread counts in one query
-- ============================================================================

CREATE OR REPLACE FUNCTION calculate_all_company_thread_counts(
    p_client_id UUID
) RETURNS TABLE (
    company_id UUID,
    open_thread_count INTEGER,
    dropped_thread_count INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        cco.id,
        COUNT(CASE WHEN ts.status IN ('awaiting_response', 'awaiting_our_response', 'overdue', 'ongoing') THEN 1 END)::INTEGER as open_count,
        COUNT(CASE WHEN ts.status = 'dropped' THEN 1 END)::INTEGER as dropped_count
    FROM customer_companies cco
    LEFT JOIN thread_status ts ON ts.primary_company_id = cco.id
    WHERE cco.client_id = p_client_id
    GROUP BY cco.id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION calculate_all_company_thread_counts(UUID)
IS 'Calculate thread counts for all companies in one query';

GRANT EXECUTE ON FUNCTION calculate_all_company_thread_counts(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION calculate_all_company_thread_counts(UUID) TO service_role;

DO $$
BEGIN
    RAISE NOTICE '✅ calculate_all_company_thread_counts function created';
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
        'calculate_all_contact_response_times',
        'calculate_all_contact_thread_counts',
        'calculate_all_company_thread_counts'
    );

    IF v_function_count = 3 THEN
        RAISE NOTICE '✅ All analytics calculation functions verified';
    ELSE
        RAISE WARNING '⚠️ Missing analytics calculation functions (found: %)', v_function_count;
    END IF;
END $$;

-- ============================================================================
-- Migration 007 Complete
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE '====================================';
    RAISE NOTICE '✅ Migration 007 completed successfully';
    RAISE NOTICE '====================================';
    RAISE NOTICE 'Analytics calculations now run on database';
    RAISE NOTICE 'Expected: 744 individual queries → 1 query';
    RAISE NOTICE '====================================';
END $$;
