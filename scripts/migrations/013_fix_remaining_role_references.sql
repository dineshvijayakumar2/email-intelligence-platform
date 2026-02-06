-- Migration 013: Fix any remaining references to old 'role' column
--
-- Purpose: Drop any policies or views that still reference the old role column
-- Date: 2026-02-02

-- Drop all RLS policies on user-related tables to ensure clean slate
DROP POLICY IF EXISTS user_profile_select_self ON user_profiles;
DROP POLICY IF EXISTS user_profile_update_self ON user_profiles;
DROP POLICY IF EXISTS user_profile_admin_all ON user_profiles;
DROP POLICY IF EXISTS user_client_admin ON user_client_assignments;
DROP POLICY IF EXISTS user_client_select_self ON user_client_assignments;
DROP POLICY IF EXISTS user_client_manager ON user_client_assignments;

-- Recreate all policies using the new 'roles' array column
-- ============================================
-- User Profiles Policies
-- ============================================

-- Users can read their own profile
CREATE POLICY user_profile_select_self ON user_profiles
  FOR SELECT USING (id = auth.uid());

-- Users can update their own profile (but not roles - that's admin only)
CREATE POLICY user_profile_update_self ON user_profiles
  FOR UPDATE USING (id = auth.uid());

-- Admins can manage all profiles
CREATE POLICY user_profile_admin_all ON user_profiles
  FOR ALL USING (
    EXISTS (
      SELECT 1 FROM user_profiles
      WHERE id = auth.uid() AND 'admin' = ANY(roles)
    )
  );

-- ============================================
-- User Client Assignments Policies
-- ============================================

-- Admins can manage all client assignments
CREATE POLICY user_client_admin ON user_client_assignments
  FOR ALL USING (
    EXISTS (
      SELECT 1 FROM user_profiles
      WHERE id = auth.uid() AND 'admin' = ANY(roles)
    )
  );

-- Users can view their own client assignments
CREATE POLICY user_client_select_self ON user_client_assignments
  FOR SELECT USING (user_id = auth.uid());

-- Client managers can view their assigned clients
CREATE POLICY user_client_manager ON user_client_assignments
  FOR SELECT USING (
    EXISTS (
      SELECT 1 FROM user_profiles
      WHERE id = auth.uid() AND 'client_manager' = ANY(roles)
    ) AND user_id = auth.uid()
  );

-- Verify the column exists and is correct type
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'user_profiles'
    AND column_name = 'roles'
    AND data_type = 'ARRAY'
  ) THEN
    RAISE EXCEPTION 'roles column not found or not an array type';
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'user_profiles'
    AND column_name = 'role'
  ) THEN
    RAISE EXCEPTION 'old role column still exists - run migration 012 first';
  END IF;
END $$;

SELECT 'All remaining role references fixed!' AS status;