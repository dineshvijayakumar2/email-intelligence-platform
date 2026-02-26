-- =========================================================================
-- SPRINT 2 - MASTER DATABASE SCHEMA
-- =========================================================================
-- Purpose: Consolidated Sprint 2 schema for reference and fresh installs
-- This file is MAINTAINED - updated whenever Sprint 2 schema changes
--
-- USAGE:
--   For Existing Databases: Use individual migration files (001, 002, 003)
--   For Fresh Installs: Can run this file after Sprint 1 schema
--   For Reference: Complete Sprint 2 schema documentation
--
-- Last Updated: 2026-02-16
-- Version: 1.8 (includes incremental extraction mode - Migration 010)
--
-- IMPORTANT (Migration 010): This migration also modifies the Sprint 1 mailboxes table.
--   Run sprint2_migration_010_incremental_mode.sql to add:
--   - last_extraction_at, extraction_mode, auto_extract_enabled, incremental_lookback_days
--   - Performance indexes: idx_emails_mailbox_sent_date, idx_emails_processing_status_sent_date
-- =========================================================================

-- =========================================================================
-- SECTION 1: NEW TABLES (6 tables)
-- =========================================================================

-- Enable UUID extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- TABLE 1: internal_domains
-- Purpose: Domains to exclude from customer extraction (own organization)
CREATE TABLE IF NOT EXISTS internal_domains (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    domain TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT internal_domains_unique_client_domain UNIQUE(client_id, domain)
);

CREATE INDEX IF NOT EXISTS idx_internal_domains_client ON internal_domains(client_id);
CREATE INDEX IF NOT EXISTS idx_internal_domains_domain ON internal_domains(domain);

ALTER TABLE internal_domains ENABLE ROW LEVEL SECURITY;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE internal_domains TO anon, authenticated;

COMMENT ON TABLE internal_domains IS 'Domains to exclude from customer extraction (e.g., company own domain)';

-- TABLE 2: free_email_providers
-- Purpose: Free email providers list (contacts go to "Individual Contacts" bucket)
CREATE TABLE IF NOT EXISTS free_email_providers (
    domain TEXT PRIMARY KEY,
    provider_name TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

GRANT SELECT, INSERT, DELETE ON TABLE free_email_providers TO anon, authenticated;

COMMENT ON TABLE free_email_providers IS 'Free email provider domains (contacts grouped separately)';

-- Seed data: 29 common free email providers
INSERT INTO free_email_providers (domain, provider_name, notes) VALUES
    ('gmail.com', 'Google Gmail', 'Most common free provider'),
    ('googlemail.com', 'Google Gmail', 'Alternative Gmail domain'),
    ('yahoo.com', 'Yahoo Mail', NULL),
    ('ymail.com', 'Yahoo Mail', 'Yahoo alternative domain'),
    ('rocketmail.com', 'Yahoo Mail', 'Yahoo alternative domain'),
    ('hotmail.com', 'Microsoft Hotmail', NULL),
    ('outlook.com', 'Microsoft Outlook', NULL),
    ('live.com', 'Microsoft Live', NULL),
    ('msn.com', 'Microsoft MSN', NULL),
    ('aol.com', 'AOL Mail', NULL),
    ('icloud.com', 'Apple iCloud', NULL),
    ('me.com', 'Apple Me', NULL),
    ('mac.com', 'Apple Mac', NULL),
    ('mail.com', 'Mail.com', NULL),
    ('protonmail.com', 'ProtonMail', 'Privacy-focused'),
    ('proton.me', 'ProtonMail', 'New ProtonMail domain'),
    ('pm.me', 'ProtonMail', 'ProtonMail short domain'),
    ('tutanota.com', 'Tutanota', 'Privacy-focused'),
    ('gmx.com', 'GMX Mail', NULL),
    ('gmx.net', 'GMX Mail', NULL),
    ('yandex.com', 'Yandex Mail', NULL),
    ('yandex.ru', 'Yandex Mail', NULL),
    ('zoho.com', 'Zoho Mail', NULL),
    ('fastmail.com', 'FastMail', NULL),
    ('hey.com', 'Hey', NULL),
    ('mail.ru', 'Mail.ru', NULL),
    ('inbox.com', 'Inbox.com', NULL),
    ('rediffmail.com', 'Rediff Mail', 'India'),
    ('outlook.in', 'Microsoft Outlook India', NULL)
ON CONFLICT (domain) DO NOTHING;

-- TABLE 3: extraction_jobs
-- Purpose: Track 13-step extraction pipeline progress
CREATE TABLE IF NOT EXISTS extraction_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    mailbox_id UUID REFERENCES mailboxes(id) ON DELETE CASCADE,
    client_id UUID REFERENCES clients(id) ON DELETE SET NULL,
    job_id UUID REFERENCES processing_jobs(id) ON DELETE SET NULL,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending','processing','completed','failed','cancelled')),

    -- Extraction mode tracking (Migration 010)
    extraction_mode VARCHAR(20) DEFAULT 'full',
    emails_in_scope INTEGER,
    date_range_start TIMESTAMPTZ,
    date_range_end TIMESTAMPTZ,

    -- Progress counters
    total_emails INTEGER DEFAULT 0,
    processed_emails INTEGER DEFAULT 0,
    contacts_created INTEGER DEFAULT 0,
    contacts_updated INTEGER DEFAULT 0,
    companies_created INTEGER DEFAULT 0,
    companies_updated INTEGER DEFAULT 0,
    rules_created INTEGER DEFAULT 0,
    emails_linked INTEGER DEFAULT 0,
    threads_analyzed INTEGER DEFAULT 0,

    -- Current step tracking
    current_step TEXT,
    current_step_number INTEGER DEFAULT 0,
    total_steps INTEGER DEFAULT 13,

    -- Error tracking
    errors JSONB DEFAULT '[]'::jsonb,

    -- Timing
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_extraction_jobs_mailbox ON extraction_jobs(mailbox_id);
CREATE INDEX IF NOT EXISTS idx_extraction_jobs_client ON extraction_jobs(client_id);
CREATE INDEX IF NOT EXISTS idx_extraction_jobs_status ON extraction_jobs(status);
CREATE INDEX IF NOT EXISTS idx_extraction_jobs_created ON extraction_jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_extraction_jobs_completed_at ON extraction_jobs(client_id, completed_at DESC) WHERE status = 'completed';  -- Migration 010

ALTER TABLE extraction_jobs ENABLE ROW LEVEL SECURITY;
GRANT SELECT, INSERT, UPDATE ON TABLE extraction_jobs TO anon, authenticated;

COMMENT ON TABLE extraction_jobs IS 'Tracks progress of 13-step customer data extraction pipeline';

-- TABLE 4: unified_email_rules
-- Purpose: Normalized email rules from Gmail/Outlook/JSON/Manual
CREATE TABLE IF NOT EXISTS unified_email_rules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    mailbox_id UUID REFERENCES mailboxes(id) ON DELETE CASCADE,
    client_id UUID REFERENCES clients(id) ON DELETE SET NULL,

    -- Source tracking
    source_type TEXT NOT NULL CHECK (source_type IN ('gmail_api', 'outlook_api', 'json_import', 'manual')),
    source_rule_id TEXT,
    rule_name TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    priority INTEGER DEFAULT 0,

    -- Conditions (normalized)
    condition_from_addresses TEXT[] DEFAULT '{}',
    condition_from_domains TEXT[] DEFAULT '{}',
    condition_to_addresses TEXT[] DEFAULT '{}',
    condition_subject_contains TEXT[] DEFAULT '{}',
    condition_body_contains TEXT[] DEFAULT '{}',
    condition_has_attachment BOOLEAN,
    condition_importance TEXT,
    condition_raw JSONB,

    -- Actions (normalized)
    action_label TEXT,
    action_move_to_folder TEXT,
    action_forward_to TEXT[] DEFAULT '{}',
    action_mark_important BOOLEAN,
    action_mark_read BOOLEAN,
    action_skip_inbox BOOLEAN,
    action_delete BOOLEAN,
    action_raw JSONB,

    -- Intelligence (derived)
    engagement_signal TEXT CHECK (engagement_signal IN ('high_value', 'low_priority', 'escalation', 'segmentation', 'neutral')),
    matched_company_id UUID REFERENCES customer_companies(id) ON DELETE SET NULL,
    matched_contact_id UUID REFERENCES customer_contacts(id) ON DELETE SET NULL,

    -- Timestamps
    synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unified_rules_unique_source UNIQUE(mailbox_id, source_type, source_rule_id)
);

