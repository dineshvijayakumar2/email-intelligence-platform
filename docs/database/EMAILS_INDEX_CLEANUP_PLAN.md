# Emails Table — Index Cleanup Plan

## Changelog

- 2026-04-12: Initial plan (6-phase audit)
- 2026-04-12: Correction pass — introduced Two-Signal Drop Rule, reclassified 4 indexes with non-zero runtime scans from DROP to WAIT_FOR_STATS, reclassified `idx_emails_mailbox_sent` from DROP to INVESTIGATE, rewrote Stages 1–3 accordingly
- 2026-04-13: `idx_emails_thread` reclassified from DROP to KEEP after `pg_stat_user_indexes` showed 1505 active scans + traced to 6 active call sites in AI services (`ai_email_analyzer.py:1071`, `ai_digest_generator.py:679`, `ai_insights_engine.py:266,271`, `comm_pattern_analyzer.py:354`, `langchain_tools.py:230`). Separate platform task added: migrate these 6 call sites from `thread_id` to `canonical_thread_id`, then index becomes droppable.
- 2026-04-13: Stage 1 executed. (a) Confirmed `idx_emails_search_text` already exists (75 MB) — keyword search no longer sequential-scans. (b) `idx_emails_mailbox_sent` definition revealed as `(mailbox_id, sent_date DESC)` btree — structurally redundant with `idx_emails_coverage_main` (same leading columns; coverage_main is also a covering index). Plan to drop in Stage 2 after monitoring whether scans shift to coverage_main. (c) REINDEX of `emails_message_id_mailbox_unique` (28→27 MB) and `emails_pkey` (11→8 MB) — minimal bloat, ~4 MB recovered.

---

## Two-Signal Drop Rule

**An index may only be dropped when BOTH conditions hold:**

1. The code audit finds no code path referencing its columns in a query predicate, AND
2. `pg_stat_user_indexes` shows zero scans over a rolling 30-day runtime window.

Either signal alone is insufficient. Code audits miss dynamic queries, PostgREST-generated predicates, and runtime-managed indexes. Runtime stats miss cold paths like monthly reports and rarely-used admin tooling. Both signals are required. Any index with even a single scan in the window is retained pending investigation, regardless of what the code audit concluded.

---

## Phase 1 — Index Inventory

**43 indexes on the `emails` table** (including PK), totaling ~6.2 GB against 457 MB of table data (13.5× ratio).

Sources cross-referenced: migration SQL files, `create_tables.sql`, `optimize_dashboard_queries.sql`, sprint migrations, and `BulkIndexManager` registry (`backend/src/database/bulk_index_manager.py:47-83`).

