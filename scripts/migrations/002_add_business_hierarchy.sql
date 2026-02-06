-- Migration: 002_add_business_hierarchy.sql
-- Description: Add business hierarchy tables (Account Managers → Clients → Customer Companies → Contacts)
-- Date: 2026-01-19
-- Stage 2 Phase 2 - Business Hierarchy Implementation

-- =========================================================================
-- 1. Account Managers Table (Platform Users)
-- =========================================================================

CREATE TABLE IF NOT EXISTS account_managers (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name TEXT NOT NULL,
  email TEXT UNIQUE NOT NULL,
  role TEXT NOT NULL DEFAULT 'account_manager',
  -- Roles: 'admin', 'account_manager', 'viewer'
  password_hash TEXT,
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE account_managers IS 'Platform users who manage client relationships';
COMMENT ON COLUMN account_managers.role IS 'User role: admin, account_manager, or viewer';
COMMENT ON COLUMN account_managers.is_active IS 'Whether the account is active';

-- =========================================================================
-- 2. Clients Table (Consulting Clients)
-- =========================================================================

CREATE TABLE IF NOT EXISTS clients (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  account_manager_id UUID REFERENCES account_managers(id) ON DELETE SET NULL,
  client_name TEXT NOT NULL,
  client_label TEXT,  -- Short label like "Carbon8", "EBNT"
  industry TEXT,
  status TEXT DEFAULT 'active',  -- 'active', 'inactive', 'prospect'

  -- Client's external systems configuration (for future integrations)
  uses_quickbase BOOLEAN DEFAULT FALSE,
  quickbase_realm TEXT,
  quickbase_api_token TEXT,  -- Should be encrypted in production

  uses_printiq BOOLEAN DEFAULT FALSE,
  printiq_api_url TEXT,
  printiq_api_key TEXT,  -- Should be encrypted in production

  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE clients IS 'Consulting clients of the platform';
COMMENT ON COLUMN clients.client_label IS 'Short identifier for display (e.g., Carbon8, EBNT)';
COMMENT ON COLUMN clients.status IS 'Client status: active, inactive, or prospect';

-- =========================================================================
-- 3. Customer Companies Table (Each Client's Customers)
-- =========================================================================

CREATE TABLE IF NOT EXISTS customer_companies (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  company_name TEXT NOT NULL,
  email_domains JSONB DEFAULT '[]'::jsonb,  -- ["acme.com", "acme-corp.com"]
  industry TEXT,
  website TEXT,

  -- Engagement metrics (auto-updated)
  first_contact_date TIMESTAMPTZ,
  last_contact_date TIMESTAMPTZ,
  total_emails INTEGER DEFAULT 0,
  total_inbound INTEGER DEFAULT 0,
  total_outbound INTEGER DEFAULT 0,

  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),

  -- Prevent duplicate company names for same client
  CONSTRAINT customer_companies_client_name_unique UNIQUE (client_id, company_name)
);

COMMENT ON TABLE customer_companies IS 'Customer companies belonging to each client';
COMMENT ON COLUMN customer_companies.email_domains IS 'Array of email domains associated with this company';
COMMENT ON COLUMN customer_companies.total_emails IS 'Total email count (auto-calculated)';

-- =========================================================================
-- 4. Customer Contacts Table (Individuals at Customer Companies)
-- =========================================================================

CREATE TABLE IF NOT EXISTS customer_contacts (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  customer_company_id UUID REFERENCES customer_companies(id) ON DELETE CASCADE,
  client_id UUID REFERENCES clients(id) ON DELETE CASCADE,  -- Denormalized for easy querying

  email_address TEXT NOT NULL,
  full_name TEXT,
  first_name TEXT,
  last_name TEXT,

  -- Signature-extracted fields
  job_title TEXT,
  company_name TEXT,  -- From signature, may differ from customer_company
  phone_number TEXT,
  mobile_number TEXT,
  linkedin_url TEXT,

  -- Engagement metrics
  first_contacted_at TIMESTAMPTZ,
  last_contacted_at TIMESTAMPTZ,
  total_emails_sent INTEGER DEFAULT 0,
  total_emails_received INTEGER DEFAULT 0,

  -- Parsed signature data
  signature_data JSONB,
  signature_last_updated TIMESTAMPTZ,

  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),

  -- Each email address unique within a customer company
  CONSTRAINT customer_contacts_company_email_unique UNIQUE (customer_company_id, email_address)
);

COMMENT ON TABLE customer_contacts IS 'Individual contacts at customer companies';
COMMENT ON COLUMN customer_contacts.signature_data IS 'Full parsed signature data as JSON';
COMMENT ON COLUMN customer_contacts.client_id IS 'Denormalized from customer_company for query performance';

-- =========================================================================
-- 5. Customer Recognition Rules Table
-- =========================================================================

CREATE TABLE IF NOT EXISTS customer_recognition_rules (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  client_id UUID REFERENCES clients(id) ON DELETE CASCADE,  -- NULL = applies to all clients
  customer_company_id UUID REFERENCES customer_companies(id) ON DELETE CASCADE,

  rule_name TEXT NOT NULL,
  rule_type TEXT NOT NULL,  -- 'domain', 'email_exact', 'email_pattern', 'subject_contains', 'body_keyword'
  pattern TEXT NOT NULL,  -- e.g., "acme.com", "*@sales.acme.com", "Quote #"

  priority INTEGER DEFAULT 0,  -- Higher priority rules evaluated first
  is_active BOOLEAN DEFAULT TRUE,

  -- Metadata
  match_count INTEGER DEFAULT 0,  -- How many emails matched this rule
  last_matched_at TIMESTAMPTZ,

  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE customer_recognition_rules IS 'Rules for automatically matching emails to customer companies';
COMMENT ON COLUMN customer_recognition_rules.rule_type IS 'Rule type: domain, email_exact, email_pattern, subject_contains, body_keyword';
COMMENT ON COLUMN customer_recognition_rules.pattern IS 'Pattern to match (wildcards supported for email_pattern)';
COMMENT ON COLUMN customer_recognition_rules.priority IS 'Higher values = higher priority (evaluated first)';

-- =========================================================================
-- 6. Update Mailboxes Table with Business Hierarchy Links
-- =========================================================================

-- Link mailbox to client
ALTER TABLE mailboxes ADD COLUMN IF NOT EXISTS client_id UUID REFERENCES clients(id) ON DELETE SET NULL;
COMMENT ON COLUMN mailboxes.client_id IS 'Client this mailbox belongs to';

-- Link mailbox to account manager
ALTER TABLE mailboxes ADD COLUMN IF NOT EXISTS account_manager_id UUID REFERENCES account_managers(id) ON DELETE SET NULL;
COMMENT ON COLUMN mailboxes.account_manager_id IS 'Account manager responsible for this mailbox';

-- OAuth fields for future Gmail/Outlook integration
ALTER TABLE mailboxes ADD COLUMN IF NOT EXISTS sync_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE mailboxes ADD COLUMN IF NOT EXISTS last_synced_at TIMESTAMPTZ;

-- =========================================================================
-- 7. Update Emails Table with Business Hierarchy Links
-- =========================================================================

-- First, add the columns to the emails table (if they don't exist)
ALTER TABLE emails ADD COLUMN IF NOT EXISTS client_id UUID;
ALTER TABLE emails ADD COLUMN IF NOT EXISTS customer_company_id UUID;
ALTER TABLE emails ADD COLUMN IF NOT EXISTS customer_contact_id UUID;
ALTER TABLE emails ADD COLUMN IF NOT EXISTS direction TEXT;  -- 'inbound' or 'outbound'

COMMENT ON COLUMN emails.client_id IS 'Client this email belongs to (via mailbox)';
COMMENT ON COLUMN emails.customer_company_id IS 'Customer company associated with this email';
COMMENT ON COLUMN emails.customer_contact_id IS 'Customer contact associated with this email';
COMMENT ON COLUMN emails.direction IS 'Email direction: inbound (from customer) or outbound (to customer)';

-- Create indexes for the new columns
CREATE INDEX IF NOT EXISTS idx_emails_client ON emails(client_id);
CREATE INDEX IF NOT EXISTS idx_emails_customer_company ON emails(customer_company_id);
CREATE INDEX IF NOT EXISTS idx_emails_customer_contact ON emails(customer_contact_id);
CREATE INDEX IF NOT EXISTS idx_emails_direction ON emails(direction);

-- Add foreign key constraint for client_id
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'emails_client_id_fkey'
    ) THEN
        ALTER TABLE emails ADD CONSTRAINT emails_client_id_fkey
            FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE SET NULL;
    END IF;
END $$;

-- Add foreign key constraint for customer_company_id
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'emails_customer_company_id_fkey'
    ) THEN
        ALTER TABLE emails ADD CONSTRAINT emails_customer_company_id_fkey
            FOREIGN KEY (customer_company_id) REFERENCES customer_companies(id) ON DELETE SET NULL;
    END IF;
END $$;

-- Add foreign key constraint for customer_contact_id
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'emails_customer_contact_id_fkey'
    ) THEN
        ALTER TABLE emails ADD CONSTRAINT emails_customer_contact_id_fkey
            FOREIGN KEY (customer_contact_id) REFERENCES customer_contacts(id) ON DELETE SET NULL;
    END IF;