CREATE INDEX IF NOT EXISTS idx_unified_rules_mailbox ON unified_email_rules(mailbox_id);
CREATE INDEX IF NOT EXISTS idx_unified_rules_client ON unified_email_rules(client_id);
CREATE INDEX IF NOT EXISTS idx_unified_rules_source ON unified_email_rules(source_type);
CREATE INDEX IF NOT EXISTS idx_unified_rules_signal ON unified_email_rules(engagement_signal);
CREATE INDEX IF NOT EXISTS idx_unified_rules_company ON unified_email_rules(matched_company_id);
CREATE INDEX IF NOT EXISTS idx_unified_rules_contact ON unified_email_rules(matched_contact_id);
CREATE INDEX IF NOT EXISTS idx_unified_rules_active ON unified_email_rules(is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_unified_rules_from_domains ON unified_email_rules USING GIN(condition_from_domains);
CREATE INDEX IF NOT EXISTS idx_unified_rules_from_addresses ON unified_email_rules USING GIN(condition_from_addresses);

ALTER TABLE unified_email_rules ENABLE ROW LEVEL SECURITY;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE unified_email_rules TO anon, authenticated;

COMMENT ON TABLE unified_email_rules IS 'Normalized email rules from all sources (Gmail, Outlook, JSON, Manual)';

-- TABLE 5: email_response_metrics
-- Purpose: Track response times for email pairs with auto-reply detection (Phase 4)
CREATE TABLE IF NOT EXISTS email_response_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Email pair references
    email_id UUID NOT NULL REFERENCES emails(id) ON DELETE CASCADE,
    responding_to_email_id UUID NOT NULL REFERENCES emails(id) ON DELETE CASCADE,

    -- Contact/Company references (denormalized for performance)
    responder_contact_id UUID REFERENCES customer_contacts(id) ON DELETE SET NULL,
    responder_company_id UUID REFERENCES customer_companies(id) ON DELETE SET NULL,

    -- Response time metrics
    response_time_seconds INTEGER NOT NULL,
    is_auto_reply BOOLEAN NOT NULL DEFAULT FALSE,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT unique_email_response UNIQUE (email_id),
    CONSTRAINT positive_response_time CHECK (response_time_seconds > 0)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_email_response_metrics_email_id ON email_response_metrics(email_id);
CREATE INDEX IF NOT EXISTS idx_email_response_metrics_responding_to ON email_response_metrics(responding_to_email_id);
CREATE INDEX IF NOT EXISTS idx_email_response_metrics_responder_contact ON email_response_metrics(responder_contact_id);
CREATE INDEX IF NOT EXISTS idx_email_response_metrics_responder_company ON email_response_metrics(responder_company_id);
CREATE INDEX IF NOT EXISTS idx_email_response_metrics_is_auto_reply ON email_response_metrics(is_auto_reply);

ALTER TABLE email_response_metrics ENABLE ROW LEVEL SECURITY;

-- RLS Policy: Users can only access metrics for their client's emails
CREATE POLICY email_response_metrics_client_isolation ON email_response_metrics
    FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM emails e
            JOIN mailboxes m ON e.mailbox_id = m.id
            WHERE e.id = email_response_metrics.email_id
              AND m.client_id = (current_setting('app.current_client_id', TRUE))::UUID
        )
    );

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE email_response_metrics TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE email_response_metrics TO service_role;