| # | Index Name | Columns | Type | WHERE Clause | Migration File | In Prod | Notes |
|---|-----------|---------|------|-------------|----------------|---------|-------|
| 1 | `emails_pkey` | `id` | btree (PK) | — | `create_tables.sql` | YES | |
| 2 | `emails_message_id_mailbox_unique` | `message_id, mailbox_id` | btree (UNIQUE) | — | `create_tables.sql:102` | YES | ON CONFLICT target |
| 3 | `idx_emails_sent_date` | `sent_date` | btree | — | `create_tables.sql:203` | YES | |
| 4 | `idx_emails_sender` | `sender_email` | btree | — | `create_tables.sql:204` | YES | |
| 5 | `idx_emails_folder` | `folder_path` | btree | — | `create_tables.sql:205` | YES | |
| 6 | `idx_emails_thread` | `thread_id` | btree | — | `create_tables.sql:206` | YES | Legacy — superseded by canonical_thread_id |
| 7 | `idx_emails_outbound` | `is_outbound` | btree | — | `create_tables.sql:207` | YES | Low cardinality (boolean) |
| 8 | `idx_emails_reply` | `is_reply` | btree | — | `create_tables.sql:208` | YES | Low cardinality (boolean) |
| 9 | `idx_emails_mailbox_id` | `mailbox_id` | btree | — | `create_tables.sql:209` | YES | In BulkIndexManager |
| 10 | `idx_emails_mailbox_date` | `mailbox_id, sent_date` | btree | — | `create_tables.sql:210` | YES | In BulkIndexManager |
| 11 | `idx_emails_processing_status` | `processing_status` | btree | — | `create_tables.sql:228` | YES | |
| 12 | `idx_emails_processing_status_mailbox` | `mailbox_id, processing_status` | btree | — | `create_tables.sql:229` | YES | In BulkIndexManager |
| 13 | `idx_emails_failed_retry` | `processing_status, processing_attempts` | btree | `processing_status = 'failed'` | `create_tables.sql:230` | YES | |
| 14 | `idx_emails_direction` | `direction` | btree | — | `create_tables.sql:232` | YES | |
| 15 | `idx_emails_client` | `client_id` | btree | — | `create_tables.sql:233` | YES | In BulkIndexManager |
| 16 | `idx_emails_customer_company` | `customer_company_id` | btree | — | `create_tables.sql:234` | YES | In BulkIndexManager |
| 17 | `idx_emails_customer_contact` | `customer_contact_id` | btree | — | `create_tables.sql:235` | YES | In BulkIndexManager |
| 18 | `idx_emails_subject_fts` | `to_tsvector('english', subject)` | GIN | — | `create_tables.sql:241` | YES | Superseded by search_text |
| 19 | `idx_emails_body_fts` | `to_tsvector('english', COALESCE(body_text,''))` | GIN | — | `create_tables.sql:242` | YES | Superseded by search_text (~298 MB) |
| 20 | `idx_emails_folder_date` | `folder_path, sent_date DESC` | btree | — | `create_tables.sql:249` | YES | |
| 21 | `idx_emails_sender_date` | `sender_email, sent_date DESC` | btree | — | `create_tables.sql:250` | YES | |
| 22 | `idx_emails_mailbox_folder_date` | `mailbox_id, folder_path, sent_date DESC` | btree | — | `create_tables.sql:251` | YES | |
| 23 | `idx_emails_mailbox_date_outbound` | `mailbox_id, sent_date DESC, is_outbound` | btree | — | `create_tables.sql:252` | YES | |
| 24 | `idx_emails_mailbox_sender_date` | `mailbox_id, sender_email, sent_date DESC` | btree | — | `create_tables.sql:253` | YES | |
| 25 | `idx_emails_mailbox_folder_outbound` | `mailbox_id, folder_path, is_outbound` | btree | — | `create_tables.sql:254` | YES | |
| 26 | `idx_emails_coverage_main` | `mailbox_id, sent_date DESC` INCLUDE(id, subject, sender_email, sender_name, is_outbound, is_reply, folder_path, message_size) | btree | — | `create_tables.sql:257` | YES | In BulkIndexManager |
| 27 | `idx_emails_embedding` | `embedding vector(768)` | HNSW(m=16, ef=64) | — | `037_vector_embeddings.sql:33` | YES | In BulkIndexManager (~903 MB) |
| 28 | `idx_emails_provider_web_link` | `id` | btree | `provider_web_link IS NOT NULL` | `031_add_email_attachments_deeplink.sql:17` | YES | |
| 29 | `idx_emails_provider_thread_id` | `provider_thread_id` | btree | `provider_thread_id IS NOT NULL` | `sprint3_019:25` | YES | |
| 30 | `idx_emails_subject_normalized` | `subject_normalized` | btree | `subject_normalized IS NOT NULL` | `sprint3_019:28` | YES | |
| 31 | `idx_emails_in_reply_to` | `in_reply_to` | btree | `in_reply_to IS NOT NULL` | `sprint3_019:31`, `055:19` | YES | |
| 32 | `idx_emails_internet_message_id` | `internet_message_id` | btree | `internet_message_id IS NOT NULL` | `sprint3_019:34`, `055:15` | YES | |
| 33 | `idx_emails_canonical_thread` | `canonical_thread_id` | btree | `canonical_thread_id IS NOT NULL` | `055:11` | YES | In BulkIndexManager |
| 34 | `idx_emails_mailbox_unlinked` | `mailbox_id, id` | btree | `customer_contact_id IS NULL` | `043:5` | YES | |
| 35 | `idx_emails_mailbox_company_unlinked` | `mailbox_id, id` | btree | `customer_company_id IS NULL AND customer_contact_id IS NULL` | `043:10` | YES | |
| 36 | `idx_emails_unresolved_threads` | `mailbox_id, sent_date` | btree | `canonical_thread_id IS NULL` | `066:21` | YES | In BulkIndexManager |
| 37 | `idx_emails_resolved_msgid` | `mailbox_id` | btree | `canonical_thread_id IS NOT NULL AND internet_message_id IS NOT NULL` | `066:26` | YES | In BulkIndexManager |
| 38 | `idx_emails_folder_mailbox` | `mailbox_id, folder_path` | btree | — | `066:35` | YES | In BulkIndexManager |
| 39 | `idx_emails_mailbox_sent_date` | `mailbox_id, sent_date DESC` | btree | `processing_status = 'success'` | `sprint2_010:51` | YES | |
| 40 | `idx_emails_processing_status_sent_date` | `processing_status, sent_date DESC` | btree | `processing_status = 'success'` | `sprint2_010:56` | YES | |
| 41 | `idx_emails_sent_date_only` | `sent_date DESC` | btree | — | `optimize_dashboard_queries.sql:43` | YES | |
| 42 | `idx_emails_mailbox_count` | `mailbox_id` | btree | `mailbox_id IS NOT NULL` | `optimize_dashboard_queries.sql:46` | YES | |
| 43 | `idx_emails_mailbox_sent` | **Unknown** | btree? | **Unknown** | **NONE — ad-hoc orphan** | YES | 120 scans in runtime snapshot |

