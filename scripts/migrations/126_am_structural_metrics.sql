-- 126: AM communication-quality Tier-A STRUCTURAL metrics (task 15.2).
--
-- Server-side aggregate for the AM coaching quality layer (docs/design/AM_QUALITY_LAYER_DESIGN.md).
-- Computes the 4 Tier-A structural metrics for ONE mailbox over ONE time window. The service
-- (am_coaching_service.py) calls it three times per AM — trailing-12-months (headline), last-90d,
-- and prior-90d (for self-referential trend) — and applies the staleness guard in app code.
--
-- Bases are the ones validated in the 15.1 readiness refresh (am_coaching_readiness_refresh.py):
--   * exchange velocity / depth      -> emails + canonical_thread_id  (NOT thread_status: mailbox_id
--                                       is 86% NULL — silent-zero)
--   * responsiveness (latency)       -> email_response_metrics (our OUTBOUND replying to their inbound),
--                                       business-hours variant, auto-replies excluded
--   * multithreading                 -> emails -> customer_company_id -> distinct customer_contact_id
--   * follow-up persistence          -> per-thread outbound sequence: did the AM re-touch after the
--                                       customer went silent, or let the thread go cold?
--
-- Every metric also returns its population/coverage so thin coverage is visible, not hidden.
-- Recency (max sent_date, window-independent) is returned so the service can flag stale mailboxes
-- (Ehab ~2026-05-21, Kenneth ~2026-05-16 had stalled syncs at 15.1) instead of reading a stalled
-- sync as "the AM went quiet".

