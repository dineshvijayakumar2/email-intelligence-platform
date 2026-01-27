-- Performance Optimization: Dashboard Queries
-- Run this in Supabase SQL Editor to optimize dashboard and mailbox loading

-- 1. Create RPC function for email counts by mailbox (eliminates N+1 queries)
CREATE OR REPLACE FUNCTION get_email_counts_by_mailbox()
RETURNS TABLE (mailbox_id UUID, email_count BIGINT)
LANGUAGE sql
STABLE
AS $$
    SELECT
        e.mailbox_id,
        COUNT(*)::BIGINT as email_count
    FROM emails e
    WHERE e.mailbox_id IS NOT NULL
    GROUP BY e.mailbox_id;
$$;

-- Grant execute to public (anon and authenticated)
GRANT EXECUTE ON FUNCTION get_email_counts_by_mailbox() TO anon, authenticated;

-- 2. Create RPC function for dashboard stats (single query instead of 4)
CREATE OR REPLACE FUNCTION get_dashboard_stats()
RETURNS TABLE (
    total_emails BIGINT,
    total_mailboxes BIGINT,
    today_emails BIGINT,
    processing_jobs BIGINT
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        (SELECT COUNT(*)::BIGINT FROM emails) as total_emails,
        (SELECT COUNT(*)::BIGINT FROM mailboxes) as total_mailboxes,
        (SELECT COUNT(*)::BIGINT FROM emails WHERE sent_date::date = NOW()::date) as today_emails,
        (SELECT COUNT(*)::BIGINT FROM processing_jobs WHERE status IN ('pending', 'running', 'downloading')) as processing_jobs;
$$;

-- Grant execute to public
GRANT EXECUTE ON FUNCTION get_dashboard_stats() TO anon, authenticated;

-- 3. Create optimized index for today's email count if not exists
CREATE INDEX IF NOT EXISTS idx_emails_sent_date_only ON emails(sent_date DESC);

-- 4. Add index hint for email count aggregation
CREATE INDEX IF NOT EXISTS idx_emails_mailbox_count ON emails(mailbox_id)
WHERE mailbox_id IS NOT NULL;

-- 5. Analyze tables to update statistics for query optimizer
-- NOTE: ANALYZE on large tables (emails with 100k+ rows) can timeout.
-- PostgreSQL auto-vacuum handles statistics updates automatically.
-- Only running ANALYZE on smaller tables here.
-- ANALYZE mailboxes;  -- Skip if large
ANALYZE processing_jobs;

-- Verify functions work
SELECT * FROM get_dashboard_stats();
SELECT * FROM get_email_counts_by_mailbox();
