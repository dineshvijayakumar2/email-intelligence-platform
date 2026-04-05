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

-- 2. Update company email counts (processes in batches to avoid statement timeout)
CREATE OR REPLACE FUNCTION update_company_email_counts_from_junction(p_client_id UUID)
RETURNS INTEGER
LANGUAGE plpgsql AS $$
DECLARE
    company_rec RECORD;
    updated INTEGER := 0;
    total_count INTEGER;
    outbound_count INTEGER;
    contact_cnt INTEGER;
    first_dt TIMESTAMPTZ;
    last_dt TIMESTAMPTZ;
BEGIN
    FOR company_rec IN
        SELECT DISTINCT company_id FROM email_contact_links
        WHERE client_id = p_client_id AND company_id IS NOT NULL
    LOOP
        SELECT
            COUNT(DISTINCT ecl.email_id),
            COUNT(DISTINCT ecl.email_id) FILTER (WHERE e.is_outbound = true),
            COUNT(DISTINCT ecl.contact_id),
            MIN(e.sent_date),
            MAX(e.sent_date)
        INTO total_count, outbound_count, contact_cnt, first_dt, last_dt
        FROM email_contact_links ecl
        JOIN emails e ON e.id = ecl.email_id
        WHERE ecl.company_id = company_rec.company_id
          AND ecl.client_id = p_client_id;

        UPDATE customer_companies
        SET total_emails = total_count,
            total_outbound = outbound_count,
            total_inbound = total_count - outbound_count,
            contact_count = contact_cnt,
            first_contact_date = first_dt,
            last_contact_date = last_dt
        WHERE id = company_rec.company_id
          AND client_id = p_client_id;

        updated := updated + 1;
    END LOOP;

    RETURN updated;
END;
$$;