COMMENT ON TABLE email_response_metrics IS 'Response time tracking for email pairs with auto-reply detection';

-- TABLE 6: thread_status
-- Purpose: Track thread completeness (awaiting reply, overdue, dropped, etc.)
CREATE TABLE IF NOT EXISTS thread_status (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    thread_id TEXT NOT NULL UNIQUE,
    mailbox_id UUID REFERENCES mailboxes(id) ON DELETE CASCADE,
    customer_company_id UUID REFERENCES customer_companies(id) ON DELETE SET NULL,
    customer_contact_id UUID REFERENCES customer_contacts(id) ON DELETE SET NULL,

    -- Thread metadata
    subject TEXT,
    status TEXT NOT NULL DEFAULT 'complete' CHECK (status IN (
        'complete', 'awaiting_reply', 'overdue', 'dropped', 'outbound_pending', 'stale'
    )),

    -- Last message tracking
    last_message_direction TEXT CHECK (last_message_direction IN ('inbound', 'outbound')),
    last_message_at TIMESTAMPTZ,
    last_inbound_at TIMESTAMPTZ,
    last_outbound_at TIMESTAMPTZ,

    -- Thread statistics
    message_count INTEGER DEFAULT 0,
    participant_count INTEGER DEFAULT 0,
    open_duration_seconds INTEGER,

    -- SLA tracking
    sla_deadline TIMESTAMPTZ,
    sla_threshold_hours INTEGER DEFAULT 4,

    -- Flags
    is_flagged BOOLEAN DEFAULT FALSE,

    -- Phase 4 Analytics columns (Migration 008)
    last_email_id UUID REFERENCES emails(id) ON DELETE SET NULL,
    last_email_date TIMESTAMPTZ,
    last_sender_is_outbound BOOLEAN,
    thread_depth INTEGER DEFAULT 0,
    days_since_last_email INTEGER,
    is_overdue BOOLEAN DEFAULT FALSE,
    primary_contact_id UUID REFERENCES customer_contacts(id) ON DELETE SET NULL,
    primary_company_id UUID REFERENCES customer_companies(id) ON DELETE SET NULL,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_thread_status_mailbox ON thread_status(mailbox_id);
CREATE INDEX IF NOT EXISTS idx_thread_status_company ON thread_status(customer_company_id);
CREATE INDEX IF NOT EXISTS idx_thread_status_contact ON thread_status(customer_contact_id);
CREATE INDEX IF NOT EXISTS idx_thread_status_status ON thread_status(status);
CREATE INDEX IF NOT EXISTS idx_thread_status_open ON thread_status(status, last_message_at DESC)
    WHERE status IN ('awaiting_reply', 'overdue', 'dropped');
CREATE INDEX IF NOT EXISTS idx_thread_status_sla ON thread_status(sla_deadline)
    WHERE status = 'awaiting_reply' AND sla_deadline IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_thread_status_flagged ON thread_status(is_flagged) WHERE is_flagged = TRUE;
CREATE INDEX IF NOT EXISTS idx_thread_status_last_email ON thread_status(last_email_id);
CREATE INDEX IF NOT EXISTS idx_thread_status_primary_contact ON thread_status(primary_contact_id);
CREATE INDEX IF NOT EXISTS idx_thread_status_primary_company ON thread_status(primary_company_id);
CREATE INDEX IF NOT EXISTS idx_thread_status_is_overdue ON thread_status(is_overdue) WHERE is_overdue = TRUE;

ALTER TABLE thread_status ENABLE ROW LEVEL SECURITY;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE thread_status TO anon, authenticated;

COMMENT ON TABLE thread_status IS 'Thread completeness tracking (complete, awaiting reply, overdue, dropped)';

-- =========================================================================
-- SECTION 2: COLUMN ADDITIONS TO EXISTING TABLES
-- =========================================================================

-- ALTER customer_contacts: Add role + analytics columns (18+ columns)
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
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS is_shared_address BOOLEAN DEFAULT FALSE;
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS contact_type TEXT DEFAULT 'person'
    CHECK (contact_type IN ('person','automated','shared','mailing_list','internal','unknown'));

CREATE INDEX IF NOT EXISTS idx_contacts_seniority ON customer_contacts(seniority_level);
CREATE INDEX IF NOT EXISTS idx_contacts_role ON customer_contacts(functional_role);
CREATE INDEX IF NOT EXISTS idx_contacts_decision_maker ON customer_contacts(is_decision_maker) WHERE is_decision_maker = TRUE;
CREATE INDEX IF NOT EXISTS idx_contacts_engagement ON customer_contacts(engagement_score DESC);
CREATE INDEX IF NOT EXISTS idx_contacts_frequency_trend ON customer_contacts(frequency_trend);
CREATE INDEX IF NOT EXISTS idx_contacts_shared ON customer_contacts(is_shared_address) WHERE is_shared_address = TRUE;

-- ALTER customer_companies: Add engagement columns (11+ columns)
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS contact_count INTEGER DEFAULT 0;
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS decision_maker_count INTEGER DEFAULT 0;
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS primary_contact_id UUID REFERENCES customer_contacts(id) ON DELETE SET NULL;
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS highest_seniority TEXT;
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS engagement_score INTEGER DEFAULT 0;
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS relationship_status TEXT DEFAULT 'new'
    CHECK (relationship_status IN ('active','cooling','dormant','new'));
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS avg_response_time_seconds INTEGER;
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS sla_compliance_rate DECIMAL(3,2);
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS open_thread_count INTEGER DEFAULT 0;
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS dropped_thread_count INTEGER DEFAULT 0;
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS avg_emails_per_month DECIMAL(8,2);
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS frequency_trend TEXT
    CHECK (frequency_trend IN ('increasing','stable','declining','inactive'));
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS communication_health TEXT DEFAULT 'good'
    CHECK (communication_health IN ('excellent','good','needs_attention','critical'));

CREATE INDEX IF NOT EXISTS idx_companies_engagement ON customer_companies(engagement_score DESC);
CREATE INDEX IF NOT EXISTS idx_companies_relationship ON customer_companies(relationship_status);
CREATE INDEX IF NOT EXISTS idx_companies_health ON customer_companies(communication_health);
CREATE INDEX IF NOT EXISTS idx_companies_dropped ON customer_companies(dropped_thread_count DESC)
    WHERE dropped_thread_count > 0;
CREATE INDEX IF NOT EXISTS idx_companies_primary_contact ON customer_companies(primary_contact_id);

-- =========================================================================
-- SECTION 3: TRIGGERS
-- =========================================================================

-- Trigger function for updated_at timestamps
CREATE OR REPLACE FUNCTION update_extraction_jobs_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply triggers
DROP TRIGGER IF EXISTS trigger_extraction_jobs_updated_at ON extraction_jobs;
CREATE TRIGGER trigger_extraction_jobs_updated_at
    BEFORE UPDATE ON extraction_jobs
    FOR EACH ROW
    EXECUTE FUNCTION update_extraction_jobs_updated_at();

DROP TRIGGER IF EXISTS trigger_unified_rules_updated_at ON unified_email_rules;
CREATE TRIGGER trigger_unified_rules_updated_at
    BEFORE UPDATE ON unified_email_rules
    FOR EACH ROW
    EXECUTE FUNCTION update_extraction_jobs_updated_at();

DROP TRIGGER IF EXISTS trigger_thread_status_updated_at ON thread_status;
CREATE TRIGGER trigger_thread_status_updated_at
    BEFORE UPDATE ON thread_status
    FOR EACH ROW
    EXECUTE FUNCTION update_extraction_jobs_updated_at();

-- =========================================================================
-- SECTION 4: HELPER SQL FUNCTIONS (5 functions)
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

-- Function 2: Get domain summary with classification
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

-- Function 3: Batch link emails by domain
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
    SELECT COUNT(*) INTO v_total_emails
    FROM emails
    WHERE customer_contact_id = p_contact_id
      AND processing_status = 'success';

    SELECT AVG(response_time_seconds)::INTEGER INTO v_avg_response_time
    FROM email_response_metrics
    WHERE customer_contact_id = p_contact_id
      AND status = 'responded';

    SELECT
        SUM(CASE WHEN status IN ('awaiting_reply', 'overdue') THEN 1 ELSE 0 END),
        SUM(CASE WHEN status = 'dropped' THEN 1 ELSE 0 END)
    INTO v_open_threads, v_dropped_threads
    FROM thread_status
    WHERE customer_contact_id = p_contact_id;

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
    SELECT
        COUNT(*),
        SUM(CASE WHEN is_decision_maker = TRUE THEN 1 ELSE 0 END)
    INTO v_contact_count, v_decision_maker_count
    FROM customer_contacts
    WHERE customer_company_id = p_company_id;

    SELECT AVG(response_time_seconds)::INTEGER INTO v_avg_response_time
    FROM email_response_metrics
    WHERE customer_company_id = p_company_id
      AND status = 'responded';

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

    SELECT
        SUM(CASE WHEN status IN ('awaiting_reply', 'overdue') THEN 1 ELSE 0 END),
        SUM(CASE WHEN status = 'dropped' THEN 1 ELSE 0 END)
    INTO v_open_threads, v_dropped_threads
    FROM thread_status
    WHERE customer_company_id = p_company_id;

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

-- =========================================================================
-- SECTION 5: BATCH OPERATIONS (PERFORMANCE OPTIMIZATION)
-- =========================================================================
-- Purpose: Enable high-performance batch updates for contact data

-- Add unique constraint on customer_contacts to enable batch upsert
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'customer_contacts_client_email_unique'
    ) THEN
        ALTER TABLE customer_contacts
        ADD CONSTRAINT customer_contacts_client_email_unique
        UNIQUE (client_id, email_address);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_customer_contacts_client_email
