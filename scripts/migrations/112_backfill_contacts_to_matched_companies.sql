-- ============================================================================
-- Migration 112: Backfill contacts/emails onto QB-matched companies
-- ============================================================================
-- Problem: After matching writes qb_customers.matched_company_id, no step
-- links the QB customer's contacts to the matched SB company, and existing
-- contacts often have NULL company_id in emails/email_contact_links tables.
-- Result: 2,282+ companies show total_emails=0 despite having contacts.
--
-- This RPC runs 3 passes:
--   A: Link unlinked contacts (customer_company_id IS NULL) to matched company
--   B: Backfill emails.customer_company_id from linked contacts
--   C: Backfill email_contact_links.company_id from linked contacts
-- ============================================================================

CREATE OR REPLACE FUNCTION backfill_contacts_to_matched_companies(p_client_id UUID)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET statement_timeout = '120s'
AS $$
DECLARE
    pass_a_count INTEGER := 0;
    pass_b_count INTEGER := 0;
    pass_c_count INTEGER := 0;
BEGIN
    -- Pass A: Link unlinked contacts to matched companies via QB email chain
    -- qb_customers (matched) → qb_unique_emails → customer_contacts (NULL company)
    UPDATE customer_contacts cc
    SET customer_company_id = sub.matched_company_id
    FROM (
        SELECT DISTINCT ON (cont.id)
            cont.id AS contact_id,
            qc.matched_company_id
        FROM qb_customers qc
        JOIN qb_unique_emails que
            ON que.client_id = p_client_id
            AND TRIM(que.qb_customer_id) = TRIM(qc.qb_record_id)
            AND que.hide = FALSE
            AND que.email_invalid = FALSE
        JOIN customer_contacts cont
            ON cont.client_id = p_client_id
            AND LOWER(cont.email_address) = LOWER(que.email)
        WHERE qc.client_id = p_client_id
            AND qc.matched_company_id IS NOT NULL
            AND cont.customer_company_id IS NULL
        ORDER BY cont.id, qc.total_invoiced DESC NULLS LAST
    ) sub
    WHERE cc.id = sub.contact_id
      AND cc.client_id = p_client_id;

    GET DIAGNOSTICS pass_a_count = ROW_COUNT;

    -- Pass B: Backfill emails.customer_company_id for contacts that have a company
    -- but whose emails still have NULL customer_company_id
    UPDATE emails e
    SET customer_company_id = cc.customer_company_id
    FROM customer_contacts cc
    WHERE e.customer_contact_id = cc.id
      AND e.client_id = p_client_id
      AND cc.client_id = p_client_id
      AND cc.customer_company_id IS NOT NULL
      AND e.customer_company_id IS NULL;

    GET DIAGNOSTICS pass_b_count = ROW_COUNT;

    -- Pass C: Backfill email_contact_links.company_id for contacts that have a company
    -- but whose junction records still have NULL company_id
    UPDATE email_contact_links ecl
    SET company_id = cc.customer_company_id
    FROM customer_contacts cc
    WHERE ecl.contact_id = cc.id
      AND ecl.client_id = p_client_id
      AND cc.client_id = p_client_id
      AND cc.customer_company_id IS NOT NULL
      AND ecl.company_id IS NULL;

    GET DIAGNOSTICS pass_c_count = ROW_COUNT;

    RETURN jsonb_build_object(
        'contacts_linked', pass_a_count,
        'emails_backfilled', pass_b_count,
        'junction_backfilled', pass_c_count
    );
END;
$$;

GRANT EXECUTE ON FUNCTION backfill_contacts_to_matched_companies(UUID) TO anon, authenticated;
