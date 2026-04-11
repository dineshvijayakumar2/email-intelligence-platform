-- ============================================================================
-- Migration 072: Helpers for bulk operation optimization
-- ============================================================================

-- 1. Extended-timeout DDL execution for slow index operations (HNSW, GIN)
--    btree indexes rebuild in <1s, but HNSW on 200K+ vectors needs minutes.
CREATE OR REPLACE FUNCTION exec_sql_extended(p_query TEXT, p_timeout_s INTEGER DEFAULT 300)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    EXECUTE format('SET LOCAL statement_timeout = %L', (p_timeout_s * 1000) || 'ms');
    EXECUTE p_query;
END;
$$;

GRANT EXECUTE ON FUNCTION exec_sql_extended(TEXT, INTEGER) TO authenticated;

-- 2. Batch update capability classifications on qb_operations
--    Replaces 1-by-1 UPDATE loop in quickbase_sync._enrich_capabilities()
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
            THEN string_to_array(u.capability_tags, ',')
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

-- 3. Batch update contact_email on qb_operations
--    Replaces 1-by-1 UPDATE loop in quickbase_sync._join_contact_email()
CREATE OR REPLACE FUNCTION batch_update_qb_contact_emails(p_updates JSONB)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    updated INTEGER;
BEGIN
    UPDATE qb_operations o
    SET contact_email = u.contact_email
    FROM jsonb_to_recordset(p_updates) AS u(id TEXT, contact_email TEXT)
    WHERE o.id = u.id::UUID;

    GET DIAGNOSTICS updated = ROW_COUNT;
    RETURN updated;
END;
$$;

GRANT EXECUTE ON FUNCTION batch_update_qb_contact_emails(JSONB) TO anon, authenticated;