ON customer_contacts(client_id, email_address);

COMMENT ON CONSTRAINT customer_contacts_client_email_unique ON customer_contacts
IS 'Ensures one contact per email per client - enables batch upsert';

-- Function 6: Batch update contact roles (used by extraction pipeline Step 8)
CREATE OR REPLACE FUNCTION batch_update_contact_roles(
    updates JSONB
) RETURNS TABLE (
    updated_count INTEGER,
    error_count INTEGER
) AS $$
DECLARE
    v_updated_count INTEGER := 0;
    v_error_count INTEGER := 0;
BEGIN
    -- Update contact roles from JSONB array
    UPDATE customer_contacts c
    SET
        job_title = u.job_title,
        seniority_level = u.seniority_level,
        functional_role = u.functional_role,
        is_decision_maker = u.is_decision_maker,
        role_source = u.role_source,
        role_confidence = u.role_confidence,
        department = u.department,
        updated_at = NOW()
    FROM jsonb_to_recordset(updates) AS u(
        email_address TEXT,
        client_id UUID,
        job_title TEXT,
        seniority_level TEXT,
        functional_role TEXT,
        is_decision_maker BOOLEAN,
        role_source TEXT,
        role_confidence NUMERIC,
        department TEXT
    )
    WHERE c.email_address = u.email_address
      AND c.client_id = u.client_id;

    GET DIAGNOSTICS v_updated_count = ROW_COUNT;
    RETURN QUERY SELECT v_updated_count, v_error_count;

