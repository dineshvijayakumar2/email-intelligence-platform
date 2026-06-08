# Bucket List: 1 June 2026 — 30-45 day plan

**Purpose:** Tracking all planned work items for the next 30-45 days. Sequencing reflects AM Comparison as first deliverable (per 1 June refinement). Final sequencing confirmed after Tuesday 2 June call with Jeff.
**Status convention:** [ ] not started / [~] in progress / [x] done + verified / [D] deferred next sprint
**Companion document:** insight_catalog.md (full spec) and insight_catalog_summary.md
**Related:** DB_PERFORMANCE_SNAPSHOT_JUN01.md (baseline for measuring impact); today's egress audits captured in BODY_TEXT_EGRESS_AUDIT.md and BUYER_QUALITY_AUDIT.md

---

## Priority 1: AM Comparison (first deliverable, 4-5 weeks)

The 12 May ask was for AM comparison based on thread insights — language, response speed, value generated, customer feedback signals. First deliverable includes the email-content-derived behaviour features, not just timing.

### Foundation (Week 1)
- [ ] **Component 1: QB-to-platform AM name mapping table** (`qb_am_mapping`)
  - Fixes zero-match silent attribution error
  - 4 active AMs + nullable rows for 10 departed/inactive AMs
  - Successor mapping policy for departed AM revenue
- [ ] **Component 2: Endpoint role-scoping**
  - Apply `_validate_client_access` to `GET /ai/am-performance/{client_id}`
  - Row-level filter: AM role gets own row + team_median aggregate
  - Extract to shared `auth.py` dependency
- [ ] **Component 3: Snapshot generation independence**
  - Decouple from Strategic Digest
  - Scheduled cron (weekly)
  - Populate `revenue_change_pct` (currently always NULL)

### Behaviour extraction (Weeks 2-3)
- [ ] **Component 4a: AM behaviour feature extraction prompt design**
  - New LLM pass on outbound emails
  - Features: consultative tone, specificity, proactiveness markers, promise tracking, options-vs-single-recommendation patterns
  - Iterate prompt against sample 100 outbound emails
- [ ] **Component 4b: Linda/Nic validation review (Week 2 milestone)**
  - Show sample behaviour features to AMs
  - Validate signal correctness before scaling
- [ ] **Component 4c: Storage schema for behaviour features**
  - New columns or new table for per-outbound-email behaviour scores
- [ ] **Component 7: Backfill across historical outbound emails**
  - ~140K emails, ~$30-50 API cost
  - Run after prompt validated

### Dashboard and correlations (Weeks 3-5)
- [ ] **Component 5a: Frontend per-AM profile page**
  - Three sections: Outcomes, Behaviours, Correlations
  - Route: `/manage/am-performance/{user_id}`
- [ ] **Component 5b: Cross-AM comparison view**
  - Client_manager+ visibility only
  - Route: `/manage/am-comparison`
- [ ] **Component 6: Correlation computation**
  - Add `scipy` to dependencies
  - Per-AM correlation: behaviour metrics vs outcome metrics
  - Team-median comparison
  - Significance testing (small sample warnings)

### Cross-cutting for AM2
- [ ] Reusable `_validate_client_access` extracted to `auth.py`
- [ ] UI framing: correlations presented as patterns to observe, not prescriptions
- [ ] Out-of-office handling documented as v1 limitation

---

## Priority 2: Contact persona insights (after AM Comparison)

### Q1 — Legit Buyer vs Window-Shopper (~3 weeks)
- [ ] Quote-to-acceptance timing computation (`days_to_accept` on qb_quotes; aggregate per contact)
- [ ] Contact-level aggregation of buying signals from ai_email_intelligence
- [ ] Contact-level competitor mention frequency aggregation
- [ ] LLM extraction pass for thread-level intent / specificity / follow-through signals
- [ ] Three-component buyer quality score with confidence (Layer A batch, weekly refresh)
- [ ] UI: three-pill display on contact profile
- [ ] UI: Sales Opportunities widget flag for quote-fodder pattern
- [ ] Validation: correlate algorithm output with QB strike rate on 30-50 sample contacts

