-- =========================================================================
-- Sprint 2 Migration 002: Column Additions + Helper Functions
-- =========================================================================
-- Purpose: Add role + analytics columns to existing tables + SQL helper functions
-- Run this AFTER migration 001 (new tables)
-- Estimated time: 2h (includes testing and verification)
-- =========================================================================

-- =========================================================================
-- SECTION 1: ALTER customer_contacts (Role + Analytics Columns)
-- =========================================================================

-- Role classification columns
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS seniority_level TEXT
    CHECK (seniority_level IN ('c_level','vp','director','manager','senior','mid','junior','intern','unknown'));

ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS functional_role TEXT
    CHECK (functional_role IN ('executive','sales','marketing','operations','finance','engineering','support','procurement','legal','hr','other','unknown'));

ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS is_decision_maker BOOLEAN DEFAULT FALSE;
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS is_primary_contact BOOLEAN DEFAULT FALSE;

ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS role_source TEXT DEFAULT 'unknown'
    CHECK (role_source IN ('manual','email_signature','ai_enriched','inferred','csv_import','unknown'));

ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS role_confidence DECIMAL(3,2) DEFAULT 0.00;
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS department TEXT;
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS engagement_score INTEGER DEFAULT 0;

-- Communication analytics columns
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS avg_response_time_seconds INTEGER;
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS their_avg_response_time INTEGER;
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS initiation_ratio DECIMAL(3,2);
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS reply_rate DECIMAL(3,2);
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS emails_per_month_avg DECIMAL(8,2);

ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS frequency_trend TEXT
    CHECK (frequency_trend IN ('increasing','stable','declining','inactive'));

ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS avg_thread_depth DECIMAL(5,2);
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS last_inbound_at TIMESTAMPTZ;
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS last_outbound_at TIMESTAMPTZ;
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS open_thread_count INTEGER DEFAULT 0;
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS dropped_thread_count INTEGER DEFAULT 0;

-- Additional contact metadata
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS is_shared_address BOOLEAN DEFAULT FALSE;

-- Indexes for customer_contacts new columns
CREATE INDEX IF NOT EXISTS idx_contacts_seniority ON customer_contacts(seniority_level);
CREATE INDEX IF NOT EXISTS idx_contacts_role ON customer_contacts(functional_role);
CREATE INDEX IF NOT EXISTS idx_contacts_decision_maker ON customer_contacts(is_decision_maker) WHERE is_decision_maker = TRUE;
CREATE INDEX IF NOT EXISTS idx_contacts_engagement ON customer_contacts(engagement_score DESC);
CREATE INDEX IF NOT EXISTS idx_contacts_frequency_trend ON customer_contacts(frequency_trend);
CREATE INDEX IF NOT EXISTS idx_contacts_shared ON customer_contacts(is_shared_address) WHERE is_shared_address = TRUE;

COMMENT ON COLUMN customer_contacts.seniority_level IS 'Job seniority: c_level, vp, director, manager, senior, mid, junior, intern, unknown';
COMMENT ON COLUMN customer_contacts.functional_role IS 'Functional area: executive, sales, marketing, operations, finance, engineering, support, procurement, legal, hr, other, unknown';
COMMENT ON COLUMN customer_contacts.is_decision_maker IS 'TRUE for c_level, vp, director roles';
COMMENT ON COLUMN customer_contacts.role_confidence IS 'Confidence score 0.00-1.00 for role classification';
COMMENT ON COLUMN customer_contacts.engagement_score IS '0-100 score based on 8 factors';
COMMENT ON COLUMN customer_contacts.initiation_ratio IS 'Ratio of threads started by contact (0.0-1.0)';
COMMENT ON COLUMN customer_contacts.reply_rate IS 'Percentage of our emails they replied to (0.0-1.0)';
COMMENT ON COLUMN customer_contacts.is_shared_address IS 'TRUE for info@, sales@, support@ type addresses';

-- =========================================================================
-- SECTION 2: ALTER customer_companies (Engagement Columns)
-- =========================================================================

-- Role summary columns
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS contact_count INTEGER DEFAULT 0;
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS decision_maker_count INTEGER DEFAULT 0;
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS primary_contact_id UUID REFERENCES customer_contacts(id) ON DELETE SET NULL;
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS highest_seniority TEXT;
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS engagement_score INTEGER DEFAULT 0;

ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS relationship_status TEXT DEFAULT 'new'
    CHECK (relationship_status IN ('active','cooling','dormant','new'));

