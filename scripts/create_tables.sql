-- Email Intelligence Platform Database Schema
-- PostgreSQL / Supabase

-- =========================================================================
-- Performance Configuration (Run on database setup)
-- =========================================================================

-- Set statement timeout to 60 seconds for batch operations
-- This prevents long-running queries from blocking the database
ALTER DATABASE postgres SET statement_timeout = '60s';

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable trigram extension for better text search
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Mailboxes table for multi-mailbox support
CREATE TABLE mailboxes (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name TEXT NOT NULL,
  email_address TEXT UNIQUE,  -- Optional: not required for file-based mailboxes (MBOX/PST/OLM)
  mailbox_type TEXT NOT NULL CHECK (mailbox_type IN ('mbox', 'pst', 'olm', 'gmail', 'outlook_live')),  -- File-based + LIVE integrations
  connection_config JSONB,
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  last_sync_at TIMESTAMPTZ,
  total_emails INTEGER DEFAULT 0,
  -- Stage 2: Business hierarchy columns (FK constraints added after tables exist)
  client_id UUID,
  account_manager_id UUID,
  sync_enabled BOOLEAN DEFAULT FALSE,
  last_synced_at TIMESTAMPTZ
);

-- Add helpful column comments
COMMENT ON COLUMN mailboxes.email_address IS 'Optional email address - not required for file-based mailboxes (MBOX/PST/OLM)';
COMMENT ON COLUMN mailboxes.mailbox_type IS 'Mailbox type: mbox (universal), pst (Windows Outlook), or olm (Mac Outlook)';

-- Main emails table
CREATE TABLE emails (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  message_id TEXT NOT NULL,
  mailbox_id UUID REFERENCES mailboxes(id) ON DELETE CASCADE,
  thread_id TEXT,
  folder_path TEXT,
  sender_email TEXT NOT NULL,
  sender_name TEXT,
  recipients JSONB,  -- Array of {email, name} objects
  cc_list JSONB,
  bcc_list JSONB,
  subject TEXT,
  body_text TEXT,
  body_html TEXT,
  sent_date TIMESTAMPTZ,
  received_date TIMESTAMPTZ,
  is_outbound BOOLEAN DEFAULT false,
  is_reply BOOLEAN DEFAULT false,
  message_size INTEGER,
  raw_headers JSONB,
  -- Stage 2: Error tracking columns
  processing_status TEXT DEFAULT 'pending',  -- pending, processing, success, failed, skipped
  processing_error TEXT,  -- Error message when failed
  processing_attempts INTEGER DEFAULT 0,  -- Retry count
  last_processing_attempt TIMESTAMPTZ,  -- Last attempt timestamp
  -- Stage 2: Business hierarchy columns (added in migration 002)
  client_id UUID,  -- References clients(id) - added after clients table exists
  customer_company_id UUID,  -- References customer_companies(id)
  customer_contact_id UUID,  -- References customer_contacts(id)
  direction TEXT,  -- inbound, outbound, internal
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  CONSTRAINT emails_message_id_mailbox_unique UNIQUE (message_id, mailbox_id)
);

-- Folder hierarchy
CREATE TABLE folders (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  folder_path TEXT NOT NULL,
  mailbox_id UUID REFERENCES mailboxes(id) ON DELETE CASCADE,
  parent_folder_id UUID REFERENCES folders(id),
  folder_type TEXT,  -- inbox, sent, spam, archive, user
  message_count INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  CONSTRAINT folders_folder_path_mailbox_unique UNIQUE (folder_path, mailbox_id)
);

-- Basic categorization (rule-based)
CREATE TABLE email_categories (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  email_id UUID REFERENCES emails(id) ON DELETE CASCADE,
  category TEXT NOT NULL,  -- system, spam, marketing, transactional, conversation
  tag_type TEXT,  -- Tag classification: direction, thread_type, folder, classification, sender_type, priority, content, metadata
  confidence DECIMAL(3,2) DEFAULT 1.0,
  detection_method TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(email_id, category)
);

COMMENT ON COLUMN email_categories.tag_type IS 'Tag classification: direction, thread_type, folder, classification, sender_type, priority, content, metadata';

-- AI enrichment (Stage 2)
CREATE TABLE email_enrichment (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  email_id UUID REFERENCES emails(id) ON DELETE CASCADE UNIQUE,
  email_type TEXT,
  tone TEXT,
  sentiment TEXT,
  happiness_index DECIMAL(3,2),
  escalation_needed BOOLEAN,
  short_summary TEXT,
  extracted_entities JSONB,
  custom_fields JSONB,  -- Flexible for evolving schema
  enriched_at TIMESTAMPTZ DEFAULT NOW(),
  model_version TEXT
);

-- Processing status tracking
CREATE TABLE processing_jobs (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  job_type TEXT NOT NULL,  -- extraction, enrichment
  mailbox_id UUID REFERENCES mailboxes(id) ON DELETE SET NULL,
  status TEXT NOT NULL,  -- pending, running, completed, failed
  total_records INTEGER,
  processed_records INTEGER DEFAULT 0,
  failed_records INTEGER DEFAULT 0,
  filtered_records INTEGER DEFAULT 0,  -- Stage 2: Emails skipped by date filter
  error_log JSONB,
  -- Stage 2: Error summary for aggregated error tracking
  error_summary JSONB,  -- {total_errors, error_types: {type: count}, sample_errors: [...]}
  -- Stage 2: Date range filter parameters (for audit trail)
  filter_start_date TIMESTAMPTZ,  -- Start of date range filter (null = no lower bound)
  filter_end_date TIMESTAMPTZ,    -- End of date range filter (null = no upper bound)
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- User integrations for OAuth2 token storage (Google Drive, etc.)
CREATE TABLE user_integrations (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id TEXT NOT NULL,  -- User identifier (string format for flexibility)
  provider TEXT NOT NULL CHECK (provider IN ('google_drive', 'gmail', 'microsoft', 'dropbox')),
  access_token TEXT NOT NULL,     -- Current access token
  refresh_token TEXT NOT NULL,    -- Long-lived refresh token
  token_expires_at TIMESTAMPTZ,   -- When access token expires
  -- Gmail/Outlook LIVE sync tracking columns
  last_sync_at TIMESTAMPTZ,          -- When last successful sync completed
  last_history_id TEXT,              -- Gmail historyId / Outlook deltaLink for incremental sync
  sync_status TEXT DEFAULT 'idle' CHECK (sync_status IN ('idle', 'syncing', 'error')),
  sync_error TEXT,                   -- Last sync error message (null if no error)
  email_count INTEGER DEFAULT 0,     -- Total emails synced via this integration
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),

  -- Ensure one integration per user per provider
  UNIQUE(user_id, provider)
);

