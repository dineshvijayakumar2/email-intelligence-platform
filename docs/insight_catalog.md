# Email Intelligence Platform — Insight Catalog

**Document 1: Design framework and question catalog for the insight layer**
**Author: Dinesh Vijayakumar | Date: 1 June 2026**

---

## Context

This document follows from the 12 May conversation about the insight layer being the gap. After the trip, I spent today verifying what's actually in the codebase against my mental model. The picture is more complete than I'd been operating with: substantial contact-level intelligence is already in production — persona classification, 10-factor engagement scoring, thread-aware response time tracking, capability rhythm with overdue detection, seasonality with outreach windows, cross-contact capability gaps, market basket analysis. The 17-field email intent classifier runs across 223K+ emails. The AM performance snapshot infrastructure exists end-to-end with the frontend page never built.

What's missing is more specific than "the insight layer." It's the contact-level aggregation of per-email AI signals, the surfacing of computed data into Carbon8-facing UI, the content-derived AM behaviour signals beyond timing, and a small set of cross-cutting plumbing fixes (QB-AM name mapping, role-scoped endpoints, industry data quality, intent classifier sharpness).

The bottom-up consolidation framing that crystallised on the trip turns out to match how the existing systems already work. The persona views, engagement scorer, and response time tracker all aggregate thread-level features upward. Extending the pattern to email-content extraction and completing the upward roll-ups is the work.

This document catalogs 13 business questions across Contact Persona, Company Profile, and AM Insights. For each, it describes what exists, what's missing, and what closing the gap requires. The three starter insights (Q1, Q3, AM2) get full specs; the remaining ten get one-page sketches. A platform stabilisation section at the end covers database optimisation work happening in parallel.

---

## What's already built

Verified by codebase investigation, 1 June 2026.

**Contact persona system.** Five-view SQL architecture (`contact_email_metrics`, `contact_quote_metrics`, `contact_persona`, `company_contact_summary`, `industry_benchmarks`). Eight-category classification: champion, active_buyer, active_relationship, warm_lead, prospect, inactive_buyer, dormant, shared_mailbox. Materialised view refreshed daily and after QB sync. API endpoints in `contacts_intelligence.py`. UI surfaces: PersonaCard, contacts list, contact detail page.

**Engagement scoring.** Ten-factor weighted formula with role-based bonuses (decision_maker, C-level, VP, director, manager, senior). Persistent score on `customer_contacts` and `customer_companies`. Time-series history in `metric_history`. Integrated as Step 10.4 of the extraction pipeline. UI: score display, trend chart. Note: a second engagement score also exists in the `contact_persona` view (3-factor: velocity + recency + quote activity). Consolidation into a single canonical score is technical debt to address — see cross-cutting concerns.

**Response time tracking.** Thread-aware, direction-separated. Detects response pairs by direction changes, excludes 18 auto-reply patterns and outliers >7 days. Bidirectional: our response time to them, and their response time to us. Business-hours variant computed per mailbox timezone. UI: response times page with slowest responders table.

**Revenue propagation.** Per-contact via `qb_unique_emails` and `qb_contacts` joins. Company-level inheritance via `batch_propagate_qb_data_to_contacts` RPC. Three-pass propagation: email-based link, direct QB link, company inheritance. Used in engagement scoring (15% weight when QB present), recommendation engine (concentration risk), customer analytics (per-capability profile).

**Email intent classifier.** Claude Haiku produces 17 structured fields per email: intent, urgency, sentiment, sentiment_score, action_type, business_signal, entities (competitors_mentioned, products_mentioned, budget_signal, buying_signals, action_items_extracted, people_mentioned, dates_mentioned), confidence, justification, qb_references. 223,188 emails classified. Outbound emails receive full classification — only `action_type` is forced to `no_action` (AM is the sender, no inbound action to take). All other fields populated.

**Thread status engine.** Two-layer logic. Layer 1 timing heuristic (dropped >30d, ongoing ≤3d, complete depth≥2 and 3-7d old, overdue >7d, awaiting_response, awaiting_our_response). Layer 2 intent overrides from `thread_status_override_rules` table (urgent for complaints/churn/critical, revenue_opportunity for quote_request/buying_signals, closing for positive_feedback in awaiting state). Redis-cached 60s TTL.

**Seasonality engine.** Production at company and industry level. Monthly/quarterly/yearly patterns, peak/trough statistical detection, outreach windows suggesting contact 1 month before peak. Computed from `qb_operations`. UI: SeasonalityChart with YTD comparison, year/year view, quarterly panel, outreach alerts. AI integration via LangChain tool feeds seasonality context into strategic summaries.

**Capability rhythm and overdue detection.** Per-capability ordering cycles computed from QB job history. Status classification (overdue, due_soon, on_track, insufficient_data) using `avg_interval × 1.3` overdue threshold. Severity buckets (danger if overdue > avg/2, warning otherwise). UI: CapabilityRhythmCard with sortable overdue table.

**Capability classification system.** 8-tag MVP taxonomy (Flat Sheets, Soft Cover Books, Hard Cover Books, Wide Format, Embellishment, Specialty Finishing, Design Services, Display & Install). 597+ operation tuples mapped in `client_taxonomy_config`. Exact match plus keyword fallback. Bulk reclassify endpoint exists.

**Market basket analysis.** `product_affinities` table with pre-computed co-occurrence across companies. For each pair of operations, counts companies using both. Confidence ranking: `count(A and B) / count(A)`. Minimum support of 3 companies. Used in `RecommendationEngine._compute_related_product()`.

**Cross-contact capability gaps.** Production via `recommendation_engine.py::_compute_cross_contact()`. For each person-type contact, identifies "already buys" (capabilities they've been quoted on) vs "untapped" (capabilities the company uses but this contact hasn't). UI: RecommendationsPanel on company detail page.

**Revenue concentration and buyer decay risk.** Flags companies where ≤2 contacts produce all revenue above $100K threshold, or where top buyer's persona = inactive_buyer. UI: alert card in RecommendationsPanel.

**Per-contact strike rate.** Fully computed via `contact_quote_metrics` view. Accepted/total ratio, total quote value, total job value, avg margin. Persona classification consumes strike rate (champion requires ≥0.3, prospect requires ≤2 quotes with no acceptances). UI: PersonaCard, StrikeRateCard, contacts list with sortable Strike% column.

