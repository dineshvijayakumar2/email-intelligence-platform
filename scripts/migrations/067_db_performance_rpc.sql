-- ============================================================================
-- Migration 067: RPC for database performance monitoring dashboard
-- ============================================================================
-- Exposes pg_stat_statements and table/index stats via RPC so the admin
-- dashboard can proactively surface IO-heavy queries and missing indexes.
-- ============================================================================

-- 1. Top queries by total execution time
CREATE OR REPLACE FUNCTION get_db_slow_queries(
    p_limit INTEGER DEFAULT 15
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER  -- needs superuser-level access to pg_stat_statements
STABLE
AS $$
BEGIN
    RETURN (
        SELECT COALESCE(jsonb_agg(row_data), '[]'::jsonb)
        FROM (
            SELECT jsonb_build_object(
                'query',         LEFT(query, 300),
                'calls',         calls,
                'total_time_s',  ROUND((total_exec_time / 1000)::numeric, 1),
                'mean_time_ms',  ROUND(mean_exec_time::numeric, 2),
                'max_time_ms',   ROUND(max_exec_time::numeric, 1),
                'rows',          rows,
                'rows_per_call', CASE WHEN calls > 0 THEN ROUND((rows::numeric / calls), 1) ELSE 0 END
            ) AS row_data
            FROM pg_stat_statements
            WHERE query NOT LIKE '%pg_stat%'
              AND query NOT LIKE 'COMMIT%'
              AND query NOT LIKE 'BEGIN%'
              AND query NOT LIKE 'SET %'
              AND query NOT LIKE 'DEALLOCATE%'
            ORDER BY total_exec_time DESC
            LIMIT p_limit
        ) sub
    );
END;
$$;

GRANT EXECUTE ON FUNCTION get_db_slow_queries(INTEGER) TO authenticated;

-- 2. Table sizes and row counts
CREATE OR REPLACE FUNCTION get_db_table_stats()
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
STABLE
AS $$
BEGIN
    RETURN (
        SELECT COALESCE(jsonb_agg(row_data), '[]'::jsonb)
        FROM (
            SELECT jsonb_build_object(
                'table_name',   t.tablename,
                'row_estimate', c.reltuples::bigint,
                'total_size',   pg_size_pretty(pg_total_relation_size(c.oid)),
                'total_bytes',  pg_total_relation_size(c.oid),
                'table_size',   pg_size_pretty(pg_relation_size(c.oid)),
                'index_size',   pg_size_pretty(pg_indexes_size(c.oid))
            ) AS row_data
            FROM pg_tables t
            JOIN pg_class c ON c.relname = t.tablename
            WHERE t.schemaname = 'public'
              AND c.reltuples > 0
            ORDER BY pg_total_relation_size(c.oid) DESC
            LIMIT 25
        ) sub
    );
END;
$$;

GRANT EXECUTE ON FUNCTION get_db_table_stats() TO authenticated;

-- 3. Index usage stats — find unused or missing indexes
CREATE OR REPLACE FUNCTION get_db_index_stats()
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
STABLE
AS $$
BEGIN
    RETURN (
        SELECT COALESCE(jsonb_agg(row_data), '[]'::jsonb)
        FROM (
            SELECT jsonb_build_object(
                'table_name',     s.relname,
                'index_name',     s.indexrelname,
                'index_scans',    s.idx_scan,
                'rows_read',      s.idx_tup_read,
                'rows_fetched',   s.idx_tup_fetch,
                'index_size',     pg_size_pretty(pg_relation_size(s.indexrelid))
            ) AS row_data
            FROM pg_stat_user_indexes s
            WHERE s.schemaname = 'public'
            ORDER BY s.idx_scan ASC, pg_relation_size(s.indexrelid) DESC
            LIMIT 30
        ) sub
    );
END;
$$;

GRANT EXECUTE ON FUNCTION get_db_index_stats() TO authenticated;

-- 4. Cache hit ratio — key health indicator
CREATE OR REPLACE FUNCTION get_db_cache_stats()
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
STABLE
AS $$
BEGIN
    RETURN jsonb_build_object(
        'heap_hit_ratio', (
            SELECT ROUND(
                100.0 * SUM(heap_blks_hit) / NULLIF(SUM(heap_blks_hit) + SUM(heap_blks_read), 0), 2
            )
            FROM pg_statio_user_tables
        ),
        'index_hit_ratio', (
            SELECT ROUND(
                100.0 * SUM(idx_blks_hit) / NULLIF(SUM(idx_blks_hit) + SUM(idx_blks_read), 0), 2
            )
            FROM pg_statio_user_indexes
        ),
        'db_size', (SELECT pg_size_pretty(pg_database_size(current_database()))),
        'db_size_bytes', (SELECT pg_database_size(current_database()))
    );
END;
$$;

GRANT EXECUTE ON FUNCTION get_db_cache_stats() TO authenticated;
