# Contact Intelligence & Industry Rollup — Design Document

## Business Context

Print/manufacturing B2B platform. Account Managers (AMs) need to understand how "painful" a contact is — measured by quote conversion, response delays, job complexity, and factory strain — so they can price accordingly and allocate effort wisely. Stats computed per contact roll up to customer (company) and then to industry for benchmarking.

## Data Model — What Already Exists

All reference fields are already synced from Quickbase. The full join chain:

```
customer_contacts.email_address
  ↕ (case-insensitive email match)
qb_quotes.contact_email          ← DIRECT contact-level quote attribution
  → qb_quotes.job_no
    → qb_jobs.job_no
      → qb_operations.job_no     (factory operations per job)
      → qb_sales_line_items.job_no (revenue per job)

customer_contacts.email_address
  ↕ (case-insensitive email match)
qb_unique_emails.email
  → qb_customers.qb_record_id
    → customer_companies (via matched_company_id)
      → customer_companies.industry (from qb_customers, field 59)
```

### Key synced fields available for metrics

**qb_quotes:** `contact_name`, `contact_email`, `date_accepted`, `job_no`, `has_job` (boolean — quote converted to job), `category`, `quantity`, `kinds`, `total_quantity`

**qb_jobs:** `job_no`, `quote_no`, `qb_customer_id`, `retail_sale`, `invoiced_margin`, `margin_pct`, `factory_rush_level`

**qb_operations:** `job_no`, `quote_no`, `operation_name`, `machine`, `department`, `date_accepted`

**qb_sales_line_items:** `job_no`, `job_am_name`, `inv_date`, `qb_customer_id`, `invoice_id`

**qb_contacts:** `qb_customer_id`, `email`, `quotes_accepted_count`, `most_recent_quote_date`, `contact_recency_days`, `matched_contact_id` (FK to customer_contacts — 12,641 already linked)

**qb_unique_emails:** `email`, `qb_customer_id`, `customer_type`, `capabilities_used`, `processes_used`, `quality`, `hide`, `email_invalid`

**qb_customers:** `industry` (field 59, populated on 15,124 of 15,127 rows), `customer_tier`, `account_manager`, `recency_days`

### Existing columns on customer_contacts (from migration 021a, ALL NULL today)
- `qb_customer_type` — never populated
- `qb_quotes_count` — never populated
- `qb_last_quote_date` — never populated
- `qb_contact_recency_days` — never populated

### Existing AI integration
`_enrich_with_sprint2_data()` in `ai_email_analyzer.py:898` already reads the above four fields from contacts for email intent classification. Currently gets NULLs. Populating them immediately improves AI output with zero code changes to the AI layer.

---

## Phase 0: Contact-QB Metadata Linking (Foundation)

**Status:** Plan exists (`081_qb_contact_linking_and_industry_rollup.sql`), ready to execute with fixes.

**What it does:**
1. Populates the four existing NULL columns on `customer_contacts` from `qb_unique_emails` + `qb_contacts`
2. Adds `qb_capabilities_used`, `qb_processes_used`, `qb_linked_at` columns
3. Propagates `industry` from `qb_customers` to `customer_companies`
4. Creates `customer_industry_segments` analytics VIEW

**Four fixes required before execution:**
1. GRANT on the new RPC must match existing `batch_propagate_qb_data` grants (likely service_role only, NOT anon/authenticated)
2. Remove inline backfill from migration — run via standalone script separately
3. Change error handling from `logger.warning` to `logger.error` with `exc_info=True`
4. Post-deployment EXPLAIN ANALYZE verification on the email-match UPDATE

**Deliverables:** Migration SQL, sync pipeline edit, backfill script.

**Estimated effort:** 2-3 days.

---

## Phase 1: Contact-Level Persona Metrics (Core Feature)

### 1A. Database Layer — Metric Computation Views

Create a set of SQL views (or a materialized view refreshed by background job) that compute persona metrics per contact. These are the building blocks for the contact profile UI and the rollup architecture.

#### View: `contact_quote_metrics`

Per-contact quote and job attribution metrics. The key join is `qb_quotes.contact_email` → `customer_contacts.email_address`.

