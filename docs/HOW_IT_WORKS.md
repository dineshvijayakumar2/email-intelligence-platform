# How It Works — Email Intelligence Platform

A plain-language guide to every capability in the Email Intelligence Platform. Describes current-state production behavior as of 2026-04-16. If something is built but not yet active, it says so.

---

## 1. The Platform at a Glance

The Email Intelligence Platform ingests emails from Outlook and Gmail mailboxes (plus file uploads), extracts contacts, companies, and engagement patterns, enriches them with QuickBase CRM data, then runs AI classification to surface actionable signals for account managers. It serves a B2B manufacturing business (Carbon8) where AMs manage customer relationships across ~271K emails and thousands of customer companies.

**Major capabilities:**

- **Email synchronization** from Outlook and Gmail via OAuth, plus MBOX/PST/OLM file uploads and Google Drive streaming
- **Contact and company extraction** via a 13-step pipeline that parses senders, recipients, domains, roles, and engagement
- **QuickBase data sync** importing customers, contacts, quotes, jobs, operations, and sales line items, then 3-pass matching to platform companies
- **AI email classification** using Claude Haiku to tag intent, urgency, sentiment, business signals, and suggested actions
- **Action signal engine** deriving 6 AM-centric signals (response urgency, deal at risk, retention risk, revenue opportunity, new relationship, account neglect) from AI + QB data with no additional AI cost
- **Strategic and daily digest generation** using a LangGraph ReAct agent with tool access for executive summaries
- **Vector search** over emails, companies, operations, and quotes using pgvector HNSW indexes with audited embeddings (OpenAI/Google, configurable via `EMBEDDING_PROVIDER`)
- **Smart Inbox** grouping classified emails by intelligence signals for AM triage
- **Customer profile pages** with engagement metrics, order history, product profiles, seasonality, and recommendations
- **Data health monitoring** with DB performance dashboards and reembed tooling
- **Thread-to-QuickBase journey linking** tracing email threads through to quotes, jobs, operations, and invoices
- **Background job system** with a dedicated worker process, heartbeat leases, and stuck-job reconciliation (partially migrated)
- **In-app notifications** via events table, notification dispatcher, and bell icon with polling (recently added, partially active)

---

## 2. How Each Capability Works

---

### 2.1 Email Synchronization

#### What it does

Brings emails into the platform from multiple sources. Users connect Outlook or Gmail via OAuth, or upload archive files (MBOX, PST, OLM) directly or from Google Drive. Live-connected mailboxes sync incrementally — only new messages since the last sync.

#### What triggers it

- **User action:** connects an OAuth account, uploads a file, or clicks "Sync" on a mailbox
- **Automatic sync:** Railway cron calls `POST /internal/jobs/gmail-sync` or `POST /internal/jobs/outlook-sync` (CRON_SECRET auth). Each endpoint checks per-mailbox intervals and only syncs mailboxes that are due. Legacy: built-in asyncio loop (disabled when `DISABLE_SYNC_LOOPS=true`)
- **Date-range fetch:** user requests a specific date range via the extraction page

#### What data it reads

- `mailboxes` table (connection config, OAuth tokens, last sync state)
- `user_integrations` table (OAuth tokens for user-level connections)
- External: Microsoft Graph API (delta queries) or Gmail API (history ID-based incremental sync)

#### What data it produces

- Inserts into `emails` table (subject, sender, recipients, body, sent_date, threading fields, folder)
- Updates `mailboxes.last_sync_at` and `connection_config` (delta link / history ID for next sync)
- Creates `processing_jobs` records to track sync progress

#### What it depends on

Nothing — this is the entry point for all data.

#### Current status

Active in production, handling real traffic. 271,432 emails across 9 mailboxes (mix of Outlook and Gmail). Both live sync and file uploads working. Sync uses dedicated cron endpoints (`/internal/jobs/gmail-sync`, `/internal/jobs/outlook-sync`) called by Railway cron. Per-mailbox interval checking prevents duplicate syncs. Legacy asyncio loops can be disabled via `DISABLE_SYNC_LOOPS=true` env var.

#### Known limitations

- OAuth tokens are stored in `mailboxes.connection_config` JSONB and `user_integrations` — two separate token stores that can drift if a user re-authenticates via a different path
- Sync runs inline when triggered by cron endpoint (not the worker process). If the API server restarts mid-sync, the sync dies silently with no retry
- Gmail incremental sync depends on history ID continuity; if Google expires the history, a full resync is needed but not automatically triggered
- No deduplication across mailboxes — if two mailboxes contain the same email (e.g., sender and recipient both connected), it appears twice
- Large file uploads (OLM 65GB+) use RemoteZip streaming but depend on stable network connection throughout

#### Verified by

Active in production — dashboard shows 271,432 total emails, 9 mailboxes with "Synced Today" timestamps. Live sync confirmed by "Outlook LIVE" and "MBOX LIVE" badges visible on dashboard.

---

### 2.2 Email Processing Pipeline (13-Step Extraction)

#### What it does

Takes raw emails and extracts business-relevant data: contacts, companies, roles, engagement scores, thread status, and communication patterns.

#### What triggers it

- User clicks "Run Extraction" on the extraction page, which calls `POST /analytics/extraction/run`
- The endpoint creates a `processing_jobs` record and runs the extraction in a FastAPI BackgroundTask

#### What data it reads

- `emails` table (raw email content, sender, recipients, CC, BCC, threading fields)
- `customer_companies`, `customer_contacts` (for deduplication and updates)
- `internal_domains`, `free_email_providers` (to exclude non-customer domains)
- `email_contact_links` (existing links to avoid re-linking)

#### What data it produces

- Inserts/updates `customer_contacts` (name, email, company, role, seniority, title)
- Inserts/updates `customer_companies` (name, domains, engagement score, email counts)
- Inserts `email_contact_links` (joins emails to contacts)
- Updates `thread_status` (thread state: active, waiting, closed, etc.)
- Updates `email_response_metrics` (response times per contact)
- Creates `extraction_jobs` records to track progress

#### What it depends on

Email Synchronization (needs raw emails in the database).

#### Current status

Active in production, handling real traffic. The 13 steps run successfully across all mailboxes. 80 completed processing jobs visible on the dashboard.

#### Known limitations

- Runs via FastAPI BackgroundTasks — if the API server restarts, the extraction job dies mid-run. The processing_jobs record will stay as "running" until manually fixed or the stuck-job reconciler catches it
- Company resolution relies on email domain matching. Free email providers (gmail.com, outlook.com) are excluded, but niche free providers may slip through
- Role classification is rule-based (regex on signatures), not AI. Accuracy depends on signature format — some contacts never have titles extracted
- Engagement scoring uses 8 factors but weights are hardcoded, not configurable per client
- Thread tracking depends on `canonical_thread_id`. Emails with no In-Reply-To or References headers start new threads even if they're part of a conversation

#### Verified by

Dashboard shows 80 completed processing jobs. Customer list shows 9 companies with data. Contacts are populated and linked.

---

### 2.3 QuickBase Data Sync

#### What it does

Imports CRM data from QuickBase — customers, contacts, quotes, jobs, operations, sales line items, and unique emails — then matches QB customers to platform-extracted companies using a 3-pass algorithm (exact name, domain root, fuzzy name at >82% similarity).

#### What triggers it

- User clicks "Sync" on the QB configuration page, calling `POST /quickbase/sync`
- Railway cron calls `POST /internal/jobs/qb-sync` (CRON_SECRET auth). Respects per-client `sync_interval_hours`: skips clients in manual mode (`sync_interval_hours=NULL`) and clients not yet due (`last_sync_at + interval > now`)
- User triggers re-match or data propagation separately

#### What data it reads

- `qb_sync_config` table (API credentials, table IDs, field mappings per client)
- External: QuickBase API (6 tables: Customers, Contacts, Quotes, Jobs, Operations, Sales Line Items + Unique Emails)
- `customer_companies` (for matching)

#### What data it produces

- Inserts/updates 7 QB cache tables: `qb_customers`, `qb_contacts`, `qb_quotes`, `qb_jobs`, `qb_operations`, `qb_sales_line_items`, `qb_unique_emails`
- Creates `qb_match_candidates` for fuzzy matches requiring review
- Enriches `customer_companies` with QB data: `qb_customer_id`, `customer_type`, `qb_tier`, `qb_total_revenue`, `days_since_last_invoice`, `open_quote_count`, `growth_pct`
- Enriches `customer_contacts` with QB data: `qb_contact_id`, `qb_quote_count`, `qb_capabilities_used`

