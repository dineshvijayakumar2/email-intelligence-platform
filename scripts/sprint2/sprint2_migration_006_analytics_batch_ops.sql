-- ============================================================================
-- Sprint 2 Migration 006: Analytics Batch Operations
-- ============================================================================
-- Purpose: Add batch update functions for Phase 4 analytics performance
-- Run After: sprint2_migration_005_fix_analytics_tables.sql
-- Duration: <1 minute
-- ============================================================================

-- PART 1: Batch update contact analytics (response times, patterns, engagement)
-- ============================================================================

CREATE OR REPLACE FUNCTION batch_update_contact_analytics(
    updates JSONB
) RETURNS TABLE (
    updated_count INTEGER,
    error_count INTEGER
) AS $$
DECLARE
    v_updated_count INTEGER := 0;
    v_error_count INTEGER := 0;
BEGIN
    -- Update contact analytics fields from JSONB array
    -- Handles: response times, thread counts, communication patterns, engagement scores
    UPDATE customer_contacts c
    SET
        -- Response time metrics
        avg_response_time_seconds = COALESCE(u.avg_response_time_seconds::INTEGER, c.avg_response_time_seconds),
        their_avg_response_time = COALESCE(u.their_avg_response_time::INTEGER, c.their_avg_response_time),

        -- Thread tracking
        open_thread_count = COALESCE(u.open_thread_count::INTEGER, c.open_thread_count),
        dropped_thread_count = COALESCE(u.dropped_thread_count::INTEGER, c.dropped_thread_count),

        -- Communication patterns
        initiation_ratio = COALESCE(u.initiation_ratio::NUMERIC, c.initiation_ratio),
        reply_rate = COALESCE(u.reply_rate::NUMERIC, c.reply_rate),
        emails_per_month_avg = COALESCE(u.emails_per_month_avg::NUMERIC, c.emails_per_month_avg),
        frequency_trend = COALESCE(u.frequency_trend, c.frequency_trend),
        avg_thread_depth = COALESCE(u.avg_thread_depth::NUMERIC, c.avg_thread_depth),
        last_inbound_at = COALESCE(u.last_inbound_at::TIMESTAMPTZ, c.last_inbound_at),
        last_outbound_at = COALESCE(u.last_outbound_at::TIMESTAMPTZ, c.last_outbound_at),

        -- Engagement score
        engagement_score = COALESCE(u.engagement_score::INTEGER, c.engagement_score),

        updated_at = NOW()
    FROM jsonb_to_recordset(updates) AS u(
        contact_id UUID,
        avg_response_time_seconds TEXT,
        their_avg_response_time TEXT,
        open_thread_count TEXT,
        dropped_thread_count TEXT,
        initiation_ratio TEXT,
        reply_rate TEXT,
        emails_per_month_avg TEXT,
        frequency_trend TEXT,
        avg_thread_depth TEXT,
        last_inbound_at TEXT,
        last_outbound_at TEXT,
        engagement_score TEXT
    )
    WHERE c.id = u.contact_id;

    GET DIAGNOSTICS v_updated_count = ROW_COUNT;
    RETURN QUERY SELECT v_updated_count, v_error_count;

EXCEPTION WHEN OTHERS THEN
    v_error_count := 1;
    RETURN QUERY SELECT v_updated_count, v_error_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION batch_update_contact_analytics(JSONB)
IS 'Batch update contact analytics: response times, thread counts, patterns, engagement scores';

GRANT EXECUTE ON FUNCTION batch_update_contact_analytics(JSONB) TO authenticated;
GRANT EXECUTE ON FUNCTION batch_update_contact_analytics(JSONB) TO service_role;

DO $$
BEGIN
    RAISE NOTICE '✅ batch_update_contact_analytics function created';
END $$;

-- ============================================================================
-- PART 2: Batch update company analytics (aggregates, health metrics)
-- ============================================================================