```sql
-- Conceptual shape (not final SQL — implementer should optimize)
SELECT
  cc.id AS contact_id,
  cc.client_id,
  cc.customer_company_id,

  -- Strike rate
  COUNT(qq.qb_record_id) AS total_quotes,
  COUNT(qq.qb_record_id) FILTER (WHERE qq.has_job = true) AS converted_quotes,
  ROUND(
    COUNT(qq.qb_record_id) FILTER (WHERE qq.has_job = true)::numeric
    / NULLIF(COUNT(qq.qb_record_id), 0), 3
  ) AS strike_rate,

  -- Revenue (from jobs that came from this contact's quotes)
  COALESCE(SUM(qj.retail_sale), 0) AS total_revenue,
  AVG(qj.retail_sale) AS avg_revenue_per_job,

  -- Profitability
  AVG(qj.margin_pct) AS avg_margin_pct,

  -- Factory strain
  AVG(qj.factory_rush_level) AS avg_rush_level,

  -- Job complexity (operations per job)
  AVG(op_counts.ops_per_job) AS avg_operations_per_job,

  -- Recency
  MAX(qq.date_accepted) AS most_recent_quote_date,
  COUNT(qq.qb_record_id) FILTER (
    WHERE qq.date_accepted >= NOW() - INTERVAL '12 months'
  ) AS quotes_last_12m

FROM customer_contacts cc
LEFT JOIN qb_quotes qq
  ON LOWER(qq.contact_email) = LOWER(cc.email_address)
  AND qq.client_id = cc.client_id
LEFT JOIN qb_jobs qj
  ON qj.job_no = qq.job_no
  AND qj.client_id = cc.client_id
LEFT JOIN LATERAL (
  SELECT COUNT(*) AS ops_per_job
  FROM qb_operations qo
  WHERE qo.job_no = qj.job_no AND qo.client_id = cc.client_id
) op_counts ON qj.job_no IS NOT NULL
GROUP BY cc.id, cc.client_id, cc.customer_company_id;
```

#### View: `contact_email_metrics`

Per-contact email behavior metrics. Uses existing `emails` + `email_contact_links` data.

```sql
-- Conceptual shape
SELECT
  cc.id AS contact_id,
  cc.client_id,

  -- Volume
  COUNT(e.id) AS total_emails,
  COUNT(e.id) FILTER (WHERE e.direction = 'inbound') AS inbound_count,
  COUNT(e.id) FILTER (WHERE e.direction = 'outbound') AS outbound_count,

  -- Thread density
  COUNT(DISTINCT e.canonical_thread_id) AS thread_count,

  -- Response time (average time between inbound and next outbound on same thread)
  -- This requires a self-join or window function on emails ordered by sent_date per thread
  -- Placeholder — implementer should use window function approach:
  --   For each inbound email, find the next outbound on the same thread,
  --   compute the gap, and average across all such pairs for this contact
  NULL::interval AS avg_response_time_to_contact,  -- time for AM to reply to this contact
  NULL::interval AS avg_response_time_from_contact, -- time for contact to reply to AM

  -- Recency
  MAX(e.sent_date) AS last_email_date,
  COUNT(e.id) FILTER (
    WHERE e.sent_date >= NOW() - INTERVAL '3 months'
  ) AS emails_last_3m

FROM customer_contacts cc
LEFT JOIN email_contact_links ecl ON ecl.contact_id = cc.id
LEFT JOIN emails e ON e.id = ecl.email_id
GROUP BY cc.id, cc.client_id;
```

**Note on response time computation:** The avg_response_time columns above are placeholders. Computing response time correctly requires pairing each inbound email with the next outbound email on the same thread (or vice versa). This is a window function problem:

```sql
-- Pattern for response time pairs (to be embedded in the view or a helper CTE)
WITH email_pairs AS (
  SELECT
    e.canonical_thread_id,
    e.sent_date,
    e.direction,
    ecl.contact_id,
    LEAD(e.sent_date) OVER (
      PARTITION BY e.canonical_thread_id
      ORDER BY e.sent_date
    ) AS next_email_date,
    LEAD(e.direction) OVER (
      PARTITION BY e.canonical_thread_id
      ORDER BY e.sent_date
    ) AS next_direction
  FROM emails e
  JOIN email_contact_links ecl ON ecl.email_id = e.id
  WHERE e.canonical_thread_id IS NOT NULL
)
-- Then filter for inbound→outbound pairs (AM response time)
-- or outbound→inbound pairs (contact response time)
-- and average the gap per contact
```

