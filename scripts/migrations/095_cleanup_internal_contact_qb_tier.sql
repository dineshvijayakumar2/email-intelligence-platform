-- ============================================================================
-- Migration 095: Clean up incorrectly propagated QB tier on internal/shared contacts
-- ============================================================================
--
-- Bug: Pass 3 of batch_propagate_qb_data_to_contacts was copying the client's
-- own QB customer tier (e.g. "Level 4 Enterprise") to internal employees and
-- shared addresses (accounts@, hello@, noreply@, etc.).
--
-- This migration:
-- 1. NULLs out qb_tier/qb_customer_type/qb_total_revenue on internal contacts
-- 2. NULLs out same fields on shared/automated/mailing_list contacts
-- 3. Sets contact_type = 'internal' for contacts at internal domains not yet tagged
-- 4. Sets contact_type = 'shared' for known shared-address patterns not yet tagged
-- ============================================================================

-- Step 1: Tag contacts at internal domains as 'internal' if not already set
UPDATE customer_contacts cc
SET contact_type = 'internal'
FROM internal_domains id
WHERE SPLIT_PART(cc.email_address, '@', 2) = id.domain
  AND cc.client_id = id.client_id
  AND COALESCE(cc.contact_type, 'person') = 'person';

-- Step 2: Tag known shared-address patterns
UPDATE customer_contacts
SET contact_type = 'shared'
WHERE COALESCE(contact_type, 'person') = 'person'
  AND (
    email_address ~* '^(info|contact|hello|sales|support|help|admin|office|team|service)@'
    OR email_address ~* '^(inquiries|feedback|billing|careers|jobs|hr|press|media|marketing)@'
    OR email_address ~* '^(webmaster|postmaster|accounts|noreply|no-reply|no\.reply)@'
    OR email_address ~* '^(donotreply|do-not-reply|form-submission|notifications?)@'
    OR email_address ~* '^(alerts?|mailer-daemon|bounce|receipts?|orders?|invoices?)@'
    OR email_address ~* '^(enquiry|enquiries)@'
  );

-- Step 3: Clear incorrectly propagated QB data from internal contacts
UPDATE customer_contacts cc
SET qb_tier          = NULL,
    qb_customer_type = NULL,
    qb_total_revenue = NULL,
    qb_linked_at     = NULL
FROM internal_domains id
WHERE SPLIT_PART(cc.email_address, '@', 2) = id.domain
  AND cc.client_id = id.client_id
  AND cc.qb_tier IS NOT NULL;

-- Step 4: Clear incorrectly propagated QB data from shared/automated/mailing_list contacts
UPDATE customer_contacts
SET qb_tier          = NULL,
    qb_customer_type = NULL,
    qb_total_revenue = NULL,
    qb_linked_at     = NULL
WHERE contact_type IN ('shared', 'automated', 'mailing_list')
  AND qb_tier IS NOT NULL;
