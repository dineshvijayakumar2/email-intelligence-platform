-- 045: Backfill orphan contacts — link to companies by email domain
-- Run AFTER deploying code changes (044 + pipeline reorder + orphan linking)
-- This fixes existing data; the pipeline fixes prevent future orphans.

-- Step 1: Backfill orphan contacts by matching email domain to company email_domains
-- Excludes free email providers to prevent bulk-linking unrelated contacts
UPDATE customer_contacts ct
SET
    customer_company_id = dm.company_id,
    updated_at = NOW()
FROM (
    SELECT DISTINCT ON (ct2.id)
        ct2.id AS contact_id,
        cc.id AS company_id
    FROM customer_contacts ct2
    CROSS JOIN LATERAL (
        SELECT split_part(ct2.email_address, '@', 2) AS domain
    ) d
    JOIN customer_companies cc ON cc.client_id = ct2.client_id
    CROSS JOIN LATERAL jsonb_array_elements_text(cc.email_domains) AS ed(domain_val)
    WHERE ct2.customer_company_id IS NULL
      AND ct2.email_address LIKE '%@%'
      AND lower(ed.domain_val) = lower(d.domain)
      AND lower(d.domain) NOT IN (
          SELECT lower(domain) FROM free_email_providers
      )
) dm
WHERE ct.id = dm.contact_id;

-- Step 2: Report results
-- Run this SELECT after the UPDATE to see the improvement:
-- SELECT
--     COUNT(*) AS total_contacts,
--     COUNT(customer_company_id) AS with_company,
--     ROUND(COUNT(customer_company_id)::numeric / COUNT(*) * 100, 1) AS link_pct
-- FROM customer_contacts;
