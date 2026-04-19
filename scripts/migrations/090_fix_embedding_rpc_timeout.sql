-- ============================================================================
-- Migration 090: Add statement_timeout to batch embedding RPCs
-- ============================================================================
-- Problem: batch_update_embeddings_emails times out at default 8s when
-- updating 100 rows with 768-dim vectors + HNSW index maintenance.
-- Fix: SET statement_timeout = '30s' on all three embedding RPCs.
-- ============================================================================

CREATE OR REPLACE FUNCTION batch_update_embeddings_emails(
    p_ids uuid[],
    p_embeddings vector(768)[]
)
RETURNS integer
LANGUAGE plpgsql
SET statement_timeout = '30s'
AS $$
DECLARE
    updated integer;
BEGIN
    UPDATE emails e
    SET embedding = u.emb
    FROM unnest(p_ids, p_embeddings) AS u(id, emb)
    WHERE e.id = u.id;

    GET DIAGNOSTICS updated = ROW_COUNT;
    RETURN updated;
END;
$$;

CREATE OR REPLACE FUNCTION batch_update_embeddings_companies(
    p_ids uuid[],
    p_embeddings vector(768)[]
)
RETURNS integer
LANGUAGE plpgsql
SET statement_timeout = '30s'
AS $$
DECLARE
    updated integer;
BEGIN
    UPDATE customer_companies c
    SET embedding = u.emb
    FROM unnest(p_ids, p_embeddings) AS u(id, emb)
    WHERE c.id = u.id;

    GET DIAGNOSTICS updated = ROW_COUNT;
    RETURN updated;
END;
$$;

CREATE OR REPLACE FUNCTION batch_update_embeddings_operations(
    p_ids uuid[],
    p_embeddings vector(768)[]
)
RETURNS integer
LANGUAGE plpgsql
SET statement_timeout = '30s'
AS $$
DECLARE
    updated integer;
BEGIN
    UPDATE qb_operations o
    SET embedding = u.emb
    FROM unnest(p_ids, p_embeddings) AS u(id, emb)
    WHERE o.id = u.id;

    GET DIAGNOSTICS updated = ROW_COUNT;
    RETURN updated;
END;
$$;

GRANT EXECUTE ON FUNCTION batch_update_embeddings_emails(uuid[], vector(768)[]) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION batch_update_embeddings_companies(uuid[], vector(768)[]) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION batch_update_embeddings_operations(uuid[], vector(768)[]) TO anon, authenticated;