### Q3 — Contact Responsiveness (~2 weeks)
- [ ] LLM extraction pass for substance classification (substantive / deflective / requirement-shifting)
- [ ] Reuse thread_status engine + last-sender check for "AM waiting" detection
- [ ] Three-component responsiveness score (Speed / Substance / Reliability) with confidence
- [ ] UI: three-pill display on contact profile
- [ ] UI: thread view outlier indicator
- [ ] UI: "needs chasing" list in AM workflow

---

## Priority 3: Remaining catalog (after Q1 and Q3)

### Q2 — Demanding vs Reasonable
- [ ] Contact-level aggregation of urgency, sentiment, sentiment_score
- [ ] LLM extraction for requirement-shift detection in response chains
- [ ] Demanding/reasonable score with breakdown
- [ ] Cross-reference with QB tier for legitimate-urgency normalization
- [ ] UI: contact profile, AM dashboard "high-maintenance contacts" view

### Q4 — Product Recommendations (contact level)
- [ ] Aggregate untapped capabilities per contact considering company peer behaviour
- [ ] UI: surface "what colleagues at this company buy" at contact level
- [ ] Wire QB tag data (capabilities, processes, embellishments) into AI agent tools

### Q5 — Seasonality (contact level)
- [ ] UI only: surface contact's parent company seasonality on contact profile page

### Q6 — Engagement-Revenue Correlation
- [ ] Per-contact correlation coefficient computation
- [ ] UI: trend chart overlaying engagement and revenue
- [ ] Engagement score consolidation decision (see Cross-cutting)

### Company Profile (C1, C2, C3)
- [ ] C1: Per-Q1/Q2/Q3 customer-level rollup with engagement weighting
- [ ] C1: Multi-contact customer handling
- [ ] C1: UI on customer profile
- [ ] C2: Diversification metric per customer
- [ ] C2: Trend over time
- [ ] C2: UI with capability breakdown
- [ ] C3: **Decision needed Tuesday — industry data resolution path**
- [ ] C3: Wire industry_benchmarks view into recommendations (if proceeding)

### AM Insights (AM1, AM3, AM4)
- [ ] AM1: Add scipy.stats (covered under AM2 Component 6)
- [ ] AM1: Per-AM correlation coefficient with confidence intervals
- [ ] AM3: Persistent per-thread proactive flag
- [ ] AM3: Outreach follow-through tracking
- [ ] AM3: Statistical correlation between proactive outreach and orders
- [ ] AM4: State machine (open → acknowledged → investigating → resolved → closed)
- [ ] AM4: `complaint_status` column on threads
- [ ] AM4: Resolution timing tracking
- [ ] AM4: SLA enforcement
- [ ] AM4: Complaint categorisation
- [ ] AM4: AM action workflow (mark resolved, escalate)
- [ ] AM4: UI for complaint lifecycle dashboard

---

## Cross-cutting infrastructure

### Used by multiple insights
- [ ] **Insights Review page** — validation UI for marking insights correct / partial / incorrect with notes
  - Migration: `insight_validations` table
  - Backend: list insights per contact/company; record validation
  - Frontend: list view with NL summary + source data link per insight
- [ ] **Top-N page** — listing top customers with NL insight summaries
- [ ] **Email vectorisation during extraction** — new emails not auto-vectorised. Integrate into extraction pipeline post-Step 9. Enables future RAG-style insights
- [ ] **Embedding model configuration UI** — currently hardcoded to Google gemini-embedding-001
- [ ] **Source data link wiring** — traceback from insights to emails / quotes / jobs

### Decisions needed Tuesday call
- [ ] Industry data resolution path (affects C3, C2, AM2 customer-mix normalisation)
- [ ] AM2 visibility model confirmation
- [ ] Catalog prioritisation and sequencing (proposed: AM Comparison → Q1 → Q3 → rest)
- [ ] Cadence: alternate-day resuming or shift to weekly

