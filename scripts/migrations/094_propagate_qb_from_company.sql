-- ============================================================================
-- Migration 094: Add Pass 3 to batch_propagate_qb_data_to_contacts
-- ============================================================================
--
-- Pass 3 inherits qb_customer_type and qb_tier from the parent company
-- for contacts that Pass 1 (qb_unique_emails) and Pass 2 (qb_contacts)
-- didn't reach. This covers contacts at QB-matched companies whose email
-- isn't in qb_unique_emails and who have no qb_contacts FK match.
--
-- ~4,896 contacts are in this bucket: their company has qb_customer_id
-- but the contact itself has no direct QB link.
-- ============================================================================

CREATE OR REPLACE FUNCTION batch_propagate_qb_data_to_contacts(
    p_client_id UUID
)
RETURNS INTEGER
LANGUAGE plpgsql AS $$
DECLARE
    pass1_count INTEGER := 0;
    pass2_count INTEGER := 0;
    pass3_count INTEGER := 0;
BEGIN
    -- Pass 1: qb_unique_emails → customer_contacts by email
    UPDATE customer_contacts cc
    SET qb_customer_type     = COALESCE(ue.customer_type, cc.qb_customer_type),
        qb_capabilities_used = COALESCE(NULLIF(NULLIF(ue.capabilities_used, ''), 'Not Selected'), cc.qb_capabilities_used),
        qb_processes_used    = COALESCE(NULLIF(NULLIF(ue.processes_used, ''), 'Not Selected'), cc.qb_processes_used),
        qb_linked_at         = NOW()
    FROM qb_unique_emails ue
    WHERE LOWER(cc.email_address) = LOWER(ue.email)
      AND cc.client_id = p_client_id
      AND ue.client_id = p_client_id
      AND ue.hide = FALSE
      AND ue.email_invalid = FALSE
      AND ue.email IS NOT NULL
      AND ue.email <> '';

    GET DIAGNOSTICS pass1_count = ROW_COUNT;

    -- Pass 2: qb_contacts → customer_contacts via matched_contact_id FK
    UPDATE customer_contacts cc
    SET qb_quotes_count         = COALESCE(qc.quotes_accepted_count, cc.qb_quotes_count),
        qb_last_quote_date      = COALESCE(qc.most_recent_quote_date, cc.qb_last_quote_date),
        qb_contact_recency_days = COALESCE(qc.contact_recency_days, cc.qb_contact_recency_days)
    FROM qb_contacts qc
    WHERE qc.matched_contact_id = cc.id
      AND qc.client_id = p_client_id
      AND qc.matched_contact_id IS NOT NULL;

    GET DIAGNOSTICS pass2_count = ROW_COUNT;

    -- Pass 3: Inherit qb_customer_type and qb_tier from parent company
    -- for EXTERNAL PERSON contacts not reached by Pass 1 or Pass 2.
    -- Excludes: internal contacts (client's own employees) and
    -- shared/automated/mailing_list addresses (no individual insight value).
    UPDATE customer_contacts cc
    SET qb_customer_type = COALESCE(co.qb_customer_type, cc.qb_customer_type),
        qb_tier          = COALESCE(co.qb_tier, cc.qb_tier),
        qb_total_revenue = COALESCE(co.qb_total_revenue, cc.qb_total_revenue),
        qb_linked_at     = NOW()
    FROM customer_companies co
    WHERE cc.customer_company_id = co.id
      AND cc.client_id = p_client_id
      AND co.qb_customer_id IS NOT NULL
      AND cc.qb_linked_at IS NULL
      AND COALESCE(cc.contact_type, 'person') NOT IN ('internal', 'shared', 'automated', 'mailing_list')
      AND NOT EXISTS (
          SELECT 1 FROM internal_domains id
          WHERE id.client_id = p_client_id
            AND id.domain = SPLIT_PART(cc.email_address, '@', 2)
      );

    GET DIAGNOSTICS pass3_count = ROW_COUNT;

    RETURN pass1_count + pass2_count + pass3_count;
END;
$$;

GRANT EXECUTE ON FUNCTION batch_propagate_qb_data_to_contacts(UUID) TO anon, authenticated;

COMMENT ON FUNCTION batch_propagate_qb_data_to_contacts(UUID) IS
  'Propagate QB signals to customer_contacts via three passes: '
  '(1) qb_unique_emails by email, (2) qb_contacts by FK, '
  '(3) inherit company qb_customer_type/qb_tier for remaining external person contacts. '
  'Pass 3 excludes internal, shared, automated, and mailing_list contact types. '
  'Extended in migration 094 to add Pass 3 with contact-type guards.';
