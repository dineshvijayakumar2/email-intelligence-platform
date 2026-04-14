# Root Cause Analysis: 43 Indexes on the `emails` Table

## How It Happened

The `emails` table accumulated 43 indexes (including PK) totaling ~6.2 GB against 457 MB of actual table data — a 13.5× index-to-table ratio. This triggered a Supabase auto-disk-expansion from 10 GB to 15 GB. Seven specific process gaps allowed this to happen:

### 1. Initial over-indexing

`create_tables.sql` created 26 indexes on the `emails` table upfront, including single-column btree indexes on low-cardinality boolean columns (`is_outbound`, `is_reply`, `direction`). Boolean columns have at most 2-3 distinct values — a btree index on them provides almost no selectivity and is rarely chosen by the query planner over a sequential scan. These indexes were speculative: no specific query justified them at the time of creation.

### 2. Sprint-additive pattern

Each sprint (sprint2_010, sprint3_019) and feature migration (031, 043, 055, 066) added indexes to support new queries without checking whether existing indexes already covered the needed predicate shape. Result: multiple indexes with overlapping coverage on the same columns, none of which was ever removed.

### 3. Duplicate-purpose indexes

`optimize_dashboard_queries.sql` added `idx_emails_sent_date_only` (sent_date DESC) and `idx_emails_mailbox_count` (mailbox_id WHERE NOT NULL) — both functionally duplicate existing indexes (`idx_emails_sent_date` and `idx_emails_mailbox_id`). The WHERE clause on `mailbox_count` adds no value because `mailbox_id` is always NOT NULL.

### 4. Search evolution without cleanup

Full-text search migrated from per-column GIN indexes (`idx_emails_body_fts` at ~298 MB, `idx_emails_subject_fts` at ~15 MB) to a combined `search_text` tsvector column with its own GIN index (`idx_emails_search_text`). The old per-column indexes were never dropped. This is the single largest source of recoverable disk space (~313 MB).

### 5. No composite-first discipline

Many single-column indexes exist where composite indexes already cover the leading column. For example, `idx_emails_mailbox_id` is the leading column of `idx_emails_coverage_main`, `idx_emails_folder_mailbox`, `idx_emails_processing_status_mailbox`, `idx_emails_unresolved_threads`, and `idx_emails_resolved_msgid`. The planner can use any of these composites for mailbox_id-only filters, making the single-column index potentially redundant (though runtime stats show it is still actively scanned — the planner's preference is path-dependent).

### 6. No review gate

No PR checklist, no policy document, and no monthly audit existed before this analysis. Each developer adding a migration could create indexes freely without verifying whether existing indexes already served the query. The absence of an `EXPLAIN ANALYZE` requirement meant indexes were added based on intuition rather than measured need.

### 7. Ad-hoc index creation without migration files

At least one index (`idx_emails_mailbox_sent`) was created directly via the SQL console or Supabase dashboard without a corresponding migration file. This index has no documented definition, no documented purpose, and no code-level reference — yet it serves 120 active scans per the runtime snapshot. Ad-hoc indexes bypass all governance and make audits unreliable, since the migration file inventory is incomplete. Any future audit must cross-reference both migration files AND the live `pg_indexes` catalog to detect orphans.

## What's Being Done

See [EMAILS_INDEX_CLEANUP_PLAN.md](EMAILS_INDEX_CLEANUP_PLAN.md) for the staged cleanup, and [INDEX_POLICY.md](INDEX_POLICY.md) for the governance framework to prevent recurrence.