#### What it depends on

Email Processing Pipeline (needs companies to match against). QB API credentials configured per client.

#### Current status

Active in production. Carbon8 QB config is active with App ID `buzfemk4f`. All 7 QB tables are populated. Matching and data propagation run on sync.

#### Known limitations

- QB sync runs via FastAPI BackgroundTasks (not worker). Server restart kills a running sync. Cron endpoint now respects `sync_interval_hours` per client (Option C)
- Fuzzy matches (pass 3) are flagged for manual review but there's no notification when new matches appear — users must check the review page
- QB API rate limits are not explicitly handled; high-volume syncs could hit throttling
- No incremental QB sync — every sync pulls all records from QB (though it uses upsert locally)
- `qb_sync_config` stores QB API credentials (realm hostname, user token) in the database. The user token has broad QB access — there's no per-table scoping

#### Verified by

QB data visible in admin data browser. Company profiles show QB-enriched fields (customer type, tier, revenue). QB Synced Data page shows populated tables.

---

### 2.4 AI Email Analysis

#### What it does

Classifies every email with intent, urgency, sentiment, business signals, entities (competitors, budgets, people), and a suggested AM action. Uses Claude Haiku in batches of 20 emails per API call for cost efficiency.

#### What triggers it

- User clicks "Analyse" on a mailbox, calling `POST /ai/analyze/{mailbox_id}` — creates a `processing_jobs` record with `job_type=ai_analysis` (status "pending", picked up by worker)
- User triggers backfill via `POST /ai/backfill-intent` — creates a `processing_jobs` record with `job_type=ai_backfill` (status "pending", picked up by worker)
- Re-analysis via `POST /ai/reanalyze/{mailbox_id}` runs via FastAPI BackgroundTasks (not worker)

#### What data it reads

- `emails` table (subject, body, sender, recipients, sent_date)
- `customer_contacts`, `customer_companies` (QB-enriched context: customer_type, tier, revenue, open quotes)
- `ai_prompt_config` table (editable prompt templates)
- Thread history (prior messages in conversation)

#### What data it produces

- Inserts/updates `ai_email_intelligence` (intent, urgency, sentiment, business_signal, action_bucket, entities, suggested_action, confidence scores)
- Updates `emails.processing_status` (pending → success/failed)
- Inserts `ai_usage_log` (token counts, costs per API call)
- Updates `processing_jobs` progress

#### What it depends on

Email Synchronization (emails). QB Sync (business context enriches prompts — optional but significantly improves quality).

#### Current status

Active in production. The `ai_analysis` and `ai_backfill` job types run on the dedicated worker process (one of the 5 migrated job types). Re-analysis still runs via BackgroundTasks.

#### Known limitations

- Batching 20 emails per API call means one malformed email can cause the entire batch to fail. Failed batches are retried but individual emails aren't isolated
- PII filtering is applied before sending to Claude but is regex-based — some PII patterns may slip through
- Claude Haiku's classification accuracy depends on prompt quality. Prompts are editable via AI Playground but changes affect all future analyses immediately (no A/B testing)
- Cost tracking is per-API-call, not per-email. Usage log shows aggregate token counts
- `json_repair` library is used to fix malformed LLM JSON responses — this adds resilience but means some classifications may be subtly incorrect after repair

#### Verified by

Active in production — ai_email_intelligence table has data, Smart Inbox displays classified emails with intent tags. `ai_analysis` and `ai_backfill` are registered worker handlers.

---

### 2.5 Action Signals (Bucket Engine)

#### What it does

Derives 6 actionable AM-centric signals from AI classifications and QB data using a deterministic decision tree. No additional AI calls — pure Python logic, predictable and debuggable.

#### What triggers it

Runs automatically as part of AI analysis (called after classification in the ai_analysis handler). Can also be re-run independently via `POST /ai/rebucket/{mailbox_id}`.

#### What data it reads

- `ai_email_intelligence` (intent, urgency, sentiment from AI classification)
- `customer_companies` (QB-enriched: customer_type, revenue, days_since_last_invoice, engagement_score)
- `customer_contacts` (email frequency, last contact date)

#### What data it produces

- Updates `ai_email_intelligence` with `action_bucket` (one of the 6 signals), `action_bucket_confidence`, and `lifecycle_tier`
- The 6 signals: response_urgency, deal_at_risk, retention_risk, revenue_opportunity, new_relationship, account_neglect
- Lifecycle tiers: prospect, new_customer, active_customer, at_risk, dormant, champion

#### What it depends on

AI Analysis (needs classifications). QB Sync (enrichment data drives several signals).

#### Current status

Active in production. Runs as part of every AI analysis job. Rebucket endpoint available for re-running with updated rules.

#### Known limitations

- Decision tree thresholds are hardcoded (e.g., "30+ days open quote" for deal_at_risk, "14+ days no reply" for account_neglect). Not configurable per client
- At most 2 signals per email — if an email qualifies for more, only the top 2 by confidence are kept
- Lifecycle tier assignment is deterministic but doesn't consider time-based trends (a customer who was "champion" last month and "at_risk" this month gets re-classified instantly with no smoothing)

#### Verified by

Smart Inbox displays action bucket tags. Opportunities page groups emails by signal type.

---

### 2.6 Daily and Strategic Digest Generation

#### What it does

Generates two types of summaries:

- **Daily digest:** per-mailbox summary of the day's classified emails, grouped by intent and urgency
- **Strategic digest:** executive summary (weekly/monthly) covering AM performance, customer health, pipeline status, and deals at risk. Uses a LangGraph ReAct agent with tools to drill into company details, email threads, and quote status.

#### What triggers it

- User clicks "Generate" on the Daily Digest or Strategic Digest page
- Daily digest: `POST /ai/daily-digest/{mailbox_id}` (BackgroundTasks)
- Strategic digest: `POST /ai/strategic-digest` (creates a processing_jobs record via factory with `initial_status=running`, then runs via BackgroundTasks — hybrid pattern)

#### What data it reads

