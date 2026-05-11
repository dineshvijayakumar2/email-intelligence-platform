-- Migration 110: Make company_name case-insensitive via CITEXT.
--
-- Root cause: PostgreSQL TEXT unique constraint is case-sensitive, allowing
-- "HH Global" and "Hhglobal" as separate rows. CITEXT makes the existing
-- unique constraint case-insensitive, preventing duplicates at DB level.
-- PostgREST's on_conflict='client_id,company_name' continues to work.
--
-- Must drop and recreate all views that depend on customer_companies.company_name.

CREATE EXTENSION IF NOT EXISTS citext;

-- Drop dependent views (reverse dependency order)
DROP VIEW IF EXISTS industry_benchmarks CASCADE;
DROP VIEW IF EXISTS company_contact_summary CASCADE;
DROP VIEW IF EXISTS contact_persona CASCADE;
DROP VIEW IF EXISTS customer_industry_segments CASCADE;
DROP VIEW IF EXISTS customer_engagement_summary CASCADE;

-- Alter the column type
ALTER TABLE customer_companies ALTER COLUMN company_name TYPE citext;

-- Recreate customer_engagement_summary
CREATE OR REPLACE VIEW customer_engagement_summary AS
SELECT
    cc.id,
    cc.company_name,
    cc.client_id,
    c.client_name,
    cc.industry,
    cc.first_contact_date,
    cc.last_contact_date,
    cc.total_emails,
    cc.total_inbound,
    cc.total_outbound,
    COUNT(DISTINCT ct.id) as contact_count,
    CASE
        WHEN cc.last_contact_date > NOW() - INTERVAL '30 days' THEN 'active'
        WHEN cc.last_contact_date > NOW() - INTERVAL '90 days' THEN 'quiet'
        ELSE 'at_risk'
    END as engagement_status,
    cc.created_at
FROM customer_companies cc
JOIN clients c ON cc.client_id = c.id
LEFT JOIN customer_contacts ct ON ct.customer_company_id = cc.id
GROUP BY cc.id, cc.company_name, cc.client_id, c.client_name, cc.industry,
         cc.first_contact_date, cc.last_contact_date, cc.total_emails,
         cc.total_inbound, cc.total_outbound, cc.created_at;

-- Recreate customer_industry_segments
CREATE OR REPLACE VIEW customer_industry_segments AS
SELECT
    cc.client_id,
    cc.industry,
    COUNT(DISTINCT cc.id)                                           AS company_count,
    COUNT(DISTINCT ct.id)                                           AS contact_count,
    COALESCE(SUM(cc.qb_total_revenue), 0)                           AS total_revenue,
    CASE WHEN COUNT(DISTINCT cc.id) > 0
         THEN COALESCE(SUM(cc.qb_total_revenue), 0) / COUNT(DISTINCT cc.id)
         ELSE 0
    END                                                             AS avg_revenue_per_company,
    COUNT(DISTINCT cc.id) FILTER (WHERE cc.qb_customer_type LIKE 'Active%')          AS active_companies,
    COUNT(DISTINCT cc.id) FILTER (WHERE cc.qb_tier IN ('Level 4 Enterprise', 'Level 3 Key Account')) AS enterprise_companies,
    COUNT(DISTINCT cc.id) FILTER (WHERE cc.qb_customer_type = 'Lapsed')              AS lapsed_companies
FROM customer_companies cc
LEFT JOIN customer_contacts ct ON ct.customer_company_id = cc.id
WHERE cc.industry IS NOT NULL
  AND cc.industry <> ''
  AND cc.industry <> 'Not Selected'
GROUP BY cc.client_id, cc.industry;

