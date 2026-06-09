-- Migration 115: surface inactive mailboxes in the list view.
--
-- A mailbox flipped to is_active=false vanishes from the mailboxes page
-- entirely (the list filters to accessible *active* mailboxes), leaving no
-- UI path to recover it. This adds a 2-arg overload of
-- get_user_accessible_mailboxes that can optionally include inactive
-- mailboxes; the list endpoint uses it so deactivated mailboxes still show
-- (with an "Inactive" label) and can be reactivated.
--
-- IMPORTANT — why an overload, not a replacement:
-- The existing 1-arg get_user_accessible_mailboxes(uuid) is referenced by the
-- RLS policies email_access (emails) and mailbox_access (mailboxes), so it
-- CANNOT be dropped, and its strict active-only behaviour must stay exactly as
-- is for those hot paths. We therefore leave it untouched and ADD a separate
-- 2-arg function. The new function has NO default on p_include_inactive, so a
-- 1-arg call (`{p_user_id}`) still resolves unambiguously to the original
-- 1-arg function — no overload ambiguity. Only the list endpoint, which passes
-- both args, hits this new function.
--
-- Keep the role-scoping logic below in sync with the 1-arg function.

CREATE OR REPLACE FUNCTION get_user_accessible_mailboxes(
  p_user_id uuid,
  p_include_inactive boolean
)
RETURNS TABLE(mailbox_id uuid)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_roles text[];
BEGIN
  SELECT roles INTO v_roles FROM user_profiles WHERE id = p_user_id;

  -- Admin: all mailboxes
  IF 'admin' = ANY(v_roles) THEN
    RETURN QUERY
      SELECT id FROM mailboxes
      WHERE (is_active = true OR p_include_inactive);
    RETURN;
  END IF;

  -- Account Manager: mailboxes of assigned clients OR own mailboxes
  IF 'account_manager' = ANY(v_roles) THEN
    RETURN QUERY
      SELECT m.id FROM mailboxes m
      WHERE (m.is_active = true OR p_include_inactive)
      AND (
        m.client_id IN (
          SELECT client_id FROM user_client_assignments WHERE user_id = p_user_id
        )
        OR m.user_id = p_user_id
      );
    RETURN;
  END IF;

  -- Client Manager: mailboxes of clients they manage
  IF 'client_manager' = ANY(v_roles) THEN
    RETURN QUERY
      SELECT m.id FROM mailboxes m
      WHERE (m.is_active = true OR p_include_inactive)
      AND m.client_id IN (
        SELECT client_id FROM client_manager_assignments WHERE user_id = p_user_id
      );
    RETURN;
  END IF;
END;
$$;

GRANT EXECUTE ON FUNCTION get_user_accessible_mailboxes(uuid, boolean) TO authenticated;

COMMENT ON FUNCTION get_user_accessible_mailboxes(uuid, boolean) IS
  'Role-scoped mailbox IDs for a user. p_include_inactive=true also returns '
  'deactivated mailboxes (list view only). Mirrors the 1-arg overload used by '
  'RLS policies — keep role logic in sync.';
