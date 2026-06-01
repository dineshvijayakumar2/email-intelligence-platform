# Email Intelligence Platform — Consolidated Implementation Progress

**Last Updated:** 14 May 2026
**Purpose:** Consolidated reference — completed work, architecture, database schema, and next priorities.

---

## Platform Overview

A commercial intelligence platform for B2B account management teams. It syncs email from Gmail and Outlook, runs AI analysis on every email, and surfaces actionable insights about customers, deals, and relationship health — enriched with CRM (QuickBase) data.

**Deployment:** Production on Railway.
**Backend:** FastAPI (Python 3.13), 16 registered routers, ~170+ API endpoints.
**Frontend:** React/TypeScript (Vite), shadcn/ui + Tailwind CSS, 35+ pages.
**Database:** Supabase PostgreSQL, ~40 tables (incl. pgvector).
**Queue:** Redis (required for real-time job progress).

---

## Status Summary

| Sprint | Scope | Status | Completed |
|--------|-------|--------|-----------|
| Sprint 1 | Foundation: Auth, Gmail/Outlook sync, RBAC | ✅ Complete | Feb 2026 |
| Sprint 2 | Customer data extraction, 30 analytics endpoints, analytics UI | ✅ Complete | Feb 2026 |
| Sprint 3 | QB integration, AI pipeline, strategic digest, prompt system | ✅ Complete | Mar 2026 |
| Prompt System Hardening | DB persistence, version tracking, playground fixes | ✅ Complete | 19 Mar 2026 |
| Invite User System | Admin-controlled onboarding, restrict open sign-up | 🔲 Planned | Not started |
| Nav restructure | Analytics + Intelligence → Customers + Insights + Manage (route rename, no new pages) | ✅ Complete | 19 Mar 2026 |
| Sprint 4 — Sales Intelligence | QB Operations sync, Capability Intelligence, Vector Search, Customer Analytics | ✅ Complete | 26 Mar 2026 |
| Post-S4 Stability | QB matching revamp, incremental sync, match review UI, logging, DevOps | ✅ Complete | 30 Mar 2026 |
| Contact-Company Linking | 5-part fix: 31% → 83.5% contact-company link rate | ✅ Complete | 30 Mar 2026 |
| QB Formula Tags | 6 QB tag fields synced, classifier fallback, analytics upgraded | ✅ Complete | 30 Mar 2026 |
| AI Chat Agent | 12-tool conversational agent at `/insights/agent`, multi-model | ✅ Complete | 31 Mar 2026 |
| QB Email-Based Matching | Unique Emails sync, email-first matching, extraction integration | ✅ Complete | 1 Apr 2026 |
| CC/BCC Email Linking | Junction table, all-recipient linking, company/contact count RPCs | ✅ Complete | 1 Apr 2026 |
| Canonical Thread Resolution | 4-tier signal stack, cross-mailbox merging, thread_status overhaul | ✅ Complete | 3-5 Apr 2026 |
| Frontend Stabilisation | TanStack Query + Table, SSE streaming, terminology cleanup | ✅ Complete | 5 Apr 2026 |
| Premium UI Overhaul | Ant Design → shadcn/ui + Tailwind CSS, 35+ files, zero antd | ✅ Complete | 7-8 Apr 2026 |
| Data Accuracy & Thread Stability | QB revenue accuracy, thread dedup root fix, Data Health page, intent status | ✅ Complete | 8 Apr 2026 |
| QB Data Cleanup & Match Integrity | Contact backfill, 1:1 match enforcement, contamination fix, orphan cleanup | ✅ Complete | 14 May 2026 |
| Invite User System | Admin-controlled onboarding, restrict open sign-up | 🔲 Planned | Not started |

---

## ✅ COMPLETE — Sprint 1: Foundation (Feb 2026)

### Authentication & Access Control

| Feature | Detail |
|---------|--------|
| User authentication | Email/password + Google OAuth + Microsoft OAuth via Supabase |
| Role-based access control | Admin / Client Manager / Account Manager — row-level security in DB |
| Multi-role support | Users can hold multiple roles simultaneously (e.g. admin + account_manager) |
| JWT verification | Supports ES256/RS256 (JWKS) and HS256 (shared secret) |
| Auto profile creation | DB trigger auto-creates `user_profiles` on Supabase Auth signup |

**Three user roles:**

| Role | Access |
|------|--------|
| `admin` | All mailboxes, all clients, system settings, user management |
| `client_manager` | View mailboxes of assigned clients (oversight) |
| `account_manager` | Own mailboxes + assigned clients (operational) |

### Gmail LIVE Sync

| Detail | Value |
|--------|-------|
| OAuth library | Google Identity Services |
| Token endpoint | `oauth2.googleapis.com` |
| Sync mechanism | Incremental via `historyId` |
| Background service | `GmailSyncService` — polls every 15 min (configurable) |
| Token storage | `mailboxes.connection_config` JSONB |
| Scopes | `gmail.readonly`, `gmail.labels`, `openid`, `email`, `profile` |
| File-based + LIVE | MBOX/OLM mailboxes can link live Gmail for ongoing sync |

**Gmail API endpoints:**

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/gmail/auth/exchange` | Exchange OAuth code for tokens |
| GET | `/api/gmail/auth/status/{user_id}` | Check connection status |
| DELETE | `/api/gmail/auth/disconnect/{user_id}` | Disconnect Gmail |
| POST | `/api/gmail/{user_id}/sync` | Trigger manual sync |
| POST | `/api/gmail/mailbox/{mailbox_id}/connect` | Connect Gmail to mailbox |
| DELETE | `/api/gmail/mailbox/{mailbox_id}/disconnect` | Disconnect from mailbox |
| POST | `/api/gmail/mailbox/{mailbox_id}/sync` | Trigger mailbox sync |

### Outlook LIVE Sync

| Detail | Value |
|--------|-------|
| OAuth library | MSAL.js |
| Token endpoint | `login.microsoftonline.com` |
| Sync mechanism | Incremental via `deltaLink` |
| Background service | `OutlookSyncService` — polls at configurable interval |
| Scopes | `Mail.Read`, `User.Read`, `MailboxSettings.Read`, `offline_access` |
| Supported accounts | O365 (work/school) and personal Microsoft accounts |

**Outlook API endpoints:**

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/outlook/auth/exchange` | Exchange OAuth code for tokens |
| GET | `/api/outlook/auth/status/{user_id}` | Check connection status |
| DELETE | `/api/outlook/auth/disconnect/{user_id}` | Disconnect Outlook |
| POST | `/api/outlook/{user_id}/sync` | Trigger manual sync |
| POST | `/api/outlook/mailbox/{mailbox_id}/connect` | Connect Outlook to mailbox |
| DELETE | `/api/outlook/mailbox/{mailbox_id}/disconnect` | Disconnect from mailbox |
| POST | `/api/outlook/mailbox/{mailbox_id}/sync` | Trigger mailbox sync |
| POST | `/api/outlook/fetch-date-range` | Fetch emails by date range |

### File Upload

| Type | Description | Source |
|------|-------------|--------|
| `mbox` | Universal email format | Gmail export, Thunderbird, Apple Mail |
| `pst` | Windows Outlook archive | Outlook for Windows |
| `olm` | Mac Outlook archive | Outlook for Mac |
| `gmail` | Gmail LIVE sync | Gmail API |
| `outlook_live` | Outlook LIVE sync | Microsoft Graph API |

- Google Drive streaming: OLM (RemoteZip), MBOX (line-by-line). No full download required. Supports 65GB+ files.

### Multi-Client Architecture

```
Platform
  └── Clients (e.g. Carbon8 Printing)
       └── Mailboxes (per Account Manager)
            └── Emails → Customer Companies → Contacts
```

---

## ✅ COMPLETE — Sprint 2: Customer Data Extraction (Feb 2026)

### 13-Step Extraction Pipeline

Runs automatically on every mailbox after sync (`extraction_orchestrator.py`):

| Step | What it does |
|------|-------------|
| 1. Validate | Check emails exist and are in scope |
| 2. Extract Contacts | Identify all unique contacts from email headers |
| 3. Deduplicate | Merge duplicate contacts by email address |
| 4. Resolve Companies | Group contacts by domain into companies |
| 5. Upsert Contacts | Write/update contacts in DB |
| 6. Upsert Companies | Write/update companies in DB (+ QB enrichment) |
| 7. Classify Roles | Parse job titles → seniority + function + decision-maker flag |
| 8. Update Roles | Persist role classifications |
| 9. Link Emails | Batch FK backfill — link emails to contacts/companies (100% rate) |
| 10. Calculate Engagement | 8-factor scoring (0–100): frequency, recency, reply rate, thread activity |
| 11. Track Threads | 6 thread states: awaiting reply, resolved, stalled, etc. |
| 12. Analyze Patterns | Initiation ratio, email frequency trend, reply rate |
| 13. Complete | Mark extraction job complete, update timestamps |

**Incremental mode:** Only processes emails since `last_extraction_at` — fast re-runs after new email sync.

### 30 Analytics API Endpoints (`/api/v1/analytics/`)

| Group | Endpoint Count |
|-------|---------------|
| Extraction Control | 5 |
| Contact Analytics | 6 |
| Company Analytics | 5 |
| Thread Analytics | 4 |
| Response Times | 4 |
| Communication Patterns | 4 |
| Dashboard Summary | 2 |

### 6 Analytics Frontend Pages

| Page | Route | What it shows |
|------|-------|---------------|
| Analytics Dashboard | `/analytics/dashboard` | Portfolio overview, period selector (7d/30d/90d/6m/1y), clickable KPIs |
| Contacts | `/analytics/contacts` | All contacts with engagement scores, search, at-risk tab, DM filter |
| Companies | `/analytics/companies` | All companies with revenue + engagement, at-risk tab, search |
| Threads | `/analytics/threads` | Thread status overview, overdue alerts, drilldown to emails |
| Contact Detail | `/analytics/contacts/:id` | Full contact history, linked emails, communication patterns |
| Company Detail | `/analytics/companies/:id` | Top contacts, threads, engagement trend |

