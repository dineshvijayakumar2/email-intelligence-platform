-- RBAC Verification Query for dinwin1989@gmail.com
-- Run this in Supabase SQL Editor

-- User ID for dinwin1989@gmail.com
-- b52a7a74-98d0-4696-92c1-ef47d4c53627

-- 1. Check user profile and roles
SELECT 'User Profile:' AS section, id, email, name, roles, is_active
FROM user_profiles
WHERE id = 'b52a7a74-98d0-4696-92c1-ef47d4c53627';

-- 2. Check user_client_assignments (for account_manager role)
SELECT 'User-Client Assignments (account_manager):' AS section,
       uca.*, c.name AS client_name
FROM user_client_assignments uca
JOIN clients c ON c.id = uca.client_id
WHERE uca.user_id = 'b52a7a74-98d0-4696-92c1-ef47d4c53627';

-- 3. Check client_manager_assignments (for client_manager role)
SELECT 'Client Manager Assignments:' AS section,
       cma.*, c.name AS client_name
FROM client_manager_assignments cma
JOIN clients c ON c.id = cma.client_id
WHERE cma.user_id = 'b52a7a74-98d0-4696-92c1-ef47d4c53627';

-- 4. Call the database function to see what mailboxes it returns
SELECT 'Accessible Mailboxes (from function):' AS section,
       mailbox_id
FROM get_user_accessible_mailboxes('b52a7a74-98d0-4696-92c1-ef47d4c53627');

-- 5. Get full mailbox details for accessible mailboxes
SELECT 'Mailbox Details:' AS section,
       m.id, m.name, m.email_address, m.client_id, m.user_id,
       c.name AS client_name
FROM mailboxes m
LEFT JOIN clients c ON c.id = m.client_id
WHERE m.id IN (
  SELECT mailbox_id FROM get_user_accessible_mailboxes('b52a7a74-98d0-4696-92c1-ef47d4c53627')
)
ORDER BY m.name;

-- 6. Show all clients (for reference)
SELECT 'All Clients:' AS section, id, name
FROM clients
ORDER BY name;