- `ai_email_intelligence`, `emails` (daily digest: today's classifications)
- `customer_companies`, `qb_quotes`, `qb_jobs` (strategic: top companies by volume, pipeline data)
- `email_response_metrics` (strategic: AM efficiency, response times)
- `am_performance_snapshots` (strategic: historical AM metrics)

#### What data it produces

- `ai_daily_digests` (daily summary per mailbox per date)
- `ai_strategic_digests` (full executive summary with structured sections)
- `ai_usage_log` (token/cost tracking for the LangGraph agent calls)

#### What it depends on

AI Analysis, QB Sync, Email Processing Pipeline, Action Signals (all feed into digest context).

#### Current status

Active in production. Both daily and strategic digest generation work when triggered by user. Strategic digest uses Claude Sonnet (or Gemini 2.0 Flash as fallback). Neither runs on a schedule — both require manual trigger.

#### Known limitations

- Strategic digest runs via BackgroundTasks despite creating a processing_jobs record. If the API server restarts, the job dies but the record stays as "running"
- Strategic digest context window is ~15K tokens. For clients with many active companies, context is truncated to top 20 by email volume — smaller accounts may be omitted
- No automatic scheduling — no cron job triggers daily or weekly digest generation
- In-memory progress tracking (`_digest_progress` dict) is lost on server restart

#### Verified by

Strategic Digest and Daily Digest pages exist in the frontend. Digest generation endpoint is functional. `ai_strategic_digests` and `ai_daily_digests` tables exist in schema.

---

### 2.7 Vector Embeddings and Semantic Search

#### What it does

Embeds emails, companies, operations, and quotes into 768-dimensional vector space using a configurable embedding provider (OpenAI text-embedding-3-small or Google gemini-embedding-001, set via `EMBEDDING_PROVIDER` env var). Uses pgvector HNSW indexes for approximate nearest-neighbor search. Every embedding write stamps `embedding_model` (e.g. `openai/text-embedding-3-small-768`) and `embedded_at` for audit traceability.

#### What triggers it

- Embedding generation: user triggers reembed via the Data Health page, creating a `processing_jobs` record with `job_type=reembed` (picked up by worker)
- Search: user types a query on the Semantic Search page, which embeds the query and calls `search_emails`, `search_companies`, or `search_operations` RPCs

#### What data it reads

- `emails` (subject + body_text + sender for embedding text)
- `customer_companies` (name + industry + domains + QB tier)
- `qb_operations` (operation_name + department + machine + capabilities + QB formula tags)
- `qb_quotes` (category + customer + contact + AM + value, enriched via `qb_customers` join on `customer_key_id`)
- External: OpenAI or Google embedding API (configured via `EMBEDDING_PROVIDER` env var)

#### What data it produces

- Updates `*.embedding` (vector(768)), `*.embedding_model` (text), `*.embedded_at` (timestamptz) on all 4 tables
- HNSW indexes: managed by `BulkIndexManager` — dropped before bulk reembed, recreated after
- Partial indexes: `idx_*_embedding_model` on each table (WHERE embedding IS NOT NULL)
- Batch writes via RPCs: `batch_update_embeddings_emails/companies/operations/quotes` (migrations 090, 097)

#### What it depends on

Email Synchronization, QB Sync (for company/operation/quote data), embedding API key, `EMBEDDING_PROVIDER` env var.

#### Current status

Active in production. All prior embeddings were cleared (migration 096) due to mixed Gemini/OpenAI vector contamination — vectors from different models occupy incompatible semantic spaces despite identical 768 dimensions. Clean reembed pending with audit columns. HNSW indexes dropped pre-reembed; `BulkIndexManager` recreates them post-reembed.

#### Known limitations

- Embedding is not automatic — new emails don't get embedded until a user triggers reembed. There's no automatic embedding on email arrival
- HNSW index rebuild requires `maintenance_work_mem=256MB` — if the index gets corrupted or needs rebuilding, it requires a manual setting change on Supabase
- Vectors from different providers (OpenAI vs Google) cannot coexist — same 768 dims but different semantic spaces. `embedding_model` audit column prevents silent contamination
- BM25 full-text search (migration 057) and hybrid retrieval (BM25 + vector + RRF fusion) are built but the hybrid retriever's usage may vary by endpoint

#### Verified by

Semantic Search page exists in frontend. `search_emails`, `search_companies`, `search_operations` RPCs defined in migration 037. Batch update RPCs with audit params in migration 097. `reembed` handler registered in worker. 13 unit tests in `backend/tests/test_vector_service.py`.

---

### 2.8 Smart Inbox

#### What it does

When an account manager opens the Smart Inbox, they see their recent emails grouped by intelligence signal — action required, deal at risk, new relationships, etc. Each email shows the AI-classified intent, urgency badge, sentiment, and suggested action. Users can filter by signal type, urgency, and date range.

#### What triggers it

User navigates to `/insights/inbox`. The page fetches intelligence data from `GET /ai/intelligence/{mailbox_id}` with 12 filter dimensions.

#### What data it reads

- `ai_email_intelligence` (intent, urgency, sentiment, action_bucket, business_signal)
- `emails` (subject, sender, sent_date, is_outbound)
- Joins across both tables filtered by the user's accessible mailboxes

#### What data it produces

Read-only — displays data, doesn't write.

#### What it depends on

AI Analysis (needs classifications), Action Signals (needs bucket assignments), Email Synchronization (needs emails).

#### Current status

Active in production. The page renders classified emails with filtering. Intelligence stats endpoint provides summary counts.

#### Known limitations

- Performance degrades with large result sets. Pagination is implemented but initial load fetches intelligence stats for the entire mailbox
- No real-time updates — if AI analysis completes while the page is open, the user must manually refresh
- Filter state is not persisted in the URL — refreshing the page resets all filters

#### Verified by

Frontend page exists at `frontend/src/pages/intelligence/inbox.tsx`. Backend endpoint serves data from `ai_email_intelligence` joined with `emails`.

---

### 2.9 Customer Profile Pages

#### What it does

Each company has a detail page showing engagement metrics, contact list, order history (from QB), product profile, AI-generated recommendations, seasonality patterns, and capability rhythm analysis. Contact detail pages show individual communication history and response patterns.

#### What triggers it

User navigates to `/customers/:id` (company detail) or clicks a contact to see `/analytics/contact-detail/:id`.

#### What data it reads

- `customer_companies` (engagement score, QB enrichment, email domains)
- `customer_contacts` (linked to company, role, email counts, QB data)
- `qb_quotes`, `qb_jobs`, `qb_operations`, `qb_sales_line_items` (order history, product profile)
- `customer_recommendations`, `product_affinities` (AI recommendations)
- `email_response_metrics`, `thread_status` (communication patterns)

#### What data it produces

Read-only for the detail pages. Refresh engagement button calls `POST /customers/{id}/refresh-engagement` which recalculates and writes engagement metrics.

#### What it depends on

Email Processing Pipeline, QB Sync, AI Analysis (for some enrichment).

#### Current status

Active in production. Company list, company detail, contact list, and contact detail pages are all functional. Seasonality engine, capability rhythm, and recommendations are built and deployed.

**Sales Opportunities** (promoted to top of company profile, May 2026):

- **Cross-contact capability gaps (Level 1):** For each contact, shows which `qb_capability_tag` categories the company uses that this contact hasn't been on a quote for. Output: `already_buys` (e.g. Flat Sheets, Wide Format) + `untapped_capabilities` (e.g. Hard Cover Books, Specialty Finishing). Aggregated from raw `qb_operations` → `qb_capability_tag`, not the 48+ individual operation names. Excludes shared mailboxes, automated contacts, mailing lists. Flags domain mismatches (contact email domain ≠ company's known domains).
- **Revenue concentration risk:** Triggered when company revenue > $100K but ≤2 contacts are producing orders (out of 3+ total). Queries `contact_persona` view. Shows top revenue contacts with % attribution and unengaged contacts.
- **Buyer decay risk:** Triggered when the top revenue contact's persona is `inactive_buyer`. Same data source as concentration risk but escalated severity.
- **Portfolio-wide scan:** `GET /customers/portfolio-insights` scans all companies for a client, returns list sorted by revenue desc.

**Company profile layout** (reorganized May 2026): action-first flow with semantic widget pairs — Business Data → Sales Opportunities → Key Contacts → Performance (strike rate + seasonality) → Capabilities (rhythm + contact capabilities) → Deep Dive (product profile + AI insights) → Order History.

#### Known limitations

- Recommendation engine (Level 1 cross-contact gaps, Level 2 market basket analysis) runs on-demand, not pre-computed. First load of a company with many orders may be slow
- Seasonality analysis requires at least 2 years of QB data to produce multi-year patterns. New clients will see limited data
- Engagement score refresh is per-company. No bulk refresh for all companies at once
- Revenue concentration thresholds are hardcoded ($100K, ≤2 contacts, 3+ total). May need tuning per client

#### Verified by

Customer pages exist in frontend. Company detail has sections for overview, contacts, sales opportunities, order history, product profile, recommendations, seasonality, and AI insights. Dashboard shows company count from `customer_companies` table.

---

### 2.10 Data Health Monitoring

#### What it does

Provides a dashboard showing database performance metrics, embedding coverage stats, index health, and tools to trigger reembed operations. Shows IO budget, query performance, and table sizes.

#### What triggers it

User navigates to `/manage/data-health`. The page calls multiple RPCs: `get_db_performance_stats`, `get_vector_stats`, `get_io_budget_stats`, etc.

#### What data it reads

- PostgreSQL system catalogs via RPCs (pg_stat_user_tables, pg_stat_user_indexes, pg_total_relation_size)
- `emails`, `customer_companies`, `qb_operations` (embedding coverage counts)
- `processing_jobs` (active reembed jobs)

#### What data it produces

Read-only display. Reembed trigger creates `processing_jobs` records.

#### What it depends on

Database RPCs (migrations 064-067, 070, 075). Worker process (for reembed execution).

#### Current status

Active in production. DB performance dashboard built during IO Budget phase. RPC functions deployed.

#### Known limitations

- Performance RPCs use `exec_sql` which executes arbitrary SQL — this is a security concern (see Section 5)
- Stats are point-in-time snapshots, not time-series. No historical tracking of DB performance
- Some RPCs may timeout on very large tables if Supabase has aggressive statement timeouts

#### Verified by

Data Health page exists at `frontend/src/pages/manage/data-health.tsx`. RPCs defined in migrations 064-067, 070, 075.

---

### 2.11 Thread-to-QuickBase Journey Linking

#### What it does

Traces an email thread through to its QuickBase quote, job, operations, and invoices — showing the complete customer journey from first email to final invoice. Two extraction sources feed links:

