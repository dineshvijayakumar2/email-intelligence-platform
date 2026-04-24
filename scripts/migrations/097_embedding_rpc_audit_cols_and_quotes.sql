-- 097_embedding_rpc_audit_cols_and_quotes.sql
-- 1. Update 3 existing batch_update_embeddings RPCs to accept audit columns
-- 2. Add embedding + audit columns to qb_quotes
-- 3. Create batch_update_embeddings_quotes RPC

-- ── 1. Update existing RPCs with audit column params ─────────────────

CREATE OR REPLACE FUNCTION batch_update_embeddings_emails(
    p_ids uuid[],
    p_embeddings vector(768)[],
    p_embedding_model text DEFAULT NULL,
    p_embedded_at timestamptz DEFAULT NULL
)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET statement_timeout = '30s'
AS $$
DECLARE
    updated integer;
BEGIN
    PERFORM set_config('statement_timeout', '30000', true);
    UPDATE emails e
    SET embedding = u.emb,
        embedding_model = COALESCE(p_embedding_model, e.embedding_model),
        embedded_at = COALESCE(p_embedded_at, e.embedded_at)
    FROM unnest(p_ids, p_embeddings) AS u(id, emb)
    WHERE e.id = u.id;

    GET DIAGNOSTICS updated = ROW_COUNT;
    RETURN updated;
END;
$$;

CREATE OR REPLACE FUNCTION batch_update_embeddings_companies(
    p_ids uuid[],
    p_embeddings vector(768)[],
    p_embedding_model text DEFAULT NULL,
    p_embedded_at timestamptz DEFAULT NULL
)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET statement_timeout = '30s'
AS $$
DECLARE
    updated integer;
BEGIN
    PERFORM set_config('statement_timeout', '30000', true);
    UPDATE customer_companies c
    SET embedding = u.emb,
        embedding_model = COALESCE(p_embedding_model, c.embedding_model),
        embedded_at = COALESCE(p_embedded_at, c.embedded_at)
    FROM unnest(p_ids, p_embeddings) AS u(id, emb)
    WHERE c.id = u.id;

    GET DIAGNOSTICS updated = ROW_COUNT;
    RETURN updated;
END;
$$;

CREATE OR REPLACE FUNCTION batch_update_embeddings_operations(
    p_ids uuid[],
    p_embeddings vector(768)[],
    p_embedding_model text DEFAULT NULL,
    p_embedded_at timestamptz DEFAULT NULL
)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET statement_timeout = '30s'
AS $$
DECLARE
    updated integer;
BEGIN
    PERFORM set_config('statement_timeout', '30000', true);
    UPDATE qb_operations o
    SET embedding = u.emb,
        embedding_model = COALESCE(p_embedding_model, o.embedding_model),
        embedded_at = COALESCE(p_embedded_at, o.embedded_at)
    FROM unnest(p_ids, p_embeddings) AS u(id, emb)
    WHERE o.id = u.id;

    GET DIAGNOSTICS updated = ROW_COUNT;
    RETURN updated;
END;
$$;

-- ── 2. Add embedding + audit columns to qb_quotes ───────────────────

ALTER TABLE qb_quotes
  ADD COLUMN IF NOT EXISTS embedding vector(768),
  ADD COLUMN IF NOT EXISTS embedding_model TEXT,
  ADD COLUMN IF NOT EXISTS embedded_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_qb_quotes_embedding_model
  ON qb_quotes (embedding_model)
  WHERE embedding IS NOT NULL;

-- ── 3. New RPC for quotes ───────────────────────────────────────────

CREATE OR REPLACE FUNCTION batch_update_embeddings_quotes(
    p_ids uuid[],
    p_embeddings vector(768)[],
    p_embedding_model text DEFAULT NULL,
    p_embedded_at timestamptz DEFAULT NULL
)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET statement_timeout = '30s'
AS $$
DECLARE
    updated integer;
BEGIN
    PERFORM set_config('statement_timeout', '30000', true);
    UPDATE qb_quotes q
    SET embedding = u.emb,
        embedding_model = COALESCE(p_embedding_model, q.embedding_model),
        embedded_at = COALESCE(p_embedded_at, q.embedded_at)
    FROM unnest(p_ids, p_embeddings) AS u(id, emb)
    WHERE q.id = u.id;

    GET DIAGNOSTICS updated = ROW_COUNT;
    RETURN updated;
END;
$$;

-- ── 4. Grants ───────────────────────────────────────────────────────

GRANT EXECUTE ON FUNCTION batch_update_embeddings_emails(uuid[], vector(768)[], text, timestamptz) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION batch_update_embeddings_companies(uuid[], vector(768)[], text, timestamptz) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION batch_update_embeddings_operations(uuid[], vector(768)[], text, timestamptz) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION batch_update_embeddings_quotes(uuid[], vector(768)[], text, timestamptz) TO anon, authenticated;
