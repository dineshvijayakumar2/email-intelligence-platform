# Platform Surgery: Data Display → Insights & Actions Engine

**Code name:** monkey-d-luffy
**Started:** 2026-04-11
**Goal:** Transform from "here's your data" to "here's what you should do, why, and when — with a draft email ready."

---

## Session 1 Progress (2026-04-11)

### Completed: AI Usage Page Overhaul (Original Surgical Plan)

All 6 steps from `frolicking-wiggling-crab` plan delivered:

| Step | What | Commit |
|------|------|--------|
| 1. DB-backed controls | load/save settings from `system_settings`, startup restore | `e931ea0` |
| 2. Per-task model config | `call_for_task()`, 8-task registry, wired all 4 callers | `e931ea0` |
| 3. DB-computed budget | `get_spend_total()` RPC, both code paths enforce | `e931ea0` + `dd2532c` |
| 4. API keys consistency | `providers_ready` field, all hooks guarded with `enabled: !!clientId` | `e931ea0` |
| 5. Frontend overhaul | Loading states, skeleton during save, TanStack Query migration | `12bbfa5` |
| 6. Verification | All 7 checks passed | — |

### Completed: Supabase Disk IO Budget Crisis

Supabase sent a disk IO depletion warning. Root cause: Python-side pagination loops fetching entire tables into memory.

**6 RPC functions created (migration 064, 065):**

| RPC | Replaced | IO Saved |
|-----|----------|----------|
| `get_spend_total()` | `get_actual_spend()` — paginated all ai_usage_log rows | ~12GB/day |
| `get_usage_summary()` | 30-day usage aggregation loop | ~1GB/day |
| `get_monitoring_stats()` | 24h health metrics pagination | ~500MB/day |
| `get_distinct_folders_for_mailbox()` | 245K-row folder scan | ~125MB/day |
| `get_classification_health()` | N+1 per-mailbox classification queries (5×N) | ~25MB/day |
| `get_thread_health()` | N+1 + pagination for thread intent coverage | ~25MB/day |

**#1 IO burner fixed:** Canonical thread resolver was scanning ALL 245K emails on every extraction run. Added `WHERE canonical_thread_id IS NULL` — now fetches only unresolved emails (~0-500).

**10 missing indexes added (migrations 064, 066):**
- `idx_ai_usage_spend_check` — budget check (every AI call)
- `idx_ai_intel_mailbox_status` — classification health
- `idx_qb_quotes_client_customer` — order history (was 3.4h cumulative)
- `idx_qb_jobs_client_customer` — job lookups (was 3h cumulative)
- `idx_qb_operations_client_customer` — company detail (was 17.6m)
- `idx_emails_unresolved_threads` — partial index for resolver
- `idx_emails_resolved_msgid` — partial index for pre-seed
- `idx_emails_folder_mailbox` — folder count joins
- PostgREST schema caching fix (12h query time eliminated)
- `update_folder_counts()` rewrite — correlated subquery → GROUP BY

### Completed: Database Performance Dashboard (Phase 6 partial)

New panel on Data Health page with 3 tabs:
- **Slow Queries** — top queries by execution time with severity badges
- **Table Sizes** — row estimates + total/table/index sizes
- **Index Usage** — sorted by scan count, unused indexes flagged

Features: cache hit ratios, health alert banner, Reset Stats button, human-readable times.

**Commits:** `fb893ac`, `d29ce19`, `6bbc9cf`, `4aed538`

### Completed: TanStack Query Migration

Both pages fully migrated from raw `useEffect` + `useState` to TanStack Query hooks:

**AI Usage page (8 hooks):**
- `useAICosts`, `useAIMonitoring`, `useAIControls`, `useAIRecentLogs`
- `useAIModels`, `useAIApiKeys`, `useAITaskModels`, `useEmbeddingConfig`
- `useVectorStats` (embedding management)

**Data Health page (3 hooks):**
- `useDataHealth`, `useClassificationHealth`, `useThreadHealth`

### Completed: Bug Fixes

