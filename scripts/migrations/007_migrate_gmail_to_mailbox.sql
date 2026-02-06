-- Migration: Move Gmail tokens from user_integrations to mailboxes.connection_config
-- This enables per-mailbox Gmail connections instead of one-per-user
-- Run this BEFORE deploying the new backend code

-- Step 1: Migrate existing Gmail tokens to mailboxes that have gmail_sync_enabled
-- This copies tokens from user_integrations to the mailbox's connection_config
UPDATE mailboxes m
SET connection_config = COALESCE(m.connection_config, '{}'::jsonb) || jsonb_build_object(
    'gmail_access_token', ui.access_token,
    'gmail_refresh_token', ui.refresh_token,
    'gmail_token_expires_at', ui.token_expires_at,
    'gmail_last_sync_at', ui.last_sync_at,
    'gmail_last_history_id', ui.last_history_id,
    'gmail_sync_status', COALESCE(ui.sync_status, 'idle'),
    'gmail_sync_error', ui.sync_error,
    'gmail_email_count', COALESCE(ui.email_count, 0)
)
FROM user_integrations ui
WHERE ui.provider = 'gmail'
AND ui.user_id = m.connection_config->>'gmail_user_id'
AND m.connection_config->>'gmail_sync_enabled' = 'true'
AND m.connection_config->>'gmail_access_token' IS NULL;  -- Only if not already migrated

-- Step 2: Verify migration worked
SELECT
    m.id as mailbox_id,
    m.name as mailbox_name,
    m.connection_config->>'gmail_email' as gmail_email,
    m.connection_config->>'gmail_sync_enabled' as sync_enabled,
    m.connection_config->>'gmail_access_token' IS NOT NULL as has_token,
    m.connection_config->>'gmail_sync_status' as sync_status
FROM mailboxes m
WHERE m.connection_config->>'gmail_sync_enabled' = 'true';

-- Note: After verifying migration, you can optionally clean up user_integrations
-- But keep the records for now in case of rollback
-- DELETE FROM user_integrations WHERE provider = 'gmail';
