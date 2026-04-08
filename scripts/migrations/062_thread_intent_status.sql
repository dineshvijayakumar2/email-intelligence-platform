-- Migration 062: Thread Intent-Based Status
--
-- Adds intent intelligence to thread_status for smarter thread classification.
-- The timing-based status (ongoing, awaiting_our_response, etc.) is supplemented
-- by intent-based signals from AI email intelligence.
--
-- Example: A "thank you" email (positive_feedback intent) shouldn't keep a thread
-- in "awaiting_our_response". A "complaint" should escalate to urgent.

-- New columns on thread_status
ALTER TABLE thread_status
    ADD COLUMN IF NOT EXISTS intent_status TEXT,
    ADD COLUMN IF NOT EXISTS intent_override_reason TEXT,
    ADD COLUMN IF NOT EXISTS last_email_intent TEXT,
    ADD COLUMN IF NOT EXISTS last_email_urgency TEXT,
    ADD COLUMN IF NOT EXISTS last_email_sentiment TEXT;

-- Intent status values: NULL (no override), urgent, revenue_opportunity,
-- closing, escalation, informational
COMMENT ON COLUMN thread_status.intent_status IS
    'Intent-based status override: urgent, revenue_opportunity, closing, escalation, informational. NULL = use timing status.';

-- Index for intent-based filtering
CREATE INDEX IF NOT EXISTS idx_thread_status_intent
    ON thread_status (intent_status) WHERE intent_status IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_thread_status_last_intent
    ON thread_status (last_email_intent) WHERE last_email_intent IS NOT NULL;
