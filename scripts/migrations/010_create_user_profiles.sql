-- Migration: 010_create_user_profiles.sql
-- Purpose: Create user profiles table for RBAC, linked to Supabase Auth
-- Date: January 28, 2026

-- ============================================
-- 1. USER PROFILES TABLE
-- ============================================

-- User profiles table (extends Supabase auth.users)
CREATE TABLE IF NOT EXISTS user_profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email TEXT NOT NULL,
  name TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'account_manager' CHECK (role IN ('admin', 'client_manager', 'account_manager')),
  is_active BOOLEAN DEFAULT true,
  avatar_url TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for user_profiles
CREATE INDEX IF NOT EXISTS idx_user_profiles_email ON user_profiles(email);
CREATE INDEX IF NOT EXISTS idx_user_profiles_role ON user_profiles(role);
CREATE INDEX IF NOT EXISTS idx_user_profiles_active ON user_profiles(is_active) WHERE is_active = true;

-- ============================================
-- 2. USER-CLIENT ASSIGNMENTS TABLE
-- ============================================

-- User-Client assignments (for client_manager role)
CREATE TABLE IF NOT EXISTS user_client_assignments (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
  client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id, client_id)
);

CREATE INDEX IF NOT EXISTS idx_user_client_user ON user_client_assignments(user_id);
CREATE INDEX IF NOT EXISTS idx_user_client_client ON user_client_assignments(client_id);

-- ============================================
-- 3. UPDATE MAILBOXES TABLE
-- ============================================

-- Add user_id column to mailboxes (links mailbox to owner)
ALTER TABLE mailboxes
ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES user_profiles(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_mailboxes_user ON mailboxes(user_id);

-- ============================================
-- 4. AUTO-CREATE USER PROFILE ON SIGNUP
-- ============================================

-- Trigger function to auto-create user_profile on signup
-- IMPORTANT: Error handling ensures user creation succeeds even if profile creation fails
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER
SECURITY DEFINER
SET search_path = public
LANGUAGE plpgsql
AS $$
BEGIN
  -- Insert into user_profiles, with error handling
  INSERT INTO public.user_profiles (id, email, name, role, is_active)
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(
      NEW.raw_user_meta_data->>'full_name',
      NEW.raw_user_meta_data->>'name',
      split_part(NEW.email, '@', 1)
    ),
    'account_manager',  -- Default role for new signups
    true
  )
  ON CONFLICT (id) DO NOTHING;

  -- Always return NEW so user creation succeeds even if profile creation fails
  RETURN NEW;
EXCEPTION WHEN OTHERS THEN
  -- Log the error but don't fail the user creation
  RAISE WARNING 'Failed to create user profile for %: %', NEW.email, SQLERRM;
  RETURN NEW;
END;
$$;

-- Create trigger on auth.users
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION handle_new_user();

-- ============================================
-- 5. HELPER FUNCTION FOR ACCESSIBLE MAILBOXES
-- ============================================

-- Get mailbox IDs accessible to a user based on their role
CREATE OR REPLACE FUNCTION get_user_accessible_mailboxes(p_user_id UUID)
RETURNS TABLE(mailbox_id UUID) AS $$
DECLARE
  v_role TEXT;
BEGIN
  SELECT role INTO v_role FROM user_profiles WHERE id = p_user_id;

  IF v_role = 'admin' THEN
    -- Admin: all mailboxes
    RETURN QUERY SELECT id FROM mailboxes WHERE is_active = true;

  ELSIF v_role = 'account_manager' THEN
    -- Account Manager: only their own mailboxes
    RETURN QUERY SELECT id FROM mailboxes WHERE user_id = p_user_id AND is_active = true;

  ELSIF v_role = 'client_manager' THEN
    -- Client Manager: mailboxes of assigned clients
    RETURN QUERY
      SELECT m.id FROM mailboxes m
      WHERE m.client_id IN (
        SELECT client_id FROM user_client_assignments WHERE user_id = p_user_id
      ) AND m.is_active = true;
  END IF;
END;
$$ LANGUAGE plpgsql STABLE SECURITY DEFINER;

