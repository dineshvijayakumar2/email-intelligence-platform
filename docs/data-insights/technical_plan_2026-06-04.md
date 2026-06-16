# Email-Driven Insights — Technical Findings & Proposed Next Round

**Date:** 4 June 2026
**Status:** Internal working document — proposed plan, hold unless asked. Not a build catalog; every item below is a consequence of what this round's analysis exposed.
**Companion:** `02_insights_for_jeff.md` (the findings, plainly).

This document does two things: records the findings with full methodology and caveats, and proposes what to build next — where each proposed feature is justified by a specific gap the analysis surfaced, not by abstract usefulness. The ordering principle is: *the data told us where it's blind; fix those first.*

---

## 1. What was done

Email interaction features (input) tested against QuickBase outcomes (target: won/lost via `has_job` at distinct-`quote_no` grain; revenue). Two accounts, chosen for clean single-AM attribution and dense email coverage:

| Account | QB key | AM | Won/lost (linked) | Email coverage |
|---|---|---|---|---|
| Artis (C14306) | 19212 | Ehab Kamel | 533 won / 1,390 lost | dense, 93% own mailbox |
| The Property Agency (C13039) | 17541 | Linda D'Arcy | 135 won / 223 lost | dense, 78% own mailbox |

Email↔quote linkage via contact + temporal proximity (±14d), validated this round as recovering 2–3× more won-revenue correlation than exact quote-number citation.

---

## 2. Findings (with the caveats that bound them)

**F1 — Email behaviour separates won/lost, but archetype-conditionally.**
Artis (transactional): clear separation. The Property Agency (relationship): flat. This is the central finding and the central design constraint — a global model averages the two and serves neither.

**F2 — At transactional accounts, conversation *intent* is the primary separator.**
Won quotes concentrate in `job_approval` / `artwork_submission` intents; lost in `quote_request` / `payment_query`. Corroborated by sustained reply latency (4.7h won vs 9.0h lost) and customer-initiated threads (won 0.34 AM-initiated vs lost 0.60).
*Caveat (reverse causation):* volume-based features (exchanges 89.8 vs 39.1; follow-ups 28.5 vs 14.9) may reflect that larger live jobs generate more email, not that more email causes wins. **Intent type is the causation-clean signal; volume is corroborating only.** Lead with intent.

**F3 — Value concentrates in one contact ≠ the volume contact.**
~52–54% of won value through a single contact at each account. Artis: `graphics@` (80% strike, value-driver) vs `accounts.pay@` (2,106 quotes, 2 emails sent, 4% strike — citation sink). TPA: `ry@` value-driver, `ck@` higher email volume but lower value. Engagement should be value-weighted.

**F4 — Book shape differs by AM (Nic recheck).**
Nic Doyle does not fold in. ~48% of his won revenue is outside the email-covered window (pre-sync / no synced email); of the testable remainder ~42% ($1.39M) converts with no contemporaneous email despite active companies; his proximity-over-citation lift is only 1.46× (vs Artis 3.3×) because his citation floor was already high. Root cause is structural: a ~1,700-company long tail vs two single trade accounts. **Email-derived coverage is intrinsically lower for long-tail books — model it, don't treat as a fixable link gap.**

**Bounding caveats on all findings:**
- n=2 (within-customer comparisons only; flags are heuristic, not significance-tested).
- Proximity linkage is time-association, not confirmed aboutness — adequate for correlation, insufficient for attribution-precise use.
- Numeric sentiment-score feature **not built** (categorical `sentiment` exists; the numeric score isn't populated) — tone untested this round.
- Artis recency understated (Ehab mailbox ~2wk behind on sync). TPA ~21% off-named-mailbox attribution noise.

---

## 3. Proposed next round — evidence-driven, prioritised

Each item names the specific finding-gap it addresses. Priority reflects evidence strength × cost, not feature ambition.

| # | Build | Justified by | Cost | Priority |
|---|---|---|---|---|
| 1 | **Intent-lifecycle rollup** (per-quote-window intent composition) | F2 — intent was the strongest, causation-cleanest separator; classifier already run, no new LLM pass | Low | **Do first** |
| 2 | **Quote-specific thread linkage** (move from proximity to aboutness) | Bounding caveat — proximity is time-association; this is the rigor fix that lets features describe the quote's *own* conversation | Med-High | High (rigor) |
| 3 | **Response-substance features** (Q3) | F1 — *motivated by* the TPA-null: tests whether substance carries signal the structural features missed. Hypothesis, not guaranteed payoff. | Med | High (exploratory) |
| 4 | **Numeric sentiment score + trajectory** | Caveat — sentiment was untestable this round; trajectory (sentiment declining before a loss) is the richer version | Med | Medium |
| 5 | **Account-archetype classifier** (transactional vs relationship) | F1 — the global-model failure means archetype must be an explicit input before any cross-account modelling | Med | Medium-High |
| 6 | **Body-NLP features** (negotiation/question density, specificity) | Plausible but unvalidated at n=2; needs portfolio scale + carries egress cost | High | Defer to portfolio round |

**Two methodology decisions (not features):**
- **Standardise ±14d proximity as the link for correlation/feature work** — but explicitly *not* for attribution-precise uses (outreach personalisation referencing a specific quote needs verified linkage, per the caveat). Don't let "standard link" flatten that distinction.
- **Populate-then-evaluate `sentiment_score`** (build it, assess it next round) rather than removing it — removing forecloses the question.

---

## 4. The actual next step (the one that matters)

The findings above are a two-customer proof of method. The single highest-value next move is **not** any one feature — it's generalising F1: classify a set of accounts by archetype, then test whether the Artis (transactional) pattern — intent-type separation + value-contact concentration — holds across transactional accounts as a class.

If it does, that's the first portfolio-scale, defensible, email-driven pattern, and it's the direct substrate for the outreach use-case: *engage this value contact, in this kind of conversation, at this account, because that is what wins at accounts of this type.* Items 1, 2, and 5 above are the minimum needed to run that test cleanly; the rest can wait.

The discipline that keeps this from becoming the catalog that gets rejected: **don't build ahead of evidence.** Build item 1 (cheap, proven), run the archetype generalisation, and let *those* results dictate which of 2–6 are actually worth their cost.
