# Sprint 2: Customer Data Extraction Pipeline — Implementation Guide

> **Version:** 5.0 Production-Ready | **Date:** February 27, 2026
> **Stack:** Python 3.11+ / FastAPI / Supabase (PostgreSQL) / Railway
> **Sprint Status:** ALL PHASES COMPLETE ✅ | Production Tested (26,000+ emails) ✅ | Analytics Frontend COMPLETE ✅
> **Depends On:** Sprint 1 (complete) | **Prepares For:** Sprint 3 (AI Semantic Intelligence)

---

## 🎉 Phase 5A & 5B Implementation Complete

**Completion Date:** February 16, 2026

### What Was Implemented

**Phase 5A: Analytics API (30 endpoints)**
- ✅ Complete analytics models (41 Pydantic models + 5 enums)
- ✅ 30 REST API endpoints across 7 categories
- ✅ Extraction control, contact analytics, company analytics
- ✅ Thread analytics, response times, communication patterns, dashboards
- ✅ Total: 2,886 lines of code

**Phase 5B: Incremental Extraction Mode**
- ✅ Migration 010 created and tested
- ✅ Support for full and incremental extraction modes
- ✅ Configurable lookback periods (1-365 days)
- ✅ 8 new columns, 3 performance indexes
- ✅ Master schema updated to v1.8

**Testing Status:**
- ✅ All analytics endpoints tested
- ✅ Incremental mode tested
- ✅ Master schema updated

**Files Created:**
- `backend/src/models/analytics.py` (581 lines)
- `backend/src/routers/analytics.py` (2,305 lines)
- `scripts/sprint2/sprint2_migration_010_incremental_mode.sql` (171 lines)

**Files Modified:**
- `backend/src/services/extraction_orchestrator.py`
- `backend/src/main.py`
- `scripts/sprint2/SPRINT2_MASTER_SCHEMA.sql` (updated to v1.8)

---

## Stability & Performance Fixes (Feb 23-24, 2026)

### Performance Fixes
| Fix | File | Impact |
|-----|------|--------|
| Removed `error_log` from `/processing-jobs` SELECT | `backend/main.py` | **620KB → ~20KB response** |
| Added `.limit(100)` to processing-jobs query | `backend/main.py` | Prevents unbounded queries |
| Removed nested retry in mailboxService | `frontend/src/services/mailboxService.ts` | Eliminates 9x retry amplification |
| Removed nested retry in dashboardService | `frontend/src/services/dashboardService.ts` | Eliminates 9x retry amplification |
| Cleaned debug logging from apiClient | `frontend/src/services/apiClient.ts` | Cleaner console, less overhead |
| Removed `JSONResponse` wrapper + `response_model=list` | `backend/main.py` | Simpler serialization path |

### WebSocket Fixes
- Fixed "WebSocket is not connected. Need to call 'accept' first" errors
- Accept WebSocket before closing/sending in `routes.py` exception handlers
- Added RuntimeError-specific handling in `manager.py` send_personal

### Email Address Guardrails
- Auto-populate `email_address` after Gmail/Outlook OAuth linking (4 handlers in `mailboxes.tsx`)
- Post-OAuth email validation prevents mismatched account linking
- Backend validation in `update_mailbox` prevents email changes when connection exists
- `email_address` field read-only in both create and edit forms

### LIVE Sync Fixes
- Dashboard shows "Sync" button for MBOX/OLM mailboxes with live sync linked (`hasLiveSync` check)
- Fixed `last_sync_at` not updating on `mailboxes` table after Gmail/Outlook sync completion
- Both `gmail_sync_service.py` and `outlook_sync_service.py` now update top-level `last_sync_at`
- Fixed date-range fetch and "View Sync History" navigation to include mailbox ID

### Environment Changes
- Frontend port changed from 3000 to 3001 (avoid conflicts)
- CORS `ALLOWED_ORIGINS` updated to `http://localhost:3001`
- Google/Microsoft OAuth redirect URIs updated to port 3001

**Files Modified:**
- `backend/main.py` — processing-jobs query optimization, mailboxes endpoint cleanup
- `backend/src/websocket/routes.py` — WebSocket accept-before-close fix
- `backend/src/websocket/manager.py` — RuntimeError handling in send_personal
- `backend/src/services/gmail_sync_service.py` — Update top-level `last_sync_at`
- `backend/src/services/outlook_sync_service.py` — Update top-level `last_sync_at`
- `frontend/src/services/apiClient.ts` — Debug logging cleanup
- `frontend/src/services/mailboxService.ts` — Simplified retry logic
- `frontend/src/services/dashboardService.ts` — Simplified retry logic, `hasLiveSync` field
- `frontend/src/pages/dashboard.tsx` — `hasLiveSync` check for Sync/Process button
- `frontend/src/pages/mailboxes.tsx` — Email guardrails, navigation fixes
- `frontend/src/components/MailboxEditForm.tsx` — Email field read-only
- `frontend/src/components/MailboxCreateForm.tsx` — Email field read-only
- `frontend/vite.config.ts` — Port 3001
- `frontend/.env.development` — Updated redirect URIs
- `backend/.env.development` — Updated CORS + redirect URIs

---

## Production Deployment Fixes (Feb 25-26, 2026)

Critical fixes discovered and resolved during production deployment with 26,654 emails:

### Fix 1: NULL processing_status Exclusion
**Problem:** PostgreSQL `neq('processing_status', 'failed')` silently excludes NULL rows because `NULL != 'failed'` evaluates to NULL (not TRUE). This caused emails with NULL processing_status to be excluded — only 999 of 26,654 emails were being processed.

**Solution:** Removed server-side `.neq('processing_status', 'failed')` filter. Added `processing_status` to SELECT columns and filter in Python:
```python
filtered = [e for e in batch if e.get('processing_status') != 'failed']
```
Python's `None != 'failed'` evaluates to `True`, correctly including NULL rows.

**Files Modified:** extraction_orchestrator.py, contact_extractor.py, email_linker.py, response_time_tracker.py, thread_tracker.py, comm_pattern_analyzer.py

### Fix 2: Supabase `.or_()` Compatibility
**Problem:** Production supabase-py version lacks `SyncSelectRequestBuilder.or_()` method. Initial fix using `.or_('processing_status.neq.failed,processing_status.is.null')` threw `AttributeError`.

**Solution:** Python-side filtering (Fix 1 above) is compatible with all supabase-py versions.

### Fix 3: Pagination Off-by-One
**Problem:** Supabase `.range(0, 499)` returns 499 rows (not 500) in production. The break condition `len(raw_batch) < PAGE_SIZE` (499 < 500) terminated pagination after page 1, processing only 499 of 26,654 emails.

**Solution:** Changed all pagination loops across 5 services (8 locations):
```python
# Before (broken):
if len(raw_batch) < PAGE_SIZE:
    break
offset += PAGE_SIZE

# After (fixed):
if len(raw_batch) == 0:
    break
offset += len(raw_batch)
```

### Fix 4: Transient Supabase SSL Errors
**Problem:** Cloudflare SSL 525 handshake failures occurring intermittently during large extractions.

**Solution:** Added `_execute_with_retry()` static method to all three paginating services (orchestrator, contact_extractor, email_linker) with exponential backoff:
```python
@staticmethod
def _execute_with_retry(query_builder, max_retries=3, base_delay=2.0):
    # Retries on: SSL 525, 502/503/504, connection reset, timeout
    # Backoff: 2s, 4s, 8s
```

### Fix 5: Total Count Visibility
**Problem:** No visibility into total emails or page count during extraction.

**Solution:** Added upfront COUNT query before pagination loop, logging "page X/Y: raw=N, kept=M, total so far=T" format for each page.

### Production Fixes Summary
| Fix | Files Modified | Impact |
|-----|---------------|--------|
| NULL processing_status | 6 services | All emails now included (26,654 vs 999) |
| .or_() compatibility | 6 services | Works with all supabase-py versions |
| Pagination off-by-one | 5 services (8 locations) | All 54 pages processed correctly |
| SSL retry logic | 3 services | Resilient to transient Cloudflare errors |
| Count visibility | 3 services | Clear logging of extraction progress |

---

## Post-Production Fixes (Feb 26-27, 2026)

Fixes discovered during analytics frontend testing with real production data:

### Fix 1: Uniform Engagement Scores (Contacts=33, Companies=51)
**Problem:** All contacts had engagement_score=33 and all companies had engagement_score=51. Scores should vary based on actual email patterns.

**Root Cause (4 issues):**
1. `comm_pattern_analyzer.save_patterns()` was NOT sending `emails_per_month_avg`, `last_inbound_at`, `last_outbound_at` to the database
2. Field name mismatch: code sent `engagement_trend` but column is `frequency_trend`
3. Company scorer had hardcoded `reply_rate_score=70.0` and `recency_score=60.0` instead of real data
4. These NULL fields caused the engagement scorer to use neutral fallback values → uniform scores

