-- ============================================================================
-- Migration 040: Batch classification update RPC
-- ============================================================================
-- reclassify_all does 1 REST call per row (600K calls for full dataset).
-- This RPC accepts arrays and updates all rows in one DB round-trip.
-- ============================================================================

CREATE OR REPLACE FUNCTION batch_update_classifications(
    p_ids uuid[],
    p_capability_tags jsonb[],
    p_has_coating boolean[],
    p_has_sewing boolean[],
    p_has_outsource_component boolean[],
    p_am_rush boolean[],
    p_row_type text[]
)
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    updated integer := 0;
BEGIN
    FOR i IN 1..array_length(p_ids, 1) LOOP
        UPDATE qb_operations SET
            capability_tags = p_capability_tags[i],
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