### Anomalies

- **Ad-hoc orphan:** `idx_emails_mailbox_sent` — exists in production with 120 active scans but no migration file creates it and it does not appear in the `BulkIndexManager` registry. Created via SQL console at some point. Must be investigated, not dropped.
- **Missing from prod:** `idx_emails_search_text` (GIN on `search_text` WHERE NOT NULL) — created in `057:11`, managed by BulkIndexManager (line 80-82). **Critical for `keyword_search_emails()` RPC.** Needs creation or confirmation it exists.
- **Missing from prod (acceptable):** `idx_emails_message_mailbox_upsert` — redundant with `emails_message_id_mailbox_unique` constraint.
- **Missing from prod (acceptable):** `idx_emails_sent_date_desc` — redundant with `idx_emails_sent_date_only`.

---

## Phase 2 — Code Reachability Audit

Evidence from searching all backend Python code + SQL RPC function bodies. Runtime scans column from `pg_stat_user_indexes` snapshot taken 2026-04-12 (a few hours after `pg_stat_reset()` — short window, zero-scan data unreliable for cold paths).

| # | Index Name | Est. Size | Category | Runtime Scans (snapshot) | Evidence | Recommendation |
|---|-----------|----------|----------|-------------------------|----------|----------------|
| 1 | `emails_pkey` | 11 MB | USED | 44,837 | Every `.eq('id', ...)` lookup | KEEP |
| 2 | `emails_message_id_mailbox_unique` | ~30 MB | USED | n/a | ON CONFLICT upsert in `operations.py` | KEEP |
| 3 | `idx_emails_embedding` | ~903 MB | USED | 0 (short window) | `search_emails` RPC uses `<=>` operator (`056:25`) | KEEP |
| 4 | `idx_emails_coverage_main` | 10 MB | USED | 317 | Main email listing `emails.py:164-303` — mailbox_id + sent_date DESC with covering columns | KEEP |
| 5 | `idx_emails_folder_mailbox` | ~5 MB | USED | 0 (short window) | `get_distinct_folders_for_mailbox()` RPC (`064:208`), `update_folder_counts()` (`066:41`) | KEEP |
| 6 | `idx_emails_processing_status_mailbox` | ~5 MB | USED | 0 (short window) | `get_failed_emails()` (`operations.py:1332`), `get_error_counts()`, `reset_failed()` | KEEP |
| 7 | `idx_emails_client` | 2 MB | USED | 9 | `search_emails` RPC filter, `get_vector_stats()` (`070:5`) | KEEP |
| 8 | `idx_emails_canonical_thread` | ~5 MB | USED | 0 (short window) | Thread analytics joins in `thread_tracker.py` | KEEP |
| 9 | `idx_emails_unresolved_threads` | ~5 MB | USED | 0 (short window) | `canonical_thread_resolver.py:130` — `WHERE canonical_thread_id IS NULL` | KEEP |
| 10 | `idx_emails_resolved_msgid` | ~5 MB | USED | 0 (short window) | Thread resolution pre-seed in `canonical_thread_resolver.py` | KEEP |
| 11 | `idx_emails_internet_message_id` | ~5 MB | USED | 0 (short window) | Thread resolver message-ID lookups | KEEP |
| 12 | `idx_emails_in_reply_to` | ~5 MB | USED | 0 (short window) | Thread resolver in-reply-to chain walking | KEEP |
| 13 | `idx_emails_mailbox_unlinked` | 1 MB | USED | 10 | `email_linker.py:153` — `WHERE customer_contact_id IS NULL` | KEEP |
| 14 | `idx_emails_mailbox_company_unlinked` | ~1 MB | USED | 0 (short window) | `email_linker.py` — `WHERE customer_company_id IS NULL AND customer_contact_id IS NULL` | KEEP |
| 15 | `idx_emails_mailbox_sent_date` | 8 MB | POSSIBLY USED | 0 | Incremental sync high-water mark? Partial WHERE `processing_status = 'success'` | WAIT_FOR_STATS |
| 16 | `idx_emails_processing_status_sent_date` | ~8 MB | POSSIBLY USED | 0 (short window) | Similar purpose, different leading column | WAIT_FOR_STATS |
| 17 | `idx_emails_subject_normalized` | ~5 MB | POSSIBLY USED | 0 (short window) | Thread resolver subject matching | WAIT_FOR_STATS |
| 18 | `idx_emails_provider_thread_id` | ~5 MB | POSSIBLY USED | 0 (short window) | Thread resolver provider thread grouping | WAIT_FOR_STATS |
| 19 | `idx_emails_customer_company` | ~5 MB | POSSIBLY USED | 0 (short window) | FK index — may serve CASCADE deletes or company-filter queries | WAIT_FOR_STATS |
| 20 | `idx_emails_customer_contact` | ~5 MB | POSSIBLY USED | 0 (short window) | FK index — may serve CASCADE deletes or contact-filter queries | WAIT_FOR_STATS |
| 21 | `idx_emails_failed_retry` | ~2 MB | POSSIBLY USED | 0 (short window) | Partial index for failed retries; `processing_status_mailbox` may serve same queries | WAIT_FOR_STATS |
| 22 | `idx_emails_mailbox_folder_date` | ~10 MB | POSSIBLY USED | 0 (short window) | Could serve folder+date filtering in `emails.py`; `folder_mailbox` + `coverage_main` likely sufficient | WAIT_FOR_STATS |
| 23 | `idx_emails_mailbox_id` | 2 MB | **INVESTIGATE** | **380** | Code audit says subsumed by composites, but 380 scans + 18M tuples read — actively load-bearing. Planner may prefer it for mailbox_id-only filters. | **WAIT_FOR_STATS** |
| 24 | `idx_emails_sent_date` | 6 MB | **INVESTIGATE** | **54** | Code audit says subsumed, but 54 scans — likely used by RPCs with date range filters | **WAIT_FOR_STATS** |
| 25 | `idx_emails_sent_date_only` | 11 MB | **INVESTIGATE** | **34** | Code audit says duplicate, but 34 scans + 4801 tuples — different sort direction may matter | **WAIT_FOR_STATS** |
| 26 | `idx_emails_mailbox_count` | 8 MB | **INVESTIGATE** | **83** | Code audit says redundant with mailbox_id, but 83 scans + 8.8M tuples read — actively used | **WAIT_FOR_STATS** |
| 27 | `idx_emails_mailbox_date` | ~5 MB | UNREACHABLE | 0 (short window) | Subsumed by `idx_emails_coverage_main` (same leading columns + INCLUDE) | DROP |
| 28 | `idx_emails_sender` | ~5 MB | UNREACHABLE | 0 (short window) | No code queries sender_email with `=`; people search uses ILIKE (no btree benefit) | DROP |
| 29 | `idx_emails_folder` | ~5 MB | UNREACHABLE | 0 (short window) | folder_path never queried without mailbox_id; `folder_mailbox` covers it | DROP |
| 30 | `idx_emails_thread` | ~20 MB | **USED** | **1505** | 6 active call sites in AI services: `ai_email_analyzer.py:1071` (`.in_("thread_id", chunk)`), `ai_digest_generator.py:679` (`.in_("thread_id", thread_ids)`), `ai_insights_engine.py:266,271` (`.eq("thread_id", thread_id)`), `comm_pattern_analyzer.py:354`, `langchain_tools.py:230` | **KEEP** (pending canonical_thread_id migration of these 6 call sites — see Stage 3 platform task) |
| 31 | `idx_emails_outbound` | ~3 MB | UNREACHABLE | 0 (short window) | `is_outbound` never filtered alone; always with mailbox_id | DROP |
| 32 | `idx_emails_reply` | ~3 MB | UNREACHABLE | 0 (short window) | `is_reply` never filtered alone; always with mailbox_id | DROP |
| 33 | `idx_emails_direction` | ~3 MB | UNREACHABLE | 0 (short window) | `direction` column not used in any WHERE predicate | DROP |
| 34 | `idx_emails_processing_status` | ~5 MB | UNREACHABLE | 0 (short window) | Always queried with mailbox_id; `processing_status_mailbox` covers it | DROP |
| 35 | `idx_emails_body_fts` | ~298 MB | UNREACHABLE | 0 (short window) | Old per-column FTS on body_text — replaced by combined `search_text` tsvector + `keyword_search_emails` RPC | DROP |
| 36 | `idx_emails_subject_fts` | ~15 MB | UNREACHABLE | 0 (short window) | Old per-column FTS on subject — replaced by combined `search_text` tsvector | DROP |
| 37 | `idx_emails_sender_date` | ~5 MB | UNREACHABLE | 0 (short window) | No code queries (sender_email, sent_date) together | DROP |
| 38 | `idx_emails_folder_date` | ~5 MB | UNREACHABLE | 0 (short window) | No code queries (folder_path, sent_date) without mailbox_id | DROP |
| 39 | `idx_emails_mailbox_sender_date` | ~8 MB | UNREACHABLE | 0 (short window) | Sender search uses ILIKE, not `=`; btree unusable for ILIKE | DROP |
| 40 | `idx_emails_mailbox_date_outbound` | ~8 MB | UNREACHABLE | 0 (short window) | Outbound filter applied after mailbox+date; `coverage_main` handles the base WHERE | DROP |
| 41 | `idx_emails_mailbox_folder_outbound` | ~8 MB | UNREACHABLE | 0 (short window) | No code queries this 3-column combination | DROP |
| 42 | `idx_emails_provider_web_link` | ~3 MB | UNREACHABLE | 0 (short window) | `provider_web_link` only in SELECT, never in WHERE | DROP |
| 43 | `idx_emails_mailbox_sent` | 19 MB | **REDUNDANT** | **120** | Ad-hoc orphan — no migration, not in BulkIndexManager. Definition (revealed 2026-04-13): `CREATE INDEX idx_emails_mailbox_sent ON emails USING btree (mailbox_id, sent_date DESC)`. **Structurally redundant with `idx_emails_coverage_main`** which has the same leading columns plus INCLUDE (covering index). 120 scans likely planner preference for older index; should shift to coverage_main once Stage 2 drops other indexes and stats refresh. | **DROP in Stage 2** (after verifying no scans for 30 days) |