1. **Regex extraction** — scans email subjects and bodies for QB reference patterns (Q20334, J460037, etc.), validates against actual QB records, writes links with `source='regex'` and `confidence=1.0`
2. **AI extraction** — during email classification, the AI prompt extracts QB references from email content, stored in `ai_email_intelligence.extracted_references`. A post-classification linking step validates these against QB records and writes links with `source='ai'` and `confidence=0.9`

#### What triggers it

- Manual: user clicks "Link" on a thread detail page, calling `POST /journey/links`
- Automated (regex): a `reference_extraction` job scans all emails for a client. Registered in the worker, runs when created
- Automated (AI): during any `ai_analysis` job, the post-classification step in the worker handler validates AI-extracted refs and writes `thread_qb_links`
- On-demand full: `python scripts/db/_link_ai_refs_full.py [mailbox_id] [--lookback N]` — runs against all classified emails, no 7-day cutoff
- Journey viewing: `GET /journey/threads/{thread_id}` assembles the full chain

#### How AI extraction works (detailed flow)

The AI extraction path has three phases: **Prompt → Store → Link**. Classification and linking are decoupled — the AI extracts refs during classification, and a separate linking step validates and writes them.

##### Phase 1: AI prompt extracts references during classification

**File:** `backend/src/services/ai_email_analyzer.py` (SYSTEM_PROMPT, lines ~196-206)

The classification prompt includes a `QB REFERENCE EXTRACTION` instruction block:

```
"qb_references": array of {"type": "quote" or "job", "number": string}

QB REFERENCE EXTRACTION:
- Look for QuickBase reference numbers in email subject or body.
- Quote numbers: Q followed by 4-6 digits only (e.g., Q20334, Q123456). 
  Do NOT extract: Q with 1-3 digits (Q1, Q100), Q with 7+ digits (Q1234567), 
  or the placeholder Q12345.
- Job numbers: J followed by 5-6 digits only (e.g., J460037, J123456).
  Do NOT extract: J with 1-4 digits, J with 7+ digits, or the placeholder J123456.
- Valid quote range is roughly Q5 to Q800000. Anything above is not a real quote.
- Valid job range is roughly J32 to J500000. Anything above is not a real job.
- Return just the prefix + numeric part. E.g., "Quote #20334" → {"type": "quote", "number": "Q20334"}.
- If no valid references found, return empty array.
- Only extract references explicitly present — do not guess or infer.
```

The AI model (Claude Haiku) returns `qb_references` as part of the classification JSON response. The response is parsed into an `EmailAnalysisResult` Pydantic model which has `qb_references: list[dict] = []`.

##### Phase 2: References stored in ai_email_intelligence

**File:** `backend/src/services/ai_email_analyzer.py` (post_process_classification)

After classification, `post_process_classification()` writes the extracted refs to the DB:

```python
"extracted_references": [ref for ref in result.qb_references] if result.qb_references else None
```

This is stored as a JSONB column on `ai_email_intelligence`. Format:

```json
[
  {"type": "quote", "number": "Q675200"},
  {"type": "job", "number": "J461400"}
]
```

At this point, refs are unvalidated raw extractions — they may or may not correspond to real QB records.

##### Phase 3: Linking step validates and writes thread_qb_links

**File:** `backend/src/workers/handlers/ai_analysis.py` (`_link_ai_extracted_refs`)

This runs as the final step of the `ai_analysis` worker handler, after classification and bucket engine complete. The algorithm:

1. **Scope selection** — Fetch `ai_email_intelligence` rows where:
   
   - `mailbox_id` matches
   - `processing_status = 'completed'`
   - `extracted_references IS NOT NULL`
   - `processed_at >= (now - 7 days)` ← pipeline mode only; full script omits this

2. **Thread resolution** — For each email_id, look up `emails.canonical_thread_id`. Emails without a canonical thread are skipped (cannot create a thread-level link).

3. **Normalization** — For each extracted reference:
   
   - Strip all non-digit characters: `re.sub(r'[^0-9]', '', ref_number)`
   - Add prefix: `"Q" + digits` for quotes, `"J" + digits` for jobs
   - Collect all unique quote refs and job refs across the entire batch

4. **Bulk validation** — In chunks of 500:
   
   - Query `qb_quotes` for matching `quote_no` (client-scoped) → get `qb_record_id`
   - Query `qb_jobs` for matching `job_no` (client-scoped) → get `qb_record_id`
   - Build lookup dicts: `valid_quotes[canonical_ref] → qb_record_id`

5. **Matching** — For each thread's refs, check against the valid dicts. Only refs that exist in QB are kept.

6. **Upsert** — For validated refs, call `_upsert_links()` which writes to `thread_qb_links`:
   
   ```
   {client_id, canonical_thread_id, link_type, qb_record_id, qb_reference, confidence: 0.9, source: "ai", verified: false}
   ```
   
   Upsert key: `(client_id, canonical_thread_id, link_type, qb_record_id)` — duplicates are skipped.

#### Pipeline mode vs full mode

| Aspect   | Pipeline (automatic)                           | Full (on-demand script)                                     |
| -------- | ---------------------------------------------- | ----------------------------------------------------------- |
| File     | `ai_analysis.py` → `_link_ai_extracted_refs`   | `scripts/db/_link_ai_refs_full.py`                          |
| Scope    | Last 7 days of `processed_at`                  | All time (or `--lookback N` days)                           |
| Trigger  | Every `ai_analysis` job completion             | Manual execution                                            |
| Use case | Keep links current for newly classified emails | Backfill links for historical emails, re-link after QB sync |

#### What data it reads

- `emails` (subject, body_text for regex extraction; canonical_thread_id for grouping)
- `ai_email_intelligence` (extracted_references JSONB for AI-sourced refs)
- `qb_quotes`, `qb_jobs` (to validate extracted reference numbers against real records)
- `thread_qb_links` (existing links — upsert avoids duplicates)
- `qb_operations`, `qb_sales_line_items`, `qb_job_status_log` (for full journey assembly via API)

#### What data it produces

- Inserts/updates `thread_qb_links` (canonical_thread_id → qb_record_id, link_type: quote or job, source: regex/ai/manual, confidence: 1.0/0.9)
- Updates `thread_status.qb_link_count` (denormalized count, synced on every create/delete)
- Stores `extracted_references` JSONB in `ai_email_intelligence` (from AI classification)

#### What it depends on

Email Synchronization (emails with thread IDs), QB Sync (quote and job records to validate against), Canonical thread resolution (migration 055). AI extraction depends on the classification prompt including QB reference instructions (stored in `ai_prompt_config` table, prompt_key `email_analysis_user`).

#### Current status

Built and deployed. Both regex and AI extraction paths are functional. The `reference_extraction` handler is registered in the worker. AI extraction runs automatically as part of the `ai_analysis` worker handler (post-classification linking step). Journey API endpoints are functional. Manual linking works.

#### Diagnostic findings (May 2026, Carbon8)

Analysis of 15,057 AI-extracted references across all mailboxes:

| Category             | Count  | %     | Description                                                                                                                                   |
| -------------------- | ------ | ----- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| Matched              | 10,344 | 68.7% | Validated against qb_quotes/qb_jobs — real links                                                                                              |
| Hallucinated         | 1,253  | 8.3%  | Numbers above QB's actual max range (quotes >Q713145, jobs >J461400). AI misidentified dates, phone numbers, or other long numbers as QB refs |
| Real gaps (in range) | 3,460  | 23.0% | Within valid QB number ranges but record not found. Likely: deleted quotes, quotes from other QB apps, or genuine data gaps                   |

**Improvement paths:**

- Add valid QB number ranges to the classification prompt to reduce hallucination (8.3% → ~0%)
- Re-run full link script after QB sync updates to convert some "real gaps" to matches
- Tighter prompt patterns (require exactly 5-6 digits for quotes, 5-7 for jobs)

#### Known limitations

- AI model sometimes extracts dates/phone numbers as QB references (8.3% hallucination rate)
- Reference extraction prompt patterns are in the system prompt AND in `ai_prompt_config` DB rows — both need updating for prompt changes
- Pipeline mode only processes 7-day window — newly synced QB records won't retroactively link old emails without running the full script
- Regex patterns for QB references are hardcoded. If QB numbering format changes, patterns must be updated in code
- AI-extracted refs have `confidence=0.9` (not verified by human) — the UI should distinguish these from regex/manual links
- Journey assembly makes multiple sequential Supabase queries (links → quotes → jobs → operations → line items → status log). For threads linked to many jobs, this can be slow

