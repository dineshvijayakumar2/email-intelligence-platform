# Contact-Level Intelligence — Current State Audit

**Date:** June 1, 2026
**Scope:** Read-only investigation of contact persona, engagement scoring, response time, revenue correlation, and UI surfaces.

---

## 1. Contact Persona

**No standalone `contact_persona` table** — persona is a SQL view (migration 088, refined in 101) that computes classification on-the-fly from email metrics + QB quote data.

### 5-View Architecture

| View | Type | Purpose |
|------|------|---------|
| `contact_email_metrics` | Materialized | Per-contact email stats (total, inbound, outbound, velocity, response time, recency) |
| `contact_quote_metrics` | Regular | Per-contact QB quote/job aggregates (count, value, strike rate, margin) |
| `contact_persona` | Regular | Unified persona joining the above + `customer_contacts` + `customer_companies` |
| `company_contact_summary` | Regular | Per-company rollup of persona distribution |
| `industry_benchmarks` | Regular | Per-industry averages for benchmarking |

### Persona Classification — 8 Categories (SQL CASE Logic)

| Category | Criteria |
|----------|----------|
| `champion` | ≥5 quotes AND strike_rate ≥0.3 AND active (≤90d), OR ≥10 accepted quotes, OR ≥$50K job value |
| `active_buyer` | Has accepted quotes AND recent emails (≤90d) |
| `active_relationship` | Recent emails AND quote activity |
| `warm_lead` | Recent emails + ≥5 emails but no quotes |
| `prospect` | ≤2 quotes, no acceptances, first email within 180d |
| `inactive_buyer` | Quote history but no recent emails (>90d) |
| `dormant` | No emails 180+ days AND no quotes in last year |
| `shared_mailbox` | contact_type not person/unknown |
| `unknown` | Insufficient data |

### Engagement Score (Persona View)

Weighted composite (0–100): 30% email velocity + 30% recency + 40% quote activity.

### Refresh Mechanism

- Materialized view refreshed daily via cron (`POST /api/internal/jobs/refresh-persona-metrics`)
- Also refreshed after QB sync completes
- Uses `REFRESH MATERIALIZED VIEW CONCURRENTLY` (non-blocking reads)

### Backend Endpoints

- `GET /contacts-intelligence/{contact_id}/persona` — Full persona record
- `GET /contacts-intelligence/company/{company_id}/summary` — Company contact summary
- `GET /contacts-intelligence/company/{company_id}/contacts` — Paginated contacts with persona data

### Key Files

- `scripts/migrations/088_contact_persona_views.sql` — Foundation (5 views, indexes, refresh function)
- `scripts/migrations/101_fix_persona_classification.sql` — Enhanced classification logic
- `backend/src/routers/contacts_intelligence.py` — Persona API endpoints
- `backend/src/routers/internal_jobs.py` — Refresh endpoint

---

## 2. Contact-Level Engagement Scoring

**Separate system from persona views.** Persistent `engagement_score` column on both `customer_contacts` and `customer_companies`.

### Engine

`backend/src/services/engagement_scorer.py` (~850 lines), v2 algorithm.

### 10-Factor Weighted Formula

Weights shift based on QB data availability:

| Factor | With QB (70%) | Without QB (100%) |
|--------|---------------|-------------------|
| Recency | 17% | 25% |
| Response time | 14% | 20% |
| Reply rate | 11% | 15% |
| Email frequency | 11% | 15% |
| Thread completeness | 10% | 15% |
| Initiation balance | 7% | 10% |
| Revenue weight | 15% | — |
| Order recency | 15% | — |

### Bonuses (Multiplicative on Base Score)

| Role | Bonus |
|------|-------|
| Decision maker | +20% |
| C-level | +15% |
| VP | +10% |
| Director | +7% |
| Manager | +5% |
| Senior | +3% |

### Supporting Columns on `customer_contacts`

- `avg_response_time_seconds`, `their_avg_response_time`
- `initiation_ratio`, `reply_rate`
- `emails_per_month_avg`, `frequency_trend`
- `last_inbound_at`, `last_outbound_at`
- `open_thread_count`, `dropped_thread_count`
- `is_decision_maker`, `seniority_level`

### Time-Series Tracking

`metric_history` table stores every score computation with all factor breakdowns, entity type (contact/company), and scoring version.

### Pipeline Integration

Triggered as **Step 10.4** of the extraction pipeline in `extraction_orchestrator.py`. Batch-persisted via `batch_update_contact_analytics()` RPC.

### Overlap Note

Two overlapping engagement scores exist:
1. **Persona view** computes its own (email velocity + recency + quote activity)
2. **Engagement scorer** computes a separate persistent one (10-factor)

Both are accessible but serve different surfaces.

---

## 3. Per-Contact Response Time

**Exists. Thread-aware, direction-separated. Not naive.**

### Engine

`backend/src/services/response_time_tracker.py` — Step 11 of extraction pipeline.

### How It Works