### Summary

| Category | Count | Action |
|----------|-------|--------|
| KEEP (confirmed used) | 15 | Retain |
| WAIT_FOR_STATS | 12 | Retain pending 30-day runtime window |
| DROP (unreachable + zero scans) | 15 | Drop after confirming zero scans over 30-day window |
| DROP (redundant with coverage_main) | 1 | `idx_emails_mailbox_sent` — drop in Stage 2 |

---

## Phase 3 — Consolidated Index Set (Target: 15)

The minimum set needed to serve all confirmed code paths. Aligns with the BulkIndexManager registry (14 managed indexes) plus PK and UNIQUE constraint.

| # | Index | Definition | Query Shapes Served |
|---|-------|-----------|---------------------|
| 1 | `emails_pkey` | PK on `id` | All single-row lookups |
| 2 | `emails_message_id_mailbox_unique` | UNIQUE on `message_id, mailbox_id` | Upsert ON CONFLICT |
| 3 | `idx_emails_embedding` | HNSW `embedding vector_cosine_ops` (m=16, ef=64) | Vector similarity via `search_emails` RPC |
| 4 | `idx_emails_search_text` | GIN on `search_text` WHERE NOT NULL | Full-text keyword search via `keyword_search_emails` RPC |
| 5 | `idx_emails_coverage_main` | `(mailbox_id, sent_date DESC)` INCLUDE(id, subject, sender_email, sender_name, is_outbound, is_reply, folder_path, message_size) | Main listing, date range, mailbox counts |
| 6 | `idx_emails_folder_mailbox` | `(mailbox_id, folder_path)` | Folder listing, folder counts, folder+mailbox filters |
| 7 | `idx_emails_processing_status_mailbox` | `(mailbox_id, processing_status)` | Failed emails, error counts, retry, stats |
| 8 | `idx_emails_client` | `(client_id)` | Multi-tenant filtering in search RPCs |
| 9 | `idx_emails_canonical_thread` | `(canonical_thread_id)` WHERE NOT NULL | Thread analytics, thread-based joins |
| 10 | `idx_emails_unresolved_threads` | `(mailbox_id, sent_date)` WHERE `canonical_thread_id IS NULL` | Thread resolution batch processing |
| 11 | `idx_emails_resolved_msgid` | `(mailbox_id)` WHERE `canonical_thread_id IS NOT NULL AND internet_message_id IS NOT NULL` | Pre-seed resolution lookups |
| 12 | `idx_emails_internet_message_id` | `(internet_message_id)` WHERE NOT NULL | Message-ID chain walking |
| 13 | `idx_emails_in_reply_to` | `(in_reply_to)` WHERE NOT NULL | In-Reply-To chain walking |
| 14 | `idx_emails_mailbox_unlinked` | `(mailbox_id, id)` WHERE `customer_contact_id IS NULL` | Email-contact linking batch |
| 15 | `idx_emails_mailbox_company_unlinked` | `(mailbox_id, id)` WHERE `customer_company_id IS NULL AND customer_contact_id IS NULL` | Email-company linking batch |

