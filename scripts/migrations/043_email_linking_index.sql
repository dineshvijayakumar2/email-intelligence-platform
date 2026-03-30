-- 043: Add composite index for email linking query performance
-- The email linker queries: WHERE mailbox_id = ? AND customer_contact_id IS NULL
-- Without this index, Supabase hits statement_timeout on large mailboxes (100K+ emails)

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_emails_mailbox_unlinked
ON emails (mailbox_id, id)
WHERE customer_contact_id IS NULL;

-- Also index for company-only linked emails (contact NULL but company set)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_emails_mailbox_company_unlinked
ON emails (mailbox_id, id)
WHERE customer_company_id IS NULL AND customer_contact_id IS NULL;
