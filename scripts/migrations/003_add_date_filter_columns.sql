-- Migration: Add date filter columns to processing_jobs table
-- Stage 2: Date Range Processing Feature
-- Date: January 20, 2026

-- Add filtered_records column to track emails excluded by date filter
ALTER TABLE processing_jobs
ADD COLUMN IF NOT EXISTS filtered_records INTEGER DEFAULT 0;

-- Add date filter parameters for audit trail
ALTER TABLE processing_jobs
ADD COLUMN IF NOT EXISTS filter_start_date TIMESTAMPTZ;

ALTER TABLE processing_jobs
ADD COLUMN IF NOT EXISTS filter_end_date TIMESTAMPTZ;

-- Add comments for documentation
COMMENT ON COLUMN processing_jobs.filtered_records IS 'Count of emails excluded by date range filter';
COMMENT ON COLUMN processing_jobs.filter_start_date IS 'Start date of the date range filter (null = no lower bound)';
COMMENT ON COLUMN processing_jobs.filter_end_date IS 'End date of the date range filter (null = no upper bound)';

-- Update statistics
ANALYZE processing_jobs;