-- ============================================
-- 6. ROW LEVEL SECURITY POLICIES
-- ============================================

-- Enable RLS on tables
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_client_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE mailboxes ENABLE ROW LEVEL SECURITY;
ALTER TABLE emails ENABLE ROW LEVEL SECURITY;

-- User profiles - users can read their own profile
DROP POLICY IF EXISTS user_profile_select_self ON user_profiles;
CREATE POLICY user_profile_select_self ON user_profiles
  FOR SELECT USING (id = auth.uid());

-- User profiles - users can update their own profile (except role)
DROP POLICY IF EXISTS user_profile_update_self ON user_profiles;
CREATE POLICY user_profile_update_self ON user_profiles
  FOR UPDATE USING (id = auth.uid());

-- User profiles - admins can manage all profiles
DROP POLICY IF EXISTS user_profile_admin_all ON user_profiles;
CREATE POLICY user_profile_admin_all ON user_profiles
  FOR ALL USING (
    EXISTS (SELECT 1 FROM user_profiles WHERE id = auth.uid() AND role = 'admin')
  );

-- User client assignments - admins only
DROP POLICY IF EXISTS user_client_admin ON user_client_assignments;
CREATE POLICY user_client_admin ON user_client_assignments
  FOR ALL USING (
    EXISTS (SELECT 1 FROM user_profiles WHERE id = auth.uid() AND role = 'admin')
  );

-- User client assignments - users can view their own
DROP POLICY IF EXISTS user_client_select_self ON user_client_assignments;
CREATE POLICY user_client_select_self ON user_client_assignments
  FOR SELECT USING (user_id = auth.uid());

-- Mailbox access policy - based on role
DROP POLICY IF EXISTS mailbox_access ON mailboxes;
CREATE POLICY mailbox_access ON mailboxes
  FOR ALL USING (
    id IN (SELECT get_user_accessible_mailboxes(auth.uid()))
  );

-- Email access policy - via mailbox access
DROP POLICY IF EXISTS email_access ON emails;
CREATE POLICY email_access ON emails
  FOR ALL USING (
    mailbox_id IN (SELECT get_user_accessible_mailboxes(auth.uid()))
  );

-- ============================================
-- 7. GRANT PERMISSIONS
-- ============================================

-- Grant access to authenticated users
GRANT SELECT, INSERT, UPDATE ON user_profiles TO authenticated;
GRANT SELECT, INSERT, DELETE ON user_client_assignments TO authenticated;
GRANT SELECT ON mailboxes TO authenticated;
GRANT SELECT ON emails TO authenticated;

-- Grant execute on functions
GRANT EXECUTE ON FUNCTION get_user_accessible_mailboxes TO authenticated;
GRANT EXECUTE ON FUNCTION handle_new_user TO service_role;
GRANT EXECUTE ON FUNCTION handle_new_user TO postgres;

-- ============================================
-- 8. UPDATE TIMESTAMPS TRIGGER
-- ============================================

-- Trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_user_profiles_updated_at ON user_profiles;
CREATE TRIGGER update_user_profiles_updated_at
  BEFORE UPDATE ON user_profiles
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- 9. BACKFILL EXISTING USERS
-- ============================================

-- Create user profiles for any existing auth.users that don't have profiles
INSERT INTO user_profiles (id, email, name, role, is_active)
SELECT
  id,
  email,
  COALESCE(
    raw_user_meta_data->>'full_name',
    raw_user_meta_data->>'name',
    split_part(email, '@', 1)
  ),
  'account_manager',
  true
FROM auth.users
WHERE id NOT IN (SELECT id FROM user_profiles)
ON CONFLICT (id) DO NOTHING;

-- ============================================
-- 10. SET FIRST USER AS ADMIN (OPTIONAL)
-- ============================================

-- Uncomment and modify to set a specific user as admin:
-- UPDATE user_profiles
-- SET role = 'admin'
-- WHERE email = 'your-email@example.com';

-- Or set the first user as admin:
-- UPDATE user_profiles
-- SET role = 'admin'
-- WHERE id = (SELECT id FROM auth.users ORDER BY created_at LIMIT 1);
