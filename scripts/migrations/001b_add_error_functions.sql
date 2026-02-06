-- Migration: 001b_add_error_functions.sql
-- Description: Add error handling functions (Part 2 of 3)
-- Date: 2026-01-20
-- NOTE: Run after 001a, before 001c
-- Railway-optimized: Split to avoid statement timeout

-- =========================================================================
-- 1. Create function to get error summary for a job
-- =========================================================================

CREATE OR REPLACE FUNCTION get_job_error_summary(p_mailbox_id UUID)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    result JSONB;
BEGIN
    SELECT jsonb_build_object(
        'total_errors', COUNT(*) FILTER (WHERE processing_status = 'failed'),
        'total_success', COUNT(*) FILTER (WHERE processing_status = 'success'),
        'total_pending', COUNT(*) FILTER (WHERE processing_status = 'pending'),
        'total_skipped', COUNT(*) FILTER (WHERE processing_status = 'skipped'),
        'error_types', (
            SELECT COALESCE(jsonb_object_agg(error_type, error_count), '{}'::jsonb)
            FROM (
                SELECT
                    COALESCE(
                        CASE
                            WHEN processing_error LIKE '%encoding%' OR processing_error LIKE '%decode%' THEN 'encoding_error'
                            WHEN processing_error LIKE '%parse%' OR processing_error LIKE '%Parse%' THEN 'parse_error'
                            WHEN processing_error LIKE '%timeout%' OR processing_error LIKE '%Timeout%' THEN 'timeout_error'
                            WHEN processing_error LIKE '%connection%' OR processing_error LIKE '%Connection%' THEN 'connection_error'
                            WHEN processing_error LIKE '%duplicate%' OR processing_error LIKE '%Duplicate%' THEN 'duplicate_error'
                            ELSE 'other_error'
                        END,
                        'unknown'
                    ) as error_type,
                    COUNT(*) as error_count
                FROM emails
                WHERE mailbox_id = p_mailbox_id AND processing_status = 'failed'
                GROUP BY 1
            ) error_counts
        )
    ) INTO result
    FROM emails
    WHERE mailbox_id = p_mailbox_id;

    RETURN result;
END;
$$;

GRANT EXECUTE ON FUNCTION get_job_error_summary(UUID) TO anon, authenticated;
COMMENT ON FUNCTION get_job_error_summary(UUID) IS 'Returns aggregated error summary for a mailbox/job';

-- =========================================================================
-- 2. Create function to get failed emails with details
-- =========================================================================

CREATE OR REPLACE FUNCTION get_failed_emails(
    p_mailbox_id UUID,
    p_limit INTEGER DEFAULT 100,
    p_offset INTEGER DEFAULT 0
)
RETURNS TABLE (
    id UUID,
    message_id TEXT,
    subject TEXT,
    sender_email TEXT,
    sent_date TIMESTAMPTZ,
    processing_error TEXT,
    processing_attempts INTEGER,
    last_processing_attempt TIMESTAMPTZ
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        e.id,
        e.message_id,
        e.subject,
        e.sender_email,
        e.sent_date,
        e.processing_error,
        e.processing_attempts,
        e.last_processing_attempt
    FROM emails e
    WHERE e.mailbox_id = p_mailbox_id
      AND e.processing_status = 'failed'
    ORDER BY e.last_processing_attempt DESC NULLS LAST, e.sent_date DESC
    LIMIT p_limit
    OFFSET p_offset;
$$;

GRANT EXECUTE ON FUNCTION get_failed_emails(UUID, INTEGER, INTEGER) TO anon, authenticated;
COMMENT ON FUNCTION get_failed_emails(UUID, INTEGER, INTEGER) IS 'Returns paginated list of failed emails for a mailbox';

-- =========================================================================
-- 3. Create function to reset failed emails for retry
-- =========================================================================

CREATE OR REPLACE FUNCTION reset_failed_emails_for_retry(
    p_mailbox_id UUID,
    p_max_attempts INTEGER DEFAULT 3
)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    updated_count INTEGER;
BEGIN
    UPDATE emails
    SET
        processing_status = 'pending',
        processing_error = NULL
    WHERE mailbox_id = p_mailbox_id
      AND processing_status = 'failed'
      AND processing_attempts < p_max_attempts;

    GET DIAGNOSTICS updated_count = ROW_COUNT;
    RETURN updated_count;
END;
$$;

GRANT EXECUTE ON FUNCTION reset_failed_emails_for_retry(UUID, INTEGER) TO anon, authenticated;
COMMENT ON FUNCTION reset_failed_emails_for_retry(UUID, INTEGER) IS 'Resets failed emails to pending status for retry (respects max attempt limit)';
