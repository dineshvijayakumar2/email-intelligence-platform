-- ============================================================================
-- Migration 080: Expand thread_status.status CHECK constraint for override values
-- ============================================================================
-- Migration 077 introduced the override engine — `status` now holds the
-- EFFECTIVE status (post-override), which can be: urgent, revenue_opportunity,
-- closing, escalation (in addition to all timing values).
--
-- The CHECK constraint was never updated, so EVERY override save has been
-- silently rejected with constraint violation 23514. This is why the
-- platform has 0 threads with override_rule_id set despite the engine
-- being correct and the rules table populated.
-- ============================================================================

ALTER TABLE thread_status DROP CONSTRAINT IF EXISTS thread_status_status_check;

ALTER TABLE thread_status ADD CONSTRAINT thread_status_status_check
CHECK (status = ANY (ARRAY[
    -- Timing-only statuses (also valid as effective when no override fires)
    'complete'::text,
    'awaiting_reply'::text,
    'awaiting_response'::text,
    'awaiting_our_response'::text,
    'outbound_pending'::text,
    'ongoing'::text,
    'stale'::text,
    'overdue'::text,
    'dropped'::text,
    -- Override-only effective statuses (post-engine values)
    'urgent'::text,
    'revenue_opportunity'::text,
    'closing'::text,
    'escalation'::text
]));
