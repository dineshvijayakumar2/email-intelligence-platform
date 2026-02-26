-- =========================================================================
-- Sprint 2 Migration 001: New Tables (Supporting Infrastructure)
-- =========================================================================
-- Purpose: Create new tables needed for customer data extraction pipeline
-- Run this FIRST before migration 002 (column additions)
-- Estimated time: 3h (includes testing and verification)
-- =========================================================================

-- Enable UUID extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =========================================================================
-- TABLE 1: internal_domains
-- Purpose: Store domains to exclude from customer extraction (own organization)
-- =========================================================================

CREATE TABLE IF NOT EXISTS internal_domains (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    domain TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT internal_domains_unique_client_domain UNIQUE(client_id, domain)
);

-- Indexes for internal_domains
CREATE INDEX IF NOT EXISTS idx_internal_domains_client ON internal_domains(client_id);
CREATE INDEX IF NOT EXISTS idx_internal_domains_domain ON internal_domains(domain);

-- Row Level Security (RLS) for internal_domains
ALTER TABLE internal_domains ENABLE ROW LEVEL SECURITY;

-- Permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE internal_domains TO anon, authenticated;

COMMENT ON TABLE internal_domains IS 'Domains to exclude from customer extraction (e.g., company own domain)';
COMMENT ON COLUMN internal_domains.domain IS 'Domain name without @ symbol (e.g., acme.com)';

-- =========================================================================
-- TABLE 2: free_email_providers
-- Purpose: List of free email providers (gmail.com, yahoo.com, etc.)
-- Contacts from these domains go to "Individual Contacts" bucket
-- =========================================================================

CREATE TABLE IF NOT EXISTS free_email_providers (
    domain TEXT PRIMARY KEY,
    provider_name TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Permissions
GRANT SELECT, INSERT, DELETE ON TABLE free_email_providers TO anon, authenticated;

COMMENT ON TABLE free_email_providers IS 'Free email provider domains (contacts grouped separately)';

-- Seed data: Common free email providers
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

-- =========================================================================
-- TABLE 3: extraction_jobs
-- Purpose: Track progress of extraction pipeline runs (13-step process)
-- =========================================================================

CREATE TABLE IF NOT EXISTS extraction_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    mailbox_id UUID REFERENCES mailboxes(id) ON DELETE CASCADE,
    client_id UUID REFERENCES clients(id) ON DELETE SET NULL,
    job_id UUID REFERENCES processing_jobs(id) ON DELETE SET NULL,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending','processing','completed','failed','cancelled')),

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

    -- Current step tracking (13 steps total)
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

-- Indexes for extraction_jobs
CREATE INDEX IF NOT EXISTS idx_extraction_jobs_mailbox ON extraction_jobs(mailbox_id);
CREATE INDEX IF NOT EXISTS idx_extraction_jobs_client ON extraction_jobs(client_id);
CREATE INDEX IF NOT EXISTS idx_extraction_jobs_status ON extraction_jobs(status);
CREATE INDEX IF NOT EXISTS idx_extraction_jobs_created ON extraction_jobs(created_at DESC);

-- Update trigger for extraction_jobs
CREATE OR REPLACE FUNCTION update_extraction_jobs_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_extraction_jobs_updated_at ON extraction_jobs;
CREATE TRIGGER trigger_extraction_jobs_updated_at
    BEFORE UPDATE ON extraction_jobs
    FOR EACH ROW
    EXECUTE FUNCTION update_extraction_jobs_updated_at();

-- Row Level Security for extraction_jobs
ALTER TABLE extraction_jobs ENABLE ROW LEVEL SECURITY;

-- Permissions
GRANT SELECT, INSERT, UPDATE ON TABLE extraction_jobs TO anon, authenticated;

COMMENT ON TABLE extraction_jobs IS 'Tracks progress of 13-step customer data extraction pipeline';
COMMENT ON COLUMN extraction_jobs.current_step IS 'Current step name (e.g., upsert_companies, compute_response_times)';
COMMENT ON COLUMN extraction_jobs.errors IS 'Array of error objects: [{step, message, timestamp}]';

-- =========================================================================
-- TABLE 4: unified_email_rules
-- Purpose: Normalized email rules from Gmail/Outlook/JSON/Manual sources
-- =========================================================================

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

    -- Conditions (normalized from Gmail/Outlook format)
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

    -- Intelligence (derived from actions)
    engagement_signal TEXT CHECK (engagement_signal IN ('high_value', 'low_priority', 'escalation', 'segmentation', 'neutral')),
    matched_company_id UUID REFERENCES customer_companies(id) ON DELETE SET NULL,
    matched_contact_id UUID REFERENCES customer_contacts(id) ON DELETE SET NULL,

    -- Timestamps
    synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unified_rules_unique_source UNIQUE(mailbox_id, source_type, source_rule_id)
);

