-- Migration: Add job_errors table for comprehensive error logging
-- Stage 2: Error Tracking Enhancement
-- Date: January 21, 2026

-- =========================================================================
-- Job Errors Table (Comprehensive Error Logging)
-- =========================================================================

-- Job errors table for detailed error tracking
-- Stores ALL errors (download, extraction, processing, categorization) in one place
CREATE TABLE IF NOT EXISTS job_errors (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  job_id UUID NOT NULL REFERENCES processing_jobs(id) ON DELETE CASCADE,
  mailbox_id UUID REFERENCES mailboxes(id) ON DELETE SET NULL,

  -- Error classification
  error_phase TEXT NOT NULL,  -- download, extraction, normalization, tagging, database, categorization
  error_type TEXT NOT NULL,   -- encoding_error, parse_error, network_error, timeout_error, auth_error, etc.
  error_severity TEXT NOT NULL DEFAULT 'error',  -- warning, error, critical

  -- Error details
  error_message TEXT NOT NULL,
  error_stack TEXT,           -- Full stack trace (truncated to 4000 chars)

  -- Context (what was being processed when error occurred)
  context_type TEXT,          -- file, chunk, email, batch
  context_id TEXT,            -- file_id, chunk_index, message_id, batch_number
  context_details JSONB,      -- Additional context: {file_name, chunk_start, chunk_end, email_subject, etc.}

  -- Retry tracking
  is_retryable BOOLEAN DEFAULT TRUE,
  retry_count INTEGER DEFAULT 0,
  max_retries INTEGER DEFAULT 3,
  last_retry_at TIMESTAMPTZ,
  resolved_at TIMESTAMPTZ,    -- When error was resolved (successful retry or manual resolution)
  resolution_type TEXT,       -- auto_retry, manual_skip, manual_fix

  -- Timestamps
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for job_errors table
CREATE INDEX IF NOT EXISTS idx_job_errors_job_id ON job_errors(job_id);
CREATE INDEX IF NOT EXISTS idx_job_errors_mailbox_id ON job_errors(mailbox_id);
CREATE INDEX IF NOT EXISTS idx_job_errors_phase ON job_errors(error_phase);
CREATE INDEX IF NOT EXISTS idx_job_errors_type ON job_errors(error_type);
CREATE INDEX IF NOT EXISTS idx_job_errors_severity ON job_errors(error_severity);
CREATE INDEX IF NOT EXISTS idx_job_errors_created ON job_errors(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_job_errors_unresolved ON job_errors(job_id, resolved_at) WHERE resolved_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_job_errors_retryable ON job_errors(job_id, is_retryable) WHERE is_retryable = TRUE AND resolved_at IS NULL;

-- Trigger to update updated_at (reuse existing function)
CREATE TRIGGER update_job_errors_updated_at BEFORE UPDATE
    ON job_errors FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Grant permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE job_errors TO anon, authenticated;

-- Comments
COMMENT ON TABLE job_errors IS 'Comprehensive error logging for all processing job errors';
COMMENT ON COLUMN job_errors.error_phase IS 'Processing phase: download, extraction, normalization, tagging, database, categorization';
COMMENT ON COLUMN job_errors.error_type IS 'Error classification: encoding_error, parse_error, network_error, timeout_error, auth_error, connection_error, duplicate_error, permission_error, memory_error, validation_error, other_error';
COMMENT ON COLUMN job_errors.context_type IS 'What was being processed: file, chunk, email, batch';
COMMENT ON COLUMN job_errors.context_details IS 'JSON with context-specific details like file_name, chunk_index, email_subject';

-- Function to get error summary for a job (from job_errors table)
CREATE OR REPLACE FUNCTION get_job_errors_summary(p_job_id UUID)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    result JSONB;
BEGIN
    SELECT jsonb_build_object(
        'total_errors', COUNT(*),
        'unresolved_errors', COUNT(*) FILTER (WHERE resolved_at IS NULL),
        'retryable_errors', COUNT(*) FILTER (WHERE is_retryable = TRUE AND resolved_at IS NULL),
        'by_phase', (
            SELECT COALESCE(jsonb_object_agg(phase, cnt), '{}'::jsonb)
            FROM (
                SELECT error_phase as phase, COUNT(*) as cnt
                FROM job_errors
                WHERE job_id = p_job_id
                GROUP BY error_phase
            ) phase_counts
        ),
        'by_type', (
            SELECT COALESCE(jsonb_object_agg(etype, cnt), '{}'::jsonb)
            FROM (
                SELECT error_type as etype, COUNT(*) as cnt
                FROM job_errors
                WHERE job_id = p_job_id
                GROUP BY error_type
            ) type_counts
        ),
        'by_severity', (
            SELECT COALESCE(jsonb_object_agg(sev, cnt), '{}'::jsonb)
            FROM (
                SELECT error_severity as sev, COUNT(*) as cnt
                FROM job_errors
                WHERE job_id = p_job_id
                GROUP BY error_severity
            ) severity_counts
        ),
        'recent_errors', (
            SELECT COALESCE(jsonb_agg(err), '[]'::jsonb)
            FROM (
                SELECT jsonb_build_object(
                    'id', id,
                    'phase', error_phase,
                    'type', error_type,
                    'severity', error_severity,
                    'message', LEFT(error_message, 200),
                    'context_type', context_type,
                    'context_id', context_id,
                    'created_at', created_at
                ) as err
                FROM job_errors
                WHERE job_id = p_job_id
                ORDER BY created_at DESC
                LIMIT 10
            ) recent
        )
    ) INTO result;

    RETURN result;
END;
$$;

GRANT EXECUTE ON FUNCTION get_job_errors_summary(UUID) TO anon, authenticated;
COMMENT ON FUNCTION get_job_errors_summary(UUID) IS 'Returns comprehensive error summary for a job from job_errors table';

-- Function to get paginated errors for a job
CREATE OR REPLACE FUNCTION get_job_errors_paginated(
    p_job_id UUID,
    p_phase TEXT DEFAULT NULL,
    p_type TEXT DEFAULT NULL,
    p_unresolved_only BOOLEAN DEFAULT FALSE,
    p_limit INTEGER DEFAULT 50,
    p_offset INTEGER DEFAULT 0
)
RETURNS TABLE (
    id UUID,
    error_phase TEXT,
    error_type TEXT,
    error_severity TEXT,
    error_message TEXT,
    error_stack TEXT,
    context_type TEXT,
    context_id TEXT,
    context_details JSONB,
    is_retryable BOOLEAN,
    retry_count INTEGER,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        je.id,
        je.error_phase,
        je.error_type,
        je.error_severity,
        je.error_message,
        je.error_stack,
        je.context_type,
        je.context_id,
        je.context_details,
        je.is_retryable,
        je.retry_count,
        je.resolved_at,
        je.created_at
    FROM job_errors je
    WHERE je.job_id = p_job_id
      AND (p_phase IS NULL OR je.error_phase = p_phase)
      AND (p_type IS NULL OR je.error_type = p_type)
      AND (NOT p_unresolved_only OR je.resolved_at IS NULL)
    ORDER BY je.created_at DESC
    LIMIT p_limit
    OFFSET p_offset;
$$;

GRANT EXECUTE ON FUNCTION get_job_errors_paginated(UUID, TEXT, TEXT, BOOLEAN, INTEGER, INTEGER) TO anon, authenticated;
COMMENT ON FUNCTION get_job_errors_paginated(UUID, TEXT, TEXT, BOOLEAN, INTEGER, INTEGER) IS 'Returns paginated errors for a job with optional filters';

-- Update statistics
ANALYZE job_errors;