-- Communication analytics columns
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS avg_response_time_seconds INTEGER;
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS sla_compliance_rate DECIMAL(3,2);
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS open_thread_count INTEGER DEFAULT 0;
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS dropped_thread_count INTEGER DEFAULT 0;
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS avg_emails_per_month DECIMAL(8,2);

ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS frequency_trend TEXT
    CHECK (frequency_trend IN ('increasing','stable','declining','inactive'));

ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS communication_health TEXT DEFAULT 'good'
    CHECK (communication_health IN ('excellent','good','needs_attention','critical'));

-- Indexes for customer_companies new columns
CREATE INDEX IF NOT EXISTS idx_companies_engagement ON customer_companies(engagement_score DESC);
CREATE INDEX IF NOT EXISTS idx_companies_relationship ON customer_companies(relationship_status);
CREATE INDEX IF NOT EXISTS idx_companies_health ON customer_companies(communication_health);
CREATE INDEX IF NOT EXISTS idx_companies_dropped ON customer_companies(dropped_thread_count DESC)
    WHERE dropped_thread_count > 0;
CREATE INDEX IF NOT EXISTS idx_companies_primary_contact ON customer_companies(primary_contact_id);

COMMENT ON COLUMN customer_companies.engagement_score IS '0-100 score based on all contacts aggregate';
COMMENT ON COLUMN customer_companies.relationship_status IS 'active: recent activity, cooling: declining, dormant: >90d no contact, new: <5 emails';
COMMENT ON COLUMN customer_companies.sla_compliance_rate IS 'Percentage of emails responded within SLA (0.0-1.0)';
COMMENT ON COLUMN customer_companies.communication_health IS 'excellent: >90% SLA + low drops, good: >75% SLA, needs_attention: <75% SLA, critical: <50% SLA or many drops';

-- =========================================================================
-- SECTION 3: Helper SQL Functions
-- =========================================================================

-- Function 1: Count unlinked emails for a mailbox
CREATE OR REPLACE FUNCTION get_unlinked_emails_count(p_mailbox_id UUID)
RETURNS TABLE(total_emails BIGINT, unlinked_emails BIGINT, linked_pct NUMERIC)
LANGUAGE sql STABLE AS $$
    SELECT
        COUNT(*) as total_emails,
        COUNT(*) FILTER (WHERE customer_company_id IS NULL) as unlinked_emails,
        ROUND(
            COUNT(*) FILTER (WHERE customer_company_id IS NOT NULL)::numeric / NULLIF(COUNT(*), 0) * 100,
            2
        ) as linked_pct
    FROM emails
    WHERE mailbox_id = p_mailbox_id
      AND processing_status = 'success';
$$;

GRANT EXECUTE ON FUNCTION get_unlinked_emails_count(UUID) TO anon, authenticated;

COMMENT ON FUNCTION get_unlinked_emails_count IS 'Returns total emails, unlinked count, and link percentage for a mailbox';

-- Function 2: Get unique domains from a mailbox with classification
CREATE OR REPLACE FUNCTION get_domain_summary(p_mailbox_id UUID, p_client_id UUID)
RETURNS TABLE(
    domain TEXT,
    email_count BIGINT,
    classification TEXT,
    company_name TEXT
)
LANGUAGE sql STABLE AS $$
    WITH email_domains AS (
        SELECT
            LOWER(SPLIT_PART(sender_email, '@', 2)) as domain,
            COUNT(*) as email_count
        FROM emails
        WHERE mailbox_id = p_mailbox_id
          AND sender_email IS NOT NULL
          AND sender_email != ''
          AND processing_status = 'success'
        GROUP BY 1
    )
    SELECT
        ed.domain,
        ed.email_count,
        CASE
            WHEN id2.domain IS NOT NULL THEN 'internal'
            WHEN fp.domain IS NOT NULL THEN 'free_provider'
            WHEN cc.id IS NOT NULL THEN 'customer'
            ELSE 'unknown'
        END as classification,
        cc.company_name
    FROM email_domains ed
    LEFT JOIN internal_domains id2 ON id2.domain = ed.domain AND id2.client_id = p_client_id
    LEFT JOIN free_email_providers fp ON fp.domain = ed.domain
    LEFT JOIN customer_companies cc ON cc.email_domains ? ed.domain AND cc.client_id = p_client_id
    ORDER BY ed.email_count DESC;