**Additional analytics pages:**

| Page | Route | What it shows |
|------|-------|---------------|
| Response Times | `/analytics/response-times` | AM response speed analytics |
| Communication Patterns | `/analytics/patterns` | Initiation ratios, frequency trends |
| Email Rules | `/analytics/email-rules` | Unified rule browser |
| Data Health | `/analytics/data-health` | Pipeline run status, link rates |

**Production verified:** 26,654 emails processed, 100% link rate, ~1.5 min full extraction.

---

## ✅ COMPLETE — Sprint 3: QB Integration + AI + Strategic Digest (Mar 2026)

### QuickBase CRM Integration

| Feature | Detail |
|---------|--------|
| Tables synced | Customers, Contacts, Quotes, Jobs, Sales Line Items (5 tables) |
| Company matching | 4-tier: exact QB ID → normalized name → fuzzy name → email domain |
| Contact matching | Email-to-email matching from QB Unique Emails table |
| Data propagation | QB revenue, tier, AM, days-since-invoice pushed into extraction pipeline |
| QB config UI | `/intelligence/quickbase-config` — connection settings + field mappings |
| QB data browser | `/intelligence/quickbase-data` — view synced records + match status |
| QB API endpoints | 6 endpoints: config, sync, status, customers, match-preview |

**QB API endpoints (`/api/v1/quickbase/`):**

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET/POST | `/config` | Get or save QB connection config |
| POST | `/sync` | Trigger full QB sync |
| GET | `/status` | Sync status and last-sync timestamps |
| GET | `/customers` | View synced QB customer records |
| GET | `/match-preview` | Preview company matching results |
| GET | `/field-definitions` | View cached QB field schema |

### AI Email Analysis (Claude Haiku — ~$0.001/email)

| Feature | Detail |
|---------|--------|
| Per-email classification | Intent (13 categories), urgency (5), sentiment (5), business signal, thread role |
| Entity extraction | Competitors, products, budget signals, buying signals, people, dates, action items |
| Action buckets | 10 buckets assigned by Python engine post-AI call |
| QB-enriched context | Customer tier, revenue, days since last invoice passed to AI per email |
| Thread context | Prior thread messages included so AI understands conversation state |
| BCC/CC handling | Detects internal vs external participants |
| Batch processing | 20 emails/API call, body truncated to 300 chars — cost-optimised |
| Prompt versioning | DB-persisted prompt version stamped on each analyzed email |

**11 AI intent categories:** `action_required` · `fyi_update` · `meeting_scheduling` · `question` · `complaint` · `positive_feedback` · `pricing_inquiry` · `feature_request` · `expansion_signal` · `churn_risk` · `follow_up`

### Action Bucket Engine (pure Python — $0)

10 buckets classify customer relationship state:

`buying_signal` · `churn_risk` · `revenue_at_risk` · `hot_prospect` · `expansion_signal` · `competitor_threat` · `missed_opportunity` · `silent_champion` · `stakeholder_entry` · `unresolved_block`

### Customer Lifecycle Tiers

Every company is auto-classified: `prospect` · `new_customer` · `active_customer` · `at_risk` · `dormant` · `champion`

### Strategic Digest (LangGraph ReAct Agent)

| Feature | Detail |
|---------|--------|
| Agent type | LangGraph ReAct with tool loop |
| Tools | `lookup_company_detail`, `lookup_contact_history`, `lookup_thread_messages`, `lookup_quote_detail` |
| Output sections | 8: Executive Summary, Urgent Actions, Revenue Momentum, Pipeline Intelligence, Relationship Health, AM Performance, Competitive Intelligence, Action Items |
| Multi-model | Claude Haiku (fast/cheap) + Claude Sonnet (strategic) + Gemini 2.0 Flash (free tier) |
| Cost | ~$0.13/digest, ~$2–5/month |
| Caching | 24h cache per period — re-uses output if period unchanged |

### 8 Intelligence Frontend Pages

| Page | Route | What it shows |
|------|-------|---------------|
| Smart Inbox | `/intelligence/inbox` | All emails with AI classification, bucket chips, urgency, confidence scores |
| Daily Digest | `/intelligence/digest` | AI-generated account summary for the day with action items |
| Opportunities | `/intelligence/opportunities` | Action items, pipeline signals, competitors, business entities |
| AI Usage & Monitoring | `/intelligence/usage` | Cost tracking, budget controls, model selection, re-analysis trigger |
| Strategic Digest | `/intelligence/strategic-digest` | LangGraph 8-section deep analysis using QB + email data |
| AI Insights | Per-entity "Analyze" button | Per-company/contact/thread AI insight, cached 24h |
| QB Config | `/intelligence/quickbase-config` | QuickBase connection and field mapping settings |
| QB Data | `/intelligence/quickbase-data` | View synced QB records and match status |
| Prompt Playground | `/intelligence/playground` | Edit all AI prompts, test against live data, version management |
| Semantic Search | `/intelligence/vector-search` | Query across emails/companies/operations with similarity scores |

**Manage pages (`/manage/`):**

| Page | Route | What it shows |
|------|-------|---------------|
| Intelligence Config | `/manage/intelligence-config` | Capability tags, classifier rules, CSV import, rush settings, reclassify, cache |

### AM Efficiency Analysis

| Metric | Detail |
|--------|--------|
| Response time | Business-hours adjusted response times |
| Quote conversion | Quote-to-accepted tracking from QB |
| Revenue attribution | Revenue per AM from QB sales data |
| SLA compliance | Thread overdue rates by AM |

---

## ✅ COMPLETE — Prompt System Hardening (19 Mar 2026)

| Fix | Detail |
|-----|--------|
| Global DB fallback | Prompts stored with `client_id IS NULL` now served correctly (was bypassed by early bail-out) |
| Auto-seed | On first use, builtin defaults automatically written to DB — all prompts editable via playground from day one |
| Insight engine client_id | `insight_company` / `insight_contact` / `insight_thread` now correctly load client-specific prompts |
| Version tracking | Email analysis stamps the DB prompt version (not hardcoded constant) so reprocessing correctly identifies affected emails |
| Reprocess endpoint | Now resolves current version from DB — reprocessing works after playground edits |
| Playground — version input | Version field with auto-suggested bump (v1.3 → v1.4) instead of hardcoded `v1.0` |
| Playground — context hints | Each prompt shows what data is auto-injected vs what variables must be kept |
| Playground — validation | Blocks save of `email_analysis_user` if `{emails_json}` placeholder is removed |
| Usage page | Version dropdown replaced with free-text input — any version can be targeted for reprocessing |

**8 configurable AI prompts (keys):** `email_analysis_system` · `email_analysis_user` · `daily_digest` · `weekly_digest` · `strategic_digest` · `insight_company` · `insight_contact` · `insight_thread`

---

## ✅ COMPLETE — Sprint 4: Sales Intelligence Engine (26 Mar 2026)

### S4.0: Communication Guidelines

| Feature | Detail |
|---------|--------|
| Prompt updates | B2B consultative tone block added to email analysis, digest, and insight prompts |
| Persistence | JSON-based prompt config in `ai_prompt_config` table |
| Editability | All prompts editable via AI Playground — version bump triggers reprocessing |

### S4.1: QB Operations Sync + Capability Intelligence

**Operations Table (6th QB table):**

| Feature | Detail |
|---------|--------|
| Table | `qb_operations` — operation_name, department, job linkage, financials |
| Sync | Stream-and-upsert with numeric overflow guard + fail-fast on API errors |
| QB table ID | `bvqsudnif` (Carbon8) |
| Migration | 032: `qb_operations` table + `operations_table_id` on `qb_sync_config` |

**Capability Intelligence:**

| Feature | Detail |
|---------|--------|
| Classifier | `capability_classifier.py` — rule-based classification of operations into capability tags |
| Seed rules | 597 rules in `capability_classifier_data.json` (170+ capability-tagged tuples) |
| MVP tags | 8 tags: Flat Sheets, Soft Cover Books, Hard Cover Books, Wide Format, Embellishment, Specialty Finishing, Design Services, Display/Installation |
| Batch reclassify | RPC-based batching — 600K operations in ~15 min (100x speedup vs individual calls) |
| Throttling | Background thread + batch throttle prevents frontend starvation during reclassify |

**Intelligence Config UI (`/manage/intelligence-config`):**

| Feature | Detail |
|---------|--------|
| Router | `intelligence_config.py` — 8 endpoints (tags, rules, import, rush settings, reclassify, cache) |
| Frontend | 5-tab UI: Capability Tags, Classifier Rules, Rush Settings, Reclassify Status, Cache |
| CSV import | BOM-safe CSV/JSON import for classifier rules |
| Client selector | Admin can switch client context on config page |
| Sidebar | Admin-only nav item under Manage section |

### S4.2–S4.3: Customer Intelligence Analytics (Phase 2A-C)

4 new analytics features on the company detail page — pure SQL/Python aggregation ($0 AI cost):

| Feature | Endpoint | Component | What it shows |
|---------|----------|-----------|---------------|
| Strike Rate | `GET /{id}/strike-rate` | `StrikeRateCard.tsx` | Quote→job conversion rate, per-contact table, YoY trend |
| Contact Capabilities | `GET /{id}/contact-capabilities` | `ContactCapabilitiesCard.tsx` | Contact × capability matrix with colored tags |
| Seasonality | `GET /{id}/seasonality` | `SeasonalityChart.tsx` | Monthly bar chart + quarterly summary |
| Capability Rhythm | `GET /{id}/capability-rhythm` | `CapabilityRhythmCard.tsx` | Per-capability reorder interval + overdue detection |