This is computationally expensive on 244K emails. Best done as a materialized view refreshed on schedule, not a live view.

#### Combined view: `contact_persona`

Joins quote metrics and email metrics into a single contact profile. This is the view the frontend queries.

```sql
SELECT
  cqm.contact_id,
  cqm.client_id,
  cqm.customer_company_id,
  comp.industry,

  -- QB metrics
  cqm.total_quotes,
  cqm.converted_quotes,
  cqm.strike_rate,
  cqm.total_revenue,
  cqm.avg_revenue_per_job,
  cqm.avg_margin_pct,
  cqm.avg_rush_level,
  cqm.avg_operations_per_job,
  cqm.quotes_last_12m,

  -- Email metrics
  cem.total_emails,
  cem.thread_count,
  cem.avg_response_time_from_contact,
  cem.emails_last_3m,

  -- Derived persona indicators
  CASE
    WHEN cqm.total_revenue > 0 THEN
      cem.thread_count::numeric / (cqm.total_revenue / 1000.0)
    ELSE NULL
  END AS effort_to_revenue_ratio,
  -- Higher = more email threads per $1K revenue = more effort per dollar

  CASE
    WHEN cqm.total_quotes > 0 THEN
      cqm.strike_rate * COALESCE(cqm.avg_margin_pct, 0) / 100.0
    ELSE NULL
  END AS value_score
  -- Higher = converts well AND profitable when they do

FROM contact_quote_metrics cqm
LEFT JOIN contact_email_metrics cem ON cem.contact_id = cqm.contact_id
LEFT JOIN customer_companies comp ON comp.id = cqm.customer_company_id;
```

### 1B. Rollup Views

#### Company rollup: `company_contact_summary`

```sql
SELECT
  customer_company_id,
  client_id,

  COUNT(*) AS total_contacts,
  COUNT(*) FILTER (WHERE total_quotes > 0) AS contacts_with_quotes,

  -- Aggregated QB metrics
  SUM(total_quotes) AS company_total_quotes,
  SUM(converted_quotes) AS company_converted_quotes,
  ROUND(SUM(converted_quotes)::numeric / NULLIF(SUM(total_quotes), 0), 3) AS company_strike_rate,
  SUM(total_revenue) AS company_contact_attributed_revenue,
  AVG(avg_margin_pct) FILTER (WHERE avg_margin_pct IS NOT NULL) AS company_avg_margin,
  AVG(avg_rush_level) FILTER (WHERE avg_rush_level IS NOT NULL) AS company_avg_rush_level,

  -- Aggregated email metrics
  SUM(total_emails) AS company_total_emails,
  SUM(thread_count) AS company_total_threads,

  -- Pain distribution
  MAX(effort_to_revenue_ratio) AS worst_effort_ratio,
  MIN(value_score) FILTER (WHERE value_score IS NOT NULL) AS lowest_value_contact

FROM contact_persona
GROUP BY customer_company_id, client_id;
```

#### Industry rollup: `industry_benchmarks`

Extends the existing `customer_industry_segments` VIEW with persona metric averages:

```sql
SELECT
  comp.industry,
  comp.client_id,

  -- Company counts (from existing view pattern)
  COUNT(DISTINCT comp.id) AS company_count,

  -- Industry-level persona benchmarks
  AVG(ccs.company_strike_rate) AS avg_strike_rate,
  AVG(ccs.company_avg_margin) AS avg_margin,
  AVG(ccs.company_avg_rush_level) AS avg_rush_level,
  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ccs.worst_effort_ratio) AS median_effort_ratio,

  -- Revenue
  SUM(ccs.company_contact_attributed_revenue) AS industry_total_revenue,
  AVG(ccs.company_contact_attributed_revenue) AS avg_revenue_per_company

FROM customer_companies comp
JOIN company_contact_summary ccs ON ccs.customer_company_id = comp.id
WHERE comp.industry IS NOT NULL
  AND comp.industry NOT IN ('Not Selected', '')
GROUP BY comp.industry, comp.client_id;
```

### 1C. Storage Strategy

