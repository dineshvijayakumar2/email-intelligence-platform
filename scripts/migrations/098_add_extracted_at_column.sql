-- Migration 098: Add extracted_at column to emails table
-- Tracks when each email was last processed by the extraction pipeline.
-- Enables true incremental extraction: only emails with extracted_at IS NULL
-- are processed in incremental mode, reducing scope from ~270K to ~50/day.

ALTER TABLE emails ADD COLUMN IF NOT EXISTS extracted_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_emails_extracted_at_null
ON emails (mailbox_id, id) WHERE extracted_at IS NULL;