**Note:** The 12 WAIT_FOR_STATS + 1 INVESTIGATE indexes are NOT in this target set but are retained until investigation completes. Final count after full cleanup: 15-28 depending on investigation outcomes.

---

## Phase 6 — Staged Execution Plan

> **IMPORTANT:** This plan is audit and documentation only. No SQL has been executed. All statements below are for human review and controlled execution.

### Stage 1 — Zero Risk (EXECUTED 2026-04-13)

**Status:** Complete. Outcomes summarized in changelog. ~4 MB recovered; `idx_emails_search_text` confirmed present (75 MB GIN); ad-hoc orphan `idx_emails_mailbox_sent` identified as structurally redundant with `idx_emails_coverage_main`.

**Preconditions:** None.

**1a. Create missing `idx_emails_search_text` (if not already present)**

Confirmed live: `keyword_search_emails()` RPC in `057_fulltext_search_emails.sql:55` is called from `hybrid_retriever.py:286`. The `search_text` column is populated by trigger for new emails and backfilled via `backfill_search_text_by_ids()` RPC. Index is managed by BulkIndexManager (`bulk_index_manager.py:80-82`).

```sql
-- Verify index doesn't exist first:
-- SELECT indexname FROM pg_indexes WHERE tablename = 'emails' AND indexname = 'idx_emails_search_text';

-- Create if missing:
SET maintenance_work_mem = '256MB';
SET statement_timeout = '0';
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_emails_search_text
ON emails USING gin(search_text) WHERE search_text IS NOT NULL;
```

