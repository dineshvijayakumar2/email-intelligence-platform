-- Migration: 001_add_error_handling.sql
-- Description: Add error tracking columns to emails and processing_jobs tables
-- Date: 2026-01-19
-- Stage 2 Phase 1 - Prerequisite: Error Handling

-- =========================================================================
-- 1. Add error tracking columns to emails table
-- =========================================================================

-- Processing status: tracks state of each email during processing
ALTER TABLE emails ADD COLUMN IF NOT EXISTS processing_status TEXT DEFAULT 'pending';
COMMENT ON COLUMN emails.processing_status IS 'Processing state: pending, processing, success, failed, skipped';

-- Error message: stores the error details when processing fails
ALTER TABLE emails ADD COLUMN IF NOT EXISTS processing_error TEXT;
COMMENT ON COLUMN emails.processing_error IS 'Error message/details when processing_status is failed';

-- Retry tracking: number of processing attempts
ALTER TABLE emails ADD COLUMN IF NOT EXISTS processing_attempts INTEGER DEFAULT 0;
COMMENT ON COLUMN emails.processing_attempts IS 'Number of times email processing has been attempted';

-- Last attempt timestamp
ALTER TABLE emails ADD COLUMN IF NOT EXISTS last_processing_attempt TIMESTAMPTZ;
COMMENT ON COLUMN emails.last_processing_attempt IS 'Timestamp of the most recent processing attempt';

-- =========================================================================
-- 2. Add error summary to processing_jobs table
-- =========================================================================

-- Error summary: aggregated error information for the job
ALTER TABLE processing_jobs ADD COLUMN IF NOT EXISTS error_summary JSONB;
COMMENT ON COLUMN processing_jobs.error_summary IS 'Aggregated error info: {total_errors, error_types: {type: count}, sample_errors: [...]}';

-- =========================================================================
-- 3. Create indexes for efficient error queries
-- =========================================================================

-- Index for querying emails by processing status
CREATE INDEX IF NOT EXISTS idx_emails_processing_status ON emails(processing_status);

-- Composite index for querying failed emails within a mailbox
CREATE INDEX IF NOT EXISTS idx_emails_processing_status_mailbox ON emails(mailbox_id, processing_status);

-- Index for finding emails that need retry (failed + low attempt count)
CREATE INDEX IF NOT EXISTS idx_emails_failed_retry ON emails(processing_status, processing_attempts)
  WHERE processing_status = 'failed';

-- =========================================================================
-- 4. Create function to get error summary for a job
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
-- 5. Create function to get failed emails with details
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
-- 6. Create function to reset failed emails for retry
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

-- =========================================================================
-- 7. Update statistics
-- =========================================================================

ANALYZE emails;
ANALYZE processing_jobs;