**Solution:**
- Fixed `comm_pattern_analyzer.py` to include all missing fields in save_patterns()
- Fixed field name from `engagement_trend` to `frequency_trend`
- Added `_score_company_recency()` method to `engagement_scorer.py` using real `last_contact_date`
- Changed company `reply_rate_score` from hardcoded `70.0` to neutral `50.0`
- Created Migration 012 to backfill scoring input fields from email data

**Files Modified:** `backend/src/services/comm_pattern_analyzer.py`, `backend/src/services/engagement_scorer.py`

### Fix 2: Migration 012 — Backfill Scoring Input Fields
**Problem:** Existing contacts/companies had NULL scoring fields because the pipeline never populated them.

**Solution:** 6-part SQL backfill migration (`scripts/sprint2/sprint2_migration_012_backfill_scoring_fields.sql`):
1. Backfill `last_inbound_at` / `last_outbound_at` from emails table
2. Backfill `emails_per_month_avg` from email counts and date ranges
3. Backfill `initiation_ratio` from thread_status + first email sender
4. Backfill `reply_rate` from inbound/outbound email counts
5. Backfill company `avg_emails_per_month` from email counts
6. Backfill `frequency_trend` from recent vs older email volume

### Fix 3: Migration 011 — Fix RPC Functions
**Problem:** Analytics RPC functions had incorrect query logic for email counts, contact dates, and thread data.

**Solution:** Migration 011 (`scripts/sprint2/sprint2_migration_011_fix_analytics_data.sql`) fixes RPC function logic.

### Fix 4: Min Engagement Score 500 Error
**Problem:** Ant Design v5 Slider sends float values (e.g., `29.0`). PostgreSQL rejects `"29.0"` for INTEGER column `engagement_score` with error: `invalid input syntax for type integer: "29.0"`.

**Solution:** Cast `min_engagement_score` to `int()` before passing to Supabase `.gte()` filter — applied to 4 locations (contacts query + count, companies query + count).

**File Modified:** `backend/src/routers/analytics.py`

### Fix 5: "Unknown" Seniority Label Display
**Problem:** Contact detail page showed "unknown" as a visible `<Tag>` element when `seniority_level='unknown'`.

**Solution:** Added guard `contact.seniority_level !== 'unknown'` to JSX rendering.

**File Modified:** `frontend/src/pages/analytics/contact-detail.tsx`

### Fix 6: Engagement Score UX Improvements
**Problem:** Score column showed raw numbers (43, 33, 0) without context. Slider triggered API on every drag pixel.

**Solution:**
- `EngagementBadge` now shows label + score: "High 85", "Medium 43", "Low 22"
- Slider uses `onChangeComplete` (fires on release) instead of `onChange` (fires on every pixel)

**Files Modified:** `frontend/src/components/analytics/EngagementBadge.tsx`, `frontend/src/pages/analytics/contacts.tsx`, `frontend/src/pages/analytics/companies.tsx`

### Analytics Frontend (Complete)
| Page | Route | Features |
|------|-------|----------|
| Dashboard | `/analytics` | Client selector, overview metrics, extraction trigger |
| Contacts | `/analytics/contacts` | All/Top/At-Risk/DMs/By-Type tabs, sort, filter, score slider |
| Companies | `/analytics/companies` | All/Top/At-Risk/By-Engagement tabs, sort, filter, score slider |
| Threads | `/analytics/threads` | All/Overdue/By-Status tabs, status chart, sort, filter |
| Contact Detail | `/analytics/contacts/:id` | Stats, threads, communication patterns |
| Company Detail | `/analytics/companies/:id` | Stats, top contacts, threads |
| Admin Data View | `/admin/data` | Raw table browser, search, sort, pagination, CSV export |

### Post-Production Fixes Summary
| Fix | Files Modified | Impact |
|-----|---------------|--------|
| Uniform engagement scores | comm_pattern_analyzer.py, engagement_scorer.py | Scores now vary based on real email patterns |
| Migration 012 backfill | sprint2_migration_012 | Existing data populated for scoring |
| Migration 011 RPC fix | sprint2_migration_011 | Correct analytics data queries |
| Min score 500 error | analytics.py router | Float-to-int casting for Supabase filters |
| Unknown seniority label | contact-detail.tsx | Hidden when value is 'unknown' |
| Engagement UX | EngagementBadge, contacts, companies | Label display + slider onChangeComplete |

---

## Table of Contents

