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
  total_emails INTEGER DEFAULT 0
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

-- User integrations performance indexes
CREATE INDEX idx_user_integrations_token_expires ON user_integrations(token_expires_at) WHERE token_expires_at IS NOT NULL;

-- Full-text search indexes
CREATE INDEX idx_emails_subject_fts ON emails USING gin(to_tsvector('english', subject));
CREATE INDEX idx_emails_body_fts ON emails USING gin(to_tsvector('english', COALESCE(body_text, '')));

-- Trigram indexes for partial text matching
CREATE INDEX idx_emails_sender_email_gin ON emails USING gin(sender_email gin_trgm_ops);
CREATE INDEX idx_emails_subject_gin ON emails USING gin(subject gin_trgm_ops);

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
  );
  
  -- Update mailbox totals
  UPDATE mailboxes m
  SET total_emails = (
    SELECT COUNT(*)
    FROM emails e
    WHERE e.mailbox_id = m.id
  );
END;
$$ LANGUAGE plpgsql;

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