**Buying signals and competitor mentions.** Extracted per email into typed fields. `buying_signals` TEXT[], `business_signal_score` 0-100, `competitors_mentioned` TEXT[]. Indexed for fast filter. Competitor entity-level aggregation in `ai_business_entities` table with mention count, first/last seen, associated company IDs. UI: Opportunities page with competitor tab.

**AM performance snapshots.** `am_performance_snapshots` table with 20+ KPI columns: revenue, customer count, quote conversion, response time (raw and business hours), retention rate, response rate, after-hours email percentage. Computed by `AMEfficiencyAnalyzer`. Currently only triggered during Strategic Digest generation. Frontend API service exists but no dashboard page consumes it.

**Initiation ratio per contact.** Computed via `calculate_all_contact_initiation_ratios()` RPC. Stored on `customer_contacts.initiation_ratio` (0.0 = contact always initiates, 1.0 = AM always initiates). Identifies first email per thread by sent_date.

**Role infrastructure.** Three roles in `user_profiles.roles[]` (admin, account_manager, client_manager). `get_user_accessible_mailboxes` RPC enforces mailbox-level visibility cleanly. Eleven users with account_manager, three with client_manager, two admins. Logic has no accumulated exceptions.

---

## What's missing across the catalog

Recurring gaps identified by investigation:

**Contact-level aggregation of per-email AI signals.** Buying signals, competitor mentions, and business signal scores are extracted per email and aggregated to entity level for competitors, but not aggregated to contact level. A contact who mentions competitors in 8 of 10 emails should be identifiable as "shopping around"; today this is extractable but not surfaced.

**Quote-to-acceptance timing.** Raw data exists (`qb_quotes.date_created`, `date_accepted`) but no `days_to_accept` computation. This single derived field unlocks decision velocity per contact, stalled quote detection, and committed-vs-speculative buyer distinction.

**QB AM name to platform user mapping.** Zero matches between `qb_customers.account_manager` (e.g. "Ehab Kamel") and `user_profiles.name` (e.g. "Ehab Kamel | Carbon8"). Every AM-level revenue attribution fails silently. Mapping table required before AM2 produces trustworthy numbers. Also: 10 QB account_manager values reference departed AMs with no platform user — needs an "unassigned" or successor mapping policy.

**Role-scoped endpoint access.** `GET /ai/am-performance/{client_id}` returns all AMs' data to any authenticated user. The visibility model (client_manager sees all AMs by name, AMs see own profile + anonymised team aggregate) requires endpoint-level row filtering plus `_validate_client_access` enforcement. Pattern exists in two other routers; needs extracting to shared auth dependency.

**Industry data quality.** 87.3% of customers have no usable industry (52.4% "Not Selected", 35.0% NULL). The 12.7% with values include casing duplicates ("Small Business or Individual" 437 vs "Small business or individual" 101) and non-industry entries ("Extinct"). Any insight depending on industry-peer comparison (C3 directly, C2 partially, AM2 customer-mix normalisation) needs industry data resolved first. Three paths: Carbon8 backfills QB-side, platform AI-infers from email/domain, or defer.

**Intent classifier sharpness.** 65% of emails classify as `general_enquiry` catch-all. Sample analysis of 100 such emails: 45% noise (acknowledgements, spam, automated notifications, feedback surveys, personal), 55% real business signal not distinguished (job instructions, delivery coordination, pickup, technical discussion). Either pre-classification noise filter, prompt refinement with re-classification, or insight design that routes around the catch-all.

**Substance classification on contact responses.** Q3 needs to distinguish substantive responses from deflective ("I'll get back to you") or requirement-shifting. Requires new LLM classification pass on contact-sent emails specifically. Small scope but net-new.

**AM email quality / behaviour assessment.** Outbound emails get intent classification but not quality assessment. Consultative vs transactional tone, specificity, proactiveness markers, promise tracking ("I'll send this by Friday — did they?") — none extracted. Required for AM2 behaviours section beyond timing.

**Statistical correlation analysis.** No scipy/statsmodels/sklearn anywhere in the codebase. AM-revenue correlation, engagement-revenue correlation per contact, behaviour-outcome correlations across AMs — all metric storage exists, correlation computation does not. Required for AM1, AM2 (Section 3), AM3.

**Complaint lifecycle tracking.** Classification exists (`complaint` intent with urgent override). State machine (open → acknowledged → investigating → resolved → closed) does not. Required for AM4.

**UI surfaces for computed data.** Per-contact engagement score breakdown by factor (data in `metric_history`), industry benchmark comparison (view exists), decision-maker / seniority badges (columns exist with scoring bonuses), contact side-by-side comparison (data available). None surfaced.

---

## Architectural framework

### Two-layer execution model

**Layer A — Batch analytics (run periodically, results cached):** stable pattern characterisation. Persona views, engagement scorer, response time tracker, capability rhythm, seasonality already operate this way. Most catalog items extend this layer.

**Layer B — Event-triggered alerts (smaller subset, action-oriented):** seasonality outreach windows (existing), reorder timing flags (existing), complaint escalation (proposed for AM4). These run as scheduled checks that flag when thresholds are crossed.

### Common conventions across all insights

**Time window: 12 months** for derived characterisations. Older threads exist but don't influence current scores.

**Recency weighting: linear decay** within window — 1.0 for last 30 days, 0.75 for 30-90, 0.5 for 90-180, 0.25 for 180-365. Active threads weight 1.0 regardless of age.

**Confidence scoring on every derived insight** — based on thread count, signal consistency, recency. Low-confidence insights show "insufficient data" rather than misleading scores.

These conventions are tuneable in v2. Some existing systems use slightly different windows (engagement scorer uses 90/180/365-day buckets); minor adjustment for consistency is part of the consolidation work.

### Bottom-up consolidation pattern

Thread → contact → customer → AM → portfolio. Same underlying extraction; aggregation level produces different insight surfaces. Already the pattern used by `contact_persona` views (contact aggregates rolling up into `company_contact_summary`). Extension: add per-email AI signals (buying signals, competitor mentions, signal scores) to the contact-level aggregation, then roll those up the same way.

---

---

## Bottom-up memory architecture

This section formalises the architectural pattern that emerged from trip thinking. The insight that crystallised: each email thread functions like a chat session — a contained conversation with its own context. The platform should treat threads accordingly, with insights derived at each level and consolidated upward.