EXCEPTION WHEN OTHERS THEN
    v_error_count := 1;
    RETURN QUERY SELECT v_updated_count, v_error_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION batch_update_contact_roles(JSONB)
IS 'Batch update contact role classifications from extraction pipeline (Step 8)';

GRANT EXECUTE ON FUNCTION batch_update_contact_roles(JSONB) TO anon, authenticated;

-- Function 7: Batch update contact company assignments (used by extraction pipeline Step 5)
CREATE OR REPLACE FUNCTION batch_update_contact_companies(
    updates JSONB
) RETURNS TABLE (
    updated_count INTEGER,
    error_count INTEGER
) AS $$
DECLARE
    v_updated_count INTEGER := 0;
    v_error_count INTEGER := 0;
BEGIN
    -- Update contact company assignments from JSONB array
    UPDATE customer_contacts c
    SET
        customer_company_id = u.customer_company_id::UUID,
        first_name = COALESCE(u.first_name, c.first_name),
        last_name = COALESCE(u.last_name, c.last_name),
        full_name = COALESCE(u.full_name, c.full_name),
        contact_type = COALESCE(u.contact_type, c.contact_type, 'person'),
        updated_at = NOW()
    FROM jsonb_to_recordset(updates) AS u(
        email_address TEXT,
        client_id UUID,
        customer_company_id TEXT,
        first_name TEXT,
        last_name TEXT,
        full_name TEXT,
        contact_type TEXT
    )
    WHERE c.email_address = u.email_address
      AND c.client_id = u.client_id;

    GET DIAGNOSTICS v_updated_count = ROW_COUNT;
    RETURN QUERY SELECT v_updated_count, v_error_count;

EXCEPTION WHEN OTHERS THEN
    v_error_count := 1;
    RETURN QUERY SELECT v_updated_count, v_error_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION batch_update_contact_companies(JSONB)
IS 'Batch update contact company assignments from extraction pipeline (Step 5)';

GRANT EXECUTE ON FUNCTION batch_update_contact_companies(JSONB) TO anon, authenticated;

-- =========================================================================
-- SECTION 6: ANALYTICS BATCH OPERATIONS (Migration 006)
-- =========================================================================
-- Purpose: Enable batch updates for Phase 4 analytics data (response times, thread counts)
-- Performance: 744 individual UPDATEs → 1-2 batch RPC calls (~25x improvement)

-- Function 8: Batch update contact analytics
CREATE OR REPLACE FUNCTION batch_update_contact_analytics(
    updates JSONB
) RETURNS TABLE (
    updated_count INTEGER,
    error_count INTEGER
) AS $$
DECLARE
    v_updated_count INTEGER := 0;
    v_error_count INTEGER := 0;
BEGIN
    -- Update contact analytics fields from JSONB array
    UPDATE customer_contacts c
    SET
        avg_response_time_seconds = COALESCE(u.avg_response_time_seconds::INTEGER, c.avg_response_time_seconds),
        their_avg_response_time = COALESCE(u.their_avg_response_time::INTEGER, c.their_avg_response_time),
        open_thread_count = COALESCE(u.open_thread_count::INTEGER, c.open_thread_count),
        dropped_thread_count = COALESCE(u.dropped_thread_count::INTEGER, c.dropped_thread_count),
        total_inbound_emails = COALESCE(u.total_inbound_emails::INTEGER, c.total_inbound_emails),
        total_outbound_emails = COALESCE(u.total_outbound_emails::INTEGER, c.total_outbound_emails),
        initiation_ratio = COALESCE(u.initiation_ratio::NUMERIC, c.initiation_ratio),
        reply_rate = COALESCE(u.reply_rate::NUMERIC, c.reply_rate),
        avg_thread_depth = COALESCE(u.avg_thread_depth::NUMERIC, c.avg_thread_depth),
        engagement_score = COALESCE(u.engagement_score::INTEGER, c.engagement_score),
        engagement_trend = COALESCE(u.engagement_trend, c.engagement_trend),
        updated_at = NOW()
    FROM jsonb_to_recordset(updates) AS u(
        contact_id UUID,
        avg_response_time_seconds TEXT,
        their_avg_response_time TEXT,
        open_thread_count TEXT,
        dropped_thread_count TEXT,
        total_inbound_emails TEXT,
        total_outbound_emails TEXT,
        initiation_ratio TEXT,
        reply_rate TEXT,
        avg_thread_depth TEXT,
        engagement_score TEXT,
        engagement_trend TEXT
    )
    WHERE c.id = u.contact_id;

    GET DIAGNOSTICS v_updated_count = ROW_COUNT;
    RETURN QUERY SELECT v_updated_count, v_error_count;

EXCEPTION WHEN OTHERS THEN
    v_error_count := 1;
    RETURN QUERY SELECT v_updated_count, v_error_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION batch_update_contact_analytics(JSONB)
IS 'Batch update contact analytics data from Phase 4 engagement pipeline (Steps 11-13)';