#### Verified by

`reference_extraction` handler exists in `backend/src/workers/handlers/reference_extraction.py`. AI linking step in `backend/src/workers/handlers/ai_analysis.py` (`_link_ai_extracted_refs`). Full link script at `scripts/db/_link_ai_refs_full.py`. Journey router exists with 5 endpoints. `thread_qb_links` table defined in migration 086 (includes `extracted_references` column on `ai_email_intelligence`). DB prompt `email_analysis_user` updated to v1.3 with QB reference extraction instructions.

---

### 2.12 Background Job System

#### What it does

Runs long tasks (AI analysis, reembed, reference extraction, notification dispatch) in a background worker process so the API stays responsive. Jobs are created as `processing_jobs` records, then claimed by the worker using database-level locks.

#### What triggers it

- Job creation: various API endpoints insert a `processing_jobs` row with `status=pending`
- Job claiming: the worker process polls every 2 seconds, calling the `claim_next_job` RPC (SELECT FOR UPDATE SKIP LOCKED)
- Heartbeat: the worker extends the lease every 30 seconds via `heartbeat_job` RPC
- Stuck-job recovery: a reconciler loop runs every 10 minutes inside the worker, calling `reconcile_stuck_jobs` RPC. There's also a belt-and-suspenders HTTP endpoint at `POST /internal/jobs/stuck-reconciler`

#### What data it reads

- `processing_jobs` table (job queue)

#### What data it produces

- Updates `processing_jobs` (status transitions: pending → running → completed/failed/stopped/interrupted)
- Emits events to `events` table on job lifecycle transitions (started, completed, failed, stopped)

#### What it depends on

Database RPCs: `claim_next_job`, `heartbeat_job`, `reconcile_stuck_jobs` (migration 083-084). Supabase service key for direct DB access.

#### Current status

Built and deployed, partial traffic. The worker process is defined in `railway.toml` as a separate service (`job-worker`, 2 replicas). The `Procfile` only has the `web` process — whether the worker is actually running as a separate Railway service needs verification.

**5 job types on the worker path:**

- `ai_analysis` — AI classification of unanalyzed emails
- `ai_backfill` — Intent backfill across multiple mailboxes
- `reembed` — Vector embedding regeneration
- `reference_extraction` — QB reference scanning
- `notification_dispatch` — Event-to-notification routing

**Job types still on FastAPI BackgroundTasks (not worker):**

- Email sync (Gmail, Outlook — via cron endpoints or legacy asyncio loop)
- 13-step extraction pipeline
- Thread resolution and recompute
- Contact email count backfill
- AI re-analysis and rebucket
- Strategic and daily digest generation (strategic uses hybrid: factory record + BackgroundTasks execution)
- QB sync, re-match, and data propagation
- Intelligence config reclassify
- Email rules apply
- Mailbox reprocessing and restart (hybrid: factory record + BackgroundTasks execution)

#### Known limitations

- Only 5 of ~20 job types run on the worker. The rest use FastAPI BackgroundTasks and die on server restart with no retry
- Hybrid callsites (factory creates a processing_jobs record but BackgroundTasks runs the actual work) create confusing state: the record exists and may be claimed by the worker, but the worker has no handler for that job_type — it will log "No handler registered" and mark it failed
- The worker polls every 2 seconds. Under no load, this means ~43,200 Supabase RPC calls per day per worker instance (2 replicas = ~86K calls)
- Single-flight protection is per `(job_type, mailbox_id)` via partial unique index. Jobs without a mailbox_id (e.g., analytics_rollup_daily) use a different dedup key
- The `Procfile` only defines `web`. If Railway uses the Procfile rather than `railway.toml`, the worker won't start

#### Verified by

Worker code exists at `backend/src/workers/job_runner.py`. Handler registry at `backend/src/workers/handlers/__init__.py` has 5 handlers. `railway.toml` defines a `job-worker` service. RPCs defined in migrations 083-084. Whether the worker is actually running in production requires checking Railway dashboard or querying `processing_jobs` for rows with `worker_id` populated.

---

### 2.13 Events and Notifications

#### What it does

Delivers in-app alerts to users when things happen (jobs complete, fail, etc.). The system emits events on job lifecycle transitions, a notification dispatcher reads undispatched events and creates notification records for the right recipients, and a bell icon in the header shows unread count.

#### What triggers it

- Event emission: the job runner calls `emit_job_event()` on job.started, job.completed, job.failed, job.stopped
- Notification dispatch: external cron calls `POST /internal/jobs/notification-dispatch` every 2 minutes (requires `CRON_SECRET`), which creates a `notification_dispatch` processing job for the worker to claim
- Bell icon: polls `GET /notifications/unread-count` every 30 seconds

#### What data it reads

- `events` table (undispatched events)
- `user_profiles` (admin role check), `user_client_assignments` (client-scoped recipient resolution)
- `notifications` table (for listing and marking read)

#### What data it produces

- `events` table (event rows with type, payload, source)
- `notifications` table (per-recipient records with title, body, status, channel)
- Updates `events.dispatched_at` after processing

#### What it depends on

Background Job System (emits events). Worker process (for notification_dispatch handler).

#### Current status

Built and deployed, partially active. Events are emitted whenever worker jobs run (the 5 migrated job types). The notification_dispatch handler exists and is registered. A cron endpoint (`POST /internal/jobs/notification-dispatch`) is available for automated dispatch every 2 minutes. However:

- Events are only emitted by jobs running on the **worker** (5 types). BackgroundTasks jobs don't emit events
- The cron endpoint exists but requires external cron (cron-job.org or Railway cron) to be configured and calling it — see `docs/CRON_SETUP.md`
- The bell icon polls for notifications via HTTP. WebSocket infrastructure exists but notifications use polling, not push
- If the worker is not running, no events are emitted and no notifications are dispatched

#### Known limitations

- Only 4 event types exist: job.started, job.completed, job.failed, job.stopped. No events for email arrival, new contact discovery, QB sync completion, or action signal detection
- Notification dispatch depends on external cron calling the endpoint every 2 minutes — if cron is not configured, events pile up with `dispatched_at=NULL`
- Recipient resolution is basic: admins see all events, assigned users see their client's events. No per-user notification preferences or muting
- No email or Slack delivery — in-app only (by design for Phase A)
- Bell icon polls every 30 seconds. In-app notifications may be up to 30 seconds stale

#### Verified by

`notification_dispatch` handler at `backend/src/workers/handlers/notification_dispatch.py`. Notification API at `backend/src/routers/notifications.py`. NotificationBell component at `frontend/src/components/NotificationBell.tsx`. `events` and `notifications` tables defined in migration 085. Whether events actually exist in production depends on whether the worker is running.

---

### 2.14 AI Insights Engine (Per-Entity Analysis)

#### What it does

On-demand AI analysis for companies, contacts, and threads. When the user clicks "Summarize this page" on a company profile, the engine gathers context from multiple data sources, sends it to an LLM, and returns a structured insight with a `strategic_summary` narrative plus detailed observations and actions.

#### What triggers it

User clicks "Summarize this page" button on company/contact/thread detail pages. No auto-trigger (cost control). Cached 24h — subsequent requests return the cached result unless `force=true`.

- `GET /v1/ai/insights/company/{company_id}?force=false&client_id=...`
- `GET /v1/ai/insights/contact/{contact_id}?force=false&client_id=...`
- `GET /v1/ai/insights/thread/{thread_id}?force=false`

#### What data it reads (company insights)

The context sent to the LLM is assembled from 5 sources:

