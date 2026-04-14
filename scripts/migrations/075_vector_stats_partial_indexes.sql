-- ============================================================================
-- Migration 075: Partial indexes for fast vector stats counts
-- ============================================================================
--
-- ⚠️  REQUIRES HUMAN REVIEW BEFORE EXECUTION.
-- ⚠️  MUST RUN OUTSIDE A TRANSACTION (CREATE INDEX CONCURRENTLY).
--     Run via psql or the Python autocommit pattern used for migration 074.
--
-- ─── Problem it solves ─────────────────────────────────────────────────────
-- The get_vector_stats RPC (migration 070) does 6 COUNT(*) queries across
-- emails / customer_companies / qb_operations. Two of every three queries
-- filter on `client_id = ? AND embedding IS NOT NULL`. With no index covering
-- that predicate, Postgres does:
--   1. Index scan on idx_<table>_client → get row IDs for the client
--   2. For each row, heap fetch to read the `embedding` column
-- With buffer cache hit at ~67% on the emails table (8GB DB vs 256MB
-- shared_buffers), step 2 is disk I/O for thousands of rows. On the 266K-row
-- emails table this takes >8 seconds — longer than statement_timeout — so
-- the endpoint times out and the UI sees zeros.
--
-- ─── Fix ───────────────────────────────────────────────────────────────────
-- Add a partial btree on `(client_id) WHERE embedding IS NOT NULL` for each
-- table. This is:
--   - Small (only covers rows where embedding is populated)
--   - Fast to scan (index-only scan — no heap access)
--   - Maintenance-cheap (updates only fire when embedding goes NULL ↔ NOT NULL,
--     which is only during reembed / deletions)
--
-- Expected impact: COUNT(*) for the "embedded" stat drops from 8s timeout to
-- <100ms. The "total" COUNT (no embedding filter) is already fast via the
-- existing idx_<table>_client.
--
-- ─── INDEX_POLICY compliance ───────────────────────────────────────────────
-- This migration conforms to docs/database/INDEX_POLICY.md:
--   [x] Named query it serves (get_vector_stats RPC in migration 070)
--   [x] No existing index covers this exact predicate — checked pg_indexes
--   [x] Composite-first rule — we already have idx_<table>_client; adding a
--       partial on the same column is a different-purpose index (covers a
--       different predicate) and is justified
--   [x] EXPLAIN ANALYZE expected improvement documented above
--
-- ─── Reviewer checklist ────────────────────────────────────────────────────
--   [ ] Run OUTSIDE a transaction (CONCURRENTLY)
--   [ ] Run during low-traffic window — CONCURRENTLY takes longer and reads
--       the whole table once, which adds IO pressure
--   [ ] After it completes, ANALYZE each table so the planner picks the
--       new index
--   [ ] Verify with EXPLAIN ANALYZE on one of the RPC queries:
--         EXPLAIN ANALYZE
--         SELECT COUNT(*) FROM emails WHERE client_id = '<uuid>' AND embedding IS NOT NULL;
--       Should show "Index Only Scan using idx_emails_client_embedded"
--   [ ] Update BulkIndexManager registry (bulk_index_manager.py) if these
--       indexes should be managed by it — they should NOT be, since they're
--       partial indexes on (client_id) that serve a read path, not write
--       performance. Leave out of registry.
--
-- ROLLBACK:
--   DROP INDEX CONCURRENTLY IF EXISTS idx_emails_client_embedded;
--   DROP INDEX CONCURRENTLY IF EXISTS idx_companies_client_embedded;
--   DROP INDEX CONCURRENTLY IF EXISTS idx_qb_ops_client_embedded;
-- ============================================================================

-- Emails: largest table, biggest win
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_emails_client_embedded
  ON emails(client_id)
  WHERE embedding IS NOT NULL;

COMMENT ON INDEX idx_emails_client_embedded IS
  'Serves: get_vector_stats RPC COUNT of emails with embeddings per client. '
  'Partial index on populated rows only — enables index-only scan.';

-- Companies: smaller table but same query shape
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_companies_client_embedded
  ON customer_companies(client_id)
  WHERE embedding IS NOT NULL;

COMMENT ON INDEX idx_companies_client_embedded IS
  'Serves: get_vector_stats RPC COUNT of companies with embeddings per client.';

-- QB Operations
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_qb_ops_client_embedded
  ON qb_operations(client_id)
  WHERE embedding IS NOT NULL;

COMMENT ON INDEX idx_qb_ops_client_embedded IS
  'Serves: get_vector_stats RPC COUNT of qb_operations with embeddings per client.';

-- After the indexes exist, update table statistics so the planner picks them up.
-- (ANALYZE is cheap; don't skip it, or queries may still use the slower plan
-- until the next autovacuum analyze cycle.)
ANALYZE emails;
ANALYZE customer_companies;
ANALYZE qb_operations;
