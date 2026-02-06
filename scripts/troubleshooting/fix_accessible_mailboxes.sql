-- Fix: Update get_user_accessible_mailboxes to handle roles array
-- This script recreates the RPC function to match the current schema
-- Note: Using CREATE OR REPLACE to avoid dropping (function is used by RLS policies)

-- Update the function to handle roles[] array
CREATE OR REPLACE FUNCTION get_user_accessible_mailboxes(p_user_id UUID)
RETURNS TABLE(mailbox_id UUID) AS $$
DECLARE
  v_roles TEXT[];
BEGIN
  -- Get user's roles array
  SELECT roles INTO v_roles FROM user_profiles WHERE id = p_user_id;

  -- Debug: Log what we found
  RAISE NOTICE 'User ID: %, Roles: %', p_user_id, v_roles;

  -- Admin: all active mailboxes
  IF 'admin' = ANY(v_roles) THEN
    RAISE NOTICE 'User is admin, returning all active mailboxes';
    RETURN QUERY SELECT id FROM mailboxes WHERE is_active = true;
    RETURN;
  END IF;

  -- Account Manager: mailboxes of assigned clients OR own mailboxes
  IF 'account_manager' = ANY(v_roles) THEN
    RAISE NOTICE 'User is account_manager, checking assignments';
    RETURN QUERY
      SELECT m.id FROM mailboxes m
      WHERE m.is_active = true
      AND (
        -- Mailboxes of clients they're assigned to
        m.client_id IN (
          SELECT client_id FROM user_client_assignments WHERE user_id = p_user_id
        )
        OR
        -- Their own mailboxes (directly assigned)
        m.user_id = p_user_id
      );
    RETURN;
  END IF;

  -- Client Manager: mailboxes of clients they manage
  IF 'client_manager' = ANY(v_roles) THEN
    RAISE NOTICE 'User is client_manager, checking client assignments';
    RETURN QUERY
      SELECT m.id FROM mailboxes m
      WHERE m.is_active = true
      AND m.client_id IN (
        SELECT client_id FROM client_manager_assignments WHERE user_id = p_user_id
      );
    RETURN;
  END IF;

  RAISE NOTICE 'No matching role found, returning empty';
END;
$$ LANGUAGE plpgsql STABLE SECURITY DEFINER;

-- Grant execution permission
GRANT EXECUTE ON FUNCTION get_user_accessible_mailboxes TO authenticated;

COMMENT ON FUNCTION get_user_accessible_mailboxes IS 'Returns mailbox IDs accessible to a user based on their roles array (supports multiple roles)';

-- ============================================
-- VERIFICATION QUERIES
-- ============================================

-- 1. Check total mailboxes in database
SELECT
  COUNT(*) as total_mailboxes,
  COUNT(*) FILTER (WHERE is_active = true) as active_mailboxes,
  COUNT(*) FILTER (WHERE is_active = false) as inactive_mailboxes
FROM mailboxes;

-- 2. Check user_profiles structure
SELECT
  id,
  email,
  name,
  roles,
  is_active
FROM user_profiles
ORDER BY created_at;

-- 3. Test the function for the current user
-- Replace 'your-email@example.com' with actual email
DO $$
DECLARE
  v_user_id UUID;
  v_mailbox_ids UUID[];
BEGIN
  -- Get user ID (update email as needed)
  SELECT id INTO v_user_id FROM user_profiles WHERE email LIKE '%Dinesh%' OR email LIKE '%dinesh%' LIMIT 1;

  IF v_user_id IS NULL THEN
    RAISE NOTICE 'User not found, trying first user in database';
    SELECT id INTO v_user_id FROM user_profiles ORDER BY created_at LIMIT 1;
  END IF;

  RAISE NOTICE 'Testing for user ID: %', v_user_id;

  -- Call the function
  SELECT ARRAY_AGG(mailbox_id) INTO v_mailbox_ids
  FROM get_user_accessible_mailboxes(v_user_id);

  RAISE NOTICE 'Accessible mailbox IDs: %', v_mailbox_ids;
  RAISE NOTICE 'Count: %', COALESCE(array_length(v_mailbox_ids, 1), 0);
END $$;

-- 4. Show mailbox assignments
SELECT
  m.id,
  m.name,
  m.email_address,
  m.is_active,
  m.user_id,
  m.client_id,
  up.email as user_email
FROM mailboxes m
LEFT JOIN user_profiles up ON m.user_id = up.id
ORDER BY m.is_active DESC, m.created_at DESC;