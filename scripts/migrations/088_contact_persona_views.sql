-- =============================================================================
-- Migration 088: Contact Persona Views
-- Date: 2026-04-17
-- Purpose: Create views that aggregate contact-level intelligence from
--          QB quote/job data, email engagement metrics, and company enrichment
--          into a unified "persona" view for AM-facing intelligence.
--
-- Views created:
--   1. contact_quote_metrics     — per-contact QB quote/job aggregates (VIEW)
--   2. contact_email_metrics     — per-contact email engagement (MATERIALIZED VIEW)
--   3. contact_persona           — unified persona combining all dimensions (VIEW)
--   4. company_contact_summary   — per-company rollup of contact personas (VIEW)
--   5. industry_benchmarks       — per-industry averages for benchmarking (VIEW)
--
-- Dependencies:
--   customer_contacts, customer_companies, qb_quotes, qb_jobs,
--   email_contact_links, emails, email_response_metrics
--
-- Column name mapping (spec → actual):
--   quote_value      → sell_ex_tax       (qb_quotes)
--   job_value        → retail_sale       (qb_jobs)
--   quote_status     → has_job / date_accepted (qb_quotes)
--   created_date     → date_created      (qb_quotes)
--   customer_type    → qb_customer_type  (customer_companies)
--   seniority        → seniority_level   (customer_contacts)
--   is_primary       → is_primary_contact(customer_contacts)
--   response_time_hours → response_time_seconds (email_response_metrics)
-- =============================================================================


-- ═══════════════════════════════════════════════════════════════════════════
-- SUPPORTING INDEXES
-- Required for the case-insensitive email join in contact_quote_metrics.
-- Without these, the view times out on 21K contacts × 148K quotes.
-- ═══════════════════════════════════════════════════════════════════════════

CREATE INDEX IF NOT EXISTS idx_qb_quotes_contact_email_lower
    ON qb_quotes (lower(contact_email), client_id);

CREATE INDEX IF NOT EXISTS idx_customer_contacts_email_lower
    ON customer_contacts (lower(email_address), client_id);

CREATE INDEX IF NOT EXISTS idx_qb_jobs_quote_no_client
    ON qb_jobs (quote_no, client_id);


-- ═══════════════════════════════════════════════════════════════════════════
-- VIEW 1: contact_quote_metrics
-- Per-contact aggregated quote and job metrics from QuickBase.
--
-- Join chain:
--   customer_contacts.email_address → qb_quotes.contact_email (case-insensitive)
--   qb_quotes.quote_no → qb_jobs.quote_no (+ client_id match)
--
-- "Accepted" = date_accepted IS NOT NULL (or has_job = true)
-- ═══════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE VIEW contact_quote_metrics AS
SELECT
    cc.id                                            AS contact_id,
    cc.client_id,
    COUNT(DISTINCT qq.id)                            AS quote_count,
    COUNT(DISTINCT qq.id) FILTER (
        WHERE qq.date_accepted IS NOT NULL
    )                                                AS accepted_quote_count,
    CASE
        WHEN COUNT(DISTINCT qq.id) = 0 THEN NULL
        ELSE ROUND(
            COUNT(DISTINCT qq.id) FILTER (WHERE qq.date_accepted IS NOT NULL)::numeric
            / COUNT(DISTINCT qq.id),
            3
        )
    END                                              AS strike_rate,
    COALESCE(SUM(qq.sell_ex_tax), 0)                 AS total_quote_value,
    ROUND(AVG(qq.sell_ex_tax), 2)                    AS avg_quote_value,
    COALESCE(SUM(j.retail_sale), 0)                  AS total_job_value,
    ROUND(AVG(j.margin_pct), 2)                      AS avg_margin_pct,
    MAX(qq.date_created)                             AS most_recent_quote_date,
    MAX(j.accepted_date)                             AS most_recent_job_date,
    -- capability_count: length of qb_capabilities_used text (comma-separated)
    CASE
        WHEN cc.qb_capabilities_used IS NULL OR cc.qb_capabilities_used = '' THEN 0
        ELSE array_length(string_to_array(cc.qb_capabilities_used, ','), 1)
    END                                              AS capability_count
FROM customer_contacts cc
LEFT JOIN qb_quotes qq
    ON lower(cc.email_address) = lower(qq.contact_email)
    AND cc.client_id = qq.client_id
LEFT JOIN qb_jobs j
    ON qq.quote_no = j.quote_no
    AND qq.client_id = j.client_id
GROUP BY cc.id, cc.client_id, cc.qb_capabilities_used;


