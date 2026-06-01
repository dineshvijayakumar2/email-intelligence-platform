# Email Intelligence Platform — Insight Catalog Summary

**Date: 1 June 2026 | Author: Dinesh Vijayakumar**
**Detailed reference: insight_catalog.md (full spec)**

---

## Context

Following the 12 May conversation about the insight layer being the gap. Spent today verifying what's actually in the codebase against my mental model. The platform's contact-level intelligence is substantially built — persona classification, engagement scoring, response time tracking, capability rhythm, seasonality, market basket analysis, cross-contact gaps, the 17-field email intent classifier across 223K+ emails, AM performance snapshots infrastructure.

What's missing is more specific than "the insight layer." It's contact-level aggregation of per-email AI signals, surfacing of computed data into Carbon8-facing UI, content-derived AM behaviour signals beyond timing, and a few cross-cutting plumbing fixes (QB-AM name mapping, role-scoped endpoints, industry data, intent classifier sharpness).

The bottom-up consolidation framing from the trip — threads as chat sessions, insights flowing upward — matches how the existing systems already work. Extending the pattern is the work.

---

## What changes — examples

Three concrete examples of the shift from "what the platform shows today" to "what we want to surface." The pattern across the catalog: raw data → interpretive layer that makes the data actionable. The platform makes patterns visible; Carbon8 decides what to do with them.

### Example 1 — Buyer Quality (Q1)

**Today the platform shows:** Peter Howie at RareID has 514 quotes, 80 accepted, 15.6% strike rate. That's accurate but raw.

**What we want to surface:** This is a high-quoting, low-buyer-signal pattern — possibly quote-fodder behaviour. The contact mentions competitors in 60% of recent threads, rarely supplies print-ready files, and quote-to-decision averages 28 days. The contact profile shows three signals — Intent: low, Specificity: medium, Follow-through: low — with confidence and rationale. The platform makes the pattern visible.

### Example 2 — AM Comparison (AM2)

**Today the platform shows:** Linda's revenue and Nic's revenue side by side. Response times and conversion rates from QB.

**What we want to surface:** Linda's response substance is 80% substantive across threads; Nic's is 50% with 30% deflective ("I'll get back to you"). Her quote-to-acceptance median is 12 days; his is 22. Her language references customer-specific context 3x more often than generic openers. The platform surfaces the behaviour differences derived from email content; Carbon8 sees what makes each AM distinctive.

### Example 3 — Responsiveness Quality (Q3)

**Today the platform shows:** Mark Stewart responds in 6 hours on average.

**What we want to surface:** 70% of his responses are substantive, but on quotes above $10K his pattern shifts to "requirement-shifting" — he introduces new requirements that restart the clock. Median effective response time on high-value quotes is 14 days, not 6 hours. The AM viewing Mark's contact profile sees the timing signal, the substance signal, and the conditional pattern — the underlying reason a 6-hour average doesn't tell the full story.

The shift in all three: the platform stops at observation. It doesn't recommend action. Linda or Nic knows their team and their customers; the platform's job is to make the patterns visible to them.

---

## How the platform remembers: bottom-up architecture

The trip framing — threads as chat sessions, insights flowing upward — turns into a concrete five-level memory pattern:

```
Email (raw + classifier extraction)
  ↓
Thread (thread-level features, status, summary)
  ↓
Contact (persona, scored characteristics)
  ↓
Customer (engagement-weighted rollups)
  ↓
Industry (cross-customer benchmarks)
```

Each level stores **structured derived memory** — typed fields and scored values, not free text. Aggregation rules at each level: recency-weighted at contact level, engagement-weighted at customer level. Confidence scoring at every level. Refresh schedules align with how fast each level changes (thread features within hours, contact persona daily, customer rollups weekly, industry monthly).

This pattern already matches how the existing platform is structured. The catalog extends it with new derived features (Q1 buyer quality, Q3 substance, AM2 behaviour features) at the levels where they belong.

**Alongside the structured memory, semantic retrieval via embeddings supports the insights** — when a user views a contact's "Intent: low" score, they can click to see the actual emails that support the conclusion. The scores come from structured features (fast, stable, comparable); the supporting evidence comes from vector similarity over the email corpus. The two work together: derived insights you can trust because you can see what they're built on.

Full architectural detail in the reference document.

---

## The 13 questions

Three levels. Computation grounding for each in the full document.

### Contact Persona

| # | Question | Foundation | Gap |
|---|----------|------------|-----|
| **Q1** | Legit buyer vs window-shopper *(full spec)* | Strike rate, persona views production | Contact-level aggregation of buying signals + competitor mentions; quote-to-acceptance timing computation |
| Q2 | Demanding vs reasonable | Urgency, sentiment per email | Contact-level aggregation; requirement-shift detection |
| **Q3** | Responsiveness *(full spec)* | Thread-aware bidirectional response time production | Substance classification (substantive / deflective / requirement-shifting) |
| Q4 | Product recommendations from same-company patterns | Market basket + cross-contact gaps production | Surface at contact level (currently company level only) |
| Q5 | Seasonality (contact) | Company/industry seasonality production | Don't build separately — surface company seasonality on contact page |
| Q6 | Engagement-revenue correlation | Engagement scorer weights revenue 15% | Explicit correlation coefficient; consolidate two engagement score systems |

### Company Profile

| # | Question | Foundation | Gap |
|---|----------|------------|-----|
| C1 | Contact-level questions rolled up to customer | company_contact_summary view exists | Per-Q1/Q2/Q3 rollup with engagement weighting |
| C2 | Product portfolio diversification | Per-customer capability tracking production | Diversification metric, trend, optional peer comparison |
| C3 | Industry-peer recommendations | industry_benchmarks view exists | **Blocked on industry data quality (87% missing) — decision needed** |

