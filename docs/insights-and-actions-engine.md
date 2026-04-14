# Insights & Actions Engine

**Initiative started:** 2026-04-11
**Goal:** Transform from "here's your data" to "here's what you should do, why, and when — with a draft email ready."

*(Formerly tracked under the codename "monkey-d-luffy" in early sessions.)*

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

### Index Audit & Bloat Prevention (2026-04-12)

**Problem:** 43 indexes on `emails` table, ~6.2 GB index space vs 457 MB table data (13.5× ratio). Triggered Supabase auto-disk-expansion 10 GB → 15 GB.

**Root cause:** Indexes added incrementally across 15+ migrations without cross-checking existing ones. Per-column FTS indexes never cleaned up after `search_text` tsvector migration. Ad-hoc indexes created via SQL console without migration files.

**Audit results (code reachability + runtime stats):**

| Category | Count | Action |
|----------|-------|--------|
| KEEP (confirmed used) | 14 | Retain — serves active code paths |
| WAIT_FOR_STATS | 12 | Retain pending 30-day runtime window |
| INVESTIGATE | 1 | `idx_emails_mailbox_sent` — ad-hoc orphan with 120 scans, trace via `pg_stat_statements` |
| DROP (unreachable + zero scans) | 16 | Drop after confirming zero scans over 30 days (target: May 12) |

**Target:** Reduce from 43 → 15 indexes (consolidated set matches BulkIndexManager registry + PK/UNIQUE).

**Key correction applied:** Initial audit falsely classified 4 indexes as droppable that had non-zero runtime scans (`idx_emails_mailbox_id` 380 scans, `idx_emails_mailbox_count` 83, `idx_emails_sent_date` 54, `idx_emails_sent_date_only` 34). Introduced **Two-Signal Drop Rule**: both code-unreachability AND zero runtime scans required before any drop.

**Estimated disk recovery:** ~350-450 MB in Stage 2 (biggest win: `idx_emails_body_fts` at ~298 MB, superseded by `search_text`).

**Deliverables:**
- [`docs/database/EMAILS_INDEX_CLEANUP_PLAN.md`](database/EMAILS_INDEX_CLEANUP_PLAN.md) — staged execution with SQL
- [`docs/database/ROOT_CAUSE.md`](database/ROOT_CAUSE.md) — how 43 indexes accumulated
- [`docs/database/INDEX_POLICY.md`](database/INDEX_POLICY.md) — governance to prevent recurrence
- `scripts/db/index_audit.sql` + `index_audit.py` — monthly review tooling (pending)
- `scripts/migrations/073_index_cleanup_template.sql` — migration template (pending)
- `.github/pull_request_template.md` — PR checklist for migrations (pending)

### Reembed Migration to processing_jobs + SSE (2026-04-13)

**Problem:** Reembed state lived in module-level dicts (`_reembed_progress`, `_reembed_cancel` in [ai.py:2004-2006](../backend/src/routers/ai.py)). Lost on API restart, no audit trail, page-refresh on the frontend wiped the connection, no concurrency safety.

