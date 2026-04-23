# Insight Engine Audit

> Generated 2026-04-22. Read-only audit — no code was modified.

This document audits four areas of the platform's intelligence/insight layer
to establish a baseline before planning new features.

---

## Table of Contents

1. [Cross-Gap Analysis & Recommendations](#1-cross-gap-analysis--recommendations)
2. [LLM Prompt Templates](#2-llm-prompt-templates)
3. [Seasonality Engine](#3-seasonality-engine)
4. [Reorder Cycles & Reactivation Windows](#4-reorder-cycles--reactivation-windows)

---

## 1. Cross-Gap Analysis & Recommendations

### DB Layer

| Migration | Purpose | Key Objects | Status | Last Modified |
|-----------|---------|-------------|--------|---------------|
| `032_qb_operations.sql` | QB operations table — granular operation detail per job, powers recommendation engine | `qb_operations` | Active | 2026-03-23 |
| `034_product_intelligence.sql` | Recommendation cache + market basket co-occurrence | `customer_recommendations`, `product_affinities` | Active | 2026-03-19 |
| `035_intelligence_config.sql` | Taxonomy config + intelligence cache; capability_tags/rush flags on qb_operations | `client_taxonomy_config`, `customer_intelligence_cache` | Active | 2026-03-23 |
| `062_thread_intent_status.sql` | Thread `intent_status` column including `revenue_opportunity` | Column on `thread_status` | Active | — |
| `077–080_thread_override_rules.sql` | Revenue-opportunity override rules (quote requests, buying signals, pricing signals) | `thread_status_override_rules` | Active | — |

**Key tables:** `customer_recommendations` (24h JSONB cache), `product_affinities` (co-occurrence), `customer_intelligence_cache` (generic), `client_taxonomy_config` (rules), `qb_operations` (source data).

### API Layer

| File | Purpose | Status | Last Modified |
|------|---------|--------|---------------|
| `backend/src/services/recommendation_engine.py` | **Core engine** — Level 1: cross-contact gaps (contacts missing operations). Level 2: market basket product affinities. Pure Python, $0 AI cost, 24h cache. | Active | 2026-04-06 |
| `backend/src/services/capability_classifier.py` | Maps QB operations → 8 capability tags + rush flags; config-driven rules from `client_taxonomy_config` | Active | 2026-03-25 |
| `backend/src/services/customer_analytics_service.py` | Strike rate, contact capabilities, seasonality — cached in `customer_intelligence_cache` | Active | — |
| `backend/src/services/ai_entity_aggregator.py` | `get_opportunity_signals()` — emails with high buying intent/budget/expansion signals | Active | 2026-03-13 |
| `backend/src/routers/customers.py` | `GET /{company_id}/recommendations` and `GET /{company_id}/product-profile` | Active | 2026-04-08 |
| `backend/src/routers/intelligence_config.py` | CRUD for capability tags, classifier rules, rush settings, cache management | Active | 2026-03-25 |
| `backend/src/routers/ai.py` | `GET /ai/entities/{client_id}/opportunities` — opportunity signals from email intelligence | Active | — |
| `backend/src/models/ai.py` | `OpportunitySignal`, `OpportunitySignalsResponse` Pydantic schemas | Active | 2026-03-17 |

### Frontend Layer

| File | Purpose | Status | Last Modified |
|------|---------|--------|---------------|
| `frontend/src/components/RecommendationsPanel.tsx` | Cross-contact gaps + product opportunities with confidence scores; collapsible detail | Active | 2026-04-08 |
| `frontend/src/components/ProductProfileCard.tsx` | Revenue by category, operations by department, capability tags | Active | 2026-04-06 |
| `frontend/src/components/ContactCapabilitiesCard.tsx` | Contact-level capability/operation matrix | Active | 2026-04-08 |
| `frontend/src/pages/intelligence/opportunities.tsx` | 4-tab dashboard: Action Items, Opportunities, Competitors, Entities at `/insights/opportunities` | Active | 2026-04-08 |
| `frontend/src/pages/analytics/company-detail.tsx` | Hosts RecommendationsPanel in "Sales Opportunities" section | Active | — |
| `frontend/src/services/analyticsService.ts` | `companiesApi.getRecommendations(companyId)` API client | Active | 2026-04-22 |

### Architecture Summary

- **Two-tier recommendation system:** cross-contact gaps (Level 1) + market basket affinity (Level 2)
- Both tiers are pure Python with $0 AI cost
- Opportunity signals are a separate AI-powered path via email intelligence (entity aggregator)
- Cache: 24h TTL in `customer_recommendations`, 5-min for prompts
- No standalone "gap analysis" page — recommendations embedded in company detail; opportunity signals at `/insights/opportunities`
- No deprecated or TODO-only gap analysis code found; everything is active

---

## 2. LLM Prompt Templates

### 2.1 Prompt Inventory (9 templates)

#### 1. Email Analysis — System (`email_analysis_system`)

| Attribute | Value |
|-----------|-------|
| **File** | `backend/src/services/ai_email_analyzer.py` lines 101–167 |
| **Variable** | `SYSTEM_PROMPT` |
| **Generates** | Per-email structured classification (intent, urgency, sentiment, entities, signals) |
| **Inputs** | None (system prompt — sets behavior rules) |
| **Output** | Strict JSON array (one object per email in batch) |
| **Caller** | Background email processing pipeline → `process_emails()` |
| **Status** | Active |

#### 2. Email Analysis — User Template (`email_analysis_user`)

| Attribute | Value |
|-----------|-------|
| **File** | `backend/src/services/ai_email_analyzer.py` lines 169–226 |
| **Variable** | `USER_PROMPT_TEMPLATE` |
| **Generates** | Batch classification for up to 20 emails |
| **Inputs** | `{emails_json}` — serialized email batch (subject, body, sender, direction, folder) |
| **Output** | JSON array: `{email_id, intent, urgency, sentiment, sentiment_score, action_type, business_signal, entities, ...}` |
| **Caller** | Same pipeline as above |
| **Status** | Active |

#### 3. Daily Digest — System (`daily_digest`)

| Attribute | Value |
|-----------|-------|
| **File** | `backend/src/services/ai_digest_generator.py` lines 38–95 |
| **Variable** | `DIGEST_SYSTEM_PROMPT` + `DIGEST_USER_TEMPLATE` |
| **Generates** | Daily intelligence briefing — cross-email patterns, timing anomalies, relationship dynamics |
| **Inputs** | Bucket summary, active threads with snippets, email metadata |
| **Output** | Strict JSON: `{summary, key_insights[], action_items[], highlights[]}` |
| **Caller** | `POST /api/v1/ai/digest/{mailbox_id}` — on-demand from frontend dashboard |
| **Status** | Active |

#### 4. Weekly Digest — System (`weekly_digest`)

| Attribute | Value |
|-----------|-------|
| **File** | `backend/src/services/ai_digest_generator.py` lines 97–167 |
| **Variable** | `WEEKLY_DIGEST_SYSTEM_PROMPT` + `WEEKLY_DIGEST_USER_TEMPLATE` |
| **Generates** | Weekly strategic review — trend analysis, pipeline momentum, AM workload, opportunity clusters |
| **Inputs** | Week's bucket summary, active threads, email metadata, QB data |
| **Output** | Strict JSON: `{executive_summary, trends[], pipeline_status, am_performance[], opportunities[], risks[]}` |
| **Caller** | Same endpoint with `digest_type="weekly"` |
| **Status** | Active |

#### 5. Strategic Digest — System (`strategic_digest`)

| Attribute | Value |
|-----------|-------|
| **File** | `backend/src/services/strategic_digest_pipeline.py` lines 57–165 |
| **Variable** | `STRATEGIC_DIGEST_SYSTEM_PROMPT` |
| **Generates** | AM efficiency analysis — response urgency, retention risk, deal risk, revenue opportunities |
| **Inputs** | LangGraph agent with tool access to portfolio, emails, contacts, QB data |
| **Output** | Structured strategic digest with prioritized action items |
| **Caller** | LangGraph ReAct agent pipeline |
| **Status** | Active |

#### 6. Company Insight (`insight_company`)

| Attribute | Value |
|-----------|-------|
| **File** | `backend/src/services/ai_insights_engine.py` lines 30–41 |
| **Variable** | `COMPANY_INSIGHT_PROMPT` |
| **Generates** | Relationship health assessment for a company |
| **Inputs** | Company profile, QB data (quotes/jobs/revenue), email history, thread status |
| **Output** | JSON: `{health_summary, revenue_risk, key_observations[], recommended_actions[], engagement_trend}` |
| **Caller** | `GET /api/v1/ai/insights/company/{id}` — "Analyze" button on company detail |
| **Status** | Active |

#### 7. Contact Insight (`insight_contact`)

| Attribute | Value |
|-----------|-------|
| **File** | `backend/src/services/ai_insights_engine.py` lines 43–54 |
| **Variable** | `CONTACT_INSIGHT_PROMPT` |
| **Generates** | Contact engagement and importance assessment |
| **Inputs** | Contact profile, email patterns, business data |
| **Output** | JSON: `{engagement_summary, importance_level, key_observations[], follow_up_suggestion, engagement_trend}` |
| **Caller** | `GET /api/v1/ai/insights/contact/{id}` |
| **Status** | Active |

#### 8. Thread Insight (`insight_thread`)

| Attribute | Value |
|-----------|-------|
| **File** | `backend/src/services/ai_insights_engine.py` lines 56–67 |
| **Variable** | `THREAD_INSIGHT_PROMPT` |
| **Generates** | Deal probability and risk assessment for an email thread |
| **Inputs** | Thread messages, participants, QB quote linkage |
| **Output** | JSON: `{thread_summary, deal_probability (0-100|null), risk_level, key_signals[], recommended_action}` |
| **Caller** | `GET /api/v1/ai/insights/thread/{id}` |
| **Status** | Active |

#### 9. Agent Chat (`agent_chat`)

| Attribute | Value |
|-----------|-------|
| **File** | `backend/src/services/ai_agent_service.py` lines 44–81 |
| **Variable** | `AGENT_SYSTEM_PROMPT` |
| **Generates** | Conversational intelligence responses with 12 tools |
| **Inputs** | User message + conversation history; agent has tool access to DB |
| **Output** | Plain text (conversational), with structured tool calls internally |
| **Caller** | `POST /api/v1/ai/agent/chat[/stream]` — Chat widget |
| **Status** | Active |
| **Tools** | portfolio_summary, account_ranking, search_emails, semantic_search_emails, search_contacts, lookup_company_detail, company_analytics, lookup_contact_history, lookup_thread_messages, lookup_quote_detail, thread_overview, semantic_search_operations |

### 2.2 Prompt Infrastructure

#### Database Table: `ai_prompt_config` (migration 027)

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | Auto-generated |
| `client_id` | UUID FK (nullable) | NULL = global default |
| `prompt_key` | TEXT | Unique per client |
| `prompt_text` | TEXT | The prompt content |
| `description` | TEXT | Human-readable label |
| `is_active` | BOOLEAN | Default TRUE |
| `version` | TEXT | Content hash, default 'v1.0' |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

**Indexes:** `idx_prompt_config_global` (unique on prompt_key WHERE client_id IS NULL), `idx_prompt_config_client` (client_id + prompt_key WHERE is_active).

**Resolution order:** client-specific → global default → auto-seed from hardcoded constant.

**Loader:** `backend/src/services/ai_prompt_loader.py` — 5-minute in-memory cache, auto-seeds on first use.

**No separate `prompt_versions` table** — versioning is a single `version` TEXT column (content hash).

### 2.3 Stored Prompt Records (Live DB Query)

**Clients:**
| Client ID (prefix) | Name |
|---------------------|------|
| `2131bdd7` | Newbound |
| `563371a5` | Impressive Wardrobes |
| `241d7b99` | Carbon8 |

**24 rows total (9 global + 15 client-specific overrides):**

| Prompt Key | Scope | Version | Status | Last Updated | Description |
|------------|-------|---------|--------|--------------|-------------|
| `agent_chat` | GLOBAL | a6778c4c | active | 2026-03-30 | Auto-seeded default |
| `daily_digest` | GLOBAL | 731d91e7 | active | 2026-03-20 | System prompt for daily email intelligence digest |
| `daily_digest` | Newbound | fc186588 | active | 2026-03-15 | Client override |
| `daily_digest` | Carbon8 | 86bd9690 | active | 2026-03-16 | Client override |
| `email_analysis_system` | GLOBAL | 2f158769 | active | 2026-03-20 | Email analysis system prompt (v1.3) |
| `email_analysis_system` | Newbound | 0f2ec6bd | active | 2026-03-15 | Client override |
| `email_analysis_system` | Carbon8 | f6382a56 | active | 2026-03-16 | Updated from Playground |
| `email_analysis_user` | GLOBAL | 86a8e8e0 | active | 2026-04-14 | Email analysis user prompt with QB reference extraction (v1.3) |
| `email_analysis_user` | Newbound | 7f5168bd | active | 2026-04-13 | Client override |
| `email_analysis_user` | Carbon8 | a1ba858c | active | 2026-04-13 | Updated from Playground |
| `insight_company` | GLOBAL | 33bc69a0 | active | 2026-03-20 | AI insight prompt for company relationship analysis |
| `insight_company` | Newbound | 270c376a | active | 2026-03-15 | Client override |
| `insight_company` | Carbon8 | 2066a823 | active | 2026-03-16 | Updated from Playground |
| `insight_contact` | GLOBAL | fee9d3b1 | active | 2026-03-20 | AI insight prompt for contact engagement analysis |
| `insight_contact` | Newbound | ff91eb2f | active | 2026-03-15 | Client override |
| `insight_contact` | Carbon8 | b6368a66 | active | 2026-03-16 | Updated from Playground |
| `insight_thread` | GLOBAL | fad7bd3c | active | 2026-03-20 | AI insight prompt for email thread deal analysis |
| `insight_thread` | Newbound | ee9180b5 | active | 2026-03-15 | Client override |
| `insight_thread` | Carbon8 | fc75fc71 | active | 2026-03-16 | Updated from Playground |
| `strategic_digest` | GLOBAL | 932d72fa | active | 2026-03-20 | System prompt for strategic digest pipeline (LangChain agent) |
| `strategic_digest` | Newbound | 5bd3fbc6 | active | 2026-03-15 | Client override |
| `strategic_digest` | Carbon8 | c6f8c319 | active | 2026-03-16 | Updated from Playground |
| `weekly_digest` | GLOBAL | b439e697 | active | 2026-03-20 | System prompt for weekly strategic email intelligence digest |
| `weekly_digest` | Carbon8 | e31c2278 | active | 2026-03-16 | Client override |

**Global prompt sizes:**

| Prompt Key | Chars | Lines |
|------------|-------|-------|
| `agent_chat` | 1,368 | 19 |
| `daily_digest` | 1,815 | 23 |
| `email_analysis_system` | 5,491 | 67 |
| `email_analysis_user` | 3,044 | 58 |
| `insight_company` | 1,262 | 21 |
| `insight_contact` | 1,106 | 20 |
| `insight_thread` | 920 | 19 |
| `strategic_digest` | 4,844 | 115 |
| `weekly_digest` | 2,434 | 36 |

**Notable:** Impressive Wardrobes (`563371a5`) has zero client-specific overrides — uses all global defaults. Newbound and Carbon8 each have overrides for most prompt keys.

### 2.4 Caller Trace Summary

| Service | Prompt Keys | Trigger | Cache |
|---------|------------|---------|-------|
| Email Analyzer | `email_analysis_system`, `email_analysis_user` | Background processing pipeline | Version-keyed |
| Digest Generator | `daily_digest`, `weekly_digest` | `POST /ai/digest/{mailbox_id}` (on-demand) | 24h in `ai_daily_digests` |
| Strategic Pipeline | `strategic_digest` | LangGraph agent invocation | — |
| Insights Engine | `insight_company`, `insight_contact`, `insight_thread` | `GET /ai/insights/{type}/{id}` (on-demand) | 24h in `relationship_context_cache` |
| Agent Service | `agent_chat` | `POST /ai/agent/chat[/stream]` (chat widget) | None (fresh each turn) |

### 2.5 Prompt Management UI

**Playground:** `frontend/src/pages/intelligence/playground.tsx`
- Edit, test, and save all 9 prompt types per-client
- `GET /api/v1/ai/prompts/defaults` — view hardcoded defaults
- `PUT /api/v1/ai/prompts` — create/update override
- `DELETE /api/v1/ai/prompts/{id}` — revert to default

**Services with NO LLM prompts (pure Python):**
- `recommendation_engine.py` — market basket + cross-contact gaps
- `ai_entity_aggregator.py` — entity rollup from already-classified emails
- `customer_analytics_service.py` — strike rate, seasonality, capabilities

---

## 3. Seasonality Engine

### 3.1 Implementation

| Layer | File | Key Objects |
|-------|------|-------------|
| **Migration** | `scripts/migrations/068_seasonality_engine.sql` | 3 RPC functions |
| **Service** | `backend/src/services/customer_analytics_service.py` lines 323–497 | `CustomerAnalyticsService.get_seasonality()` |
| **Router** | `backend/src/routers/customers.py` lines 828–845 | `GET /customers/{company_id}/seasonality` |
| **Router** | `backend/src/routers/analytics.py` line 4028 | `GET /outreach-windows` (client aggregate) |
| **Router** | `backend/src/routers/analytics.py` line 4067 | `GET /analytics/seasonality/industry/{industry}` |
| **Frontend** | `frontend/src/components/SeasonalityChart.tsx` | Full React component with aggregate + YoY views |
| **API Client** | `frontend/src/services/analyticsService.ts` lines 342–352 | `companiesApi.getSeasonality()` |

### 3.2 RPC Functions (migration 068)

| Function | Purpose |
|----------|---------|
| `get_company_seasonality(p_company_id, p_client_id)` | Monthly/yearly aggregation of orders + revenue for one company |
| `get_industry_seasonality(p_industry, p_client_id)` | Same aggregation across all companies in an industry |
| `get_outreach_windows(p_client_id, p_weeks_ahead)` | Peak months + approach windows for all companies in a client |

### 3.3 What It Computes

| Metric | Scope | Granularity |
|--------|-------|-------------|
| Monthly order count + revenue | Per company, all years aggregated | Month 1–12 |
| Year-over-year breakdown | Per company, per year | Year × Month |
| Quarterly rollup | Per company | Q1–Q4 |
| Peak months | Per company | Months where orders > mean + threshold |
| Trough months | Per company | Months where 0 < orders < mean − threshold |
| Outreach windows | Per company | 1 month before each peak month |
| YTD comparison | Per company | Current vs prior year (Jan–current month) |

**Peak/trough threshold:** `max(stdev × 0.5, mean × 0.15)` — requires ≥3 months with data.

### 3.4 Data Source

- **Table:** `qb_operations`
- **Key columns:** `matched_company_id`, `date_accepted` (NOT NULL filter), `cost_plus_price`
- **Scope:** QB-only (order history, not email engagement)
- **Date range:** All historical data for the company (no hard limit)
- **Index:** `idx_qb_operations_company_date` on `(matched_company_id, date_accepted DESC)`

### 3.5 Output Format

```typescript
{
  monthly: Array<{ month, month_name, order_count, revenue }>
  quarterly: Array<{ quarter, order_count, revenue }>
  yearly: Record<string, Array<{ month, month_name, order_count, revenue }>>
  peak_months: number[]
  trough_months: number[]
  outreach_windows: Array<{
    peak_month, peak_month_name,
    approach_month, approach_month_name,
    approach_start, approach_end,      // ISO date strings
    avg_peak_revenue, avg_peak_orders, // per-year average
    is_approaching: boolean
  }>
  ytd_comparison: {
    current_year, prior_year,
    current_ytd_revenue, prior_ytd_revenue,
    growth_pct, months_compared
  } | null
  total_orders: number
  date_range: { earliest_year, latest_year } | null
  computed_at?: string  // added by cache layer
}
```

### 3.6 UI

`SeasonalityChart.tsx` renders:
- Header with total orders and date range
- View toggle: "All Years" (aggregate) vs "Year/Year" (YoY)
- YTD growth banner (current vs prior year)
- Outreach alert if windows are approaching
- Monthly table with revenue bars, peak/trough indicators
- Quarterly breakdown panel
- Outreach window cards with "Now" badge

### 3.7 Known Limitations

| Constraint | Detail | Impact |
|------------|--------|--------|
| Min data for peaks | ≥3 months with data required | Companies with <3 active months show no pattern |
| Min data for outreach | ≥2 historical orders in a month | Sparse months won't trigger windows |
| Max rows | 50,000 operations per company (hardcoded) | Very large customers may have incomplete data |
| YoY view cap | UI shows max 4 years in legend | Older years hidden in YoY chart |
| Approach window | Month-based (peak_month − 1), not week-based | Comment says "4-6 weeks" but code does calendar months |
| No forecast | Purely retrospective pattern matching | No ML prediction of next month's orders |
| No contact-level | Company-level only | Can't see per-contact seasonal patterns |
| No fiscal year | Assumes Gregorian calendar months 1–12 | No support for alternate fiscal years |
| Cache TTL | 24 hours | Stale until next request with `force=True` |
| No explicit TODOs | None found in code comments | — |

### 3.8 Cache

Stored in `customer_intelligence_cache` with `cache_type = 'seasonality_profile'`, 24h TTL (enforced in Python, not DB).

---

## 4. Reorder Cycles & Reactivation Windows

### 4.1 What Already Exists

#### Per-Capability Order Rhythm (COMPUTED, not static)

**File:** `backend/src/services/customer_analytics_service.py` lines 500–626
**Function:** `get_capability_rhythm(company_id)`

This is the closest thing to a reorder cycle computation:
- Computes per-capability-tag average order interval from `qb_operations.date_accepted`
- Filters out same-day operations (interval < 7 days = likely batch processing)
- Returns actual computed cycles per capability tag

**Output per capability:**
```json
{
  "capability": "Digital Printing",
  "order_count": 5,
  "avg_interval_days": 42,
  "last_order_date": "2026-04-15",
  "days_since_last": 7,
  "status": "on_track",        // "overdue" if > avg × 1.3, "due_soon" if > avg × 0.9
  "message": "Usually orders every 6 weeks. Last order was 7 days ago."
}
```

**Cached:** Yes, in `customer_intelligence_cache` with `cache_type = 'capability_rhythm'`, 24h TTL.

#### Static Lifecycle Thresholds

**File:** `backend/src/services/ai_action_bucket_engine.py`

| Constant | Value | Meaning |
|----------|-------|---------|
| `NEW_CUSTOMER_DAYS` | 90 | Customer is "new" if first invoice within 90 days |
| `AT_RISK_DAYS` | 90 | "at_risk" if no orders for 90+ days AND declining engagement |
| `DEAL_STALE_DAYS` | 30 | Quote considered stale if 30+ days old with no job |
| `DORMANT_DAYS` | 180 | "dormant" if no email + no QB activity for 180+ days |

**Lifecycle function:** `compute_lifecycle_tier()` → returns `prospect | new_customer | active_customer | at_risk | dormant | champion`

#### Days-Since-Last-Order Tracking

| Source | Field | Scope |
|--------|-------|-------|
| `customer_companies` | `qb_days_since_last_invoice` (INT) | Company-level, QB sync |
| `customer_contacts` | `qb_contact_recency_days` (INT) | Contact-level, QB sync |
| `customers.py` endpoint | `computed_days_since_last_order` | On-the-fly from order history |

#### Engagement Scoring Factor

**File:** `backend/src/services/engagement_scorer.py` lines 609–630
**Function:** `_score_order_recency(days_since_last_invoice)`

| Days Since | Score (0–100) |
|------------|---------------|
| ≤ 30 | 100 |
| ≤ 60 | 85 |
| ≤ 90 | 70 |
| ≤ 180 | 50 |
| > 180 | 10 |

Weight in overall engagement score: 15%.

### 4.2 What Does NOT Exist

| Missing Feature | Description |
|----------------|-------------|
| **Per-company average order cycle** | `capability_rhythm` does it per-tag but no company-level rollup |
| **Predictive next order date** | Could derive from `last_order_date + avg_interval_days` |
| **Cycle acceleration/deceleration** | No tracking of whether intervals are shortening or lengthening |
| **Personalized at-risk thresholds** | Fixed 90/180-day thresholds, not based on each customer's actual cycle |
| **Product-level reorder cycle** | Capability rhythm is tag-level, not specific product/SKU |
| **Cross-customer cycle benchmarks** | No "your customers typically reorder every N months" baseline |

### 4.3 Available Data for Building Reorder Cycles

| Table | Field | Type | Use |
|-------|-------|------|-----|
| `qb_operations` | `date_accepted` | DATE | Primary order timing source |
| `qb_operations` | `cost_plus_price` | DECIMAL | Order revenue |
| `qb_operations` | `matched_company_id` | UUID FK | Company link |
| `qb_quotes` | `date_created`, `date_accepted` | DATE | Quote timing |
| `qb_quotes` | `contact_email` | TEXT | Contact attribution |
| `qb_quotes` | `has_job` | BOOLEAN | Conversion flag |
| `qb_jobs` | `accepted_date` | DATE | Job acceptance |
| `qb_jobs` | `invoiced_margin` | DECIMAL | Job revenue |
| `qb_sales_line_items` | `inv_date` | DATE | Invoice date |
| `qb_customers` | `recency_days` | INT | QB-computed recency |

**Indexes already exist:** `idx_qb_operations_company_date` on `(matched_company_id, date_accepted DESC)`.

### 4.4 Target Insight

To surface: *"Customer X has a typical reorder cycle of 14 months. They're at month 16 — approaching reactivation window."*

**What's needed:**

1. **Company-level cycle rollup** — aggregate `capability_rhythm` intervals into a single company-level average, weighted by revenue or order count
2. **Predictive next order** — `last_order_date + avg_cycle_days` = expected next order date
3. **Overdue detection** — `days_since_last > avg_cycle × threshold` (threshold already exists at 1.3× in capability_rhythm)
4. **Personalized at-risk** — replace static 90-day threshold with `avg_cycle × 1.3`
5. **Cycle confidence** — based on order count and interval consistency (stdev)

**Foundation exists:** `capability_rhythm` already computes per-tag intervals with overdue detection. The gap is aggregation to company level and surfacing it as a first-class metric alongside seasonality.

---

*End of audit. Sections 1–4 complete.*
