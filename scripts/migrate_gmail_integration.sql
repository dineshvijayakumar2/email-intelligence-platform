-- Gmail LIVE Integration Migration
-- Run this in Supabase SQL Editor to add Gmail sync support
-- Stage 2 Epic 1.3 (S1-07 to S1-10)

-- ============================================================
-- Step 1: Update provider constraint to include 'gmail'
-- ============================================================

-- First, drop the existing constraint if it exists
ALTER TABLE user_integrations
DROP CONSTRAINT IF EXISTS user_integrations_provider_check;

-- Add updated constraint with gmail
ALTER TABLE user_integrations
ADD CONSTRAINT user_integrations_provider_check
CHECK (provider IN ('google_drive', 'gmail', 'microsoft', 'dropbox'));

-- ============================================================
-- Step 2: Add sync tracking columns to user_integrations
-- ============================================================

-- Add last_sync_at column
ALTER TABLE user_integrations
ADD COLUMN IF NOT EXISTS last_sync_at TIMESTAMPTZ;

-- Add last_history_id for Gmail incremental sync
ALTER TABLE user_integrations
ADD COLUMN IF NOT EXISTS last_history_id TEXT;

-- Add sync_status column with check constraint
ALTER TABLE user_integrations
ADD COLUMN IF NOT EXISTS sync_status TEXT DEFAULT 'idle';

-- Drop existing constraint if any
ALTER TABLE user_integrations
DROP CONSTRAINT IF EXISTS user_integrations_sync_status_check;

-- Add sync_status check constraint
ALTER TABLE user_integrations
ADD CONSTRAINT user_integrations_sync_status_check
CHECK (sync_status IN ('idle', 'syncing', 'error'));

-- Add sync_error column for error messages
ALTER TABLE user_integrations
ADD COLUMN IF NOT EXISTS sync_error TEXT;

-- Add email_count column for tracking synced emails
ALTER TABLE user_integrations
ADD COLUMN IF NOT EXISTS email_count INTEGER DEFAULT 0;

-- ============================================================
-- Step 3: Update mailbox_type constraint to include gmail
-- ============================================================

-- Drop existing constraint
ALTER TABLE mailboxes
DROP CONSTRAINT IF EXISTS mailboxes_mailbox_type_check;

-- Add updated constraint with gmail and outlook_live types
ALTER TABLE mailboxes
ADD CONSTRAINT mailboxes_mailbox_type_check
CHECK (mailbox_type IN ('mbox', 'pst', 'olm', 'eml', 'gmail', 'outlook_live'));

-- ============================================================
-- Step 4: Create gmail_filters table for S1-08
-- ============================================================

CREATE TABLE IF NOT EXISTS gmail_filters (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT NOT NULL,
    filter_id TEXT NOT NULL,
    criteria JSONB NOT NULL DEFAULT '{}',
    action JSONB NOT NULL DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE,
    imported_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, filter_id)
);

-- Create index for faster user lookups
CREATE INDEX IF NOT EXISTS idx_gmail_filters_user ON gmail_filters(user_id);

-- Grant permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gmail_filters TO anon, authenticated;

-- ============================================================
-- Verification: Check the changes
-- ============================================================

-- You can run these SELECT statements to verify:
-- SELECT column_name, data_type, column_default
-- FROM information_schema.columns
-- WHERE table_name = 'user_integrations';

-- SELECT constraint_name, check_clause
-- FROM information_schema.check_constraints
-- WHERE constraint_name LIKE '%user_integrations%';

SELECT 'Gmail integration migration completed successfully!' as status;
