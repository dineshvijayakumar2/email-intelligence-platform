# Product / Order Pattern Analysis — Current State Audit

**Date:** June 1, 2026
**Scope:** Read-only investigation of seasonality, reorder logic, capability tracking, capability gaps, and cross-company gaps.

---

## 1. Seasonality Engine

### What It Computes

- **Monthly seasonality patterns** — order counts + revenue by month (aggregated across all years)
- **Year-over-year breakdown** — monthly data per individual year for comparison
- **Quarterly rollups** — revenue and orders by Q1–Q4
- **Peak / trough detection** — statistical analysis identifying significantly above/below-average months
- **Outreach windows** — suggests 1 month before each peak month for proactive contact
- **YTD comparison** — current year vs prior year revenue (Jan to current month)

### Level

**Per-company** and **per-industry** (aggregate across all companies in an industry). No contact-level seasonality.

### Time Window

All historical data — no hard year limit. Capped at 50,000 operations per company (pagination safeguard).

### Data Source

`qb_operations` table — actual orders/invoices from QuickBase. NOT email-based.

Key columns: `matched_company_id`, `date_accepted` (NOT NULL filtered), `cost_plus_price`.

### Peak / Trough Formula

```python
if len(counts) >= 3:
    mean = statistics.mean(counts)
    stdev = statistics.stdev(counts) if len(counts) > 1 else 0
    threshold = max(stdev * 0.5, mean * 0.15)
    peak_months = [m for m in monthly if m['order_count'] > mean + threshold]
    trough_months = [m for m in monthly if 0 < m['order_count'] < mean - threshold]
```

Requires minimum 3 months with data for pattern detection.

### Database RPCs (Migration 068)

| RPC | Purpose |
|-----|---------|
| `get_company_seasonality(p_company_id, p_client_id)` | Monthly aggregation per company (year, month, order_count, revenue) |
| `get_industry_seasonality(p_industry, p_client_id)` | Cross-company aggregation per industry with company_count |
| `get_outreach_windows(p_client_id, p_weeks_ahead)` | All companies approaching a peak month (default 8 weeks ahead) |

### Backend

**Service:** `backend/src/services/customer_analytics_service.py` (lines 323–497)

**Method:** `get_seasonality(company_id, force=False)` — checks 24h cache in `customer_intelligence_cache`, calls RPC, computes peaks/troughs/outreach/YTD.

**API Endpoints:**

| Endpoint | Purpose |
|----------|---------|
| `GET /customers/{company_id}/seasonality` | Full seasonality response (cached 24h) |
| `GET /analytics/outreach-windows?client_id=X&weeks_ahead=8` | Client-wide outreach windows |
| `GET /analytics/seasonality/industry/{industry}?client_id=X` | Industry-level monthly patterns |

### Frontend

**Component:** `SeasonalityChart.tsx` — displays on company detail page alongside StrikeRateCard.

Features:
- Toggle between "All Years" and "Year/Year" views
- YTD comparison banner (green/red growth %)
- Outreach alert banner when window is approaching
- Monthly table with peak/trough indicators
- Year-over-year color-coded table (max 4 years in legend)
- Quarterly panel (Q1–Q4)
- Outreach window cards with "Now" badge

### AI Integration

- LangChain tool: `company_analytics` with `analysis="seasonality"` (langchain_tools.py lines 927–1019)
- Context appended to company insight prompts: peak months, outreach windows, YTD comparison
- Used in strategic summary generation

### Known Limitations

| Constraint | Impact |
|-----------|--------|
| Min 3 months data for peaks | Sparse companies show no pattern |
| Min 2 orders/month for outreach | Low-volume months won't trigger |
| Month-based approach window (peak_month − 1) | Not week-granular |
| No forecast/ML prediction | Purely retrospective |
| No contact-level | Company-level only |
| No fiscal year support | Assumes Jan–Dec |
| 24h cache TTL | Stale until forced refresh |
| Max 50K operations/company | Very large customers may truncate |

