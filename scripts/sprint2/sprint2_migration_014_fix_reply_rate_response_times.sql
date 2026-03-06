-- ============================================================================
-- Sprint 2 Migration 014: Fix Reply Rate & Response Time Direction
-- ============================================================================
-- Purpose: Fix two calculation bugs:
--   1. Reply rate counted ALL response metrics (both directions) instead of
--      only our outbound replies to their inbound emails
--   2. Response times were identical for both directions instead of being
--      separated into our avg vs their avg
-- Run After: sprint2_migration_013_outlook_rules_mailbox_id.sql
-- Duration: <1 minute
-- ============================================================================

-- PART 1: Fix reply rate calculation
-- ============================================================================
-- Before: counted ALL email_response_metrics rows for contact (both directions)
-- After:  only counts rows where responding email is outbound (our reply)

CREATE OR REPLACE FUNCTION calculate_all_contact_reply_rates(
    p_client_id UUID
) RETURNS TABLE (
    contact_id UUID,
    reply_rate NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    WITH our_replies AS (
        -- Count our outbound replies to this contact's inbound emails
        -- Join to emails table to check the direction of the responding email
        SELECT
            erm.responder_contact_id,
            COUNT(*) as reply_count
        FROM email_response_metrics erm
        JOIN customer_contacts cc ON cc.id = erm.responder_contact_id
        JOIN emails e ON e.id = erm.email_id  -- The responding email
        WHERE cc.client_id = p_client_id
          AND erm.is_auto_reply = FALSE
          AND e.is_outbound = TRUE  -- Only our outbound replies
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
                    COALESCE(r.reply_count, 0)::NUMERIC / ci.total_inbound,
                    3
                )
            ELSE 0
        END as reply_rate
    FROM contact_inbound ci
    LEFT JOIN our_replies r ON r.responder_contact_id = ci.customer_contact_id;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    RAISE NOTICE '✅ calculate_all_contact_reply_rates fixed (direction-aware)';
END $$;

-- ============================================================================
-- PART 2: Fix response time calculation to separate directions
-- ============================================================================
-- Before: avg_response_time_seconds = their_avg_response_time = same average
-- After:  avg_response_time_seconds = OUR avg (outbound replies to inbound)
--         their_avg_response_time = THEIR avg (inbound replies to outbound)

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
        -- Our avg response time: outbound replies (we replied to their inbound)
        AVG(erm.response_time_seconds) FILTER (WHERE e.is_outbound = TRUE)::INTEGER as avg_response_time,
        -- Their avg response time: inbound replies (they replied to our outbound)
        AVG(erm.response_time_seconds) FILTER (WHERE e.is_outbound = FALSE)::INTEGER as their_avg_response_time
    FROM email_response_metrics erm
    JOIN customer_contacts cc ON cc.id = erm.responder_contact_id
    JOIN emails e ON e.id = erm.email_id  -- The responding email
    WHERE cc.client_id = p_client_id
      AND erm.is_auto_reply = FALSE
      AND erm.responder_contact_id IS NOT NULL
    GROUP BY erm.responder_contact_id;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    RAISE NOTICE '✅ calculate_all_contact_response_times fixed (direction-separated)';
END $$;

-- ============================================================================
-- PART 3: Verify
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE '====================================';
    RAISE NOTICE '✅ Migration 014 completed';
    RAISE NOTICE '====================================';
    RAISE NOTICE 'Reply rate: now counts only our outbound replies';
    RAISE NOTICE 'Response times: separated our avg vs their avg';
    RAISE NOTICE '====================================';
    RAISE NOTICE 'NOTE: Re-run extraction to recalculate values';
    RAISE NOTICE '====================================';
END $$;
