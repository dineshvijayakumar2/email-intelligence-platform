-- Migration 012: Add Multiple Roles Support
--
-- Purpose: Allow users to have multiple roles simultaneously
-- Example: Admin user can also be an account_manager to monitor mailboxes linked to clients
--
-- Date: 2026-02-02

-- ============================================
-- Step 1: Drop dependent RLS policies first
-- ============================================

-- Drop policies that depend on the role column
DROP POLICY IF EXISTS user_profile_admin_all ON user_profiles;
DROP POLICY IF EXISTS user_client_admin ON user_client_assignments;

-- ============================================
-- Step 2: Change role column from TEXT to TEXT[]
-- ============================================

-- Add new roles column (array)
ALTER TABLE user_profiles
ADD COLUMN IF NOT EXISTS roles TEXT[] DEFAULT ARRAY['account_manager'::TEXT];

-- Migrate existing role data to roles array
UPDATE user_profiles
SET roles = ARRAY[role]
WHERE roles IS NULL OR cardinality(roles) = 0;

-- Drop old role column (after migration)
ALTER TABLE user_profiles
DROP COLUMN IF EXISTS role;

-- Add constraint to validate role values
ALTER TABLE user_profiles
ADD CONSTRAINT user_profiles_roles_check
CHECK (
  roles <@ ARRAY['admin', 'client_manager', 'account_manager']::TEXT[] AND
  cardinality(roles) > 0
);

-- ============================================
-- Step 3: Update indexes
-- ============================================

-- Drop old role index
DROP INDEX IF EXISTS idx_user_profiles_role;

-- Create GIN index for array operations (efficient for ANY queries)
CREATE INDEX IF NOT EXISTS idx_user_profiles_roles ON user_profiles USING GIN(roles);

-- ============================================
-- Step 4: Update helper function for accessible mailboxes
-- ============================================

-- Updated function to handle multiple roles
CREATE OR REPLACE FUNCTION get_user_accessible_mailboxes(p_user_id UUID)
RETURNS TABLE(mailbox_id UUID) AS $$
DECLARE
  v_roles TEXT[];
BEGIN
  SELECT roles INTO v_roles FROM user_profiles WHERE id = p_user_id;

  IF v_roles IS NULL THEN
    RETURN;
  END IF;

  -- If user has admin role, return all mailboxes
  IF 'admin' = ANY(v_roles) THEN
    RETURN QUERY SELECT id FROM mailboxes WHERE is_active = true;
    RETURN;
  END IF;

  -- Collect mailboxes based on all roles
  -- Use UNION to combine results from different roles
  IF 'account_manager' = ANY(v_roles) THEN
    -- Account Manager: their own mailboxes
    RETURN QUERY
      SELECT id FROM mailboxes
      WHERE user_id = p_user_id AND is_active = true;
  END IF;

  IF 'client_manager' = ANY(v_roles) THEN
    -- Client Manager: mailboxes of assigned clients
    RETURN QUERY
      SELECT m.id FROM mailboxes m
      WHERE m.client_id IN (
        SELECT client_id FROM user_client_assignments WHERE user_id = p_user_id
      ) AND m.is_active = true
      AND m.id NOT IN (
        -- Avoid duplicates if already returned by account_manager role
        SELECT id FROM mailboxes WHERE user_id = p_user_id AND is_active = true
      );
  END IF;
END;
$$ LANGUAGE plpgsql STABLE SECURITY DEFINER;

-- ============================================
-- Step 5: Recreate RLS policies to use roles array
-- ============================================

-- Recreate admin policies using roles array
CREATE POLICY user_profile_admin_all ON user_profiles
  FOR ALL USING (
    EXISTS (
      SELECT 1 FROM user_profiles
      WHERE id = auth.uid() AND 'admin' = ANY(roles)
    )
  );

CREATE POLICY user_client_admin ON user_client_assignments
  FOR ALL USING (
    EXISTS (
      SELECT 1 FROM user_profiles
      WHERE id = auth.uid() AND 'admin' = ANY(roles)
    )
  );

-- ============================================
-- Step 6: Add helper function to check if user has role
-- ============================================

-- Helper function to check if user has a specific role
CREATE OR REPLACE FUNCTION user_has_role(p_user_id UUID, p_role TEXT)
RETURNS BOOLEAN AS $$
DECLARE
  v_roles TEXT[];
BEGIN
  SELECT roles INTO v_roles FROM user_profiles WHERE id = p_user_id;
  RETURN p_role = ANY(v_roles);
END;
$$ LANGUAGE plpgsql STABLE SECURITY DEFINER;

GRANT EXECUTE ON FUNCTION user_has_role TO authenticated;

-- ============================================
-- Step 7: Update trigger function for new users
-- ============================================

-- Update handle_new_user to use roles array
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER
SECURITY DEFINER
SET search_path = public
LANGUAGE plpgsql
AS $$
BEGIN
  -- Insert into user_profiles with roles array
  INSERT INTO public.user_profiles (id, email, name, roles, is_active)
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(
      NEW.raw_user_meta_data->>'full_name',
      NEW.raw_user_meta_data->>'name',
      split_part(NEW.email, '@', 1)
    ),
    ARRAY['account_manager']::TEXT[],  -- Default role as array
    true
  )
  ON CONFLICT (id) DO NOTHING;

  RETURN NEW;
EXCEPTION WHEN OTHERS THEN
  RAISE WARNING 'Failed to create user profile for %: %', NEW.email, SQLERRM;
  RETURN NEW;
END;
$$;

-- ============================================
-- Step 8: Add comments
-- ============================================

COMMENT ON COLUMN user_profiles.roles IS 'Array of user roles: admin, client_manager, account_manager. Users can have multiple roles.';

-- ============================================
-- Verification
-- ============================================

SELECT 'Multiple roles migration completed successfully!' AS status;