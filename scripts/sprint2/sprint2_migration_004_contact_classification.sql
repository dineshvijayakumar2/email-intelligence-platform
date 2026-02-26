-- =========================================================================
-- Sprint 2 Migration 004: Contact Classification (Tag Instead of Filter)
-- =========================================================================
-- Purpose: Add contact_type column to classify contacts instead of filtering
-- Run this to enable tagging of automated/shared/mailing list contacts
-- =========================================================================

-- Add contact_type column to customer_contacts
ALTER TABLE customer_contacts
ADD COLUMN IF NOT EXISTS contact_type TEXT DEFAULT 'person'
CHECK (contact_type IN ('person', 'automated', 'shared', 'mailing_list', 'internal', 'unknown'));

-- Add index for filtering by contact type
CREATE INDEX IF NOT EXISTS idx_customer_contacts_type
ON customer_contacts(contact_type);

-- Add index for filtering real people (most common query)
CREATE INDEX IF NOT EXISTS idx_customer_contacts_person
ON customer_contacts(contact_type)
WHERE contact_type = 'person';

COMMENT ON COLUMN customer_contacts.contact_type IS
'Contact classification: person (real person), automated (noreply/donotreply), shared (info/support/sales), mailing_list (newsletter), internal (own domain), unknown';

-- =========================================================================
-- Update existing contacts to classify them
-- =========================================================================

-- Classify automated contacts (noreply, no-reply, donotreply, etc.)
UPDATE customer_contacts
SET contact_type = 'automated'
WHERE contact_type = 'person'
  AND (
    email_address ILIKE '%noreply%' OR
    email_address ILIKE '%no-reply%' OR
    email_address ILIKE '%donotreply%' OR
    email_address ILIKE '%do-not-reply%' OR
    email_address ILIKE '%bounce%' OR
    email_address ILIKE '%mailer-daemon%' OR
    email_address ILIKE '%postmaster%' OR
    email_address ILIKE '%notification%' OR
    email_address ILIKE '%automated%' OR
    email_address ILIKE '%auto-%'
  );

-- Classify shared addresses (info, support, sales, etc.)
UPDATE customer_contacts
SET contact_type = 'shared'
WHERE contact_type = 'person'
  AND (
    email_address ILIKE 'info@%' OR
    email_address ILIKE 'support@%' OR
    email_address ILIKE 'sales@%' OR
    email_address ILIKE 'help@%' OR
    email_address ILIKE 'contact@%' OR
    email_address ILIKE 'hello@%' OR
    email_address ILIKE 'team@%' OR
    email_address ILIKE 'admin@%' OR
    email_address ILIKE 'service@%' OR
    email_address ILIKE 'customer%@%' OR
    email_address ILIKE 'billing@%' OR
    email_address ILIKE 'accounts@%'
  );

-- =========================================================================
-- Verification
-- =========================================================================

DO $$
DECLARE
    total_contacts INTEGER;
    person_count INTEGER;
    automated_count INTEGER;
    shared_count INTEGER;
    mailing_list_count INTEGER;
BEGIN
    -- Get counts
    SELECT COUNT(*) INTO total_contacts FROM customer_contacts;
    SELECT COUNT(*) INTO person_count FROM customer_contacts WHERE contact_type = 'person';
    SELECT COUNT(*) INTO automated_count FROM customer_contacts WHERE contact_type = 'automated';
    SELECT COUNT(*) INTO shared_count FROM customer_contacts WHERE contact_type = 'shared';
    SELECT COUNT(*) INTO mailing_list_count FROM customer_contacts WHERE contact_type = 'mailing_list';

    RAISE NOTICE '';
    RAISE NOTICE '========================================';
    RAISE NOTICE '✅ Migration 004 Complete';
    RAISE NOTICE '========================================';
    RAISE NOTICE '';
    RAISE NOTICE 'Contact Classification Results:';
    RAISE NOTICE '  Total contacts:      %', total_contacts;
    RAISE NOTICE '  Real people:         % (%.1f%%)', person_count, (person_count::numeric / NULLIF(total_contacts, 0) * 100);
    RAISE NOTICE '  Automated:           % (%.1f%%)', automated_count, (automated_count::numeric / NULLIF(total_contacts, 0) * 100);
    RAISE NOTICE '  Shared addresses:    % (%.1f%%)', shared_count, (shared_count::numeric / NULLIF(total_contacts, 0) * 100);
    RAISE NOTICE '  Mailing lists:       % (%.1f%%)', mailing_list_count, (mailing_list_count::numeric / NULLIF(total_contacts, 0) * 100);
    RAISE NOTICE '';

    IF person_count > 0 THEN
        RAISE NOTICE '✅ Contact classification successful';
    ELSE
        RAISE WARNING '⚠️  No person contacts found - all contacts classified as automated/shared';
    END IF;
END $$;

-- =========================================================================
-- Sample Queries for Analytics
-- =========================================================================

-- Example 1: Get only real people (for CRM)
-- SELECT * FROM customer_contacts WHERE contact_type = 'person';

-- Example 2: Get contact breakdown by type
-- SELECT
--     contact_type,
--     COUNT(*) as count,
--     ROUND(COUNT(*)::numeric / (SELECT COUNT(*) FROM customer_contacts) * 100, 1) as percentage
-- FROM customer_contacts
-- GROUP BY contact_type
-- ORDER BY count DESC;

-- Example 3: Get emails from real people only
-- SELECT e.*
-- FROM emails e
-- JOIN customer_contacts c ON e.customer_contact_id = c.id
-- WHERE c.contact_type = 'person';

-- Example 4: Exclude automated contacts from analytics
-- SELECT customer_company_id, COUNT(*) as contact_count
-- FROM customer_contacts
-- WHERE contact_type NOT IN ('automated', 'mailing_list')
-- GROUP BY customer_company_id;

-- =========================================================================
-- Rollback Script (if needed)
-- =========================================================================

-- To rollback this migration:
-- ALTER TABLE customer_contacts DROP COLUMN IF EXISTS contact_type;
-- DROP INDEX IF EXISTS idx_customer_contacts_type;
-- DROP INDEX IF EXISTS idx_customer_contacts_person;

-- =========================================================================
-- END OF MIGRATION 004
-- =========================================================================
