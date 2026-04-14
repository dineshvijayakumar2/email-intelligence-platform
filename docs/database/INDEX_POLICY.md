# Index Policy — Email Intelligence Platform

This document governs the creation, review, and removal of database indexes across the platform.

---

## Safe Drop Criteria (Two-Signal Drop Rule)

**An index may only be dropped when BOTH conditions hold:**

1. The code audit finds no code path referencing its columns in a query predicate, AND
2. `pg_stat_user_indexes` shows zero scans over a rolling 30-day runtime window.

Either signal alone is insufficient. Code audits miss dynamic queries, PostgREST-generated predicates, and runtime-managed indexes. Runtime stats miss cold paths like monthly reports and rarely-used admin tooling. Both signals are required. Any index with even a single scan in the window is retained pending investigation, regardless of what the code audit concluded.

---

## Single Source of Truth for Index Definitions

All indexes on production tables must be created via committed migration files. Runtime-managed indexes (e.g., via `BulkIndexManager`) are permitted only for genuinely dynamic cases and must be documented in the migration corresponding to the table's base schema, with a comment pointing to the managing code. Ad-hoc indexes created via SQL console are prohibited. Any index discovered in production without a corresponding migration file is an incident: file a ticket, investigate what created it, and either formalize it via a retroactive migration or drop it after confirming zero usage.

---

## Core Principles

### Every index must have a named query it serves

No speculative indexes. When creating an index, document (in the migration file as a SQL comment) the specific query shape it optimizes. If you cannot name the query, the index should not exist.

### Composite-first rule

Prefer composite indexes over multiple single-column indexes where query shapes allow. A composite index on `(a, b, c)` can serve queries filtering on `a`, on `(a, b)`, and on `(a, b, c)`. A single-column index on `a` is redundant if a composite starting with `a` already exists and covers the needed query.

Exceptions: partial indexes with WHERE clauses serve a different purpose and are not redundant with composites on the same columns.

---

## Migration Requirements

Every migration that adds an index must include:

1. **Query documentation** — a SQL comment in the migration file showing the exact query or query shape the index serves
2. **EXPLAIN ANALYZE result** — included in the PR description, showing the improvement (before/after execution plans)
3. **Redundancy audit** — confirmation that no existing index already serves the same query shape. Check:
   - `pg_indexes` for indexes with the same or overlapping leading columns
   - `BulkIndexManager` registry for runtime-managed indexes
   - The consolidated index set in `EMAILS_INDEX_CLEANUP_PLAN.md`
4. **Drop-before-add** — when adding a new index, audit existing indexes for redundancy and drop any superseded indexes in the same migration

---

## Monthly Review Process

Run `scripts/db/index_audit.sql` (or `scripts/db/index_audit.py`) monthly. Review:

- **Zero-scan indexes** older than 30 days since `pg_stat_reset()`: apply the Two-Signal Drop Rule (code audit + runtime stats) and schedule drops for confirmed dead indexes
- **Index-to-table size ratio**: flag any table where total index size exceeds 2× table size
- **Duplicate leading columns**: flag indexes whose leading column(s) are a prefix of another existing index

---

## Naming Convention

```
idx_<table>_<columns>_<purpose>
```

- `<table>`: table name (e.g., `emails`, `qb_operations`)
- `<columns>`: abbreviated column list in index order (e.g., `mailbox_date`, `sender_email`)
- `<purpose>`: optional suffix for partial or specialized indexes (e.g., `_unlinked`, `_failed`)

Examples:
- `idx_emails_mailbox_date` — btree on (mailbox_id, sent_date)
- `idx_emails_mailbox_unlinked` — partial btree WHERE customer_contact_id IS NULL
- `idx_emails_embedding` — HNSW vector index

Enforce this convention during PR review. Reject indexes with unclear or non-standard names.

---

## Index Type Guidelines

| Type | Use Case | Timeout | Notes |
|------|----------|---------|-------|
| btree | Equality, range, sorting | 30s | Default. Leave in place during bulk writes. |
| GIN | Full-text search (tsvector), JSONB, arrays | 300s | Use `exec_sql_extended` for creation. |
| HNSW | Vector similarity (pgvector) | 300s | Drop before bulk embedding writes, recreate after. Needs `maintenance_work_mem = '256MB'`. |
| GiST | Range types, geometric | 30s | Rarely needed in this project. |

---

## Review Checklist (for PRs touching migrations)

- [ ] If this PR adds an index: the migration file documents the query it serves
- [ ] If this PR adds an index: EXPLAIN ANALYZE output is in the PR description
- [ ] If this PR adds an index: existing indexes were audited for redundancy
- [ ] If this PR adds an index: no existing index already serves this query shape