-- ═══════════════════════════════════════════════════════════════════════════
-- VIEW 2: contact_email_metrics (MATERIALIZED)
-- Per-contact aggregated email engagement metrics.
-- Materialized because the joins across email_contact_links (462K rows),
-- emails (272K rows), and email_response_metrics (55K rows) are expensive.
--
-- email_contact_links.role values:
--   'sender' = this contact sent the email → INBOUND to the AM
--   'to'/'cc' = this contact received the email → OUTBOUND from the AM
-- ═══════════════════════════════════════════════════════════════════════════

CREATE MATERIALIZED VIEW IF NOT EXISTS contact_email_metrics AS
SELECT
    ecl.contact_id,
    ecl.client_id,
    COUNT(*)                                         AS total_emails,
    COUNT(*) FILTER (WHERE ecl.role = 'sender')      AS inbound_emails,
    COUNT(*) FILTER (WHERE ecl.role IN ('to', 'cc')) AS outbound_emails,
    COUNT(DISTINCT e.canonical_thread_id)            AS unique_threads,
    ROUND(
        AVG(erm.response_time_seconds) FILTER (
            WHERE erm.response_time_seconds IS NOT NULL
              AND erm.is_auto_reply = false
        ) / 3600.0,
        2
    )                                                AS avg_response_time_hours,
    MAX(e.received_date)                             AS last_email_date,
    MIN(e.received_date)                             AS first_email_date,
    EXTRACT(DAY FROM (NOW() - MAX(e.received_date)))::int
                                                     AS days_since_last_email,
    COUNT(*) FILTER (
        WHERE e.received_date >= NOW() - INTERVAL '30 days'
    )                                                AS email_velocity_30d,
    COUNT(*) FILTER (
        WHERE e.received_date >= NOW() - INTERVAL '90 days'
    )                                                AS email_velocity_90d
FROM email_contact_links ecl
JOIN emails e ON ecl.email_id = e.id
LEFT JOIN email_response_metrics erm
    ON erm.responder_contact_id = ecl.contact_id
    AND erm.email_id = ecl.email_id
WHERE ecl.contact_id IS NOT NULL
GROUP BY ecl.contact_id, ecl.client_id;

-- Unique index required for REFRESH MATERIALIZED VIEW CONCURRENTLY
CREATE UNIQUE INDEX IF NOT EXISTS idx_contact_email_metrics_contact_id
    ON contact_email_metrics(contact_id);

-- Additional index for client-scoped queries
CREATE INDEX IF NOT EXISTS idx_contact_email_metrics_client_id
    ON contact_email_metrics(client_id);


-- ═══════════════════════════════════════════════════════════════════════════
-- Refresh function for the materialized view.
-- Called by external cron via POST /internal/jobs/refresh-persona-metrics
-- and after each QB sync completes.
-- ═══════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION refresh_contact_email_metrics()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY contact_email_metrics;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

GRANT EXECUTE ON FUNCTION refresh_contact_email_metrics() TO authenticated;


