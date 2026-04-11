-- ============================================================================
-- Migration 070: Fast vector stats RPC — replaces 6 COUNT queries with 1
-- ============================================================================

CREATE OR REPLACE FUNCTION get_vector_stats(p_client_id UUID)
RETURNS JSONB
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN jsonb_build_object(
        'emails', jsonb_build_object(
            'total',    (SELECT COUNT(*) FROM emails WHERE client_id = p_client_id),
            'embedded', (SELECT COUNT(*) FROM emails WHERE client_id = p_client_id AND embedding IS NOT NULL)
        ),
        'companies', jsonb_build_object(
            'total',    (SELECT COUNT(*) FROM customer_companies WHERE client_id = p_client_id),
            'embedded', (SELECT COUNT(*) FROM customer_companies WHERE client_id = p_client_id AND embedding IS NOT NULL)
        ),
        'operations', jsonb_build_object(
            'total',    (SELECT COUNT(*) FROM qb_operations WHERE client_id = p_client_id),
            'embedded', (SELECT COUNT(*) FROM qb_operations WHERE client_id = p_client_id AND embedding IS NOT NULL)
        )
    );
END;
$$;

GRANT EXECUTE ON FUNCTION get_vector_stats(UUID) TO anon, authenticated;
