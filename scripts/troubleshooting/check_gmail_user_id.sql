-- Check Gmail connection for your mailbox
-- Run this in Supabase SQL Editor

-- 1. First, find your user ID
SELECT 'Your Supabase User ID:' AS info, id, email
FROM user_profiles
WHERE email = 'dinwin1989@gmail.com';

-- 2. Check mailboxes with Gmail connected
SELECT
    'Mailboxes with Gmail:' AS info,
    id,
    name,
    connection_config->'gmail_user_id' AS stored_gmail_user_id,
    connection_config->'gmail_email' AS gmail_email,
    connection_config->'gmail_sync_enabled' AS sync_enabled
FROM mailboxes
WHERE connection_config->'gmail_sync_enabled' = 'true';

-- 3. Fix mailbox: Update gmail_user_id to match your Supabase user ID
-- REPLACE 'YOUR_USER_ID_HERE' and 'YOUR_MAILBOX_ID_HERE' with actual values from queries above

-- UPDATE mailboxes
-- SET connection_config = jsonb_set(
--     connection_config,
--     '{gmail_user_id}',
--     '"YOUR_USER_ID_HERE"'
-- )
-- WHERE id = 'YOUR_MAILBOX_ID_HERE';

-- Uncomment and run the UPDATE after replacing the IDs