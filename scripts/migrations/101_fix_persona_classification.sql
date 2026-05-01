-- ============================================================================
-- Migration 101: Fix persona classification logic
-- ============================================================================
-- Issue 1: Peter Howie has 80 accepted quotes / $610K in jobs but is
--          classified "active_relationship" not "champion". The champion
--          rule requires quote_count >= 5 AND strike_rate >= 0.3 — Peter
--          has strike_rate 0.156, so he's excluded despite massive volume.
--          Fix: champion also triggers on high accepted count or job value.
--
-- Issue 2: "active_relationship" is too broad — 15 to 92 engagement_score
--          contacts all get the same label. Added "active_buyer" (has
--          conversions + recent emails) and "warm_lead" (engaged but no
--          quotes) to segment more usefully.
--
-- Issue 3: Shared mailboxes (accounts@, info@) get persona labels.
--          Fix: non-person contacts get 'shared_mailbox' classification
--          so UI can filter them, but they stay in the view for count
--          purposes.
--
-- Note: contact_type column added on contact_persona so frontend can
-- filter shared contacts in/out.
-- ============================================================================

-- ─── Drop dependent views first, then recreate all ─────────────────────

DROP VIEW IF EXISTS industry_benchmarks CASCADE;
DROP VIEW IF EXISTS company_contact_summary CASCADE;
DROP VIEW IF EXISTS contact_persona CASCADE;

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

    -- ─── Persona Classification (v2) ───
    CASE
        -- Non-person contacts: label as shared_mailbox for UI filtering
        WHEN cc.contact_type NOT IN ('person', 'unknown')
            THEN 'shared_mailbox'

        -- Champion: significant conversion history, recently active
        -- Triggers on high strike rate, high accepted count, OR high job value
        WHEN (
                (COALESCE(cqm.quote_count, 0) >= 5 AND COALESCE(cqm.strike_rate, 0) >= 0.3)
                OR COALESCE(cqm.accepted_quote_count, 0) >= 10
                OR COALESCE(cqm.total_job_value, 0) >= 50000
             )
             AND COALESCE(cem.days_since_last_email, 999) <= 180
            THEN 'champion'

        -- Active buyer: has conversions + recent emails (but below champion threshold)
        WHEN COALESCE(cqm.accepted_quote_count, 0) > 0
             AND COALESCE(cem.days_since_last_email, 999) <= 90
            THEN 'active_buyer'

        -- Active relationship: regular email engagement + quote activity (no conversions yet)
        WHEN COALESCE(cem.days_since_last_email, 999) <= 90
             AND COALESCE(cqm.quote_count, 0) > 0
            THEN 'active_relationship'

        -- Warm lead: recent email engagement but no quotes yet
        WHEN COALESCE(cem.days_since_last_email, 999) <= 90
             AND COALESCE(cem.total_emails, 0) >= 5
            THEN 'warm_lead'

        -- Prospect: few/no quotes, recent first contact, no acceptances yet
        WHEN COALESCE(cqm.quote_count, 0) <= 2
             AND COALESCE(cqm.accepted_quote_count, 0) = 0
             AND cem.first_email_date >= NOW() - INTERVAL '180 days'
            THEN 'prospect'

        -- Inactive buyer: has conversion history but gone quiet
        WHEN COALESCE(cqm.accepted_quote_count, 0) > 0
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
    -- Same weighting: 30% velocity + 30% recency + 40% quote activity
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


-- ─── Recreate company_contact_summary (depends on contact_persona) ─────
-- Only counts person contacts for persona stats, but total_contacts includes all.

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


-- ─── Recreate industry_benchmarks (person contacts only) ───────────────

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


-- ─── Grants ────────────────────────────────────────────────────────────

GRANT SELECT ON contact_persona          TO authenticated;
GRANT SELECT ON company_contact_summary  TO authenticated;
GRANT SELECT ON industry_benchmarks      TO authenticated;
