-- ============================================================================
-- Migration 078: Thread override rules — Group D (existing-but-rule-less intents)
-- ============================================================================
--
-- Transactional — safe to run in Supabase SQL Editor.
--
-- ─── Purpose ───────────────────────────────────────────────────────────────
-- Migration 077 seeded 5 override rules matching the original Python
-- _apply_intent_override. However, the AI classifier (ai_email_analyzer)
-- already emits several intent values that had NO corresponding rule — so
-- those signals were invisible to the UI / agent / digest even though the
-- AI was producing them.
--
-- Specifically:
--   quote_request       (394 classifications, unused)
--   production_blocker  (153 classifications, unused)
--   payment_query       (327 classifications, unused)
--   buying_signal        (94 classifications, unused)
--
-- This migration adds rules that consume those signals and project them into
-- effective status. No AI prompt changes required — all four intents are
-- already in the classifier output.
--
-- ─── Rules added ───────────────────────────────────────────────────────────
--   quote_request_revenue_opp       (priority 21) quote_request -> revenue_opportunity
--   production_blocker_urgent       (priority 11) production_blocker -> urgent
--   payment_query_escalation        (priority 41) payment_query on non-ongoing/complete -> escalation
--   buying_signal_revenue_opp       (priority 22) buying_signal -> revenue_opportunity
--
-- Priority choice rationale:
--   Urgent rules cluster at priority 10-11. Production blocker is in the
--   same semantic space as complaint/critical_urgency but slightly lower in
--   case both fire simultaneously (complaint rule wins).
--   Revenue-opportunity rules cluster at 20-22.
--   Escalation rules cluster at 40-41.
--
-- payment_query is conditional on timing: if the thread is already "ongoing"
-- (active back-and-forth) or "complete", we're probably handling it already —
-- escalation would be spammy. Escalation only fires on stalled threads.
--
-- ─── Verification ──────────────────────────────────────────────────────────
-- After this migration applies, test_thread_status_engine.py B1 must be
-- updated to include these 4 new rules in its fixture, or it will fail
-- (because the DB will have 9 rules vs fixture's 5). The test file is
-- updated in the same commit as this migration.
--
-- ROLLBACK:
--   DELETE FROM thread_status_override_rules WHERE name IN (
--     'quote_request_revenue_opp', 'production_blocker_urgent',
--     'payment_query_escalation', 'buying_signal_revenue_opp'
--   );
-- ============================================================================

INSERT INTO thread_status_override_rules
    (name, description, priority, when_timing_in, when_timing_not_in,
     when_intent_in, when_urgency_in, effective_status_becomes, reason_template)
VALUES
    (
        'quote_request_revenue_opp',
        'Quote request detected -- active sales signal, promote to revenue_opportunity.',
        21, NULL, NULL,
        ARRAY['quote_request'], NULL,
        'revenue_opportunity',
        'Quote request received'
    ),
    (
        'production_blocker_urgent',
        'Production blocker detected -- operational fire, needs urgent triage.',
        11, NULL, NULL,
        ARRAY['production_blocker'], NULL,
        'urgent',
        'Production blocker reported'
    ),
    (
        'payment_query_escalation',
        'Payment / AR query on a thread we are not actively engaged in. '
        'Stalled or pre-completion payment questions need to be addressed. '
        'Not triggered when the thread is "ongoing" (active back-and-forth) '
        'or "complete" (already resolved).',
        41, NULL, ARRAY['ongoing', 'complete'],
        ARRAY['payment_query'], NULL,
        'escalation',
        'Payment query requires attention (thread state: {timing_status})'
    ),
    (
        'buying_signal_revenue_opp',
        'Buying signal detected by AI -- promote to revenue_opportunity.',
        22, NULL, NULL,
        ARRAY['buying_signal'], NULL,
        'revenue_opportunity',
        'Buying signal detected'
    )
ON CONFLICT (name) DO NOTHING;

-- Invalidate the Redis cache marker so the engine reloads rules on the next
-- evaluator run. (The Python-side cache is advisory; rules are always
-- authoritative in the DB — this just avoids a 60s lag.)
-- Done in the app via thread_status_engine.invalidate_rules_cache().
