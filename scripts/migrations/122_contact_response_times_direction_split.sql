-- 122: contact response-time rollup — fix direction-collapse + PostgREST 1000-row cap.
--
-- Two bugs in the old calculate_all_contact_response_times (migration 038):
--   1. PostgREST db-max-rows cap: the RPC RETURNS TABLE, so the Python caller only
--      ever received the first 1000 rows. Carbon8 has 21,655 contacts -> only 1000
--      contacts ever got their avg_response_time updated. (Same class as 120/121.)
--   2. Direction collapse: both avg_response_time_seconds and their_avg_response_time
--      were computed from the identical AVG(response_time_seconds) with no is_outbound
--      split, so "our reply time" and "their reply time" were the same number —
--      contradicting the Python _calculate_contact_response_times, which splits them.
--
-- Fix: a single function that does the aggregation AND the UPDATE server-side and
-- returns just the affected-row count. Doing the UPDATE in SQL sidesteps the row cap
-- entirely (no result set is paged to the client), and the FILTER clauses restore the
-- direction split:
--   * responding email outbound  -> WE replied to them -> avg_response_time_seconds
--   * responding email inbound   -> THEY replied to us -> their_avg_response_time
-- COALESCE preserves an existing value when a contact has data for only one direction
-- (matching the old batch_update_contact_analytics behaviour).

CREATE OR REPLACE FUNCTION update_all_contact_response_times(p_client_id UUID)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET statement_timeout = '180s'
AS $$
DECLARE
    v_updated INTEGER := 0;
BEGIN
    WITH agg AS (
        SELECT
            erm.responder_contact_id AS contact_id,
            AVG(erm.response_time_seconds) FILTER (WHERE e.is_outbound IS TRUE)::INTEGER  AS our_avg,
            AVG(erm.response_time_seconds) FILTER (WHERE e.is_outbound IS FALSE)::INTEGER AS their_avg
        FROM email_response_metrics erm
        JOIN emails e ON e.id = erm.email_id
        WHERE erm.is_auto_reply = FALSE
          AND erm.responder_contact_id IS NOT NULL
          AND erm.responder_contact_id IN (
              SELECT cc.id FROM customer_contacts cc WHERE cc.client_id = p_client_id
          )
        GROUP BY erm.responder_contact_id
    )
    UPDATE customer_contacts c
    SET avg_response_time_seconds = COALESCE(agg.our_avg, c.avg_response_time_seconds),
        their_avg_response_time   = COALESCE(agg.their_avg, c.their_avg_response_time),
        updated_at = NOW()
    FROM agg
    WHERE c.id = agg.contact_id;

    GET DIAGNOSTICS v_updated = ROW_COUNT;
    RETURN v_updated;
END;
$$;

GRANT EXECUTE ON FUNCTION update_all_contact_response_times(UUID) TO authenticated, service_role;

-- Retire the superseded, buggy function (only caller was update_contact_averages).
DROP FUNCTION IF EXISTS calculate_all_contact_response_times(UUID);
