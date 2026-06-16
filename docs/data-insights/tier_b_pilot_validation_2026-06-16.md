# Tier-B Content-Quality PILOT — Validation Gate Report (Task 15.3)

**Date:** 2026-06-16 · **Client:** Carbon8 · **Status:** ✅ complete (read-only, no production writes, on `main`)
**Design:** `docs/design/AM_QUALITY_LAYER_DESIGN.md` §10.12 · **Scripts:** `scripts/db/_tier_b_pilot_{sample,score,analyze}.py`
**Artifacts:** `tier_b_pilot_sample.json`, `tier_b_pilot_scores.json`, `tier_b_pilot_report.json`, `tier_b_pilot_spotcheck.md`

## Verdict (headline)

**STOP — do not scale Tier-B content extraction as designed.** All three content dimensions are
**HOLLOW**: on a balanced, length-matched, blind-scored sample they do **not** discriminate
won-linked from lost-linked threads. The §10.12 gate did its job — it caught a hollow metric
*before* corpus-scale investment.

| Dimension | Won mean | Lost mean | Cliff's δ [95% CI] | Cohen's d | MWU p | Verdict |
|---|---|---|---|---|---|---|
| discovery | 1.06 | 1.10 | **−0.021** [−0.090,+0.049] | −0.12 | 0.54 | HOLLOW (and floored) |
| consultative | 1.17 | 1.16 | **−0.008** [−0.101,+0.083] | +0.02 | 0.87 | HOLLOW (and floored) |
| answer_responsiveness | 2.88 | 2.84 | **+0.022** [−0.128,+0.175] | +0.03 | 0.77 | HOLLOW (has variance, no outcome link) |

Every effect size is negligible; every CI straddles zero; no p approaches significance. Won ≈ lost
on all three.

## Method

- **Sample:** 100 won-linked + 100 lost-linked threads, **outbound AM emails only**. Won/lost
  linkage identical to the 15.1 refresh (`thread_qb_links`→`qb_quotes`, won = `has_job OR job_no`,
  plurality mailbox). Won and lost sampled **separately** (15.1 caveat: a thread is "won" if linked
  to *any* won quote → never sample from the mixed pool).
- **Confound control by construction:** stratified into (AM × outbound-email bucket) cells and drew
  **equal won/lost counts per cell**, so the two samples have identical AM and thread-length
  composition. Verified: mean `n_out` 2.51 (won) vs 2.59 (lost); mean AM-chars 1865 vs 1762.
- **AMs:** Nic, Linda, Ehab (ample individually; Kenneth excluded — thin and sync-stalled, not
  needed). Transcripts HTML-stripped and quoted-history-trimmed.
- **Scoring:** **blind** (won/lost never sent to the model), OpenAI **gpt-4o**, temperature 0,
  calibrated-skeptical rubric, 1–5 + a verbatim evidence span per dimension. 200/200 scored, 0
  failures. **Cost: $0.86.** No writes to `ai_usage_log` or any production table.

## Length-confound check (the "won threads are just longer" trap)

Scores rise weakly–moderately with length (Spearman score~`n_out` 0.21–0.36; score~chars 0.26–0.48
— longer threads have more answering/clarifying). But this does **not** hide any won/lost signal:
the headline comparison is already length-matched, and the **within-(AM×bucket)-stratified Cliff's δ
is ≈ 0** for all three (−0.021 / −0.002 / +0.037). So there is no discrimination beyond length —
and there is no discrimination *from* length either. Nothing to surface beyond Tier-A.

## Why hollow — and is the scorer trustworthy? (§10.13 spot-check)

The scorer is **well-calibrated, not defaulting to 1.** The 15-thread human spot-check
(`tier_b_pilot_spotcheck.md`) shows it correctly finds the *rare* real instances:

- discovery **3/5** → Ehab: *"Do you have a budget in mind that you can share…"* (genuine open question)
- consultative **4/5** → Linda: *"That won't work for section sewn .. it has to be 4pp sections for the folding"* (advises a real constraint/tradeoff)
- answer_responsiveness **5/5** for precise spec answers; **1/5** for *"Thanks Karl"* non-answers.

So the **floor is real**, not an artifact: 95% of threads score 1 on discovery and 87% on
consultative because **Carbon8's quote-linked email is overwhelmingly transactional** —
quote requests, artwork files, PDF proofs, approvals, spec confirmations, invoices. Discovery and
consultative selling barely occur in this channel, in **won and lost alike**. Tellingly, some of the
*most* consultative threads in the sample were LOST (e.g. Ehab's budget-discovery thread, composite
10/15) and many WON threads are pure logistics (composite 3–5/15).

## Limitations / honest confounds

1. **Quote-linkage selects execution threads.** A thread linked to a quote is, by nature, about
   *that quote* — often post-quote fulfilment (artwork→proof→approval→invoice). Any consultative
   *selling* that exists likely happens **before** a quote (and so isn't quote-linked) or **off
   email** (phone/in-person). This pilot proves content quality doesn't predict winning **in the
   measurable, quote-linked email channel** — it is *not* proof that consultative selling is
   irrelevant to the business.
2. **One client, one channel, one model.** Carbon8 trade-print is a fast transactional workflow;
   a relationship-led business might differ. Consistent with existing memory
   `project_won_lost_archetype` (won/lost email behaviour separates for transactional accounts only;
   relationship accounts need content-substance) — here even that didn't surface, because the
   behaviour is near-absent.
3. **`answer_responsiveness` has real variance but no outcome link.** It measures something genuine,
   but as a *win predictor* it's hollow. (Cross-ref 15.3b: raw latency on the same metric is itself
   contaminated by threading mis-pairs for Kenneth/Ehab and mostly captures one-line acks — so
   "responsiveness" is weak on two independent grounds.)

## Recommendation (per dimension + overall)

- **discovery — DROP.** Floored and non-discriminating. Almost no behaviour to measure or coach.
- **consultative — DROP.** Same.
- **answer_responsiveness — DO NOT ship as an effectiveness/win signal.** It doesn't predict
  outcome. (It may have narrow value as a hygiene metric, but that overlaps Tier-A latency and is
  itself caveated by 15.3b.)
- **Overall: do not proceed to corpus-scale Tier-B extraction.** Lead AM coaching with the
  **Tier-A structural layer** (15.2), self-referential framing. This answers the OPEN DECISION in
  the ledger: **15.4 should surface a structural-only self-view, not a content layer.**
- **If Tier-B is revisited later (optional redesign, not now):** target **pre-quote / early-relationship
  threads** (where discovery actually happens) rather than quote-linked fulfilment threads, and first
  confirm the behaviour is even present in email vs phone. Re-run this same cheap gate before any
  scaling.

The pilot cost **$0.86** and one afternoon to prevent shipping a hollow "who communicates well"
metric to management. That is exactly the §10.12 outcome.
