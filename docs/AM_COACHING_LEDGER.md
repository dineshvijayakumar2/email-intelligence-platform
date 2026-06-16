# AM Coaching Project Ledger — operational tracking

> **Single source of truth for the AM-Coaching / Communication-Quality workstream.**
> Separate from OUTREACH_PROJECT_LEDGER.md (that's the cards/cross-sell track).
> Update cadence: once or twice a day, NOT per-turn.
> Status: 🔜 next / 🔄 running / ✅ done / ⏸ held / 📌 parked
> Numbering: prompts prefixed by day (15.x = 15 Jun).
> Created: 15 June 2026.

---

## CONTEXT & AIM

**Dinesh's two stated goals:**
1. Management understands who is doing a great job.
2. AMs get usable insights to improve their communication style and win more revenue.

**Standing principle:** build IN THE PLATFORM (API + UI), not a throwaway PDF, so it's MVP-ready. The compute/data layer is the substance and is identical whether surfaced as PDF or UI; build it as a real service with an endpoint.

**Design doc:** `docs/design/AM_QUALITY_LAYER_DESIGN.md` (research-grounded dimensions + the §10.12 pilot).

**Honest tension recorded:** structural metrics measure ACTIVITY, not QUALITY. A management "who's great" ranking built on activity alone rewards busyness and can mis-judge an AM (esp. with the fairness artifacts below). So the management comparative view waits until the content-quality layer (Tier B) is VALIDATED. AM-assist (self-referential) leads — it's safe + useful now.

---

## RESEARCH BASIS (web research 15 Jun — grounds the dimensions, not guesses)
- **Gong Labs:** email velocity is the single best close predictor (won ~8.2 emails/wk vs lost ~1.87); multithreading critical; "feature dumping sinks win rates"; short/closed customer replies = disengagement.
- **Consultative-selling literature:** ask discovery questions + understand needs BEFORE recommending ("stop pitching, start helping"); 86% of buyers more likely to buy when seller understands their goals, 59% say reps don't; reps systematically under-ask open questions; failure mode = feature-led/generic pitches.

---

## DIMENSIONS (grounded, split by data support)

**Tier A — STRUCTURAL (compute now, no extraction):** exchange velocity · responsiveness (latency, mig-122) · multithreading (distinct contacts/company) · follow-up persistence. Highest-evidence, ready.

**Tier B — CONTENT (new LLM pass over OUTBOUND bodies; PILOT before scale):** discovery/question-asking · consultative-vs-feature-dumping · answer-responsiveness. This is "use the body text better" — grounded in the research.

**Excluded v1 (low ROI / not grounded / risky):** sentiment trajectory (data degenerate), generic tone/warmth (vague, hollow-risk), personality scoring (not coachable/defensible).

---

## FAIRNESS GUARDS (from 12.3, non-negotiable for any comparison)
- Common time cut-off (Ehab's mailbox trailed ~3wk — don't penalize a data artifact).
- Volume-normalize (CV 1.14–3.1 across AMs).
- Mary/Peter have NO mailbox → email-quality excluded; QB-outcome track only.
- Self-referential framing (vs own baseline) for AM-assist sidesteps cross-AM unfairness.

---

## BUILD ORDER & STATUS

- **15.1 — Readiness refresh (audit current state) — ✅ DONE (read-only, `am_coaching_readiness_refresh.json`).** Findings vs 12.3:
  - **Latency FIXED:** mig-122 backfill ran; Nic recovered 1,001→8,431 exactly as predicted; all 4 AMs now 55–72% of inbound. No longer a Tier-A blocker.
  - **CV lumpiness was an ARTIFACT:** trailing-12mo CV is 0.41–0.62 (even) for all 4; the 12.3 figures of 1.14–3.1 were all-history (ramp-up + stale trailing month). Volume-normalization = cheap insurance now, not heavy lifting.
  - **⚠️ NEW DOMINANT FAIRNESS ISSUE — two mailboxes STALLED:** Ehab no movement since 2026-05-21 (356/30d); **Kenneth sync DIED ~2026-05-16 (9 emails/30d).** Nic + Linda current (06-15). **A management comparison today would make Ehab/Kenneth look 'gone quiet' from a DATA artifact, not behavior — the exact §10.13 trap. Stalled syncs are a PREREQUISITE to fix before 15.5.**
  - **Tier-A: all 5 features computable now.** Multithreading avg 1.68–1.77 contacts/company, only 25–30% of companies have 2+ contacts engaged → real coaching headroom (Gong flags single-threading as deal risk).
  - **Tier-B pilot well-resourced:** 4,792 linked threads (3,115 won / 1,677 lost), 25× the design minimum. Nic/Linda/Ehab ample individually; Kenneth thin (65/28) but fine pooled. **Sampling caveat (§10.13): a thread = 'won' if linked to ANY won quote → inflates won share → SAMPLE WON & LOST STRATA SEPARATELY, not from the mixed pool.**

- **15.1b — Fix stalled mailbox syncs (Ehab, Kenneth) — 🔜 PREREQUISITE for 15.5 (management view), NOT for self-view/pilot.** Two Outlook mailboxes stopped mid-May (Ehab ~05-21, Kenneth ~05-16). Data-pipeline issue, independent of the coaching build. Investigate why + restore. Until fixed: any cross-AM comparison must cut at ~2026-05-16 OR explicitly flag both stale, and must NOT be management-facing.

- **15.2 — Tier-A structural compute layer + API endpoint — ✅ DONE (on `main`, verified vs live).** Migration 126 (`am_structural_metrics` RPC, server-side §10.11, applied), `am_coaching_service.py`, `GET /ai/coaching/am/{am_id}/structural`, mailbox-scoped auth. Self-referential only (no cross-AM ranking). Both checkpoints PASS: reproduces 15.1 audit (multithreading 1.64–1.71); staleness fires for Ehab (25d)/Kenneth (30d) with trend labeled UNRELIABLE so stalled syncs can't read as 'gone quiet'. Mary/Peter → `email_coachable=false` (no zeros). Per-AM headline captured in chat.
  - **Responsiveness caveats:** (a) **business-hours latency — ✅ FIXED separately:** root cause was tz read from `user_profiles.timezone='UTC'` not `clients.timezone`; backlog recomputed (`_recompute_bh_response_time.py`, 72,176 rows, 13.4%→94.3% positive-bh, idempotent) AND source fixed (`response_time_tracker.py` now reads `clients.timezone`); `business_hours_reliable` flips true (Nic 98.6/Linda 88.7/Ehab 95.2/Kenneth 94.5). Documented HOW_IT_WORKS §2.15 + memory. Known minor: `am_efficiency_analyzer.py` uses 9–17 window + non-DST fixed-offset fallback (logged, out of scope). (b) **raw-latency plausibility — STILL OPEN → 15.3b.**

- **15.3 — Tier-B content PILOT (§10.12 gate) — ✅ DONE (read-only, on `main`, $0.86). VERDICT: STOP — all 3 dimensions HOLLOW. Do NOT scale Tier-B content extraction.** The cheap gate did its job: a strong gpt-4o judge means the null is TRUSTWORTHY, not a weak-scorer artifact. Report: `docs/data-insights/tier_b_pilot_validation_2026-06-16.md`. Scripts `_tier_b_pilot_{sample,score,analyze}.py`.
  - **Sample:** 100 won + 100 lost, outbound AM emails, sampled SEPARATELY (15.1 caveat); confound controlled BY CONSTRUCTION via matched (AM×outbound-bucket) cells (mean n_out 2.51 vs 2.59). Nic/Linda/Ehab. Blind scoring, OpenAI gpt-4o (Anthropic key out of credits → use OpenAI), 1-5 + evidence span. 200/200 scored, 0 failures.
  - **Gate (won vs lost, Cliff's δ [95% CI], MWU p):** discovery δ=−0.02 [−0.09,+0.05] p=0.54 (95% floored at 1); consultative δ=−0.01 [−0.10,+0.08] p=0.87 (87% floored at 1); answer_responsiveness δ=+0.02 [−0.13,+0.18] p=0.77 (has variance, but NO outcome link). **All negligible, all CIs straddle 0, none significant. Won≈lost on all three.**
  - **Length confound checked:** scores rise weakly with length (Spearman 0.21–0.48) but stratified within-cell δ ≈ 0 (−0.02/−0.00/+0.04) → no signal hidden behind OR coming from length.
  - **WHY (scorer trustworthy — §10.13 spot-check confirms calibration, NOT default-to-1):** correctly finds rare real instances (Ehab "Do you have a budget in mind" → discovery 3; Linda "has to be 4pp sections for the folding" → consultative 4; precise spec answer → responsiveness 5; "Thanks Karl" → 1). The **floor is REAL**: Carbon8's quote-linked email is transactional (quotes/artwork/proofs/approvals/invoices); consultative selling barely occurs, in won AND lost. Some MOST-consultative threads were LOST; many WON were pure logistics.
  - **Key limitation (honest):** quote-linkage selects EXECUTION threads; consultative *selling* likely lives in PRE-quote threads (not quote-linked) or off-email (phone). Proves content quality doesn't predict winning *in the quote-linked email channel* — NOT that consultative selling is irrelevant. Redesign path if ever revisited: target pre-quote/early-relationship threads, re-run this same cheap gate FIRST before scaling.
  - **Decisions:** don't scale Tier-B; DROP discovery + consultative (floored); do NOT ship answer_responsiveness as a win signal (no outcome link; also caveated by 15.3b mis-pairs + one-line-ack framing). **Resolves the open decision: 15.4 surfaces STRUCTURAL-ONLY, no content layer.** Lead coaching with Tier-A structural (15.2), self-referential.

- **15.3b — Raw-latency plausibility check — ✅ DONE (read-only). VERDICT: two different stories — Nic/Linda genuine, Kenneth/Ehab artifacts.** Repro mirrored the metric's exact population. Distribution + full classification of the sub-5-min cluster:
  - **Nic genuine** (median ~18min, 93% same-thread pairs — real terse acks). **Linda genuine** (~6min, 95% same-thread; 46% sub-5min is real fast acks). Trustworthy as-is.
  - **Kenneth NOT trustworthy** (69% of pairs are threading MIS-PAIRS — inbound about convo A paired with unrelated outbound about convo B; true median ~5× higher, 0.094h→0.479h). **Ehab NOT trustworthy** (75% mis-pairs; headline 0.038h mostly artifact). Examples unmistakable (Kenneth: IN 'Flash Courier'→OUT 'FW: Your Uber trip'; Ehab: IN 'Q708209 Annual Report'→OUT 'Emily Ziz PO samples'). 0% NULL-thread — the paired emails HAVE canonical threads and they DIFFER.
  - **ROOT CAUSE (same lesson again):** tracker (`response_time_tracker.py:211-334`) pairs on provider `emails.thread_id`, which over-collapses distinct conversations for Kenneth/Ehab's mailboxes (per-mailbox provider/import quality diff). Same 'use canonical_thread_id not the raw/provider field' pattern as `thread_status.mailbox_id`.
  - **FIX (→ 15.3c, fix-the-tap §10.14):** (1) pair within `canonical_thread_id` not provider thread_id; (2) validate each pair (subject-normalized match OR inbound sender ∈ outbound recipients); (3) exclude automated/no-reply/OOO INBOUND from forming pairs (`is_auto_reply` currently only checks the OUTBOUND — missed an OOO inbound); (4) recompute `email_response_metrics`. **A min-gap floor is the WRONG fix** (would discard Nic/Linda's genuine fast acks, miss the over-floor mis-pairs). Pairing-validation is the lever.
  - **⚠️ FRAMING CAVEAT (bigger than the bug, for coaching design):** even after the fix, 'responsiveness' here largely measures speed of ONE-LINE ACKS in a fast print-production workflow, NOT substantive replies. May not deserve much WEIGHT in the coaching surface — a reflexive 'got it' shouldn't outscore a slower deal-advancing reply. Hold until 15.3 pilot reports (the pilot measures the substantive-reply quality responsiveness can't see).

- **15.3c — Tracker pairing fix (canonical thread + pair validation) — ✅ DONE (on `main`, §10.14 fix-the-tap).** 4-step fix applied to `response_time_tracker.py` (durable, also fixes the live pipeline): (1) group/pair within `canonical_thread_id` not provider `thread_id`; (2) validate each pair (`_subjects_match` OR `_reply_addressed_back` — reply addressed to the original sender); (3) exclude auto-reply/OOO + automated/no-reply senders (`AUTOMATED_SENDER_PATTERNS`) from ANCHORING a pair (the responding-to side, which `is_auto_reply` never checked); (4) recompute. Pipeline-safe: `orchestrator._assign_canonical_threads` (step 9) runs before the engagement step (10), so `canonical_thread_id` is populated live.
  - **Recompute:** delete-all-Carbon8 + insert-fresh via the patched tracker (`_recompute_response_metrics_15_3c.py`), 69,099 pairs, 0 errors, contact averages refreshed. Shared `hello` box needed a mailbox-scoped re-clean (`_cleanup_hello_15_3c.py`) — pre-existing data quirk: ~95% of hello@ emails carry a non-CARBON8 `client_id`, so the client-scoped delete missed its stale rows. **Final state: all 7 boxes CLEAN (mailbox count == inserted, delta 0), 0 cross-canonical pairs, 0 null-thread.**
  - **VERIFIED via the production `am_structural_metrics` RPC (trailing-12-mo):** Nic 0.297→0.310h (unchanged, was genuine), Linda 0.099→0.100h (unchanged, genuine), **Kenneth 0.094→0.820h (~49min, 8.7×), Ehab 0.038→0.160h (~9.6min, 4.2×).** All four now plausible. thread_mismatch in the sub-5-min cluster: 77–85%→0 for Kenneth/Ehab. Ehab's residual sub-5-min is `bulk_identical` templated one-liner sends ("Thank you, Regards Ehab") — genuine fast replies, not mis-pairs.
  - **AUDIT — other code sharing the provider-thread bug:** reply-rate/response-time RPCs (sprint2 mig 014) + `am_efficiency_analyzer` consume the now-fixed `email_response_metrics` table → AUTO-CORRECTED. **One independent instance found & NOT yet fixed: `calculate_all_contact_initiation_ratios` (sprint2 mig 009) groups by provider `e.thread_id`** for thread-initiation → under-counts threads / mis-attributes initiation for collision-heavy mailboxes (affects contacts.`initiation_ratio`, lower severity than latency). The legacy Python `comm_pattern_analyzer._calculate_initiation_ratio` / `_calculate_avg_thread_depth` also use `thread_id` but are dead (superseded by the RPC path). **→ 15.3d candidate:** fix the initiation RPC to `canonical_thread_id` + re-run `comm_pattern_analyzer` for Carbon8 (its own recompute + verify; awaiting go-ahead).
  - Repro/ops scripts (`_resp_latency_plausibility.py`, `_recompute_response_metrics_15_3c.py`, `_cleanup_hello_15_3c.py`, `_verify_*`) were **removed in the final pre-shutdown cleanup**; the method is fully documented in this entry and the 15.3c commit (a5e6abe).

- **15.3d — Initiation-ratio RPC fix (same provider-thread root cause) — 🔜 NEXT (before 15.4; it's a coaching metric about to be surfaced).** `calculate_all_contact_initiation_ratios` (sprint2 mig 009) groups by provider `e.thread_id` → under-counts threads / mis-attributes initiation for collision-heavy mailboxes (affects `contacts.initiation_ratio`). Same one-line root cause as 15.3c (`thread_id`→`canonical_thread_id`). Lower severity than latency (under-count, not 5× error) BUT initiation IS a Tier-A coaching metric feeding 15.4 — don't surface it broken. Fix RPC + re-run `comm_pattern_analyzer` for Carbon8 + verify. Confirm legacy Python `_calculate_initiation_ratio`/`_calculate_avg_thread_depth` are genuinely dead (unreachable) before leaving them.

- **15.3e — INVESTIGATE `hello@` client_id anomaly — 🔜 SEPARATE (NOT a reactive fix; deliberate look).** ~95% of the shared `hello@` box's emails carry a NON-CARBON8 `client_id` (pre-existing, not introduced by 15.3c). Higher-stakes than a coaching metric: any client-scoped query or RLS boundary could silently miss/mis-include hello@ rows → potential TENANCY-ISOLATION issue beyond coaching. **Investigate root cause FIRST (sync bug? import artifact? intentional?) before any fix** — don't reactively rewrite client_ids. Out of scope for the coaching build but flagged because it touches data integrity broadly.

- **15.4 — AM-facing frontend (self-view) — 🔜 (after 15.3d, MVP surface).** React view, each AM sees their OWN patterns. Simpler — no cross-AM permission logic. The MVP-ready surface. **Surfaces STRUCTURAL-ONLY (no content layer, per 15.3 verdict).** Frame responsiveness honestly (speed-of-ack, not substance — modest weight). All 4 Tier-A metrics must be data-clean first (latency ✅ 15.3c, initiation pending 15.3d).

- **15.5 — Management comparative view — 🔜 LAST.** Needs: (a) Tier-B validated (15.3), (b) role-scoped endpoint access (NEW auth/endpoint build, not-yet-existing), (c) fairness handling, AND (d) **15.1b stalled syncs FIXED** (else Ehab/Kenneth look falsely quiet). Framed as effectiveness once content signal proven, NOT activity-as-proxy. The hardest + last piece — do not rush it in front of management.

---

## OPEN DECISIONS
- **MVP scope: AM self-view first (15.4) or management view first (15.5)?** Steer: self-view first (simpler, safer, no new auth surface, immediately useful). Awaiting Dinesh's call.
- ~~15.3 pilot verdict (per-dimension real/hollow) decides whether 15.4 surfaces a content layer or structural-only.~~ **RESOLVED 16 Jun: all 3 hollow → 15.4 surfaces STRUCTURAL-ONLY. No content layer.**
- ~~15.3b verdict decides whether responsiveness is coaching-surface-ready or needs an artifact filter first.~~ **RESOLVED 16 Jun (15.3c): artifact was threading mis-pairs; fixed at source (canonical-thread pairing + validation), table recomputed, all 4 medians now plausible. Responsiveness is data-clean — but heed the §10.14 FRAMING caveat (one-line acks ≠ substantive replies; weight it modestly).**

---

## CROSS-REFERENCE
- Prerequisite DONE: latency backfill + mig 122 (all 7 mailboxes) — from the outreach track.
- Other track: OUTREACH_PROJECT_LEDGER.md (cards/cross-sell — shipped 15 Jun, tracking rep responses).
