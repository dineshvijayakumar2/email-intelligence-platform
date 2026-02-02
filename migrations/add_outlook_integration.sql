-- Migration: Add Outlook LIVE Integration Support
-- Purpose: Enable Microsoft Outlook (O365 and personal accounts) integration
-- Run this in your Supabase SQL editor

-- ============================================================
-- Step 1: Update user_integrations provider constraint
-- ============================================================

-- Drop existing constraint
ALTER TABLE user_integrations
DROP CONSTRAINT IF EXISTS user_integrations_provider_check;

-- Add new constraint including 'outlook'
ALTER TABLE user_integrations
ADD CONSTRAINT user_integrations_provider_check
CHECK (provider IN ('google_drive', 'gmail', 'outlook', 'microsoft', 'dropbox'));

-- ============================================================
-- Step 2: Add Outlook-specific columns to user_integrations
-- ============================================================

-- Add delta_link column for Outlook incremental sync
-- (Microsoft Graph API equivalent of Gmail's historyId)
ALTER TABLE user_integrations
ADD COLUMN IF NOT EXISTS delta_link TEXT;

-- Add sync-related columns if they don't exist (may already exist from Gmail)
ALTER TABLE user_integrations
ADD COLUMN IF NOT EXISTS sync_status TEXT DEFAULT 'idle';

ALTER TABLE user_integrations
ADD COLUMN IF NOT EXISTS email_count INTEGER DEFAULT 0;

ALTER TABLE user_integrations
ADD COLUMN IF NOT EXISTS sync_error TEXT;

ALTER TABLE user_integrations
ADD COLUMN IF NOT EXISTS last_sync_at TIMESTAMPTZ;

ALTER TABLE user_integrations
ADD COLUMN IF NOT EXISTS last_history_id TEXT;

-- Comments for documentation
COMMENT ON COLUMN user_integrations.delta_link IS 'Microsoft Graph deltaLink for Outlook incremental sync';
COMMENT ON COLUMN user_integrations.sync_status IS 'Current sync status: idle, syncing, error';
COMMENT ON COLUMN user_integrations.email_count IS 'Total emails synced for this integration';
COMMENT ON COLUMN user_integrations.sync_error IS 'Last sync error message if any';
COMMENT ON COLUMN user_integrations.last_sync_at IS 'Timestamp of last successful sync';
COMMENT ON COLUMN user_integrations.last_history_id IS 'Gmail historyId for incremental sync';

-- ============================================================
-- Step 3: Update mailboxes type constraint to include outlook_live
-- ============================================================

-- Drop existing constraint
ALTER TABLE mailboxes
DROP CONSTRAINT IF EXISTS mailboxes_mailbox_type_check;

-- Add new constraint with outlook_live support
ALTER TABLE mailboxes
ADD CONSTRAINT mailboxes_mailbox_type_check
CHECK (mailbox_type IN ('mbox', 'pst', 'olm', 'gmail', 'outlook_live'));

COMMENT ON COLUMN mailboxes.mailbox_type IS 'Mailbox type: mbox (universal), pst (Windows Outlook), olm (Mac Outlook), gmail (Gmail LIVE), outlook_live (Outlook LIVE)';

-- ============================================================
-- Step 4: Add app_config entry for Outlook sync interval
-- ============================================================

INSERT INTO app_config (config_key, config_value, created_at, updated_at)
VALUES ('outlook_sync_interval', '15', NOW(), NOW())
ON CONFLICT (config_key) DO NOTHING;

-- ============================================================
-- Step 5: Create outlook_rules table (for imported mail rules)
-- ============================================================

CREATE TABLE IF NOT EXISTS outlook_rules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT NOT NULL,
    rule_id TEXT NOT NULL,           -- Microsoft Graph rule ID
    display_name TEXT,               -- Rule display name
    sequence INTEGER,                -- Rule priority/order
    is_enabled BOOLEAN DEFAULT TRUE,
    conditions JSONB NOT NULL DEFAULT '{}',
    actions JSONB NOT NULL DEFAULT '{}',
    exceptions JSONB DEFAULT '{}',   -- Outlook supports rule exceptions
    imported_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(user_id, rule_id)
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_outlook_rules_user ON outlook_rules(user_id);

-- Update trigger for updated_at
DROP TRIGGER IF EXISTS update_outlook_rules_updated_at ON outlook_rules;
CREATE TRIGGER update_outlook_rules_updated_at
    BEFORE UPDATE ON outlook_rules
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Grant permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE outlook_rules TO anon, authenticated;
GRANT ALL ON outlook_rules TO service_role;

COMMENT ON TABLE outlook_rules IS 'Stores imported Outlook mail rules for user reference';

-- ============================================================
-- Step 6: Document connection_config schema for mailboxes
-- ============================================================

COMMENT ON COLUMN mailboxes.connection_config IS
'JSON config for mailbox connection.

For Gmail LIVE sync:
{
  gmail_sync_enabled: boolean,
  gmail_email: string,
  gmail_access_token: string,
  gmail_refresh_token: string,
  gmail_token_expires_at: string (ISO),
  gmail_last_history_id: string,
  gmail_sync_status: "idle" | "syncing" | "error",
  gmail_sync_error: string | null,
  gmail_email_count: number
}

For Outlook LIVE sync:
{
  outlook_sync_enabled: boolean,
  outlook_email: string,
  outlook_access_token: string,
  outlook_refresh_token: string,
  outlook_token_expires_at: string (ISO),
  outlook_delta_link: string,
  outlook_sync_status: "idle" | "syncing" | "error",
  outlook_sync_error: string | null,
  outlook_email_count: number
}';

-- ============================================================
-- Verification
-- ============================================================

SELECT 'Outlook integration migration completed successfully!' AS status;
