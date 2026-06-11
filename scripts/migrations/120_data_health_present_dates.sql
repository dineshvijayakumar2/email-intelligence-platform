-- 120: Data Health fixes
-- (a) data_health_present_dates: server-side DISTINCT dates with email in a window.
--     Replaces the buggy endpoint fetch `.select('sent_date').limit(200000)` which PostgREST
--     silently capped at db-max-rows (1000) with NO order — so it only ever saw ~2 dates and
--     false-flagged ~21 weekdays as "missing". Aggregating in SQL is correct and cheap.
-- (b) data_health_mailbox_bounds: per-mailbox max(sent_date), to compute the missing range
--     for re-auth-stalled mailboxes surfaced on the Data Health page.

CREATE OR REPLACE FUNCTION data_health_present_dates(p_client uuid, p_since date)
RETURNS jsonb
LANGUAGE sql STABLE
SET search_path = public
AS $$
  SELECT coalesce(jsonb_agg(d ORDER BY d), '[]'::jsonb)
  FROM (
    SELECT DISTINCT sent_date::date AS d
    FROM emails
    WHERE (p_client IS NULL OR client_id = p_client)
      AND sent_date >= p_since
  ) s;
$$;

GRANT EXECUTE ON FUNCTION data_health_present_dates(uuid, date) TO anon, authenticated, service_role;

CREATE OR REPLACE FUNCTION data_health_mailbox_bounds(p_client uuid)
RETURNS jsonb
LANGUAGE sql STABLE
SET search_path = public
AS $$
  SELECT coalesce(jsonb_object_agg(mailbox_id, last_email), '{}'::jsonb)
  FROM (
    SELECT mailbox_id, max(sent_date)::date AS last_email
    FROM emails
    WHERE (p_client IS NULL OR client_id = p_client)
      AND mailbox_id IS NOT NULL
    GROUP BY mailbox_id
  ) s;
$$;

GRANT EXECUTE ON FUNCTION data_health_mailbox_bounds(uuid) TO anon, authenticated, service_role;
