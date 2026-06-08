-- Migration 116: SQL-side body_text truncation RPCs
-- Egress reduction (BODY_TEXT_EGRESS_AUDIT Tier 3): callers fetch only the
-- portion of body_text they actually consume instead of the full ~8.4 KB avg row.
-- Additive and reversible (DROP FUNCTION). No table schema change.
--
-- n is clamped inside the function: negative is rejected, max capped at 50000,
-- so a bad caller cannot defeat the egress savings.

CREATE OR REPLACE FUNCTION emails_body_left(email_ids uuid[], n int)
RETURNS TABLE(id uuid, body text)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    IF n < 0 THEN
        RAISE EXCEPTION 'emails_body_left: n must be non-negative, got %', n;
    END IF;
    n := LEAST(n, 50000);
    RETURN QUERY
    SELECT e.id, LEFT(e.body_text, n)
    FROM emails e
    WHERE e.id = ANY(email_ids);
END;
$$;

CREATE OR REPLACE FUNCTION emails_body_right(email_ids uuid[], n int)
RETURNS TABLE(id uuid, body text)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    IF n < 0 THEN
        RAISE EXCEPTION 'emails_body_right: n must be non-negative, got %', n;
    END IF;
    n := LEAST(n, 50000);
    RETURN QUERY
    SELECT e.id, RIGHT(e.body_text, n)
    FROM emails e
    WHERE e.id = ANY(email_ids);
END;
$$;