| Bug | Root Cause | Fix | Commit |
|-----|-----------|-----|--------|
| AI switch shows ON after reload | Fallback defaults had `ai_enabled: true` | Default to `false`, show skeleton while loading | `1df502f` |
| Embeddings ignore kill switch | Separate code path, no check | Block `POST /vector/reembed` when AI disabled | `1df502f` |
| "api_timeout" when budget exceeded | `last_error` not set in budget/kill-switch checks | Set descriptive `last_error` before returning None | `8ffc064` |
| "Reset Spend" misleading | Only cleared 60s cache, not actual spend | Renamed to "Refresh Cache" | `8ffc064` |
| Embedding shows "env" source | Raw useEffect, no TanStack Query | `useEmbeddingConfig()` hook with proper caching | `874dd42` |
| Embedding section shows empty | `statsLoading` defaulted false, dead "Select a client" message | `useVectorStats()` hook, skeleton fallback | `6a9f802`, `8f35b39` |
| Embedding provider reads "openai" | `_resolve_provider()` had no `client_id` filter | Scoped query to active client | `8a0346b` |
| Silent OpenAI fallback | Fell back to Google with wrong batch sizes | Raise clear error instead, detect provider from model instance | `ac53562`, `24b0e21` |
| "Unknown" mailbox names | Thread health missing `name` in SELECT | Added `name` column | `dde0253` |
| Classification health 500 | JSONB array wrapping from PostgREST | Added unwrapping logic | `dde0253` |
| DB_CHUNK=50 timeouts | Too aggressive for Supabase tier | Reduced to 20 | `c0bed2a` |

---

## Phase Status

| Phase | Description | Status | Notes |
|-------|-------------|--------|-------|
| **6** | Data Health Expansion | **Done** | Thread health, classification, embeddings, DB perf dashboard |
| **1** | Seasonality Engine | **Done** | Multi-year analysis, outreach windows, YTD comparison, industry seasonality |
| **—** | IO Budget + Bulk Ops | **Done** | BulkIndexManager, 10 migrations, 12 RPCs, 7 operations optimized |
| **3** | Thread Intelligence | Partial | `intent_status` column exists, override logic not wired |
| **2** | Gap Analysis Engine | Not started | |
| **4** | Action Items Engine | Not started | Depends on 1-3 |
| **5** | Industry Analytics | Not started | |
| **7** | Analytics Intelligence (NL) | Not started | |
| **8** | Digest Enhancement | Not started | |
| **9** | Smart Inbox (Thread-First) | Not started | |
| **10** | Remove Ops by Dept display | Not started | |

---

## Phase 1: Seasonality Engine — Implementation Plan

### What's done
- Migration 068: `get_company_seasonality()`, `get_industry_seasonality()`, `get_outreach_windows()` RPCs + index

### What's next
1. **Enhance `customer_analytics_service.py`** — replace `_fetch_all_paginated` with RPC call, add year-over-year data model
2. **Add outreach windows endpoint** — `GET /analytics/outreach-windows` returns upcoming approach windows
3. **Add YTD comparison** — current year vs previous year(s) by month
4. **Enhance `SeasonalityChart.tsx`** — year-over-year bars/lines, peak markers, outreach window callouts
5. **Company detail page** — add outreach window card alongside seasonality chart

### Data model enhancement
Current: `{ monthly: [{month, order_count, revenue}], peak_months, trough_months }`

Target:
```json
{
  "monthly": [{ "month": 1, "order_count": 12, "revenue": 45000.50 }],
  "yearly": {
    "2024": [{ "month": 1, "order_count": 5, "revenue": 22000 }, ...],
    "2025": [{ "month": 1, "order_count": 7, "revenue": 23000 }, ...]
  },
  "peak_months": [3, 9],
  "trough_months": [7],
  "outreach_windows": [
    {
      "peak_month": 9,
      "approach_start": "2026-07-15",
      "approach_end": "2026-08-15",
      "avg_peak_revenue": 45000,
      "has_active_quote": false
    }
  ],
  "ytd_comparison": {
    "current_year": 2026,
    "current_ytd_revenue": 125000,
    "prior_year_ytd_revenue": 110000,
    "growth_pct": 13.6
  }
}
```

---

## Session 1 — Continued: Embedding Pipeline + Bulk Operation Optimization