### AM Insights

| # | Question | Foundation | Gap |
|---|----------|------------|-----|
| AM1 | Engagement-revenue correlation per AM | Engagement aggregates upward; AM revenue in snapshots | Statistical correlation (no scipy currently) |
| **AM2** | AM comparison *(full spec — first deliverable)* | am_performance_snapshots + outbound emails classified | QB-AM mapping, role-scoping, frontend, behaviour features, correlation |
| AM3 | Proactiveness impact | Initiation ratio per contact; thread_role='initial' | Persistent proactive flag, follow-through tracking, correlation |
| AM4 | Complaint tracking and resolution | Complaint intent + urgent override | State machine, resolution timing, SLA, AM workflow — real net-new work |

---

## AM2 — AM Comparison (first deliverable)

The 12 May ask was for AM comparison based on thread insights — language, response speed, value generated, customer feedback signals. Language and feedback are email-content-derived; speed is timing. The first deliverable includes both, not just timing.

**Dashboard structure, three sections per AM:**
- **Outcomes** (QB-grounded): strike rate, revenue, conversion, retention
- **Behaviours** (email-derived): response speed, engagement depth, proactiveness ratio, consultative ratio, specificity ratio, tone adaptation, action follow-through
- **Correlations**: which behaviours most predict outcomes per AM, vs team median

**Visibility (proposed, your call):** Client managers see full AM comparison by name. AMs see own profile + anonymised team aggregate. Admin sees everything.

**Realistic timeline: 4-5 weeks for complete AM Comparison.** Weekly visible progress: behaviour extraction samples in week 2 for validation, validated extraction at scale in week 3, dashboard structure in week 3-4, full integration in week 5. The work is accessible as it builds — not gated on a final demo.

**Build components (described, not clustered — clustering is your call):**

1. QB-to-platform AM name mapping table — fixes zero-match silent attribution error. Half day.
2. Endpoint role-scoping — applies access control, row-level filter for AM role. Half day.
3. Snapshot generation independence — separate from Strategic Digest, scheduled cron. 2-3 hours.
4. AM behaviour feature extraction — new LLM pass extracting tone, specificity, promise tracking. 2-3 days + $30-50 API for backfill.
5. Frontend dashboard pages — per-AM profile + comparison view. 2-3 days.
6. Correlation computation — scipy.stats per AM, vs team median. 1 day.
7. Backfill across historical outbound emails. 1 day.

**Open design questions:** visibility model, departed-AM revenue attribution, framing of correlations (patterns to observe, not prescriptions).

**After AM Comparison:** Q1 buyer quality (3 weeks), Q3 responsiveness substance (2 weeks). Then the rest of the catalog over the following months.

---

## Q1 — Legit Buyer vs Window-Shopper

**Why this question:** most distinctive "email intelligence" question. Cannot be answered by QB alone. Methodology developed here transfers to Q2 and the other persona questions.

**Output:** Three-component score plus confidence — Intent (low/med/high), Specificity (low/med/high), Follow-through (low/med/high). Plus rationale citing specific evidence.

**Computation:** LLM extracts thread-level intent/specificity/follow-through signals. Aggregate per contact with recency weighting. Cross-reference with QB strike rate + decision timing.

**Validation:** Algorithm output correlates with QB strike rate. Linda/Nic review sample of 30-50 for qualitative check.

---

## Q3 — Contact Responsiveness

**Building on:** Existing thread-aware response time tracker (timing only).

**Adding:** Substance classification on contact responses — substantive vs deflective vs requirement-shifting. The new layer that converts "responded in 2 hours" into useful signal.

**Output:** Three components plus confidence — Speed (fast/moderate/slow/silent), Substance (substantive/deflective/requirement-shifting), Reliability (consistent/variable/unreliable).

**Computation:** Use existing thread_status to identify "AM waiting" periods. Reuse existing response time tracker. New LLM pass classifies contact response substance.

---

## Cross-cutting decisions needed Tuesday

1. **Industry data quality** — 87% missing. Three paths: Carbon8 backfills QB-side (weeks of AM effort), platform AI-infers from email/domain (~$50, 70-80% accuracy, 2-3 days), or defer C3. Affects C3 directly, C2 partially, AM2 customer-mix normalisation.

2. **AM2 visibility model** — confirm or revise: client_manager sees all AMs by name, AMs see own + anonymised team aggregate.

3. **Catalog prioritisation** — AM Comparison proposed as first deliverable (4-5 weeks). Q1 and Q3 follow. Confirm or adjust.

4. **Cadence resume** — alternate-day calls continuing? Or shift to weekly?

---

## Common conventions across all insights

- **12-month time window** for derived characterisations
- **Recency weighting** linear decay: last 30d = 1.0, 30-90d = 0.75, 90-180d = 0.5, 180-365d = 0.25
- **Confidence scoring** on every insight — low confidence shows "insufficient data" rather than misleading number
- **Platform stops at observation** — insights describe what's true; the platform doesn't prescribe action

---

## Parallel platform work

Database performance analysis identified specific optimisations for current Supabase tier. Engineering remediation, not new features. Runs in parallel with insight work. Key items: RLS auth function pattern fix, email count aggregation refactor, keyset pagination on heavy endpoints, unused index cleanup, FK index additions, email body_text vertical partition. Details in full document.

---

## Reference

Full document with what's built per system, complete specs for AM2/Q1/Q3, all 10 one-page sketches, and platform stabilisation detail: **insight_catalog.md**