This pattern turns out to match how the existing platform is already structured (`contact_persona` views aggregating from `contact_email_metrics`, `engagement_scorer` rolling up thread features to contacts, `am_performance_snapshots` aggregating contact-level signals to AMs). Formalising it makes the existing structure explicit and gives a consistent framework for the new insights.

### The five levels

```
Email           (raw + per-email AI extraction)
  ↓
Thread          (thread-level features + status + summary)
  ↓
Contact         (persona + scored characteristics + memory of patterns)
  ↓
Customer        (engagement-weighted rollups + diversification + relationship state)
  ↓
Industry        (cross-customer patterns + benchmarks + peer comparisons)
```

Each level is a "memory" of the level below — derived state that captures stable characteristics rather than raw text. Memory at each level is:

- **Structured**, not free-text — typed fields, scored values, classified categories
- **Derived** from the level below with explicit aggregation rules
- **Refreshed** on schedule (batch), not real-time on every change
- **Confidence-scored** — low-confidence values surface as "insufficient data" rather than misleading numbers

### Level 1: Email

**Raw data:** the email itself (subject, body, sender, recipients, timestamps, thread_id).

**Derived memory (per-email):** the 17-field classifier output stored in `ai_email_intelligence` — intent, urgency, sentiment, sentiment_score, action_type, business_signal, entities (competitors_mentioned, products_mentioned, budget_signal, buying_signals, action_items_extracted, people_mentioned, dates_mentioned), confidence, justification, qb_references.

**Semantic memory:** email body vectorised into pgvector embeddings (gemini-embedding-001). Currently exists but new emails aren't auto-vectorised — gap in extraction pipeline noted in bucket list.

**Refresh:** computed once per email during extraction. Stable until the email itself is reprocessed.

### Level 2: Thread

**Derived memory:** thread-level rollup of per-email features. Production today: `thread_status` (active/overdue/awaiting), intent override-driven effective status, depth, last-sender direction, participant list. Catalog extends this with:

- For Q1: thread-level intent / specificity / follow-through signals
- For Q3: per-message substance classification on contact responses
- For AM2: per-thread AM behaviour features (consultative tone, specificity, promise tracking)

**Refresh:** triggered when thread receives new emails. Most thread features stabilise within hours of last message; substance and behaviour features can be batched daily.

**Connection to chat-session analogy:** a thread is the closest analog to a Claude chat session. It has its own conversational context, participants, intent flow, and resolution state. Thread-level memory captures "what happened in this conversation."

### Level 3: Contact

**Derived memory:** contact-level aggregation of thread features. Production today: `contact_persona` (8-category classification), `engagement_score` (10-factor), `avg_response_time_seconds`, `initiation_ratio`, `qb_quotes_count`, `strike_rate`. Catalog extends this with:

- Buyer quality components (Q1)
- Demandingness pattern (Q2)
- Responsiveness substance pattern (Q3)
- Engagement-revenue correlation coefficient (Q6)

**Aggregation rules:** thread features → contact features via recency-weighted aggregation. Common conventions: 12-month window, linear decay (1.0 last 30d, 0.75 30-90d, 0.5 90-180d, 0.25 180-365d). Confidence scoring based on thread count, signal consistency, recency of most recent.

**Refresh:** weekly batch via existing cron infrastructure (extends `refresh-persona-metrics`).

**Connection to chat-session analogy:** if a thread is a chat session, the contact is the user-across-sessions. Their persona is the derived characterisation of them across many conversations — stable enough to inform interaction, refreshed as new conversations occur.

### Level 4: Customer

**Derived memory:** customer-level aggregation of contact-level signals. Production today: `company_contact_summary` (persona distribution), `qb_total_revenue`, `qb_tier`, capability profile, seasonality patterns, ordering rhythm with overdue flags. Catalog extends this with:

- Rollup of contact-level Q1/Q2/Q3 scores (C1)
- Product diversification metric (C2)
- Industry positioning (C3 if data resolves)

**Aggregation rules:** contact features → customer features via engagement-weighted aggregation. Primary contacts (high engagement) weight more than peripheral contacts in customer-level scores. A "champion" contact contributes more to customer-level buyer quality than a "dormant" one.

**Refresh:** weekly batch. Some signals (seasonality, capability rhythm) already on independent schedules and remain so.

### Level 5: Industry

**Derived memory:** cross-customer aggregation per industry segment. Production today: `industry_benchmarks` view (avg strike rate, avg quote value, avg email velocity per industry, requiring ≥3 person-contacts). Catalog extends this with industry-peer comparisons (C3).

**Blocker:** industry data quality (87% missing). Resolution path is a Tuesday decision.

**Aggregation rules:** customer features → industry patterns via simple averages with confidence scoring (low-N segments surface as insufficient data).

**Refresh:** monthly batch sufficient. Industry patterns shift slowly.

### How the levels connect: structured derivation

When new evidence arrives at level N (a new email, a new thread message), it propagates upward through batch refresh:

```
New email
    → Email classification (immediate, in extraction pipeline)
    → Thread feature update (within hours, async)
    → Contact persona refresh (next daily cron)
    → Customer rollup refresh (next weekly cron)
    → Industry pattern refresh (next monthly cron)
```

Each level reads from the level below at its own refresh cadence. No level reads raw data from levels far below — contact persona doesn't read individual emails, it reads thread aggregates. This keeps computation costs bounded and enables incremental updates.

### How the levels connect: semantic retrieval (Pattern B)

Structured memory (above) answers "what is the platform's derived view of this contact?" — fast, stable, scored.

Semantic memory via embeddings answers "what specific evidence supports this view?" — the email-level corpus is queryable by similarity, retrieving relevant emails to substantiate derived insights.

The two patterns connect at the point of insight surfacing:

```
User views contact profile
    → Structured memory provides scores (Intent: low, Specificity: medium)
    → User clicks for evidence
    → Semantic retrieval finds emails most representative of "low intent"
    → User sees actual emails that support the conclusion
```

This is where source data link wiring (bucket list item) lives. Without it, derived insights are opaque. With it, the platform produces insights *that can be defended* — Linda can verify a Q1 score by reading the supporting emails directly.

Pattern B does not drive the score itself. The score is computed from structured features (Pattern A). Pattern B makes the score *defensible*.

### Why Pattern B is not used to compute insights (in v1)

A tempting alternative: compute insights via RAG at query time. Retrieve relevant emails, feed to LLM, synthesise answer.