---

## 2. Ordering Rhythm / Overdue Capability Flags

### What Exists

A **per-capability ordering rhythm engine** that computes actual reorder cycles from historical order data, detects overdue orders, and flags approaching reorder windows.

### Engine

**Service:** `backend/src/services/customer_analytics_service.py` (lines 503–626)
**Endpoint:** `GET /customers/{company_id}/capability-rhythm`
**Cache:** 24h TTL in `customer_intelligence_cache` (cache_type = `capability_rhythm`)

### Computation Per Capability Tag

| Step | Calculation |
|------|-----------|
| Collect dates | All `date_accepted` values per `qb_capability_tag` |
| Deduplicate | Remove same-day duplicates (batch ops) |
| Filter intervals | Days between consecutive orders; remove < 7 days (same-job ops) |
| Average interval | `avg_interval_days = sum(filtered) / count(filtered)` |
| Days since last | `today - last_order_date` |
| Overdue threshold | `avg_interval × 1.3` |
| Due soon threshold | `avg_interval × 0.9` |
| Status | `overdue` / `due_soon` / `on_track` / `insufficient_data` |
| Overdue days | `max(0, round(days_since_last - avg_interval))` |

### Alert Severity

| Condition | Severity |
|-----------|----------|
| `overdue_days > avg_interval × 0.5` | `danger` |
| `overdue_days > 0` but below above | `warning` |

### Output Schema

```typescript
{
  rhythms: [{
    capability: string,
    order_count: number,
    avg_interval_days: number | null,
    last_order_date: string,
    days_since_last: number,
    status: "overdue" | "due_soon" | "on_track" | "insufficient_data",
    overdue: boolean,
    overdue_days: number,
    message: string
  }],
  alerts: [{
    capability: string,
    overdue_days: number,
    severity: "danger" | "warning"
  }]
}
```

### Frontend

**Component:** `CapabilityRhythmCard.tsx`
- Table sorted by overdue_days descending
- Overdue count badge in header (red with alert icon)
- Overdue rows highlighted light red
- Status column: "X days overdue" (danger) / "Due soon" (warning) / "On track" (success)

### What Does NOT Exist

| Missing Feature | Description |
|----------------|-------------|
| Company-level reorder cycle | No rollup of per-capability rhythms into single company cycle |
| Persistent reorder flag | No column marking customer as "due for reorder" on `customer_companies` |
| Predictive next order date | Not calculated: `last_order_date + avg_interval_days` |
| Personalized at-risk thresholds | Fixed 90/180-day cutoffs in lifecycle logic, not tied to actual customer cycle |
| Cycle confidence / variability | No stdev tracking — can't distinguish consistent vs erratic orderers |
| SKU-level reorder | Capability-tag level only, not specific product/SKU |
| Cross-customer cycle benchmarks | No "typical reorder interval" per industry |

**Bucket list status:** `[D] Due for Reorder (reorder cycle, approaching-window flag)` — deferred.

---

## 3. Product / Capability Tracking

### Data Sources

**QB Operations** (`qb_operations`) — primary source with three tiers of capability data:

| Field | Source | Description |
|-------|--------|-------------|
| `qb_capability_tag` | QB formula field | Primary capability (e.g., "Flat Sheets", "Embellishment") |
| `qb_process_tag` | QB formula field | Process classification |
| `qb_embellishment_tag` | QB formula field | Embellishment type (foil, UV, etc.) |
| `qb_machine_tier_tag` | QB formula field | Machine capability tier |
| `capability_tags` | Local classifier | JSONB array — fallback when QB tags missing |

**QB Unique Emails** (`qb_unique_emails`) — aggregated per-contact:
- `capabilities_used` (JSON array)
- `processes_used` (JSON array)
- `embellishments_used` (JSON array)

### Capability Taxonomy — 8 MVP Tags