GRANT EXECUTE ON FUNCTION batch_update_contact_analytics(JSONB) TO authenticated;
GRANT EXECUTE ON FUNCTION batch_update_contact_analytics(JSONB) TO service_role;

-- Function 9: Batch update company analytics
CREATE OR REPLACE FUNCTION batch_update_company_analytics(
    updates JSONB
) RETURNS TABLE (
    updated_count INTEGER,
    error_count INTEGER
) AS $$
DECLARE
    v_updated_count INTEGER := 0;
    v_error_count INTEGER := 0;
BEGIN
    -- Update company analytics fields from JSONB array
    UPDATE customer_companies c
    SET
        avg_response_time_seconds = COALESCE(u.avg_response_time_seconds::INTEGER, c.avg_response_time_seconds),
        open_thread_count = COALESCE(u.open_thread_count::INTEGER, c.open_thread_count),
        dropped_thread_count = COALESCE(u.dropped_thread_count::INTEGER, c.dropped_thread_count),
        total_inbound_emails = COALESCE(u.total_inbound_emails::INTEGER, c.total_inbound_emails),
        total_outbound_emails = COALESCE(u.total_outbound_emails::INTEGER, c.total_outbound_emails),
        engagement_score = COALESCE(u.engagement_score::INTEGER, c.engagement_score),
        engagement_status = COALESCE(u.engagement_status, c.engagement_status),
        engagement_trend = COALESCE(u.engagement_trend, c.engagement_trend),
        updated_at = NOW()
    FROM jsonb_to_recordset(updates) AS u(
        company_id UUID,
        avg_response_time_seconds TEXT,
        open_thread_count TEXT,
        dropped_thread_count TEXT,
        total_inbound_emails TEXT,
        total_outbound_emails TEXT,
        engagement_score TEXT,
        engagement_status TEXT,
        engagement_trend TEXT
    )
    WHERE c.id = u.company_id;

    GET DIAGNOSTICS v_updated_count = ROW_COUNT;
    RETURN QUERY SELECT v_updated_count, v_error_count;

EXCEPTION WHEN OTHERS THEN
    v_error_count := 1;
    RETURN QUERY SELECT v_updated_count, v_error_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION batch_update_company_analytics(JSONB)
IS 'Batch update company analytics data from Phase 4 engagement pipeline (Steps 11-13)';

GRANT EXECUTE ON FUNCTION batch_update_company_analytics(JSONB) TO authenticated;
GRANT EXECUTE ON FUNCTION batch_update_company_analytics(JSONB) TO service_role;

-- =========================================================================
-- SECTION 7: DATABASE-SIDE ANALYTICS CALCULATIONS (Migration 007)
-- =========================================================================
-- Purpose: Move analytics calculations to database for maximum performance
-- Performance: 744 individual SELECT queries → 1 calculation query (~733x improvement)

