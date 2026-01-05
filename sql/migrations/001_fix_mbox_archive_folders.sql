-- Migration: Fix "MBOX Archive" folder leak and normalize folder names
-- Issue: 267 emails ended up with folder_path = "MBOX Archive" (generic placeholder)
-- Also fixes case inconsistency: INBOX → Inbox
--
-- Run this in Supabase SQL Editor after deploying normalizer.py fixes

-- Step 1: Fix "MBOX Archive" folders by inferring correct folder
-- For outbound emails → Sent
-- For inbound emails → Inbox (default)
-- For spam emails (if we can detect) → Spam

UPDATE emails
SET folder_path = CASE
    WHEN is_outbound = true THEN 'Sent'
    WHEN is_outbound = false THEN 'Inbox'
    ELSE 'Inbox'
END
WHERE folder_path = 'MBOX Archive';

-- Step 2: Normalize case inconsistency: INBOX → Inbox
UPDATE emails
SET folder_path = 'Inbox'
WHERE folder_path = 'INBOX';

-- Step 3: Normalize other common folder name variations
UPDATE emails
SET folder_path = 'Archive'
WHERE folder_path IN ('archive', 'Archived', 'archived', 'All Mail');

UPDATE emails
SET folder_path = 'Sent'
WHERE folder_path IN ('sent', 'SENT', 'Sent Items', 'Sent Mail', 'Outbox');

UPDATE emails
SET folder_path = 'Spam'
WHERE folder_path IN ('spam', 'SPAM', 'Junk', 'junk', 'Junk Email');

UPDATE emails
SET folder_path = 'Trash'
WHERE folder_path IN ('trash', 'TRASH', 'Deleted', 'Deleted Items');

UPDATE emails
SET folder_path = 'Drafts'
WHERE folder_path IN ('draft', 'DRAFT', 'Drafts');

-- Step 4: Capitalize first letter of other folders (for consistency)
-- This handles folders like "muted" → "Muted", "important" → "Important"
UPDATE emails
SET folder_path = INITCAP(folder_path)
WHERE folder_path NOT IN ('Inbox', 'Sent', 'Archive', 'Spam', 'Trash', 'Drafts')
  AND folder_path = LOWER(folder_path);

-- Step 5: Update folders table to reflect changes
-- Delete old folder entries
DELETE FROM folders WHERE folder_path IN ('MBOX Archive', 'INBOX', 'archive', 'sent', 'spam');

-- Recalculate folder counts
INSERT INTO folders (mailbox_id, folder_path, folder_type, message_count, created_at)
SELECT
    e.mailbox_id,
    e.folder_path,
    CASE
        WHEN LOWER(e.folder_path) IN ('inbox', 'mail') THEN 'inbox'
        WHEN LOWER(e.folder_path) IN ('sent', 'sent items') THEN 'sent'
        WHEN LOWER(e.folder_path) IN ('spam', 'junk') THEN 'spam'
        WHEN LOWER(e.folder_path) IN ('trash', 'deleted') THEN 'trash'
        WHEN LOWER(e.folder_path) IN ('archive', 'archived') THEN 'archive'
        WHEN LOWER(e.folder_path) IN ('drafts', 'draft') THEN 'drafts'
        ELSE 'user'
    END as folder_type,
    COUNT(*) as message_count,
    NOW() as created_at
FROM emails e
GROUP BY e.mailbox_id, e.folder_path
ON CONFLICT (mailbox_id, folder_path)
DO UPDATE SET
    message_count = EXCLUDED.message_count,
    folder_type = EXCLUDED.folder_type;

-- Verify the migration
SELECT
    folder_path,
    COUNT(*) as email_count
FROM emails
GROUP BY folder_path
ORDER BY email_count DESC;
