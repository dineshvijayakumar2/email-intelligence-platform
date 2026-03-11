# Sprint 3 & 4 — Platform Surgery + Strategic Digest + Power Mode

## Context

The current platform analyzes emails in isolation — no contact history, no business context (revenue, orders, quotes), and no customer classification. The daily digest isn't useful for business owners. Critical feedback requires a **full overhaul** across three layers:

1. **Pipeline surgery** — Make the extraction pipeline QB-aware (customer type, revenue context)
2. **Analytics enrichment** — Add business context (revenue, quotes, tiers) to all existing analytics pages
3. **AI rethink** — Redesign all AI features around business context, not just email content
4. **Strategic digest** — New LangChain-powered digest combining email intelligence + QB business data
5. **Power Mode** — 7 radical features: Deal Radar, Ghost Writer, Heatmap, War Room, Alerts, Scoreboard, Executive Report

Additionally, cleanup critical bugs (duplicate endpoints) and dead code (superseded routers).

**Key decisions:**
- **Flexible period digest** — weekly, monthly, quarterly, YTD, custom date ranges
- **QB schema is developer-configured** per client via JSON field mappings
- **LangChain** as full AI backbone — hybrid chain + agent, free/open-source, no vectorization/RAG
- **AM Performance Comparison** — revenue, quote conversion, response time, retention
- **Budget:** up to $50/month (currently $16)
- **Initial processing: incremental** — 3 months first (~$7-8), backfill older months over time

---

## Quickbase Schema Summary (from `quickbase-integration/`)

The Quickbase app is a **B2B printing company CRM** with these core tables:

| Table | QB Table ID | Key Fields |
|-------|-------------|------------|
| **Customers** | buzhzbv39 | Name, Customer ID, CusTier, Account Manager, Active, MKTG: Customer Status?, Total Invoiced $, Invoiced $ TY/Y-1/Y-2, Recency, Cadence, 90d Growth, Days Since Last Invoice, Industry, # Line Items |
| **Contacts** | bu4ctqehy | Customer Contact ID, Customer ID, First/Surname, Email, Phone, Active, Contact Recency, # Quotes Accepted, Most Recent Quote Date, Customer AM |
| **Quotes** | buz9p6tzu | Quote No, Customer ID, Quote AM Name, Quote Sell ex Tax, Quote Date Created, Date Accepted, Job No (FK), Category, Quote Contact Email, Quantity, Kinds |
| **Jobs** | buziry2ri | Job No, Customer ID, Job Status, Job Retail Sale $, Invoiced Prod Margin, Margin%, Job Accepted/Due Date, Factory Rush Lvl, Pieces/Kinds/Qty Ordered |
| **Sales Line Items** | bu4cwdinf | Invoice Line ID, Invoice ID, Job No, Customer, Inv Date, Subtotal, Total, Product Group, Industry, Job AM Name |
| **Unique Emails** | bvmtc5re6 | email, Customer ID, Customer Name, Invoiced $ TY/L90d/L12M, Customer Recency, quality/result/role flags |

**Key relationships:** Customers → Contacts → Unique Emails; Customers → Quotes → Jobs → Sales Line Items

---

# SPRINT 3: Platform Surgery + QB + Strategic Digest (5 weeks)

## Part A: Platform Surgery

### A1. Critical Bug Fixes & Cleanup

**File: `backend/src/routers/analytics.py`**
- **DELETE duplicate extraction endpoints** (lines ~2564-2869) — 5 endpoints duplicated, will cause routing conflicts
- Keep the original set (lines ~67-274)

**Deprecate superseded routers:**
- `backend/src/routers/contacts.py` — superseded by `/v1/analytics/contacts` (richer, with engagement)
- Mark with `deprecated=True` in FastAPI or remove entirely
- `/api/customers/{id}/contacts` and `/api/customers/{id}/engagement` — superseded by analytics versions

### A2. Pipeline Surgery — QB-Aware Extraction

**Goal:** After Quickbase sync, the Sprint 2 extraction pipeline incorporates QB data during processing.