### Engagement score consolidation (technical debt)
- [ ] Decision: which of two existing engagement score systems is canonical
- [ ] Migration plan if consolidation chosen
- [ ] Downstream impact assessment (recommendation engine, persona views, UI surfaces)

---

## Platform stabilisation — egress reduction (priority track)

Supabase egress quota exceeded in previous billing cycle. Grace period until 11 June. Current cycle at 21% of 250 GB. Remediation work prioritised by per-run egress impact. Full inventory in `BODY_TEXT_EGRESS_AUDIT.md`.

### Tier 1 — Highest egress (AI pipeline batch fetches)

These pipelines legitimately need body content but pull full bodies when truncated portions would suffice. Per-run egress: ~2.5 MB per batch × hundreds of batches.

- [ ] **vector_service.py:309** — embedding pipeline fetches body_text for 500 emails/batch. Fix: RPC with `LEFT(body_text, N)` or use partition with truncation
- [ ] **ai_email_analyzer.py:691** — AI classification fetches body_text for PAGE_SIZE emails per batch. Fix: same pattern as above
- [ ] **ai_email_analyzer.py:898** — thread context builder fetches full body_text, truncates to MAX_BODY_CHARS in Python. Fix: RPC with SQL-side `LEFT()` truncation

### Tier 2 — SELECT * on non-emails tables ✅ DONE (8 June)

5 callsites in langchain_tools.py doing `select("*")` on customer_companies, qb_customers, customer_contacts, qb_quotes, qb_jobs. These tables have JSONB columns and wide schemas.

- [x] **langchain_tools.py** — replaced 5 SELECT * callsites with explicit column lists (traced downstream usage; excluded wide `embedding`/`signature_data` JSONB columns). Commit `3082761`.

### Tier 3 — Fetch-then-truncate waste ✅ DONE (8 June)

Callsites that fetched full body_text then discarded most of it in Python. Now truncated SQL-side via two reusable SECURITY DEFINER RPCs (`emails_body_left(email_ids uuid[], n int)`, `emails_body_right(email_ids uuid[], n int)`) added in **migration 116**. Both clamp `n` (reject negative, cap at 50000) and SET search_path = public.

- [x] **analytics.py** — thread detail fetched full body for N emails, truncated to **500** chars in Python; now `emails_body_left` n=501 (501 preserves the `'...'` truncation marker). Commit `8e9e03f`.
- [x] **role_classifier.py** — fetched full body, uses last 1000 chars only; now `emails_body_right` n=1000. Validated via gate (parser self-truncates to `body_text[-500:]`, 50/50 sample identical full-vs-RIGHT(1000)). Commit `bbd648f`. **Measured: 91.2% egress reduction** (9,981→878 B/email avg over 2000 emails); projected full corpus pass **2.77 GB → 0.24 GB (saves 2.52 GB/pass)**.
- [x] **ai_insights_engine.py** — fetched full body, uses first 200 chars; now `emails_body_left` n=200. Commit `6df1449`.
- [x] **ai_digest_generator.py** — fetched full body, uses MAX_SNIPPET=200 chars; now `emails_body_left` n=200 (snippet ids = last 5 msgs/thread). Commit `b122f9c`.

### Tier 4 — Large batch preloads (ai_email_intelligence)

- [ ] **thread_tracker.py:221** — loads ALL completed classifications for entire client in 1000-row pages. Lightweight columns but high row count (100K+ per client) makes meaningful

### Structural fix (enables most of Tier 1 and 3)