Rollback:
```sql
DROP INDEX CONCURRENTLY IF EXISTS idx_emails_search_text;
```

**1b. REINDEX bloated unique/PK indexes**

```sql
REINDEX INDEX CONCURRENTLY emails_message_id_mailbox_unique;
REINDEX INDEX CONCURRENTLY emails_pkey;
```

Rollback: None needed — REINDEX is always safe and reversible.

**1c. Investigate `idx_emails_mailbox_sent` (ad-hoc orphan)**

Do NOT drop. Instead, trace which queries hit it:

```sql
-- Step 1: Get the index definition
SELECT indexdef FROM pg_indexes WHERE indexname = 'idx_emails_mailbox_sent';

-- Step 2: Check pg_stat_statements for queries using the columns
SELECT query, calls, mean_exec_time, rows
FROM pg_stat_statements
WHERE query LIKE '%mailbox_id%sent%'
  AND query LIKE '%emails%'
ORDER BY calls DESC
LIMIT 20;
```

After identifying the source query, either:
- Formalize with a migration file if the index is needed
- Drop if confirmed redundant with another index AND zero scans over 30 days

**Estimated recovery (Stage 1):** ~5-15 MB from REINDEX bloat reduction. Net gain from `idx_emails_search_text` creation depends on existing data (~50-100 MB for GIN on 245K rows).

---

### Stage 2 — Low Risk (after 30-day stats window, target: May 12, 2026)

**Precondition:** Before executing, re-run the following query and verify every listed index still has zero scans. Any index that accumulated scans during the window is removed from this stage and moved to Stage 3.

```sql
SELECT
    i.indexrelname AS index_name,
    pg_size_pretty(pg_relation_size(i.indexrelid)) AS size,
    i.idx_scan AS scans,
    i.idx_tup_read AS tup_read,
    i.idx_tup_fetch AS tup_fetch
FROM pg_stat_user_indexes i
JOIN pg_indexes ix ON i.indexrelname = ix.indexname
WHERE ix.tablename = 'emails'
  AND i.indexrelname IN (
    'idx_emails_mailbox_date',
    'idx_emails_sender',
    'idx_emails_folder',
    'idx_emails_outbound',
    'idx_emails_reply',
    'idx_emails_direction',
    'idx_emails_processing_status',
    'idx_emails_body_fts',
    'idx_emails_subject_fts',
    'idx_emails_sender_date',
    'idx_emails_folder_date',
    'idx_emails_mailbox_sender_date',
    'idx_emails_mailbox_date_outbound',
    'idx_emails_mailbox_folder_outbound',
    'idx_emails_provider_web_link'
  )
ORDER BY i.idx_scan DESC, pg_relation_size(i.indexrelid) DESC;
```