**Modify: `backend/src/services/extraction_orchestrator.py`**

Add 2 new steps to the 13-step pipeline (becomes 15 steps):

- **Step 4.5 (after Company Resolution): QB Company Matching**
  - After resolving a company from email domain, check `qb_customers` for a match (by `matched_company_id`)
  - If matched: pull `customer_type`, `customer_tier`, `account_manager`, `total_invoiced`, `days_since_last_invoice`, `recency_days`
  - Store on `customer_companies` as enrichment columns (new migration adds: `qb_customer_type`, `qb_tier`, `qb_total_revenue`, `qb_last_order_days`)
  - This makes QB context available to ALL downstream steps

- **Step 5.5 (after Contact Upsert): QB Contact Matching**
  - After upserting contacts, check `qb_contacts` for email match (by `matched_contact_id`)
  - If matched: pull `quotes_accepted_count`, `most_recent_quote_date`, `contact_recency_days`
  - Store on `customer_contacts` as enrichment columns (new: `qb_quotes_count`, `qb_last_quote_date`, `qb_contact_recency_days`)

**Modify: `backend/src/services/engagement_scorer.py`**

Add QB factors to the 8-factor engagement score:
- **Factor 9: Revenue weight** — customers with higher QB revenue get engagement boost
- **Factor 10: Order recency** — recent orders = active relationship indicator
- Adjust factor weights: email-based factors (70%), QB-based factors (30%)
- Update `SCORING_VERSION` from 1 → 2

**Modify: `backend/src/services/thread_tracker.py`**

- Tag threads with `customer_type` from QB (prospective/existing/new) — helps prioritize thread urgency
- Prospective customer threads with `awaiting_response` status → higher priority

### A3. Analytics Enrichment — QB Business Context

**Goal:** Every analytics page shows QB business context alongside email analytics.

**Modify: `backend/src/routers/analytics.py`** — Enrich existing endpoints:

**Contact endpoints:**
- `GET /analytics/contacts` — add columns: `qb_customer_type`, `qb_tier`, `qb_quotes_count`, `qb_last_quote_date`
- `GET /analytics/contacts/{id}` — add QB section: recent quotes, order history, customer type
- `GET /analytics/contacts/at-risk` — add `qb_total_revenue` (high-revenue at-risk contacts are critical)

**Company endpoints:**
- `GET /analytics/companies` — add columns: `qb_tier`, `qb_total_revenue`, `qb_invoiced_ty`, `qb_growth_90d`, `qb_customer_status`
- `GET /analytics/companies/{id}` — add QB section: revenue breakdown (TY/LY/L90d), open quotes, active jobs, AM assignment
- `GET /analytics/companies/at-risk` — add `qb_total_revenue`, `qb_days_since_last_invoice`

**Dashboard endpoint:**
- `GET /analytics/dashboard` — add revenue summary: total portfolio value, top revenue customers, revenue at risk

**Thread endpoints:**
- `GET /analytics/threads/status` — add `customer_type`, `qb_tier` columns
- `GET /analytics/threads/overdue` — sort by QB revenue impact

**New endpoint:**
- `GET /analytics/am-summary/{client_id}` — AM-level view: customer count, total revenue, response time, at-risk count

**Frontend changes (modify existing pages):**

| Page | File | Changes |
|------|------|---------|
| Contacts list | `contacts.tsx` | Add Tier, Revenue, Customer Type columns. Color-code by tier. |
| Contact detail | `contact-detail.tsx` | Add QB section: quotes, orders, customer type badge, revenue card |
| Companies list | `companies.tsx` | Add Revenue TY, Growth %, Tier columns. Sort by revenue. |
| Company detail | `company-detail.tsx` | Add QB revenue card, quotes table, jobs table, AM info |
| Dashboard | `dashboard.tsx` | Add revenue KPI cards, revenue-at-risk metric |
| Threads | `threads.tsx` | Add Customer Type, Tier columns. Priority sort by revenue impact. |

### A4. AI Full Rethink

**Goal:** All AI features use business context (QB data + contact history + thread context), not just raw email content.

