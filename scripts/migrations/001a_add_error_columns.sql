-- Migration: 001a_add_error_columns.sql
-- Description: Add error tracking columns (Part 1 of 3 - fast column additions)
-- Date: 2026-01-20
-- NOTE: Run this first, then 001b, then 001c
-- Railway-optimized: Split to avoid statement timeout

-- =========================================================================
-- 1. Add error tracking columns to emails table
-- These are fast operations (just metadata changes)
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