-- Function 10: Calculate all contact response time averages in one query
CREATE OR REPLACE FUNCTION calculate_all_contact_response_times(
    p_client_id UUID
) RETURNS TABLE (
    contact_id UUID,
    avg_response_time_seconds INTEGER,
    their_avg_response_time INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        erm.responder_contact_id,
        AVG(erm.response_time_seconds)::INTEGER as avg_response_time,
        AVG(erm.response_time_seconds)::INTEGER as their_avg_response_time
    FROM email_response_metrics erm
    JOIN customer_contacts cc ON cc.id = erm.responder_contact_id
    WHERE cc.client_id = p_client_id
      AND erm.is_auto_reply = FALSE
      AND erm.responder_contact_id IS NOT NULL
    GROUP BY erm.responder_contact_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION calculate_all_contact_response_times(UUID)
IS 'Calculate average response times for all contacts in one query (excludes auto-replies)';

GRANT EXECUTE ON FUNCTION calculate_all_contact_response_times(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION calculate_all_contact_response_times(UUID) TO service_role;

-- Function 11: Calculate all contact thread counts in one query
CREATE OR REPLACE FUNCTION calculate_all_contact_thread_counts(
    p_client_id UUID
) RETURNS TABLE (
    contact_id UUID,
    open_thread_count INTEGER,
    dropped_thread_count INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        cc.id,
        COUNT(CASE WHEN ts.status IN ('awaiting_response', 'awaiting_our_response', 'overdue', 'ongoing') THEN 1 END)::INTEGER as open_count,
        COUNT(CASE WHEN ts.status = 'dropped' THEN 1 END)::INTEGER as dropped_count
    FROM customer_contacts cc
    LEFT JOIN thread_status ts ON COALESCE(ts.primary_contact_id, ts.customer_contact_id) = cc.id
    WHERE cc.client_id = p_client_id
    GROUP BY cc.id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION calculate_all_contact_thread_counts(UUID)
IS 'Calculate thread counts for all contacts in one query';

GRANT EXECUTE ON FUNCTION calculate_all_contact_thread_counts(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION calculate_all_contact_thread_counts(UUID) TO service_role;

-- Function 12: Calculate all company thread counts in one query
CREATE OR REPLACE FUNCTION calculate_all_company_thread_counts(
    p_client_id UUID
) RETURNS TABLE (
    company_id UUID,
    open_thread_count INTEGER,
    dropped_thread_count INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        cco.id,
        COUNT(CASE WHEN ts.status IN ('awaiting_response', 'awaiting_our_response', 'overdue', 'ongoing') THEN 1 END)::INTEGER as open_count,
        COUNT(CASE WHEN ts.status = 'dropped' THEN 1 END)::INTEGER as dropped_count
    FROM customer_companies cco
    LEFT JOIN thread_status ts ON ts.primary_company_id = cco.id
    WHERE cco.client_id = p_client_id
    GROUP BY cco.id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION calculate_all_company_thread_counts(UUID)
IS 'Calculate thread counts for all companies in one query';

GRANT EXECUTE ON FUNCTION calculate_all_company_thread_counts(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION calculate_all_company_thread_counts(UUID) TO service_role;

-- =========================================================================
-- SECTION 8: COMMUNICATION PATTERN CALCULATIONS (Migration 009)
-- =========================================================================
-- Purpose: Move communication pattern calculations to database for performance
-- Performance: 744+ individual queries → 3 RPC calls (~250x improvement)

-- Function 13: Calculate all contact communication patterns
CREATE OR REPLACE FUNCTION calculate_all_contact_comm_patterns(
    p_client_id UUID
) RETURNS TABLE (
    contact_id UUID,
    total_inbound_emails INTEGER,
    total_outbound_emails INTEGER,
    emails_per_month NUMERIC,
    avg_thread_depth NUMERIC,
    last_inbound_date TIMESTAMPTZ,
    last_outbound_date TIMESTAMPTZ,
    days_since_last_contact INTEGER
) AS $$
BEGIN
    RETURN QUERY
    WITH contact_emails AS (
        SELECT
            e.customer_contact_id,
            COUNT(*) FILTER (WHERE e.is_outbound = FALSE) as inbound_count,
            COUNT(*) FILTER (WHERE e.is_outbound = TRUE) as outbound_count,
            MAX(e.sent_date) FILTER (WHERE e.is_outbound = FALSE) as last_inbound,
            MAX(e.sent_date) FILTER (WHERE e.is_outbound = TRUE) as last_outbound,
            MIN(e.sent_date) as first_email,
            MAX(e.sent_date) as last_email
        FROM emails e
        JOIN customer_contacts cc ON cc.id = e.customer_contact_id
        WHERE cc.client_id = p_client_id
          AND e.processing_status = 'success'
        GROUP BY e.customer_contact_id
    ),
    thread_depths AS (
        SELECT
            COALESCE(ts.primary_contact_id, ts.customer_contact_id) as contact_id,
            AVG(ts.thread_depth)::NUMERIC as avg_depth
        FROM thread_status ts
        JOIN customer_contacts cc ON cc.id = COALESCE(ts.primary_contact_id, ts.customer_contact_id)
        WHERE cc.client_id = p_client_id
        GROUP BY COALESCE(ts.primary_contact_id, ts.customer_contact_id)
    )
    SELECT
        ce.customer_contact_id,
        ce.inbound_count::INTEGER,
        ce.outbound_count::INTEGER,
        CASE
            WHEN EXTRACT(EPOCH FROM (ce.last_email - ce.first_email)) > 0 THEN
                ROUND(
                    (ce.inbound_count + ce.outbound_count)::NUMERIC /
                    GREATEST(EXTRACT(EPOCH FROM (ce.last_email - ce.first_email)) / 2592000, 1),
                    2
                )
            ELSE 0
        END as emails_per_month,
        COALESCE(td.avg_depth, 0) as avg_thread_depth,
        ce.last_inbound,
        ce.last_outbound,
        EXTRACT(DAYS FROM (NOW() - GREATEST(ce.last_inbound, ce.last_outbound)))::INTEGER as days_since_last
    FROM contact_emails ce
    LEFT JOIN thread_depths td ON td.contact_id = ce.customer_contact_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION calculate_all_contact_comm_patterns(UUID)
IS 'Calculate communication pattern metrics for all contacts in one query';

GRANT EXECUTE ON FUNCTION calculate_all_contact_comm_patterns(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION calculate_all_contact_comm_patterns(UUID) TO service_role;

-- Function 14: Calculate thread initiation ratios for all contacts
CREATE OR REPLACE FUNCTION calculate_all_contact_initiation_ratios(
    p_client_id UUID
) RETURNS TABLE (
    contact_id UUID,
    threads_initiated_by_us INTEGER,
    threads_initiated_by_them INTEGER,
    initiation_ratio NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    WITH thread_initiators AS (
        SELECT
            e.customer_contact_id,
            e.thread_id,
            (ARRAY_AGG(e.is_outbound ORDER BY e.sent_date ASC))[1] as first_is_outbound
        FROM emails e
        JOIN customer_contacts cc ON cc.id = e.customer_contact_id
        WHERE cc.client_id = p_client_id
          AND e.thread_id IS NOT NULL
          AND e.processing_status = 'success'
        GROUP BY e.customer_contact_id, e.thread_id
    )
    SELECT
        ti.customer_contact_id,
        COUNT(*) FILTER (WHERE ti.first_is_outbound = TRUE)::INTEGER as initiated_by_us,
        COUNT(*) FILTER (WHERE ti.first_is_outbound = FALSE)::INTEGER as initiated_by_them,
        CASE
            WHEN COUNT(*) > 0 THEN
                ROUND(
                    COUNT(*) FILTER (WHERE ti.first_is_outbound = TRUE)::NUMERIC / COUNT(*),
                    3
                )
            ELSE 0.5
        END as initiation_ratio
    FROM thread_initiators ti
    GROUP BY ti.customer_contact_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION calculate_all_contact_initiation_ratios(UUID)
IS 'Calculate thread initiation ratios for all contacts in one query';

GRANT EXECUTE ON FUNCTION calculate_all_contact_initiation_ratios(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION calculate_all_contact_initiation_ratios(UUID) TO service_role;

-- Function 15: Calculate reply rates for all contacts
CREATE OR REPLACE FUNCTION calculate_all_contact_reply_rates(
    p_client_id UUID
) RETURNS TABLE (
    contact_id UUID,
    reply_rate NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    WITH contact_responses AS (
        SELECT
            erm.responder_contact_id,
            COUNT(*) FILTER (WHERE erm.is_auto_reply = FALSE) as valid_responses
        FROM email_response_metrics erm
        JOIN customer_contacts cc ON cc.id = erm.responder_contact_id
        WHERE cc.client_id = p_client_id
        GROUP BY erm.responder_contact_id
    ),
    contact_inbound AS (
        SELECT
            e.customer_contact_id,
            COUNT(*) as total_inbound
        FROM emails e
        JOIN customer_contacts cc ON cc.id = e.customer_contact_id
        WHERE cc.client_id = p_client_id
          AND e.is_outbound = FALSE
          AND e.processing_status = 'success'
        GROUP BY e.customer_contact_id
    )
    SELECT
        ci.customer_contact_id,
        CASE
            WHEN ci.total_inbound > 0 THEN
                ROUND(
                    COALESCE(cr.valid_responses, 0)::NUMERIC / ci.total_inbound,
                    3
                )
            ELSE 0
        END as reply_rate
    FROM contact_inbound ci
    LEFT JOIN contact_responses cr ON cr.responder_contact_id = ci.customer_contact_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION calculate_all_contact_reply_rates(UUID)
IS 'Calculate reply rates for all contacts in one query (excludes auto-replies)';

GRANT EXECUTE ON FUNCTION calculate_all_contact_reply_rates(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION calculate_all_contact_reply_rates(UUID) TO service_role;

-- =========================================================================
-- END OF SPRINT 2 MASTER SCHEMA
-- =========================================================================

-- CHANGE LOG:
-- 2026-02-11 v1.0 - Initial Sprint 2 schema
--   - 6 new tables
--   - 29+ columns added to existing tables
--   - 5 SQL helper functions
--   - All indexes, triggers, RLS, permissions
--
-- 2026-02-11 v1.1 - Added batch operations (Migration 003)
--   - Unique constraint on customer_contacts(client_id, email_address)
--   - batch_update_contact_roles() function (Step 8 optimization)
--   - batch_update_contact_companies() function (Step 5 optimization)
--   - Performance improvement: 500+ individual UPDATEs → 1-2 batch calls
--
-- 2026-02-11 v1.2 - Added contact classification (Migration 004)
--   - customer_contacts.contact_type column (person/automated/shared/mailing_list/internal/unknown)
--   - Updated batch_update_contact_companies() to handle contact_type
--   - Changed extraction from filtering to tagging all contacts
--
-- 2026-02-12 v1.3 - Fixed analytics tables for Phase 4 (Migration 005)
--   - Recreated email_response_metrics table with correct schema
--   - Added is_auto_reply column for auto-reply detection
--   - Changed from SLA tracking schema to response pair tracking
--   - Fixed Supabase boolean filter syntax in all Phase 4 services
--   - Ready for Phase 4 engagement analytics pipeline
--
-- 2026-02-12 v1.4 - Analytics batch operations (Migration 006)
--   - batch_update_contact_analytics() function (Steps 11-13 optimization)
--   - batch_update_company_analytics() function (Steps 11-13 optimization)
--   - Performance improvement: 744 individual UPDATEs → 1-2 batch calls (~25x faster)
--
-- 2026-02-12 v1.5 - Database-side analytics calculations (Migration 007)
--   - calculate_all_contact_response_times() - Calculate all averages in 1 query
--   - calculate_all_contact_thread_counts() - Calculate all thread counts in 1 query
--   - calculate_all_company_thread_counts() - Calculate all thread counts in 1 query
--   - Performance improvement: 744 individual SELECTs → 1 calculation query (~733x faster)
--   - Overall pipeline improvement: 271.90s → 42.64s (6.4x faster)
--
-- 2026-02-12 v1.6 - Thread status Phase 4 columns (Migration 008)
--   - Added 8 missing columns to thread_status table
--   - last_email_id, last_email_date, last_sender_is_outbound
--   - thread_depth, days_since_last_email, is_overdue
--   - primary_contact_id, primary_company_id (for improved analytics joins)
--   - Added 4 new indexes for query optimization
--   - Fixed Migration 007 functions to use COALESCE for column compatibility
--
-- 2026-02-12 v1.7 - Communication pattern calculations (Migration 009)
--   - calculate_all_contact_comm_patterns() - Calculate emails, dates, thread depth in 1 query
--   - calculate_all_contact_initiation_ratios() - Calculate thread initiation in 1 query
--   - calculate_all_contact_reply_rates() - Calculate reply rates in 1 query
--   - Updated comm_pattern_analyzer to use database-side calculations
--   - Updated save_patterns to use batch updates via batch_update_contact_analytics
--   - Performance improvement: 744+ individual queries to 3 RPC calls (~250x faster)
--   - Fixed email_linker payload size issue (992 emails) by chunking to 100 per batch
--
-- 2026-02-16 v1.8 - Incremental extraction mode (Migration 010)
--   - Added 4 columns to mailboxes: last_extraction_at, extraction_mode, auto_extract_enabled, incremental_lookback_days
--   - Added 4 columns to extraction_jobs: extraction_mode, emails_in_scope, date_range_start, date_range_end
--   - Created 3 performance indexes: idx_emails_mailbox_sent_date, idx_emails_processing_status_sent_date, idx_extraction_jobs_completed_at
--   - Updated ExtractionOrchestrator to support 'full' and 'incremental' modes
--   - Incremental mode processes only emails from last N days (configurable 1-365, default 7)
--   - Updated analytics API to accept extraction_mode parameter in job creation
--   - Backfilled last_extraction_at for existing mailboxes with successful jobs
