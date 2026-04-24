-- 096_add_embedding_audit_columns.sql
-- Adds model + timestamp audit columns to tables with vector embeddings.
-- Nulls out all pre-audit embeddings (mixed Gemini/OpenAI with no provenance)
-- so the reembed pipeline regenerates them cleanly with embedding_model stamped.
--
-- HNSW indexes are dropped first so the bulk NULL UPDATE is fast (~seconds
-- instead of minutes). The reembed runner's BulkIndexManager recreates them
-- after re-embedding completes.

-- ── 1. Add audit columns ─────────────────────────────────────────────

ALTER TABLE emails
  ADD COLUMN IF NOT EXISTS embedding_model TEXT,
  ADD COLUMN IF NOT EXISTS embedded_at TIMESTAMPTZ;

ALTER TABLE qb_operations
  ADD COLUMN IF NOT EXISTS embedding_model TEXT,
  ADD COLUMN IF NOT EXISTS embedded_at TIMESTAMPTZ;

ALTER TABLE customer_companies
  ADD COLUMN IF NOT EXISTS embedding_model TEXT,
  ADD COLUMN IF NOT EXISTS embedded_at TIMESTAMPTZ;

-- ── 2. Drop HNSW indexes before bulk null-out ────────────────────────

DROP INDEX IF EXISTS idx_emails_embedding;
DROP INDEX IF EXISTS idx_qb_operations_embedding;
DROP INDEX IF EXISTS idx_companies_embedding;

-- ── 3. Null out stale embeddings (no audit trail = not trustworthy) ──

UPDATE emails
  SET embedding = NULL
  WHERE embedding IS NOT NULL AND embedding_model IS NULL;

UPDATE qb_operations
  SET embedding = NULL
  WHERE embedding IS NOT NULL AND embedding_model IS NULL;

UPDATE customer_companies
  SET embedding = NULL
  WHERE embedding IS NOT NULL AND embedding_model IS NULL;

-- ── 4. Partial indexes on embedding_model ────────────────────────────
-- HNSW indexes are NOT recreated here — the reembed runner owns that.

CREATE INDEX IF NOT EXISTS idx_emails_embedding_model
  ON emails (embedding_model)
  WHERE embedding IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_qb_operations_embedding_model
  ON qb_operations (embedding_model)
  WHERE embedding IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_customer_companies_embedding_model
  ON customer_companies (embedding_model)
  WHERE embedding IS NOT NULL;
