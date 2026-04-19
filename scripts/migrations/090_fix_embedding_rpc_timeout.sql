-- ============================================================================
-- Migration 090: Fix batch embedding RPC timeouts
-- ============================================================================
-- Problem: batch_update_embeddings_emails times out at Supabase's 8s default
-- when updating rows with 768-dim vectors + HNSW index maintenance.
-- Fix: SECURITY DEFINER (runs as owner, bypasses role-level timeout) +
--       explicit SET LOCAL statement_timeout inside function body +
--       function-level SET clause as belt-and-suspenders.
-- App-side: DB_CHUNK reduced from 100 to 25 to stay safe within 8s anyway.
-- ============================================================================

CREATE OR REPLACE FUNCTION batch_update_embeddings_emails(
    p_ids uuid[],
    p_embeddings vector(768)[]
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
SECURITY DEFINER
SET search_path = public
SET statement_timeout = '30s'
AS $$
DECLARE
    updated integer;
BEGIN
    PERFORM set_config('statement_timeout', '30000', true);
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
SECURITY DEFINER
SET search_path = public
SET statement_timeout = '30s'
AS $$
DECLARE
    updated integer;
BEGIN
    PERFORM set_config('statement_timeout', '30000', true);
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
