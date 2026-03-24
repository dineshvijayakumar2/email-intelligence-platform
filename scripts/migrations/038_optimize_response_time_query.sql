-- ============================================================================
-- Migration 038: Optimize contact response time calculation
-- ============================================================================
-- The calculate_all_contact_response_times() RPC was timing out under load.
-- Root cause: JOIN to customer_contacts for client_id filter forces a full
-- table scan on email_response_metrics.
--
-- Fix:
-- 1. Covering index on (responder_contact_id, is_auto_reply) INCLUDE (response_time_seconds)
--    → enables index-only scan for the GROUP BY + AVG
-- 2. Rewrite function to use a semi-join (WHERE IN subquery) instead of JOIN
--    → PostgreSQL can use the index on customer_contacts(client_id) first,
--    then do a fast index lookup on email_response_metrics
-- ============================================================================

-- 1. Covering index for the aggregation
-- Note: CONCURRENTLY not supported in Supabase SQL editor (runs inside transaction)
CREATE INDEX IF NOT EXISTS idx_erm_contact_response_covering
    ON email_response_metrics (responder_contact_id, is_auto_reply)
    INCLUDE (response_time_seconds)
    WHERE responder_contact_id IS NOT NULL AND is_auto_reply = FALSE;

-- 2. Rewrite function with semi-join instead of full JOIN
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
        AVG(erm.response_time_seconds)::INTEGER,
        AVG(erm.response_time_seconds)::INTEGER
    FROM email_response_metrics erm
    WHERE erm.is_auto_reply = FALSE
      AND erm.responder_contact_id IS NOT NULL
      AND erm.responder_contact_id IN (
          SELECT cc.id FROM customer_contacts cc WHERE cc.client_id = p_client_id
      )
    GROUP BY erm.responder_contact_id;
END;
$$ LANGUAGE plpgsql;
