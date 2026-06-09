-- Migration 117: company email/contact aggregates from the CANONICAL assignment
-- (emails.customer_company_id + customer_contacts.customer_company_id), NOT the
-- divergent email_contact_links.company_id.
--
-- Why: email_contact_links.company_id is resolved per-participant (contact-FK ->
-- email_domains domain lookup) and systematically diverges from the email's primary
-- assignment. The old junction-based count (mig 054) under-counted ~588 companies whose
-- assigned emails' links resolved elsewhere, and INFLATED ~1159 companies with broker /
-- shared-domain spillover (e.g. emilyziz.com emails attributed to every end-customer).
-- Counting from customer_company_id makes total_emails match "emails assigned to this
-- company" (what the company email list shows after the paired endpoint fix).
--
-- Name kept as update_company_email_counts_from_junction for caller compatibility
-- (analytics backfill, migration runners); source is now the assignment, not the junction.
-- Set-based single UPDATE; companies with no assigned emails are correctly set to 0.
CREATE OR REPLACE FUNCTION update_company_email_counts_from_junction(p_client_id UUID)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    updated INTEGER := 0;
BEGIN
    WITH em AS (
        SELECT e.customer_company_id AS cid,
               COUNT(*) AS n,
               COUNT(*) FILTER (WHERE e.is_outbound = true) AS outb,
               MIN(e.sent_date) AS fdt,
               MAX(e.sent_date) AS ldt
        FROM emails e
        JOIN customer_companies c
          ON c.id = e.customer_company_id AND c.client_id = p_client_id
        WHERE e.customer_company_id IS NOT NULL
        GROUP BY e.customer_company_id
    ),
    ct AS (
        SELECT customer_company_id AS cid,
               COUNT(*) AS n,
               COUNT(*) FILTER (WHERE is_decision_maker) AS dm
        FROM customer_contacts
        WHERE client_id = p_client_id
        GROUP BY customer_company_id
    )
    UPDATE customer_companies cc
    SET total_emails        = COALESCE(em.n, 0),
        total_outbound      = COALESCE(em.outb, 0),
        total_inbound       = COALESCE(em.n, 0) - COALESCE(em.outb, 0),
        contact_count       = COALESCE(ct.n, 0),
        decision_maker_count = COALESCE(ct.dm, 0),
        first_contact_date  = em.fdt,
        last_contact_date   = em.ldt
    FROM customer_companies base
    LEFT JOIN em ON em.cid = base.id
    LEFT JOIN ct ON ct.cid = base.id
    WHERE cc.id = base.id
      AND base.client_id = p_client_id;

    GET DIAGNOSTICS updated = ROW_COUNT;
    RETURN updated;
END;
$$;