#### A4a. Email Analyzer Overhaul

**Modify: `backend/src/services/ai_email_analyzer.py`**

Current per-email context sent to Haiku:
```
email_id, subject, sender, body (300 chars), sender_context (company, title, seniority), pre_classification
```

**Enhanced context (add QB + relationship data):**
```
+ customer_type: "existing" / "prospective" / "new"
+ customer_tier: "A" / "B" / "C"
+ total_revenue: "$125,000 (TY: $45,000, LY: $52,000 — declining)"
+ days_since_last_order: 45
+ open_quotes: 2 (total $12,500)
+ engagement_trend: "declining (score dropped from 72 to 54 in 90d)"
+ thread_context: "3rd email in thread about 'Reprint of Q4 catalog' — we haven't replied in 5 days"
+ contact_history: "12 emails in last 90d, usually replies within 4 hours"
```

Cost: ~50 additional tokens per email — negligible.

**Rethink prompt to be business-outcome-focused:**
- "This is a **$125K existing customer** whose revenue is declining. They have 2 open quotes. Classify this email with that context."
- vs current: "Classify this email's intent, urgency, sentiment" (context-free)

#### A4b. Action Buckets Rethink

**Modify: `backend/src/services/ai_action_bucket_engine.py`**

| Current Bucket | Problem | Proposed Change |
|---------------|---------|----------------|
| `buying_signal` | Detects keywords only | **Enhance:** Weight by customer type (prospective >> existing) |
| `expansion_signal` | Generic | **Enhance:** Cross-reference with QB quote history |
| `churn_risk` | Only explicit exit intent | **Enhance:** Add "revenue declining + email silence + no recent orders" |
| `competitor_threat` | Keyword-only | **Keep** as-is |
| `missed_opportunity` | No outbound response | **Enhance:** Weight by QB revenue |
| `stakeholder_entry` | Senior contact, low engagement | **Keep** as-is |
| `silent_champion` | Contact going quiet | **Enhance:** Add QB order recency |
| `unresolved_block` | Overdue threads | **Enhance:** Add QB customer tier |

**Add 2 new buckets:**
- `revenue_at_risk` — existing customer with declining QB revenue + declining email engagement + no recent quotes
- `hot_prospect` — prospective customer with buying signals + active quote + positive sentiment

#### A4c. Entity Aggregator Enhancement

**Modify: `backend/src/services/ai_entity_aggregator.py`**
- Cross-reference extracted competitors with QB product groups
- Cross-reference extracted people with QB contacts (known vs new stakeholder)

#### A4d. Existing Digest QB Enrichment

**Modify: `backend/src/services/ai_digest_generator.py`**
- Add QB revenue context to top signal emails ("Email from $125K customer — revenue declining 15% YoY")
- Add QB quote context to action items ("Follow up on Quote #1234, $5,000, 30 days old")

### A5. Database Migration for Surgery

**File: `scripts/sprint3/sprint3_migration_021a_platform_surgery.sql`**

```sql
-- Add QB context to customer_companies
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS qb_customer_type TEXT;
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS qb_tier TEXT;
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS qb_total_revenue DECIMAL(12,2);
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS qb_invoiced_ty DECIMAL(12,2);
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS qb_invoiced_ly DECIMAL(12,2);
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS qb_growth_90d DECIMAL(5,2);
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS qb_days_since_last_invoice INTEGER;
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS qb_account_manager TEXT;

-- Add QB context to customer_contacts
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS qb_quotes_count INTEGER DEFAULT 0;
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS qb_last_quote_date DATE;
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS qb_contact_recency_days INTEGER;

-- Add customer_type to thread_status for priority sorting
ALTER TABLE thread_status ADD COLUMN IF NOT EXISTS qb_customer_type TEXT;
ALTER TABLE thread_status ADD COLUMN IF NOT EXISTS qb_customer_tier TEXT;
```

---

## Part B: Quickbase Integration + Strategic Digest

### B1. Database Migration (Migration 021)

**File:** `scripts/sprint3/sprint3_migration_021_strategic_digest.sql`

#### New Tables

