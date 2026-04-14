-- ============================================================================
-- Migration 077: Thread status — effective_status + data-driven override rules
-- ============================================================================
--
-- ⚠️  REQUIRES HUMAN REVIEW BEFORE EXECUTION.
--     Transactional — safe to run in Supabase SQL Editor.
--
-- ─── Design ────────────────────────────────────────────────────────────────
-- Previously `thread_status.status` held a timing-derived value and
-- `intent_status` held a parallel AI-derived signal. The UI/digest/agent
-- consumers read both and had to reconcile themselves. Behaviour promised
-- in the platform spec ("thank-you emails don't keep threads stuck in
-- awaiting response") was never delivered — the Python helper named
-- `_apply_intent_override` explicitly supplements rather than overrides.
--
-- This migration aligns the schema with the intended semantics:
--
--   status           → EFFECTIVE thread status (post-override). This is the
--                       field every consumer should read by default.
--   timing_status    → NEW: the raw mechanical signal (pre-override).
--                       Audit trail. Consumers that need "has this thread
--                       been sitting for N days regardless of intent" read
--                       this column.
--   intent_status,
--   last_email_intent,
--   last_email_urgency,
--   last_email_sentiment  → UNCHANGED. Raw AI signals, preserved.
--   override_rule_id → NEW: references which rule fired. Null if no override.
--
-- Override rules move from hardcoded Python (thread_tracker._apply_intent_override)
-- to the new table `thread_status_override_rules`. Each rule is a row. The
-- Python evaluator loads all enabled rules once per evaluator run and applies
-- them in priority order (lower priority number = fires first).
--
-- ─── Backfill strategy ─────────────────────────────────────────────────────
-- For existing rows:
--   1. Copy current `status` into `timing_status` (the raw value exactly as
--      it was — it was already the timing-derived value).
--   2. Do NOT modify `status` itself. The refactored evaluator will compute
--      the new effective value on its next run and write back.
--   3. `override_rule_id` stays NULL until the evaluator recomputes.
--
-- The next thread evaluator run will populate the new semantics for every
-- thread. No need to trigger a full recompute from this migration — it
-- happens naturally during the next extraction cycle (which already calls
-- thread evaluation).
--
-- ─── Rule seed ─────────────────────────────────────────────────────────────
-- Six rules, derived 1:1 from thread_tracker._apply_intent_override:
--   1. complaint_or_churn_urgent       (priority 10)
--   2. high_critical_urgency_urgent    (priority 10)
--   3. pricing_signal_revenue_opp      (priority 20)
--   4. positive_feedback_closing       (priority 30)
--   5. action_required_escalation      (priority 40)
--   6. (Rule "informational" is metadata-only, not persisted here.
--       Handled separately in Python as a simple dict lookup; it does NOT
--       alter effective_status.)
--
-- Behavior must match current Python semantics 1:1. Integration test
-- "seed_rules_match_legacy_python" verifies this. If that test fails, this
-- migration has diverged and must be fixed BEFORE the Python refactor ships.
--
-- ROLLBACK:
--   DROP TABLE IF EXISTS thread_status_override_rules;
--   ALTER TABLE thread_status DROP COLUMN IF EXISTS timing_status;
--   ALTER TABLE thread_status DROP COLUMN IF EXISTS override_rule_id;
--   (The `status` column stays — only its semantics change at the Python
--   layer, not the column itself.)
-- ============================================================================

-- ── 1. New columns on thread_status ────────────────────────────────────────

ALTER TABLE thread_status
    ADD COLUMN IF NOT EXISTS timing_status TEXT;

ALTER TABLE thread_status
    ADD COLUMN IF NOT EXISTS override_rule_id UUID;

COMMENT ON COLUMN thread_status.timing_status IS
  'Raw timing-derived status (pre-override). ''status'' column is the effective '
  'value after override rules are applied.';
COMMENT ON COLUMN thread_status.override_rule_id IS
  'If an override rule fired for this thread, the rule''s id. NULL if no override.';
COMMENT ON COLUMN thread_status.status IS
  'EFFECTIVE thread status (post-override). Consumers read this by default. '
  'Raw timing signal is in timing_status column.';

-- Backfill timing_status for existing rows — they were computed under
-- the old semantics where status == timing (no override was ever applied).
UPDATE thread_status
SET timing_status = status
WHERE timing_status IS NULL;

-- ── 2. Override rules table ────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS thread_status_override_rules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL UNIQUE,
    description TEXT,

    -- Priority: lower number fires first. Rules are evaluated in ascending
    -- priority order; first match wins (matches current Python if/elif logic).
    priority INTEGER NOT NULL,

    -- Match conditions. NULL/empty array = field not a condition for this rule.
    -- A rule matches iff every non-NULL condition passes.
    when_timing_in     TEXT[],   -- e.g. {'awaiting_response','awaiting_our_response'}
    when_timing_not_in TEXT[],   -- e.g. {'ongoing'} for "anything except ongoing"
    when_intent_in     TEXT[],   -- e.g. {'complaint','churn_risk'}
    when_urgency_in    TEXT[],   -- e.g. {'critical','high'}

    -- Effect: the status value to set when this rule matches.
    effective_status_becomes TEXT NOT NULL,

    -- Template for the reason field. Uses Python str.format syntax.
    -- Available variables: {intent}, {urgency}, {sentiment}, {timing_status}.
    reason_template TEXT,

    -- Operational
    enabled    BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Fast lookup of enabled rules ordered by priority
CREATE INDEX IF NOT EXISTS idx_thread_override_rules_priority
  ON thread_status_override_rules(priority)
  WHERE enabled = TRUE;

COMMENT ON TABLE thread_status_override_rules IS
  'Data-driven rules for computing effective thread status from timing+intent '
  'signals. Loaded by thread_tracker at evaluator init. Priority ASC = fires first.';

-- Auto-update updated_at on row change
CREATE OR REPLACE FUNCTION tsor_touch_updated_at() RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_tsor_touch_updated_at ON thread_status_override_rules;
CREATE TRIGGER trg_tsor_touch_updated_at
    BEFORE UPDATE ON thread_status_override_rules
    FOR EACH ROW EXECUTE FUNCTION tsor_touch_updated_at();

-- ── 3. Seed rules — 1:1 with thread_tracker._apply_intent_override ─────────
--
-- The original Python rules are:
--   if intent in (complaint, churn_risk) or urgency in (critical, high):
--       urgent
--   elif intent in (pricing_inquiry, expansion_signal, feature_request):
--       revenue_opportunity
--   elif intent in (positive_feedback, fyi_update) and status in (awaiting_*):
--       closing
--   elif intent == action_required and status != ongoing:
--       escalation
--
-- OR semantics (complaint OR high urgency → urgent) require splitting into
-- two rules with the same priority and same output.

INSERT INTO thread_status_override_rules
    (name, description, priority, when_timing_in, when_timing_not_in,
     when_intent_in, when_urgency_in, effective_status_becomes, reason_template)
VALUES
    (
        'complaint_or_churn_urgent',
        'Complaint or churn_risk intent → urgent, regardless of timing.',
        10, NULL, NULL,
        ARRAY['complaint', 'churn_risk'], NULL,
        'urgent',
        'Last email intent: {intent}'
    ),
    (
        'high_critical_urgency_urgent',
        'High or critical urgency → urgent, regardless of intent or timing.',
        10, NULL, NULL,
        NULL, ARRAY['critical', 'high'],
        'urgent',
        'Last email urgency: {urgency}'
    ),
    (
        'pricing_signal_revenue_opp',
        'Pricing / expansion / feature signals → revenue_opportunity.',
        20, NULL, NULL,
        ARRAY['pricing_inquiry', 'expansion_signal', 'feature_request'], NULL,
        'revenue_opportunity',
        'Last email shows {intent}'
    ),
    (
        'positive_feedback_closing',
        'Positive feedback or FYI on an awaiting thread → closing (the '
        '"thank-you email doesn''t keep threads stuck" rule).',
        30,
        ARRAY['awaiting_response', 'awaiting_our_response'], NULL,
        ARRAY['positive_feedback', 'fyi_update'], NULL,
        'closing',
        'Last email is {intent} — thread naturally concluding'
    ),
    (
        'action_required_escalation',
        'Contact requires action AND we are not actively engaged → escalation.',
        40, NULL, ARRAY['ongoing'],
        ARRAY['action_required'], NULL,
        'escalation',
        'Action required by contact, current status: {timing_status}'
    )
ON CONFLICT (name) DO NOTHING;

-- ── 4. Grants ──────────────────────────────────────────────────────────────

GRANT SELECT ON thread_status_override_rules TO anon, authenticated;
-- Writes are service-role only — rule tuning is an admin action.