**For launch:** Use regular views for `contact_quote_metrics` and `contact_persona`. Use a materialized view for `contact_email_metrics` (the response-time computation is too expensive for live queries). Refresh the materialized view daily or after QB sync.

**Post-launch if performance requires:** Convert all three to materialized views with scheduled refresh. Or move to a precomputed `contact_metrics` table updated by a background job after each QB sync — matches the existing `propagate_qb_data_to_companies` pattern.

**Do NOT add 15 metric columns to `customer_contacts`.** Keep the base table clean. Metrics are derived data — they belong in views or materialized views, not in the source table.

### 1D. API Endpoints

```
GET /contacts/{contact_id}/persona
  → Returns the contact_persona view row for this contact
  → Include the company's industry benchmarks alongside for context
  → "This contact's strike rate is 42% vs industry average of 68%"

GET /companies/{company_id}/contact-summary
  → Returns company_contact_summary + individual contact personas
  → Sorted by value_score DESC (most valuable first) or effort_ratio DESC (most painful first)

GET /analytics/industry-benchmarks?client_id=X
  → Returns industry_benchmarks view
  → For the industry comparison dashboard
```

### 1E. Estimated effort

- Database views + materialized view: 1 week
- Response time computation (the tricky part): 2-3 days within that week
- API endpoints: 2-3 days
- Testing + validation against known contacts: 2-3 days
- Total: ~2 weeks

---

## Phase 2: Frontend — Contact Persona UI

### 2A. Contact Profile Card

Displayed on the contact detail page and as a summary row in the company profile's contact list.

**Sections:**

**Identity header:**
- Name, email, company name, `qb_customer_type` badge ("Active A Customer", "Prospect")
- Last contact date, email volume trend (last 3 months vs prior 3 months)

**QB performance metrics (from contact_quote_metrics):**
- Strike rate: "42% (5 of 12 quotes converted)" with visual bar
- Total revenue: "$34,200 across 5 jobs"
- Avg margin: "28.3%" (color-coded: green >30%, amber 15-30%, red <15%)
- Factory rush level: average, with indicator if above company/industry norm

**Email behavior (from contact_email_metrics):**
- Avg response time FROM contact: "2.4 days" (how fast they respond to AMs)
- Thread density: "8.2 threads per quote" (how much hand-holding they need)
- Email recency: "Last email: 3 days ago"

**Persona summary (derived indicators):**
- Effort-to-revenue ratio: visual indicator (low/medium/high effort per $)
- Value score: composite of strike rate × margin
- One-line AI-generated summary: "High-converting contact with above-average margins but slow response times. Jobs occasionally require rush handling."

**Comparison to benchmarks:**
- Show each metric alongside the company average and industry average
- Highlight where this contact deviates significantly (>1 std dev from company mean)

### 2B. Company Profile Enhancement

Add a "Contact Breakdown" section to the existing company profile page:

- Table of contacts with key persona metrics as columns
- Sortable by any metric
- Visual highlighting of "most valuable" and "most painful" contacts
- Company-level aggregates as a summary row at top

### 2C. Industry Dashboard (new page or section)

- Table of industries with benchmarked metrics
- Sortable, filterable by client
- Click-through to see companies in that industry
- Comparison view: "How does Company X compare to its industry?"

### 2D. Estimated effort
- Contact persona card component: 1 week
- Company profile enhancement: 3-4 days
- Industry dashboard: 3-4 days
- Total: ~2.5 weeks (can overlap with late Phase 1)

---

## Phase 3: Thread-to-QB Journey Linking (Deferred)

### What it does
Links specific email threads to specific QB quotes/jobs, enabling:
- "Show me the email conversation that led to Job #4521"
- "This thread discusses Quote #2847 — here's what happened to that quote"
- Journey timeline on the customer profile: inquiry → quote → job → production → invoice

### Approach
1. **Reference number extraction** from email subjects/bodies using regex patterns for quote numbers, job numbers, PO numbers. The 80/20 approach.
2. **AI extraction** as enhancement for threads where regex doesn't find references.
3. **Manual linking** as a correction mechanism — AMs can associate threads with quotes/jobs in the UI.