**1. `qb_sync_config`** — Per-client Quickbase connection settings (developer-configured)
- `client_id` (FK, UNIQUE), `realm_hostname`, `app_id`, `user_token_encrypted`
- Table IDs: `customers_table_id`, `contacts_table_id`, `quotes_table_id`, `jobs_table_id`, `sales_line_items_table_id`
- `field_mappings` JSONB — maps QB field IDs to column names per table:
  ```json
  {
    "customers": {"7": "customer_name", "16": "account_manager", "894": "customer_tier", ...},
    "quotes": {"6": "quote_id", "12": "sell_ex_tax", "13": "date_created", ...}
  }
  ```
  Default template based on Carbon8 schema; override per client.
- `sync_interval_hours` (default 6), `last_sync_at`, `is_active`

**2. `qb_customers`** — Cached QB Customers
- `qb_record_id`, `client_id`, `customer_name`, `customer_code`, `customer_tier`
- `customer_status` (prospective/existing/new/inactive), `account_manager`, `industry`, `active`
- Financial: `total_invoiced`, `invoiced_ty`, `invoiced_ly`, `invoiced_l90d`, `invoiced_l12m`
- Health: `recency_days`, `cadence_score`, `growth_90d`, `days_since_last_invoice`
- `matched_company_id` FK → `customer_companies`, `synced_at`

**3. `qb_contacts`** — Cached QB Contacts
- `qb_record_id`, `client_id`, `qb_customer_id`, `first_name`, `surname`, `email`, `phone`, `active`
- `contact_recency_days`, `quotes_accepted_count`, `most_recent_quote_date`
- `matched_contact_id` FK → `customer_contacts`, `synced_at`

**4. `qb_quotes`** — Cached QB Quotes
- `qb_record_id`, `client_id`, `qb_customer_id`, `quote_no`, `quote_am_name`, `sell_ex_tax`
- `date_created`, `date_accepted`, `category`, `contact_email`, `contact_name`
- `job_no`, `has_job`, `quantity`, `kinds`, `total_quantity`
- `matched_company_id` FK → `customer_companies`, `synced_at`

**5. `qb_jobs`** — Cached QB Jobs
- `qb_record_id`, `client_id`, `qb_customer_id`, `job_no`, `quote_no`, `job_status`
- `retail_sale`, `invoiced_margin`, `margin_pct`, `accepted_date`, `due_date`, `factory_rush_level`
- `pieces_ordered`, `kinds_ordered`, `total_qty_ordered`
- `matched_company_id` FK → `customer_companies`, `synced_at`

**6. `qb_sales_line_items`** — Cached QB Sales (invoiced revenue)
- `qb_record_id`, `client_id`, `qb_customer_id`, `invoice_id`, `invoice_no`, `job_no`, `job_am_name`
- `customer_name`, `inv_date`, `subtotal`, `total`, `product_group`, `industry`, `job_title`
- `matched_company_id` FK → `customer_companies`, `synced_at`

**7. `relationship_context_cache`** — Pre-computed relationship summaries
- `client_id`, `company_id` (FK, UNIQUE together)
- `customer_type`, `customer_tier`, `account_manager`
- `engagement_trajectory` TEXT, `engagement_scores_history` JSONB
- `communication_health` JSONB, `key_contacts` JSONB
- `active_threads_summary` JSONB, `ai_signals_summary` JSONB, `qb_financial_summary` JSONB
- `computed_at` TIMESTAMPTZ

**8. `ai_strategic_digests`** — Strategic digest output (flexible periods)
- `client_id`, `digest_date`, `period_type` CHECK IN ('weekly','monthly','quarterly','ytd','custom')
- `period_start`, `period_end`, `comparison_period_start`, `comparison_period_end`
- Sections (JSONB): `executive_summary`, `relationship_health`, `pipeline_intelligence`, `risk_alerts`, `opportunities`, `competitive_landscape`, `am_performance`, `action_items`
- AI metadata: `model_used`, `total_input_tokens`, `total_output_tokens`, `total_cost_usd`, `chain_steps_completed`, `raw_ai_responses`
- UNIQUE(`client_id`, `digest_date`, `period_type`)