| Infrastructure | Detail |
|----------------|--------|
| Service | `customer_analytics_service.py` — ~400 lines, all 4 aggregations |
| Cache | 24h TTL in `customer_intelligence_cache` table |
| Company detail | Deferred card loading — timeout 30s, null-safe access, retry on null |
| Analytics cap | All analytics queries capped at 10K rows to prevent slow page loads |

### S4.4: Vector Embeddings + Semantic Search

| Feature | Detail |
|---------|--------|
| Extension | pgvector with HNSW indexes |
| Model | Google `gemini-embedding-001`, 768 dimensions |
| Tables embedded | `emails`, `customer_companies`, `qb_operations` |
| Batch config | 50 texts/batch, 2s delay, exponential backoff on rate limits |
| Resilience | Skip rate-limited batches (don't abort), per-table graceful degradation |
| DB writes | Chunks of 25 via batch RPC |

**Vector API endpoints (`/api/v1/ai/vector/`):**

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/reembed` | Bootstrap or re-embed per table |
| GET | `/reembed/status` | Poll embedding progress |
| POST | `/reembed/stop` | Stop running job, keep embedded records |
| GET | `/search/emails` | Semantic search emails |
| GET | `/search/companies` | Semantic search companies |
| GET | `/search/operations` | Semantic search operations |
| GET | `/search` | Unified search across all 3 tables |
| GET | `/stats` | Embedding coverage stats |

**Semantic Search UI (`/insights/vector-search`):**

| Feature | Detail |
|---------|--------|
| Query input | Free text + 8 suggested prompts (wide format, binding, foil, rush, retention, etc.) |
| Results | Per-table results with similarity scores (0–100%) |
| Reembed controls | Per-table embed/re-embed with progress polling + stop button |
| Stats dashboard | Emails/companies/operations embedded counts |

### Supporting Infrastructure (Sprint 4)

| Change | Detail |
|--------|--------|
| Router refactor | `main.py` split into modular routers — security + performance fixes |
| Lightweight extraction | Auto-sync runs steps 1–9 only (skip engagement/threads/patterns) |
| LIVE mailbox UI | Gmail/Outlook mailboxes show sync info instead of old processing form |
| Auth improvements | `supabase.auth.get_user()` replaces JWKS — eliminates login failures; auth cache reduces connection pressure |
| Log noise | Suppressed repetitive auth/ws/polling log lines |
| Skip recent sync | Startup skips email sync if mailbox was recently synced |

### Sprint 4 Migrations

| # | File | What it adds |
|---|------|-------------|
| 032 | `032_qb_operations.sql` | `qb_operations` table + `operations_table_id` on `qb_sync_config` |
| 033 | `033_prompt_communication_guidelines.sql` | AI prompt config persistence |
| 034 | `034_product_intelligence.sql` | Product profile data structures |
| 035 | `035_intelligence_config.sql` | Capability taxonomy config tables |
| 036 | `036_fix_operations_profit_pct.sql` | Widen `profit_pct` DECIMAL(5,2) → DECIMAL(8,2) |
| 037 | `037_vector_embeddings.sql` | pgvector extension + embedding columns + HNSW indexes |
| 037b | `037b_vector_resize_3072.sql` | Resize embeddings to 768 dims |
| 038 | `038_optimize_response_time_query.sql` | Response time query performance |
| 039 | `039_batch_embedding_update.sql` | Batch RPC for embeddings |
| 040 | `040_batch_classify_update.sql` | Batch RPC for classifications |
| 041 | `041_customer_matching_revamp.sql` | Matching revamp: `qb_customer_id`, `qb_match_method`, `qb_matched_at` on `customer_companies` + `qb_match_candidates` staging table |
| 042 | `042_fix_growth_precision.sql` | Widen `growth_90d` DECIMAL(5,2) → DECIMAL(8,2) |

---

## Database: Complete Table Inventory (~40 tables)

### Sprint 1 — Core Tables

| Table | Purpose |
|-------|---------|
| `emails` | Individual email records (subject, body, sender, recipients, date, direction, attachments, provider_web_link) |
| `mailboxes` | Email accounts — type (gmail/outlook/mbox/pst/olm), `connection_config` JSONB stores per-type OAuth tokens and sync state |
| `processing_jobs` | Async job tracking — status, progress, error details for file processing runs |
| `folders` | Email folder tree per mailbox |
| `user_profiles` | Platform users — email, name, `roles TEXT[]`, is_active. Linked to Supabase auth.users |
| `user_client_assignments` | Account Manager → Client operational assignments |
| `client_manager_assignments` | Client Manager → Client oversight assignments |
| `clients` | Client organisations — name, QB config, currency_code, timezone |
| `user_integrations` | Per-user OAuth tokens for Gmail/Outlook (legacy; active mailboxes use `mailboxes.connection_config`) |

### Sprint 2 — Customer Intelligence Tables

| Table | Purpose |
|-------|---------|
| `customer_companies` | Discovered companies — engagement_score, lifecycle signals, QB enrichment columns (qb_tier, qb_total_revenue, qb_days_since_last_invoice, qb_account_manager, etc.) |
| `customer_contacts` | Discovered contacts — seniority, functional_role, is_decision_maker, engagement_score, response times, communication patterns, QB enrichment columns |
| `internal_domains` | Email domains treated as internal per client (filters out internal emails from contact extraction) |
| `free_email_providers` | Gmail/Hotmail/Yahoo etc. — prevents treating these as company domains |
| `extraction_jobs` | Pipeline run tracking — current_step, progress counters, extraction_mode (full/incremental) |
| `unified_email_rules` | Email filtering rules from Gmail/Outlook APIs or manual entry — conditions + actions + engagement signals |
| `email_response_metrics` | Response time data per email pair — response_time_seconds, is_auto_reply |
| `thread_status` | Thread state per thread_id — status (awaiting_reply/overdue/dropped/stale/resolved), SLA tracking, QB tier columns |

### Sprint 3 — AI Intelligence Tables

| Table | Purpose |
|-------|---------|
| `ai_email_intelligence` | Per-email AI results — intent, urgency, sentiment, action_buckets (JSONB), entities extracted, human feedback, prompt_version, processing_status |
| `ai_usage_log` | AI API cost tracking — model, operation, tokens in/out, cost_usd, per mailbox/client |
| `ai_daily_digests` | Cached daily digest outputs — email stats, bucket summaries, action items, model used, cost |
| `ai_strategic_digests` | Strategic digest outputs — 8-section JSONB (exec summary, pipeline, relationships, AM perf, etc.), period type, model used, cost |
| `relationship_context_cache` | Pre-computed per-company relationship summaries — lifecycle_tier, AM details, key_contacts, financial summary (JSONB). 24h TTL |
| `am_performance_snapshots` | AM performance per period — response times, quote conversion, revenue, customer counts, retention rate |

### Sprint 3 — QuickBase Cache Tables

| Table | Purpose |
|-------|---------|
| `qb_sync_config` | Per-client QB connection — realm_hostname, app_id, encrypted_token, table IDs, field_mappings, sync interval |
| `qb_customers` | Cached QB customers — revenue fields (total_invoiced, invoiced_ty/ly/l90d/l12m), recency_days, cadence_score, matched_company_id |
| `qb_contacts` | Cached QB contacts — names, email, quotes_accepted_count, contact_recency_days, matched_contact_id |
| `qb_quotes` | Cached QB quotes — sell_ex_tax, date_created/accepted, category, job_no, has_job, matched_company_id |
| `qb_jobs` | Cached QB jobs — retail_sale, invoiced_margin, margin_pct, due_date, factory_rush_level, matched_company_id |
| `qb_sales_line_items` | Cached QB invoiced revenue — subtotal, total, inv_date, product_group, job_am_name, matched_company_id |
| `qb_field_definitions` | Cached QB field schema (label, type) per table — used to display field names in UI |
| `qb_sync_log` | QB sync audit log — table_name, record_count, status (success/error), synced_at |

### Sprint 4 — Sales Intelligence Tables

| Table | Purpose |
|-------|---------|
| `qb_operations` | Cached QB operations — operation_name, department, job linkage, financials, capability_tags (TEXT[]) |
| `customer_intelligence_cache` | Cached analytics aggregations (strike rate, seasonality, capabilities) — 24h TTL |

### Post-Sprint 3 Config Tables

| Table | Purpose |
|-------|---------|
| `system_settings` | Client-scoped key-value settings (client_id + key + value) — e.g. AI model selection, budget cap |
| `ai_prompt_config` | Configurable AI prompts — client_id (NULL = global), prompt_key, prompt_text, version, is_active |
| `business_entities` | Aggregated entity tracking — competitors, products, people mentioned across emails |

---

## Backend Architecture

### API Routers (16 registered in `main.py`)

| Router | Prefix | Purpose |
|--------|--------|---------|
| `auth.py` | `/api` | JWT validation, user profile, accessible mailboxes |
| `gmail.py` | `/api` | Gmail OAuth, connection, sync |
| `outlook.py` | `/api` | Outlook OAuth, connection, sync |
| `account_managers.py` | `/api` | Account manager CRUD |
| `clients.py` | `/api` | Client CRUD, mailbox assignment |
| `customers.py` | `/api` | Customer company endpoints |
| `contacts.py` | `/api` | Customer contact endpoints |
| `analytics.py` | `/api/v1` | 30 analytics endpoints (contacts, companies, threads, patterns) |
| `admin.py` | `/api/v1` | Raw table browser, CSV export |
| `ai.py` | `/api/v1` | AI analysis, digests, insights, usage, models |
| `rules.py` | `/api/v1` | Email rules CRUD and sync |
| `quickbase.py` | `/api/v1` | QB config, sync, status, data browser |
| `errors.py` | `/api` | Error log browser |
| `intelligence_config.py` | `/api/v1` | Capability tags, classifier rules, reclassify, rush settings |
| `customers.py` | `/api/v1` | Customer analytics (strike rate, seasonality, capabilities, rhythm) |
| `websocket` | `/ws` | Real-time job progress streaming |

Plus inline endpoints on `main.py`: mailbox management, processing jobs, file upload, Google Drive streaming.

### Service Layer (35 services in `backend/src/services/`)

**Email Extraction (Sprint 2):**
- `extraction_orchestrator.py` — 13-step pipeline coordinator
- `contact_extractor.py` — Email address extraction + deduplication
- `company_resolver.py` — Domain → company grouping
- `role_classifier.py` — Job title → seniority + function + decision-maker
- `email_linker.py` — Batch FK backfill, 100% link rate
- `engagement_scorer.py` — v2: 10-factor scoring (70% email + 30% QB)
- `response_time_tracker.py` — Response time calculation, auto-reply detection
- `thread_tracker.py` — Thread state evaluation (6 states)
- `comm_pattern_analyzer.py` — Initiation ratio, reply rate, frequency trends

**AI Intelligence (Sprint 3):**
- `ai_client.py` — Claude API client (Haiku/Sonnet)
- `ai_privacy_filter.py` — PII filtering before AI calls
- `ai_usage_tracker.py` — Token and cost logging
- `ai_email_analyzer.py` — Per-email AI classification in batches of 20
- `ai_action_bucket_engine.py` — v2.0: 10-bucket Python classifier
- `ai_entity_aggregator.py` — Aggregate entity stats from emails
- `ai_digest_generator.py` — Daily and weekly digest generation
- `ai_insights_engine.py` — Per-entity (company/contact/thread) AI insight with 24h cache

**QuickBase & Strategic (Sprint 3):**
- `quickbase_client.py` — QB REST API client
- `quickbase_sync.py` — 5-table sync, 4-tier company matching, data propagation
- `langchain_core.py` — Multi-model: Claude Haiku/Sonnet + Gemini 2.0 Flash
- `langchain_tools.py` — 4 LangGraph agent tools
- `strategic_context_builder.py` — Pre-computes relationship_context_cache + AM snapshots
- `strategic_digest_pipeline.py` — Full LangGraph ReAct agent pipeline
- `am_efficiency_analyzer.py` — Business-hours response, quote conversion, revenue attribution

**Sales Intelligence (Sprint 4):**
- `capability_classifier.py` — Rule-based operations → capability tag classification (597 seed rules)
- `customer_analytics_service.py` — Strike rate, seasonality, contact capabilities, capability rhythm
- `vector_service.py` — Gemini embedding + pgvector semantic search across emails/companies/operations

**Sync Services:**
- `gmail_sync_service.py` — Background Gmail incremental sync
- `outlook_sync_service.py` — Background Outlook delta sync

### Email Extractors (`backend/src/extractors/`)
- `gmail_extractor.py` — Gmail API streaming extractor
- `outlook_extractor.py` — Microsoft Graph API streaming extractor
- MBOX, PST, OLM extractors (file-based)

---

## Frontend Architecture

### All Pages (30+)

**Core pages:**

| Page | Route |
|------|-------|
| Login | `/login` |
| Dashboard | `/` |
| Mailboxes | `/mailboxes` |
| Emails | `/emails/:mailboxId` |
| Processing | `/processing/:mailboxId` |
| Mailbox Process | `/mailbox-process` |
| Clients | `/clients` |
| Users | `/users` |
| Settings | `/settings` |
| Admin Data | `/admin-data` |
| Audit Logs | `/audit-logs` |
| Errors | `/errors` |
| Extraction | `/extraction` |
| OAuth Callback | `/oauth-callback` |
| Reset Password | `/reset-password` |

**Analytics pages (`/analytics/`):**

| Page | Route |
|------|-------|
| Dashboard | `/analytics/dashboard` |
| Companies | `/analytics/companies` |
| Company Detail | `/analytics/companies/:id` |
| Contacts | `/analytics/contacts` |
| Contact Detail | `/analytics/contacts/:id` |
| Threads | `/analytics/threads` |
| Response Times | `/analytics/response-times` |
| Communication Patterns | `/analytics/patterns` |
| Email Rules | `/analytics/email-rules` |
| Data Health | `/analytics/data-health` |

**Intelligence pages (`/intelligence/`):**

| Page | Route |
|------|-------|
| Smart Inbox | `/intelligence/inbox` |
| Daily/Weekly Digest | `/intelligence/digest` |
| Opportunities | `/intelligence/opportunities` |
| AI Usage & Monitoring | `/intelligence/usage` |
| Strategic Digest | `/intelligence/strategic-digest` |
| QB Config | `/intelligence/quickbase-config` |
| QB Data Browser | `/intelligence/quickbase-data` |
| Prompt Playground | `/intelligence/playground` |

### Shared Components
- `ActionBucketTag` — Colour-coded AI bucket chips
- `FeedbackButtons` — Thumbs up/down on AI classifications
- `LifecycleBadge` — Colour-coded tier badge (prospect → champion)
- `AIInsightsCard` — Reusable "Analyse with AI" → cached insight display
- `EngagementBadge` — Score badge with tier colour
- `MailboxSelector` — Context switcher used across all pages
- `ClientSelector` — Admin-level client context switcher

---

## Environment Configuration

### Backend (`.env.production`)

```env
# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_KEY=...
SUPABASE_JWT_SECRET=...

# Redis (required)
REDIS_URL=${Redis.REDIS_URL}
REDIS_TTL_DAYS=7

# Google (Gmail + Drive)
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=https://yourapp.com/auth/google/callback

# Microsoft (Outlook)
MICROSOFT_CLIENT_ID=...
MICROSOFT_CLIENT_SECRET=...
MICROSOFT_TENANT_ID=common

# AI models
ANTHROPIC_API_KEY=...
GOOGLE_GENAI_API_KEY=...    # Gemini 2.0 Flash (free tier)
```

### Frontend (`.env.production`)

```env
VITE_API_BASE_URL=https://${{backend.RAILWAY_PRIVATE_DOMAIN}}/api
VITE_SUPABASE_URL=...
VITE_SUPABASE_ANON_KEY=...
VITE_GOOGLE_CLIENT_ID=...
VITE_MICROSOFT_CLIENT_ID=...
```

---

## Migration History

| # | File | What it adds |
|---|------|-------------|
| 001–016 | Sprint 1–2 core | Business hierarchy, RBAC, mailboxes, extraction pipeline |
| Sprint 2 001–014 | `scripts/sprint2/` | customer_companies, customer_contacts, extraction_jobs, unified_email_rules, email_response_metrics, thread_status, incremental mode |
| Sprint 3 013 | `sprint3_migration_013_ai_layer.sql` | ai_email_intelligence, ai_usage_log, ai_daily_digests, business_entities |
| Sprint 3 021 | `sprint3_migration_021_strategic_digest.sql` | qb_sync_config, qb_customers, qb_contacts, qb_quotes, qb_jobs, qb_sales_line_items, relationship_context_cache, ai_strategic_digests, am_performance_snapshots |
| 021a | `021a_add_qb_enrichment_columns.sql` | QB columns on customer_companies, customer_contacts, thread_status |
| 022 | `022_add_qb_field_definitions.sql` | qb_field_definitions |
| 023 | `023_add_qb_sync_log.sql` | qb_sync_log |
| 025 | `025_add_system_settings.sql` | system_settings |
| 026 | `026_am_lifecycle_rehaul.sql` | lifecycle_tier + AM columns on relationship_context_cache, am_performance_snapshots; timezone on clients |
| 027 | `027_ai_prompt_config.sql` | ai_prompt_config |
| 028 | `028_client_scoped_settings.sql` | Restructure system_settings → client-scoped |
| 029 | `029_drop_ai_check_constraints.sql` | Remove rigid check constraints from ai_email_intelligence |
| 030 | `030_add_currency_code.sql` | currency_code on clients |
| 031 | `031_add_email_attachments_deeplink.sql` | attachments (JSONB) + provider_web_link on emails |
| 032 | `032_qb_operations.sql` | `qb_operations` table + `operations_table_id` on `qb_sync_config` |
| 033 | `033_prompt_communication_guidelines.sql` | AI prompt config persistence |
| 034 | `034_product_intelligence.sql` | Product profile data structures |
| 035 | `035_intelligence_config.sql` | Capability taxonomy config tables |
| 036 | `036_fix_operations_profit_pct.sql` | Widen `profit_pct` DECIMAL(5,2) → DECIMAL(8,2) |
| 037 | `037_vector_embeddings.sql` | pgvector extension + embedding columns + HNSW indexes |
| 037b | `037b_vector_resize_3072.sql` | Resize embeddings to 768 dims |
| 038 | `038_optimize_response_time_query.sql` | Response time query performance |
| 039 | `039_batch_embedding_update.sql` | Batch RPC for embeddings |
| 040 | `040_batch_classify_update.sql` | Batch RPC for classifications |
| 041 | `041_customer_matching_revamp.sql` | `qb_customer_id`, `qb_customer_code`, `qb_match_method`, `qb_matched_at` on `customer_companies` + `qb_match_candidates` staging table + `promote_accepted_matches` RPC |
| 042 | `042_fix_growth_precision.sql` | Widen `growth_90d` DECIMAL(5,2) → DECIMAL(8,2) on `qb_customers` + `customer_companies` |

---

## Cost Summary (Current Production)

| Component | Monthly Cost |
|-----------|-------------|
| Email analysis — Claude Haiku | ~$8–12 |
| Daily/weekly digests — Claude Sonnet | ~$3–4 |
| Strategic digest — Claude Sonnet + Gemini | ~$2–5 |
| Per-page AI insights | ~$1–3 |
| QuickBase sync | $0 |
| **Total current** | **~$14–24/month** |
| **Budget cap** | **$50/month** |

Sprint 4 additions (vector embeddings + AI Chat Agent): +~$3–8/month → well within budget.

---

## 🔲 PLANNED — Invite User System (Not started)

**Design document:** `docs/INVITE_USER_SMTPLESS.md`

**Problem:** Sign-up is currently open — anyone with the URL can create an account.

**Proposed solution:** Admin-controlled invite-only onboarding.

| Item | Detail |
|------|--------|
| DB: pending_invites table | Migration 014 — stores invite tokens, expiry, role, client assignment |
| Backend: invites.py router | 6 endpoints: create, validate, accept, list, resend, revoke |
| Auto-mailbox creation | On acceptance, inactive mailbox auto-created from email domain (gmail/outlook detected) |
| Frontend: InviteUserModal | Two-step modal: form → delivery options (magic link / shared URL / direct OAuth) |
| Frontend: InviteAcceptPage | Public acceptance page — handles all 3 sign-in paths |
| Frontend: Users page update | "Invite User" button + pending invites in table |
| Frontend: Login page | Remove "Create Account" tab |
| Frontend: Dashboard banner | "Connect your email" prompt for users with unconnected mailbox |

**Effort estimate:** 3–5 days

---

## ✅ COMPLETE — Post-Sprint 4 Stability & DevOps (27–30 Mar 2026)

### QB Matching Revamp
- 3-pass matching pipeline: exact name → domain root → fuzzy staging (rapidfuzz ≥82%)
- 7,186 matched / 15,121 QB customers (47.5% match rate)
- Match Review page at `/manage/quickbase-matches` — confirm/skip/override fuzzy candidates
- QBLinkWidget on company + contact detail pages for manual linking
- Incremental sync default (fid:2 Date Modified)

### Backend Stability Fixes (30 Mar 2026)
| Fix | Detail |
|-----|--------|
| Event loop blocking | QB rematch/sync/propagation background tasks converted from `async def` to `def` — FastAPI runs in thread pool instead of blocking event loop |
| QB propagation speed | Removed `time.sleep(0.5)` throttle, added company deduplication — 7K updates in minutes instead of hours |
| Email linker timeout | Replaced `ORDER BY sent_date` with `ORDER BY id` (PK) — eliminates full-table sort. Added partial index migration 043 |
| Pipeline resilience | Steps 9-12 (enrichment/analytics) now non-critical — failures log warning and continue instead of aborting |
| Orphaned jobs | Cleanup now clears Redis progress + DB status on restart. Job list endpoint only reads Redis for active jobs |
| Domain-only email linking | Email linker falls back to company domain match when contact not found — emails from unknown senders at known companies now link |
| Company detail threads | `GET /analytics/companies/{id}` now returns `active_threads` and `overdue_threads` counts |

### DevOps
| Feature | Detail |
|---------|--------|
| `USE_PROD_DB` mode | Set `USE_PROD_DB=true` to run local backend against prod Supabase. Auto-disables Gmail/Outlook sync to prevent conflicts |
| `start-platform-proddb.bat` | One-click local dev against prod database (backend + frontend) |
| `npm run dev:proddb` | Frontend Vite mode with prod Supabase auth credentials |
| Progress logging | All QB background tasks emit step-level + iteration progress logs with `client_id` context for live log monitor filtering |

### Structured Logging (27–29 Mar 2026)
- Thread-local `set_log_context(mailbox_id, client_id)` for all extraction sub-services
- `client_id` context on all QB background tasks
- Progress logging every 200-2000 iterations across all long-running loops
- Mailbox name resolution in log monitor (shows name or email local-part instead of UUID)

---

## ✅ COMPLETE — Contact-Company Linking Fix (30 Mar 2026)

**Problem:** Only 6,211 out of 20,035 contacts (31%) had `customer_company_id` set.
**Result:** After fix + migration → 17,305 / 20,735 (83.5%) linked. Remaining are free email provider contacts (gmail, yahoo) correctly excluded.

| Fix | Description | Status |
|-----|-------------|--------|
| 1. SQL COALESCE fix (044) | `batch_update_contact_companies` preserves existing company links when update has NULL | ✅ |
| 2. Reorder Steps 5↔6 | Upsert companies BEFORE contacts — root cause elimination | ✅ |
| 3. Orphan contact linking | Post-upsert scan links contacts to companies by email domain (excluding free providers) | ✅ |
| 4. Email linker backfill | Domain fallback in Step 9 also updates contact's `customer_company_id` | ✅ |
| 5. Data migration (045) | One-time backfill: 11,094 orphan contacts linked by domain match | ✅ |

---

## ✅ COMPLETE — QB Formula Tags Integration (30 Mar 2026)

6 QB formula tag fields synced from Operations table. Our classifier becomes fallback.

| Field | QB FID | Column | Values |
|-------|--------|--------|--------|
| Process_Tag | 44 | `qb_process_tag` | ~27 process categories |
| Capability_Tag | 45 | `qb_capability_tag` | 8 broad capabilities (same as classifier) |
| Machine_Tier_Tag | 46 | `qb_machine_tier_tag` | ~35 technology groups |
| Row_Type_Tag | 47 | `qb_row_type_tag` | Operation classification |
| Blank_Reason_Tag | 48 | `qb_blank_reason_tag` | Why untagged |
| Embellishment_Tag | 52 | `qb_embellishment_tag` | Embellishment type |

- Migration 046 adds columns + indexes
- `_classify_operations()` uses QB `Capability_Tag` as primary, classifier as fallback
- Analytics methods (contact capabilities, seasonality, rhythm) prefer QB tags
- Product profile includes `capability_breakdown`, `process_tags`, `embellishment_tags`
- Vector embeddings include QB tags for richer semantic search
- Strategic digest context includes capability profile per company
- **Blocked:** `MVP_tag` field not yet created in QB — `Row_Type_Tag` and `Blank_Reason_Tag` will improve once added

---

## ✅ COMPLETE — AI Chat Agent (30–31 Mar 2026)

Conversational AI assistant at `/insights/agent` with 12 tools for full portfolio intelligence.

### Architecture
- **Backend:** `ai_agent_service.py` — LangGraph ReAct agent with retry + direct LLM fallback
- **Endpoint:** `POST /api/v1/ai/agent/chat` — auth-protected, 90s timeout
- **Frontend:** Chat UI with conversation history, tool usage display, suggested starters
- **Model:** Configurable per-client (Claude Sonnet, Gemini Flash, GPT-4o, GPT-4o Mini)
- **Cost tracking:** Usage logged to `ai_usage_log` per conversation turn

### 12 Agent Tools
| Category | Tools |
|----------|-------|
| Portfolio | `portfolio_summary`, `account_ranking` (by revenue, engagement, growth, contact recency) |
| Emails | `search_emails` (recent/urgent/sender/intent/company/signal/unresponded), `semantic_search_emails` |
| Companies | `lookup_company_detail`, `company_analytics` (strike rate, seasonality, rhythm, capabilities) |
| Contacts | `search_contacts` (decision makers, by role/engagement/company/inactive), `lookup_contact_history` |
| Threads | `thread_overview` (summary/overdue/active/per-company), `lookup_thread_messages` |
| Operations | `semantic_search_operations`, `lookup_quote_detail` |

### Multi-Model AI Support
| Model | Provider | Use Case |
|-------|----------|----------|
| Claude Haiku | Anthropic | Per-email analysis (cheap/fast) |
| Claude Sonnet | Anthropic | Strategic analysis |
| Gemini 2.5 Flash | Google | Free tier / budget |
| GPT-4o | OpenAI | Strategic (alternative) |
| GPT-4o Mini | OpenAI | Budget (alternative) |

- OpenAI API key configurable via **Insights > Usage** page
- All 3 provider keys (Anthropic, Google, OpenAI) manageable per-client
- `langchain-openai` added to requirements

---

## ✅ COMPLETE — Internal Domains Management (30 Mar 2026)

- 3 CRUD endpoints: `GET/POST/DELETE /clients/{id}/internal-domains`
- Edit Client modal shows Internal Domains section with tag-style add/remove
- Domains excluded from customer extraction (contacts from these domains won't create companies)

---

## 🟡 IN PROGRESS — Sprint 4: Sales Intelligence Engine

**Goal:** Merge email engagement intelligence with production intelligence from QuickBase — showing not just who's communicating, but what they buy, what they should be buying, and what to recommend next.

### Completed (Mar 2026):
- ✅ S4.0: Communication Guidelines in prompt templates
- ✅ S4.1: QB Operations sync (650K+ records) + Capability Intelligence (8 MVP tags, 597 classifier rules)
- ✅ S4.1: Operations table in QB Config + QB Data pages (6th table)
- ✅ S4.4: Vector embeddings (pgvector, gemini-embedding-001, 768 dims, HNSW indexes)
- ✅ S4.4: Semantic Search page (`/insights/search`) — unified email/company/operations search
- ✅ S4.4: Per-table embedding controls, stop button, batch RPC updates
- ✅ Fix: Lightweight extraction for auto-sync (steps 1-9 only, skips heavy analytics)
- ✅ Fix: LIVE mailbox process page shows sync info instead of old processing form
- ✅ Fix: Disambiguate thread_status FK in digest generator
- ✅ Fix: Optimized response time query (covering index + semi-join)
- ✅ Fix: profit_pct column widened (DECIMAL(5,2) → DECIMAL(8,2))
- ✅ Fix: Redirect routes preserve mailboxId params

### Completed (30–31 Mar 2026):
- ✅ Contact-Company Linking Fix — 31% → 83.5% link rate (5-part fix + migration)
- ✅ QB Formula Tags (6 fields synced, classifier fallback, analytics upgraded)
- ✅ AI Chat Agent (`/insights/agent`) — 12 tools, multi-model, configurable per-client
- ✅ OpenAI model support (GPT-4o, GPT-4o Mini) + API key management
- ✅ Internal Domains management UI on Clients page

### Completed (1 Apr 2026):
- ✅ QB Email-Based Matching — complete revamp (see section below)
- ✅ Jobs embellishment fields (8 "Has X?" fields synced from QB)
- ✅ Unique Emails tag fields (capabilities_used, processes_used, embellishments_used)
- ✅ Streamed sync for all 7 QB tables (consistent page-by-page, was buffered for 6/7)
- ✅ Per-table incremental timestamps (each table tracks its own last sync)
- ✅ Dedicated Supabase client for sync (no frontend blocking)
- ✅ Sync cancellation + auto-cancel on re-trigger
- ✅ Resumable re-match (incremental by default, optional full reset)
- ✅ RPC batch match writing (migration 050 — 500x fewer HTTP calls)
- ✅ Per-table sync buttons on QB Data + Config pages (incremental + full)
- ✅ QB httpx client: connection pooling, 120s read timeout, built-in retry

### Planned:
- Invite User System (admin-controlled onboarding)
- Email vectorisation during extraction
- Embedding model configuration (UI selector for embedding provider)
- Phase 2D: Enriched AI insights with precomputed analytics + vector context

**Five tracks:**

### S4.0 — Communication Guidelines in Prompt Templates

A "Communication Guidelines" block is added to all base prompt templates, shaping the tone and framing of every AI output across the platform.

| Item | Detail |
|------|--------|
| Storage | Existing `prompt_templates` table — prompt content update only |
| Editable | Via AI Playground (no code change needed to adjust later) |
| Version | Each updated template bumps version number — reprocessing flow handles re-analysis |
| Scope | Email analysis, daily/weekly digest, strategic digest, AI insights, AI Chat Agent |

**Guidelines baked into prompts:**
- Consultative, commercially grounded tone — outcome and risk focused, not vendor-pitched
- Lead with what matters, why it matters, and consequence of inaction
- Frame signals as: risks, opportunities, and recommended next actions with rationale
- Treat account silences, reorder patterns, and campaign timing as business signals
- Avoid superlatives, marketing fluff, and jargon without context

### S4.1 — QB Operations Table Sync + Capability Intelligence

**Table:** `bvqsudnif` (Operations — granular product/service detail per job)

| Key Field | QB Field ID | Purpose |
|-----------|-------------|---------|
| `operation_name` | 9 | Product/service identifier (e.g. "HP Indigo 4-col Process") |
| `department` | 11 | Production department ("Press", "Finishing", "Wide Format") |
| `job_no` | 7 | FK to `qb_jobs` (`buziry2ri`) |
| `qb_customer_id` | 14 | FK to `qb_customers` (`buzhzbv39`) |
| `quantity` | 20 | Units produced |
| `cost_plus_price` | 23 | Selling price |
| `profit_pct` | 25 | Margin % |
| `finishing_type` | 26 | e.g. "Perfect Bind", "Guillotine" |

**QB Data Model (confirmed Mar 2026):**
```
Customer → Unique Emails (1:many — all customer email addresses)
  → Contacts (many per email — multiple people share an email)
    → Quotes (linked to Unique Email + Contact)
      → Job (1 quote → 1 job, essentially 1:1 — 8 exceptions in 147K jobs)
        ├── Operations (many — each production step: "HP Indigo", "Scodix Foiling", etc.)
        ├── Sales Line Items (invoiced line items)
        └── Factory Rush Level (set at invoice time, not before)
```

**Key data facts:**
- ~70,000 operation records; 597 unique (dept, op, machine) tuples cover 100% of data
- `am_rush`: operation_name starts with `"RUSH: Approx"` — AM acknowledged rush at job creation
- `factory_rush`: `qb_jobs.factory_rush_level` IS NOT NULL — set when invoice generated. 253 of 295 factory-rush jobs had NO am_rush (customer got rush service without being charged)
- `has_outsource_component`: operation sent to external supplier — NOT an inhouse capability
- `contact_email` derived via: `qb_operations.job_no → qb_quotes.contact_email` (all data already synced)
- `factory_rush` derived via: `qb_operations.job_no → qb_jobs.factory_rush_level` (already synced as field 21)
- T-Cancelled (`production_status = 'T-Cancelled'`) filtered before storing — clean data in DB
- Industry classification: direct QB relationship on Operations table → joined via `matched_company_id → customer_companies.industry`

**WHAT NOT TO DO (critical):**
- Do NOT use raw operation names (423 values) for recommendations — 'Paper Stock Draw' is not a product
- Do NOT use department names as capability proxies — 'None' is the second-largest department (15K rows)
- Do NOT treat outsource operations (`has_outsource_component=TRUE`) as inhouse capabilities
- Do NOT include T-Cancelled jobs in any analysis (already handled at sync time)

**Capability Taxonomy (8 MVP tags):**

| Tag | Examples |
|-----|---------|
| Flat Sheets | HP Indigo, Komori offset, digital colour, VDP |
| Soft Cover Books | Perfect bind, saddle stitch, saddle sewn, wire bind |
| Hard Cover Books | Casebinding, section sewing, oversewing |
| Wide Format | WF Print, WF Laminating, WF Mounting |
| Embellishment | Scodix Foiling, Spot UV, Digital Foil, Embossing |
| Specialty Finishing | Zund cut types, Laser Cut, Die Cut |
| Design Services | Design/Artwork, Pre-Press |
| Display / Installation | Signage, display, installation |

Phase 2A will expand to ~30 granular sub-tags per MVP tag.

**Intelligence columns added to `qb_operations` (migration 035):**
- `capability_tags JSONB` — array of MVP tag names (GIN indexed)
- `has_coating`, `has_sewing`, `has_outsource_component` — operation flags from classifier
- `am_rush`, `factory_rush` — rush flags from QB data (separate, different sources)
- `row_type VARCHAR(20)` — production/process/outsource/logistics/leadtime/costing/rush_charge/admin/constraint
- `contact_email TEXT` — join via job_no → qb_quotes (enrichment step, no QB admin needed)

**New DB tables (migrations 032–035):**
- `qb_operations` (032) — raw QB operations cache
- `customer_recommendations`, `product_affinities` (034) — recommendation cache
- `client_taxonomy_config` (035) — generic per-client JSON config (capability tags, classifier rules, rush settings)
- `customer_intelligence_cache` (035) — per-company (+ contact_id for Phase 2B) computed profiles

**Backend changes:**
- `capability_classifier.py` — loads rules from DB, exact match on (dept, op, machine), keyword fallback, `reclassify_all()`
- `quickbase_sync.py` — `sync_operations()` + `enrich_operations()` (classify + contact_email + factory_rush joins)
- `intelligence_config.py` router — CRUD for taxonomy config, CSV import for classifier rules, reclassify trigger
- `/manage/intelligence-config` frontend — 4-tab page: Capability Tags, Classifier Rules (CSV import), Rush Settings, Cache & Rebuild

### S4.2 — Customer Profile Page Redesign

**Route:** Keep `/analytics/companies/:id` — redesign `company-detail.tsx` in-place as a 6-section full customer profile:

1. **Header** — company name, tier/lifecycle badges, AM, revenue YTD, days since last order
2. **Product Profile** — bar chart of product categories bought (revenue + frequency)
3. **Relationship Overview** — engagement score, email stats, first/last contact
4. **Contacts Table** — role, seniority, score, last email, products involved in, quote count
5. **Order History** — merged quotes + jobs + invoices timeline (date, type, ref, category, value, status, contact)
6. **Recommendations** — cross-contact gaps + related product affinities
7. **Communication Timeline** — recent threads + AI signals

**New API endpoints:** `/customers/{company_id}/order-history`, `/customers/{company_id}/product-profile`, `/customers/{company_id}/recommendations`

**New components:** `OrderHistoryTable.tsx`, `ProductProfileCard.tsx`, `RecommendationsPanel.tsx`

### S4.3 — Recommendation Engine (Two Levels, $0 cost)

#### Level 1: Cross-Contact Gaps (within a company)

**Algorithm:** `qb_operations.job_no → qb_quotes.job_no → qb_quotes.contact_email → customer_contacts.email_address`

For each contact: find operations the company has bought that this contact hasn't been involved in → recommendation to engage them on that product/service.

**Output example:**
```
"2 other contacts at Acme Co have ordered Wide Format — Jane Smith hasn't been involved"
```

#### Level 2: Related Product Affinities (across portfolio)

**Algorithm:** Market basket analysis on `capability_tags` (8 MVP tags, not raw operation names). Co-occurrence counting across all companies where `has_outsource_component=FALSE`. `confidence = companies_using_both / companies_using_A`. 8 tags = 8×8 = 64 pairs max — trivial to compute.

**Output example:**
```
"68% of customers using Embellishment also use Wide Format — Acme Co hasn't tried this"
```

**Caching:** 24h TTL in `customer_recommendations` table (same pattern as `relationship_context_cache`).

**Recommendations surfaced at:**
- Customer Profile → `RecommendationsPanel` component
- Smart Inbox → collapsible "Sales Opportunities" panel in email detail drawer
- Daily/Weekly Digest → "Sales Opportunities" section (top 5 companies)

### S4.4 — Vector Intelligence (✅ Complete) + AI Chat Agent (Planned)

**Embedding model:** `gemini-embedding-001` (Google, 768 dims via `output_dimensionality`) — `langchain-google-genai`

| What gets embedded | Table column | Embed text | Status |
|--------------------|-------------|-----------|--------|
| Raw emails | `emails.embedding` | subject + body_text (1000 chars) + sender | ✅ Live |
| Company profiles | `customer_companies.embedding` | name + industry + domains + QB tier/revenue/AM | ✅ Live |
| QB operations | `qb_operations.embedding` | operation + dept + machine + customer + capability_tags | ✅ Live |

**Independent of AI analysis pipeline** — embeds raw source data, not AI-processed fields.

**Migrations:** 037 (pgvector + HNSW indexes + 3 search RPC functions), 037b (reset to 768 dims), 039 (batch RPC updates)

**Backend (`vector_service.py`):**
- Non-blocking: all DB ops via `asyncio.to_thread`, runs as detached `asyncio.create_task`
- Batch embedding: 50 texts/API call, 2s delay, exponential backoff on 429
- Batch DB writes: 25 rows/RPC call (avoids statement timeout)
- Resilient: skips rate-limited batches + continues (no job-killing errors)
- Configurable: `?limit=10` for testing, `?tables=emails,companies` for per-table control
- Stop button: `POST /vector/reembed/stop` sets cancel flag checked between batches

**Frontend (`vector-search.tsx`):**
- Semantic search across emails, companies, operations with natural language
- Embedding coverage stats panel with per-table progress bars
- Per-table embed buttons: Embed Emails / Companies / Operations / All
- Stop button during embedding
- ClientSelector for multi-client support
- 8 suggested search prompts

**Planned — AI Chat Agent:**
- `ai_agent_service.py` — general portfolio Q&A with 6 tools (4 lookup + 2 semantic search)
- `POST /agent/chat` endpoint
- `agent.tsx` — chat UI at `/insights/agent`

---

## Sprint 4 Cost Impact

| Component | Cost |
|-----------|------|
| QB Operations sync | $0 |
| Recommendation Engine (Level 1 + Level 2) | $0 — pure Python |
| One-time bootstrap embedding | ~$0.15 total |
| Per-email vector context (1 search/company, not 1/email) | ~$0.0001/email |
| Digest semantic retrieval (3 queries/digest) | ~$0.001/digest |
| AI Chat Agent (Claude Sonnet, 5 AMs × 5 queries/day) | ~$3–8/month |
| **Total Sprint 4 monthly addition** | **~$3–8/month** |
| **New total (Sprint 3 + Sprint 4)** | **~$17–32/month** |

---

## ✅ COMPLETE — QB Email-Based Matching (1 Apr 2026)

Complete revamp of the QB↔SB customer matching system. Previously name-based (~44% match rate), now email-first via QB "Unique Emails" table.

### Architecture

**Matching priority (Pass 0 → Pass 3):**
1. **Pass 0 — Email lookup (primary):** SB contact email → `qb_unique_emails` → `qb_customer_id` → link SB company. Auto-write, 100% confidence.
2. **Pass 1 — Exact name:** Normalised QB customer name = SB company name.
3. **Pass 2 — Domain root:** SB company email domain root found in QB customer name.
4. **Pass 3 — Fuzzy (staging):** RapidFuzz token_sort_ratio ≥82% → staged for human review.

**Match rate improvement:** 44% → 56%+ (8,441/15,121 QB customers matched, 3,000+ via email lookup).

### New Tables & Migrations

| Migration | Purpose |
|-----------|---------|
| 047 | `qb_unique_emails` cache table + `unique_emails_table_id` on `qb_sync_config` |
| 048 | 8 "Has X?" embellishment columns on `qb_jobs` |
| 049 | `capabilities_used`, `processes_used`, `embellishments_used` on `qb_unique_emails` |
| 050 | `batch_write_qb_matches()` RPC — bulk writes N matches in 2 SQL statements |

### Extraction Pipeline Integration

The `CompanyResolver` (Step 4) now resolves companies in two phases:
1. **Phase 1 — QB email lookup:** Contact email → `qb_unique_emails` → QB customer name → company. QB metadata (`qb_customer_id`, `qb_match_method='email_lookup'`) written during upsert.
2. **Phase 2 — Domain fallback:** Remaining contacts resolved by email domain (existing logic).

Contact name matching against QB contacts runs in Step 6 (`_rematch_quickbase`).

### Sync Infrastructure Improvements

- All 7 QB tables use streamed (page-by-page) sync via `_sync_table_streamed()`
- Per-table incremental timestamps from `qb_sync_log` (not global `last_sync_at`)
- Operations sync log written before enrichment (restart-safe)
- Dedicated Supabase client for background sync/rematch (no frontend blocking)
- QB httpx client: persistent connection pool, 120s read timeout, 3-retry with backoff
- Sync cancellation via threading.Event, auto-cancel on re-trigger
- Re-match: incremental by default (only unmatched), optional `?reset=true` for full rebuild

### Key Files Changed

| File | Change |
|------|--------|
| `backend/src/services/quickbase_sync.py` | Streamed sync, email matching, RPC batch writes, cancellation |
| `backend/src/services/quickbase_client.py` | Unique emails field mappings, connection pooling, retry |
| `backend/src/services/company_resolver.py` | QB email lookup in Phase 1 of company resolution |
| `backend/src/services/extraction_orchestrator.py` | Email-based QB matching + contact name matching in Step 6 |
| `backend/src/routers/quickbase.py` | Dedicated sync client, cancel endpoint, health stats, per-table sync logs |
| `backend/src/models/quickbase.py` | `unique_emails_table_id` on config models |
| `frontend/src/pages/intelligence/quickbase-data.tsx` | Unique Emails tab, per-table sync buttons + timestamps, tag columns |
| `frontend/src/pages/intelligence/quickbase-matches.tsx` | Email-matched stats card, incremental/reset Re-Match dropdown |
| `frontend/src/pages/intelligence/quickbase-config.tsx` | Unique Emails table config, per-table sync dropdowns, merged field mappings |

---

## ✅ COMPLETE — CC/BCC Email Linking (1 Apr 2026)

Previously emails were linked to only one contact (the primary TO recipient). Now all participants (sender, TO, CC, BCC) are captured.

- **`email_contact_links` junction table** — many-to-many email↔contact/company with role (sender/to/cc/bcc)
- **441K+ junction links** across 261K emails — includes 53K CC'd emails
- **Backfill endpoint** — `/extraction/backfill-email-links` processes all mailboxes, populates junction table
- **Company/contact email counts** — RPCs `update_company_email_counts_from_junction` + `update_contact_email_counts_from_junction` refresh stored counts from junction data
- **Auto-refresh** — counts updated automatically after every extraction (lightweight + full)
- **Email endpoints** — `/contacts/{id}/emails` and `/companies/{id}/emails` query junction table (includes CC/BCC)
- Migrations: 053 (junction table), 054 (count RPCs)

## ✅ COMPLETE — Canonical Thread Resolution (3-5 Apr 2026)

Complete overhaul of email thread tracking. Previously threads were per-mailbox using provider thread IDs, causing duplicates when the same conversation existed in multiple mailboxes.

### Architecture

**4-Tier Signal Stack** (priority order):
1. **In-Reply-To → Message-ID** — definitive cross-mailbox match (31K matches)
2. **References header chain** — walk to earliest ancestor (6K matches)
3. **Subject + participant scoring** — heuristic with overlap ratio (88K matches)
4. **New thread** — no match found (90K new threads)

**Thread Status States:**

| Status | Definition | Action Required |
|--------|-----------|-----------------|
| `ongoing` | Active conversation, last email within 3 days | Monitor |
| `awaiting_response` | We sent last, waiting for contact reply | Follow up if stale |
| `awaiting_our_response` | Contact sent last, we need to reply | Respond |
| `overdue` | Waiting >7 days for response | Urgent attention |
| `dropped` | No activity >30 days | Consider re-engagement |
| `complete` | Natural end with sufficient back-and-forth | Archive |

**Results:** 52,821 unique threads from 135K emails across 6 mailboxes. 7,247 duplicates merged by subject normalization.

### Key Files
- `backend/src/services/canonical_thread_resolver.py` — 4-tier resolution engine
- `backend/src/services/thread_tracker.py` — Thread evaluation + status + subject merge
- Migration 055 — `canonical_thread_id`, `thread_match_method`, `thread_match_confidence` on emails

### Automatic Maintenance
New emails automatically get:
1. `canonical_thread_id` assigned (via `_assign_canonical_threads` in extraction)
2. Affected threads re-evaluated (via `_update_affected_threads`)
3. Contact + company email counts refreshed (via `_refresh_email_counts`)
No manual recompute needed for ongoing operation.

## ✅ COMPLETE — Frontend Stabilisation (5 Apr 2026)

Surgical upgrades to the existing React + Vite + Ant Design frontend — no migration to Next.js.

### TanStack Query (Upgrade 1)
- Replaced manual cache layer in `analyticsService.ts` (getCached/setCache/dedupedFetch stripped)
- `QueryClientProvider` in App.tsx with 30s staleTime, 5min gcTime
- Query hooks: `useCompanies`, `useContacts`, `useThreads`, `useFilterOptions`, etc.
- `keepPreviousData` for smooth pagination transitions
- Companies, contacts, threads pages migrated to hooks

### TanStack Table (Upgrade 2)
- `DataTable` component: TanStack Table + Ant Design Pagination/Skeleton
- `manualSorting: true` — SortingState drives server-side sort_by/sort_dir
- Column definitions via type-safe `createColumnHelper<T>()`
- Companies, contacts, threads "All" tabs use TanStack Table
- Secondary tabs (Top Engaged, At Risk) keep AnalyticsTable (Ant Design)

### SSE Streaming (Upgrade 3)
- Backend: `POST /ai/agent/chat/stream` with `StreamingResponse` + LangGraph `astream_events`
- Frontend: `agentChatStream()` with fetch + ReadableStream consumer
- Events: `token`, `tool_start`, `tool_end`, `done`, `error`
- Agent page shows tokens live as LLM generates, tools displayed in real-time
- Digest streaming deferred to post-launch

### UI Cleanup
- Terminology: "Messages" → "Emails" in all thread tables
- Contacts page: 3 tabs (removed Decision Makers, By Type), QB Linked filter
- Companies page: dynamic Tier/AM filters from backend, QB Matched toggle, Company column width fixed
- Thread tables: removed QB Type/Tier columns (low utility)
- All filter counts server-side (no client-side count mismatch)

---

## ✅ COMPLETE — Premium UI Overhaul: Ant Design → shadcn/ui + Tailwind CSS (7-8 Apr 2026)

Full migration from Ant Design to a premium B2B SaaS aesthetic (Linear, Vercel, Raycast style). **Zero antd imports remain.**

### Migration Scope

| Metric | Value |
|--------|-------|
| Files migrated | 35+ (18 pages, 12 shared components, 6 connection/form components) |
| Lines of antd CSS deleted | 1,855 (glass.css) + 114 (glassTheme.ts) + 78 (AnalyticsTable.tsx) |
| TypeScript errors | 0 |
| Production build | Clean (93KB CSS, down from ~150KB+) |

### New Design System

- **Component library:** shadcn/ui (new-york style) — Button, Card, Badge, Dialog, Sheet, DropdownMenu, Tabs, Tooltip, Avatar, Skeleton, Table, Select, Popover
- **Custom UI primitives:** StatusBadge (CVA variants), KPICard, PageShell, PageHeader, ContentSkeleton, EmptyState
- **Styling:** Tailwind CSS v3.4 with semantic color tokens (primary, destructive, warning, success, risk)
- **Icons:** Lucide React (37 mappings from @ant-design/icons)
- **Toasts:** Sonner (replaced 263 `message.*` calls)
- **Typography:** Inter via Google Fonts preconnect
- **Risk pattern:** Global `getRiskClass()` for consistent at-risk visual treatment

### Pages Migrated (zero antd)

| Category | Pages |
|----------|-------|
| Customers | companies, company-detail, contacts, contact-detail, threads |
| Insights | inbox, digest, opportunities, strategic-digest, vector-search, agent, email-rules |
| Manage | response-times, patterns, data-health, processing, errors, intelligence-config |
| Admin | users, clients, settings, extraction, admin-data, audit-logs, log-monitor |
| QuickBase | quickbase-config, quickbase-data, quickbase-matches |
| Mailbox | mailboxes, mailbox-process, mailbox create/edit forms |
| AI Usage | usage, playground |
| Auth | login, reset-password, oauth-callback |

### Components Migrated (zero antd)

ProtectedRoute, EmailDetailPanel, DataTable, AIInsightsCard, StrikeRateCard, SeasonalityChart, CapabilityRhythmCard, ContactCapabilitiesCard, ProductProfileCard, RecommendationsPanel, OrderHistoryTable, EngagementBadge, LifecycleBadge, ClientSelector, MailboxSelector, QBLinkWidget, ProcessingStatusBadge, SyncStatusBar, ErrorDisplay, FeedbackButtons, ActionBucketTag, ChartCard, MetricCard, GmailConnection, OutlookConnection, GoogleDriveConnection, GoogleDrivePicker, MailboxCreateForm, MailboxEditForm

### Infrastructure Changes

- **App.tsx:** Removed `ConfigProvider`, antd theme, glass.css import
- **Deleted:** `glass.css` (1,855 lines), `glassTheme.ts` (114 lines), `AnalyticsTable.tsx` (unused)
- **Global client context:** `useClient()` hook replaced per-page ClientSelector on admin/manage pages
- **TanStack Query for mailboxes:** `useMailboxes()` + `useProcessingJobs()` hooks replace manual polling
- **Number formatting:** `'en-AU'` locale enforced globally via `formatNumber()` utility — zero bare `.toLocaleString()` calls remain
- **Live revenue computation:** Company detail Business Data now computes revenue from actual order history (accepted quotes + jobs) instead of stale QB `total_invoiced` field; `days_since_last_invoice=9999` sentinel hidden
- **Nav restructure:** Threads moved to Emails dropdown (All Emails + Threads); Customers simplified to Companies + Contacts

---

## ✅ COMPLETE — Data Accuracy & Thread Stability Fixes (8 Apr 2026)

Targeted fixes for QB revenue accuracy, thread deduplication root causes, and UI correctness.

### Revenue & QB Data Accuracy

| Fix | Detail |
|-----|--------|
| Live revenue computation | Company Business Data computes revenue from actual accepted quotes + jobs (not stale `total_invoiced` QB field). Artis: displayed $410 → corrected to ~$500K |
| 9999 sentinel hidden | `days_since_last_invoice = 9999` (QB placeholder for "no order") no longer displayed |
| Strike rate — all QB keys | Strike rate now fetches ALL QB customer records for a company; was `limit(1)`, silently missing quotes tied to secondary QB customer records |

### Thread Deduplication (Root Cause Fix)

| Fix | Detail |
|-----|--------|
| Delete-then-insert | `save_thread_statuses` replaced broken upsert with delete-then-insert to prevent ghost duplicate rows |
| Migration 060 | `UNIQUE(thread_id)` constraint on `thread_status` — prevents future duplicates at the DB level |
| Two-pass server dedup | Query-time dedup: first collapse by `canonical_thread_id`, then by subject+contact for threads still unresolved |
| Outlook UUID5 hashing | Outlook base64 thread IDs deterministically hashed to UUID5 values for stable cross-request identity |
| Page size 200 → 500 | Extraction page size increased to reduce API timeouts on large mailboxes |

### Threads Page UI Fixes

- **Count query** — fixed `or_()` filter mismatch that was returning 0 for all thread count queries
- **Nav highlight** — `/customers/threads` now correctly highlights only the Emails menu item (not Customers)
- **Contact names** — strip `"| Company"` suffix from contact display names in thread list

### Data Health Page Additions

- **Thread Health card** — shows total thread count, unique threads, and duplicate count
- **Recompute Threads button** — triggers full thread recompute with real-time Redis progress bar
- **Mailbox error tracking** — displays which mailbox timed out during thread computation with a per-mailbox retry button

### Intent-Based Thread Status (Migration 062)

New columns on `thread_status` wired for future AI-driven status overrides:

| Column | Purpose |
|--------|---------|
| `intent_status` | AI override: `urgent`, `revenue_opportunity`, `closing`, `escalation`, `informational`. NULL = use timing status |
| `intent_override_reason` | Human-readable reason for the override |
| `last_email_intent` | Intent class of the most recent email in thread |
| `last_email_urgency` | Urgency level of most recent email |
| `last_email_sentiment` | Sentiment of most recent email |

Indexes: `idx_thread_status_intent` (WHERE intent_status IS NOT NULL) + `idx_thread_status_last_intent` (WHERE last_email_intent IS NOT NULL).

---

## ✅ COMPLETE — QB Data Cleanup & Match Integrity (14 May 2026)

Comprehensive cleanup of QB matching data and permanent architectural fix for contamination (multiple QB customers matching to the same SB company).

### Contact Backfill (Migration 112)

| Item | Detail |
|------|--------|
| `backfill_contacts_to_matched_companies` RPC | 3-pass: (1) link contacts to matched companies via QB email chain, (2) backfill `emails.customer_company_id`, (3) backfill `email_contact_links.company_id` |
| Wired into 6 entry points | Main sync, rematch, extraction pipeline, manual link, review accept, bulk review |
| Email count refresh | Calls `update_company_email_counts_from_junction` after backfill when count > 0 |
| Initial run results | 1 contact linked, 10,758 emails backfilled, 16,639 junction links backfilled |

### 1:1 Match Enforcement (Migrations 113–114)

| Item | Detail |
|------|--------|
| `batch_write_qb_matches` rewrite (113) | DISTINCT ON dedup within batch + NOT EXISTS guard against cross-batch duplicates |
| Python-side company_id dedup | Pre-dedup in `_rpc_batch_write_matches` before sending to RPC |
| Fallback path removed | Unguarded direct-write fallback (root cause of contamination) deleted entirely |
| `_enforce_1to1_matches` cleanup RPC (114) | Keeps highest-revenue QB customer per company, unmatches rest |
| Unique partial index (114) | `idx_qb_customers_unique_match ON qb_customers (client_id, matched_company_id) WHERE matched_company_id IS NOT NULL` — physically prevents contamination |

### Data Cleanup

| Item | Detail |
|------|--------|
| Orphan companies deleted | 583 companies with no contacts, no emails, no QB match, no pending candidates |
| Stale candidates dismissed | 1,089 candidates for already-matched QB customers marked as reviewed |
| Contamination cleared | All multi-match contamination resolved to 0, verified stable |

### UI Enhancement

| Item | Detail |
|------|--------|
| "Has emails" filter | Default filter on companies list page hides 0-email companies; toggle to show all |

---

## Next Sprint — Pending Items (Starting 29 May 2026)

### High Priority

| Item | Detail | Effort |
|------|--------|--------|
| Candidates count mismatch | Tab badge shows 228 vs browse total 240 — different query definitions (tab counts unreviewed, browse shows all pending+unreviewed) | 2h |
| Contact creation from QB data | 1,344 unmatched QB customers have emails in `qb_unique_emails` but no corresponding SB contacts — need to create contacts from QB data to enable matching | 1 day |
| Fix email count sorting in matched view | Sorting by email count in QB matched companies doesn't work correctly | 2h |
| Method filter dropdown fix | QB review page method filter parked from earlier sessions | 2h |

### Medium Priority

| Item | Detail | Effort |
|------|--------|--------|
| Invite User System | Admin-controlled onboarding, restrict open sign-up. Fully designed (`docs/INVITE_USER_SMTPLESS.md`) | 3 days |
| Manual-only unmatched cleanup | 942 "No link (manual)" unmatched QB customers with $0 revenue — decide: auto-dismiss or leave for review | 1h |

### Architectural Gaps

1. **No invite-only access control** — open sign-up currently. Invite system fully designed but not built.
2. **Email vectorisation during extraction** — New emails are not automatically vectorised. Needs integration into extraction pipeline (post-Step 9).
3. **Embedding model not configurable** — Hardcoded to Google `gemini-embedding-001`. UI selector planned.
4. **QB tag data → analytics/AI** — Capabilities, processes, embellishments now synced on unique emails; need to wire into customer profiling, AI agent tools, and digest generation.

---

## Minor Outstanding Items (Backlog)

| Item | Priority | Effort |
|------|----------|--------|
| Processing page status filter dropdown | Medium | 2h |
| Remove debug console.logs (MailboxSelector.tsx, emails.tsx) | Low | 1h |
| E2E tests for mailbox switching flow | Medium | 1 day |
| Unit tests for email loading guards | Medium | 0.5 day |
| Virtual scrolling for large email lists | Low | 1 day |
| Dark mode | Low | 2 days |
| Advanced search (boolean operators, saved searches) | Low | 2 days |
