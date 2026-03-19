# Email Intelligence Platform — Consolidated Implementation Progress

**Last Updated:** 19 March 2026
**Purpose:** Business partner reference — completed work, architecture, database schema, and next priorities.

---

## Platform Overview

A commercial intelligence platform for B2B account management teams. It syncs email from Gmail and Outlook, runs AI analysis on every email, and surfaces actionable insights about customers, deals, and relationship health — enriched with CRM (QuickBase) data.

**Deployment:** Production on Railway.
**Backend:** FastAPI (Python 3.13), 14 registered routers, ~150+ API endpoints.
**Frontend:** React/TypeScript (Vite), 30+ pages.
**Database:** Supabase PostgreSQL, ~34 tables.
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
| Sprint 4 — Power Mode | Deal Radar, Ghost Writer, Heatmap, War Room, Alerts, Scoreboard, Report | 🔲 Planned | Not started |

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

## Database: Complete Table Inventory (~34 tables)

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

### Post-Sprint 3 Config Tables

| Table | Purpose |
|-------|---------|
| `system_settings` | Client-scoped key-value settings (client_id + key + value) — e.g. AI model selection, budget cap |
| `ai_prompt_config` | Configurable AI prompts — client_id (NULL = global), prompt_key, prompt_text, version, is_active |
| `business_entities` | Aggregated entity tracking — competitors, products, people mentioned across emails |

---

## Backend Architecture

### API Routers (14 registered in `main.py`)

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
| `websocket` | `/ws` | Real-time job progress streaming |

Plus inline endpoints on `main.py`: mailbox management, processing jobs, file upload, Google Drive streaming.

### Service Layer (31 services in `backend/src/services/`)

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

Sprint 4 additions (Ghost Writer + Executive Report): +~$2.80/month → well within budget.

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

## 🔲 PLANNED — Sprint 4: Power Mode (7 features, Not started)

**Full technical plan:** `docs/SPRINT3_4_IMPLEMENTATION_PLAN.md`

### C1. Deal Radar — Predictive Revenue Intelligence
**What it does:** Scores every active deal thread with a probability (0–100%) and trajectory (rising/falling/flat). Flags deals about to close and deals going cold.
**Data sources:** AI classifications + QB quote data + email silence signals
**Cost:** $0 (pure Python computation)
**UI:** `/intelligence/deal-radar` — pipeline cards with trajectory arrows

### C2. Ghost Writer — AI Reply Suggestions
**What it does:** On demand, suggests 3 draft replies for any email thread: Quick / Thorough / Escalate. Uses full thread context + customer QB profile.
**Cost:** ~$1.80/month (Claude Haiku, cached 24h)
**UI:** "Suggested Replies" section in Smart Inbox email drawer with Copy button

### C3. Relationship Heatmap — Visual Account Health
**What it does:** Grid/treemap where colour = engagement health (green/yellow/red) and size = QB revenue. Instant portfolio health overview.
**Cost:** $0 (frontend-only, uses existing data)
**UI:** `/analytics/heatmap` — hover tooltip, click → company detail, filter by AM

### C4. War Room — Competitive Intelligence Dashboard
**What it does:** Aggregated view of competitor mentions across all emails — which competitors are being named, which accounts are at risk, win/loss patterns.
**Cost:** $0 (uses existing entity extraction)
**UI:** `/intelligence/war-room` — bar chart, active battles with deal values

### C5. Executive Briefing — PDF Report
**What it does:** Generates a PDF combining strategic digest + deal radar + heatmap + AM performance. One-click board-ready report.
**Cost:** ~$1/month (Claude Sonnet for narrative, reportlab/weasyprint for PDF)
**UI:** "Generate Report" button on strategic digest + dashboard

### C6. Smart Alerts — Proactive Notifications
**What it does:** Triggers in-app alerts when: churn risk on >$50K account, buying signal from prospect, competitor mentioned, missed opportunity >24h, deal probability drops >15 points.
**Cost:** $0 (rule-based, no AI)
**UI:** Notification bell in header + alert preferences in settings

### C7. AM Scoreboard — Performance Leaderboard
**What it does:** Gamified AM performance scores based on response speed, SLA compliance, signals actioned, customers retained, new customers acquired.
**Cost:** $0 (computed from existing data)
**UI:** Leaderboard on main dashboard + `/intelligence/scoreboard` page

**Sprint 4 effort estimate: 3 weeks**

---

## Key Gaps for Business Partner Review

1. **No invite-only access control** — open sign-up currently. Any user who knows the URL can register. Invite system is designed but not built.

2. **No proactive alerts** — the platform surfaces insights reactively (user must log in). Smart Alerts (C6) would push notifications when a high-value account goes silent or a buying signal appears.

3. **No deal pipeline view** — quotes and jobs are visible in QB data but there is no deal probability scoring or pipeline stage tracking. Deal Radar (C1) fills this gap.

4. **No PDF reporting** — insights live only in the app. Executive Briefing (C5) would produce a shareable PDF.

5. **No reply drafting** — AMs must write their own emails. Ghost Writer (C2) would suggest drafts using full thread + customer context.

6. **No visual portfolio overview** — health of all accounts requires navigating individual pages. Heatmap (C3) gives instant visual overview.

7. **No AM performance gamification** — AM comparison metrics exist in strategic digest but no persistent scoreboard or trend tracking. Scoreboard (C7) adds this.

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