**9. `am_performance_snapshots`** — AM performance per period (computed, not AI)
- `client_id`, `account_manager`, `period_start`, `period_end`
- Revenue: `total_revenue`, `revenue_change_pct`, `customer_count`, `avg_revenue_per_customer`
- Quotes: `quotes_sent`, `quotes_accepted`, `quote_conversion_rate`, `avg_quote_value`
- Communication: `avg_response_time_hours`, `avg_bh_response_time_hours`, `emails_sent`, `emails_received`
- Retention: `active_customers`, `churned_customers`, `new_customers`, `retention_rate`
- UNIQUE(`client_id`, `account_manager`, `period_start`, `period_end`)

### B2. Quickbase Integration Layer

**`backend/src/services/quickbase_client.py`** — Low-level QB API client
- Uses `httpx` for HTTP calls, QB-Realm-Hostname header + User-Token auth
- Methods: `query_records()`, `get_fields()` | Pagination: max 1000/request, cursor-based
- Field ID → label mapping via configurable dict from `qb_sync_config.field_mappings`

**`backend/src/services/quickbase_sync.py`** — Sync orchestrator
- `sync_all(client_id)` → `sync_customers` → `sync_contacts` → `sync_quotes` → `sync_jobs` → `sync_sales_line_items`
- `match_to_companies(client_id)` — match by name (normalized lowercase, then fuzzy)
- `match_to_contacts(client_id)` — match by email address
- Follows existing patterns: `_execute_with_retry()`, batch upserts (100/batch)

**`backend/src/routers/quickbase.py`** — API endpoints
- `GET /v1/quickbase/config` | `PUT /v1/quickbase/config` | `POST /v1/quickbase/sync`
- `GET /v1/quickbase/sync-status` | `GET /v1/quickbase/customers` | `GET /v1/quickbase/match-preview`

### B3. Enhanced Context Builder

**`backend/src/services/strategic_context_builder.py`**

- `build_company_context(client_id, company_id, lookback_months=6)` — engagement trajectory, communication health, thread context, AI signals, QB enrichment, key contacts
- `build_all_contexts(client_id)` — iterate all companies, cache in `relationship_context_cache`. **Cost: $0**
- `build_am_performance(client_id, period_start, period_end, comparison_start, comparison_end)` — revenue metrics, quote conversion, response time, retention. **Cost: $0**
- `get_contexts_for_digest(client_id, top_n=20)` — prioritize by engagement + revenue + signal count

### B4. LangChain Pipeline

**Dependencies:** `langchain>=0.3.0`, `langchain-anthropic>=0.3.0`

**`backend/src/services/langchain_core.py`** — Shared AI backbone
- `ChatAnthropic` wrapper with budget tracking (integrates with `ai_usage_tracker.py`)
- Shared tool registry, context builder integration, token budget management

**`backend/src/services/strategic_digest_pipeline.py`** — Hybrid: LCEL Chain + Agent

Step 1 — Data Gathering Chain ($0): fetch company contexts, email stats, QB pipeline, competitive signals
Step 2 — Context Compilation Chain ($0): format, truncate to ~15K tokens
Step 3 — Strategic Analysis Agent (~$0.13/digest): Claude Sonnet with tools for deeper investigation

**`backend/src/services/langchain_tools.py`** — Agent tools
- `lookup_company_detail`, `lookup_contact_history`, `lookup_thread_messages`, `lookup_quote_detail`

**`backend/src/services/ai_insights_engine.py`** — Per-page AI insights
- `GET /v1/ai/insights/company/{company_id}` | `/contact/{contact_id}` | `/thread/{thread_id}`
- Cached in `ai_insights_cache` (TTL: 24h). Cost: ~$0.02/query

**Cost:** ~$0.13/digest, ~$0.52/month per client. Total ~$18-20/month with existing pipeline.

### B5. API Endpoints