-- ═══════════════════════════════════════════════════════════════════════════
-- VIEW 3: contact_persona
-- The unified "persona" combining quote metrics, email metrics, and
-- QB enrichment into a single per-contact intelligence view.
--
-- ─── Persona Classification Logic ───
-- Based on email recency (days_since_last_email), quote history, and
-- strike rate. Categories:
--
--   'champion'           — ≥5 quotes, strike_rate ≥ 0.3, active emails (≤90d)
--   'active_relationship' — regular email engagement (≤90d), some quote activity
--   'prospect'           — ≤2 quotes, first email within last 180d, no acceptances
--   'inactive_buyer'     — has quote history but no recent emails (>90d)
--   'dormant'            — no emails in 180+ days AND no quotes in last year
--   'unknown'            — insufficient data (no emails AND no quotes)
--
-- ─── Engagement Score (0-100) ───
-- Composite weighted score:
--   Email velocity component  (30%): 0-100 based on email_velocity_30d
--     0 emails/30d = 0, 1-2 = 25, 3-5 = 50, 6-15 = 75, 16+ = 100
--   Recency component         (30%): 0-100 based on days_since_last_email
--     0-7d = 100, 8-30d = 75, 31-90d = 50, 91-180d = 25, 180+ = 0
--   Quote activity component  (40%): 0-100 based on quote_count + strike_rate
--     0 quotes = 0, 1-2 + no acceptance = 20, 1-2 + acceptance = 40,
--     3-9 + acceptance = 60, 10+ = 80, 10+ with strike_rate ≥ 0.3 = 100
-- ═══════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE VIEW contact_persona AS
SELECT
    cc.id                          AS contact_id,
    cc.email_address               AS email,
    cc.full_name                   AS name,
    cc.customer_company_id         AS company_id,
    co.company_name,
    co.industry,
    co.qb_tier,
    co.qb_customer_type            AS customer_type,
    cc.seniority_level             AS seniority,
    cc.is_primary_contact,
    cc.client_id,

    -- Quote metrics (from contact_quote_metrics view)
    COALESCE(cqm.quote_count, 0)          AS quote_count,
    COALESCE(cqm.accepted_quote_count, 0) AS accepted_quote_count,
    cqm.strike_rate,
    COALESCE(cqm.total_quote_value, 0)    AS total_quote_value,
    cqm.avg_quote_value,
    COALESCE(cqm.total_job_value, 0)      AS total_job_value,
    cqm.avg_margin_pct,
    cqm.most_recent_quote_date,
    cqm.most_recent_job_date,
    COALESCE(cqm.capability_count, 0)     AS capability_count,

    -- Email metrics (from contact_email_metrics materialized view)
    COALESCE(cem.total_emails, 0)         AS email_total,
    COALESCE(cem.inbound_emails, 0)       AS email_inbound,
    COALESCE(cem.outbound_emails, 0)      AS email_outbound,
    COALESCE(cem.unique_threads, 0)       AS email_unique_threads,
    cem.avg_response_time_hours            AS email_avg_response_time_hours,
    cem.last_email_date                    AS email_last_date,
    cem.first_email_date                   AS email_first_date,
    cem.days_since_last_email              AS email_days_since_last,
    COALESCE(cem.email_velocity_30d, 0)   AS email_velocity_30d,
    COALESCE(cem.email_velocity_90d, 0)   AS email_velocity_90d,

    -- ─── Persona Classification ───
    CASE
        -- Champion: heavy quoter, decent strike rate, recently active
        WHEN COALESCE(cqm.quote_count, 0) >= 5
             AND COALESCE(cqm.strike_rate, 0) >= 0.3
             AND COALESCE(cem.days_since_last_email, 999) <= 90
            THEN 'champion'

        -- Active relationship: regular email engagement, some quote activity
        WHEN COALESCE(cem.days_since_last_email, 999) <= 90
             AND (COALESCE(cqm.quote_count, 0) > 0 OR COALESCE(cem.total_emails, 0) >= 5)
            THEN 'active_relationship'

        -- Prospect: few/no quotes, recent first contact, no acceptances yet
        WHEN COALESCE(cqm.quote_count, 0) <= 2
             AND COALESCE(cqm.accepted_quote_count, 0) = 0
             AND cem.first_email_date >= NOW() - INTERVAL '180 days'
            THEN 'prospect'

        -- Inactive buyer: has quote history but gone quiet
        WHEN COALESCE(cqm.quote_count, 0) > 0
             AND COALESCE(cem.days_since_last_email, 999) > 90
            THEN 'inactive_buyer'

        -- Dormant: no emails in 180+ days and no recent quotes
        WHEN COALESCE(cem.days_since_last_email, 999) > 180
             AND (cqm.most_recent_quote_date IS NULL
                  OR cqm.most_recent_quote_date < CURRENT_DATE - INTERVAL '365 days')
            THEN 'dormant'

        -- Unknown: insufficient data
        ELSE 'unknown'
    END AS persona_classification,

    -- ─── Engagement Score (0-100) ───
    LEAST(100, GREATEST(0, (
        -- Email velocity component (30%)
        0.30 * (CASE
            WHEN COALESCE(cem.email_velocity_30d, 0) >= 16 THEN 100
            WHEN COALESCE(cem.email_velocity_30d, 0) >= 6  THEN 75
            WHEN COALESCE(cem.email_velocity_30d, 0) >= 3  THEN 50
            WHEN COALESCE(cem.email_velocity_30d, 0) >= 1  THEN 25
            ELSE 0
        END)
        +
        -- Recency component (30%)
        0.30 * (CASE
            WHEN COALESCE(cem.days_since_last_email, 999) <= 7   THEN 100
            WHEN COALESCE(cem.days_since_last_email, 999) <= 30  THEN 75
            WHEN COALESCE(cem.days_since_last_email, 999) <= 90  THEN 50
            WHEN COALESCE(cem.days_since_last_email, 999) <= 180 THEN 25
            ELSE 0
        END)
        +
        -- Quote activity component (40%)
        0.40 * (CASE
            WHEN COALESCE(cqm.quote_count, 0) >= 10
                 AND COALESCE(cqm.strike_rate, 0) >= 0.3        THEN 100
            WHEN COALESCE(cqm.quote_count, 0) >= 10             THEN 80
            WHEN COALESCE(cqm.quote_count, 0) >= 3
                 AND COALESCE(cqm.accepted_quote_count, 0) > 0  THEN 60
            WHEN COALESCE(cqm.quote_count, 0) >= 1
                 AND COALESCE(cqm.accepted_quote_count, 0) > 0  THEN 40
            WHEN COALESCE(cqm.quote_count, 0) >= 1              THEN 20
            ELSE 0
        END)
    )))::int AS engagement_score