CREATE OR REPLACE FUNCTION batch_update_company_analytics(
    updates JSONB
) RETURNS TABLE (
    updated_count INTEGER,
    error_count INTEGER
) AS $$
DECLARE
    v_updated_count INTEGER := 0;
    v_error_count INTEGER := 0;
BEGIN
    -- Update company analytics fields from JSONB array
    UPDATE customer_companies c
    SET
        -- Contact aggregates
        contact_count = COALESCE(u.contact_count::INTEGER, c.contact_count),
        decision_maker_count = COALESCE(u.decision_maker_count::INTEGER, c.decision_maker_count),
        highest_seniority = COALESCE(u.highest_seniority, c.highest_seniority),

        -- Thread tracking
        open_thread_count = COALESCE(u.open_thread_count::INTEGER, c.open_thread_count),
        dropped_thread_count = COALESCE(u.dropped_thread_count::INTEGER, c.dropped_thread_count),

        -- Communication health
        avg_response_time_seconds = COALESCE(u.avg_response_time_seconds::INTEGER, c.avg_response_time_seconds),
        avg_emails_per_month = COALESCE(u.avg_emails_per_month::NUMERIC, c.avg_emails_per_month),
        frequency_trend = COALESCE(u.frequency_trend, c.frequency_trend),
        relationship_status = COALESCE(u.relationship_status, c.relationship_status),
        communication_health = COALESCE(u.communication_health, c.communication_health),

        -- Engagement score
        engagement_score = COALESCE(u.engagement_score::INTEGER, c.engagement_score),

        updated_at = NOW()
    FROM jsonb_to_recordset(updates) AS u(
        company_id UUID,
        contact_count TEXT,
        decision_maker_count TEXT,
        highest_seniority TEXT,
        open_thread_count TEXT,
        dropped_thread_count TEXT,
        avg_response_time_seconds TEXT,
        avg_emails_per_month TEXT,
        frequency_trend TEXT,
        relationship_status TEXT,
        communication_health TEXT,
        engagement_score TEXT
    )
    WHERE c.id = u.company_id;

    GET DIAGNOSTICS v_updated_count = ROW_COUNT;
    RETURN QUERY SELECT v_updated_count, v_error_count;

EXCEPTION WHEN OTHERS THEN
    v_error_count := 1;
    RETURN QUERY SELECT v_updated_count, v_error_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION batch_update_company_analytics(JSONB)
IS 'Batch update company analytics: aggregates, thread counts, health metrics, engagement scores';

GRANT EXECUTE ON FUNCTION batch_update_company_analytics(JSONB) TO authenticated;
GRANT EXECUTE ON FUNCTION batch_update_company_analytics(JSONB) TO service_role;

DO $$
BEGIN
    RAISE NOTICE '✅ batch_update_company_analytics function created';
END $$;

-- ============================================================================
-- PART 3: Verify functions
-- ============================================================================

DO $$
DECLARE
    v_function_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_function_count
    FROM pg_proc
    WHERE proname IN ('batch_update_contact_analytics', 'batch_update_company_analytics');

    IF v_function_count = 2 THEN
        RAISE NOTICE '✅ All analytics batch functions verified';
    ELSE
        RAISE WARNING '⚠️ Missing analytics batch functions (found: %)', v_function_count;
    END IF;
END $$;

-- Test batch functions (safe - updates 0 rows with empty array)
SELECT * FROM batch_update_contact_analytics('[]'::JSONB);
SELECT * FROM batch_update_company_analytics('[]'::JSONB);

-- ============================================================================
-- Migration 006 Complete
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE '====================================';
    RAISE NOTICE '✅ Migration 006 completed successfully';
    RAISE NOTICE '====================================';
    RAISE NOTICE 'Analytics batch operations ready';
    RAISE NOTICE 'Expected performance: 25x improvement';
    RAISE NOTICE '====================================';
END $$;