**Modify: `backend/src/routers/ai.py`** — New endpoints:
- `GET /v1/ai/strategic-digest/{client_id}` — get/generate digest (period_type, date params)
- `POST /v1/ai/strategic-digest/{client_id}/generate` — force generate (BackgroundTasks)
- `GET /v1/ai/strategic-digest/{client_id}/history` — past digests
- `GET /v1/ai/am-performance/{client_id}` — AM scorecard

**Modify:** `ai_client.py` (budget $16→$50), `models/ai.py` (strategic digest models)

### B6. Frontend

**New pages:**
- `frontend/src/pages/intelligence/strategic-digest.tsx` — Period selector, 8 sections (Executive Summary, AM Performance, Relationship Health, Pipeline Intelligence, Risk Alerts, Opportunities, Competitive Landscape, Action Items)
- `frontend/src/pages/settings/quickbase.tsx` — Connection form, field mapping, test/sync

**New components:** `AIInsightsCard.tsx` — reusable "AI Insights" button on every detail page

---

# SPRINT 4: Power Mode (3 weeks)

### Migration 022 (`scripts/sprint4/sprint4_migration_022_power_mode.sql`)

New tables: `ai_deal_tracker`, `ai_suggested_replies`, `user_alert_preferences`, `user_alerts`, `am_weekly_scores`, `ai_insights_cache`

### C1. Deal Radar — Predictive Revenue Intelligence

**`backend/src/services/deal_radar.py`** — $0 cost (pure Python)
- Computes `deal_probability` (0-100%) per thread from existing AI classifications + QB data
- Positive signals: pricing (+15), procurement CC'd (+20), contract request (+25), manager loop-in (+10), budget (+15), multi-stakeholder (+10)
- Negative signals: competitor (+) (-10), "deprioritized" (-15), silence >14d (-10), "go with another" (-20)
- QB boost: active quote (+10), recent orders (+5), high-tier (+5)
- Trajectory: 7-day rolling average → UP/DOWN/FLAT

**Endpoint:** `GET /v1/ai/deal-radar/{client_id}` — likely to close, at risk, new opportunities, pipeline value

**Frontend:** `/intelligence/deal-radar` — pipeline cards, 3 sections, deal cards with trajectory arrows

### C2. Ghost Writer — AI Reply Suggestions

**`backend/src/services/ai_reply_generator.py`** — $1.80/month
- On-demand via LangChain: thread context + classification + QB context → 3 reply options (Quick/Thorough/Escalate)
- Uses Haiku (~$0.002/reply), cached 24h in `ai_suggested_replies`

**Endpoint:** `GET /v1/ai/replies/{email_id}`
**Frontend:** "Suggested Replies" section in Smart Inbox detail drawer with Copy button

### C3. Relationship Heatmap — Visual Account Health

**Frontend-only: `/analytics/heatmap`** — $0 cost
- CSS grid/D3.js treemap: color = engagement score (green/yellow/red), size = QB revenue
- Hover tooltip, click → company detail, filter by AM

### C4. War Room — Competitive Intelligence Dashboard

**Frontend: `/intelligence/war-room`** — $0 cost
- Top Competitors bar chart with trends, Active Battles with deal values, Win/Loss correlation
- Uses existing `entityApi.getCompetitors()` + new aggregation endpoint

**Endpoint:** `GET /v1/ai/war-room/{client_id}`

### C5. Executive Briefing — PDF Report

**`backend/src/services/executive_report.py`** — $1/month
- PDF from strategic digest + deal radar + heatmap + AM performance
- Uses `reportlab` or `weasyprint`, LangChain for narrative (~$0.05/report)

**Endpoint:** `POST /v1/ai/executive-report/{client_id}`
**Frontend:** "Generate Report" button on strategic digest + dashboard

### C6. Smart Alerts — Push Notifications

**`backend/src/services/alert_engine.py`** — $0 cost
- Triggers: churn risk (>$50K), buying signal (prospect), competitor (top 10), missed opportunity (>24h), deal drop (>15pts)
- Phase 1: in-app (notification bell) | Phase 2: browser push | Phase 3: email/Slack

**Frontend:** NotificationBell component in header, alert preferences in settings

