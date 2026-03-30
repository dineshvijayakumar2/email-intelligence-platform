-- 044: Fix batch_update_contact_companies — preserve existing company links
-- Problem: When the extraction pipeline passes NULL customer_company_id in the
-- update payload (e.g., company not yet resolved), the SQL function unconditionally
-- overwrites the existing non-null value with NULL, breaking previously-correct links.
-- Fix: Use COALESCE so NULL input preserves the existing value.

CREATE OR REPLACE FUNCTION batch_update_contact_companies(
    updates JSONB
) RETURNS TABLE (
    updated_count INTEGER,
    error_count INTEGER
) AS $$
DECLARE
    v_updated_count INTEGER := 0;
    v_error_count INTEGER := 0;
BEGIN
    UPDATE customer_contacts c
    SET
        customer_company_id = COALESCE(u.customer_company_id::UUID, c.customer_company_id),
        first_name = COALESCE(u.first_name, c.first_name),
        last_name = COALESCE(u.last_name, c.last_name),
        full_name = COALESCE(u.full_name, c.full_name),
        contact_type = COALESCE(u.contact_type, c.contact_type, 'person'),
        updated_at = NOW()
    FROM jsonb_to_recordset(updates) AS u(
        email_address TEXT,
        client_id UUID,
        customer_company_id TEXT,
        first_name TEXT,
        last_name TEXT,
        full_name TEXT,
        contact_type TEXT
    )
    WHERE c.email_address = u.email_address
      AND c.client_id = u.client_id;

    GET DIAGNOSTICS v_updated_count = ROW_COUNT;
    RETURN QUERY SELECT v_updated_count, v_error_count;

EXCEPTION WHEN OTHERS THEN
    v_error_count := 1;
    RETURN QUERY SELECT v_updated_count, v_error_count;
END;
$$ LANGUAGE plpgsql;
