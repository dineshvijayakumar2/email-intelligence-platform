-- ============================================================================
-- Migration 076: Fix type mismatch in batch_update_qb_capabilities
-- ============================================================================
--
-- ⚠️  REQUIRES HUMAN REVIEW BEFORE EXECUTION.
--     Transactional — safe to run in Supabase SQL Editor.
--
-- ─── Problem ───────────────────────────────────────────────────────────────
-- Migration 072 defined `batch_update_qb_capabilities` with this CASE:
--
--     capability_tags = CASE
--         WHEN u.capability_tags IS NOT NULL AND u.capability_tags != ''
--         THEN string_to_array(u.capability_tags, ',')
--         ELSE o.capability_tags END,
--
-- `string_to_array(...)` returns `text[]`, but `qb_operations.capability_tags`
-- is `jsonb`. The CASE fails at runtime with:
--
--     ERROR: CASE types jsonb and text[] cannot be matched (SQLSTATE 42804)
--
-- The bug has existed in production since migration 072 was applied — the RPC
-- has never executed successfully. QB operations classification fell back to
-- the old per-row UPDATE path (which worked by accident via supabase-py's
-- JSON serialization of Python lists).
--
-- Discovered 2026-04-13 by integration test test_qb_batch_rpcs when refactoring
-- the classification code to use this RPC.
--
-- ─── Fix ───────────────────────────────────────────────────────────────────
-- Wrap `string_to_array(...)` in `to_jsonb()` so both CASE branches return
-- jsonb. Semantics are preserved: supabase-py already serializes Python lists
-- as JSON arrays to the column.
--
-- ROLLBACK: restore the broken version from migration 072 (not recommended —
-- the old version was non-functional).
-- ============================================================================

CREATE OR REPLACE FUNCTION batch_update_qb_capabilities(p_updates JSONB)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    updated INTEGER;
BEGIN
    UPDATE qb_operations o
    SET capability_tags = CASE
            WHEN u.capability_tags IS NOT NULL AND u.capability_tags != ''
            THEN to_jsonb(string_to_array(u.capability_tags, ','))  -- FIX: wrap as jsonb
            ELSE o.capability_tags END,
        has_coating = COALESCE((u.has_coating)::BOOLEAN, o.has_coating),
        has_sewing = COALESCE((u.has_sewing)::BOOLEAN, o.has_sewing),
        has_outsource_component = COALESCE((u.has_outsource_component)::BOOLEAN, o.has_outsource_component),
        am_rush = COALESCE((u.am_rush)::BOOLEAN, o.am_rush),
        row_type = COALESCE(u.row_type, o.row_type)
    FROM jsonb_to_recordset(p_updates) AS u(
        id TEXT,
        capability_tags TEXT,
        has_coating TEXT,
        has_sewing TEXT,
        has_outsource_component TEXT,
        am_rush TEXT,
        row_type TEXT
    )
    WHERE o.id = u.id::UUID;

    GET DIAGNOSTICS updated = ROW_COUNT;
    RETURN updated;
END;
$$;

GRANT EXECUTE ON FUNCTION batch_update_qb_capabilities(JSONB) TO anon, authenticated;

COMMENT ON FUNCTION batch_update_qb_capabilities(JSONB) IS
  'Batch update capability fields on qb_operations. Fixes type mismatch bug in migration 072 (jsonb vs text[]). '
  'See migration 076 for full context.';