### C7. AM Scoreboard — Gamified Performance

**`backend/src/services/am_scoreboard.py`** — $0 cost
- Scoring: fast response (+10), SLA compliance (+5/day), signal acted on (+15), positive sentiment (+10), missed opportunity (-25), new customer (+50), retained (+20)

**Endpoint:** `GET /v1/ai/scoreboard/{client_id}?period=weekly`
**Frontend:** Leaderboard on dashboard + `/intelligence/scoreboard` page

---

## Incremental Backfill Strategy

**Day 1:** Process last 3 months (~25K emails) — ~$7-8. Set daily budget to $10 temporarily.

**Background:** Backfill older months at ~$2-3/month within daily budget.
- Priority: most recent first (month 4, 5, 6, then 7-12)
- 6-month complete in ~2-3 weeks; full year in ~6-8 weeks
- QB data: sync all immediately ($0, REST API)

---

## Implementation Order

### Sprint 3 (5 weeks)

**Migration 021a** (`scripts/sprint3/sprint3_migration_021a_platform_surgery.sql`):
QB enrichment columns on `customer_companies`, `customer_contacts`, `thread_status`

**Migration 021** (`scripts/sprint3/sprint3_migration_021_strategic_digest.sql`):
QB cache tables + strategic digest tables + AM performance snapshots

```
Week 1-2: Surgery + QB Foundation
  S3.1  Fix duplicate extraction endpoints in analytics.py       [1 hour]
  S3.2  Run migrations 021a + 021                                 [1 hour]
  S3.3  quickbase_client.py + quickbase_sync.py                   [1 day]
  S3.4  quickbase.py router                                       [0.5 day]
  S3.5  Test QB sync + company/contact matching                   [0.5 day]
  S3.6  Pipeline surgery — QB-aware extraction steps              [1 day]
  S3.7  Engagement scorer v2 — QB factors                         [0.5 day]

Week 2-3: Analytics + AI Enhancement
  S3.8  Analytics enrichment — QB fields on all endpoints         [1 day]
  S3.9  Frontend analytics — QB columns on existing pages         [1 day]
  S3.10 AI analyzer overhaul — QB-enriched prompts                [1 day]
  S3.11 Action buckets rethink + 2 new buckets                    [0.5 day]
  S3.12 Entity aggregator + existing digest QB enrichment         [0.5 day]

Week 4-5: LangChain + Strategic Digest
  S3.13 LangChain core infrastructure (langchain_core.py)         [0.5 day]
  S3.14 strategic_context_builder.py + AM performance             [1 day]
  S3.15 strategic_digest_pipeline.py + langchain_tools.py         [1 day]
  S3.16 AI insights engine (per-page insights)                    [1 day]
  S3.17 Strategic digest + insights API endpoints                 [0.5 day]
  S3.18 Frontend: strategic digest page + QB settings             [1.5 days]
  S3.19 Frontend: "AI Insights" buttons on detail pages           [0.5 day]
  S3.20 Integration testing + budget update ($16→$50)             [0.5 day]
```

### Sprint 4 (3 weeks)

**Migration 022** (`scripts/sprint4/sprint4_migration_022_power_mode.sql`):
`ai_deal_tracker`, `ai_suggested_replies`, `user_alert_preferences`, `user_alerts`, `am_weekly_scores`, `ai_insights_cache`

```
Week 1: Deal Radar + Ghost Writer
  S4.1  Run migration 022                                         [0.5 hour]
  S4.2  deal_radar.py — deal probability engine                   [1 day]
  S4.3  Deal Radar API endpoint + frontend page                   [1 day]
  S4.4  ai_reply_generator.py — Ghost Writer service              [0.5 day]
  S4.5  Ghost Writer frontend (inbox drawer section)              [0.5 day]

Week 2: Heatmap + War Room + Alerts
  S4.6  Relationship Heatmap frontend page ($0, no backend)       [0.5 day]
  S4.7  War Room API endpoint + frontend page                     [1 day]
  S4.8  alert_engine.py — Smart Alerts service                    [0.5 day]
  S4.9  Alert preferences API + notification bell frontend        [1 day]

Week 3: Scoreboard + Executive Report + Polish
  S4.10 am_scoreboard.py — scoring engine                         [0.5 day]
  S4.11 Scoreboard API + frontend (leaderboard + dashboard)       [0.5 day]
  S4.12 executive_report.py — PDF generation                      [1 day]
  S4.13 Executive Report endpoint + "Generate Report" button      [0.5 day]
  S4.14 Integration testing all power features                    [0.5 day]
  S4.15 Production deployment                                     [0.5 day]
```

