-- Migration 014: Fix role hierarchy and clarify assignments
--
-- Purpose: Correct the role hierarchy to match business logic:
--   - Admin: Full access to everything
--   - Client Manager: Manages account managers for assigned clients (oversight role)
--   - Account Manager: Direct user assigned to clients, manages mailboxes
--
-- Date: 2026-02-02

-- ============================================
-- ROLE HIERARCHY (Corrected)
-- ============================================
--
-- admin:
--   - Full platform access
--   - Can manage all users, clients, and mailboxes
--
-- client_manager:
--   - Oversees account_managers for specific clients
--   - Can assign account_managers to their clients
--   - Has VIEW access to mailboxes of their managed clients (for oversight)
--   - Does NOT get directly assigned to clients (they manage the client relationship)
--
-- account_manager:
--   - Individual contributors assigned to specific clients
--   - Manages mailboxes for their assigned clients
--   - Direct operational access to mailboxes
--
-- ============================================

-- Add a separate table for client_manager assignments (who manages which clients)
CREATE TABLE IF NOT EXISTS client_manager_assignments (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
  client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id, client_id)
);

CREATE INDEX idx_client_manager_user ON client_manager_assignments(user_id);
CREATE INDEX idx_client_manager_client ON client_manager_assignments(client_id);

COMMENT ON TABLE client_manager_assignments IS 'Tracks which client_managers oversee which clients';

-- Update comments on user_client_assignments to clarify it's for account_managers
COMMENT ON TABLE user_client_assignments IS 'Tracks which account_managers are assigned to which clients (operational assignments)';

-- Update the helper function to handle the corrected role hierarchy
CREATE OR REPLACE FUNCTION get_user_accessible_mailboxes(p_user_id UUID)
RETURNS TABLE(mailbox_id UUID) AS $$
DECLARE
  v_roles TEXT[];
BEGIN
  SELECT roles INTO v_roles FROM user_profiles WHERE id = p_user_id;

  -- Admin: all mailboxes
  IF 'admin' = ANY(v_roles) THEN
    RETURN QUERY SELECT id FROM mailboxes WHERE is_active = true;

  -- Account Manager: mailboxes of assigned clients OR own mailboxes
  ELSIF 'account_manager' = ANY(v_roles) THEN
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

  -- Client Manager: mailboxes of clients they manage (for oversight)
  ELSIF 'client_manager' = ANY(v_roles) THEN
    RETURN QUERY
      SELECT m.id FROM mailboxes m
      WHERE m.is_active = true
      AND m.client_id IN (
        SELECT client_id FROM client_manager_assignments WHERE user_id = p_user_id
      );
  END IF;
END;
$$ LANGUAGE plpgsql STABLE SECURITY DEFINER;

COMMENT ON FUNCTION get_user_accessible_mailboxes IS 'Returns mailbox IDs accessible to a user based on their role(s) and assignments';

-- Add RLS policy for client_manager_assignments table
ALTER TABLE client_manager_assignments ENABLE ROW LEVEL SECURITY;

-- Admins can manage all client_manager assignments
CREATE POLICY client_manager_assignments_admin ON client_manager_assignments
  FOR ALL USING (
    EXISTS (
      SELECT 1 FROM user_profiles
      WHERE id = auth.uid() AND 'admin' = ANY(roles)
    )
  );

-- Client managers can view their own assignments
CREATE POLICY client_manager_assignments_self ON client_manager_assignments
  FOR SELECT USING (user_id = auth.uid());

SELECT 'Role hierarchy fixed! account_managers assigned to clients, client_managers oversee clients' AS status;