1. **Company profile:** `customer_companies` (name, type, tier, engagement score, email counts, QB financials). Revenue figures are labeled as "invoiced to customer" (not the customer's own revenue).
2. **Active threads:** top 5 from `thread_status` by recency (subject, status, message count).
3. **AI signals:** last 20 classified emails via `emails` → `ai_email_intelligence` (bucket distribution).
4. **Strike rate:** from `CustomerAnalyticsService` — overall conversion %, per-contact breakdown, year-over-year trend.
5. **Seasonality:** from `CustomerAnalyticsService` — peak/trough months, approaching outreach windows, YTD comparison with prior year.
6. **Sales opportunities:** from `RecommendationEngine` — revenue concentration/buyer decay risk (top contacts, % attribution), capability gaps per contact (already_buys + untapped at `qb_capability_tag` level), related product affinities.

All data sources are fault-tolerant — if any fails, it's skipped with a debug log and the remaining context is sent.

#### What data it produces

Returns structured JSON:
- `strategic_summary` — 3-4 sentence narrative synthesizing the most important trends across all data sources. Framed from the account manager's perspective (revenue = what we bill this customer).
- `health_summary` — 2-3 sentence relationship assessment
- `revenue_risk` — low/medium/high/unknown
- `engagement_trend` — improving/stable/declining/unknown
- `key_observations[]` — bullet points
- `recommended_actions[]` — actionable next steps

Cached in `relationship_context_cache.ai_signals_summary._ai_insight` (24h TTL for companies).

#### What it depends on

AI Analysis (signals), QB Sync (financial data), Customer Analytics Service (strike rate, seasonality), Recommendation Engine (revenue risk, capability gaps), Contact Persona views (buyer classification).

#### Current status

Active in production. Company, contact, and thread insights all functional. Prompt customizable per client via `ai_prompt_config` table (key: `insight_company`). Uses `entity_insights` task model (typically Claude Haiku or Gemini Flash). Migration 103 updated prompt to request `strategic_summary` and clarify revenue framing.

#### Known limitations

- Context gathering makes 6-10 Supabase queries per company insight — adds ~2-3s latency on top of LLM call
- Contact and thread insights don't use the enriched context (no strike rate/seasonality for contacts yet)
- Cache is per-company only — contact and thread insights have a simpler cache path
- `strategic_summary` quality depends on data availability: companies without QB data or seasonality history produce thinner summaries

#### Verified by

Backend: `backend/src/services/ai_insights_engine.py`. Frontend: `frontend/src/components/AIInsightsCard.tsx`. Types: `frontend/src/types/strategic-digest.ts` (`AIInsight` interface). Endpoint: `backend/src/routers/ai.py` (lines 1452-1470). Prompt config: `ai_prompt_config` rows for `insight_company` (global + per-client). Migration 103: prompt text update.

---

### 2.N Contact Intelligence (Persona Views)

#### What it does

Aggregates contact-level data from three dimensions — QuickBase quote/job history, email engagement metrics, and company enrichment — into a unified "persona" view for AM-facing intelligence. Each contact gets a persona classification (champion, active_relationship, prospect, inactive_buyer, dormant, unknown) and an engagement score (0-100) derived from email velocity, recency, and quote activity.

#### How it works

Five SQL views built in migration 088, refined in migration 101:

1. **`contact_quote_metrics`** (VIEW) — per-contact quote/job aggregates. Joins `customer_contacts.email_address → qb_quotes.contact_email → qb_jobs.quote_no`. Computes strike rate (accepted/total), total quote value, average margin, capability count.
2. **`contact_email_metrics`** (MATERIALIZED VIEW) — per-contact email engagement. Joins `email_contact_links → emails → email_response_metrics`. Computes total/inbound/outbound counts, unique threads, average response time, velocity (30d/90d), recency. Refreshed via `refresh_contact_email_metrics()` RPC.
3. **`contact_persona`** (VIEW) — the unified persona combining identity, quote metrics, email metrics, contact_type, classification, and engagement score. Includes `contact_type` column from `customer_contacts` for frontend filtering. Classification is a CASE expression with 8 categories (see below); engagement score is a weighted composite (30% velocity + 30% recency + 40% quote activity).
4. **`company_contact_summary`** (VIEW) — per-company rollup of persona counts (person contacts only), strike rate, total quote value, warm leads count.
5. **`industry_benchmarks`** (VIEW) — per-industry averages for benchmarking (requires ≥ 3 person-type contacts per industry, excludes shared/internal).

#### Persona classification rules (migration 101)

Non-person contacts (`contact_type != 'person'`) are classified as `shared_mailbox`. Person contacts are classified into 7 buckets:

- **champion** — strike rate ≥ 0.3 with ≥ 5 quotes, OR ≥ 10 accepted quotes, OR ≥ $50K total job value
- **active_buyer** — has conversions (accepted quotes/jobs) AND recent email activity (≤ 90 days)
- **active_relationship** — has quotes but no conversions yet
- **warm_lead** — engaged (email activity) but no quotes at all
- **prospect** — low engagement, no quotes
- **inactive_buyer** — has conversions but no recent activity (> 90 days)
- **dormant** — no email activity in 180+ days

#### What triggers it

- The materialized view (`contact_email_metrics`) is refreshed by external cron calling `POST /api/internal/jobs/refresh-persona-metrics` (daily at 03:00 UTC recommended) and after QB sync completes.
- The regular views read live from base tables on every query — no staleness.

#### Dependencies

`customer_contacts`, `customer_companies`, `qb_quotes`, `qb_jobs`, `email_contact_links`, `emails`, `email_response_metrics`. All must be populated by prior pipeline stages (extraction + QB sync).

#### API endpoints

- `GET /api/contacts-intelligence/{contact_id}/persona` — full persona for one contact
- `GET /api/contacts-intelligence/company/{company_id}/summary` — company rollup
- `GET /api/contacts-intelligence/company/{company_id}/contacts` — paginated contact list with persona data
- `GET /api/contacts-intelligence/industry/{industry}/benchmarks` — industry averages
- `GET /api/contacts-intelligence/industries` — all accessible industry benchmarks

All endpoints enforce cross-tenant isolation by deriving accessible client_ids from the user's mailbox assignments.

#### Frontend UI

**Contact profile page** (`/customers/contacts/:contactId`) shows two intelligence cards below the KPI strip:

- **PersonaCard** — persona classification badge (champion / active / prospect / inactive buyer / dormant), engagement score bar (0-100), email velocity 30d/90d, quote count + strike rate, days since last email. Returns null (hidden) if no persona data.
- **DealActivityCard** — thread-to-deal funnel: linked threads → quotes → converted jobs. Shows open pipeline value, converted value, job revenue. Lists the 5 most recent thread_qb_links with source badges (regex/ai/manual). Returns null if no threads.

**Contacts list page** (`/customers/contacts`) columns and filters:

- Columns: Contact (name + email), Company (hidden in company drilldown), Persona (PersonaBadge), Engagement (score), Sent, Recv, Quotes (count), Last Contact
- Filters: search (name/email), Lifecycle dropdown (Active/Prospect/New/Dormant/At Risk — maps to QB `customer_type`), QB Linked checkbox
- Persona classification fetched via batch lookup from `contact_persona` view (500 IDs per batch)
- All columns are sortable (server-side).

**Threads list page** (`/customers/threads`) columns and filters:

- Columns: Subject, Contact, Company, Status (badge), Intent (badge), QB Links (quote/job refs), Emails, Last Email, Days
- Filters: search (subject), Status dropdown (Active/Needs Attention/Awaiting/Ongoing/Overdue/Complete/Dropped), Intent dropdown (Urgent/Revenue Opp/Escalation/Closing/Informational), QB Linked checkbox
- All filters are server-side: status, intent, has_qb_links, search. QB Linked uses `.in_()` (not `.or_()`) to avoid supabase-py filter overwrite.
- QB Links column is sortable via denormalized `qb_link_count` on `thread_status` (migration 094). Count kept in sync by application code in journey.py and reference_extractor.py.

**Thread Journey panel** (shown in email thread drilldown):

- Left accent border: primary color when links exist, subtle when empty
- Deduplicates links by `qb_reference` + `link_type`, keeping the most authoritative (verified manual > verified AI > unverified regex). Dedup runs both server-side (backend) and client-side (defense in depth).
- Each link shows: type badge (Quote/Job), QB reference, verified/unverified status, source badge (manual/ai/regex), date. Hover reveals delete button.
- Expandable "QB Details" section: Quotes (quote_no, contact, amount, category, dates), Jobs (job_no, status, dates), Operations, Invoices, Status Timeline. Collapses to reduce clutter.

**Company profile contacts section** (`/customers/:id`):

- Inline contacts table on company detail page showing up to 10 contacts sorted by engagement score
- Columns: Contact (name + email), Persona (PersonaBadge), Score, Sent, Recv, Quotes, Last Contact
- Data sourced from `contact_persona` view via `GET /contacts-intelligence/company/{company_id}/contacts`
- "View all N contacts" link navigates to contacts list filtered by company_id

#### Current status

Data layer built (migrations 088 + 100 + 101). Frontend UI built (PersonaCard, DealActivityCard, company profile contacts section, unified contacts list with PersonaBadge). Deployed to production.

#### Known limitations

- `contact_email_metrics` is a materialized view — data is stale between refreshes (up to 24 hours for email metrics)
- Industry benchmarks require ≥ 3 contacts per industry to avoid noisy averages
- Persona classification thresholds are static CASE expressions — not ML-trained
- Contact list Type filter uses client-side prefix matching on paginated data — contacts not in the current page won't be filtered. For exact counts, the backend would need a native `qb_customer_type` filter parameter.

#### Verified by

Migrations `088_contact_persona_views.sql`, `100_contact_dates_and_enriched_rpc.sql`, `101_fix_persona_classification.sql`. API at `backend/src/routers/contacts_intelligence.py`. Batch persona lookup in `backend/src/routers/analytics.py` (contacts endpoint). Refresh endpoint at `backend/src/routers/internal_jobs.py` (`/refresh-persona-metrics`). Frontend: `PersonaBadge.tsx`, `PersonaCard.tsx`, `DealActivityCard.tsx`, `contact-detail.tsx`, `contacts.tsx`, `company-detail.tsx`, `threads.tsx`, `ThreadJourneyPanel.tsx`.

---

## 3. How the Pieces Fit Together

### The email lifecycle

When a new email arrives via Outlook live sync, the Outlook sync service fetches it via Microsoft Graph's delta query, parses it into the platform schema, and inserts it into the `emails` table with `processing_status='pending'`. The email now exists in the database but has no contacts, no company link, no AI classification, and no embedding.

After sync completes, an `email_pipeline` job is created. The pipeline runs 10 stages in this order:

1. **ai_classify** — Batches unanalyzed emails to Claude Haiku with QB-enriched business context, writes classifications to `ai_email_intelligence`. Uses batch upserts (50 records per call) instead of per-row writes
2. **bucket_engine** — Assigns action signals (response_urgency, deal_at_risk, etc.) based on AI classifications
3. **extract_and_link** — 13-step extraction: contacts, companies, roles, email linking. In incremental mode, only processes emails where `extracted_at IS NULL` (skips already-extracted emails). After step 9 completes, stamps `extracted_at` on processed emails. QB enrichment (step 6 sub-step) uses SQL `UPDATE...FROM` joins instead of per-row HTTP calls. Company stats update uses SQL `UPDATE...FROM VALUES` for batch efficiency
4. **assign_threads** — Assigns `canonical_thread_id` to new emails
5. **evaluate_threads** — Updates thread status for affected threads
6. **refresh_counts** — Updates email counts on contacts and companies
7. **embed_emails** — Generates vector embeddings for new emails
8. **entity_aggregation** — Aggregates entity data across emails
9. **link_ai_refs** — Links AI-extracted references to QB records. Scoped to emails classified in the last 7 days (not entire mailbox history). Validates all refs in bulk (1-2 queries) instead of per-row
10. **evaluate_threads_final** — Final thread status pass after all data is linked

Classification runs first (stages 1-2) because it has no dependency on extraction and is fast (~2 min per batch). This ensures new emails get classified even if the heavier extraction step times out. For on-demand full reference linking across the entire mailbox history, use `scripts/db/_link_ai_refs_full.py` (supports `--lookback N` for custom windows).

### The QB enrichment path

QB sync runs independently of email processing. When triggered, it fetches all records from 7 QB tables and upserts them locally. Then the 3-pass matching algorithm runs: exact company name match, domain root match, fuzzy name match. Matched companies get enriched with QB metadata (customer type, tier, revenue, invoice recency). This enrichment is then available to the AI analyzer — when classifying emails, the prompt includes "this customer is a Level 3 Key Account with $X revenue and an open quote" which dramatically improves classification quality.

### The job and worker flow

Jobs get created in two ways today:

1. **Factory path** (`create_job` in `services/jobs/factory.py`): inserts a `processing_jobs` row with `status=pending`. The worker polls for these and claims them. Used by: ai_analysis, ai_backfill, reembed, reference_extraction, and a few hybrid callsites.
2. **Direct BackgroundTasks path**: the API endpoint inserts a processing_jobs row for tracking, then immediately starts execution in a FastAPI BackgroundTask. The worker never touches these. Used by: email sync, extraction, QB sync, digests, and most other job types.

The worker claims jobs via `claim_next_job`, an RPC that does `SELECT ... FROM processing_jobs WHERE status='pending' ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1`. This means only one worker gets each job, even with 2 replicas. The worker sets `status='running'`, populates `worker_id` and `lease_expires_at`, then starts the handler with a parallel heartbeat task that calls `heartbeat_job` every 30 seconds to extend the lease.

If a worker crashes, its heartbeat stops, and the lease expires. Every 10 minutes, each worker runs the `reconcile_stuck_jobs` RPC which finds jobs with expired leases and marks them as `interrupted`. There's also a belt-and-suspenders HTTP endpoint (`POST /internal/jobs/stuck-reconciler`) that external cron can call.

### The event-to-notification path

When a worker job transitions state (started, completed, failed, stopped), the job runner calls `emit_job_event()` which inserts a row into the `events` table with `dispatched_at=NULL`. The notification_dispatch handler (when triggered) reads undispatched events, resolves recipients (admins + users assigned to the event's client), creates `notifications` rows, and marks events as dispatched. The frontend's NotificationBell component polls `GET /notifications/unread-count` every 30 seconds and displays the count badge. Currently, this chain only fires for the 5 worker job types, and only if someone triggers a notification_dispatch job.

### What to check when something breaks

- **Smart Inbox not updating after sync:** Check that email sync completed (look at `mailboxes.last_sync_at`). Then check that AI analysis has been run (look at `ai_email_intelligence` for the new emails). Then check that bucket engine ran (look at `action_bucket` column).
- **Company showing no QB data:** Check `qb_sync_config` is active. Check `qb_customers` has the company. Check `customer_companies.qb_customer_id` is populated (matching ran). Check QB data propagation ran after matching.
- **Processing job stuck as "running":** Check if `worker_id` is populated (worker path) or NULL (BackgroundTasks path). If worker path: check if the worker is alive and heartbeating. If BackgroundTasks path: the API server may have restarted — manually update the job status.
- **No notifications appearing:** Check `events` table for recent rows. If empty: the worker isn't running or no worker jobs have run. If events exist but `dispatched_at` is NULL: the notification_dispatch job hasn't been triggered. If notifications exist but the bell shows 0: check `recipient_user_id` matches the current user.

---

## 4. Cross-Cutting Concerns

### Multi-tenancy

Every major table has a `client_id` column. API endpoints scope queries by the user's accessible mailboxes (via `get_accessible_mailbox_ids` dependency, which calls the `get_user_accessible_mailboxes` RPC). Client_id is derived from mailbox assignments, not passed directly by the frontend (except on admin endpoints). Cross-tenant leakage risk: some analytics endpoints accept `client_id` as a query parameter from the frontend and trust it — the authorization check is that the user has the required role, but doesn't verify the user is assigned to that specific client. Admin role bypasses all scoping.

### Authentication and roles

Users log in via Supabase Auth (email/password, Google OAuth, Microsoft OAuth). The backend verifies the JWT on every request via `get_current_user` dependency, which calls `supabase.auth.get_user()` and caches the result for 5 minutes (in-process cache, max 1000 entries). Three role levels:

- **Admin:** full access to all mailboxes, users, configuration, all clients
- **Client Manager:** access to mailboxes of assigned clients, can manage users
- **Account Manager:** access to their own assigned mailboxes only

Row-Level Security (RLS) is enabled on all 49 public tables (migration 102, May 2026). The backend uses the service_role key (which bypasses RLS), so authorization is enforced application-side via the `require_role` and `get_accessible_mailbox_ids` dependencies. The frontend uses Supabase exclusively for auth (zero direct table access) — all data queries route through the backend API. The anon key returns 0 rows on all tables. Views and materialized views show UNRESTRICTED in the Supabase dashboard (Postgres limitation) but inherit protection from their RLS-enabled base tables. The frontend hides/shows pages and nav items based on role.

### Background job execution

The platform is mid-migration from FastAPI BackgroundTasks to a dedicated worker process. Currently:

- **Worker path (5 types):** ai_analysis, ai_backfill, reembed, reference_extraction, notification_dispatch. These create `processing_jobs` rows with `status=pending`, which the worker claims via database lock.
- **BackgroundTasks path (~15+ types):** email sync, extraction, QB sync, digests, re-analysis, rebucket, thread operations, reprocessing. These run in the API server's event loop and die on restart.
- **Hybrid (~4 callsites):** strategic_digest, email restart, reprocessing, date-range fetch. These use the factory to create a processing_jobs record (for tracking) but execute via BackgroundTasks. The worker sees these jobs as "pending" but has no handler — if it claims them, it marks them as failed with "Unknown job_type."

Both paths coexist because the migration is incremental. The `railway.toml` defines a `job-worker` service but the `Procfile` only has `web`.

### Notifications

Only `in_app` channel is active (Phase A). Events are emitted for 4 job lifecycle types (started, completed, failed, stopped) but only from worker-executed jobs. The notification_dispatch handler routes events to recipients based on role and client assignment. A cron endpoint (`POST /internal/jobs/notification-dispatch`) exists for automated dispatch every 2 minutes — requires external cron to be configured (see `docs/CRON_SETUP.md`). No email, Slack, or push notification channels.

### Data retention

Nothing is automatically deleted. Emails, processing_jobs, events, notifications, audit_log entries, and AI usage logs grow indefinitely. Old processing_jobs records (completed months ago) remain in the table. No TTL or archival policy exists. Redis keys have a configurable TTL (`REDIS_TTL_DAYS`, default 7), but database rows have none.

### Database sizing and indexes

97 migrations have been applied. Recent audit work (migrations 063-075) added missing indexes, IO budget RPCs, DB performance RPCs, and partial indexes for vector stats. HNSW indexes on `emails`, `customer_companies`, and `qb_operations` are managed by `BulkIndexManager` (dropped before bulk reembed, recreated after). Migration 096 added `embedding_model` + `embedded_at` audit columns and cleared stale mixed-provider embeddings. Migration 097 updated batch embedding RPCs to accept audit params and added `qb_quotes` embedding support. Full-text search index exists on `emails` (migration 057). The `exec_sql` RPC (migration 071) allows index management from application code.

### Secrets and credentials

All secrets are managed via environment variables: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_SECRET`, `GOOGLE_CLIENT_ID/SECRET`, `MICROSOFT_CLIENT_ID/SECRET`, `REDIS_URL`, `CRON_SECRET`, `ANTHROPIC_API_KEY` (or `GEMINI_API_KEY`). In production, these are Railway environment variables. QB API user token is stored in the `qb_sync_config` database table (not an env var). OAuth refresh tokens are stored in `mailboxes.connection_config` and `user_integrations`. No hardcoded secrets were found in application code, but the `exec_sql` RPC grants `EXECUTE` to the `authenticated` role, which means any authenticated user could theoretically execute arbitrary SQL via the Supabase client (if they bypass the API and call Supabase directly with their JWT).

---

## 5. Known Debt and Gaps

- **Worker migration is ~25% complete.** 5 of ~20 job types run on the worker. The other ~15 use FastAPI BackgroundTasks and die on uvicorn restart with no retry or notification. Hybrid callsites (factory record + BackgroundTasks execution) create confusing state where the worker may claim a job it can't handle.

- **External cron setup pending.** The `internal_jobs` router has cron endpoints for all sync types: QB sync (`/qb-sync`), Gmail sync (`/gmail-sync`), Outlook sync (`/outlook-sync`), stuck reconciliation, analytics rollup, and notification dispatch — all requiring `CRON_SECRET` auth. Endpoints are interval-aware (check `last_sync_at + interval` per entity, skip manual-mode configs). Railway cron (Option 1: curl to endpoint) is the recommended setup. Gmail/Outlook legacy asyncio loops can be disabled via `DISABLE_SYNC_LOOPS=true` once Railway cron is confirmed. See `docs/CRON_SETUP.md`.

- **`exec_sql` and `exec_sql_extended` RPCs allow arbitrary SQL from application code.** Granted to the `authenticated` role (migration 071). Any Supabase user who obtains a JWT can call this RPC directly to execute arbitrary DDL/DML. Pending security review.

- **QB API user token stored in database table** (`qb_sync_config`), not in environment variables or a secrets vault. Any code path that reads `qb_sync_config` has access to the token.

- **No data retention policy.** Tables grow indefinitely. `processing_jobs`, `events`, `notifications`, `audit_log`, and `ai_usage_log` have no cleanup. Over time, the `processing_jobs` table will accumulate thousands of completed/failed records that slow down queries.

- **Email deduplication across mailboxes doesn't exist.** The same email received by a sender and recipient (both with connected mailboxes) appears twice in the `emails` table and gets classified twice.

- **Embedding is not automatic.** New emails arrive without embeddings. Semantic search only covers records that existed when reembed was last triggered. There's no pipeline to embed on arrival.

- **BackgroundTasks jobs have no crash recovery.** If the API server restarts while a BackgroundTasks job is running, the `processing_jobs` record stays as "running" forever (unless the stuck-job reconciler catches it, but reconciler only works on worker-leased jobs with `lease_expires_at`).

- **Some analytics endpoints accept `client_id` from the frontend without verifying the user is assigned to that client.** Authorization checks role but not client assignment, creating potential cross-tenant data access for client_manager and account_manager roles.

- **`analytics_rollup_daily` job type has a cron endpoint and uses the factory, but no handler is registered in the worker.** Creating this job will result in the worker marking it as failed with "Unknown job_type."

- **Strategic digest progress tracking uses an in-memory dict** (`_digest_progress`) that is lost on server restart. If the server restarts mid-generation, the frontend will show stale progress.

---

## 6. Glossary

**Canonical thread** — A normalized thread identifier computed from email headers (In-Reply-To, References, Subject). Groups related emails into conversations even when email clients generate inconsistent thread IDs. Computed by migration 055's canonical thread resolution logic.

**Customer tier** — A QB-derived classification of customer importance. Values include "Level 3 Key Account", "Level 2 Regular", "Level 1 Transactional". Stored in `customer_companies.qb_tier`, propagated from QB sync.

**Customer type** — A QB-derived lifecycle classification. Values include "Active A", "Active B", "Prospect", "Dormant", "Lapsed". Stored in `customer_companies.customer_type`.

**Engagement score** — A 0-100 score computed by the engagement_scorer service across 8 factors: email frequency, recency, response rate, response time, contact seniority, thread depth, outbound ratio, and consistency. Stored in `customer_companies.engagement_score`.

**Communication health** — A categorical assessment derived from engagement patterns: healthy, at_risk, declining, quiet. Used in customer profile displays.

**Factory rush level** — A QB-derived indicator of current production load, used by the AI classifier to contextualize urgency. Comes from QB operations data.

**Primary contact** — The contact with the highest email count for a company. Identified during extraction, stored as `customer_contacts.is_primary`.

**Canonical thread resolution** — The process (migration 055) of computing stable thread IDs from email header chains. Handles cases where email clients break threading.

**Embedding vs classification** — Two different AI operations. *Embedding* converts text into a 768-dimensional vector for similarity search (provider set by `EMBEDDING_PROVIDER` env var, stored in `*.embedding` columns with `embedding_model` audit trail). *Classification* uses an LLM (Claude Haiku) to assign structured labels (intent, urgency, sentiment) to an email (stored in `ai_email_intelligence`). They serve different purposes and run independently.

**Processing status** (of an email) — `pending` (not yet classified), `success` (AI classification completed), `failed` (classification attempted but errored). Stored in `emails.processing_status`.

**Job status** (of a processing_jobs row) — `pending` (waiting to be claimed), `running` (actively executing), `completed` (finished successfully), `failed` (errored), `stopped` (manually cancelled), `interrupted` (worker died mid-execution, detected by reconciler).

**Active vs idle** — "Active" means the code is deployed AND serving production traffic. "Idle" means the code is deployed but no production traffic flows through it (e.g., a handler is registered but nobody triggers the job type).

**Action bucket** — One of 6 AM-centric signals assigned to an email by the bucket engine: response_urgency, deal_at_risk, retention_risk, revenue_opportunity, new_relationship, account_neglect.

**Lifecycle tier** — A deterministic customer classification: prospect, new_customer, active_customer, at_risk, dormant, champion. Assigned by the bucket engine based on QB data and engagement patterns.

**Lease** — A time-limited claim on a processing_jobs row by a worker. Set when the worker claims the job (`lease_expires_at` = now + 2 minutes). Extended every 30 seconds by the heartbeat. If the heartbeat stops, the lease expires and the reconciler marks the job as interrupted.

---

*Last updated: 2026-05-01*