**Dependencies:** Sprint 3 must complete before Sprint 4. Within Sprint 4, S4.1 must run first.

---

## Cost Summary

| Component | Monthly Cost |
|-----------|-------------|
| Existing email analysis (Haiku) | ~$8-12 |
| Existing daily/weekly digests (Sonnet) | ~$3-4 |
| Strategic digest (Sonnet) | ~$2-5 |
| Per-page AI insights (Haiku) | ~$1-3 |
| Ghost Writer replies (Haiku) | ~$1.80 |
| Executive reports (Sonnet) | ~$1 |
| Deal Radar / Heatmap / War Room / Alerts / Scoreboard | $0 |
| Quickbase sync | $0 |
| **Total estimated** | **~$17-27/month** |

Well within the $50/month budget.

---

## Key Files Reference

### Existing files to modify (Sprint 3 surgery):
- `backend/src/routers/analytics.py` — DELETE duplicates + enrich with QB
- `backend/src/services/ai_email_analyzer.py` — QB-enriched prompts
- `backend/src/services/ai_action_bucket_engine.py` — rethink + 2 new buckets
- `backend/src/services/ai_entity_aggregator.py` — QB cross-reference
- `backend/src/services/ai_digest_generator.py` — QB context enrichment
- `backend/src/services/ai_client.py` — budget $16→$50
- `backend/src/services/extraction_orchestrator.py` — QB-aware pipeline steps
- `backend/src/services/engagement_scorer.py` — QB factors, SCORING_VERSION 2
- `backend/src/services/thread_tracker.py` — customer_type/tier
- `backend/src/models/analytics.py` — extend with QB fields
- `backend/src/routers/ai.py` — strategic digest + insights endpoints
- `backend/main.py` — register quickbase router
- `frontend/src/pages/analytics/*.tsx` — QB columns on all analytics pages
- `frontend/src/types/analytics.ts` — extend interfaces

### New files — Sprint 3:
- `scripts/sprint3/sprint3_migration_021a_platform_surgery.sql`
- `scripts/sprint3/sprint3_migration_021_strategic_digest.sql`
- `backend/src/services/quickbase_client.py`
- `backend/src/services/quickbase_sync.py`
- `backend/src/services/strategic_context_builder.py`
- `backend/src/services/strategic_digest_pipeline.py`
- `backend/src/services/langchain_core.py`
- `backend/src/services/langchain_tools.py`
- `backend/src/services/ai_insights_engine.py`
- `backend/src/routers/quickbase.py`
- `backend/src/models/quickbase.py`
- `frontend/src/types/strategic-digest.ts`
- `frontend/src/services/strategicDigestService.ts`
- `frontend/src/pages/intelligence/strategic-digest.tsx`
- `frontend/src/pages/settings/quickbase.tsx`

### New files — Sprint 4:
- `scripts/sprint4/sprint4_migration_022_power_mode.sql`
- `backend/src/services/deal_radar.py`
- `backend/src/services/ai_reply_generator.py`
- `backend/src/services/alert_engine.py`
- `backend/src/services/am_scoreboard.py`
- `backend/src/services/executive_report.py`
- `frontend/src/pages/intelligence/deal-radar.tsx`
- `frontend/src/pages/intelligence/war-room.tsx`
- `frontend/src/pages/intelligence/scoreboard.tsx`
- `frontend/src/pages/analytics/heatmap.tsx`
- `frontend/src/components/NotificationBell.tsx`
- `frontend/src/components/AIInsightsCard.tsx`
