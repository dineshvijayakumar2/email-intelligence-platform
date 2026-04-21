-- =============================================================================
-- Migration 093: Contact Deal Activity view
-- Date: 2026-04-21
-- Purpose: Aggregate thread_qb_links per contact to surface deal funnels,
--          open pipeline value, and conversion metrics on the contact profile.
--          Joins: customer_contacts → thread_status → thread_qb_links → qb_quotes/qb_jobs
-- =============================================================================

-- View: contact_deal_activity
-- One row per contact that has at least one thread. Contacts with no threads
-- are excluded (they have no deal activity to report).

CREATE OR REPLACE VIEW contact_deal_activity AS
WITH thread_links AS (
  SELECT
    ts.customer_contact_id AS contact_id,
    m.client_id,
    ts.canonical_thread_id,
    tql.id              AS link_id,
    tql.link_type,
    tql.qb_record_id,
    tql.qb_reference,
    tql.source,
    tql.confidence
  FROM thread_status ts
  JOIN mailboxes m ON m.id = ts.mailbox_id
  LEFT JOIN thread_qb_links tql
    ON ts.canonical_thread_id::text = tql.canonical_thread_id
   AND m.client_id = tql.client_id
  WHERE ts.customer_contact_id IS NOT NULL
),

-- Deduplicate quotes: same quote may be linked from multiple threads
distinct_quotes AS (
  SELECT DISTINCT ON (tl.contact_id, tl.client_id, qq.quote_no)
    tl.contact_id,
    tl.client_id,
    qq.quote_no,
    qq.sell_ex_tax,
    qq.has_job,
    qq.date_created,
    qq.date_accepted
  FROM thread_links tl
  JOIN qb_quotes qq
    ON tl.qb_record_id = qq.qb_record_id
   AND tl.client_id   = qq.client_id
  WHERE tl.link_type = 'quote'
),

quote_summary AS (
  SELECT
    contact_id,
    client_id,
    COUNT(*)                                      AS linked_quotes,
    COUNT(*) FILTER (WHERE has_job)                AS converted_quotes,
    COUNT(*) FILTER (WHERE NOT has_job)             AS open_quotes,
    COALESCE(SUM(sell_ex_tax) FILTER (WHERE NOT has_job), 0) AS open_pipeline_value,
    COALESCE(SUM(sell_ex_tax) FILTER (WHERE has_job), 0)     AS converted_value,
    MAX(date_created)                              AS latest_quote_date
  FROM distinct_quotes
  GROUP BY contact_id, client_id
),

-- Deduplicate jobs
distinct_jobs AS (
  SELECT DISTINCT ON (tl.contact_id, tl.client_id, qj.job_no)
    tl.contact_id,
    tl.client_id,
    qj.job_no,
    qj.retail_sale,
    qj.invoiced_margin,
    qj.accepted_date
  FROM thread_links tl
  JOIN qb_jobs qj
    ON tl.qb_record_id = qj.qb_record_id
   AND tl.client_id   = qj.client_id
  WHERE tl.link_type = 'job'
),

job_summary AS (
  SELECT
    contact_id,
    client_id,
    COUNT(*)                           AS linked_jobs,
    COALESCE(SUM(retail_sale), 0)      AS linked_job_revenue,
    COALESCE(SUM(invoiced_margin), 0)  AS linked_margin,
    MAX(accepted_date)                 AS latest_job_date
  FROM distinct_jobs
  GROUP BY contact_id, client_id
)

SELECT
  tl.contact_id,
  tl.client_id,
  -- Thread funnel
  COUNT(DISTINCT tl.canonical_thread_id)                                         AS total_threads,
  COUNT(DISTINCT tl.canonical_thread_id) FILTER (WHERE tl.link_id IS NOT NULL)   AS linked_threads,
  -- Link source breakdown
  COUNT(tl.link_id) FILTER (WHERE tl.source = 'regex')   AS regex_links,
  COUNT(tl.link_id) FILTER (WHERE tl.source = 'ai')      AS ai_links,
  COUNT(tl.link_id) FILTER (WHERE tl.source = 'manual')  AS manual_links,
  -- Quote pipeline
  COALESCE(qs.linked_quotes, 0)       AS linked_quotes,
  COALESCE(qs.converted_quotes, 0)    AS converted_quotes,
  COALESCE(qs.open_quotes, 0)         AS open_quotes,
  COALESCE(qs.open_pipeline_value, 0) AS open_pipeline_value,
  COALESCE(qs.converted_value, 0)     AS converted_value,
  qs.latest_quote_date,
  -- Job outcomes
  COALESCE(js.linked_jobs, 0)         AS linked_jobs,
  COALESCE(js.linked_job_revenue, 0)  AS linked_job_revenue,
  COALESCE(js.linked_margin, 0)       AS linked_margin,
  js.latest_job_date
FROM thread_links tl
LEFT JOIN quote_summary qs ON tl.contact_id = qs.contact_id AND tl.client_id = qs.client_id
LEFT JOIN job_summary   js ON tl.contact_id = js.contact_id AND tl.client_id = js.client_id
GROUP BY
  tl.contact_id, tl.client_id,
  qs.linked_quotes, qs.converted_quotes, qs.open_quotes,
  qs.open_pipeline_value, qs.converted_value, qs.latest_quote_date,
  js.linked_jobs, js.linked_job_revenue, js.linked_margin, js.latest_job_date;

-- Grant access
GRANT SELECT ON contact_deal_activity TO authenticated, service_role;
