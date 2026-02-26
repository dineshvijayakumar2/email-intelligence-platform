-- =========================================================================
-- Sprint 2 Migration 003: Enable Batch Operations
-- =========================================================================
-- Purpose: Add unique constraints and batch update functions for performance
-- Run this after testing the extraction pipeline
-- =========================================================================

-- =========================================================================
-- PART 1: Add Unique Constraint on customer_contacts
-- =========================================================================
-- This enables batch upsert with ON CONFLICT (like customer_companies)

-- Check if constraint already exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'customer_contacts_client_email_unique'
    ) THEN
        ALTER TABLE customer_contacts
        ADD CONSTRAINT customer_contacts_client_email_unique
        UNIQUE (client_id, email_address);

        RAISE NOTICE '✅ Added unique constraint on (client_id, email_address)';
    ELSE
        RAISE NOTICE '⚠️  Unique constraint already exists, skipping';
    END IF;
END $$;

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_customer_contacts_client_email
ON customer_contacts(client_id, email_address);

COMMENT ON CONSTRAINT customer_contacts_client_email_unique ON customer_contacts
IS 'Ensures one contact per email per client - enables batch upsert';

-- =========================================================================
-- PART 2: Batch Update Function for Contact Roles
-- =========================================================================
-- Accepts JSONB array and updates multiple contacts in one operation

CREATE OR REPLACE FUNCTION batch_update_contact_roles(
    updates JSONB
) RETURNS TABLE (
    updated_count INTEGER,
    error_count INTEGER
) AS $$
DECLARE
    v_updated_count INTEGER := 0;
    v_error_count INTEGER := 0;
BEGIN
    -- Update contact roles from JSONB array
    UPDATE customer_contacts c
    SET
        job_title = u.job_title,
        seniority_level = u.seniority_level,
        functional_role = u.functional_role,
        is_decision_maker = u.is_decision_maker,
        role_source = u.role_source,
        role_confidence = u.role_confidence,
        department = u.department,
        updated_at = NOW()
    FROM jsonb_to_recordset(updates) AS u(
        email_address TEXT,
        client_id UUID,
        job_title TEXT,
        seniority_level TEXT,
        functional_role TEXT,
        is_decision_maker BOOLEAN,
        role_source TEXT,
        role_confidence NUMERIC,
        department TEXT
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

COMMENT ON FUNCTION batch_update_contact_roles(JSONB)
IS 'Batch update contact role classifications from extraction pipeline';

-- =========================================================================
-- PART 3: Batch Update Function for Contact Company Assignments
-- =========================================================================
-- Updates customer_company_id for multiple contacts in one operation

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
    -- Update contact company assignments from JSONB array
    UPDATE customer_contacts c
    SET
        customer_company_id = u.customer_company_id::UUID,
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

COMMENT ON FUNCTION batch_update_contact_companies(JSONB)
IS 'Batch update contact company assignments from extraction pipeline';

-- =========================================================================
-- PART 4: Grant Permissions
-- =========================================================================

GRANT EXECUTE ON FUNCTION batch_update_contact_roles(JSONB) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION batch_update_contact_companies(JSONB) TO anon, authenticated;

-- =========================================================================
-- PART 5: Verification
-- =========================================================================

-- Test the batch update functions
DO $$
DECLARE
    test_updates JSONB;
    result RECORD;
BEGIN
    -- Verify unique constraint
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'customer_contacts_client_email_unique'
    ) THEN
        RAISE NOTICE '✅ Unique constraint verified';
    ELSE
        RAISE EXCEPTION '❌ Unique constraint not found!';
    END IF;

    -- Verify batch update functions
    IF EXISTS (
        SELECT 1 FROM pg_proc
        WHERE proname = 'batch_update_contact_roles'
    ) THEN
        RAISE NOTICE '✅ batch_update_contact_roles function created';
    ELSE
        RAISE EXCEPTION '❌ batch_update_contact_roles function not found!';
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_proc
        WHERE proname = 'batch_update_contact_companies'
    ) THEN
        RAISE NOTICE '✅ batch_update_contact_companies function created';
    ELSE
        RAISE EXCEPTION '❌ batch_update_contact_companies function not found!';
    END IF;

    RAISE NOTICE '✅ Migration 003 completed successfully';
END $$;

-- =========================================================================
-- Usage Examples
-- =========================================================================

-- Example 1: Batch update contact roles
-- SELECT * FROM batch_update_contact_roles('[
--   {
--     "email_address": "john@example.com",
--     "client_id": "uuid-here",
--     "job_title": "Senior Software Engineer",
--     "seniority_level": "senior",
--     "functional_role": "engineering",
--     "is_decision_maker": false,
--     "role_source": "signature",
--     "role_confidence": 0.85,
--     "department": "Engineering"
--   }
-- ]'::JSONB);

-- Example 2: Batch update contact company assignments
-- SELECT * FROM batch_update_contact_companies('[
--   {
--     "email_address": "john@example.com",
--     "client_id": "uuid-here",
--     "customer_company_id": "company-uuid-here",
--     "first_name": "John",
--     "last_name": "Doe",
--     "full_name": "John Doe",
--     "contact_type": "person"
--   }
-- ]'::JSONB);

-- =========================================================================
-- Rollback Script (if needed)
-- =========================================================================

-- To rollback this migration:
-- ALTER TABLE customer_contacts DROP CONSTRAINT IF EXISTS customer_contacts_client_email_unique;
-- DROP FUNCTION IF EXISTS batch_update_contact_roles(JSONB);
-- DROP FUNCTION IF EXISTS batch_update_contact_companies(JSONB);
-- DROP INDEX IF EXISTS idx_customer_contacts_client_email;

-- =========================================================================
-- END OF MIGRATION 003
-- =========================================================================