Reasons we don't:

1. **Stability:** RAG-generated answers vary with retrieval and synthesis randomness. A buyer-quality score that changes between page refreshes erodes trust.
2. **Cost:** retrieval + synthesis on every view is expensive at scale.
3. **Comparability:** Pattern A produces comparable scored values across contacts/AMs/customers. RAG produces narratives that are hard to rank or aggregate.
4. **Quality dependency:** RAG quality depends on embedding quality and corpus completeness. We already have classifier sharpness issues; coupling derived insights to embedding quality compounds the risk.

Pattern B's strength is exploration and evidence; Pattern A's strength is characterisation and comparison. Each used for what it's good at.

### Future direction: Pattern B as exploratory surface

Beyond the catalog: Pattern B enables a query interface where Carbon8 can ask ad-hoc questions ("show me threads where customers raised concerns about turnaround"). The infrastructure exists — `langchain_tools.py`, embeddings, pgvector. The surface (UI for querying, governance over what queries are allowed) does not.

This is a v2+ capability. The catalog's first deliverables build the structured memory layer that makes the platform's stable insights reliable. The exploratory surface comes after.

### Memory refresh: implementation pattern

For each catalog insight, the implementation follows the same shape:

```
1. Feature extraction (LLM if needed) — runs per email or per message
2. Thread-level aggregation — runs when thread updates
3. Contact-level aggregation — runs in daily cron, recency-weighted
4. Customer-level rollup — runs in weekly cron, engagement-weighted
5. Industry-level rollup — runs in monthly cron (if applicable)
```

The existing `refresh-persona-metrics` cron extends naturally. New cron jobs added per insight as needed, scheduled to align with the level they refresh.

### Trade-offs accepted in this architecture

- **Latency:** weekly refresh means insights lag actual behaviour by up to a week. Acceptable for stable characterisations; not acceptable for action-triggered alerts (which are Layer B in the two-layer execution model, separate from this memory architecture).
- **Storage growth:** each derived layer stores derived state. Disk usage grows with platform usage. Partially mitigated by Pattern A producing compact scored values rather than free text.
- **Aggregation lossiness:** rolling up from email-level to industry-level necessarily loses detail. The semantic retrieval layer (Pattern B) recovers detail on demand when needed.
- **Confidence handling:** every aggregation introduces uncertainty. Confidence scoring at every level is non-negotiable — silent low-confidence outputs would mislead more than they help.


---

## The 13 questions — computation summary

### Contact Persona

**Q1. Legit buyer vs window-shopper.** *(Full spec below)* Foundation: strike rate, quote count, persona classification all production. Add: contact-level aggregation of buying signals, competitor mentions, decision velocity (from qb_quotes timing). Output: three-component score (intent, specificity, follow-through) with confidence.

**Q2. Demanding vs reasonable.** Foundation: urgency, sentiment, sentiment_score per email already extracted. Add: contact-level aggregation, requirement-shift detection (LLM classification on contact response chains), escalation pattern recognition.

**Q3. Contact responsiveness.** *(Full spec below)* Foundation: thread-aware bidirectional response time, business-hours variant, thread_status all production. Add: substance classification (substantive / deflective / requirement-shifting) via LLM pass on contact responses.

**Q4. Product recommendations from same-company patterns.** Foundation: per-contact capability profile, market basket analysis with product_affinities, cross-contact gaps all production. Add: aggregate untapped capabilities per contact considering company peer behaviour, surface as contact-level recommendation.

**Q5. Seasonality (contact level).** Foundation: company and industry seasonality production. Decision needed: contact-level seasonality may not be useful (most ordering behaviour is company-level). Likely better to surface contact's company seasonality on the contact page than build new per-contact seasonality.

**Q6. Engagement-revenue correlation.** Foundation: engagement scorer already weights revenue 15% when QB present; per-capability revenue exists. Add: explicit correlation coefficient per contact (engagement score vs revenue trend) rather than weighted blend. Also: consolidate two existing engagement score systems into one canonical computation.

### Company Profile

**C1. Contact-level questions rolled up to customer.** Foundation: `company_contact_summary` exists with persona distribution rollups. Add: per-Q1/Q2/Q3 rollup logic, weighted by contact engagement to handle multi-contact customers correctly.

**C2. Product portfolio diversification.** Foundation: per-customer capability tracking via QB jobs. Add: diversification metric (Shannon entropy or simpler count-based), trend over time, threshold for "diversifying" vs "concentrating". Optional: industry-peer comparison (depends on industry data resolution).

**C3. Industry-peer recommendations.** Foundation: `industry_benchmarks` view exists. Blocker: industry data quality (87% missing). Path depends on Tuesday's decision on industry resolution.

### AM Insights

**AM1. Engagement-revenue correlation per AM.** Foundation: engagement scores aggregate upward; AM revenue in snapshots. Add: explicit statistical correlation per AM, with confidence intervals. Requires statistical library (scipy or similar).

**AM2. Compare AM behaviours and outcomes.** *(Full spec below)* Foundation: outcomes data in `am_performance_snapshots`; outbound emails already classified for intent/sentiment/entities. Add: QB-AM name mapping, role-scoped endpoint, frontend dashboard, AM behaviour quality features (tone/specificity/promise tracking via new LLM pass), correlation computation.

**AM3. Proactiveness impact on orders.** Foundation: initiation ratio per contact, `thread_role='initial'` on outbound. Add: per-thread persistent proactive flag, outreach follow-through tracking (did AM contact customer before peak window?), statistical correlation with subsequent orders.

**AM4. Complaint tracking and resolution.** Foundation: complaint intent classification, urgent override. Add: state machine (open → acknowledged → investigating → resolved → closed), resolution timing, SLA, AM action workflow ("mark resolved", "escalate"), categorisation (product_quality, delivery, billing, service).

---

## Full specification: AM2 — Account Manager Comparison

### Business question

Across the Carbon8 AM team, which AMs are operating most effectively as relationship managers and revenue producers, and what specific behaviours distinguish stronger from weaker performance?

This is the May 12 ask. The question that most directly justifies the "Email Intelligence" name — answered from how AMs communicate, not from QB outcomes alone.

### Why this matters

QB tells you each AM's revenue, strike rate, customer count. It doesn't tell you why one AM converts at 35% and another at 15% on similar portfolios. The "why" lives in email behaviour: response speed, proactiveness, language choices, consultative vs transactional style, how objections are handled, how quiet customers are re-engaged.