-- Add helpful comments
COMMENT ON TABLE user_integrations IS 'Stores OAuth2 tokens and integration status for external services like Google Drive';
COMMENT ON COLUMN user_integrations.user_id IS 'User identifier (string format for flexibility)';
COMMENT ON COLUMN user_integrations.provider IS 'Service provider (google_drive, microsoft, etc.)';
COMMENT ON COLUMN user_integrations.access_token IS 'Short-lived access token for API calls';
COMMENT ON COLUMN user_integrations.refresh_token IS 'Long-lived token for refreshing access tokens';

-- Performance indexes
CREATE INDEX idx_emails_sent_date ON emails(sent_date);
CREATE INDEX idx_emails_sender ON emails(sender_email);
CREATE INDEX idx_emails_folder ON emails(folder_path);
CREATE INDEX idx_emails_thread ON emails(thread_id);
CREATE INDEX idx_emails_outbound ON emails(is_outbound);
CREATE INDEX idx_emails_reply ON emails(is_reply);
CREATE INDEX idx_emails_mailbox_id ON emails(mailbox_id);
CREATE INDEX idx_emails_mailbox_date ON emails(mailbox_id, sent_date);
CREATE INDEX idx_folders_mailbox_id ON folders(mailbox_id);
CREATE INDEX idx_processing_jobs_mailbox ON processing_jobs(mailbox_id);
CREATE INDEX idx_user_integrations_user_provider ON user_integrations(user_id, provider);

-- Email categories table indexes (critical for tag queries)
CREATE INDEX idx_email_categories_email_id ON email_categories(email_id);
CREATE INDEX idx_email_categories_category ON email_categories(category);
CREATE INDEX idx_email_categories_email_category ON email_categories(email_id, category);

-- Additional email table indexes for filtering (based on existing schema)

-- Processing jobs performance indexes
CREATE INDEX idx_processing_jobs_status ON processing_jobs(status);
CREATE INDEX idx_processing_jobs_type_status ON processing_jobs(job_type, status);
CREATE INDEX idx_processing_jobs_created_at ON processing_jobs(created_at DESC);

-- Stage 2: Error tracking indexes
CREATE INDEX idx_emails_processing_status ON emails(processing_status);
CREATE INDEX idx_emails_processing_status_mailbox ON emails(mailbox_id, processing_status);
CREATE INDEX idx_emails_failed_retry ON emails(processing_status, processing_attempts)
  WHERE processing_status = 'failed';
CREATE INDEX idx_emails_direction ON emails(direction);
CREATE INDEX idx_emails_client ON emails(client_id);
CREATE INDEX idx_emails_customer_company ON emails(customer_company_id);
CREATE INDEX idx_emails_customer_contact ON emails(customer_contact_id);

-- User integrations performance indexes
CREATE INDEX idx_user_integrations_token_expires ON user_integrations(token_expires_at) WHERE token_expires_at IS NOT NULL;

-- Full-text search indexes
CREATE INDEX idx_emails_subject_fts ON emails USING gin(to_tsvector('english', subject));
CREATE INDEX idx_emails_body_fts ON emails USING gin(to_tsvector('english', COALESCE(body_text, '')));

-- Trigram indexes for partial text matching (requires pg_trgm extension)
-- CREATE INDEX idx_emails_sender_email_gin ON emails USING gin(sender_email gin_trgm_ops);
-- CREATE INDEX idx_emails_subject_gin ON emails USING gin(subject gin_trgm_ops);

-- Composite indexes for common queries
CREATE INDEX idx_emails_folder_date ON emails(folder_path, sent_date DESC);
CREATE INDEX idx_emails_sender_date ON emails(sender_email, sent_date DESC);
CREATE INDEX idx_emails_mailbox_folder_date ON emails(mailbox_id, folder_path, sent_date DESC);
CREATE INDEX idx_emails_mailbox_date_outbound ON emails(mailbox_id, sent_date DESC, is_outbound);
CREATE INDEX idx_emails_mailbox_sender_date ON emails(mailbox_id, sender_email, sent_date DESC);
CREATE INDEX idx_emails_mailbox_folder_outbound ON emails(mailbox_id, folder_path, is_outbound);

-- Covering indexes for performance (includes frequently selected columns)
CREATE INDEX idx_emails_coverage_main ON emails(mailbox_id, sent_date DESC) 
  INCLUDE (id, subject, sender_email, sender_name, is_outbound, is_reply, folder_path, message_size);
CREATE INDEX idx_email_categories_coverage ON email_categories(email_id) 
  INCLUDE (category, confidence, detection_method);

-- Updated timestamp trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_emails_updated_at BEFORE UPDATE
    ON emails FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_user_integrations_updated_at BEFORE UPDATE
    ON user_integrations FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Full-text search function