| Tag ID | Name | Description |
|--------|------|-------------|
| `flat_sheets` | Flat Sheets | Sheetfed offset and digital flat print |
| `soft_cover_books` | Soft Cover Books | Perfect binding, saddle stitch, wire binding |
| `hard_cover_books` | Hard Cover Books | Casebinding, section sewing, oversewing |
| `wide_format` | Wide Format | WF print, laminating, mounting |
| `embellishment` | Embellishment | Foil, spot UV, varnish, digital foil, embossing |
| `specialty_finishing` | Specialty Finishing | Zund, laser cut, die cut |
| `design_services` | Design Services | Design, artwork, pre-press |
| `display_install` | Display & Install | Display, signage, installation |

### Classifier System

**File:** `backend/src/services/capability_classifier.py`

- 597+ operation tuples `(department, operation, machine) → capability_tag`
- Stored in `client_taxonomy_config` table (per-client, versioned)
- Exact match first, keyword fallback second
- Also sets flags: `has_coating`, `has_sewing`, `has_outsource_component`, `am_rush`
- Bulk reclassify via `POST /intelligence-config/reclassify`

### Per-Company Capability Aggregation

Three analytics methods in `customer_analytics_service.py`:

| Method | What It Computes |
|--------|-----------------|
| `get_contact_capabilities(company_id)` | Per-contact capability usage (order_count, revenue, last_order_date per tag) |
| `get_capability_rhythm(company_id)` | Per-capability reorder interval + overdue detection |
| `get_seasonality(company_id)` | Monthly/quarterly ordering patterns |

### Market Basket Analysis ("Similar Customers Buy")

**Yes, exists.** Implemented in `recommendation_engine.py::recompute_affinities()`.

| Table | Purpose |
|-------|---------|
| `product_affinities` | Pre-computed co-occurrence of operations across companies |

**Logic:**
```
For each pair (operation_a, operation_b):
    count = companies that use both
    if count >= 3 (MIN_AFFINITY_SUPPORT):
        confidence = count / companies_using_operation_a
        → stored in product_affinities
```

At query time: suggest operations the company hasn't tried but similar companies use, ranked by confidence.

### No Product Catalog / Hierarchy

- No formal product catalog table
- No parent-child capability hierarchy
- No capability versioning or lifecycle tracking
- Taxonomy is flat (8 tags, no nesting)

### Frontend Components

| Component | What It Shows |
|-----------|---------------|
| `ContactCapabilitiesCard.tsx` | Per-contact capability table (contact × capability × orders × revenue) |
| `ProductProfileCard.tsx` | Revenue by category, capabilities breakdown, ops by department, processes, embellishments |
| `CapabilityRhythmCard.tsx` | Per-capability ordering rhythm with overdue status |

---

## 4. Capability Gaps Analysis

### What Exists — Two Levels

#### Level 1: Cross-Contact Capability Gaps (Production)

**File:** `backend/src/services/recommendation_engine.py` (lines 189–325)
**Method:** `_compute_cross_contact(company_id)`

**Logic:**
- For each person-type contact at a company:
  - `already_buys` = capabilities this contact has been quoted on (via `qb_quotes` → `qb_capability_tag`)
  - `untapped_capabilities` = capabilities the company uses that this contact hasn't touched
- Minimum: 2 person contacts per company (`MIN_CONTACTS_FOR_GAPS = 2`)
- Filters: excludes shared mailboxes, automated contacts; flags domain mismatches