-- Indexes for unified_email_rules
CREATE INDEX IF NOT EXISTS idx_unified_rules_mailbox ON unified_email_rules(mailbox_id);
CREATE INDEX IF NOT EXISTS idx_unified_rules_client ON unified_email_rules(client_id);
CREATE INDEX IF NOT EXISTS idx_unified_rules_source ON unified_email_rules(source_type);
CREATE INDEX IF NOT EXISTS idx_unified_rules_signal ON unified_email_rules(engagement_signal);
CREATE INDEX IF NOT EXISTS idx_unified_rules_company ON unified_email_rules(matched_company_id);
CREATE INDEX IF NOT EXISTS idx_unified_rules_contact ON unified_email_rules(matched_contact_id);
CREATE INDEX IF NOT EXISTS idx_unified_rules_active ON unified_email_rules(is_active) WHERE is_active = TRUE;

-- GIN indexes for array columns (faster CONTAINS queries)
CREATE INDEX IF NOT EXISTS idx_unified_rules_from_domains ON unified_email_rules USING GIN(condition_from_domains);
CREATE INDEX IF NOT EXISTS idx_unified_rules_from_addresses ON unified_email_rules USING GIN(condition_from_addresses);

-- Update trigger for unified_email_rules
DROP TRIGGER IF EXISTS trigger_unified_rules_updated_at ON unified_email_rules;
CREATE TRIGGER trigger_unified_rules_updated_at
    BEFORE UPDATE ON unified_email_rules
    FOR EACH ROW
    EXECUTE FUNCTION update_extraction_jobs_updated_at();

-- Row Level Security
ALTER TABLE unified_email_rules ENABLE ROW LEVEL SECURITY;

-- Permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE unified_email_rules TO anon, authenticated;

COMMENT ON TABLE unified_email_rules IS 'Normalized email rules from all sources (Gmail, Outlook, JSON, Manual)';
COMMENT ON COLUMN unified_email_rules.engagement_signal IS 'Derived signal: high_value (VIP), low_priority (auto-delete), escalation (forwarded), segmentation (labeled), neutral';
COMMENT ON COLUMN unified_email_rules.source_rule_id IS 'Original rule ID from Gmail/Outlook API (null for manual rules)';

-- =========================================================================
-- TABLE 5: email_response_metrics
-- Purpose: Track response times for inbound-outbound email pairs
-- =========================================================================

CREATE TABLE IF NOT EXISTS email_response_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    thread_id TEXT NOT NULL,
    mailbox_id UUID REFERENCES mailboxes(id) ON DELETE CASCADE,
    inbound_email_id UUID REFERENCES emails(id) ON DELETE CASCADE,
    outbound_email_id UUID REFERENCES emails(id) ON DELETE SET NULL,
    customer_contact_id UUID REFERENCES customer_contacts(id) ON DELETE SET NULL,
    customer_company_id UUID REFERENCES customer_companies(id) ON DELETE SET NULL,

    -- Timing
    inbound_at TIMESTAMPTZ NOT NULL,
    responded_at TIMESTAMPTZ,
    response_time_seconds INTEGER,

    -- SLA tracking
    is_within_sla BOOLEAN,
    sla_threshold_hours INTEGER DEFAULT 4,
    is_business_hours_only BOOLEAN DEFAULT FALSE,

    -- Status
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('responded', 'open', 'no_response_needed')),

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for email_response_metrics
CREATE INDEX IF NOT EXISTS idx_response_metrics_thread ON email_response_metrics(thread_id);
CREATE INDEX IF NOT EXISTS idx_response_metrics_mailbox ON email_response_metrics(mailbox_id);
CREATE INDEX IF NOT EXISTS idx_response_metrics_company ON email_response_metrics(customer_company_id);
CREATE INDEX IF NOT EXISTS idx_response_metrics_contact ON email_response_metrics(customer_contact_id);
CREATE INDEX IF NOT EXISTS idx_response_metrics_status ON email_response_metrics(status) WHERE status = 'open';
CREATE INDEX IF NOT EXISTS idx_response_metrics_sla ON email_response_metrics(is_within_sla) WHERE is_within_sla = FALSE;
CREATE INDEX IF NOT EXISTS idx_response_metrics_inbound_at ON email_response_metrics(inbound_at DESC);

-- Row Level Security
ALTER TABLE email_response_metrics ENABLE ROW LEVEL SECURITY;

-- Permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE email_response_metrics TO anon, authenticated;

COMMENT ON TABLE email_response_metrics IS 'Response time tracking for inbound-outbound email pairs';
COMMENT ON COLUMN email_response_metrics.response_time_seconds IS 'NULL if unanswered (status=open)';
COMMENT ON COLUMN email_response_metrics.is_within_sla IS 'TRUE if responded within sla_threshold_hours';

-- =========================================================================
-- TABLE 6: thread_status
-- Purpose: Track thread completeness (awaiting reply, overdue, dropped, etc.)
-- =========================================================================

CREATE TABLE IF NOT EXISTS thread_status (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    thread_id TEXT NOT NULL UNIQUE,
    mailbox_id UUID REFERENCES mailboxes(id) ON DELETE CASCADE,
    customer_company_id UUID REFERENCES customer_companies(id) ON DELETE SET NULL,
    customer_contact_id UUID REFERENCES customer_contacts(id) ON DELETE SET NULL,

    -- Thread metadata
    subject TEXT,
    status TEXT NOT NULL DEFAULT 'complete' CHECK (status IN (
        'complete',
        'awaiting_reply',
        'overdue',
        'dropped',
        'outbound_pending',
        'stale'
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

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for thread_status
CREATE INDEX IF NOT EXISTS idx_thread_status_mailbox ON thread_status(mailbox_id);
CREATE INDEX IF NOT EXISTS idx_thread_status_company ON thread_status(customer_company_id);
CREATE INDEX IF NOT EXISTS idx_thread_status_contact ON thread_status(customer_contact_id);
CREATE INDEX IF NOT EXISTS idx_thread_status_status ON thread_status(status);
CREATE INDEX IF NOT EXISTS idx_thread_status_open ON thread_status(status, last_message_at DESC)
    WHERE status IN ('awaiting_reply', 'overdue', 'dropped');
CREATE INDEX IF NOT EXISTS idx_thread_status_sla ON thread_status(sla_deadline)
    WHERE status = 'awaiting_reply' AND sla_deadline IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_thread_status_flagged ON thread_status(is_flagged) WHERE is_flagged = TRUE;

-- Update trigger for thread_status
DROP TRIGGER IF EXISTS trigger_thread_status_updated_at ON thread_status;
CREATE TRIGGER trigger_thread_status_updated_at
    BEFORE UPDATE ON thread_status
    FOR EACH ROW
    EXECUTE FUNCTION update_extraction_jobs_updated_at();

-- Row Level Security
ALTER TABLE thread_status ENABLE ROW LEVEL SECURITY;

-- Permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE thread_status TO anon, authenticated;

COMMENT ON TABLE thread_status IS 'Thread completeness tracking (complete, awaiting reply, overdue, dropped)';
COMMENT ON COLUMN thread_status.status IS 'complete: last msg outbound | awaiting_reply: last msg inbound <7d | overdue: >SLA | dropped: >7d | outbound_pending: waiting for customer | stale: >30d';
COMMENT ON COLUMN thread_status.open_duration_seconds IS 'How long thread has been in current open state';

-- =========================================================================
-- Verification Queries
-- =========================================================================

-- Verify all tables were created
DO $$
DECLARE
    table_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO table_count
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name IN (
        'internal_domains',
        'free_email_providers',
        'extraction_jobs',
        'unified_email_rules',
        'email_response_metrics',
        'thread_status'
      );

    IF table_count = 6 THEN
        RAISE NOTICE '✅ All 6 tables created successfully';
    ELSE
        RAISE WARNING '⚠️ Only % tables created (expected 6)', table_count;
    END IF;
END $$;

-- Verify free email providers seed data
DO $$
DECLARE
    provider_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO provider_count FROM free_email_providers;

    IF provider_count >= 29 THEN
        RAISE NOTICE '✅ Free email providers seeded: % domains', provider_count;
    ELSE
        RAISE WARNING '⚠️ Only % free email providers (expected 29)', provider_count;
    END IF;
END $$;

-- Summary report
SELECT
    'Migration 001 Complete' AS status,
    NOW() AS executed_at,
    (SELECT COUNT(*) FROM information_schema.tables
     WHERE table_schema = 'public'
       AND table_name IN ('internal_domains', 'free_email_providers', 'extraction_jobs',
                          'unified_email_rules', 'email_response_metrics', 'thread_status')
    ) AS tables_created,
    (SELECT COUNT(*) FROM free_email_providers) AS free_providers_seeded,
    'Ready for Migration 002 (column additions)' AS next_step;

-- =========================================================================
-- END OF MIGRATION 001
-- =========================================================================
