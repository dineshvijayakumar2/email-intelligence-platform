-- Migration 049: Add tag summary fields to qb_unique_emails
-- These are rolled up from operations via Unique Emails in QB.

ALTER TABLE qb_unique_emails
    ADD COLUMN IF NOT EXISTS embellishments_used TEXT,
    ADD COLUMN IF NOT EXISTS processes_used TEXT,
    ADD COLUMN IF NOT EXISTS capabilities_used TEXT;
