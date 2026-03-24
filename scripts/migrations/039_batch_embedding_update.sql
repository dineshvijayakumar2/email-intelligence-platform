-- ============================================================================
-- Migration 039: Batch embedding update RPC functions
-- ============================================================================
-- Individual row updates (1 REST call per row) are too slow for embedding
-- 26K+ emails. These RPC functions accept arrays and update in bulk.
-- ============================================================================

CREATE OR REPLACE FUNCTION batch_update_embeddings_emails(
    p_ids uuid[],
    p_embeddings vector(768)[]
)
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    updated integer := 0;
BEGIN
    FOR i IN 1..array_length(p_ids, 1) LOOP
        UPDATE emails SET embedding = p_embeddings[i] WHERE id = p_ids[i];
        updated := updated + 1;
    END LOOP;
    RETURN updated;
END;
$$;

CREATE OR REPLACE FUNCTION batch_update_embeddings_companies(
    p_ids uuid[],
    p_embeddings vector(768)[]
)
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    updated integer := 0;
BEGIN
    FOR i IN 1..array_length(p_ids, 1) LOOP
        UPDATE customer_companies SET embedding = p_embeddings[i] WHERE id = p_ids[i];
        updated := updated + 1;
    END LOOP;
    RETURN updated;
END;
$$;

CREATE OR REPLACE FUNCTION batch_update_embeddings_operations(
    p_ids uuid[],
    p_embeddings vector(768)[]
)
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    updated integer := 0;
BEGIN
    FOR i IN 1..array_length(p_ids, 1) LOOP
        UPDATE qb_operations SET embedding = p_embeddings[i] WHERE id = p_ids[i];
        updated := updated + 1;
    END LOOP;
    RETURN updated;
END;
$$;
