-- ============================================================================
-- Migration 071: exec_sql RPC for DDL operations (index management)
-- ============================================================================
-- Allows the application to drop/create indexes during bulk operations.
-- SECURITY DEFINER: runs as the function owner (superuser), not the caller.
-- Only authenticated users can call this.
-- ============================================================================

CREATE OR REPLACE FUNCTION exec_sql(query TEXT)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    EXECUTE query;
END;
$$;

GRANT EXECUTE ON FUNCTION exec_sql(TEXT) TO authenticated;