CREATE OR REPLACE FUNCTION search_emails(search_query TEXT, limit_count INTEGER DEFAULT 100)
RETURNS TABLE (
  id UUID,
  subject TEXT,
  sender_email TEXT,
  sender_name TEXT,
  sent_date TIMESTAMPTZ,
  folder_path TEXT,
  rank REAL
) AS $$
BEGIN
  RETURN QUERY
  SELECT 
    e.id,
    e.subject,
    e.sender_email,
    e.sender_name,
    e.sent_date,
    e.folder_path,
    ts_rank(
      to_tsvector('english', COALESCE(e.subject, '') || ' ' || COALESCE(e.body_text, '')),
      plainto_tsquery('english', search_query)
    ) as rank
  FROM emails e
  WHERE to_tsvector('english', COALESCE(e.subject, '') || ' ' || COALESCE(e.body_text, ''))
    @@ plainto_tsquery('english', search_query)
  ORDER BY rank DESC
  LIMIT limit_count;
END;
$$ LANGUAGE plpgsql;

-- Email statistics by folder (with mailbox support)
CREATE VIEW folder_stats AS
SELECT 
  f.mailbox_id,
  m.name as mailbox_name,
  f.folder_path,
  f.folder_type,
  COUNT(e.id) as email_count,
  COUNT(CASE WHEN e.is_outbound THEN 1 END) as outbound_count,
  COUNT(CASE WHEN NOT e.is_outbound THEN 1 END) as inbound_count,
  MIN(e.sent_date) as earliest_email,
  MAX(e.sent_date) as latest_email
FROM folders f
LEFT JOIN emails e ON f.folder_path = e.folder_path AND f.mailbox_id = e.mailbox_id
LEFT JOIN mailboxes m ON f.mailbox_id = m.id
GROUP BY f.mailbox_id, m.name, f.folder_path, f.folder_type;

-- Daily email volume (with mailbox support)
CREATE VIEW daily_email_volume AS
SELECT 
  e.mailbox_id,
  m.name as mailbox_name,
  DATE(e.sent_date) as date,
  COUNT(*) as total_emails,
  COUNT(CASE WHEN e.is_outbound THEN 1 END) as outbound,
  COUNT(CASE WHEN NOT e.is_outbound THEN 1 END) as inbound,
  COUNT(DISTINCT e.sender_email) as unique_senders,
  COUNT(CASE WHEN e.is_reply THEN 1 END) as replies
FROM emails e
JOIN mailboxes m ON e.mailbox_id = m.id
WHERE e.sent_date IS NOT NULL
GROUP BY e.mailbox_id, m.name, DATE(e.sent_date)
ORDER BY date DESC;

-- Top correspondents (with mailbox support)
CREATE VIEW top_correspondents AS
SELECT 
  e.mailbox_id,
  m.name as mailbox_name,
  e.sender_email,
  e.sender_name,
  COUNT(*) as email_count,
  MIN(e.sent_date) as first_email,
  MAX(e.sent_date) as last_email,
  COUNT(CASE WHEN e.is_reply THEN 1 END) as reply_count,
  AVG(e.message_size) as avg_message_size
FROM emails e
JOIN mailboxes m ON e.mailbox_id = m.id
WHERE e.sender_email IS NOT NULL AND e.sender_email != ''
GROUP BY e.mailbox_id, m.name, e.sender_email, e.sender_name
ORDER BY email_count DESC;

-- Thread analysis view (with mailbox support)
CREATE VIEW thread_stats AS
SELECT 
  e.mailbox_id,
  m.name as mailbox_name,
  e.thread_id,
  COUNT(*) as message_count,
  MIN(e.sent_date) as thread_start,
  MAX(e.sent_date) as thread_end,
  COUNT(DISTINCT e.sender_email) as participant_count,
  COUNT(CASE WHEN e.is_outbound THEN 1 END) as outbound_messages,
  COUNT(CASE WHEN NOT e.is_outbound THEN 1 END) as inbound_messages
FROM emails e
JOIN mailboxes m ON e.mailbox_id = m.id
WHERE e.thread_id IS NOT NULL
GROUP BY e.mailbox_id, m.name, e.thread_id
HAVING COUNT(*) > 1  -- Only show actual threads
ORDER BY message_count DESC;

-- Note: Default folders will be created per mailbox through application logic
-- INSERT INTO folders (folder_path, folder_type, mailbox_id) VALUES 
-- ('INBOX', 'inbox', <mailbox_id>), etc.

-- Function to update folder message counts (with mailbox support)
CREATE OR REPLACE FUNCTION update_folder_counts()
RETURNS void AS $$
BEGIN
  -- Update per-mailbox folder counts
  UPDATE folders f
  SET message_count = (
    SELECT COUNT(*)
    FROM emails e
    WHERE e.folder_path = f.folder_path
    AND e.mailbox_id = f.mailbox_id
  )
  WHERE f.id IS NOT NULL;  -- Add WHERE clause for RLS compatibility

  -- Update mailbox totals
  UPDATE mailboxes m
  SET total_emails = (
    SELECT COUNT(*)
    FROM emails e
    WHERE e.mailbox_id = m.id
  )
  WHERE m.id IS NOT NULL;  -- Add WHERE clause for RLS compatibility
END;
$$ LANGUAGE plpgsql;

-- Grant execute permission to anon and authenticated roles
GRANT EXECUTE ON FUNCTION update_folder_counts() TO anon, authenticated;

COMMENT ON FUNCTION update_folder_counts() IS 'Updates message counts in folders table and total_emails in mailboxes table';

-- Grant table permissions for email processing
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE emails TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE email_categories TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE folders TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE mailboxes TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE processing_jobs TO anon, authenticated;