$$;

GRANT EXECUTE ON FUNCTION get_domain_summary(UUID, UUID) TO anon, authenticated;

COMMENT ON FUNCTION get_domain_summary IS 'Returns domains from mailbox emails with classification (internal/free_provider/customer/unknown)';

-- Function 3: Batch link emails to a company by domain
CREATE OR REPLACE FUNCTION link_emails_by_domain(
    p_client_id UUID,
    p_domain TEXT,
    p_company_id UUID
)
RETURNS INTEGER
LANGUAGE plpgsql AS $$
DECLARE
    updated_count INTEGER;
BEGIN
    UPDATE emails
    SET customer_company_id = p_company_id,
        client_id = p_client_id,
        updated_at = NOW()
    WHERE customer_company_id IS NULL
      AND LOWER(SPLIT_PART(sender_email, '@', 2)) = LOWER(p_domain)
      AND processing_status = 'success';

    GET DIAGNOSTICS updated_count = ROW_COUNT;
    RETURN updated_count;
END;
$$;

GRANT EXECUTE ON FUNCTION link_emails_by_domain(UUID, TEXT, UUID) TO anon, authenticated;

COMMENT ON FUNCTION link_emails_by_domain IS 'Links all unlinked emails from a domain to a company. Returns count of emails linked.';

-- Function 4: Update contact engagement metrics
CREATE OR REPLACE FUNCTION update_contact_engagement_metrics(p_contact_id UUID)
RETURNS VOID
LANGUAGE plpgsql AS $$
DECLARE
    v_total_emails INTEGER;
    v_avg_response_time INTEGER;
    v_open_threads INTEGER;
    v_dropped_threads INTEGER;
BEGIN
    -- Get total emails for this contact
    SELECT COUNT(*) INTO v_total_emails
    FROM emails
    WHERE customer_contact_id = p_contact_id
      AND processing_status = 'success';

    -- Get average response time
    SELECT AVG(response_time_seconds)::INTEGER INTO v_avg_response_time
    FROM email_response_metrics
    WHERE customer_contact_id = p_contact_id
      AND status = 'responded';

    -- Get open and dropped thread counts
    SELECT
        SUM(CASE WHEN status IN ('awaiting_reply', 'overdue') THEN 1 ELSE 0 END),
        SUM(CASE WHEN status = 'dropped' THEN 1 ELSE 0 END)
    INTO v_open_threads, v_dropped_threads
    FROM thread_status
    WHERE customer_contact_id = p_contact_id;

    -- Update contact record
    UPDATE customer_contacts
    SET
        avg_response_time_seconds = v_avg_response_time,
        open_thread_count = v_open_threads,
        dropped_thread_count = v_dropped_threads,
        updated_at = NOW()
    WHERE id = p_contact_id;
END;
$$;

GRANT EXECUTE ON FUNCTION update_contact_engagement_metrics(UUID) TO anon, authenticated;

COMMENT ON FUNCTION update_contact_engagement_metrics IS 'Updates engagement metrics for a contact (avg response time, open/dropped threads)';

-- Function 5: Update company engagement metrics
CREATE OR REPLACE FUNCTION update_company_engagement_metrics(p_company_id UUID)
RETURNS VOID
LANGUAGE plpgsql AS $$
DECLARE
    v_contact_count INTEGER;
    v_decision_maker_count INTEGER;
    v_avg_response_time INTEGER;
    v_sla_compliance DECIMAL(3,2);
    v_open_threads INTEGER;
    v_dropped_threads INTEGER;
