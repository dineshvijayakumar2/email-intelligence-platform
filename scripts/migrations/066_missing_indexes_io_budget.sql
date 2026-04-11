-- ============================================================================
-- Migration 066: Missing indexes identified from pg_stat_statements analysis
-- ============================================================================
-- The top IO burners were:
--   1. canonical thread resolution scanning ALL emails (fixed in Python)
--   2. qb_quotes lookups by customer_id with no index (9.3K calls, 3.4h)
--   3. qb_jobs lookups by customer_id with no index (4.7K calls, 3h)
--   4. emails.canonical_thread_id IS NULL filter (thread resolver)
-- ============================================================================

-- 1. qb_quotes: lookups by customer_id (used by order-history + revenue sync)
CREATE INDEX IF NOT EXISTS idx_qb_quotes_client_customer
    ON qb_quotes(client_id, qb_customer_id);

-- 2. qb_jobs: same pattern as quotes
CREATE INDEX IF NOT EXISTS idx_qb_jobs_client_customer
    ON qb_jobs(client_id, qb_customer_id);

-- 3. emails: canonical thread resolver filters on (mailbox_id, canonical_thread_id IS NULL)
--    Partial index covers only unresolved emails — shrinks as resolution progresses
CREATE INDEX IF NOT EXISTS idx_emails_unresolved_threads
    ON emails(mailbox_id, sent_date)
    WHERE canonical_thread_id IS NULL;

-- 4. emails: pre-seed query filters (mailbox_id, canonical_thread_id IS NOT NULL, internet_message_id IS NOT NULL)
CREATE INDEX IF NOT EXISTS idx_emails_resolved_msgid
    ON emails(mailbox_id)
    WHERE canonical_thread_id IS NOT NULL AND internet_message_id IS NOT NULL;
