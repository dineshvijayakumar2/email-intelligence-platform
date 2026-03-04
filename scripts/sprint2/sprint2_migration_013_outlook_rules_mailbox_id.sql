-- Migration 013: Add mailbox_id to outlook_rules table
-- This allows tracking which mailbox each rule belongs to,
-- supporting users with multiple mailboxes.

-- Add mailbox_id column (nullable for backward compat with existing rows)
ALTER TABLE outlook_rules
    ADD COLUMN IF NOT EXISTS mailbox_id UUID;

-- Backfill: Try to resolve mailbox_id from user_id where possible
-- (user_id in outlook_rules maps to mailboxes.user_id or connection_config->outlook_user_id)
UPDATE outlook_rules r
SET mailbox_id = m.id
FROM mailboxes m
WHERE r.mailbox_id IS NULL
  AND (
    m.user_id::text = r.user_id
    OR m.connection_config->>'outlook_user_id' = r.user_id
  );

-- Index for mailbox_id lookups
CREATE INDEX IF NOT EXISTS idx_outlook_rules_mailbox ON outlook_rules(mailbox_id)
    WHERE mailbox_id IS NOT NULL;

-- Drop old unique constraint and create new one that includes mailbox_id
-- (keeping user_id,rule_id as fallback for rows without mailbox_id)
-- Note: We keep the existing UNIQUE(user_id, rule_id) since mailbox_id is nullable.
-- New records will always have mailbox_id set.