-- RLS (Row Level Security) policies for multi-tenant usage (if needed)
-- ALTER TABLE emails ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE folders ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE email_categories ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE email_enrichment ENABLE ROW LEVEL SECURITY;

-- Grant permissions (adjust based on your Supabase setup)
-- GRANT ALL ON ALL TABLES IN SCHEMA public TO authenticated;
-- GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO authenticated;

-- Note: ANALYZE statements moved to end of file to run after all tables are created

-- =========================================================================
-- Helper Functions for Filter Dropdowns (Performance Optimization)
-- =========================================================================

-- Function to get distinct folder names efficiently
CREATE OR REPLACE FUNCTION get_distinct_folders()
RETURNS TABLE (folder_path TEXT)
LANGUAGE sql
STABLE
AS $$
  SELECT DISTINCT emails.folder_path
  FROM emails
  WHERE emails.folder_path IS NOT NULL
  ORDER BY emails.folder_path;
$$;

-- Grant execute permission to anon and authenticated roles
GRANT EXECUTE ON FUNCTION get_distinct_folders() TO anon, authenticated;

COMMENT ON FUNCTION get_distinct_folders() IS 'Returns distinct folder paths from emails table for filter dropdowns - much faster than fetching all rows';

-- Function to get mailbox names efficiently
CREATE OR REPLACE FUNCTION get_distinct_mailboxes()
RETURNS TABLE (id UUID, name TEXT)
LANGUAGE sql
STABLE
AS $$
  SELECT DISTINCT m.id, m.name
  FROM mailboxes m
  WHERE m.name IS NOT NULL
  ORDER BY m.name;
$$;

-- Grant execute permission to anon and authenticated roles
GRANT EXECUTE ON FUNCTION get_distinct_mailboxes() TO anon, authenticated;

COMMENT ON FUNCTION get_distinct_mailboxes() IS 'Returns mailbox names for filter dropdowns';

-- =========================================================================
-- Stage 2 Phase 2: Business Hierarchy Tables
-- =========================================================================

