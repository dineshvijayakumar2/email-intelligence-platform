# AM Communication-Quality Layer — Research-Grounded Design (pilot first)

> Goal (Dinesh): (1) help management see who is doing a great job, (2) give AMs usable
> insights to improve their communication style and win more revenue.
> Principle: quality dimensions are grounded in B2B sales-effectiveness research, NOT in
> what is convenient to extract. Pilot + validate before any corpus-scale extraction (§10.12).

## Why this layer (the gap)
Structural metrics (latency, initiation, thread depth, cadence) measure ACTIVITY, not
QUALITY. The email BODIES are almost entirely unmined (sentiment ~all-zero, key_topics
0.4%, buying_signal 0.08% — see am_coaching_readiness.json). The quality signal that
research links to winning lives in the body text and needs a new LLM extraction pass.

## Research basis (web research, 15 Jun 2026)

**Conversation-analytics (Gong Labs) — structural signals that correlate with winning:**
- Email velocity is the single best close predictor: closed-WON deals ~8.2 emails/week
  vs closed-LOST ~1.87; final week 11.5 vs 1.35. (gong.io/blog/sales-analytics,
  the-signal-all-winning-deals-have-in-common)
- Multithreading (engaging multiple stakeholders) is critical to deal success.
- "Feature dumping sinks win rates" — listing product features instead of solving.
- Customers giving short/closed responses signal disengagement.

**Consultative-selling literature — quality behaviors that separate effective sellers:**
- Ask discovery questions and understand needs BEFORE recommending; "stop pitching, start
  helping." (highspot, thesalesblog, grovaleulers, nutshell)
- 86% of buyers more likely to buy when the seller understands their goals; 59% say reps
  DON'T take time to understand them. (nutshell / consultative research)
- Open-ended questions >> closed; reps systematically under-ask open questions.
- Failure modes: pitching too fast, feature-led messaging, generic/one-size-fits-all,
  not tailoring to the buyer's constraints/timeline.

## The dimensions (grounded, split by what data supports)

### Tier A — STRUCTURAL (compute NOW, no extraction; highest evidence)
| Dimension | Definition | Source data | Research backing |
|---|---|---|---|
| Exchange velocity | emails exchanged per active thread/week with a contact | emails + canonical_thread_id | Gong: strongest close predictor |
| Responsiveness (latency) | business-hours reply time to inbound | email_response_metrics (mig 122) | fast response = engagement |
| Multithreading | distinct contacts engaged per company | emails -> company_id, contacts | Gong: critical to deal success |
| Follow-up persistence | does the AM re-touch after silence (vs let go cold) | outbound sent_date sequences | consistent follow-up drives conversion |

### Tier B — CONTENT (the NEW LLM pass over OUTBOUND bodies; pilot before scale)
| Dimension | What the LLM scores (per outbound email or thread) | Research backing |
|---|---|---|
| Discovery / question-asking | Does the AM ask open-ended questions to understand the customer's need? (count + open-vs-closed) | consultative: under-asking is the #1 gap |
| Consultative vs feature-dumping | Does the reply translate to the customer's need, or list product/price features? (scale) | "feature dumping sinks win rates" |
| Answer-responsiveness | Does the reply actually address what the customer asked, or deflect/generic? | 59% of buyers feel reps don't understand them |

DELIBERATELY EXCLUDED for v1 (low ROI / not grounded / risky): sentiment trajectory
(data degenerate), generic "tone/warmth" (vague, hard to validate, easy to be hollow),
personality scoring (not coachable, not defensible to management).

## §10.12 PILOT — prove the content signal is real before corpus-scale extraction

The danger: extract a plausible-sounding "consultative score" across ~60k outbound emails,
build coaching on it, and discover it is noise that correlates with nothing. That hollow
metric, handed to management as "who communicates well," could mis-judge an AM. The pilot
is the guard.

**Pilot design (cheap, validated):**
1. **Sample with ground truth.** Pull outbound emails/threads from a balanced set of
   WON deals and LOST deals (use qb_quotes won/lost linkage to threads). ~100-200 threads.
2. **Extract the 3 Tier-B dimensions** on that sample with an LLM (scored 1-5 + short
   evidence span per score, so it's auditable, not a black-box number).
3. **VALIDATION GATE (the §10.12 check): does the score discriminate won vs lost?**
   If consultative/discovery/responsiveness scores are materially HIGHER on won-deal emails
   than lost-deal emails -> the signal is REAL, proceed to scale. If won≈lost -> the metric
   is hollow; STOP, redesign or drop that dimension. Do NOT ship a dimension that doesn't
   discriminate.
4. **Human spot-check.** Dinesh reads ~15 scored emails: do the scores + evidence spans
   match a human's read? (Catches the LLM being confidently wrong, the §10.13 reflex.)

**Only if the gate passes:** scale the extraction (scoped, provenance-tagged, recomputable
on new email — same platform discipline as the capability/industry layers; a new column or
table beside the email, not a one-shot script).

## Fairness (carry from 12.3 — non-negotiable for the management view)
- Common time cut-off (Ehab's mailbox trailed ~3wk; don't penalize a data artifact).
- Volume-normalize (CV 1.14-3.1 across AMs; lumpy months mislead naive comparison).
- Mary/Peter have NO mailbox -> excluded from email-quality entirely; QB-outcome track only.
- Self-referential framing for AM-assist ("vs your own baseline") sidesteps cross-AM
  unfairness; cross-AM comparison (management) ONLY with the above handling + "activity/
  behavior, not a verdict" framing until the content layer is validated.

## Two-aim split (Dinesh's stated goals)
- **AM-assist (lead with this):** self-referential — each AM vs their own baseline on
  Tier A now, Tier B after the pilot. Safe, immediately useful, coachable.
- **Management "who's doing great":** needs Tier B validated (activity alone rewards
  busyness, not effectiveness) + fairness handling. Sequence AFTER the pilot, framed as
  effectiveness once the content signal is proven, not activity-as-proxy.

## Build order
1. Re-confirm 12.3 readiness on CURRENT data (3 days + syncs since; check Ehab caught up,
   latency populations grew) — narrow refresh, read-only.
2. Tier A structural scorecard, self-referential, 4 mailbox AMs + fairness caveats.
3. Tier B PILOT on won/lost sample -> validation gate. Only scale if it discriminates.
4. Management comparative view last, once Tier B is proven.