CREATE OR REPLACE FUNCTION am_structural_metrics(
    p_mailbox_id uuid,
    p_client_id  uuid,
    p_start      timestamptz,
    p_end        timestamptz
)
RETURNS jsonb
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
SET statement_timeout = '120s'
AS $fn$
WITH win AS (   -- the mailbox's emails inside the window
  SELECT id, canonical_thread_id ct, is_outbound, sent_date,
         customer_company_id, customer_contact_id
  FROM emails
  WHERE mailbox_id = p_mailbox_id AND client_id = p_client_id
    AND sent_date >= p_start AND sent_date < p_end
),
-- ── exchange velocity (emails per active thread + per active week) ──────────
thr AS (
  SELECT ct,
         count(*) n,
         count(*) FILTER (WHERE is_outbound) n_out,
         count(*) FILTER (WHERE NOT coalesce(is_outbound,false)) n_in
  FROM win WHERE ct IS NOT NULL GROUP BY ct
),
vel AS (
  SELECT count(*) threads_active,
         round(avg(n)::numeric,2) avg_emails_per_thread,
         round((percentile_cont(0.5) WITHIN GROUP (ORDER BY n))::numeric,1) median_emails_per_thread,
         count(*) FILTER (WHERE n_out > 0 AND n_in > 0) two_sided
  FROM thr
),
wk AS (
  SELECT count(*) total_emails,
         count(DISTINCT date_trunc('week', sent_date)) active_weeks,
         count(*) FILTER (WHERE ct IS NOT NULL) threaded
  FROM win
),
inb AS (SELECT count(*) inbound FROM win WHERE NOT coalesce(is_outbound,false)),
-- ── responsiveness (our reply latency to inbound, business hours) ──────────
resp AS (
  SELECT m.business_hours_response_time_seconds bh, m.response_time_seconds rt
  FROM email_response_metrics m
  JOIN emails e ON e.id = m.email_id
  WHERE e.mailbox_id = p_mailbox_id
    AND e.is_outbound IS TRUE                    -- our outbound = WE replied to them
    AND coalesce(m.is_auto_reply,false) = false
    AND e.sent_date >= p_start AND e.sent_date < p_end
),
resp_agg AS (
  SELECT count(*) reply_rows,
         count(*) FILTER (WHERE bh IS NOT NULL) bh_rows,
         count(*) FILTER (WHERE bh > 0) bh_positive,   -- bh col is ~85% zero (tz artifact); used to flag degraded
         round((percentile_cont(0.5) WITHIN GROUP (ORDER BY bh)
                FILTER (WHERE bh > 0) / 3600.0)::numeric,2) median_bh_positive_hours,
         round((percentile_cont(0.5) WITHIN GROUP (ORDER BY bh)
                FILTER (WHERE bh IS NOT NULL) / 3600.0)::numeric,2) median_bh_hours,
         round((percentile_cont(0.5) WITHIN GROUP (ORDER BY rt) / 3600.0)::numeric,2) median_raw_hours
  FROM resp
),
-- ── multithreading (distinct contacts engaged per company) ─────────────────
cc AS (
  SELECT customer_company_id comp,
         count(DISTINCT customer_contact_id) FILTER (WHERE customer_contact_id IS NOT NULL) ncontacts
  FROM win WHERE customer_company_id IS NOT NULL GROUP BY 1
),
mt AS (
  SELECT count(*) companies,
         round(avg(ncontacts)::numeric,2) avg_contacts_per_company,
         count(*) FILTER (WHERE ncontacts >= 2) multithreaded
  FROM cc
),
-- ── follow-up persistence (re-touch after silence vs let go cold) ──────────
-- classify each outbound by the NEXT email in its thread:
--   next is outbound  -> AM re-touched their own unanswered message (persistence)
--   next is inbound   -> the customer replied (answered, not a silence point)
--   no next + >7d old  -> AM's message was last, customer silent, AM never followed up (cold)
seq AS (
  SELECT is_outbound, sent_date,
         lead(is_outbound) OVER w next_out
  FROM win WHERE ct IS NOT NULL
  WINDOW w AS (PARTITION BY ct ORDER BY sent_date, id)
),
fu AS (
  SELECT count(*) FILTER (WHERE is_outbound) outbound,
         count(*) FILTER (WHERE is_outbound AND next_out IS TRUE) re_touch,
         count(*) FILTER (WHERE is_outbound AND next_out IS FALSE) answered,
         count(*) FILTER (WHERE is_outbound AND next_out IS NULL
                          AND sent_date < p_end - interval '7 days') cold
  FROM seq
),
-- ── recency (window-INDEPENDENT — drives the staleness flag) ───────────────
rec AS (
  SELECT to_char(max(sent_date),'YYYY-MM-DD') last_email_date,
         (CURRENT_DATE - max(sent_date)::date) days_since_last,
         count(*) total_emails_all
  FROM emails WHERE mailbox_id = p_mailbox_id AND client_id = p_client_id
)
SELECT jsonb_build_object(
  'window', jsonb_build_object('start', p_start, 'end', p_end),
  'volume', jsonb_build_object(
     'emails', (SELECT total_emails FROM wk),
     'inbound', (SELECT inbound FROM inb),
     'active_weeks', (SELECT active_weeks FROM wk),
     'threaded', (SELECT threaded FROM wk)),
  'exchange_velocity', jsonb_build_object(
     'threads_active', (SELECT threads_active FROM vel),
     'avg_emails_per_thread', (SELECT avg_emails_per_thread FROM vel),
     'median_emails_per_thread', (SELECT median_emails_per_thread FROM vel),
     'two_sided_thread_pct', CASE WHEN (SELECT threads_active FROM vel) > 0
        THEN round(((SELECT two_sided FROM vel) * 100.0 / (SELECT threads_active FROM vel))::numeric,1) END,
     'emails_per_active_week', CASE WHEN (SELECT active_weeks FROM wk) > 0
        THEN round(((SELECT total_emails FROM wk) * 1.0 / (SELECT active_weeks FROM wk))::numeric,2) END),
  'responsiveness', jsonb_build_object(
     'reply_rows', (SELECT reply_rows FROM resp_agg),
     'bh_populated_rows', (SELECT bh_rows FROM resp_agg),
     'bh_positive_rows', (SELECT bh_positive FROM resp_agg),
     'median_raw_hours', (SELECT median_raw_hours FROM resp_agg),
     'median_business_hours', (SELECT median_bh_hours FROM resp_agg),
     'median_business_hours_positive_only', (SELECT median_bh_positive_hours FROM resp_agg),
     'coverage_pct_of_inbound', CASE WHEN (SELECT inbound FROM inb) > 0
        THEN round(((SELECT reply_rows FROM resp_agg) * 100.0 / (SELECT inbound FROM inb))::numeric,1) END),
  'multithreading', jsonb_build_object(
     'companies', (SELECT companies FROM mt),
     'avg_contacts_per_company', (SELECT avg_contacts_per_company FROM mt),
     'multithreaded_companies', (SELECT multithreaded FROM mt),
     'multithreaded_pct', CASE WHEN (SELECT companies FROM mt) > 0
        THEN round(((SELECT multithreaded FROM mt) * 100.0 / (SELECT companies FROM mt))::numeric,1) END),
  'follow_up_persistence', jsonb_build_object(
     'outbound', (SELECT outbound FROM fu),
     're_touch', (SELECT re_touch FROM fu),
     'answered', (SELECT answered FROM fu),
     'cold', (SELECT cold FROM fu),
     'persistence_pct', CASE WHEN ((SELECT re_touch FROM fu) + (SELECT cold FROM fu)) > 0
        THEN round(((SELECT re_touch FROM fu) * 100.0
                    / ((SELECT re_touch FROM fu) + (SELECT cold FROM fu)))::numeric,1) END),
  'recency', jsonb_build_object(
     'last_email_date', (SELECT last_email_date FROM rec),
     'days_since_last_email', (SELECT days_since_last FROM rec),
     'total_emails_all_time', (SELECT total_emails_all FROM rec))
);
$fn$;

GRANT EXECUTE ON FUNCTION am_structural_metrics(uuid, uuid, timestamptz, timestamptz)
  TO authenticated, service_role;
