-- Migration 015: Remove obsolete account_manager_id field from mailboxes
--
-- Purpose: Clean up obsolete fields after RBAC migration
-- The account_manager_id field was replaced by user_id in the new RBAC system
--
-- Date: 2026-02-03

-- ============================================
-- Step 1: Verify current state
-- ============================================

-- Check if any mailboxes still use account_manager_id (should migrate data first if needed)
SELECT 'Mailboxes with account_manager_id:' AS section, COUNT(*) AS count
FROM mailboxes
WHERE account_manager_id IS NOT NULL;

-- Check if any mailboxes use user_id
SELECT 'Mailboxes with user_id:' AS section, COUNT(*) AS count
FROM mailboxes
WHERE user_id IS NOT NULL;

-- ============================================
-- Step 2: Migrate any remaining data (if needed)
-- ============================================

-- If there are mailboxes with account_manager_id but no user_id, migrate them
-- This handles any edge cases where data wasn't migrated
UPDATE mailboxes
SET user_id = account_manager_id
WHERE account_manager_id IS NOT NULL
  AND user_id IS NULL;

-- ============================================
-- Step 3: Drop the obsolete column
-- ============================================

-- Drop the account_manager_id column
ALTER TABLE mailboxes DROP COLUMN IF EXISTS account_manager_id;

-- ============================================
-- Step 4: Verify cleanup
-- ============================================

-- Verify the column is gone
SELECT 'Verification - mailboxes columns:' AS section;
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'mailboxes'
  AND table_schema = 'public'
ORDER BY ordinal_position;

SELECT 'Migration 015 completed successfully!' AS status;