1. Groups emails by `thread_id`
2. Detects direction changes (inbound→outbound or vice versa) to identify response pairs
3. Filters: auto-replies excluded (18 patterns), outliers >7 days excluded
4. Stores raw pairs in `email_response_metrics` with `responder_contact_id`
5. Aggregates via RPC `calculate_all_contact_response_times()`:
   - `avg_response_time_seconds` = avg where responding email `is_outbound = TRUE` (our response time to them)
   - `their_avg_response_time` = avg where responding email `is_outbound = FALSE` (their response time to us)
6. Business hours variant computed using mailbox owner's timezone

### Key Files

| File | Purpose |
|------|---------|
| `backend/src/services/response_time_tracker.py` | Core computation, thread-aware pair detection |
| `scripts/sprint2/sprint2_migration_014_fix_reply_rate_response_times.sql` | Direction-separated calculation |
| `scripts/migrations/038_optimize_response_time_query.sql` | Covering index for performance |

---

## 4. Contact-Revenue Correlation

**Exists via two parallel paths.**

### Path A — Company Inheritance

Migration 094, 3-pass propagation via `batch_propagate_qb_data_to_contacts()` RPC after QB sync:

1. **Pass 1 — Email-based link**: `qb_unique_emails` → `customer_contacts` (capabilities, processes)
2. **Pass 2 — Direct QB link**: `qb_contacts.matched_contact_id` → contact stats (quotes count, last quote date)
3. **Pass 3 — Company inheritance**: Contacts inherit `qb_total_revenue`, `qb_tier`, `qb_customer_type` from parent company

### Path B — Contact-Specific (via `contact_persona` View)

- `total_job_value` = sum of `qb_jobs.retail_sale` for jobs linked to this contact's quotes
- `total_quote_value`, `strike_rate`, `accepted_quote_count` — all per-contact

### Where Correlation Is Used

| Location | What It Does |
|----------|-------------|
| `engagement_scorer.py` | Revenue weight = 15% of engagement score when QB data present |
| `recommendation_engine.py` | Revenue concentration risk — flags if ≤2 contacts drive >$100K |
| `am_efficiency_analyzer.py` | AM-level revenue attribution (company-level, not per-contact) |
| `customer_analytics_service.py` | Per-contact capability profile with revenue per capability |

---

## 5. UI Surfaces for Contact Intelligence

### Dedicated Pages

| Page | Route | What It Shows |
|------|-------|---------------|
| Contact Detail | `/customers/contacts/{id}` | Full persona card, engagement score, KPI strip (emails, initiation ratio, reply rate, response time), deal activity, threads, company context, AI insights |
| Contacts List | `/customers/contacts` | Paginated table with persona badge, engagement score, emails, quotes, strike %, job value, last contact |
| Response Times | `/manage/response-times` | Slowest responders table (per-contact), KPI strip with avg/median/business-hours response times |
| Comm Patterns | `/manage/patterns` | Three tabs: thread initiation (per-contact), frequency (emails/week/month), engagement trends (score + 30d change) |
| Dashboard | `/customers/analytics` | Top Engaged Contacts table, At-Risk Contacts table |

### Reusable Components

- `PersonaCard.tsx` — persona badge, engagement score bar, velocity, strike rate
- `EngagementTrendChart.tsx` — 30-day engagement score trend with factor breakdown

### Not Surfaced in UI Despite Existing in Backend

| Field / Feature | Backend Status | Frontend Status |
|----------------|----------------|-----------------|
| `is_decision_maker` flag | Column + scoring bonus | No badge, no filter |
| `seniority_level` | Column + scoring bonus | Not displayed |
| Per-contact engagement status badge | Available | Companies have it, contacts don't |
| Score component breakdown | `metric_history` has all factors | Single number only, no drill-down |
| Industry benchmarks vs individual | `industry_benchmarks` view exists | Not displayed |
| Contact comparison (side-by-side) | Data available | Not built |
| Contact-level data in Strategic Digest | Queryable | Only company + AM rollups shown |

---

## Summary Table

| Capability | Schema | Backend | Frontend | Status |
|------------|--------|---------|----------|--------|
| Persona classification (8 types) | SQL view (088, 101) | 3 endpoints | PersonaCard, contacts table | **Production** |
| Engagement score (0–100, 10-factor) | Persistent column + metric_history | engagement_scorer.py, Step 10.4 | Score display, trend chart, sorting | **Production** |
| Per-contact response time (bidirectional) | 2 columns + email_response_metrics | response_time_tracker.py, Step 11 | Response times page, slowest responders | **Production** |
| Contact-revenue correlation | Inherited (company) + direct (persona view) | engagement_scorer, recommendation_engine | Job value column, persona card | **Production** |
| Decision maker / seniority | Columns exist | Bonus in engagement score | **Not displayed** | Backend only |
| Contact-level score breakdown | metric_history has all factors | API available | **Not built** | Stubbed |
| Contact benchmarking vs industry | industry_benchmarks view exists | Queryable | **Not built** | Stubbed |