FROM customer_contacts cc
LEFT JOIN customer_companies co
    ON cc.customer_company_id = co.id
LEFT JOIN contact_quote_metrics cqm
    ON cc.id = cqm.contact_id
LEFT JOIN contact_email_metrics cem
    ON cc.id = cem.contact_id;


-- ═══════════════════════════════════════════════════════════════════════════
-- VIEW 4: company_contact_summary
-- Per-company rolled-up contact summary for the company profile page.
-- ═══════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE VIEW company_contact_summary AS
SELECT
    cp.company_id,
    cp.company_name,
    cp.client_id,
    COUNT(*)                                                    AS total_contacts,
    -- Primary contact (from customer_companies.primary_contact_id)
    co.primary_contact_id,
    (SELECT full_name FROM customer_contacts
     WHERE id = co.primary_contact_id)                          AS primary_contact_name,
    COUNT(*) FILTER (
        WHERE cp.persona_classification = 'champion'
    )                                                           AS champions_count,
    COUNT(*) FILTER (
        WHERE cp.persona_classification = 'prospect'
    )                                                           AS prospects_count,
    COUNT(*) FILTER (
        WHERE cp.persona_classification = 'dormant'
    )                                                           AS dormant_count,
    COUNT(*) FILTER (
        WHERE cp.persona_classification = 'active_relationship'
    )                                                           AS active_count,
    COUNT(*) FILTER (
        WHERE cp.persona_classification = 'inactive_buyer'
    )                                                           AS inactive_buyers_count,
    ROUND(AVG(cp.strike_rate) FILTER (
        WHERE cp.strike_rate IS NOT NULL
    ), 3)                                                       AS avg_strike_rate,
    SUM(cp.total_quote_value)                                   AS total_quote_value,
    ROUND(AVG(cp.engagement_score), 0)                          AS avg_engagement_score
FROM contact_persona cp
LEFT JOIN customer_companies co ON cp.company_id = co.id
WHERE cp.company_id IS NOT NULL
GROUP BY cp.company_id, cp.company_name, cp.client_id,
         co.primary_contact_id;


-- ═══════════════════════════════════════════════════════════════════════════
-- VIEW 5: industry_benchmarks
-- Per-industry average metrics for benchmarking contacts/companies
-- against their industry peers.
-- ═══════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE VIEW industry_benchmarks AS
SELECT
    cp.industry,
    cp.client_id,
    COUNT(DISTINCT cp.contact_id)                               AS contact_count,
    ROUND(AVG(cp.strike_rate) FILTER (
        WHERE cp.strike_rate IS NOT NULL
    ), 3)                                                       AS avg_strike_rate,
    ROUND(AVG(cp.avg_quote_value) FILTER (
        WHERE cp.avg_quote_value IS NOT NULL
    ), 2)                                                       AS avg_quote_value,
    ROUND(AVG(cp.email_velocity_30d), 1)                        AS avg_email_velocity_30d,
    ROUND(AVG(cp.engagement_score), 0)                          AS avg_engagement_score
FROM contact_persona cp
WHERE cp.industry IS NOT NULL
  AND cp.industry != 'Not Selected'
GROUP BY cp.industry, cp.client_id
HAVING COUNT(DISTINCT cp.contact_id) >= 3;


-- ═══════════════════════════════════════════════════════════════════════════
-- GRANTS: ensure PostgREST (authenticated role) can read the views
-- ═══════════════════════════════════════════════════════════════════════════

GRANT SELECT ON contact_quote_metrics    TO authenticated;
GRANT SELECT ON contact_email_metrics    TO authenticated;
GRANT SELECT ON contact_persona          TO authenticated;
GRANT SELECT ON company_contact_summary  TO authenticated;
GRANT SELECT ON industry_benchmarks      TO authenticated;


-- ═══════════════════════════════════════════════════════════════════════════
-- NOTE: Refresh schedule for contact_email_metrics
--
-- pg_cron is NOT available on this Supabase instance.
-- The materialized view is refreshed via:
--   1. External cron calling POST /api/internal/jobs/refresh-persona-metrics
--   2. After each QB sync completes (added to QB sync flow)
--
-- Recommended cron schedule: daily at 03:00 UTC
-- ═══════════════════════════════════════════════════════════════════════════