END $$;

-- =========================================================================
-- 8. Create Indexes for Query Performance
-- =========================================================================

-- Account managers indexes
CREATE INDEX IF NOT EXISTS idx_account_managers_email ON account_managers(email);
CREATE INDEX IF NOT EXISTS idx_account_managers_active ON account_managers(is_active) WHERE is_active = TRUE;

-- Clients indexes
CREATE INDEX IF NOT EXISTS idx_clients_account_manager ON clients(account_manager_id);
CREATE INDEX IF NOT EXISTS idx_clients_status ON clients(status);
CREATE INDEX IF NOT EXISTS idx_clients_label ON clients(client_label);

-- Customer companies indexes
CREATE INDEX IF NOT EXISTS idx_customer_companies_client ON customer_companies(client_id);
CREATE INDEX IF NOT EXISTS idx_customer_companies_name ON customer_companies(company_name);
CREATE INDEX IF NOT EXISTS idx_customer_companies_last_contact ON customer_companies(last_contact_date DESC);

-- Customer contacts indexes
CREATE INDEX IF NOT EXISTS idx_customer_contacts_company ON customer_contacts(customer_company_id);
CREATE INDEX IF NOT EXISTS idx_customer_contacts_client ON customer_contacts(client_id);
CREATE INDEX IF NOT EXISTS idx_customer_contacts_email ON customer_contacts(email_address);
CREATE INDEX IF NOT EXISTS idx_customer_contacts_last_contact ON customer_contacts(last_contacted_at DESC);

