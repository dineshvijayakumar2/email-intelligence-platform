-- Fix RBAC Assignments for dinwin1989@gmail.com
-- This script identifies and fixes incorrect client assignments

-- User ID for dinwin1989@gmail.com
-- b52a7a74-98d0-4696-92c1-ef47d4c53627

-- ============================================
-- Step 1: Check Current State
-- ============================================

-- Show user profile
SELECT 'User Profile:' AS section;
SELECT id, email, name, roles, is_active
FROM user_profiles
WHERE id = 'b52a7a74-98d0-4696-92c1-ef47d4c53627';

-- Show mailboxes directly assigned to user (via user_id)
SELECT 'Directly Assigned Mailboxes (via user_id):' AS section;
SELECT id, name, email_address, client_id, user_id, mailbox_type
FROM mailboxes
WHERE user_id = 'b52a7a74-98d0-4696-92c1-ef47d4c53627'
ORDER BY name;

-- Show client assignments (these give access to ALL mailboxes of a client)
SELECT 'Client Assignments (via user_client_assignments):' AS section;
SELECT uca.*, c.client_name
FROM user_client_assignments uca
JOIN clients c ON c.id = uca.client_id
WHERE uca.user_id = 'b52a7a74-98d0-4696-92c1-ef47d4c53627';

-- Show what mailboxes they get via client assignments
SELECT 'Mailboxes Accessible via Client Assignments:' AS section;
SELECT m.id, m.name, m.email_address, m.client_id, m.user_id, c.client_name
FROM mailboxes m
JOIN clients c ON c.id = m.client_id
WHERE m.client_id IN (
  SELECT client_id FROM user_client_assignments WHERE user_id = 'b52a7a74-98d0-4696-92c1-ef47d4c53627'
)
ORDER BY m.name;

-- Show total accessible mailboxes (via database function)
SELECT 'Total Accessible Mailboxes (from function):' AS section;
SELECT mailbox_id FROM get_user_accessible_mailboxes('b52a7a74-98d0-4696-92c1-ef47d4c53627');

-- ============================================
-- Step 2: Fix - Remove Client Assignments
-- ============================================

-- IMPORTANT: Only run this if you want the user to ONLY see their directly assigned mailboxes
-- Comment out the DELETE if you want to keep client assignments

-- Remove ALL client assignments for this user
-- This will make them only see mailboxes where user_id = their_id
DELETE FROM user_client_assignments
WHERE user_id = 'b52a7a74-98d0-4696-92c1-ef47d4c53627';

-- ============================================
-- Step 3: Verify Fix
-- ============================================

-- After running DELETE, verify the user now only sees their directly assigned mailboxes
SELECT 'After Fix - Accessible Mailboxes:' AS section;
SELECT mailbox_id FROM get_user_accessible_mailboxes('b52a7a74-98d0-4696-92c1-ef47d4c53627');

-- Should match only the directly assigned mailboxes
SELECT 'After Fix - Should Match These:' AS section;
SELECT id AS mailbox_id, name FROM mailboxes
WHERE user_id = 'b52a7a74-98d0-4696-92c1-ef47d4c53627';