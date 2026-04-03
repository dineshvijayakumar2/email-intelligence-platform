-- Migration 054: RPCs to update email counts from email_contact_links junction table
-- Updates stored counts on customer_contacts and customer_companies
-- using the many-to-many junction table (includes CC/BCC).

-- 1. Update contact email counts
CREATE OR REPLACE FUNCTION update_contact_email_counts_from_junction(p_client_id UUID)
RETURNS INTEGER
LANGUAGE plpgsql AS $$
DECLARE
    updated INTEGER := 0;
BEGIN
    WITH contact_counts AS (
        SELECT
            ecl.contact_id,
            COUNT(DISTINCT ecl.email_id) AS total_emails,
            COUNT(DISTINCT ecl.email_id) FILTER (WHERE e.is_outbound = true) AS sent,
            COUNT(DISTINCT ecl.email_id) FILTER (WHERE e.is_outbound = false OR e.is_outbound IS NULL) AS received
        FROM email_contact_links ecl
        JOIN emails e ON e.id = ecl.email_id
        WHERE ecl.client_id = p_client_id
          AND ecl.contact_id IS NOT NULL
        GROUP BY ecl.contact_id
    )
    UPDATE customer_contacts cc
    SET total_emails_sent = cc2.sent,
        total_emails_received = cc2.received
    FROM contact_counts cc2
    WHERE cc.id = cc2.contact_id
      AND cc.client_id = p_client_id;

    GET DIAGNOSTICS updated = ROW_COUNT;
    RETURN updated;
END;
$$;

-- 2. Update company email counts
CREATE OR REPLACE FUNCTION update_company_email_counts_from_junction(p_client_id UUID)
RETURNS INTEGER
LANGUAGE plpgsql AS $$
DECLARE
    updated INTEGER := 0;
BEGIN
    WITH company_counts AS (
        SELECT
            ecl.company_id,
            COUNT(DISTINCT ecl.email_id) AS total_emails,
            COUNT(DISTINCT ecl.email_id) FILTER (WHERE e.is_outbound = true) AS outbound,
            COUNT(DISTINCT ecl.email_id) FILTER (WHERE e.is_outbound = false OR e.is_outbound IS NULL) AS inbound,
            COUNT(DISTINCT ecl.contact_id) AS contact_count,
            MIN(e.sent_date) AS first_contact,
            MAX(e.sent_date) AS last_contact
        FROM email_contact_links ecl
        JOIN emails e ON e.id = ecl.email_id
        WHERE ecl.client_id = p_client_id
          AND ecl.company_id IS NOT NULL
        GROUP BY ecl.company_id
    )
    UPDATE customer_companies cc
    SET total_emails = cc2.total_emails,
        total_outbound = cc2.outbound,
        total_inbound = cc2.inbound,
        contact_count = cc2.contact_count,
        first_contact_date = cc2.first_contact,
        last_contact_date = cc2.last_contact
    FROM company_counts cc2
    WHERE cc.id = cc2.company_id
      AND cc.client_id = p_client_id;

    GET DIAGNOSTICS updated = ROW_COUNT;
    RETURN updated;
END;
$$;