-- Recognition rules indexes
CREATE INDEX IF NOT EXISTS idx_rules_client ON customer_recognition_rules(client_id);
CREATE INDEX IF NOT EXISTS idx_rules_customer ON customer_recognition_rules(customer_company_id);
CREATE INDEX IF NOT EXISTS idx_rules_type ON customer_recognition_rules(rule_type);
CREATE INDEX IF NOT EXISTS idx_rules_active ON customer_recognition_rules(is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_rules_priority ON customer_recognition_rules(priority DESC);

-- Mailboxes business hierarchy indexes
CREATE INDEX IF NOT EXISTS idx_mailboxes_client ON mailboxes(client_id);
CREATE INDEX IF NOT EXISTS idx_mailboxes_account_manager ON mailboxes(account_manager_id);

-- GIN index for email_domains JSON array search
CREATE INDEX IF NOT EXISTS idx_customer_companies_domains_gin ON customer_companies USING gin(email_domains);

-- =========================================================================
-- 9. Create Update Triggers for Timestamps
-- =========================================================================

-- Trigger for account_managers
CREATE TRIGGER update_account_managers_updated_at BEFORE UPDATE
    ON account_managers FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Trigger for clients
CREATE TRIGGER update_clients_updated_at BEFORE UPDATE
    ON clients FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Trigger for customer_companies
CREATE TRIGGER update_customer_companies_updated_at BEFORE UPDATE
    ON customer_companies FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Trigger for customer_contacts
CREATE TRIGGER update_customer_contacts_updated_at BEFORE UPDATE
    ON customer_contacts FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Trigger for customer_recognition_rules
CREATE TRIGGER update_customer_recognition_rules_updated_at BEFORE UPDATE
    ON customer_recognition_rules FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =========================================================================
-- 10. Create Helper Functions
-- =========================================================================

-- Function to find customer company by email domain
CREATE OR REPLACE FUNCTION find_customer_by_domain(
    p_email TEXT,
    p_client_id UUID DEFAULT NULL
)
RETURNS TABLE (
    company_id UUID,
    company_name TEXT,
    client_id UUID
)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    email_domain TEXT;
BEGIN
    -- Extract domain from email address
    email_domain := lower(split_part(p_email, '@', 2));

    RETURN QUERY
    SELECT
        cc.id as company_id,
        cc.company_name,
        cc.client_id
    FROM customer_companies cc
    WHERE
        cc.email_domains @> to_jsonb(email_domain)
        AND (p_client_id IS NULL OR cc.client_id = p_client_id)
    LIMIT 1;
END;
$$;

GRANT EXECUTE ON FUNCTION find_customer_by_domain(TEXT, UUID) TO anon, authenticated;
COMMENT ON FUNCTION find_customer_by_domain(TEXT, UUID) IS 'Find customer company by email domain';

-- Function to find or create customer contact
CREATE OR REPLACE FUNCTION upsert_customer_contact(
    p_email_address TEXT,
    p_customer_company_id UUID,
    p_client_id UUID,
    p_full_name TEXT DEFAULT NULL,
    p_first_name TEXT DEFAULT NULL,
    p_last_name TEXT DEFAULT NULL
)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    contact_id UUID;
BEGIN
    -- Try to find existing contact
    SELECT id INTO contact_id
    FROM customer_contacts
    WHERE email_address = lower(p_email_address)
      AND customer_company_id = p_customer_company_id;

    IF contact_id IS NOT NULL THEN
        -- Update existing contact
        UPDATE customer_contacts
        SET
            full_name = COALESCE(p_full_name, full_name),
            first_name = COALESCE(p_first_name, first_name),
            last_name = COALESCE(p_last_name, last_name),
            last_contacted_at = NOW()
        WHERE id = contact_id;

        RETURN contact_id;
    END IF;

    -- Create new contact
    INSERT INTO customer_contacts (
        email_address,
        customer_company_id,
        client_id,
        full_name,
        first_name,
        last_name,
        first_contacted_at,
        last_contacted_at
    ) VALUES (
        lower(p_email_address),
        p_customer_company_id,
        p_client_id,
        p_full_name,
        p_first_name,
        p_last_name,
        NOW(),
        NOW()
    )
    RETURNING id INTO contact_id;

    RETURN contact_id;
END;
$$;

GRANT EXECUTE ON FUNCTION upsert_customer_contact(TEXT, UUID, UUID, TEXT, TEXT, TEXT) TO anon, authenticated;
COMMENT ON FUNCTION upsert_customer_contact(TEXT, UUID, UUID, TEXT, TEXT, TEXT) IS 'Find or create a customer contact';

-- Function to get client hierarchy summary
CREATE OR REPLACE FUNCTION get_client_summary(p_client_id UUID)
RETURNS JSONB
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    result JSONB;
BEGIN
    SELECT jsonb_build_object(
        'client_id', c.id,
        'client_name', c.client_name,
        'client_label', c.client_label,
        'status', c.status,
        'account_manager', jsonb_build_object(
            'id', am.id,
            'name', am.name,
            'email', am.email
        ),
        'stats', jsonb_build_object(
            'total_mailboxes', (SELECT COUNT(*) FROM mailboxes WHERE client_id = p_client_id),
            'total_customer_companies', (SELECT COUNT(*) FROM customer_companies WHERE client_id = p_client_id),
            'total_customer_contacts', (SELECT COUNT(*) FROM customer_contacts WHERE client_id = p_client_id),
            'total_emails', (SELECT COUNT(*) FROM emails WHERE client_id = p_client_id),
            'total_rules', (SELECT COUNT(*) FROM customer_recognition_rules WHERE client_id = p_client_id)
        )
    ) INTO result
    FROM clients c
    LEFT JOIN account_managers am ON c.account_manager_id = am.id
    WHERE c.id = p_client_id;

    RETURN result;
END;
$$;

GRANT EXECUTE ON FUNCTION get_client_summary(UUID) TO anon, authenticated;
COMMENT ON FUNCTION get_client_summary(UUID) IS 'Get comprehensive summary of a client including stats';

-- Function to update customer company engagement metrics
CREATE OR REPLACE FUNCTION update_customer_engagement(p_customer_company_id UUID)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE customer_companies cc
    SET
        total_emails = (
            SELECT COUNT(*) FROM emails e WHERE e.customer_company_id = p_customer_company_id
        ),
        total_inbound = (
            SELECT COUNT(*) FROM emails e
            WHERE e.customer_company_id = p_customer_company_id AND e.direction = 'inbound'
        ),
        total_outbound = (
            SELECT COUNT(*) FROM emails e
            WHERE e.customer_company_id = p_customer_company_id AND e.direction = 'outbound'
        ),
        first_contact_date = (
            SELECT MIN(e.sent_date) FROM emails e WHERE e.customer_company_id = p_customer_company_id
        ),
        last_contact_date = (
            SELECT MAX(e.sent_date) FROM emails e WHERE e.customer_company_id = p_customer_company_id
        )
    WHERE cc.id = p_customer_company_id;
END;
$$;

GRANT EXECUTE ON FUNCTION update_customer_engagement(UUID) TO anon, authenticated;
COMMENT ON FUNCTION update_customer_engagement(UUID) IS 'Update engagement metrics for a customer company';

-- =========================================================================
-- 11. Create Views for Reporting
-- =========================================================================

-- Client overview with stats
CREATE OR REPLACE VIEW client_overview AS
SELECT
    c.id,
    c.client_name,
    c.client_label,
    c.status,
    c.industry,
    am.name as account_manager_name,
    am.email as account_manager_email,
    COUNT(DISTINCT cc.id) as customer_company_count,
    COUNT(DISTINCT ct.id) as contact_count,
    COUNT(DISTINCT m.id) as mailbox_count,
    COALESCE(SUM(cc.total_emails), 0) as total_emails,
    c.created_at,
    c.updated_at
FROM clients c
LEFT JOIN account_managers am ON c.account_manager_id = am.id
LEFT JOIN customer_companies cc ON cc.client_id = c.id
LEFT JOIN customer_contacts ct ON ct.client_id = c.id
LEFT JOIN mailboxes m ON m.client_id = c.id
GROUP BY c.id, c.client_name, c.client_label, c.status, c.industry,
         am.name, am.email, c.created_at, c.updated_at;

-- Customer engagement summary
CREATE OR REPLACE VIEW customer_engagement_summary AS
SELECT
    cc.id,
    cc.company_name,
    cc.client_id,
    c.client_name,
    cc.industry,
    cc.first_contact_date,
    cc.last_contact_date,
    cc.total_emails,
    cc.total_inbound,
    cc.total_outbound,
    COUNT(DISTINCT ct.id) as contact_count,
    CASE
        WHEN cc.last_contact_date > NOW() - INTERVAL '30 days' THEN 'active'
        WHEN cc.last_contact_date > NOW() - INTERVAL '90 days' THEN 'quiet'
        ELSE 'at_risk'
    END as engagement_status,
    cc.created_at
FROM customer_companies cc
JOIN clients c ON cc.client_id = c.id
LEFT JOIN customer_contacts ct ON ct.customer_company_id = cc.id
GROUP BY cc.id, cc.company_name, cc.client_id, c.client_name, cc.industry,
         cc.first_contact_date, cc.last_contact_date, cc.total_emails,
         cc.total_inbound, cc.total_outbound, cc.created_at;

-- =========================================================================
-- 12. Grant Permissions
-- =========================================================================

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE account_managers TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE clients TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE customer_companies TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE customer_contacts TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE customer_recognition_rules TO anon, authenticated;

GRANT SELECT ON client_overview TO anon, authenticated;
GRANT SELECT ON customer_engagement_summary TO anon, authenticated;

-- =========================================================================
-- 13. Update Statistics
-- =========================================================================

ANALYZE account_managers;
ANALYZE clients;
ANALYZE customer_companies;
ANALYZE customer_contacts;
ANALYZE customer_recognition_rules;