**If all show zero scans, execute these drops (15 indexes):**

```sql
-- GIN indexes (biggest wins — ~313 MB)
DROP INDEX CONCURRENTLY IF EXISTS idx_emails_body_fts;        -- ~298 MB, superseded by search_text
DROP INDEX CONCURRENTLY IF EXISTS idx_emails_subject_fts;     -- ~15 MB, superseded by search_text

-- Subsumed single-column btree indexes
DROP INDEX CONCURRENTLY IF EXISTS idx_emails_mailbox_date;    -- subsumed by coverage_main
DROP INDEX CONCURRENTLY IF EXISTS idx_emails_sender;          -- ILIKE queries can't use btree
DROP INDEX CONCURRENTLY IF EXISTS idx_emails_folder;          -- subsumed by folder_mailbox
DROP INDEX CONCURRENTLY IF EXISTS idx_emails_outbound;        -- boolean, never filtered alone
DROP INDEX CONCURRENTLY IF EXISTS idx_emails_reply;           -- boolean, never filtered alone
DROP INDEX CONCURRENTLY IF EXISTS idx_emails_direction;       -- never in WHERE predicate
DROP INDEX CONCURRENTLY IF EXISTS idx_emails_processing_status; -- subsumed by processing_status_mailbox

-- Unused composite indexes
DROP INDEX CONCURRENTLY IF EXISTS idx_emails_sender_date;            -- no code queries this combo
DROP INDEX CONCURRENTLY IF EXISTS idx_emails_folder_date;            -- folder always with mailbox
DROP INDEX CONCURRENTLY IF EXISTS idx_emails_mailbox_sender_date;    -- sender uses ILIKE
DROP INDEX CONCURRENTLY IF EXISTS idx_emails_mailbox_date_outbound;  -- coverage_main serves base query
DROP INDEX CONCURRENTLY IF EXISTS idx_emails_mailbox_folder_outbound; -- no code uses this combo

-- Unused partial index
DROP INDEX CONCURRENTLY IF EXISTS idx_emails_provider_web_link; -- provider_web_link never in WHERE
```

**Note:** `idx_emails_thread` was previously in this list but has been moved to KEEP after the 2026-04-13 trace identified 6 active call sites. See Stage 3 platform task for the canonical_thread_id migration that would later allow this index to be dropped.

Rollback (recreate any dropped index):
```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_emails_body_fts ON emails USING gin(to_tsvector('english', COALESCE(body_text, '')));
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_emails_subject_fts ON emails USING gin(to_tsvector('english', subject));
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_emails_mailbox_date ON emails(mailbox_id, sent_date);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_emails_sender ON emails(sender_email);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_emails_folder ON emails(folder_path);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_emails_outbound ON emails(is_outbound);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_emails_reply ON emails(is_reply);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_emails_direction ON emails(direction);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_emails_processing_status ON emails(processing_status);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_emails_sender_date ON emails(sender_email, sent_date DESC);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_emails_folder_date ON emails(folder_path, sent_date DESC);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_emails_mailbox_sender_date ON emails(mailbox_id, sender_email, sent_date DESC);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_emails_mailbox_date_outbound ON emails(mailbox_id, sent_date DESC, is_outbound);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_emails_mailbox_folder_outbound ON emails(mailbox_id, folder_path, is_outbound);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_emails_provider_web_link ON emails(id) WHERE provider_web_link IS NOT NULL;
```

**Estimated recovery (Stage 2):** ~350-450 MB (body_fts alone is ~298 MB; 15 additional btree indexes ~3-10 MB each).

---

### Stage 3 — Per-Index Investigation (ongoing)

Indexes where either: (a) the code audit suggests redundancy but runtime stats show active use, or (b) the code path is ambiguous. Each index requires individual investigation using `pg_stat_statements` to identify which queries hit it, followed by either retaining the index or confirming another index can serve the same plan.

**No mass DROP in Stage 3.** Each index is investigated and resolved individually.

**Indexes requiring investigation (13 total):**