### Completed: Embedding Pipeline Fixes
| Bug | Root Cause | Fix | Commit |
|-----|-----------|-----|--------|
| Reembed uses wrong provider | `_resolve_provider()` fetched first client via LIMIT 1, not active client | Thread `client_id` through entire chain | `244ad9e` |
| API keys not read from DB | Vector service only read env vars | `_resolve_api_key()` reads base64 keys from system_settings | `b81f7f4` |
| Embedding writes timeout | HNSW index rebuild on every UPDATE | Drop indexes before bulk, recreate after | `ec885d8` |
| Batch RPC was FOR LOOP | `batch_update_embeddings_emails` did N individual UPDATEs | Rewrite with `unnest()` — 1 UPDATE per batch | `9f921f5` |

**Result:** 20K emails embedded in 14 minutes (was 2+ hours)

### Completed: BulkIndexManager — Platform-Wide Bulk Write Optimization

**New class:** `backend/src/database/bulk_index_manager.py`

Centralized index management for all bulk database operations. Registry of 60+ indexes across 12 tables. Drops non-essential indexes before bulk writes, recreates in `finally` block.

**Key features:**
- UNIQUE/ON CONFLICT indexes never dropped
- Two-tier recreation: btree (30s timeout), HNSW/GIN (5min via `exec_sql_extended`)
- Threshold: only engages for 500+ rows
- Both sync (`@contextmanager`) and async (`@asynccontextmanager`) support
- Graceful degradation if `exec_sql` RPC unavailable

**Scoped to HNSW-only (revised `51e9691`):**

The initial approach dropped ALL indexes on a table during bulk writes. This was too aggressive — dropping btree indexes broke query performance, and HNSW recreation failures caused cascading timeouts. Revised to:
- **Only drops HNSW indexes** — the real write bottleneck (~50-100ms/row vs ~0.1ms for btree)
- **Only used by VectorService** — embedding is the only operation that writes to HNSW-indexed columns
- PostgreSQL only updates indexes on columns that changed, so non-embedding writes never trigger HNSW maintenance
- Removed from: email insert, QB upsert, thread status, canonical threads, email contact links

| Operation | File | Tables | Status |
|-----------|------|--------|--------|
| Vector embedding | `vector_service.py` | `emails`, `customer_companies`, `qb_operations` | Active — drops HNSW before, recreates after |
| Email batch insert | `database/operations.py` | `emails` | Removed — btree-only overhead is negligible |
| QB sync upsert | `quickbase_sync.py` | All QB tables | Removed — no HNSW columns touched |
| Email contact links | `email_linker.py` | `email_contact_links` | Removed — no HNSW |
| Thread status | `thread_tracker.py` | `thread_status` | Removed — no HNSW |
| Canonical thread resolution | `canonical_thread_resolver.py` | `emails` | Removed — updates canonical_thread_id, not embedding |

**Commits:** `dfb1f21` (initial), `51e9691` (scoped to HNSW-only)

### Pending: Tier 3 — QB 1-by-1 Update Loop Fixes
- `_enrich_capabilities()` — convert to batch via `batch_update_qb_capabilities` RPC
- `_join_contact_email()` — convert to batch via `batch_update_qb_contact_emails` RPC
- RPCs created in migration 072, Python refactor pending

### Key Lesson: Index Management Scope
Dropping ALL indexes is dangerous on a production Supabase instance:
- HNSW index recreation on 187K+ vectors can timeout and leave the DB degraded
- Cascading timeouts from missing btree indexes affect all queries
- **Only drop HNSW indexes**, and only for operations that write to embedding columns
- Btree indexes have negligible write overhead (~0.1ms/row) — always leave them in place

---

## Migrations to Run

| Migration | Status | Description |
|-----------|--------|-------------|
| 063 | Run | system_settings created_at + changelog trigger |
| 064 | Run | IO budget RPCs (spend, usage, monitoring, folders) |
| 065 | Run | Data health RPCs (classification, thread) |
| 066 | Run | Missing indexes (qb_quotes, qb_jobs, qb_ops, emails, folder_counts rewrite) |
| 067 | Run | DB performance dashboard RPCs (slow queries, tables, indexes, cache, reset) |
| 068 | Run | Seasonality engine RPCs + index |
| 069 | Run | Fast batch embedding (unnest replaces FOR LOOP) |
| 070 | Run | Vector stats RPC (replaces 6 COUNT queries) |
| 071 | Run | exec_sql RPC for DDL from application |
| 072 | Pending | exec_sql_extended + batch update RPCs for Tier 3 |