**Comparison level:** Contact-to-company (what capabilities does the company use that this specific contact hasn't been exposed to). NOT customer-to-customer or industry benchmarking.

#### Level 2: Related Product Opportunities (Production)

**File:** `recommendation_engine.py` (lines 557–615)
**Method:** `_compute_related_product(company_id)`

Uses pre-computed `product_affinities` table. Suggests operations the company hasn't tried based on co-occurrence across other companies. Confidence-ranked, top 5 returned.

#### Revenue Concentration & Buyer Decay Risk (Production)

**File:** `recommendation_engine.py` (lines 331–429)
**Method:** `_compute_revenue_concentration(company_id)`

| Risk Type | Trigger |
|-----------|---------|
| `buyer_decay_risk` | Top buyer's persona = `inactive_buyer` |
| `concentration_risk` | Revenue > $100K AND ≤2 contacts producing revenue AND >4 total contacts |

### How "Industry" Is Defined

Industry comes **exclusively from QB customer master data** — stored in `customer_companies.industry`.

- One industry per company (no multi-industry)
- Values stored verbatim from QB (granular, not normalized)
- `industry_benchmarks` view (migration 088) computes per-industry averages but requires ≥3 person-type contacts
- Benchmarks include: `avg_strike_rate`, `avg_quote_value`, `avg_email_velocity_30d`, `avg_engagement_score`
- Accessible via `GET /contacts-intelligence/industry/{industry}/benchmarks`

### Industry Data Quality — Production Reality (June 2026)

| Category | Count | % |
|----------|------:|---:|
| `Not Selected` | 10,496 | 52.4% |
| `NULL` | 7,013 | 35.0% |
| **Meaningful values** | **2,538** | **12.7%** |

**16 distinct industry values** (meaningful only):

| Industry | Count |
|----------|------:|
| Creative Arts & Design | 472 |
| Small Business or Individual | 437 |
| Advertising & Marketing | 274 |
| Corporate & Professional | 254 |
| Property & Real Estate | 212 |
| Hospitality Food & Beverage | 146 |
| Trade Printers | 143 |
| Luxury Brands | 124 |
| Small business or individual | 101 |
| Retail & POS | 97 |
| Government & NFP | 84 |
| Industrial & Manufacturing | 73 |
| Education & Training | 59 |
| Healthcare & Medical | 46 |
| Print Industry / Broker / Supplier | 11 |
| Extinct | 5 |

**Data quality issues:**
1. **87.3% have no industry** — `Not Selected` + `NULL` = 17,509 of 20,047 companies
2. **Case-sensitivity dupe** — "Small Business or Individual" (437) vs "Small business or individual" (101)
3. **"Extinct" (5)** — status value, not an industry
4. **Trade Printers (143) vs Print Industry / Broker / Supplier (11)** — potentially mergeable

**Verdict:** Industry-peer comparison is **not viable** without normalization work. Options: QB-side backfill (upstream), AI-inferred industry (expensive/noisy), or collapsing to fewer mega-categories (reduces usefulness).

### What's NOT Implemented

| Feature | Status |
|---------|--------|
| Industry peer comparison for capabilities | **Not built** — `industry_benchmarks` view exists but not wired into recommendations |
| "Median company in your industry uses X capabilities" | **Not built** |
| Cross-customer capability gap (company vs peers) | **Not built** — only contact-vs-own-company |
| Capability coverage % per industry | **Not built** |
| Industry data normalization | **Not done** — 87.3% of companies have no meaningful industry value |

### Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /customers/{company_id}/recommendations` | Cross-contact gaps + related products + revenue insight (24h cache) |
| `GET /customers/portfolio-insights` | Portfolio-wide scan for concentration/decay risks |

### Frontend

**Component:** `RecommendationsPanel.tsx` — on company detail page under "Sales Opportunities":
- Revenue concentration/decay risk alert card
- Contact capability gaps (emerald "already buys" + amber "untapped" badges)
- Related product opportunities (confidence % + supporting company count)
- Manual refresh button

---

## 5. Cross-Company Gaps Revival

### What Was Revived

The Cross-Company Gaps feature was **fully revived and completed in May 2026**, integrated into `RecommendationEngine` (not standalone code).

### What It Surfaces

#### A. Cross-Contact Capability Gaps
Shows per-contact: what the company buys that this contact hasn't been involved with.

```
Contact: Sarah Jones
  Already buys: [Digital Printing, Binding]
  Untapped:     [Wide Format, Embellishment, Specialty Finishing]
  → "Sarah buys 2 capability(ies) but hasn't been introduced to 3 other(s)"
```

#### B. Revenue Concentration Risk
```
Revenue: $125,000
Contacts: 8 total, 2 producing revenue
Top Revenue Contacts:
  Contact A: 65% · $81,250
  Contact B: 35% · $43,750
Unengaged: [Contact C (prospect, score 42), ...]
```

#### C. Related Product Opportunities
```
"75% of customers using Digital Printing also use Binding (12 companies)"
```

#### D. Product Profile Breakdown
- Revenue by product category (from `qb_sales_line_items.product_group`)
- Operations by department
- Capability/process/embellishment tag lists

### AI Integration

- AI strategic summary includes revenue risk + capability gaps as context
- Prompt (migration 103) references concentration risk + gaps
- "Analyze" button on company detail triggers LLM synthesis

---

## Gaps for Future Work

### For Product Diversification Analysis (C2)

| Gap | Description | Severity |
|-----|-------------|----------|
| No industry-peer capability comparison | Can't answer "what do similar companies buy that you don't?" | **High** — core C2 requirement |
| No capability coverage % per industry | Can't benchmark: "you use 4 of 8 capabilities; peers average 6" | **High** |
| No normalized industry taxonomy | QB industry values are raw/granular, not grouped for comparison | **Medium** |
| No capability adoption trajectory | Can't show "companies your size typically adopt X after Y" | **Medium** |
| No revenue-per-capability benchmarking | Can't compare "$X/year on printing" vs industry median | **Medium** |
| Flat taxonomy (8 tags) | No parent-child hierarchy for drill-down analysis | **Low** |

### For Industry-Peer Recommendations (C3, Q4)

| Gap | Description | Severity |
|-----|-------------|----------|
| Status transition analytics blocked until July 2026 | Can't track persona changes over time | **Blocking** |
| No cross-client industry benchmarks | All comparisons scoped to single client (tenant) | **High** — limits peer pool |
| `industry_benchmarks` view not wired to recommendations | View exists but not used in gap suggestions | **Medium** — plumbing exists |
| No insight validation UI | Can't mark recommendations as correct/partial/incorrect | **Medium** |
| No push-based alerts for new gaps | Recommendations are pull-only (click to see) | **Low** |
| No seasonal timing integration | Gaps don't consider "is now the right time?" | **Low** |

---

## Summary Table

| Capability | Schema | Backend | Frontend | Status |
|------------|--------|---------|----------|--------|
| Seasonality (company) | RPC (068) + cache | customer_analytics_service | SeasonalityChart | **Production** |
| Seasonality (industry) | RPC (068) | analytics router | — | **Backend only** |
| Outreach windows | RPC (068) | analytics router | SeasonalityChart (banner) | **Production** |
| Capability rhythm + overdue | Cache table | customer_analytics_service | CapabilityRhythmCard | **Production** |
| Company-level reorder flag | — | — | — | **Deferred** |
| 8-tag capability taxonomy | client_taxonomy_config | capability_classifier | ProductProfileCard | **Production** |
| 597+ classifier rules | client_taxonomy_config | capability_classifier | Intelligence Config page | **Production** |
| Market basket (product_affinities) | product_affinities table | recommendation_engine | RecommendationsPanel | **Production** |
| Cross-contact capability gaps | customer_recommendations cache | recommendation_engine | RecommendationsPanel | **Production** |
| Revenue concentration risk | contact_persona view | recommendation_engine | RecommendationsPanel | **Production** |
| Industry benchmarks view | SQL view (088) | contacts_intelligence router | — | **Backend only** |
| Industry-peer capability comparison | — | — | — | **Not built** (C2) |
| Status transition analytics | — | — | — | **Blocked** (C3, July 2026) |
| Insight validation UI | — | — | — | **Not built** |