Intent: surface patterns distinguishing strong AM behaviour so they can be shared across the team. Not performance management ("Kenneth is slower than Linda") but practice transfer ("Linda's pattern of asking clarifying questions before quoting correlates with her higher strike rate — worth Kenneth trying").

### Dashboard structure

Three sections per AM profile:

**Section 1 — Outcomes (QB-grounded):** strike rate, total revenue, customer count, average deal size, retention rate, trend over last 12 months.

**Section 2 — Behaviours (email-derived):**
- Response speed (median, business-hours variant)
- Thread engagement depth (avg back-and-forth count)
- Proactiveness ratio (threads AM-initiated vs contact-initiated)
- Consultative ratio (messages with questions vs messages providing answers)
- Specificity ratio (customer-context references vs generic language)
- Tone adaptation (variance in formality across customer types)
- Action follow-through (promises made in AM messages vs marked complete in later messages)

**Section 3 — Correlations:** which Section 2 behaviours most strongly correlate with this AM's Section 1 outcomes. Comparison to team median per behaviour. Specific behaviour gaps where the AM diverges meaningfully from top performers.

### Visibility model

Client managers see full comparison across AMs by name. AMs see their own profile plus anonymised team aggregate (median behaviours, distribution percentiles). Admin sees everything.

This is the suggested model for Carbon8 culture; final call is yours.

### Build components

Each component described factually. Clustering and sequencing are your call.

**Component 1 — QB-to-platform AM name mapping table.**
- New table `qb_am_mapping (qb_account_manager_string, user_id, status, notes)`
- Manual population for 4 active AMs + nullable rows for 10 departed/inactive AMs
- Successor mapping policy for departed AMs (whose customers inherit their history)
- Update `AMEfficiencyAnalyzer` to join through this table
- Without this, every AM revenue number is currently silently mis-attributed
- Effort: half a day including data entry and verification

**Component 2 — Endpoint role-scoping.**
- Apply `_validate_client_access` dependency to `GET /ai/am-performance/{client_id}`
- Add row-level filter: account_manager role gets own row + team_median aggregate; client_manager + admin get full data
- Extract `_validate_client_access` to shared `auth.py` dependency
- Same pattern needed for related endpoints in catalog
- Effort: half a day

**Component 3 — Snapshot generation independence.**
- Currently snapshots only generate during Strategic Digest run
- Add scheduled cron (weekly) or on-demand endpoint
- Add `revenue_change_pct` population (column exists, never populated)
- Effort: 2-3 hours

**Component 4 — AM behaviour feature extraction (new LLM pass).**
- Existing classifier processes outbound emails for intent/sentiment/entities — that's reusable
- Net-new extraction needed: AM email quality features (consultative tone, specificity, proactiveness markers, promise tracking, options-vs-single-recommendation patterns)
- Either extend existing classifier prompt with these features, or separate behaviour-extraction pass
- New columns or new table for behaviour features per outbound email
- Backfill across historical outbound emails (~140K emails, ~$30-50 in API cost)
- Effort: 2-3 days including prompt iteration and validation

**Component 5 — Frontend dashboard pages.**
- Per-AM profile page (`/manage/am-performance/{user_id}`) with three-section layout
- Team comparison view (`/manage/am-comparison`) — client_manager+ only
- Reuses existing `amPerformanceApi` service (wired up, never called)
- Effort: 2-3 days

