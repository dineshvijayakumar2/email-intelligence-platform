-- Migration: 001c_add_error_indexes.sql
-- Description: Add error handling indexes (Part 3 of 3)
-- Date: 2026-01-20
-- NOTE: Run after 001a and 001b
-- Railway-optimized: Regular indexes (CONCURRENTLY not supported in transactions)

-- Index for querying emails by processing status
CREATE INDEX IF NOT EXISTS idx_emails_processing_status ON emails(processing_status);

-- Composite index for querying failed emails within a mailbox
CREATE INDEX IF NOT EXISTS idx_emails_processing_status_mailbox ON emails(mailbox_id, processing_status);

-- Partial index for finding emails that need retry (more efficient, smaller index)
CREATE INDEX IF NOT EXISTS idx_emails_failed_retry ON emails(processing_status, processing_attempts)
  WHERE processing_status = 'failed';