### Data model
```sql
thread_qb_links (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  canonical_thread_id TEXT NOT NULL,
  link_type TEXT NOT NULL,  -- 'quote', 'job'
  qb_record_id TEXT NOT NULL,
  qb_reference TEXT,  -- the human-readable reference (e.g., "Q-2847", "J-4521")
  confidence FLOAT DEFAULT 1.0,
  source TEXT NOT NULL,  -- 'regex', 'ai', 'manual'
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Why deferred
Phases 0-2 deliver the persona scoring and rollup metrics without needing thread-level linking. The journey view is additive. Ship the persona first, validate with AMs, then build this.

### Estimated effort: 3-4 weeks when undertaken.

---

## Phase 4: Status Transition Analytics (Blocked)

### Dependency
QB job status log child table — being created this week. Needs to be:
1. Created in Quickbase
2. Added to the sync field mappings (new table: `qb_job_status_log`)
3. Accumulate 2-3 months of data before meaningful analytics

### What it enables (when data is available)
- Time-in-phase metrics: "This contact's jobs spend 4.2 days in proofing vs 1.8 industry average"
- Bottleneck detection: "Jobs from Contact X get stuck in 'Waiting art/approval' 3x more than average"
- Production cycle time: quote acceptance → job completion duration per contact
- Status-aware factory strain: not just "did it go on hold" but "how long was it on hold"

### Action for now
When the child table is created, immediately add it to the sync pipeline as a new table. Start syncing even before building analytics — data accumulation is the bottleneck, not code.

Proposed sync mapping:
```
qb_job_status_log:
  - qb_record_id (Record ID)
  - job_no (Job No reference)
  - old_status (Previous status)
  - new_status (New status)  
  - changed_at (Timestamp of change)
  - changed_by (User who made the change)
```

---

## Dependency Graph

```
Phase 0: Contact-QB metadata linking ← THIS WEEK
  │
  ├── Phase 1: Persona metric views + API (2 weeks)
  │     │
  │     └── Phase 2: Frontend UI (2.5 weeks, overlaps with late Phase 1)
  │
  ├── Start syncing QB job status log (whenever created, no code dependency)
  │
  └── Industry propagation (included in Phase 0 migration)
        │
        └── Industry benchmarks (included in Phase 1 rollup views)

Phase 3: Thread-QB journey linking (deferred, 3-4 weeks when undertaken)
Phase 4: Status transition analytics (blocked on data accumulation, ~3 months)
```

**Total to shippable persona feature:** ~5-6 weeks from Phase 0 completion.
**First visible improvement (AI prompt enrichment):** This week with Phase 0.

---

## Fields Not Currently Synced but Worth Adding

Review the QB field counts — you're syncing a fraction of available fields:
- Contacts: 10/74
- Quotes: 15/55
- Jobs: 22/62
- Sales Line Items: 13/62
- Operations: 30/43
- Unique Emails: 16/106
- Customers: 14/128

For persona metrics, consider adding to the sync:
- **Quotes:** `date_created` (for quote-to-acceptance cycle time), `quote_value` or `quote_total` (for value before conversion)
- **Jobs:** `job_status` (current status — for the status distribution metrics), `date_created`, `date_completed` (for job cycle time)
- **Operations:** `status`, `date_completed` (for operation-level cycle time)
- **Contacts:** `title` (for contact role context in AI prompts)

These are additive — they make metrics richer but aren't blockers for Phase 1.

---

## Open Questions for Business Partner

1. **Persona metric weighting:** Which matters more for pricing decisions — strike rate, margin, or factory strain? This determines how the composite "value score" should be weighted.
2. **Threshold definitions:** At what strike rate is a contact "concerning"? What margin threshold triggers a pricing review? These become the color-coding and alert thresholds in the UI.
3. **Industry classification quality:** The `industry` field in QB is populated on 15,124 of 15,127 customers, but how clean is it? Are there junk values, inconsistent naming, too-broad categories? The rollup is only useful if the groupings are meaningful.
4. **AM workflow:** Where in their daily workflow would AMs see the persona card? Before a call? When reviewing a quote request? When deciding pricing? This determines where the UI surfaces the data.
5. **Quote attribution edge cases:** Some quotes may have no `contact_email` or have a generic company email. What percentage of quotes have usable contact attribution? Run: `SELECT COUNT(*) FILTER (WHERE contact_email IS NOT NULL AND contact_email != '') AS attributed, COUNT(*) AS total FROM qb_quotes;`