**Component 6 — Correlation computation.**
- Statistical analysis per AM: which behaviours correlate with their outcome metrics
- Cross-AM comparison: each AM's behaviour percentile vs team median
- Requires statistical library — scipy.stats.pearsonr or similar
- Significance testing (correlation isn't meaningful at small sample sizes)
- Effort: 1 day

**Component 7 — Backfill across historical outbound emails for Component 4 features.**
- One-time job to extract behaviour features from existing outbound emails
- ~140K emails over the platform lifetime
- API cost estimate $30-50 at current rates
- Effort: 1 day including verification

### Validation method

Three checks before broad rollout:

1. Sanity check on aggregations — team-level metrics from existing data should match what AMs intuit about their own behaviour. If Linda's "response speed median 6 hours" feels wildly off to her, the underlying data or aggregation has a problem.

2. Correlation sanity — behaviours that correlate with strike rate in this data should align directionally with industry research on AM effectiveness. Zero correlation where industry research says it strongly matters is a signal that the metric is wrongly computed.

3. AM review — show one AM's profile (with permission) to Jeff and/or that AM themselves. Does the picture ring true? Anything surprising? Anything obviously wrong? Qualitative gut-check before scaling.

### Open design questions

1. Visibility model confirmation — proposed model (client_manager sees all AMs, AMs see own + anonymised team aggregate) needs Carbon8 culture validation
2. Successor mapping for departed QB AMs — Dan Sutherland's $X customers, where does that revenue attribute?
3. Causation framing — correlations between behaviour and outcomes don't prove causation. UI should frame as patterns to investigate, not prescriptions
4. Behaviour normalisation for customer mix — AMs with different customer portfolios may show behaviour differences that reflect customer differences, not AM differences. v2 should normalise; v1 should note this caveat

### Known limitations (v1)

- Out-of-office contact patterns not handled — auto-responder periods will appear as slow in scores
- The 65% `general_enquiry` catch-all caps signal quality for behaviour metrics depending on intent specificity
- Behaviour comparison assumes equivalent customer portfolios; v1 doesn't normalise for customer mix
- Departed-AM revenue handling depends on successor mapping decision

---

## Full specification: Q1 — Legit Buyer vs Window-Shopper

### Business question

For each contact who requests quotes from Carbon8, is this person likely to convert quotes to actual orders, or are they primarily using Carbon8 as a price benchmark for purchasing elsewhere?

In commercial print this is "quote fodder" behaviour — buyers who collect multiple quotes to pressure their preferred printer on price, or to satisfy procurement requirements, without serious intent to use the quoting printer.

### Why this matters

AMs invest real time per quote (estimation, custom specs, sample preparation). A contact at 15% strike rate consuming the same effort as a contact at 60% strike rate is a 4x cost-per-conversion difference. The platform should help AMs allocate effort proportionally.

This is also a question QB cannot answer alone. QB tells you conversion ratio. It cannot tell you why — whether low conversion is from shopping around, wrong pricing, slow turnaround losing to faster competitors, or speculatively quoting projects that never get funded.

### Signal sources

Already production:
- Strike rate per contact (`contact_quote_metrics` view)
- Total quote count and accepted count per contact
- Persona classification (champion, active_buyer, prospect, dormant)
- Per-email buying signals, business signal score, competitor mentions
- Per-email entity extraction (budget_signal, buying_signals, action_items)

Available but not aggregated to contact level:
- Quote-to-acceptance timing (qb_quotes.date_created, date_accepted exist; days_to_accept not computed)
- Per-contact aggregation of buying signals from `ai_email_intelligence`
- Per-contact competitor mention frequency

Net-new extraction:
- Intent signal per thread: how committed does the contact read in their language (price-comparison phrases, project context, decision-prompting urgency)
- Specificity signal per thread: detailed specs vs vague requests, whether files/proofs are provided
- Follow-through signal per thread: what happens after quote sent (silence, negotiation, detail clarification)

### Output shape

Three components plus confidence, surfaced separately rather than as opaque single number:

- **Intent signal** (low / medium / high): how committed do the emails read
- **Specificity signal** (low / medium / high): how detailed and project-grounded are requests
- **Follow-through signal** (low / medium / high): what happens after quote sent
- **Confidence** (low / medium / high): based on thread count, consistency, recency

Plus 1-2 sentence rationale citing specifics: "Frequent quote requests but rarely supplies print-ready files. Recent threads show language like 'comparing with two other suppliers' on 3 of last 5 quotes. Average days between quote sent and any follow-up: 18."

Three-component split matters because each implies different action. Low intent → AM might deprioritise. Low specificity with high intent → AM might invest in scoping conversations. High intent and specificity but low follow-through → operational/pricing issue rather than buyer issue.

### Computation approach

Layer A (batch, weekly):

1. For each contact, identify qualifying threads in last 12 months (with recency weighting)
2. For each thread, LLM extracts intent / specificity / follow-through scores from email content (new prompt, behaviour-extraction pass)
3. Aggregate per contact: recency-weighted average of thread-level scores
4. Cross-reference with existing QB-derived signals (strike rate, quote velocity, decision timing)
5. Compute confidence from thread count + consistency + recency
6. Cache on contact profile, refresh weekly

The LLM prompt is the core engineering work. Validation against QB strike rate is the methodology check — high-intent contacts should have meaningfully higher strike rates than low-intent.

Quote-to-acceptance timing computation (currently missing) feeds into this: contacts with consistent ~14-day decision cycles read as committed buyers; long delays (60+ days) read as speculative.

### Where it surfaces

- Contact profile page: three-pill display under persona section (Intent / Specificity / Follow-through) with confidence indicator and rationale on expand
- Sales Opportunities widget: when a contact has low buyer quality but high quote volume (Peter Howie / RareID pattern — 514 quotes, 80 accepted, 15.6% strike), flag as "high quoting activity, low buyer signal — possible quote-fodder pattern"
- AM dashboard: "Contacts you're investing the most quoting time in, ranked by buyer quality"

### Validation method

Two checks:

1. Quantitative: LLM-extracted intent scores correlate with QB strike rate. High-intent contacts should convert more. If correlation is weak, the prompt is extracting wrong signal.

2. Qualitative: spot-check 30-50 contacts. Linda or Kenneth reviews algorithm output against their own intuition. Where the algorithm disagrees with the AM, dig into why — either prompt issue or genuine signal the AM hadn't seen.

### Open design questions

1. Minimum threads for meaningful score — guess 3 threads with at least 1 in last 90 days; tune after seeing real data
2. Handling contacts who shift behaviour (window-shopper becomes serious buyer or vice versa) — recency weighting addresses this, but threshold for "meaningful shift" detection is a v2 refinement
3. Quote-fodder explicit classification — should low-buyer-quality contacts get an explicit persona category, or is the three-component score sufficient

### Known limitations (v1)

- Depends on contact having sufficient email history (3+ threads); low-engagement contacts will show as low confidence
- LLM extraction quality determines signal quality; will require prompt iteration
- Doesn't distinguish legitimate-but-slow buyers (long procurement cycles) from speculative quoters without other signals
- Out-of-office handling not implemented

---

## Full specification: Q3 — Contact Responsiveness

### Business question

For each contact engaged with Carbon8, how reliably and quickly do they respond when an AM needs something from them — information for a quote, sign-off on a proof, approval of pricing, response to follow-up? And beyond timing, what does response quality reveal about how the relationship operates?

### Why this matters

In commercial print, deals stall on the customer side as often as the printer side. An AM waiting on a contact for spec clarification can lose a week, lose the production slot, or lose the deal to a faster competitor. Knowing which contacts respond quickly vs slowly lets the AM plan workload realistically — chase slow-responders earlier, build buffer for jobs dependent on slow contacts, prioritise quick-responders for time-sensitive opportunities.

The earlier implementation computed response times from email timestamps. That's a starting point, but misses what each response was. A contact who "responds in 2 hours" but always replies with "let me check internally" isn't actually fast — they're polite delays. The platform should distinguish.

### Signal sources

Already production:
- Thread-aware response time tracking (response_time_tracker.py)
- Bidirectional metrics: our response time to them, their response time to us
- Auto-reply filtering (18 patterns), outlier exclusion (>7 days)
- Business-hours variant per mailbox timezone
- Initiation ratio per contact
- Thread status engine identifies overdue threads (>7 days waiting)

Available, not yet used:
- `thread_status` engine output can identify "AM waiting for contact" periods via last-sender check
- Engagement scorer already uses response time as 14% factor

Net-new extraction:
- Substance classification on contact response messages: substantive (direct answers, files supplied) / deflective ("I'll check", "get back to you") / requirement-shifting (introduces new requirements that restart clock)

### Output shape

Three components plus confidence:

- **Response speed** (fast / moderate / slow / silent): median time-to-respond when AM is waiting
- **Response substance** (substantive / deflective / requirement-shifting): does the response actually move things forward
- **Reliability** (consistent / variable / unreliable): how predictable is the pattern
- **Confidence**: based on qualifying thread count, consistency, recency

Plus rationale: "Median response time 8 hours during business days. 70% of responses are substantive. Occasional silence on quotes >$10K — last three high-value quotes went unanswered for 14+ days."

The three-component split: "slow but substantive" is very different from "fast but deflective." A slow-but-substantive contact is reliable — you can plan around them. A fast-but-deflective contact creates false urgency.

### Computation approach

Layer A (batch, weekly):

1. For each contact, identify threads from last 12 months where contact participated
2. Use existing thread_status + last-message-sender check to identify "AM waiting for contact" periods
3. For each waiting period: compute response time (or mark still pending)
4. For each contact response message: LLM classifies as substantive / deflective / requirement-shifting (new prompt)
5. Aggregate with recency weighting per common convention
6. Compute confidence from thread count, consistency, recency

Reuses existing response_time_tracker output for timing — no new timing infrastructure needed. The new work is substance classification.

### Where it surfaces

- Contact profile page: three-pill display (Speed / Substance / Reliability) with rationale on expand
- Thread view: while viewing an active thread, surface "Median 8h response; current thread waiting 36h — outlier"
- AM workflow: "needs chasing" list showing threads exceeding contact's typical response time
- Customer profile: aggregate contact-level scores showing customers with structurally slow patterns (often signals internal procurement complexity)

### Validation method

1. Quantitative: response speed correlates with quote-to-acceptance days from QB. Fast responders close quotes faster on average.
2. Qualitative: spot-check 20 contacts. Read threads. Does substance classification match human reading? Distinguishing genuine "need to check internally" from soft-no "get back to you" is the test of prompt quality.

### Open design questions

1. What counts as "AM waiting for contact" — investigation showed thread_status + last-sender check is a reasonable v1; LLM classification at message level is a v2 refinement
2. Multi-participant threads — when three contacts at a customer are on a thread, who's responsible for responding? Attribute to whichever contact AM addressed directly
3. Out-of-office handling — documented as v1 limitation; some auto-responder periods will appear as slow

### Known limitations (v1)

- Out-of-office detection not implemented
- Single contact attribution in multi-participant threads
- Substance classification is new and will require prompt iteration

---

## One-page sketches: remaining 10 questions

### Q2 — Demanding vs Reasonable Contact

**Question:** Is the contact's expectation level reasonable or persistently demanding (frequent escalations, requirement shifts, deadline compression)?

**Foundation:** Per-email urgency and sentiment already classified. Sentiment_score 0-100. Escalation language detectable via existing classifier (urgency=critical/high).

**Gap:** Contact-level aggregation of urgency/escalation patterns. Requirement-shift detection (LLM pass on response chains identifying when contact introduces new requirements mid-thread).

**Output:** Demanding/reasonable score with breakdown (escalation frequency, requirement-shift frequency, sentiment trend, deadline-pressure language frequency). Confidence indicator.

**Surfaces on:** Contact profile, AM dashboard "high-maintenance contacts" view.

**Effort:** Low-medium. Aggregation work plus one new LLM prompt for requirement-shift detection.

**Open:** How to distinguish legitimately urgent business contexts from persistently demanding behaviour. Probably needs cross-referencing with QB tier (large customers may have legitimate urgency more often).

### Q4 — Product Recommendations from Same-Company Patterns

**Question:** What products has this contact ordered, and what related products might they buy based on what other contacts at the same company buy?

**Foundation:** Per-contact capability profile production. Cross-contact capability gaps production. Market basket analysis production (product_affinities).

**Gap:** Surface "what your colleagues at this company buy that you don't" as contact-level recommendation. Currently exists at company level via RecommendationsPanel; needs contact-level rendering.

**Output:** Per-contact list of suggested capabilities with rationale (which colleagues use them, revenue volume, confidence from cross-customer market basket).

**Surfaces on:** Contact profile page, Sales Opportunities widget.

**Effort:** Low. Aggregation + UI work. No new extraction needed.

### Q5 — Seasonality (Contact Level)

**Question:** Does this contact have a seasonality pattern in their ordering?

**Foundation:** Company and industry seasonality production. Outreach windows existing.

**Recommendation:** Don't build contact-level seasonality as a separate insight. Most ordering behaviour is company-level, not contact-level. Surface the contact's company seasonality on the contact page (a UI change, not new computation).

**Surfaces on:** Contact profile — show parent company's seasonality view.

**Effort:** Trivial. UI work only.

### Q6 — Engagement-Revenue Correlation (Contact Level)

**Question:** Does this contact's engagement level correlate with revenue they generate?

**Foundation:** Engagement scorer weights revenue 15% when QB present. Time-series engagement history in metric_history. Per-contact revenue via persona view.

**Gap:** Explicit correlation coefficient per contact (engagement trend vs revenue trend over 12 months). Also: consolidate the two existing engagement score systems (10-factor persistent vs 3-factor in persona view) into single canonical computation.

**Output:** Correlation coefficient with significance indicator. Trend chart overlaying engagement and revenue.

**Surfaces on:** Contact profile.

**Effort:** Medium. Correlation computation requires statistical library. Engagement score consolidation is technical debt with broad downstream impact — separate decision.

### C1 — Contact-Level Questions Rolled Up to Customer

**Question:** For each customer, what do contact-level patterns aggregate to at the customer level?

**Foundation:** `company_contact_summary` view exists with persona distribution rollups.

**Gap:** Per-Q1/Q2/Q3 rollup logic with engagement-weighted aggregation (multi-contact customers shouldn't average all contacts equally — primary contacts should weight more than peripheral ones).

**Output:** Customer-level versions of buyer quality, demandingness, responsiveness, with breakdown showing per-contact contribution.

**Surfaces on:** Customer profile page.

**Effort:** Low-medium. SQL aggregation work. Depends on Q1/Q2/Q3 being built first.

### C2 — Product Portfolio Diversification

**Question:** Is the customer's product portfolio diversified or concentrated?

**Foundation:** Per-customer capability tracking via QB jobs production.

**Gap:** Diversification metric (count-based or Shannon entropy), trend over time. Optional industry-peer comparison depends on industry data quality.

**Output:** Diversification score with capability breakdown, trend, peer comparison (if industry resolved).

**Surfaces on:** Customer profile.

**Effort:** Low for basic version. Medium if industry-peer comparison included.

### C3 — Industry-Peer Recommendations

**Question:** What products do similar-industry customers buy that this customer doesn't?

**Foundation:** `industry_benchmarks` view exists. Market basket exists.

**Blocker:** Industry data quality. 87.3% of customers have no usable industry. Resolution path needed before this insight can be built reliably.

**Three resolution paths:**
1. Carbon8 backfills QB-side industry on missing customers (real-people-doing-real-work effort, weeks)
2. Platform AI-infers industry from email content/domain/company name (2-3 days, ~70-80% accuracy)
3. Defer until data improves

**Effort:** Cannot estimate until resolution path chosen.

**Decision needed:** Tuesday's call.

### AM1 — Engagement-Revenue Correlation per AM

**Question:** Does each AM's engagement style correlate with the revenue they develop?

**Foundation:** Engagement scores aggregate upward; AM revenue in snapshots.

**Gap:** Explicit statistical correlation per AM, with confidence intervals. Requires statistical library (no scipy/statsmodels imports anywhere currently).

**Output:** Per-AM correlation coefficient, significance, comparison to team. Probably surfaces alongside AM2.

**Effort:** Medium. Statistical computation + integration with AM2 dashboard.

### AM3 — Proactiveness Impact on Orders

**Question:** Does proactive outreach from the AM generate more orders?

**Foundation:** Initiation ratio per contact. Thread_role='initial' on outbound. Seasonality outreach windows.

**Gap:** Persistent per-thread proactive flag. Outreach follow-through tracking (did AM contact customer before peak window?). Statistical correlation between proactive outreach and subsequent orders.

**Output:** Per-AM proactiveness score with breakdown (initiation rate, window-aligned outreach rate). Correlation with order generation.

**Effort:** Medium. New per-thread flag + correlation computation.

### AM4 — Complaint Tracking and Resolution

**Question:** Are complaints tracked through to resolution, and do AMs address them effectively?

**Foundation:** Complaint intent classification, urgent override existing.

**Gap:** State machine (open → acknowledged → investigating → resolved → closed). Resolution timing. SLA. AM action workflow. Categorisation (product_quality, delivery, billing, service).

**Output:** Complaint lifecycle dashboard per AM (open count, avg resolution time, closure rate, reopened rate). Per-customer complaint history.

**Effort:** High. Real net-new work — state machine, status column on threads, UI workflow for AMs to mark resolved/escalate. Probably 1-2 weeks of focused work.

**Surfaces on:** AM dashboard, customer profile (complaint history), dedicated complaints view.

---

## Cross-cutting concerns

### Engagement score consolidation

Two engagement scoring systems exist:
- 10-factor persistent score in `customer_contacts.engagement_score` (production, time-series tracked)
- 3-factor score in `contact_persona` view (production, recomputed on view refresh)

Both surface in different UI contexts. Values can disagree because they weight different inputs. Consolidation into a single canonical score is technical debt with broad downstream impact (recommendation engine, persona views, frontend display all depend on engagement values).

Recommendation: keep both for now, document the divergence, plan consolidation as a v2 refactor once new insights stabilise.

### Industry data quality

Already covered in "What's missing". Resolution decision needed Tuesday.

### Outbound email classification clarification

Earlier framing suggested outbound emails were skipped by the classifier. Investigation showed they are classified fully — only `action_type` is forced to `no_action`. All other 16 fields populate normally. AM behaviour features can build on existing classification rather than requiring a separate extraction pipeline (though new behaviour-specific features will need prompt additions).

### Intent classifier sharpness

65% of emails classify as `general_enquiry` catch-all. Sample analysis revealed 45% noise (filterable pre-classification) and 55% real signal not distinguished. Options: pre-classification noise filter (cheap, half-day), prompt refinement with re-classification (~$30-40 API cost, half-day work plus 24-48h re-run), or insight design that routes around catch-all. Recommendation depends on which insights actually need intent specificity — many can work without it.

### Causation framing in correlation insights

AM2 Section 3, AM1, AM3 all surface correlations. UI framing should consistently present these as "patterns to investigate" rather than prescriptions. A correlation between consultative tone and higher strike rate doesn't prove causation — good AMs may do both. Document this caveat where correlations surface.

---

## Platform stabilisation work (parallel track)

Database performance analysis on 1 June identified specific optimisations for the current Supabase tier. These are independent of the catalog items and will run in parallel.

**Remediation items, ordered by impact:**

1. **RLS auth function pattern fix.** Several RLS policies call `auth.uid()` in a way forcing per-row re-evaluation. Wrapping in `(SELECT auth.uid())` forces single evaluation per query. Affects emails, mailboxes, audit_log, user tables. SQL-only fix, immediate impact on cache pressure.

2. **Email count aggregation refactor.** `update_company_email_counts_from_junction` consumes ~14% of total DB time. Convert from full-recompute to incremental updates via triggers or event-driven pattern.

3. **Keyset pagination on heavy endpoints.** PostgREST default uses `pg_catalog.count()` on full result set per page request. Replace with cursor-based pagination on qb_operations, qb_jobs, emails list endpoints. Significant CPU reduction.

4. **Capability tags GIN operator fix.** Current query uses `=` on GIN-indexed column (designed for `@>` containment). Single-query rewrite, fixes 33% cache-hit query.

5. **Unused index cleanup.** Drop unused indexes on emails table after verifying `idx_scan = 0` over representative window. Reclaims buffer cache (which is currently under pressure).

6. **Foreign key index additions.** 185 unindexed FK columns flagged. CONCURRENTLY add indexes on hot tables. Eliminates sequential scan risk on JOINs.

7. **Email body_text vertical partition.** Move body_text to child table. Wide-column SELECTs over 9.71 GB emails table become narrower on hot path. Reduces tail latency on list/preview queries.

8. **Multiple permissive RLS policy consolidation.** Combine overlapping permissive policies on user-related tables. Reduces policy evaluation overhead.

This work is engineering remediation, not new feature development. Sequencing: items 1-5 can land in the same week; items 6-8 are larger and benefit from being separated.

---

## What this document is and isn't

**This is** a design proposal for completing the insight layer, grounded in verified codebase state as of 1 June 2026.

**This isn't** a commitment to ship all 13 questions. Which to prioritise and in what sequence is the conversation for Tuesday's call.

**This isn't** a claim that nothing has been built. Substantial foundational work is in production, particularly at the contact level. The proposal completes rather than rebuilds.

**This isn't** trip-thinking presented as fact. The bottom-up consolidation framing turns out to match how existing persona/engagement/response systems already work — reassuring rather than coincidental. Validation of the new content-extraction layers comes from building one insight end-to-end and observing whether the methodology produces signal Carbon8 finds actionable.
