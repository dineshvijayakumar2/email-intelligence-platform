-- Migration 013: Add mailbox_id to outlook_rules + gmail_filters tables
-- Also adds missing updated_at to gmail_filters for production catch-up.
-- This allows tracking which mailbox each rule/filter belongs to,
-- supporting users with multiple mailboxes.

-- =========================================================================
-- gmail_filters: add updated_at (production catch-up) + mailbox_id
-- =========================================================================

ALTER TABLE gmail_filters
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

ALTER TABLE gmail_filters
    ADD COLUMN IF NOT EXISTS mailbox_id UUID;

-- Backfill gmail_filters mailbox_id
UPDATE gmail_filters f
SET mailbox_id = m.id
FROM mailboxes m
WHERE f.mailbox_id IS NULL
  AND (
    m.user_id::text = f.user_id
    OR m.connection_config->>'gmail_user_id' = f.user_id
  );

CREATE INDEX IF NOT EXISTS idx_gmail_filters_mailbox ON gmail_filters(mailbox_id)
    WHERE mailbox_id IS NOT NULL;

-- =========================================================================
-- outlook_rules: add mailbox_id
-- =========================================================================

ALTER TABLE outlook_rules
    ADD COLUMN IF NOT EXISTS mailbox_id UUID;

-- Backfill outlook_rules mailbox_id
UPDATE outlook_rules r
SET mailbox_id = m.id
FROM mailboxes m
WHERE r.mailbox_id IS NULL
  AND (
    m.user_id::text = r.user_id
    OR m.connection_config->>'outlook_user_id' = r.user_id
  );

CREATE INDEX IF NOT EXISTS idx_outlook_rules_mailbox ON outlook_rules(mailbox_id)
    WHERE mailbox_id IS NOT NULL;