BEGIN
    -- Get contact counts
    SELECT
        COUNT(*),
        SUM(CASE WHEN is_decision_maker = TRUE THEN 1 ELSE 0 END)
    INTO v_contact_count, v_decision_maker_count
    FROM customer_contacts
    WHERE customer_company_id = p_company_id;

    -- Get average response time across all company emails
    SELECT AVG(response_time_seconds)::INTEGER INTO v_avg_response_time
    FROM email_response_metrics
    WHERE customer_company_id = p_company_id
      AND status = 'responded';

    -- Get SLA compliance rate
    SELECT
        ROUND(
            SUM(CASE WHEN is_within_sla = TRUE THEN 1 ELSE 0 END)::numeric /
            NULLIF(COUNT(*), 0),
            2
        )
    INTO v_sla_compliance
    FROM email_response_metrics
    WHERE customer_company_id = p_company_id
      AND status = 'responded';

    -- Get open and dropped thread counts
    SELECT
        SUM(CASE WHEN status IN ('awaiting_reply', 'overdue') THEN 1 ELSE 0 END),
        SUM(CASE WHEN status = 'dropped' THEN 1 ELSE 0 END)
    INTO v_open_threads, v_dropped_threads
    FROM thread_status
    WHERE customer_company_id = p_company_id;

    -- Update company record
    UPDATE customer_companies
    SET
        contact_count = v_contact_count,
        decision_maker_count = v_decision_maker_count,
        avg_response_time_seconds = v_avg_response_time,
        sla_compliance_rate = v_sla_compliance,
        open_thread_count = v_open_threads,
        dropped_thread_count = v_dropped_threads,
        updated_at = NOW()
    WHERE id = p_company_id;
END;
$$;

GRANT EXECUTE ON FUNCTION update_company_engagement_metrics(UUID) TO anon, authenticated;

COMMENT ON FUNCTION update_company_engagement_metrics IS 'Updates engagement metrics for a company (contacts, response time, SLA, threads)';

-- =========================================================================
-- Verification Queries
-- =========================================================================

-- Verify customer_contacts columns
DO $$
DECLARE
    col_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO col_count
    FROM information_schema.columns
    WHERE table_name = 'customer_contacts'
      AND column_name IN (
        'seniority_level', 'functional_role', 'is_decision_maker',
        'engagement_score', 'avg_response_time_seconds', 'initiation_ratio',
        'reply_rate', 'frequency_trend', 'is_shared_address'
      );

    IF col_count >= 9 THEN
        RAISE NOTICE '✅ customer_contacts: % new columns added', col_count;
    ELSE
        RAISE WARNING '⚠️ customer_contacts: Only % columns added (expected 9+)', col_count;
    END IF;
END $$;

-- Verify customer_companies columns
DO $$
DECLARE
    col_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO col_count
    FROM information_schema.columns
    WHERE table_name = 'customer_companies'
      AND column_name IN (
        'contact_count', 'decision_maker_count', 'engagement_score',
        'relationship_status', 'avg_response_time_seconds',
        'sla_compliance_rate', 'communication_health'
      );

    IF col_count >= 7 THEN
        RAISE NOTICE '✅ customer_companies: % new columns added', col_count;
    ELSE
        RAISE WARNING '⚠️ customer_companies: Only % columns added (expected 7+)', col_count;
    END IF;
END $$;

-- Verify SQL functions
DO $$
DECLARE
    func_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO func_count
    FROM pg_proc p
    JOIN pg_namespace n ON p.pronamespace = n.oid
    WHERE n.nspname = 'public'
      AND p.proname IN (
        'get_unlinked_emails_count',
        'get_domain_summary',
        'link_emails_by_domain',
        'update_contact_engagement_metrics',
        'update_company_engagement_metrics'
      );

    IF func_count = 5 THEN
        RAISE NOTICE '✅ All 5 SQL helper functions created';
    ELSE
        RAISE WARNING '⚠️ Only % SQL functions created (expected 5)', func_count;
    END IF;
END $$;

-- Summary report
SELECT
    'Migration 002 Complete' AS status,
    NOW() AS executed_at,
    (SELECT COUNT(*) FROM information_schema.columns
     WHERE table_name = 'customer_contacts'
       AND column_name IN ('seniority_level', 'functional_role', 'engagement_score')
    ) AS contact_columns_added,
    (SELECT COUNT(*) FROM information_schema.columns
     WHERE table_name = 'customer_companies'
       AND column_name IN ('contact_count', 'engagement_score', 'relationship_status')
    ) AS company_columns_added,
    (SELECT COUNT(*) FROM pg_proc p
     JOIN pg_namespace n ON p.pronamespace = n.oid
     WHERE n.nspname = 'public'
       AND p.proname LIKE '%engagement%' OR p.proname LIKE '%unlinked%' OR p.proname LIKE '%domain%'
    ) AS helper_functions_created,
    'Ready for Phase 2 (Build extraction services)' AS next_step;

-- =========================================================================
-- END OF MIGRATION 002
-- =========================================================================
