-- Migration 105: Clean up contaminated QB customer matches
-- Root cause: Pass 1 (exact name) and Pass 2 (domain root) auto-wrote matches
-- that produced massive false positives (759 companies with >1 QB customer,
-- 2,757 excess matches, $17.2M in contaminated revenue data).
--
-- Fix: Clear ALL name-based matches from qb_customers and qb_operations.
-- Email-based matches (Pass 0 via match_companies_via_unique_emails and
-- match_customers_via_contacts) will re-populate on next QB sync.
-- Name-based matches now stage to qb_match_candidates for human review.

-- 1. Clear matched_company_id on ALL qb_customers
--    (email-based matching will re-populate the correct ones on next sync)
UPDATE qb_customers
SET matched_company_id = NULL
WHERE matched_company_id IS NOT NULL;

-- 2. Clear matched_company_id on ALL qb_operations
--    (derived from qb_customers matches, will be re-derived after re-matching)
UPDATE qb_operations
SET matched_company_id = NULL
WHERE matched_company_id IS NOT NULL;

-- 3. Clear QB match metadata on customer_companies
--    (will be re-populated by email-based matching with correct data)
UPDATE customer_companies
SET qb_customer_id = NULL,
    qb_customer_code = NULL,
    qb_match_method = NULL,
    qb_matched_at = NULL
WHERE qb_match_method IS NOT NULL;

-- 4. Clear stale match candidates (will be regenerated on next sync)
DELETE FROM qb_match_candidates
WHERE reviewed = FALSE;
