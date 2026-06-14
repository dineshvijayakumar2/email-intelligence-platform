-- ============================================================================
-- Migration 123: Fix capability_tags double-encoding in batch_update_classifications
-- ============================================================================
-- The RPC declared p_capability_tags as jsonb[]. Callers (reclassify_all and the
-- Layer-1 reclassify) send each element as a JSON-encoded TEXT string ('["Foo"]'),
-- because PostgREST cannot map a Python list-of-lists onto a jsonb[] param
-- (it treats nested arrays as a multidimensional array -> dimension-mismatch error).
-- Result: each json string was stored as a jsonb STRING scalar ("[\"Foo\"]"),
-- i.e. capability_tags became double-encoded for every reclassified row, breaking
-- any SQL consumer that does capability_tags->>0 / jsonb_array_length.
--
-- Fix: accept p_capability_tags as text[] and cast ::jsonb inside, so '["Foo"]'
-- becomes a proper jsonb array ["Foo"]. reclassify_all already passes json.dumps()
-- strings, so it is compatible with no app change.
-- ============================================================================

DROP FUNCTION IF EXISTS batch_update_classifications(uuid[], jsonb[], boolean[], boolean[], boolean[], boolean[], text[]);

CREATE OR REPLACE FUNCTION batch_update_classifications(
    p_ids uuid[],
    p_capability_tags text[],          -- JSON-encoded array text, e.g. '["Embellishment"]'
    p_has_coating boolean[],
    p_has_sewing boolean[],
    p_has_outsource_component boolean[],
    p_am_rush boolean[],
    p_row_type text[]
)
RETURNS integer
LANGUAGE plpgsql
SET search_path = public
AS $$
DECLARE
    updated integer := 0;
BEGIN
    FOR i IN 1..array_length(p_ids, 1) LOOP
        UPDATE qb_operations SET
            capability_tags = p_capability_tags[i]::jsonb,   -- text -> proper jsonb array
            has_coating = p_has_coating[i],
            has_sewing = p_has_sewing[i],
            has_outsource_component = p_has_outsource_component[i],
            am_rush = p_am_rush[i],
            row_type = p_row_type[i]
        WHERE id = p_ids[i];
        updated := updated + 1;
    END LOOP;
    RETURN updated;
END;
$$;