| Index | Why Investigate | Size | Runtime Scans |
|-------|----------------|------|---------------|
| `idx_emails_mailbox_id` | 380 scans, 18M tuples — code audit says subsumed by composites but planner prefers it for mailbox_id-only filters | 2 MB | 380 |
| `idx_emails_mailbox_count` | 83 scans, 8.8M tuples — code audit says redundant with mailbox_id but actively used (may be PostgREST-generated) | 8 MB | 83 |
| `idx_emails_sent_date` | 54 scans — may serve RPC date range filters that bypass the app code | 6 MB | 54 |
| `idx_emails_sent_date_only` | 34 scans, 4801 tuples — different sort direction from sent_date, may serve dashboard queries | 11 MB | 34 |
| `idx_emails_mailbox_sent` | 120 scans — ad-hoc orphan, no migration, no BulkIndexManager entry. Must trace query source. | 19 MB | 120 |
| `idx_emails_mailbox_sent_date` | Partial index for incremental sync. Zero scans in short window — may fire during sync cycles | 8 MB | 0 |
| `idx_emails_processing_status_sent_date` | Partial index, similar to above | ~8 MB | 0 |
| `idx_emails_subject_normalized` | Thread resolver subject matching — may fire during extraction runs | ~5 MB | 0 |
| `idx_emails_provider_thread_id` | Thread resolver provider thread grouping | ~5 MB | 0 |
| `idx_emails_customer_company` | FK index, possible CASCADE or admin queries | ~5 MB | 0 |
| `idx_emails_customer_contact` | FK index, possible CASCADE or admin queries | ~5 MB | 0 |
| `idx_emails_failed_retry` | Retry logic partial index, may be subsumed | ~2 MB | 0 |
| `idx_emails_mailbox_folder_date` | May serve folder+date combo, but other indexes likely cover it | ~10 MB | 0 |

**Investigation protocol for each index:**

1. Run `pg_stat_statements` query filtered for the index's column pattern
2. If queries found: document the query, confirm the index is the best plan, retain
3. If no queries found after 30-day window + zero scans: safe to drop
4. For `idx_emails_mailbox_sent` specifically: get the index definition via `pg_indexes`, then either formalize with a migration or drop

**Estimated recovery (Stage 3):** 0-94 MB depending on investigation outcomes. Most of these indexes are small (2-19 MB each).

### Stage 3 Platform Task — Migrate `thread_id` → `canonical_thread_id`

**Not an index task — a code refactor that, when complete, makes `idx_emails_thread` (~20 MB) droppable.**

The 6 active call sites currently using `thread_id`:

| File | Line | Pattern |
|------|------|---------|
| `backend/src/services/ai_email_analyzer.py` | 1071 | `.in_("thread_id", chunk)` — fetch prior messages for AI reply analysis |
| `backend/src/services/ai_digest_generator.py` | 679 | `.in_("thread_id", thread_ids)` — fetch thread messages for digest |
| `backend/src/services/ai_insights_engine.py` | 266 | `.eq("thread_id", thread_id).single()` |
| `backend/src/services/ai_insights_engine.py` | 271 | `.eq("thread_id", thread_id)` |
| `backend/src/services/comm_pattern_analyzer.py` | 354 | `.eq('thread_id', thread_id)` |
| `backend/src/services/langchain_tools.py` | 230 | `.eq("thread_id", thread_id)` |

**Why migrate:** `canonical_thread_id` (added in migration 055) was specifically designed to handle conversation grouping cases that `thread_id` misses (subject changes, cross-provider chains, forwarded threads). AI features using `thread_id` are missing context that canonical resolution would catch.

**Migration risk:** Any thread whose `canonical_thread_id` is NULL (resolver hasn't run yet, or resolution failed) would return no context. Caller code must handle this gracefully — either fall back to `thread_id` for unresolved threads, or skip those threads with a logged warning.

**Sequence:**
1. For each call site, change `.eq("thread_id", X)` / `.in_("thread_id", [...])` to use `canonical_thread_id`
2. Add fallback for NULL canonical_thread_id (use thread_id, log warning)
3. Wait one full week of production traffic to confirm `idx_emails_thread` scans drop to 0
4. Drop `idx_emails_thread` in Stage 2 of next cleanup cycle

---

### Total Estimated Recovery

| Stage | Indexes | Est. Recovery | Timeline |
|-------|---------|--------------|----------|
| Stage 1 | 0 drops, 1 creation, REINDEX | 5-15 MB (bloat) | Immediate |
| Stage 2 | 15 drops | 350-450 MB | After May 12 (30-day window) |
| Stage 3 | 0-13 drops (per-index) | 0-94 MB | Ongoing investigation |
| Stage 3 platform task | 1 drop after canonical_thread_id migration | ~20 MB | After 6-call-site refactor + 1 week verification |
| **Total** | **16-29 drops** | **~370-579 MB** | |

**Note:** The largest single index (`idx_emails_embedding`, ~903 MB) is KEEP — it's essential for vector search. The biggest win in this cleanup is `idx_emails_body_fts` at ~298 MB, which is superseded and should cleanly drop in Stage 2.