-- Recreate contact_persona (from migration 101)
CREATE VIEW contact_persona AS
SELECT
    cc.id                          AS contact_id,
    cc.email_address               AS email,
    cc.full_name                   AS name,
    cc.customer_company_id         AS company_id,
    co.company_name,
    co.industry,
    co.qb_tier,
    co.qb_customer_type            AS customer_type,
    cc.contact_type,
    cc.seniority_level             AS seniority,
    cc.is_primary_contact,
    cc.client_id,
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
    CASE
        WHEN cc.contact_type NOT IN ('person', 'unknown')
            THEN 'shared_mailbox'
        WHEN (
                (COALESCE(cqm.quote_count, 0) >= 5 AND COALESCE(cqm.strike_rate, 0) >= 0.3)
                OR COALESCE(cqm.accepted_quote_count, 0) >= 10
                OR COALESCE(cqm.total_job_value, 0) >= 50000
             )
             AND COALESCE(cem.days_since_last_email, 999) <= 180
            THEN 'champion'
        WHEN COALESCE(cqm.accepted_quote_count, 0) > 0
             AND COALESCE(cem.days_since_last_email, 999) <= 90
            THEN 'active_buyer'
        WHEN COALESCE(cem.days_since_last_email, 999) <= 90
             AND COALESCE(cqm.quote_count, 0) > 0
            THEN 'active_relationship'
        WHEN COALESCE(cem.days_since_last_email, 999) <= 90
             AND COALESCE(cem.total_emails, 0) >= 5
            THEN 'warm_lead'
        WHEN COALESCE(cqm.quote_count, 0) <= 2
             AND COALESCE(cqm.accepted_quote_count, 0) = 0
             AND cem.first_email_date >= NOW() - INTERVAL '180 days'
            THEN 'prospect'
        WHEN COALESCE(cqm.accepted_quote_count, 0) > 0
             AND COALESCE(cem.days_since_last_email, 999) > 90
            THEN 'inactive_buyer'
        WHEN COALESCE(cem.days_since_last_email, 999) > 180
             AND (cqm.most_recent_quote_date IS NULL
                  OR cqm.most_recent_quote_date < CURRENT_DATE - INTERVAL '365 days')
            THEN 'dormant'
        ELSE 'unknown'
    END AS persona_classification,
    LEAST(100, GREATEST(0, (
        0.30 * (CASE
            WHEN COALESCE(cem.email_velocity_30d, 0) >= 16 THEN 100
            WHEN COALESCE(cem.email_velocity_30d, 0) >= 6  THEN 75
            WHEN COALESCE(cem.email_velocity_30d, 0) >= 3  THEN 50
            WHEN COALESCE(cem.email_velocity_30d, 0) >= 1  THEN 25
            ELSE 0
        END)
        +
        0.30 * (CASE
            WHEN COALESCE(cem.days_since_last_email, 999) <= 7   THEN 100
            WHEN COALESCE(cem.days_since_last_email, 999) <= 30  THEN 75
            WHEN COALESCE(cem.days_since_last_email, 999) <= 90  THEN 50
            WHEN COALESCE(cem.days_since_last_email, 999) <= 180 THEN 25
            ELSE 0
        END)
        +
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

-- Recreate company_contact_summary (depends on contact_persona)
CREATE VIEW company_contact_summary AS
SELECT
    cp.company_id,
    cp.company_name,
    cp.client_id,
    COUNT(*)                                                    AS total_contacts,
    COUNT(*) FILTER (
        WHERE cp.contact_type = 'person'
    )                                                           AS person_contacts,
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
        WHERE cp.persona_classification IN ('active_buyer', 'active_relationship')
    )                                                           AS active_count,
    COUNT(*) FILTER (
        WHERE cp.persona_classification = 'inactive_buyer'
    )                                                           AS inactive_buyers_count,
    COUNT(*) FILTER (
        WHERE cp.persona_classification = 'warm_lead'
    )                                                           AS warm_leads_count,
    ROUND(AVG(cp.strike_rate) FILTER (
        WHERE cp.strike_rate IS NOT NULL
    ), 3)                                                       AS avg_strike_rate,
    SUM(cp.total_quote_value)                                   AS total_quote_value,
    ROUND(AVG(cp.engagement_score) FILTER (
        WHERE cp.contact_type = 'person'
    ), 0)                                                       AS avg_engagement_score
FROM contact_persona cp
LEFT JOIN customer_companies co ON cp.company_id = co.id
WHERE cp.company_id IS NOT NULL
GROUP BY cp.company_id, cp.company_name, cp.client_id,
         co.primary_contact_id;

-- Recreate industry_benchmarks (depends on contact_persona)
CREATE VIEW industry_benchmarks AS
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
  AND cp.contact_type = 'person'
GROUP BY cp.industry, cp.client_id
HAVING COUNT(DISTINCT cp.contact_id) >= 3;

-- Restore security settings and grants
ALTER VIEW public.customer_engagement_summary SET (security_invoker = on);
ALTER VIEW public.customer_industry_segments SET (security_invoker = on);
ALTER VIEW public.contact_persona SET (security_invoker = on);
ALTER VIEW public.company_contact_summary SET (security_invoker = on);
ALTER VIEW public.industry_benchmarks SET (security_invoker = on);

GRANT SELECT ON customer_engagement_summary TO anon, authenticated;
GRANT SELECT ON customer_industry_segments TO anon, authenticated;
GRANT SELECT ON contact_persona TO authenticated;
GRANT SELECT ON company_contact_summary TO authenticated;
GRANT SELECT ON industry_benchmarks TO authenticated;
