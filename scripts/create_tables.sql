-- Email Intelligence Platform Database Schema
-- PostgreSQL / Supabase

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable trigram extension for better text search
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Mailboxes table for multi-mailbox support
CREATE TABLE mailboxes (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name TEXT NOT NULL,
  email_address TEXT UNIQUE,  -- Optional: not required for file-based mailboxes (MBOX/PST/OLM)
  mailbox_type TEXT NOT NULL CHECK (mailbox_type IN ('mbox', 'pst', 'olm')),  -- File-based formats only
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
  confidence DECIMAL(3,2) DEFAULT 1.0,
  detection_method TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(email_id, category)
);

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
  error_log JSONB,
  -- Stage 2: Error summary for aggregated error tracking
  error_summary JSONB,  -- {total_errors, error_types: {type: count}, sample_errors: [...]}
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- User integrations for OAuth2 token storage (Google Drive, etc.)
CREATE TABLE user_integrations (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id TEXT NOT NULL,  -- User identifier (string format for flexibility)
  provider TEXT NOT NULL CHECK (provider IN ('google_drive', 'microsoft', 'dropbox')),
  access_token TEXT NOT NULL,     -- Current access token
  refresh_token TEXT NOT NULL,    -- Long-lived refresh token
  token_expires_at TIMESTAMPTZ,   -- When access token expires
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

-- Update table statistics for better query planning
ANALYZE emails;
ANALYZE email_categories;
ANALYZE processing_jobs;
ANALYZE mailboxes;
ANALYZE folders;

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

-- Update statistics for business hierarchy tables
ANALYZE account_managers;
ANALYZE clients;
ANALYZE customer_companies;
ANALYZE customer_contacts;
ANALYZE customer_recognition_rules;