**Migrated to:** persistent state in `processing_jobs` (existing table) + SSE streaming (matches digest endpoint pattern at [ai.py:1410](../backend/src/routers/ai.py#L1410)). Polling endpoint kept as fallback.

**Schema additions ([scripts/migrations/073](../scripts/migrations/073_processing_jobs_for_reembed.sql) + [074](../scripts/migrations/074_processing_jobs_reembed_unique_index.sql)):**
- `processing_jobs.client_id UUID REFERENCES clients(id)` — nullable (legacy rows untouched)
- `processing_jobs.parameters JSONB NOT NULL DEFAULT '{}'` — stores `{tables, limit, triggered_by_user_id}`
- `processing_jobs.current_stage TEXT` — UI-friendly stage indicator
- Partial unique index `uq_processing_jobs_one_active_reembed_per_client` — single-flight enforcement
- `increment_job_progress(UUID, INT, INT, TEXT)` SQL function — atomic counter increments via RPC. Typed parameters only; NEVER accepts SQL fragments. SECURITY INVOKER (default).

**API surface:**
- `POST /vector/reembed` — same signature, now returns `job_id`. 409 if active reembed exists for client.
- `GET /vector/reembed/status` — same signature + optional `job_id`; reads from `processing_jobs`. Backward compatible.
- `POST /vector/reembed/stop` — same + optional `job_id`. Returns immediately.
- `GET /vector/reembed/stream/{job_id}` — **NEW SSE endpoint**. Polls table at 750ms; emits `snapshot`, `progress`, terminal events.

**Helper:** [`backend/src/services/reembed_job_state.py`](../backend/src/services/reembed_job_state.py) — owns ALL processing_jobs read/write for reembed. Rest of router code does not touch the table directly.

**Frontend:** [`vectorService.ts`](../frontend/src/services/vectorService.ts) gains `streamReembed()` (matches `streamDigestGeneration` pattern — fetch + getReader, NOT EventSource because EventSource can't carry Authorization headers). [`usage.tsx`](../frontend/src/pages/intelligence/usage.tsx) reembed flow now SSE-first with polling fallback on stream error.

**Tests:** [`backend/test_reembed_jobs.py`](../backend/test_reembed_jobs.py) — integration script in the existing project style. Covers atomic increment, single-flight race (via `asyncio.gather`), state transitions, cancellation round-trip. Project does not use pytest; this is an executable script.

**Deployment runbook:**
1. Apply migration 073 (transactional, fast — ~seconds)
2. Apply migration 074 separately, OUTSIDE a transaction (CONCURRENTLY index)
3. Verify with `python scripts/db/index_registry_reconcile.py` — index should appear under `processing_jobs`
4. Deploy backend + frontend together
5. **In-flight reembed jobs in the old in-memory dict are lost on restart.** Confirm no reembeds running before deploy; deploy in a low-traffic window.

**Known limitations (flagged for follow-up tasks):**
- Progress granularity is one update per reembed (final count only). Per-batch updates would require modifying `vector_service.reembed_all` to accept a callback — out of scope for this task.
- Cancellation race: `request_cancel` sets `status='stopped'` immediately, but the worker's `BulkIndexManager` finally block (which recreates HNSW indexes) may not have completed yet. A second reembed triggered in this small window would race with the first's index recreation. Documented in helper module's FLAG #1.
- `backfill-search-text` endpoint has the same in-memory pattern but is out of scope for this task. Phase 1.5 follow-up.

### Key Lessons Learned

**1. Index Management Scope:**
- Dropping ALL indexes is dangerous on production Supabase
- **Only drop HNSW indexes**, and only for embedding writes
- Btree indexes have negligible write overhead (~0.1ms/row) — always leave in place
- PostgreSQL only updates indexes on columns that changed

**2. HNSW Index Rebuild Requirements:**
- HNSW build on 187K vectors needs `maintenance_work_mem = '256MB'` minimum
- Default Supabase `maintenance_work_mem` is too small — causes "no longer fits" error
- Always `SET maintenance_work_mem = '256MB'` and `SET statement_timeout = '0'` before rebuild
- If disk space is low, HNSW build fails with "No space left on device" — run `VACUUM FULL` first or use IVFFlat as alternative
- IVFFlat (`WITH (lists = 200)`) builds in seconds and needs far less memory/disk

**3. Cascading Failure Pattern:**
- Missing HNSW index → sequential scans on 245K rows → every auto-refresh query slow
- Frontend auto-refresh every 60s → constant sequential scans → instance overwhelmed
- **Always stop the backend before rebuilding indexes** to prevent cascading load

**4. HNSW Rebuild Command (save for future use):**
```sql
SET maintenance_work_mem = '256MB';
SET statement_timeout = '0';
CREATE INDEX IF NOT EXISTS idx_emails_embedding 
ON emails USING hnsw (embedding vector_cosine_ops) 
WITH (m = 16, ef_construction = 64);
```

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