1. [Project Setup](#1-project-setup)
2. [Database Migrations](#2-database-migrations)
3. [FastAPI Project Structure](#3-fastapi-project-structure)
4. [Utility Modules](#4-utility-modules)
5. [Core Extraction Pipeline](#5-core-extraction-pipeline)
6. [Email Rules Intelligence](#6-email-rules-intelligence)
7. [Engagement Analytics Suite](#7-engagement-analytics-suite)
8. [API Endpoints](#8-api-endpoints)
9. [Task Checklist](#9-task-checklist)
10. [Edge Cases & Notes](#10-edge-cases--notes)

---

## 1. Project Setup

### 1.1 Dependencies

```txt
# requirements.txt
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
supabase>=2.3.0
asyncpg>=0.29.0
pydantic>=2.5.0
pydantic-settings>=2.1.0
python-jose[cryptography]>=3.3.0
httpx>=0.26.0
python-dateutil>=2.8.0
```

### 1.2 Environment Variables

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
DATABASE_URL=postgresql://...  # Direct connection for asyncpg batch ops
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
MICROSOFT_CLIENT_ID=...
MICROSOFT_CLIENT_SECRET=...
DEFAULT_SLA_HOURS=4
BATCH_SIZE=500
```

### 1.3 Config Module

```python
# app/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    supabase_url: str
    supabase_key: str
    supabase_service_role_key: str
    database_url: str
    google_client_id: str = ""
    google_client_secret: str = ""
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    default_sla_hours: int = 4
    batch_size: int = 500
    
    class Config:
        env_file = ".env"

settings = Settings()
```

---

## 2. Database Migrations

Run these in Supabase SQL Editor in order.

### 2.1 New Tables

```sql
-- =========================================================================
-- Sprint 2 Migration 001: Supporting Tables
-- =========================================================================

-- Internal domains (exclude from customer extraction)
CREATE TABLE IF NOT EXISTS internal_domains (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    domain TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(client_id, domain)
);

CREATE INDEX IF NOT EXISTS idx_internal_domains_client ON internal_domains(client_id);
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE internal_domains TO anon, authenticated;

-- Free email providers
CREATE TABLE IF NOT EXISTS free_email_providers (
    domain TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO free_email_providers (domain) VALUES
    ('gmail.com'), ('yahoo.com'), ('hotmail.com'), ('outlook.com'),
    ('aol.com'), ('icloud.com'), ('mail.com'), ('protonmail.com'),
    ('yandex.com'), ('zoho.com'), ('live.com'), ('msn.com'),
    ('me.com'), ('mac.com'), ('fastmail.com'), ('hey.com'),
    ('pm.me'), ('proton.me'), ('tutanota.com'), ('gmx.com'),
    ('ymail.com'), ('rocketmail.com'), ('outlook.in'), ('rediffmail.com')
ON CONFLICT DO NOTHING;

GRANT SELECT, INSERT, DELETE ON TABLE free_email_providers TO anon, authenticated;

-- Extraction jobs tracking
CREATE TABLE IF NOT EXISTS extraction_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    mailbox_id UUID REFERENCES mailboxes(id) ON DELETE CASCADE,
    client_id UUID REFERENCES clients(id) ON DELETE SET NULL,
    job_id UUID REFERENCES processing_jobs(id) ON DELETE SET NULL,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending','processing','completed','failed','cancelled')),
    
    -- Progress counters
    total_emails INTEGER DEFAULT 0,
    processed_emails INTEGER DEFAULT 0,
    contacts_created INTEGER DEFAULT 0,
    contacts_updated INTEGER DEFAULT 0,
    companies_created INTEGER DEFAULT 0,
    companies_updated INTEGER DEFAULT 0,
    rules_created INTEGER DEFAULT 0,
    emails_linked INTEGER DEFAULT 0,
    threads_analyzed INTEGER DEFAULT 0,
    
    -- Current step tracking
    current_step TEXT,  -- e.g., 'upsert_companies', 'compute_response_times'
    current_step_number INTEGER DEFAULT 0,
    total_steps INTEGER DEFAULT 13,
    
    errors JSONB DEFAULT '[]'::jsonb,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_extraction_jobs_mailbox ON extraction_jobs(mailbox_id);
CREATE INDEX IF NOT EXISTS idx_extraction_jobs_status ON extraction_jobs(status);
CREATE TRIGGER update_extraction_jobs_updated_at BEFORE UPDATE
    ON extraction_jobs FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
GRANT SELECT, INSERT, UPDATE ON TABLE extraction_jobs TO anon, authenticated;
```

### 2.2 Unified Email Rules Table

```sql
-- =========================================================================
-- Sprint 2 Migration 002: Unified Email Rules
-- =========================================================================

CREATE TABLE IF NOT EXISTS unified_email_rules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    mailbox_id UUID REFERENCES mailboxes(id) ON DELETE CASCADE,
    client_id UUID REFERENCES clients(id) ON DELETE SET NULL,
    
    -- Source tracking
    source_type TEXT NOT NULL CHECK (source_type IN ('gmail_api', 'outlook_api', 'json_import', 'manual')),
    source_rule_id TEXT,          -- Original rule ID from Gmail/Outlook (null for manual)
    rule_name TEXT,               -- Human-readable name
    is_active BOOLEAN DEFAULT TRUE,
    priority INTEGER DEFAULT 0,   -- Lower = higher priority
    
    -- Conditions (normalized)
    condition_from_addresses TEXT[] DEFAULT '{}',
    condition_from_domains TEXT[] DEFAULT '{}',
    condition_to_addresses TEXT[] DEFAULT '{}',
    condition_subject_contains TEXT[] DEFAULT '{}',
    condition_body_contains TEXT[] DEFAULT '{}',
    condition_has_attachment BOOLEAN,
    condition_importance TEXT,
    condition_raw JSONB,          -- Original conditions for reference
    
    -- Actions (normalized)
    action_label TEXT,
    action_move_to_folder TEXT,
    action_forward_to TEXT[] DEFAULT '{}',
    action_mark_important BOOLEAN,
    action_mark_read BOOLEAN,
    action_skip_inbox BOOLEAN,
    action_delete BOOLEAN,
    action_raw JSONB,             -- Original actions for reference
    
    -- Intelligence (derived)
    engagement_signal TEXT CHECK (engagement_signal IN ('high_value', 'low_priority', 'escalation', 'segmentation', 'neutral')),
    matched_company_id UUID REFERENCES customer_companies(id) ON DELETE SET NULL,
    matched_contact_id UUID REFERENCES customer_contacts(id) ON DELETE SET NULL,
    
    -- Timestamps
    synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(mailbox_id, source_type, source_rule_id)
);

CREATE INDEX IF NOT EXISTS idx_unified_rules_mailbox ON unified_email_rules(mailbox_id);
CREATE INDEX IF NOT EXISTS idx_unified_rules_client ON unified_email_rules(client_id);
CREATE INDEX IF NOT EXISTS idx_unified_rules_source ON unified_email_rules(source_type);
CREATE INDEX IF NOT EXISTS idx_unified_rules_signal ON unified_email_rules(engagement_signal);
CREATE INDEX IF NOT EXISTS idx_unified_rules_company ON unified_email_rules(matched_company_id);
CREATE TRIGGER update_unified_rules_updated_at BEFORE UPDATE
    ON unified_email_rules FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE unified_email_rules TO anon, authenticated;
```

### 2.3 Engagement Analytics Tables

```sql
-- =========================================================================
-- Sprint 2 Migration 003: Engagement Analytics Tables
-- =========================================================================

-- Response time tracking (per inbound-outbound pair)
CREATE TABLE IF NOT EXISTS email_response_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    thread_id TEXT NOT NULL,
    mailbox_id UUID REFERENCES mailboxes(id) ON DELETE CASCADE,
    inbound_email_id UUID REFERENCES emails(id) ON DELETE CASCADE,
    outbound_email_id UUID REFERENCES emails(id) ON DELETE SET NULL,  -- null if unanswered
    customer_contact_id UUID REFERENCES customer_contacts(id) ON DELETE SET NULL,
    customer_company_id UUID REFERENCES customer_companies(id) ON DELETE SET NULL,
    inbound_at TIMESTAMPTZ NOT NULL,
    responded_at TIMESTAMPTZ,            -- null if unanswered
    response_time_seconds INTEGER,       -- null if unanswered
    is_within_sla BOOLEAN,
    is_business_hours_only BOOLEAN DEFAULT FALSE,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('responded', 'open', 'no_response_needed')),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_response_metrics_thread ON email_response_metrics(thread_id);
CREATE INDEX IF NOT EXISTS idx_response_metrics_mailbox ON email_response_metrics(mailbox_id);
CREATE INDEX IF NOT EXISTS idx_response_metrics_company ON email_response_metrics(customer_company_id);
CREATE INDEX IF NOT EXISTS idx_response_metrics_contact ON email_response_metrics(customer_contact_id);
CREATE INDEX IF NOT EXISTS idx_response_metrics_status ON email_response_metrics(status) WHERE status = 'open';
CREATE INDEX IF NOT EXISTS idx_response_metrics_sla ON email_response_metrics(is_within_sla) WHERE is_within_sla = FALSE;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE email_response_metrics TO anon, authenticated;

-- Thread completeness tracking
CREATE TABLE IF NOT EXISTS thread_status (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    thread_id TEXT NOT NULL UNIQUE,
    mailbox_id UUID REFERENCES mailboxes(id) ON DELETE CASCADE,
    customer_company_id UUID REFERENCES customer_companies(id) ON DELETE SET NULL,
    customer_contact_id UUID REFERENCES customer_contacts(id) ON DELETE SET NULL,
    subject TEXT,
    status TEXT NOT NULL DEFAULT 'complete' CHECK (status IN (
        'complete', 'awaiting_reply', 'overdue', 'dropped', 'outbound_pending', 'stale'
    )),
    last_message_direction TEXT CHECK (last_message_direction IN ('inbound', 'outbound')),
    last_message_at TIMESTAMPTZ,
    last_inbound_at TIMESTAMPTZ,
    last_outbound_at TIMESTAMPTZ,
    message_count INTEGER DEFAULT 0,
    participant_count INTEGER DEFAULT 0,
    open_duration_seconds INTEGER,       -- how long in current open state
    sla_deadline TIMESTAMPTZ,
    is_flagged BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_thread_status_mailbox ON thread_status(mailbox_id);
CREATE INDEX IF NOT EXISTS idx_thread_status_company ON thread_status(customer_company_id);
CREATE INDEX IF NOT EXISTS idx_thread_status_status ON thread_status(status);
CREATE INDEX IF NOT EXISTS idx_thread_status_open ON thread_status(status, last_message_at DESC)
    WHERE status IN ('awaiting_reply', 'overdue', 'dropped');
CREATE INDEX IF NOT EXISTS idx_thread_status_sla ON thread_status(sla_deadline)
    WHERE status = 'awaiting_reply';
CREATE TRIGGER update_thread_status_updated_at BEFORE UPDATE
    ON thread_status FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE thread_status TO anon, authenticated;
```

### 2.4 ALTER customer_contacts (Add Role + Analytics Columns)

```sql
-- =========================================================================
-- Sprint 2 Migration 004: customer_contacts role + analytics columns
-- =========================================================================

-- Role columns
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS seniority_level TEXT
    CHECK (seniority_level IN ('c_level','vp','director','manager','senior','mid','junior','intern','unknown'));
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS functional_role TEXT
    CHECK (functional_role IN ('executive','sales','marketing','operations','finance','engineering','support','procurement','legal','hr','other','unknown'));
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS is_decision_maker BOOLEAN DEFAULT FALSE;
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS is_primary_contact BOOLEAN DEFAULT FALSE;
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS role_source TEXT DEFAULT 'unknown'
    CHECK (role_source IN ('manual','email_signature','ai_enriched','inferred','csv_import','unknown'));
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS role_confidence DECIMAL(3,2) DEFAULT 0.00;
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS department TEXT;
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS engagement_score INTEGER DEFAULT 0;

-- Communication analytics columns
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS avg_response_time_seconds INTEGER;
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS their_avg_response_time INTEGER;
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS initiation_ratio DECIMAL(3,2);
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS reply_rate DECIMAL(3,2);
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS emails_per_month_avg DECIMAL(8,2);
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS frequency_trend TEXT
    CHECK (frequency_trend IN ('increasing','stable','declining','inactive'));
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS avg_thread_depth DECIMAL(5,2);
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS last_inbound_at TIMESTAMPTZ;
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS last_outbound_at TIMESTAMPTZ;
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS open_thread_count INTEGER DEFAULT 0;
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS dropped_thread_count INTEGER DEFAULT 0;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_contacts_seniority ON customer_contacts(seniority_level);
CREATE INDEX IF NOT EXISTS idx_contacts_role ON customer_contacts(functional_role);
CREATE INDEX IF NOT EXISTS idx_contacts_decision_maker ON customer_contacts(is_decision_maker) WHERE is_decision_maker = TRUE;
CREATE INDEX IF NOT EXISTS idx_contacts_engagement ON customer_contacts(engagement_score DESC);
CREATE INDEX IF NOT EXISTS idx_contacts_frequency_trend ON customer_contacts(frequency_trend);
```

### 2.5 ALTER customer_companies (Add Engagement Columns)

```sql
-- =========================================================================
-- Sprint 2 Migration 005: customer_companies engagement columns
-- =========================================================================

-- Role summary columns
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS contact_count INTEGER DEFAULT 0;
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS decision_maker_count INTEGER DEFAULT 0;
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS primary_contact_id UUID REFERENCES customer_contacts(id) ON DELETE SET NULL;
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS highest_seniority TEXT;
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS engagement_score INTEGER DEFAULT 0;
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS relationship_status TEXT DEFAULT 'new'
    CHECK (relationship_status IN ('active','cooling','dormant','new'));

-- Communication analytics columns
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS avg_response_time_seconds INTEGER;
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS sla_compliance_rate DECIMAL(3,2);
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS open_thread_count INTEGER DEFAULT 0;
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS dropped_thread_count INTEGER DEFAULT 0;
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS avg_emails_per_month DECIMAL(8,2);
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS frequency_trend TEXT
    CHECK (frequency_trend IN ('increasing','stable','declining','inactive'));
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS communication_health TEXT DEFAULT 'good'
    CHECK (communication_health IN ('excellent','good','needs_attention','critical'));

-- Indexes
CREATE INDEX IF NOT EXISTS idx_companies_engagement ON customer_companies(engagement_score DESC);
CREATE INDEX IF NOT EXISTS idx_companies_relationship ON customer_companies(relationship_status);
CREATE INDEX IF NOT EXISTS idx_companies_health ON customer_companies(communication_health);
CREATE INDEX IF NOT EXISTS idx_companies_dropped ON customer_companies(dropped_thread_count DESC)
    WHERE dropped_thread_count > 0;
```

### 2.6 New SQL Functions

```sql
-- =========================================================================
-- Sprint 2 Migration 006: Helper Functions
-- =========================================================================

-- Count unlinked emails for a mailbox
CREATE OR REPLACE FUNCTION get_unlinked_emails_count(p_mailbox_id UUID)
RETURNS TABLE(total_emails BIGINT, unlinked_emails BIGINT, linked_pct NUMERIC)
LANGUAGE sql STABLE AS $$
    SELECT
        COUNT(*) as total_emails,
        COUNT(*) FILTER (WHERE customer_company_id IS NULL) as unlinked_emails,
        ROUND(
            COUNT(*) FILTER (WHERE customer_company_id IS NOT NULL)::numeric / NULLIF(COUNT(*), 0) * 100,
            2
        ) as linked_pct
    FROM emails
    WHERE mailbox_id = p_mailbox_id
      AND processing_status = 'success';
$$;

GRANT EXECUTE ON FUNCTION get_unlinked_emails_count(UUID) TO anon, authenticated;

-- Get unique domains from a mailbox with classification
CREATE OR REPLACE FUNCTION get_domain_summary(p_mailbox_id UUID, p_client_id UUID)
RETURNS TABLE(
    domain TEXT,
    email_count BIGINT,
    classification TEXT,
    company_name TEXT
)
LANGUAGE sql STABLE AS $$
    WITH email_domains AS (
        SELECT
            LOWER(SPLIT_PART(sender_email, '@', 2)) as domain,
            COUNT(*) as email_count
        FROM emails
        WHERE mailbox_id = p_mailbox_id
          AND sender_email IS NOT NULL
          AND sender_email != ''
        GROUP BY 1
    )
    SELECT
        ed.domain,
        ed.email_count,
        CASE
            WHEN id2.domain IS NOT NULL THEN 'internal'
            WHEN fp.domain IS NOT NULL THEN 'free_provider'
            WHEN cc.id IS NOT NULL THEN 'customer'
            ELSE 'unknown'
        END as classification,
        cc.company_name
    FROM email_domains ed
    LEFT JOIN internal_domains id2 ON id2.domain = ed.domain AND id2.client_id = p_client_id
    LEFT JOIN free_email_providers fp ON fp.domain = ed.domain
    LEFT JOIN customer_companies cc ON cc.email_domains ? ed.domain AND cc.client_id = p_client_id
    ORDER BY ed.email_count DESC;
$$;

GRANT EXECUTE ON FUNCTION get_domain_summary(UUID, UUID) TO anon, authenticated;

-- Batch link emails to a company by domain
CREATE OR REPLACE FUNCTION link_emails_by_domain(
    p_client_id UUID,
    p_domain TEXT,
    p_company_id UUID
)
RETURNS INTEGER
LANGUAGE plpgsql AS $$
DECLARE
    updated_count INTEGER;
BEGIN
    UPDATE emails
    SET customer_company_id = p_company_id,
        client_id = p_client_id,
        updated_at = NOW()
    WHERE customer_company_id IS NULL
      AND LOWER(SPLIT_PART(sender_email, '@', 2)) = LOWER(p_domain);
    
    GET DIAGNOSTICS updated_count = ROW_COUNT;
    RETURN updated_count;
END;
$$;

GRANT EXECUTE ON FUNCTION link_emails_by_domain(UUID, TEXT, UUID) TO anon, authenticated;
```

---

## 3. FastAPI Project Structure

```
app/
├── main.py                          # FastAPI app, CORS, lifespan
├── config.py                        # Settings (pydantic-settings)
├── dependencies.py                  # Supabase client, JWT auth, current_user
│
├── routers/
│   ├── extraction.py                # POST /extract, GET /extract/status
│   ├── customers.py                 # CRUD: companies, contacts, roles
│   ├── rules.py                     # Email rules sync, import, view
│   ├── analytics.py                 # All analytics endpoints
│   └── config.py                    # Internal domains, free providers, recognition rules
│
├── services/
│   ├── contact_extractor.py         # Parse emails → extract addresses + names
│   ├── company_resolver.py          # Domain → company grouping
│   ├── email_linker.py              # Backfill FKs on emails table
│   ├── role_classifier.py           # Title → seniority + functional role
│   ├── rules_sync.py               # Gmail API + Graph API rule fetching
│   ├── rules_normalizer.py          # Gmail/Outlook/JSON → unified format
│   ├── rules_analyzer.py            # Derive engagement signals from rules
│   ├── response_time_tracker.py     # Compute response times per thread
│   ├── thread_tracker.py            # Detect open/incomplete/dropped threads
│   ├── comm_pattern_analyzer.py     # Initiation ratio, reply rate, frequency
│   ├── engagement_scorer.py         # 8-factor engagement score
│   ├── stats_updater.py             # Recompute all aggregated stats
│   └── extraction_orchestrator.py   # Runs the 13-step pipeline
│
├── models/
│   ├── schemas.py                   # Pydantic request/response models
│   ├── rules_schema.py              # Unified rule format, JSON import schema
│   └── role_schema.py               # Role/seniority enums
│
└── utils/
    ├── domain_parser.py             # Email → domain, normalization
    ├── name_parser.py               # Display name → first/last
    └── title_parser.py              # Job title → seniority + functional role
```

---

## 4. Utility Modules

### 4.1 Domain Parser (`app/utils/domain_parser.py`)

```python
"""
Extract and classify email domains.

Usage:
    domain = extract_domain("john@acme.com")  # "acme.com"
    company = domain_to_company_name("acme.com")  # "Acme"
"""

import re
from typing import Optional

def extract_domain(email: str) -> Optional[str]:
    """Extract domain from email address, lowercased."""
    if not email or '@' not in email:
        return None
    return email.strip().lower().split('@')[1]

def normalize_domain(domain: str) -> str:
    """Normalize domain: lowercase, strip whitespace."""
    return domain.strip().lower()

def domain_to_company_name(domain: str) -> str:
    """
    Convert domain to a readable company name.
    acme.com → Acme
    acme.co.uk → Acme
    my-company.io → My Company
    """
    # Remove TLD(s)
    name = domain.split('.')[0]
    # Replace hyphens/underscores with spaces
    name = re.sub(r'[-_]', ' ', name)
    # Title case
    return name.title()

def is_noreply_address(email: str) -> bool:
    """Detect system/no-reply addresses."""
    if not email:
        return False
    local = email.lower().split('@')[0]
    noreply_patterns = [
        'noreply', 'no-reply', 'no_reply', 'donotreply', 'do-not-reply',
        'mailer-daemon', 'postmaster', 'notifications', 'alert', 'alerts',
        'system', 'automated', 'auto-', 'bounce', 'unsubscribe',
        'feedback-', 'news@', 'newsletter', 'updates@', 'info@',
    ]
    return any(p in local for p in noreply_patterns)
```

### 4.2 Name Parser (`app/utils/name_parser.py`)

```python
"""
Parse display names into first_name, last_name.

Handles:
  "John Doe" → John, Doe
  "Doe, John" → John, Doe
  "john.doe@company.com" → John, Doe (inferred)
  "Dr. John A. Doe III" → John, Doe
"""

import re
from dataclasses import dataclass
from typing import Optional

PREFIXES = {'mr', 'mrs', 'ms', 'dr', 'prof', 'sir', 'dame', 'rev'}
SUFFIXES = {'jr', 'sr', 'ii', 'iii', 'iv', 'v', 'phd', 'md', 'esq', 'cpa'}

@dataclass
class ParsedName:
    first_name: str
    last_name: str
    full_name: str

def parse_display_name(display_name: Optional[str], email: Optional[str] = None) -> ParsedName:
    """Parse a display name into first/last. Falls back to email prefix."""
    if display_name:
        name = display_name.strip().strip('"').strip("'").strip()
        # Remove email in angle brackets: "John Doe <john@x.com>"
        name = re.sub(r'<[^>]+>', '', name).strip()
        
        if name:
            return _parse_name_string(name)
    
    # Fallback: infer from email
    if email and '@' in email:
        local = email.split('@')[0]
        # john.doe → John Doe
        parts = re.split(r'[._\-]', local)
        parts = [p for p in parts if not p.isdigit() and len(p) > 1]
        if len(parts) >= 2:
            return ParsedName(
                first_name=parts[0].title(),
                last_name=parts[-1].title(),
                full_name=' '.join(p.title() for p in parts)
            )
        elif parts:
            return ParsedName(first_name=parts[0].title(), last_name='', full_name=parts[0].title())
    
    return ParsedName(first_name='', last_name='', full_name='')

def _parse_name_string(name: str) -> ParsedName:
    """Parse a cleaned name string."""
    # Handle "Last, First" format
    if ',' in name:
        parts = [p.strip() for p in name.split(',', 1)]
        if len(parts) == 2 and len(parts[0].split()) <= 2 and len(parts[1].split()) <= 2:
            return ParsedName(first_name=parts[1], last_name=parts[0], full_name=f"{parts[1]} {parts[0]}")
    
    words = name.split()
    # Strip prefixes and suffixes
    words = [w for w in words if w.lower().rstrip('.') not in PREFIXES]
    words = [w for w in words if w.lower().rstrip('.') not in SUFFIXES]
    # Remove single initials (A., B.)
    words = [w for w in words if not (len(w) <= 2 and w.endswith('.'))]
    
    if not words:
        return ParsedName(first_name=name, last_name='', full_name=name)
    elif len(words) == 1:
        return ParsedName(first_name=words[0], last_name='', full_name=words[0])
    else:
        return ParsedName(first_name=words[0], last_name=words[-1], full_name=' '.join(words))
```

### 4.3 Title Parser (`app/utils/title_parser.py`)

```python
"""
Parse job titles into seniority_level and functional_role.

Usage:
    result = parse_title("Vice President of Sales")
    # TitleInfo(seniority='vp', role='sales', is_decision_maker=True)
"""

import re
from dataclasses import dataclass
from typing import Optional

@dataclass
class TitleInfo:
    seniority_level: str   # c_level, vp, director, manager, senior, mid, junior, intern, unknown
    functional_role: str   # executive, sales, marketing, operations, finance, engineering, support, procurement, legal, hr, other, unknown
    is_decision_maker: bool
    confidence: float      # 0.0-1.0

# Ordered by priority (check c_level first)
SENIORITY_PATTERNS = [
    ('c_level', [
        r'\bceo\b', r'\bcfo\b', r'\bcto\b', r'\bcoo\b', r'\bcmo\b', r'\bcio\b', r'\bcso\b',
        r'\bchief\b', r'\bpresident\b', r'\bowner\b', r'\bfounder\b', r'\bco-founder\b',
        r'\bpartner\b', r'\bprincipal\b(?!.*engineer)',
    ]),
    ('vp', [
        r'\bvp\b', r'\bvice.?president\b', r'\bsvp\b', r'\bevp\b', r'\bavp\b',
    ]),
    ('director', [
        r'\bdirector\b', r'\bhead\s+of\b', r'\bmanaging\s+director\b', r'\bgm\b',
        r'\bgeneral\s+manager\b',
    ]),
    ('manager', [
        r'\bmanager\b', r'\bsupervisor\b', r'\bteam\s+lead\b', r'\bcoordinator\b',
        r'\blead\b(?!.*developer|.*engineer)',
    ]),
    ('senior', [
        r'\bsenior\b', r'\bsr\.?\b', r'\blead\b', r'\bprincipal\b', r'\bstaff\b',
    ]),
    ('mid', [
        r'\banalyst\b', r'\bspecialist\b', r'\bassociate\b', r'\bengineer\b',
        r'\bdeveloper\b', r'\bdesigner\b', r'\bconsultant\b', r'\badvisor\b',
    ]),
    ('junior', [
        r'\bjunior\b', r'\bjr\.?\b', r'\bassistant\b', r'\bentry\b',
    ]),
    ('intern', [
        r'\bintern\b', r'\bco-?op\b', r'\bfellow\b', r'\btrainee\b', r'\bapprentice\b',
    ]),
]

ROLE_PATTERNS = [
    ('executive', [r'\bceo\b', r'\bcoo\b', r'\bchief\b', r'\bpresident\b', r'\bowner\b', r'\bfounder\b']),
    ('sales', [r'\bsales\b', r'\bbd\b', r'\bbusiness\s+dev', r'\baccount\b', r'\brevenue\b']),
    ('marketing', [r'\bmarketing\b', r'\bbrand\b', r'\bcontent\b', r'\bpr\b', r'\bcommunications\b', r'\bgrowth\b']),
    ('operations', [r'\boperations\b', r'\bops\b', r'\blogistics\b', r'\bsupply\s+chain\b', r'\bproject\b']),
    ('finance', [r'\bfinance\b', r'\bcfo\b', r'\baccounting\b', r'\bcontroller\b', r'\btreasur']),
    ('engineering', [r'\bengineering\b', r'\bcto\b', r'\btechnolog', r'\bsoftware\b', r'\bit\b', r'\bdata\b', r'\bdev']),
    ('support', [r'\bsupport\b', r'\bcustomer\s+service\b', r'\bcustomer\s+success\b', r'\bhelpdesk\b']),
    ('procurement', [r'\bprocurement\b', r'\bpurchasing\b', r'\bbuying\b', r'\bsourcing\b', r'\bvendor\b']),
    ('legal', [r'\blegal\b', r'\bcounsel\b', r'\bcompliance\b', r'\battorney\b', r'\blawyer\b']),
    ('hr', [r'\bhr\b', r'\bhuman\s+resource', r'\bpeople\b', r'\btalent\b', r'\brecruiting\b']),
]

DECISION_MAKER_SENIORITIES = {'c_level', 'vp', 'director'}

def parse_title(title: Optional[str], source: str = 'email_signature') -> TitleInfo:
    """Parse a job title into seniority, role, and decision-maker flag."""
    if not title or not title.strip():
        return TitleInfo('unknown', 'unknown', False, 0.0)
    
    normalized = title.lower().strip()
    
    seniority = _match_patterns(normalized, SENIORITY_PATTERNS) or 'unknown'
    role = _match_patterns(normalized, ROLE_PATTERNS) or 'unknown'
    is_decision_maker = seniority in DECISION_MAKER_SENIORITIES
    
    confidence_map = {
        'manual': 1.0, 'csv_import': 0.9, 'email_signature': 0.7,
        'ai_enriched': 0.85, 'inferred': 0.3, 'unknown': 0.0,
    }
    confidence = confidence_map.get(source, 0.5)
    
    # Reduce confidence if both are unknown
    if seniority == 'unknown' and role == 'unknown':
        confidence = max(confidence - 0.3, 0.0)
    
    return TitleInfo(seniority, role, is_decision_maker, round(confidence, 2))

def _match_patterns(text: str, pattern_groups: list) -> Optional[str]:
    """Match text against ordered pattern groups, return first match."""
    for label, patterns in pattern_groups:
        for pattern in patterns:
            if re.search(pattern, text):
                return label
    return None
```

---

## 5. Core Extraction Pipeline

### 5.1 Pipeline Overview (13 Steps)

The extraction orchestrator runs these steps in sequence:

| Step | Phase | Service | Description |
|------|-------|---------|-------------|
| 1 | Validate | orchestrator | Verify mailbox exists, has emails, linked to client. Load configs. |
| 2 | Collect | contact_extractor | Scan emails, extract all unique addresses + display names. |
| 3 | Classify | company_resolver | Classify each domain: internal → skip, free → flag, else → company. |
| 4 | Companies | company_resolver | Upsert customer_companies grouped by domain. |
| 5 | Contacts | contact_extractor | Upsert customer_contacts, link to companies, parse names. |
| 6 | Roles | role_classifier | Run title parser on contacts with job_title. Set seniority, role, decision-maker. |
| 7 | Rules | email_linker | Auto-generate domain_match recognition rules per company. |
| 8 | Link | email_linker | Batch-update emails: set customer_company_id, customer_contact_id, client_id. |
| 9 | Match Rules | rules_analyzer | Cross-reference unified_email_rules with companies/contacts. |
| 10 | Response Times | response_time_tracker | For each thread: compute response times, populate email_response_metrics. |
| 11 | Thread Status | thread_tracker | For each thread: evaluate completeness, populate thread_status. |
| 12 | Comm Patterns | comm_pattern_analyzer | Per contact/company: initiation ratio, reply rate, frequency trend. |
| 13 | Stats | stats_updater + engagement_scorer | Update all aggregated stats, engagement scores, communication health. |

### 5.2 Extraction Orchestrator Pseudocode

```python
# app/services/extraction_orchestrator.py

async def run_extraction(mailbox_id: str, client_id: str, job_id: str):
    """Run the full 13-step extraction pipeline."""
    
    # Step 1: Validate
    update_step(job_id, 'validate', 1)
    mailbox = await get_mailbox(mailbox_id)
    if not mailbox or not client_id:
        raise ValueError("Mailbox not found or no client_id")
    internal_domains = await load_internal_domains(client_id)
    free_providers = await load_free_providers()
    
    # Step 2: Collect addresses
    update_step(job_id, 'collect_addresses', 2)
    addresses = await contact_extractor.collect_all_addresses(mailbox_id, batch_size=500)
    # Returns: list of {email, name, source_email_id, is_sender}
    
    # Step 3: Classify domains
    update_step(job_id, 'classify_domains', 3)
    domain_map = company_resolver.classify_domains(
        addresses, internal_domains, free_providers
    )
    # Returns: {domain: 'internal'|'free'|'customer'|'new'}
    
    # Step 4: Upsert companies
    update_step(job_id, 'upsert_companies', 4)
    company_map = await company_resolver.upsert_companies(
        client_id, domain_map, addresses
    )
    # Returns: {domain: company_id}
    
    # Step 5: Upsert contacts
    update_step(job_id, 'upsert_contacts', 5)
    contact_map = await contact_extractor.upsert_contacts(
        client_id, addresses, company_map, free_providers
    )
    # Returns: {email: contact_id}
    
    # Step 6: Classify roles
    update_step(job_id, 'classify_roles', 6)
    await role_classifier.classify_all_contacts(client_id)
    
    # Step 7: Create recognition rules
    update_step(job_id, 'create_rules', 7)
    await email_linker.create_recognition_rules(client_id, company_map)
    
    # Step 8: Link emails
    update_step(job_id, 'link_emails', 8)
    linked = await email_linker.backfill_email_fks(
        mailbox_id, client_id, company_map, contact_map
    )
    
    # Step 9: Match email rules
    update_step(job_id, 'match_rules', 9)
    await rules_analyzer.match_rules_to_entities(client_id)
    
    # Step 10: Compute response times
    update_step(job_id, 'compute_response_times', 10)
    await response_time_tracker.compute_for_mailbox(mailbox_id, client_id)
    
    # Step 11: Evaluate thread status
    update_step(job_id, 'evaluate_threads', 11)
    await thread_tracker.evaluate_all_threads(mailbox_id, client_id)
    
    # Step 12: Analyze communication patterns
    update_step(job_id, 'analyze_patterns', 12)
    await comm_pattern_analyzer.analyze_for_client(client_id)
    
    # Step 13: Update all stats
    update_step(job_id, 'update_stats', 13)
    await stats_updater.update_all(client_id)
    await engagement_scorer.score_all(client_id)
    
    # Done
    mark_job_completed(job_id)
```

### 5.3 Domain Classification Logic

Priority order (check in this sequence):
1. **Internal domain** → skip entirely (own org's employees)
2. **System/no-reply address** → skip (no human contact)
3. **Free email provider** → create contact under "Individual Contacts" company
4. **Known customer domain** → link to existing customer_company
5. **New business domain** → create new customer_company + recognition rule

### 5.4 Free Email Provider Handling

Contacts from gmail.com, yahoo.com, etc. are grouped under a single "Individual Contacts" company per client:

```python
async def get_or_create_individual_bucket(client_id: str) -> str:
    """Get or create the 'Individual Contacts' company for a client."""
    result = await supabase.table('customer_companies').select('id').eq(
        'client_id', client_id
    ).eq('company_name', 'Individual Contacts').single().execute()
    
    if result.data:
        return result.data['id']
    
    result = await supabase.table('customer_companies').insert({
        'client_id': client_id,
        'company_name': 'Individual Contacts',
        'industry': 'Individual',
        'notes': 'Auto-created bucket for contacts from free email providers (Gmail, Yahoo, etc.)',
    }).execute()
    return result.data[0]['id']
```

---

## 6. Email Rules Intelligence

### 6.1 Gmail Rules Sync (`app/services/rules_sync.py`)

```python
async def sync_gmail_filters(mailbox_id: str, access_token: str) -> int:
    """Fetch Gmail filters via API and upsert into unified_email_rules."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            'https://gmail.googleapis.com/gmail/v1/users/me/settings/filters',
            headers={'Authorization': f'Bearer {access_token}'}
        )
        resp.raise_for_status()
        filters = resp.json().get('filter', [])
    
    count = 0
    for f in filters:
        normalized = rules_normalizer.normalize_gmail_filter(f)
        normalized['mailbox_id'] = mailbox_id
        normalized['source_type'] = 'gmail_api'
        normalized['source_rule_id'] = f['id']
        normalized['synced_at'] = datetime.utcnow().isoformat()
        
        await supabase.table('unified_email_rules').upsert(
            normalized, on_conflict='mailbox_id,source_type,source_rule_id'
        ).execute()
        count += 1
    
    return count
```

### 6.2 Outlook Rules Sync

```python
async def sync_outlook_rules(mailbox_id: str, access_token: str) -> int:
    """Fetch Outlook rules via Microsoft Graph and upsert."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            'https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messageRules',
            headers={'Authorization': f'Bearer {access_token}'}
        )
        resp.raise_for_status()
        rules = resp.json().get('value', [])
    
    count = 0
    for r in rules:
        normalized = rules_normalizer.normalize_outlook_rule(r)
        normalized['mailbox_id'] = mailbox_id
        normalized['source_type'] = 'outlook_api'
        normalized['source_rule_id'] = r['id']
        normalized['synced_at'] = datetime.utcnow().isoformat()
        
        await supabase.table('unified_email_rules').upsert(
            normalized, on_conflict='mailbox_id,source_type,source_rule_id'
        ).execute()
        count += 1
    
    return count
```

### 6.3 JSON Import Schema

```python
# app/models/rules_schema.py
from pydantic import BaseModel
from typing import Optional

class RuleConditions(BaseModel):
    from_domains: list[str] = []
    from_addresses: list[str] = []
    to_addresses: list[str] = []
    subject_contains: list[str] = []
    body_contains: list[str] = []
    has_attachment: Optional[bool] = None

class RuleActions(BaseModel):
    label: Optional[str] = None
    move_to_folder: Optional[str] = None
    forward_to: list[str] = []
    mark_important: Optional[bool] = None
    mark_read: Optional[bool] = None
    skip_inbox: Optional[bool] = None
    delete: Optional[bool] = None

class ImportRule(BaseModel):
    name: str
    conditions: RuleConditions
    actions: RuleActions
    is_active: bool = True

class RulesImportPayload(BaseModel):
    mailbox_id: str
    source: str = "json_import"  # or "manual"
    rules: list[ImportRule]
```

### 6.4 Engagement Signal Derivation

```python
def derive_engagement_signal(rule: dict) -> str:
    """Derive engagement signal from normalized rule actions."""
    # High value signals
    if rule.get('action_mark_important'):
        return 'high_value'
    label = (rule.get('action_label') or '').lower()
    if any(kw in label for kw in ['key', 'vip', 'priority', 'important', 'strategic']):
        return 'high_value'
    
    # Escalation signals
    if rule.get('action_forward_to'):
        return 'escalation'
    
    # Low priority signals
    if rule.get('action_skip_inbox') or rule.get('action_mark_read') or rule.get('action_delete'):
        return 'low_priority'
    
    # Segmentation signals
    if rule.get('action_move_to_folder') or rule.get('action_label'):
        return 'segmentation'
    
    return 'neutral'
```

---

## 7. Engagement Analytics Suite

### 7.1 Response Time Tracker (`app/services/response_time_tracker.py`)

**Algorithm:**
1. Query all threads for the mailbox (group emails by thread_id, order by sent_date ASC)
2. For each thread, walk through messages in order
3. When an inbound message is followed by an outbound message → that's a response pair
4. Compute `response_time_seconds = outbound.sent_date - inbound.sent_date`
5. Check against SLA threshold
6. If inbound has no following outbound → status = 'open'
7. Upsert into `email_response_metrics`

**Key query:**
```sql
-- Get all emails in a mailbox grouped by thread, ordered for pairing
SELECT id, thread_id, sender_email, sent_date, is_outbound,
       customer_contact_id, customer_company_id
FROM emails
WHERE mailbox_id = $1 AND thread_id IS NOT NULL
ORDER BY thread_id, sent_date ASC;
```

### 7.2 Thread Status Tracker (`app/services/thread_tracker.py`)

**Thread status rules:**
| Status | Condition |
|--------|-----------|
| `complete` | Last message is outbound, OR last inbound is acknowledgment-only |
| `awaiting_reply` | Last message is inbound, age < SLA threshold |
| `overdue` | Last message is inbound, age > SLA threshold but < 7 days |
| `dropped` | Last message is inbound, age > 7 days |
| `outbound_pending` | Last message is outbound, awaiting customer response |
| `stale` | No activity from either side in 30+ days |

### 7.3 Communication Pattern Analyzer (`app/services/comm_pattern_analyzer.py`)

**Per-contact metrics to compute:**

| Metric | Formula |
|--------|---------|
| `initiation_ratio` | threads_started_by_contact / total_threads (0.0-1.0) |
| `reply_rate` | outbound_emails_with_reply / total_outbound_emails (0.0-1.0) |
| `emails_per_month_avg` | total_emails_last_6_months / 6 |
| `frequency_trend` | Compare last 3 months vs prior 3 months: increasing (>20% up), declining (>20% down), stable, inactive (0 emails in 3 months) |
| `avg_thread_depth` | total_messages_in_threads / number_of_threads |
| `their_avg_response_time` | avg of (our_outbound → their_next_inbound) time deltas |

### 7.4 Engagement Score (8-Factor Formula)

```python
def compute_engagement_score(contact_stats: dict) -> int:
    """Compute 0-100 engagement score from 8 factors."""
    score = 0.0
    
    # 1. Email Frequency (20%)
    epm = contact_stats.get('emails_per_month_avg', 0)
    score += min(epm / 10, 1.0) * 20  # 10+ emails/month = max
    
    # 2. Recency (15%)
    days_since = contact_stats.get('days_since_last_email', 999)
    if days_since < 7: score += 15
    elif days_since < 30: score += 12
    elif days_since < 90: score += 6
    elif days_since < 180: score += 2
    
    # 3. Our Response Time (15%)
    rt = contact_stats.get('avg_response_time_hours', 999)
    if rt < 1: score += 15
    elif rt < 4: score += 12
    elif rt < 24: score += 8
    else: score += 3
    
    # 4. Their Reply Rate (15%)
    rr = contact_stats.get('reply_rate', 0)
    score += rr * 15
    
    # 5. Bidirectionality (10%)
    ir = contact_stats.get('initiation_ratio', 0)
    # Closer to 0.5 = better
    balance = 1.0 - abs(ir - 0.5) * 2
    score += balance * 10
    
    # 6. Thread Completeness (10%)
    total_threads = contact_stats.get('total_threads', 1)
    dropped = contact_stats.get('dropped_thread_count', 0)
    complete_pct = max(0, (total_threads - dropped)) / max(total_threads, 1)
    score += complete_pct * 10
    
    # 7. Rule Signal Bonus (8%)
    signal = contact_stats.get('rule_engagement_signal')
    signal_scores = {'high_value': 8, 'escalation': 6, 'segmentation': 4, 'neutral': 2, 'low_priority': -4}
    score += signal_scores.get(signal, 0)
    
    # 8. Seniority Weight (7%)
    seniority = contact_stats.get('seniority_level', 'unknown')
    seniority_scores = {'c_level': 7, 'vp': 6, 'director': 5, 'manager': 4, 'senior': 3, 'mid': 2, 'junior': 1, 'intern': 0.5}
    score += seniority_scores.get(seniority, 1)
    
    return max(0, min(100, round(score)))
```

### 7.5 Communication Health Score (Company-Level)

```python
def derive_communication_health(company_stats: dict) -> str:
    """Derive company communication health from metrics."""
    sla = company_stats.get('sla_compliance_rate', 0)
    dropped = company_stats.get('dropped_thread_count', 0)
    engagement = company_stats.get('engagement_score', 0)
    trend = company_stats.get('frequency_trend', 'stable')
    
    if sla >= 0.9 and dropped == 0 and engagement > 70 and trend in ('increasing', 'stable'):
        return 'excellent'
    elif sla >= 0.75 and dropped <= 2 and engagement >= 40:
        return 'good'
    elif sla < 0.5 or dropped > 5 or engagement < 20 or trend == 'inactive':
        return 'critical'
    else:
        return 'needs_attention'
```

### 7.6 Relationship Status Derivation

```python
def derive_relationship_status(company_stats: dict) -> str:
    """Derive relationship status from engagement metrics."""
    days_since = company_stats.get('days_since_last_contact', 999)
    engagement = company_stats.get('engagement_score', 0)
    total_emails = company_stats.get('total_emails', 0)
    
    if total_emails < 5 and days_since < 30:
        return 'new'
    elif days_since > 90 or engagement < 20:
        return 'dormant'
    elif days_since > 30 or company_stats.get('frequency_trend') == 'declining':
        return 'cooling'
    else:
        return 'active'
```

---

## 8. API Endpoints

### 8.1 Extraction Router (`app/routers/extraction.py`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/extract/{mailbox_id}` | Trigger extraction. Body: `{client_id, options?}`. Returns `{job_id}`. |
| `GET` | `/api/v1/extract/status/{job_id}` | Job progress: step, counts, errors. |
| `POST` | `/api/v1/extract/{mailbox_id}/preview` | Dry-run preview without writing. |
| `DELETE` | `/api/v1/extract/{mailbox_id}/reset` | Clear extracted data for re-run. |

### 8.2 Rules Router (`app/routers/rules.py`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/rules/sync/{mailbox_id}` | Sync from Gmail/Outlook API. |
| `POST` | `/api/v1/rules/import` | JSON bulk import for archive mailboxes. |
| `POST` | `/api/v1/rules/manual` | Add single rule via form. |
| `GET` | `/api/v1/rules` | List unified rules (paginated, filterable). |
| `GET` | `/api/v1/rules/{id}` | Rule detail with matched company/contact. |
| `PUT` | `/api/v1/rules/{id}` | Update rule metadata. |
| `DELETE` | `/api/v1/rules/{id}` | Delete manual rule. |
| `GET` | `/api/v1/rules/summary/{client_id}` | Engagement signal summary. |
| `POST` | `/api/v1/rules/match` | Re-run rule-to-entity matching. |

### 8.3 Customers Router (`app/routers/customers.py`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/companies` | List with engagement_score, relationship_status, health. |
| `GET` | `/api/v1/companies/{id}` | Detail: contacts, stats, rules, timeline. |
| `PUT` | `/api/v1/companies/{id}` | Update company details. |
| `POST` | `/api/v1/companies/merge` | Merge duplicates. |
| `GET` | `/api/v1/contacts` | List with seniority, role, engagement. Filter by is_decision_maker. |
| `GET` | `/api/v1/contacts/{id}` | Detail: role, email history, rules. |
| `PUT` | `/api/v1/contacts/{id}` | Update contact. |
| `PUT` | `/api/v1/contacts/{id}/role` | Update role specifically (manual, confidence=1.0). |
| `POST` | `/api/v1/contacts/{id}/move` | Move to different company. |
| `GET` | `/api/v1/contacts/decision-makers/{client_id}` | All decision-makers for campaign targeting. |

### 8.4 Analytics Router (`app/routers/analytics.py`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/analytics/top-companies` | By engagement score, with breakdown. |
| `GET` | `/api/v1/analytics/top-contacts` | By engagement score. |
| `GET` | `/api/v1/analytics/at-risk` | Companies: cooling + dormant. |
| `GET` | `/api/v1/analytics/company/{id}/timeline` | Volume + engagement over time. |
| `GET` | `/api/v1/analytics/role-distribution/{client_id}` | Seniority distribution. |
| `GET` | `/api/v1/analytics/engagement-funnel/{client_id}` | By relationship status. |
| `GET` | `/api/v1/analytics/rules-insights/{client_id}` | Signal distribution. |
| `GET` | `/api/v1/analytics/response-times/{client_id}` | Response times by company, SLA compliance. |
| `GET` | `/api/v1/analytics/open-threads/{client_id}` | Open/overdue/dropped threads ("close all loops"). |
| `GET` | `/api/v1/analytics/dropped-threads/{client_id}` | Dropped threads only (critical). |
| `GET` | `/api/v1/analytics/comm-patterns/{client_id}` | Initiation ratios, reply rates, trends. |
| `GET` | `/api/v1/analytics/communication-health/{client_id}` | Health breakdown. |
| `GET` | `/api/v1/analytics/domains` | Domain summary with classification. |
| `GET` | `/api/v1/analytics/unlinked` | Extraction coverage. |

### 8.5 Config Router (`app/routers/config.py`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/config/internal-domains/{client_id}` | List internal domains. |
| `POST` | `/api/v1/config/internal-domains/{client_id}` | Add internal domain. |
| `DELETE` | `/api/v1/config/internal-domains/{id}` | Remove. |
| `GET` | `/api/v1/config/free-providers` | List free providers. |
| `POST` | `/api/v1/config/free-providers` | Add provider. |
| `GET` | `/api/v1/config/recognition-rules/{client_id}` | List with match counts. |
| `PUT` | `/api/v1/config/recognition-rules/{id}` | Update rule. |

---

## 9. Task Checklist

### Phase 1: Foundation — COMPLETE ✅

- [x] 1.1 FastAPI scaffolding + config + deps
- [x] 1.2 Supabase client + JWT auth middleware
- [x] 1.3 SQL: internal_domains + free_email_providers + seeds
- [x] 1.4 SQL: extraction_jobs table
- [x] 1.5 SQL: unified_email_rules table
- [x] 1.6 SQL: ALTER customer_contacts (role + analytics columns)
- [x] 1.7 SQL: ALTER customer_companies (engagement columns)
- [x] 1.8 SQL: email_response_metrics table
- [x] 1.9 SQL: thread_status table
- [x] 1.10 SQL: New functions + indexes
- [x] 1.11 Domain parser utility
- [x] 1.12 Name parser utility
- [x] 1.13 Title parser utility

### Phase 2: Core Extraction Engine — COMPLETE ✅

- [x] 2.1 Contact Extractor service (with pagination, retry, Python-side filtering)
- [x] 2.2 Company Resolver service (domain grouping, free provider handling)
- [x] 2.3 Free provider handling (Individual Contacts bucket)
- [x] 2.4 Contact type classification (person/automated/shared/mailing_list/internal)
- [x] 2.5 Role Classifier service (title parsing, seniority, decision-maker flag)
- [x] 2.6 Email Linker service (chunked batches, 100% link rate)
- [x] 2.7 Engagement Score calculator (8-factor, 0-100 scale)
- [x] 2.8 Relationship Status derivation (active/cooling/dormant/new)
- [x] 2.9 Extraction orchestrator (13-step pipeline with mode support)
- [x] 2.10 Progress tracking + error handling + Redis integration

### Phase 3: Skipped (Rules Intelligence deferred to Sprint 3)

### Phase 4: Engagement Analytics Suite — COMPLETE ✅

- [x] 4.1 Response time tracker service (database-side calculations via RPC)
- [x] 4.2 Auto-reply detection (subject patterns + header analysis)
- [x] 4.3 Thread status evaluator (6 states: complete/awaiting/overdue/dropped/ongoing)
- [x] 4.4 Communication pattern analyzer (initiation ratio, reply rate, frequency trends)
- [x] 4.5 Database-side batch operations (25x improvement, Migration 006)
- [x] 4.6 Database-side analytics calculations (~250x improvement, Migrations 007-009)
- [x] 4.7 8-factor engagement scoring with seniority and decision-maker bonuses

### Phase 5A: Analytics API — COMPLETE ✅

- [x] 5.1 Analytics Pydantic models (41 models + 5 enums, 581 lines)
- [x] 5.2 30 REST API endpoints across 7 categories (2,305 lines)
- [x] 5.3 Extraction control endpoints (run, status, list, cancel, progress)
- [x] 5.4 Contact analytics endpoints (list, detail, top-engaged, at-risk, decision-makers, by-type)
- [x] 5.5 Company analytics endpoints (list, detail, top-engaged, at-risk, by-engagement)
- [x] 5.6 Thread analytics endpoints (status, overdue, by-status, by-contact)
- [x] 5.7 Response time endpoints (list, stats, slowest, by-contact)
- [x] 5.8 Communication pattern endpoints (initiation, frequency, trends, by-contact)
- [x] 5.9 Dashboard endpoints (summary, client summary)
- [x] 5.10 All endpoints tested and verified

### Phase 5B: Incremental Extraction — COMPLETE ✅

- [x] 5.11 Migration 010 (8 columns, 3 indexes, backfill logic)
- [x] 5.12 Full + incremental mode support in orchestrator
- [x] 5.13 Configurable lookback days (1-365)
- [x] 5.14 Master schema updated to v1.8

### Phase 6: Production Deployment & Fixes — COMPLETE ✅

- [x] 6.1 Production deployment to Railway
- [x] 6.2 Fix NULL processing_status exclusion (Python-side filtering)
- [x] 6.3 Fix Supabase .or_() compatibility (removed server-side filter)
- [x] 6.4 Fix pagination off-by-one (len==0 break, offset+=len(batch))
- [x] 6.5 Add retry logic for transient Supabase errors (SSL 525, 502-504)
- [x] 6.6 Add total count visibility and page X/Y logging
- [x] 6.7 Production test: 26,654 emails across 54 pages processed successfully
- [x] 6.8 Performance verified: Full mode ~1.5min, Incremental ~15-30s

### Phase 7: Analytics Frontend & Post-Production Fixes — COMPLETE ✅

- [x] 7.1 Analytics dashboard page (client selector, metrics, extraction trigger)
- [x] 7.2 Contacts analytics page (5 tabs, sort, filter, engagement score slider)
- [x] 7.3 Companies analytics page (4 tabs, sort, filter, score slider)
- [x] 7.4 Threads analytics page (3 tabs, status chart, sort, filter)
- [x] 7.5 Contact detail page (stats, threads, communication patterns)
- [x] 7.6 Company detail page (stats, top contacts, threads)
- [x] 7.7 Admin Data View (raw table browser, search, sort, pagination, CSV export)
- [x] 7.8 Fix uniform engagement scores (missing fields + hardcoded values)
- [x] 7.9 Migration 011: Fix RPC functions for analytics data
- [x] 7.10 Migration 012: Backfill scoring input fields from email data
- [x] 7.11 Fix min_engagement_score 500 error (float-to-int casting)
- [x] 7.12 Fix 'unknown' seniority label display on contact detail
- [x] 7.13 Engagement badge UX (show labels + scores, fix slider onChangeComplete)

---

## 10. Edge Cases & Notes

### Domain Classification
- **Multi-domain companies** (acme.com + acme.co.uk): Sprint 2 treats as separate, use `/companies/merge` to combine. Sprint 3 AI clusters.
- **Shared addresses** (info@acme.com): Create single contact, flag for review.
- **Email aliases** (john@, j.doe@ same person): Sprint 2 treats as separate. Sprint 3 AI deduplicates.
- **Mailing lists**: Detect via `List-*` headers in raw_headers JSONB, skip contact creation.
- **Auto-generated emails**: Pattern-detect noreply/notifications/system, skip.

### Performance
- **Batch size**: Process 500 emails per batch to avoid memory issues.
- **Supabase timeout**: Chunk batch updates to 1000 rows max per statement.
- **Idempotent upserts**: All upserts use ON CONFLICT to allow safe re-runs.
- **Don't load body_text**: Extraction only needs sender_email, sender_name, recipients, thread_id, sent_date.

### Response Time Calculation
- **Business hours**: Optional. When enabled, subtract non-business hours from response time.
- **Auto-replies**: Exclude from response time calculation (detect via email_categories tags or subject patterns like "Out of Office").
- **Multi-party threads**: Track response to the primary external contact, not internal CCs.

### Thread Status Edge Cases
- **Threads with only outbound**: Status = `outbound_pending`
- **Single-email threads**: If inbound and no reply within SLA → `awaiting_reply`, else `complete`
- **Threads that resume after long gaps**: Re-evaluate status when new emails arrive

### Sprint 3 Handoff: AI Semantic Intelligence

Sprint 3 transitions the platform from metadata tracking to **Semantic & Intent Intelligence** using the Claude API.

**Pre-Sprint 3 Prerequisites — COMPLETE:**
- ✅ Admin Data View (raw table browser with search, sort, pagination, CSV export)
- ✅ Analytics Frontend (6 pages with full interactivity)
- ✅ Post-production scoring fixes (12 migrations, varied engagement scores)

**Immediate Next Step:**
1. **AI Usage Tracking** — Admin dashboard for monitoring Claude API costs and usage

**Phase 1: Semantic Intent & Sentiment Engine**
- `AIIntentProcessor` — Classify emails: Pricing Inquiry, Feature Request, Expansion Signal, Churn Risk
- Sentiment drift detection in `EngagementScorer` — Track tone shifts across threads
- Hidden urgency detection — AI analysis of email body for critical business blockers

**Phase 2: Entity & Opportunity Extraction**
- Business entity extraction — Detect competitors, product names, budget mentions in `extraction_orchestrator.py`
- Lead Scoring 2.0 — Weight buying signals (procurement, legal review, implementation timeline) in `engagement_scorer.py`
- AI contact enrichment — Infer job functions from email signatures/content when `title_parser.py` fails

**Phase 3: Hidden Network & Relationship Insights**
- Influence mapping — Track when high-seniority contacts (via `role_classifier.py`) enter threads via CC
- Communication gap analysis — Flag single-point-of-contact risk in company relationships
- Relationship summarization — Claude-generated 3-sentence executive summaries of relationship history

**Phase 4: Proactive "Next Best Action"**
- Suggested responses — AI-drafted responses based on thread history and detected intent
- Proactive churn alerts — Auto-flag accounts with >30% engagement velocity drop in 1 week
- Marketing trigger exports — Identify champions for case study recruitment, export to CSV/CRM

**AI Model Strategy:**
- Use Claude API (latest model) in cost-optimized way
- Track AI model usage per request for admin cost control
- Batch processing for email analysis
- Caching to avoid re-analyzing unchanged content