- [ ] **Email body_text vertical partition** — move body_text and body_html to separate `email_bodies` table. The ~40 queries that never touch body get faster for free. The ~13 callsites that need body add a JOIN. Largest structural win.
  - 13 production callsites need JOIN after partition (see BODY_TEXT_EGRESS_AUDIT.md for full inventory)
  - 40+ email queries unaffected (don't touch body)
  - Multiple existing patterns already exclude body_text (good hygiene)

### Completed 1 June

- [x] **operations.py:1000** — `search_emails` SELECT * → explicit column list excluding body_text, body_html, raw_headers, embedding, search_text. (Note: dead code with zero production callers; fix is defensive)

### CPU / cache improvements (not egress-focused, still valuable)

- [ ] **RLS auth function pattern fix** — wrap `auth.uid()` in `(SELECT auth.uid())`. SQL-only fix
- [ ] **Email count aggregation refactor** — `update_company_email_counts_from_junction` consumes ~14% of total DB time
- [ ] **Keyset pagination on heavy endpoints** — replace PostgREST count-pagination on qb_operations, qb_jobs, emails list
- [ ] **Capability tags GIN operator fix** — current query uses `=` on GIN-indexed column
- [ ] **Unused index cleanup** — drop unused indexes on emails table after verifying `idx_scan = 0`
- [ ] **Foreign key index additions** — 185 unindexed FK columns flagged
- [ ] **Multiple permissive RLS policy consolidation** — combine overlapping policies

---

## Carryover from May sprint

### QB Match Review fixes
- [ ] **Candidates count mismatch** — tab badge shows 228 vs browse total 240
- [ ] **Method filter dropdown fix** — dropdown values stale
- [ ] **Fix email count sorting in matched view**

### QB Data Quality
- [ ] **Contact creation from QB data** — 1,344 unmatched QB customers have emails in `qb_unique_emails` but no SB contacts
- [~] **Email-method SB name correction / mis-key contamination** — ~4,250 email-matched QB customers have wrong SB company names. Mis-key bug fixed in pipeline + `company_resolver.py` (keys by `customer_key_id`). Remediation run 3 June: 174 RELINK fixes (census 209→35 genuinely-wrong), 19 DUP_COMPANY merges (CONFLICT 24→1), 3 of 4 freed CHAIN relinks. Scripts in `scripts/db/_fix_miskey_relink.py`, `_fix_conflict_dups.py`, census via `_diagnose_miskey_live.py`.
  - [ ] **Name-vs-email-content knots (human review needed)** — companies NAMED for one customer but POPULATED by another's contact emails; name-canon match picks wrong QB and resolver re-asserts the email-owner QB on next ingestion. Durable fix = correct the company name or move mis-filed contacts, NOT the QB link. Cases: Louisvuitton→Louis Vuitton (contacts @blaineynorth.com), Matthewely→Matthew Ely (studio@stephenlayfield.com), Flintwood (@virtuoso.com), Bec Morris Design (contact_chain blocker). See `memory/project_qb_name_vs_email_contamination.md`.
  - [ ] **11 UNLINK cases** — likely false positives (e.g. Arup ↔ Arup Pty Ltd); leave unless reviewed.
- [x] **Duplicate company merge (squished vs spaced names)** — 2026-06-03: consolidated 240 duplicate `customer_companies` groups (e.g. `Qreport`→`Q Report`) via `scripts/db/merge_duplicate_companies.py`; FKs repointed across 11 tables, survivors renamed to nicest name, stored counts recomputed. Fixed the count=N/drilldown=0 symptom. Rollback manifests: `_merge_rollback_batch1.json` (218) + `_merge_rollback.json` (22).
  - [ ] **16 QB-conflict pairs (human review needed)** — both squished + spaced record carry a *different* real QB customer with material revenue; auto-merge skipped to avoid orphaning a QB match. Decide which QB customer is authoritative, then merge by hand. Standouts: Coco Republic ($1,022,568 vs $318), Matthew Ely ($10,418 vs $70,337), Louis Vuitton ($29,319 vs $10,161), Cocogun, Publicis Sapient. Full list in `scripts/db/_merge_plan.json` → `skipped`. Overlaps the name-vs-email-content knots above.
- [ ] **Manual-only unmatched cleanup** — 942 "No link (manual)" unmatched QB customers with $0 revenue
- [ ] **Automate candidate review** — 972 staged candidates could be auto-promoted

### Known-issue cleanup
- [x] `hello@carbon8.com.au` mailbox extraction coverage — resolved
- [ ] 14 Carbon8 domain variant cleanup
- [ ] 21 weekdays with no email data investigation

---

## Intent classifier improvements

From 1 June general_enquiry sample analysis (45% noise, 55% real signal not distinguished).

- [ ] Pre-classification noise filter — sender-domain heuristics for spam/marketing/automated/feedback-survey patterns (reduces classification API cost ~30%)
- [ ] Decision: prompt refinement to add categories (job_instruction, delivery_and_logistics, pickup_coordination, technical_discussion, production_update, internal_communication) — requires re-classification of 145K emails, ~$30-50 API cost
- [ ] Hallucinated intent value cleanup — ~28 hallucinated values across ~166 emails

---

## Feature work (non-insight)

### Invite User System
- [ ] Migration 014: `pending_invites` + user table columns + RLS policies
- [ ] RLS policy design: anon-readable by token only
- [ ] Backend: 6 endpoints per design doc (`invites.py`)
- [ ] Frontend: InviteUserModal (two-step)
- [ ] Frontend: InviteAcceptPage (Paths A/B/C)
- [ ] Auth callback: invite detection hook
- [ ] Frontend: Users.tsx integration
- [ ] Supabase config: redirect URLs
- [ ] OAuth email-mismatch UX
- [ ] Test matrix: 3 paths x 3 providers x 4 states

---

## Infrastructure & operations

### Staged worker rollout
- [ ] Staged rollout: analytics → QB sync → reembed → remaining job types
- [ ] Verify all Tier 2 BackgroundTasks callsites work correctly alongside workers

### Operations Center UI consolidation
- [ ] Final merge plan
- [ ] Move operational triggers from AI Usage into Data Health
- [ ] Move extraction features from Extraction page into Data Health
- [ ] Retire standalone Extraction page
- [ ] "Run Full Pipeline" button

### Supabase Data API grant enforcement
- [ ] Backfill explicit GRANTs in migration templates

### Stabilization
- [ ] Smoke test checklist for daily partner use
- [ ] Confirm cron-based sync runs autonomously
- [ ] Confirm two-worker Railway Pro setup handles peak load unattended

---

## Deferred (re-examined 1 June)

### Moved into active scope by catalog
- ~~[D] Industry Gap Analysis (Insight 2)~~ → C3 in catalog (decision needed Tuesday)
- ~~[D] Status Transition Analytics (C3)~~ → Self-imposed block, not hard. Active under C3 if decision proceeds
- ~~[D] Due for Reorder~~ → Foundation exists; persistent flag could move into Layer B alerts
- ~~[D] Seasonality patterns query design + integration~~ → Largely covered by existing seasonality engine

### Re-examined, staying deferred
- [D] Real-time action signal alerts / Action Signal Engine
- [D] Role change notifications
- [D] Smart inbox revival
- [D] Vector search revival as user-facing feature
- [D] LinkedIn prospect replication
- [D] Daily/Strategic digest as user-facing features
- [D] AU seasonal calendar integration
- [D] Classification/digest model audit columns
- [D] Operations embedding (615K rows)
- [D] Quotes embedding (~19K matched)
- [D] I/O budget fix — partially addressed by Platform Stabilisation items
- [D] Dropped threads cleanup

---

## Flags / risks

- AM Comparison as first deliverable = 4-5 weeks. Weekly visible progress (samples in week 2, validated extraction in week 3) mitigates the "no visible output" risk
- Full catalog is multi-month work. Sprint sequencing happens after Tuesday's call
- Industry data quality (87% missing) is a real blocker for C3 and partial blocker for C2; resolution decision needed Tuesday
- Invite User estimate (8-9 days) deprioritised given catalog focus; would need separate sprint
- Engagement score consolidation is technical debt with broad downstream impact — decision needed before Q6 build
- Carryover QB data quality items (4,250 wrong names, 1,344 unmatched) affect insight accuracy. Should not be ignored indefinitely
- Platform stabilisation runs in parallel; key items (RLS fix, email count refactor, body_text partition) need scheduling
- Egress quota exceeded in previous cycle; grace period until 11 June. Current cycle at 21%. Primary remediation: body_text vertical partition + RPC wrappers for truncation. Tier 1 fixes require careful execution, not quick wins