-- Account Managers (Platform Users)
CREATE TABLE IF NOT EXISTS account_managers (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name TEXT NOT NULL,
  email TEXT UNIQUE NOT NULL,
  role TEXT NOT NULL DEFAULT 'account_manager',
  password_hash TEXT,
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE account_managers IS 'Platform users who manage client relationships';

-- Clients (Consulting Clients)
CREATE TABLE IF NOT EXISTS clients (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  account_manager_id UUID REFERENCES account_managers(id) ON DELETE SET NULL,
  client_name TEXT NOT NULL,
  client_label TEXT,
  industry TEXT,
  status TEXT DEFAULT 'active',
  uses_quickbase BOOLEAN DEFAULT FALSE,
  quickbase_realm TEXT,
  quickbase_api_token TEXT,
  uses_printiq BOOLEAN DEFAULT FALSE,
  printiq_api_url TEXT,
  printiq_api_key TEXT,
  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE clients IS 'Consulting clients of the platform';

-- Customer Companies (Each Client's Customers)
CREATE TABLE IF NOT EXISTS customer_companies (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  company_name TEXT NOT NULL,
  email_domains JSONB DEFAULT '[]'::jsonb,
  industry TEXT,
  website TEXT,
  first_contact_date TIMESTAMPTZ,
  last_contact_date TIMESTAMPTZ,
  total_emails INTEGER DEFAULT 0,
  total_inbound INTEGER DEFAULT 0,
  total_outbound INTEGER DEFAULT 0,
  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  CONSTRAINT customer_companies_client_name_unique UNIQUE (client_id, company_name)
);

COMMENT ON TABLE customer_companies IS 'Customer companies belonging to each client';

-- Customer Contacts (Individuals at Customer Companies)
CREATE TABLE IF NOT EXISTS customer_contacts (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  customer_company_id UUID REFERENCES customer_companies(id) ON DELETE CASCADE,
  client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
  email_address TEXT NOT NULL,
  full_name TEXT,
  first_name TEXT,
  last_name TEXT,
  job_title TEXT,
  company_name TEXT,
  phone_number TEXT,
  mobile_number TEXT,
  linkedin_url TEXT,
  first_contacted_at TIMESTAMPTZ,
  last_contacted_at TIMESTAMPTZ,
  total_emails_sent INTEGER DEFAULT 0,
  total_emails_received INTEGER DEFAULT 0,
  signature_data JSONB,
  signature_last_updated TIMESTAMPTZ,
  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  CONSTRAINT customer_contacts_company_email_unique UNIQUE (customer_company_id, email_address)
);

COMMENT ON TABLE customer_contacts IS 'Individual contacts at customer companies';

-- Customer Recognition Rules
CREATE TABLE IF NOT EXISTS customer_recognition_rules (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
  customer_company_id UUID REFERENCES customer_companies(id) ON DELETE CASCADE,
  rule_name TEXT NOT NULL,
  rule_type TEXT NOT NULL,
  pattern TEXT NOT NULL,
  priority INTEGER DEFAULT 0,
  is_active BOOLEAN DEFAULT TRUE,
  match_count INTEGER DEFAULT 0,
  last_matched_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE customer_recognition_rules IS 'Rules for automatically matching emails to customer companies';

-- Business hierarchy indexes
CREATE INDEX IF NOT EXISTS idx_account_managers_email ON account_managers(email);
CREATE INDEX IF NOT EXISTS idx_account_managers_active ON account_managers(is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_clients_account_manager ON clients(account_manager_id);
CREATE INDEX IF NOT EXISTS idx_clients_status ON clients(status);
CREATE INDEX IF NOT EXISTS idx_clients_label ON clients(client_label);
CREATE INDEX IF NOT EXISTS idx_customer_companies_client ON customer_companies(client_id);
CREATE INDEX IF NOT EXISTS idx_customer_companies_name ON customer_companies(company_name);
CREATE INDEX IF NOT EXISTS idx_customer_companies_last_contact ON customer_companies(last_contact_date DESC);
CREATE INDEX IF NOT EXISTS idx_customer_contacts_company ON customer_contacts(customer_company_id);
CREATE INDEX IF NOT EXISTS idx_customer_contacts_client ON customer_contacts(client_id);
CREATE INDEX IF NOT EXISTS idx_customer_contacts_email ON customer_contacts(email_address);
CREATE INDEX IF NOT EXISTS idx_customer_contacts_last_contact ON customer_contacts(last_contacted_at DESC);
CREATE INDEX IF NOT EXISTS idx_rules_client ON customer_recognition_rules(client_id);
CREATE INDEX IF NOT EXISTS idx_rules_customer ON customer_recognition_rules(customer_company_id);
CREATE INDEX IF NOT EXISTS idx_rules_type ON customer_recognition_rules(rule_type);
CREATE INDEX IF NOT EXISTS idx_rules_active ON customer_recognition_rules(is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_rules_priority ON customer_recognition_rules(priority DESC);
CREATE INDEX IF NOT EXISTS idx_mailboxes_client ON mailboxes(client_id);
CREATE INDEX IF NOT EXISTS idx_mailboxes_account_manager ON mailboxes(account_manager_id);
CREATE INDEX IF NOT EXISTS idx_customer_companies_domains_gin ON customer_companies USING gin(email_domains);

-- Business hierarchy update triggers
CREATE TRIGGER update_account_managers_updated_at BEFORE UPDATE
    ON account_managers FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_clients_updated_at BEFORE UPDATE
    ON clients FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_customer_companies_updated_at BEFORE UPDATE
    ON customer_companies FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_customer_contacts_updated_at BEFORE UPDATE
    ON customer_contacts FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_customer_recognition_rules_updated_at BEFORE UPDATE
    ON customer_recognition_rules FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Business hierarchy permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE account_managers TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE clients TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE customer_companies TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE customer_contacts TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE customer_recognition_rules TO anon, authenticated;

-- Note: ANALYZE statements moved to end of file

-- =========================================================================
-- Stage 2: Error Handling Functions
-- =========================================================================

-- Function to get error summary for a job/mailbox
CREATE OR REPLACE FUNCTION get_job_error_summary(p_mailbox_id UUID)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    result JSONB;
BEGIN
    SELECT jsonb_build_object(
        'total_errors', COUNT(*) FILTER (WHERE processing_status = 'failed'),
        'total_success', COUNT(*) FILTER (WHERE processing_status = 'success'),
        'total_pending', COUNT(*) FILTER (WHERE processing_status = 'pending'),
        'total_skipped', COUNT(*) FILTER (WHERE processing_status = 'skipped'),
        'error_types', (
            SELECT COALESCE(jsonb_object_agg(error_type, error_count), '{}'::jsonb)
            FROM (
                SELECT
                    COALESCE(
                        CASE
                            WHEN processing_error LIKE '%encoding%' OR processing_error LIKE '%decode%' THEN 'encoding_error'
                            WHEN processing_error LIKE '%parse%' OR processing_error LIKE '%Parse%' THEN 'parse_error'
                            WHEN processing_error LIKE '%timeout%' OR processing_error LIKE '%Timeout%' THEN 'timeout_error'
                            WHEN processing_error LIKE '%connection%' OR processing_error LIKE '%Connection%' THEN 'connection_error'
                            WHEN processing_error LIKE '%duplicate%' OR processing_error LIKE '%Duplicate%' THEN 'duplicate_error'
                            ELSE 'other_error'
                        END,
                        'unknown'
                    ) as error_type,
                    COUNT(*) as error_count
                FROM emails
                WHERE mailbox_id = p_mailbox_id AND processing_status = 'failed'
                GROUP BY 1
            ) error_counts
        )
    ) INTO result
    FROM emails
    WHERE mailbox_id = p_mailbox_id;

    RETURN result;
END;
$$;

GRANT EXECUTE ON FUNCTION get_job_error_summary(UUID) TO anon, authenticated;
COMMENT ON FUNCTION get_job_error_summary(UUID) IS 'Returns aggregated error summary for a mailbox/job';

-- Function to get failed emails with details
CREATE OR REPLACE FUNCTION get_failed_emails(
    p_mailbox_id UUID,
    p_limit INTEGER DEFAULT 100,
    p_offset INTEGER DEFAULT 0
)
RETURNS TABLE (
    id UUID,
    message_id TEXT,
    subject TEXT,
    sender_email TEXT,
    sent_date TIMESTAMPTZ,
    processing_error TEXT,
    processing_attempts INTEGER,
    last_processing_attempt TIMESTAMPTZ
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        e.id,
        e.message_id,
        e.subject,
        e.sender_email,
        e.sent_date,
        e.processing_error,
        e.processing_attempts,
        e.last_processing_attempt
    FROM emails e
    WHERE e.mailbox_id = p_mailbox_id
      AND e.processing_status = 'failed'
    ORDER BY e.last_processing_attempt DESC NULLS LAST, e.sent_date DESC
    LIMIT p_limit
    OFFSET p_offset;
$$;

GRANT EXECUTE ON FUNCTION get_failed_emails(UUID, INTEGER, INTEGER) TO anon, authenticated;
COMMENT ON FUNCTION get_failed_emails(UUID, INTEGER, INTEGER) IS 'Returns paginated list of failed emails for a mailbox';

-- Function to reset failed emails for retry
CREATE OR REPLACE FUNCTION reset_failed_emails_for_retry(
    p_mailbox_id UUID,
    p_max_attempts INTEGER DEFAULT 3
)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    updated_count INTEGER;
BEGIN
    UPDATE emails
    SET
        processing_status = 'pending',
        processing_error = NULL
    WHERE mailbox_id = p_mailbox_id
      AND processing_status = 'failed'
      AND processing_attempts < p_max_attempts;

    GET DIAGNOSTICS updated_count = ROW_COUNT;
    RETURN updated_count;
END;
$$;

GRANT EXECUTE ON FUNCTION reset_failed_emails_for_retry(UUID, INTEGER) TO anon, authenticated;
COMMENT ON FUNCTION reset_failed_emails_for_retry(UUID, INTEGER) IS 'Resets failed emails to pending status for retry (respects max attempt limit)';

-- =========================================================================
-- Stage 2: Job Errors Table (Comprehensive Error Logging)
-- =========================================================================

-- Job errors table for detailed error tracking
-- Stores ALL errors (download, extraction, processing, categorization) in one place
CREATE TABLE IF NOT EXISTS job_errors (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  job_id UUID NOT NULL REFERENCES processing_jobs(id) ON DELETE CASCADE,
  mailbox_id UUID REFERENCES mailboxes(id) ON DELETE SET NULL,

  -- Error classification
  error_phase TEXT NOT NULL,  -- download, extraction, normalization, tagging, database, categorization
  error_type TEXT NOT NULL,   -- encoding_error, parse_error, network_error, timeout_error, auth_error, etc.
  error_severity TEXT NOT NULL DEFAULT 'error',  -- warning, error, critical

  -- Error details
  error_message TEXT NOT NULL,
  error_stack TEXT,           -- Full stack trace (truncated to 4000 chars)

  -- Context (what was being processed when error occurred)
  context_type TEXT,          -- file, chunk, email, batch
  context_id TEXT,            -- file_id, chunk_index, message_id, batch_number
  context_details JSONB,      -- Additional context: {file_name, chunk_start, chunk_end, email_subject, etc.}

  -- Retry tracking
  is_retryable BOOLEAN DEFAULT TRUE,
  retry_count INTEGER DEFAULT 0,
  max_retries INTEGER DEFAULT 3,
  last_retry_at TIMESTAMPTZ,
  resolved_at TIMESTAMPTZ,    -- When error was resolved (successful retry or manual resolution)
  resolution_type TEXT,       -- auto_retry, manual_skip, manual_fix

  -- Timestamps
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for job_errors table
CREATE INDEX IF NOT EXISTS idx_job_errors_job_id ON job_errors(job_id);
CREATE INDEX IF NOT EXISTS idx_job_errors_mailbox_id ON job_errors(mailbox_id);
CREATE INDEX IF NOT EXISTS idx_job_errors_phase ON job_errors(error_phase);
CREATE INDEX IF NOT EXISTS idx_job_errors_type ON job_errors(error_type);
CREATE INDEX IF NOT EXISTS idx_job_errors_severity ON job_errors(error_severity);
CREATE INDEX IF NOT EXISTS idx_job_errors_created ON job_errors(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_job_errors_unresolved ON job_errors(job_id, resolved_at) WHERE resolved_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_job_errors_retryable ON job_errors(job_id, is_retryable) WHERE is_retryable = TRUE AND resolved_at IS NULL;

-- Trigger to update updated_at
CREATE TRIGGER update_job_errors_updated_at BEFORE UPDATE
    ON job_errors FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Grant permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE job_errors TO anon, authenticated;

-- Comments
COMMENT ON TABLE job_errors IS 'Comprehensive error logging for all processing job errors';
COMMENT ON COLUMN job_errors.error_phase IS 'Processing phase: download, extraction, normalization, tagging, database, categorization';
COMMENT ON COLUMN job_errors.error_type IS 'Error classification: encoding_error, parse_error, network_error, timeout_error, auth_error, connection_error, duplicate_error, permission_error, memory_error, validation_error, other_error';
COMMENT ON COLUMN job_errors.context_type IS 'What was being processed: file, chunk, email, batch';
COMMENT ON COLUMN job_errors.context_details IS 'JSON with context-specific details like file_name, chunk_index, email_subject';

-- Function to get error summary for a job (from job_errors table)
CREATE OR REPLACE FUNCTION get_job_errors_summary(p_job_id UUID)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    result JSONB;
BEGIN
    SELECT jsonb_build_object(
        'total_errors', COUNT(*),
        'unresolved_errors', COUNT(*) FILTER (WHERE resolved_at IS NULL),
        'retryable_errors', COUNT(*) FILTER (WHERE is_retryable = TRUE AND resolved_at IS NULL),
        'by_phase', (
            SELECT COALESCE(jsonb_object_agg(phase, cnt), '{}'::jsonb)
            FROM (
                SELECT error_phase as phase, COUNT(*) as cnt
                FROM job_errors
                WHERE job_id = p_job_id
                GROUP BY error_phase
            ) phase_counts
        ),
        'by_type', (
            SELECT COALESCE(jsonb_object_agg(etype, cnt), '{}'::jsonb)
            FROM (
                SELECT error_type as etype, COUNT(*) as cnt
                FROM job_errors
                WHERE job_id = p_job_id
                GROUP BY error_type
            ) type_counts
        ),
        'by_severity', (
            SELECT COALESCE(jsonb_object_agg(sev, cnt), '{}'::jsonb)
            FROM (
                SELECT error_severity as sev, COUNT(*) as cnt
                FROM job_errors
                WHERE job_id = p_job_id
                GROUP BY error_severity
            ) severity_counts
        ),
        'recent_errors', (
            SELECT COALESCE(jsonb_agg(err), '[]'::jsonb)
            FROM (
                SELECT jsonb_build_object(
                    'id', id,
                    'phase', error_phase,
                    'type', error_type,
                    'severity', error_severity,
                    'message', LEFT(error_message, 200),
                    'context_type', context_type,
                    'context_id', context_id,
                    'created_at', created_at
                ) as err
                FROM job_errors
                WHERE job_id = p_job_id
                ORDER BY created_at DESC
                LIMIT 10
            ) recent
        )
    ) INTO result;

    RETURN result;
END;
$$;

GRANT EXECUTE ON FUNCTION get_job_errors_summary(UUID) TO anon, authenticated;
COMMENT ON FUNCTION get_job_errors_summary(UUID) IS 'Returns comprehensive error summary for a job from job_errors table';

-- Function to get paginated errors for a job
CREATE OR REPLACE FUNCTION get_job_errors_paginated(
    p_job_id UUID,
    p_phase TEXT DEFAULT NULL,
    p_type TEXT DEFAULT NULL,
    p_unresolved_only BOOLEAN DEFAULT FALSE,
    p_limit INTEGER DEFAULT 50,
    p_offset INTEGER DEFAULT 0
)
RETURNS TABLE (
    id UUID,
    error_phase TEXT,
    error_type TEXT,
    error_severity TEXT,
    error_message TEXT,
    error_stack TEXT,
    context_type TEXT,
    context_id TEXT,
    context_details JSONB,
    is_retryable BOOLEAN,
    retry_count INTEGER,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        je.id,
        je.error_phase,
        je.error_type,
        je.error_severity,
        je.error_message,
        je.error_stack,
        je.context_type,
        je.context_id,
        je.context_details,
        je.is_retryable,
        je.retry_count,
        je.resolved_at,
        je.created_at
    FROM job_errors je
    WHERE je.job_id = p_job_id
      AND (p_phase IS NULL OR je.error_phase = p_phase)
      AND (p_type IS NULL OR je.error_type = p_type)
      AND (NOT p_unresolved_only OR je.resolved_at IS NULL)
    ORDER BY je.created_at DESC
    LIMIT p_limit
    OFFSET p_offset;
$$;

GRANT EXECUTE ON FUNCTION get_job_errors_paginated(UUID, TEXT, TEXT, BOOLEAN, INTEGER, INTEGER) TO anon, authenticated;
COMMENT ON FUNCTION get_job_errors_paginated(UUID, TEXT, TEXT, BOOLEAN, INTEGER, INTEGER) IS 'Returns paginated errors for a job with optional filters';

-- =========================================================================
-- Stage 2: Downloaded Files Table (Cache Tracking)
-- =========================================================================

-- Tracks downloaded files to avoid re-downloading when re-processing
-- Works with both local development and cloud storage (Railway)
CREATE TABLE IF NOT EXISTS downloaded_files (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

  -- Source identification
  google_drive_file_id TEXT NOT NULL,
  file_name TEXT NOT NULL,
  file_size BIGINT NOT NULL,

  -- Storage location
  -- For local: file path (e.g., C:\temp\file.olm)
  -- For cloud: storage URL (e.g., s3://bucket/path or supabase storage URL)
  storage_type TEXT NOT NULL DEFAULT 'local',  -- local, s3, r2, supabase
  storage_path TEXT NOT NULL,

  -- Integrity
  checksum TEXT,  -- MD5 or SHA256 for verification

  -- Association
  mailbox_id UUID REFERENCES mailboxes(id) ON DELETE SET NULL,
  last_job_id UUID REFERENCES processing_jobs(id) ON DELETE SET NULL,

  -- Lifecycle
  downloaded_at TIMESTAMPTZ DEFAULT NOW(),
  last_used_at TIMESTAMPTZ DEFAULT NOW(),
  expires_at TIMESTAMPTZ,  -- Optional auto-cleanup
  keep_file BOOLEAN DEFAULT FALSE,  -- If true, don't auto-delete

  -- Status
  is_valid BOOLEAN DEFAULT TRUE,  -- Set to false if file is deleted/corrupted

  -- Timestamps
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),

  -- Unique constraint: one entry per Google Drive file
  UNIQUE(google_drive_file_id)
);

-- Indexes for downloaded_files table
CREATE INDEX IF NOT EXISTS idx_downloaded_files_gdrive_id ON downloaded_files(google_drive_file_id);
CREATE INDEX IF NOT EXISTS idx_downloaded_files_mailbox ON downloaded_files(mailbox_id);
CREATE INDEX IF NOT EXISTS idx_downloaded_files_valid ON downloaded_files(is_valid) WHERE is_valid = TRUE;
CREATE INDEX IF NOT EXISTS idx_downloaded_files_expires ON downloaded_files(expires_at) WHERE expires_at IS NOT NULL;

-- Trigger for updated_at
CREATE TRIGGER update_downloaded_files_updated_at BEFORE UPDATE
    ON downloaded_files FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE downloaded_files TO anon, authenticated;

-- Comments
COMMENT ON TABLE downloaded_files IS 'Tracks downloaded files to enable re-processing without re-downloading';
COMMENT ON COLUMN downloaded_files.storage_type IS 'Where file is stored: local, s3, r2, supabase';
COMMENT ON COLUMN downloaded_files.storage_path IS 'Full path or URL to the stored file';
COMMENT ON COLUMN downloaded_files.keep_file IS 'If true, do not auto-delete after processing';

-- Function to check if a cached file exists and is valid
CREATE OR REPLACE FUNCTION get_cached_download(p_google_drive_file_id TEXT)
RETURNS TABLE (
  id UUID,
  file_name TEXT,
  file_size BIGINT,
  storage_type TEXT,
  storage_path TEXT,
  downloaded_at TIMESTAMPTZ,
  last_used_at TIMESTAMPTZ,
  is_valid BOOLEAN,
  age_hours NUMERIC
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    df.id,
    df.file_name,
    df.file_size,
    df.storage_type,
    df.storage_path,
    df.downloaded_at,
    df.last_used_at,
    df.is_valid,
    EXTRACT(EPOCH FROM (NOW() - df.downloaded_at)) / 3600 as age_hours
  FROM downloaded_files df
  WHERE df.google_drive_file_id = p_google_drive_file_id
    AND df.is_valid = TRUE
    AND (df.expires_at IS NULL OR df.expires_at > NOW())
  LIMIT 1;
$$;

GRANT EXECUTE ON FUNCTION get_cached_download(TEXT) TO anon, authenticated;

-- Function to mark a download as used (updates last_used_at)
CREATE OR REPLACE FUNCTION mark_download_used(p_download_id UUID)
RETURNS VOID
LANGUAGE sql
AS $$
  UPDATE downloaded_files
  SET last_used_at = NOW()
  WHERE id = p_download_id;
$$;

GRANT EXECUTE ON FUNCTION mark_download_used(UUID) TO anon, authenticated;

-- Function to invalidate a cached download
CREATE OR REPLACE FUNCTION invalidate_download(p_download_id UUID)
RETURNS VOID
LANGUAGE sql
AS $$
  UPDATE downloaded_files
  SET is_valid = FALSE
  WHERE id = p_download_id;
$$;

GRANT EXECUTE ON FUNCTION invalidate_download(UUID) TO anon, authenticated;

-- =========================================================================
-- Stage 2: Gmail LIVE Integration
-- =========================================================================

-- Gmail filters table - stores imported Gmail filters for visibility
-- Used by S1-08 (Import existing Gmail filters)
CREATE TABLE IF NOT EXISTS gmail_filters (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT NOT NULL,           -- User who owns this filter
    filter_id TEXT NOT NULL,         -- Gmail's filter ID
    criteria JSONB NOT NULL,         -- Filter criteria: {from, to, subject, hasAttachment, query, etc.}
    action JSONB NOT NULL,           -- Filter action: {addLabelIds, removeLabelIds, forward, etc.}
    is_active BOOLEAN DEFAULT TRUE,  -- Whether filter is currently active
    imported_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, filter_id)
);

-- Index for fast lookup by user
CREATE INDEX IF NOT EXISTS idx_gmail_filters_user ON gmail_filters(user_id);

-- Trigger to update updated_at
CREATE TRIGGER update_gmail_filters_updated_at BEFORE UPDATE
    ON gmail_filters FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gmail_filters TO anon, authenticated;

COMMENT ON TABLE gmail_filters IS 'Gmail filters imported via API to understand email organization rules (Stage 2 S1-08)';
COMMENT ON COLUMN gmail_filters.criteria IS 'Gmail filter criteria: {from, to, subject, hasAttachment, query, negatedQuery, size, sizeComparison}';
COMMENT ON COLUMN gmail_filters.action IS 'Gmail filter action: {addLabelIds, removeLabelIds, forward, markAsRead, markImportant}';

-- =========================================================================
-- Performance Optimization (Final Section)
-- =========================================================================

-- Critical index for batch upsert operations (message_id + mailbox_id lookups)
-- This dramatically improves upsert performance for large mailboxes
CREATE INDEX IF NOT EXISTS idx_emails_message_mailbox_upsert
ON emails(message_id, mailbox_id);

-- Index for faster sent_date range queries (common filter)
CREATE INDEX IF NOT EXISTS idx_emails_sent_date_desc
ON emails(sent_date DESC NULLS LAST);

-- Partial index for active/recent jobs (reduces index size)
CREATE INDEX IF NOT EXISTS idx_processing_jobs_active
ON processing_jobs(status, created_at DESC)
WHERE status IN ('pending', 'running', 'paused');

-- =========================================================================
-- Table Statistics (Run after data is loaded for optimal query planning)
-- =========================================================================
-- Note: These ANALYZE commands update PostgreSQL's query planner statistics.
-- For best performance, run ANALYZE after bulk data imports.
-- They are safe to skip during initial setup (empty tables).

-- Wrap in DO block to prevent failures on empty tables
-- NOTE: ANALYZE on large tables (emails with 100k+ rows) can timeout in Supabase SQL Editor.
-- PostgreSQL auto-vacuum handles statistics updates automatically for large tables.
-- We only run ANALYZE on smaller tables here.
DO $$
BEGIN
    -- Skip large tables - auto-vacuum handles these
    -- ANALYZE emails;  -- Skip - can have 100k+ rows
    -- ANALYZE email_categories;  -- Skip - can have 100k+ rows

    -- Smaller tables - safe to analyze
    ANALYZE processing_jobs;
    ANALYZE mailboxes;
    ANALYZE folders;

    -- Business hierarchy tables
    ANALYZE account_managers;
    ANALYZE clients;
    ANALYZE customer_companies;
    ANALYZE customer_contacts;
    ANALYZE customer_recognition_rules;

    -- Support tables
    ANALYZE job_errors;
    ANALYZE downloaded_files;
    ANALYZE user_integrations;
    ANALYZE gmail_filters;
EXCEPTION WHEN OTHERS THEN
    -- Ignore errors from empty tables or missing tables
    RAISE NOTICE 'ANALYZE completed with some skipped tables (this is normal for fresh installs)';
END;
$$;

-- =========================================================================
-- Performance Recommendations
-- =========================================================================
--
-- For optimal performance with large mailboxes (100k+ emails):
--
-- 1. Supabase Connection Pooling (Dashboard → Settings → Database):
--    - Enable PgBouncer: Yes
--    - Pool Mode: Transaction
--    - Pool Size: 15-20
--
-- 2. Use the Pooler connection string for your application
--
-- 3. After bulk imports, run: ANALYZE emails; ANALYZE email_categories;
--
-- 4. For very large tables, consider partitioning by mailbox_id or date
--
-- =========================================================================