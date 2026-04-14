-- ============================================================================
-- Migration 079: Thread override rules — 3 unambiguous intent additions
-- ============================================================================
--
-- Transactional — safe to run in Supabase SQL Editor.
--
-- ─── Purpose ───────────────────────────────────────────────────────────────
-- After Group D (migration 078) unlocked existing-but-rule-less intents,
-- we considered additional intents for marketing/CRM/customer management.
-- Most candidates (inbound_lead, renewal_discussion, referral_introduction,
-- etc.) were cut as too ambiguous for reliable AI classification —
-- two classifiers would disagree on boundaries.
--
-- These 3 survived the "unambiguous" bar. Each has clear linguistic markers
-- that a single AI prompt can reliably detect:
--
--   cancellation_intent        — explicit wording "cancel account",
--                                 "terminate service", "close our account"
--   escalation_to_management   — explicit request for "manager", "supervisor",
--                                 "senior person", "take this to your boss"
--   legal_or_compliance        — mentions lawsuit, legal, GDPR, contract,
--                                 liability, compliance audit, indemnity
--
-- All 3 map to `urgent` effective status — they each represent signals that
-- require immediate human attention regardless of thread state.
--
-- ─── Companion work (NOT in this migration) ────────────────────────────────
-- The AI classifier prompt (ai_prompt_config.prompt_key = 'email_analysis_user')
-- must also be updated to produce these 3 intent values. Without the prompt
-- update, these rules exist but never fire because the AI never classifies
-- any email as `cancellation_intent` etc.
-- Prompt updates are applied via a companion Python script since client-
-- specific prompts exist per-client and are not well-suited to SQL.
--
-- ─── Priority rationale ────────────────────────────────────────────────────
-- All 3 at priority 12 (below production_blocker at 11, below the two
-- hard-urgent rules at 10 — complaint, high-critical-urgency). This means
-- if a customer sends a complaint that also contains cancellation_intent,
-- the earlier complaint rule fires first, but both produce `urgent` so the
-- effective status is the same either way.
--
-- ROLLBACK:
--   DELETE FROM thread_status_override_rules WHERE name IN (
--     'cancellation_intent_urgent',
--     'escalation_to_management_urgent',
--     'legal_or_compliance_urgent'
--   );
-- ============================================================================

INSERT INTO thread_status_override_rules
    (name, description, priority, when_timing_in, when_timing_not_in,
     when_intent_in, when_urgency_in, effective_status_becomes, reason_template)
VALUES
    (
        'cancellation_intent_urgent',
        'Customer explicitly requesting to cancel account / terminate service. '
        'High save-opportunity signal — needs immediate human attention.',
        12, NULL, NULL,
        ARRAY['cancellation_intent'], NULL,
        'urgent',
        'Cancellation requested'
    ),
    (
        'escalation_to_management_urgent',
        'Customer explicitly asking to speak with a manager / supervisor / '
        'senior person. A sign the AM-level conversation has hit a limit.',
        12, NULL, NULL,
        ARRAY['escalation_to_management'], NULL,
        'urgent',
        'Escalation to management requested'
    ),
    (
        'legal_or_compliance_urgent',
        'Customer email mentions legal action, lawsuits, GDPR, liability, '
        'compliance audits, or similar regulated topics. Always needs human '
        'review — AI responses alone are risky.',
        12, NULL, NULL,
        ARRAY['legal_or_compliance'], NULL,
        'urgent',
        'Legal or compliance matter raised'
    )
ON CONFLICT (name) DO NOTHING;
