-- Migration 019: Threading Overhaul
-- Adds first-class threading columns, provider thread IDs, subject normalization,
-- and thread confidence scoring for robust multi-source thread grouping.
--
-- Run AFTER migration 018 (audit_log).
--
-- STEP 1: Run this file (schema + indexes only)
-- STEP 2: Run sprint3_migration_019b_backfill.sql (batched backfill, safe for large tables)

-- ============================================================================
-- 1. New columns on emails table
-- ============================================================================

ALTER TABLE emails ADD COLUMN IF NOT EXISTS internet_message_id TEXT;
ALTER TABLE emails ADD COLUMN IF NOT EXISTS in_reply_to TEXT;
ALTER TABLE emails ADD COLUMN IF NOT EXISTS references_header TEXT;
ALTER TABLE emails ADD COLUMN IF NOT EXISTS provider_thread_id TEXT;
ALTER TABLE emails ADD COLUMN IF NOT EXISTS subject_normalized TEXT;
ALTER TABLE emails ADD COLUMN IF NOT EXISTS thread_confidence REAL DEFAULT 1.0;

-- ============================================================================
-- 2. Indexes for threading queries
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_emails_provider_thread_id
  ON emails(provider_thread_id) WHERE provider_thread_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_emails_subject_normalized
  ON emails(subject_normalized) WHERE subject_normalized IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_emails_in_reply_to
  ON emails(in_reply_to) WHERE in_reply_to IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_emails_internet_message_id
  ON emails(internet_message_id) WHERE internet_message_id IS NOT NULL;

-- ============================================================================
-- Done. Now run 019b for backfill.
-- ============================================================================
