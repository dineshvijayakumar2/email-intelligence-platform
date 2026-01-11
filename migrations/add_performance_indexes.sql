-- Performance optimization indexes for email intelligence platform
-- These indexes improve query performance for common operations

-- Email categories table indexes (critical for tag queries)
CREATE INDEX IF NOT EXISTS idx_email_categories_email_id ON email_categories(email_id);
CREATE INDEX IF NOT EXISTS idx_email_categories_category ON email_categories(category);
CREATE INDEX IF NOT EXISTS idx_email_categories_email_category ON email_categories(email_id, category);

-- Additional email table indexes for filtering (removed - columns don't exist in current schema)

-- Composite indexes for common filter combinations
CREATE INDEX IF NOT EXISTS idx_emails_mailbox_date_outbound ON emails(mailbox_id, sent_date DESC, is_outbound);
CREATE INDEX IF NOT EXISTS idx_emails_mailbox_sender_date ON emails(mailbox_id, sender_email, sent_date DESC);
CREATE INDEX IF NOT EXISTS idx_emails_mailbox_folder_outbound ON emails(mailbox_id, folder_path, is_outbound);

-- Processing jobs performance indexes
CREATE INDEX IF NOT EXISTS idx_processing_jobs_status ON processing_jobs(status);
CREATE INDEX IF NOT EXISTS idx_processing_jobs_type_status ON processing_jobs(job_type, status);
CREATE INDEX IF NOT EXISTS idx_processing_jobs_created_at ON processing_jobs(created_at DESC);

-- User integrations performance indexes
CREATE INDEX IF NOT EXISTS idx_user_integrations_token_expires ON user_integrations(token_expires_at) WHERE token_expires_at IS NOT NULL;

-- Covering index for common email queries (includes frequently selected columns)
CREATE INDEX IF NOT EXISTS idx_emails_coverage_main ON emails(mailbox_id, sent_date DESC) 
  INCLUDE (id, subject, sender_email, sender_name, is_outbound, is_reply, folder_path, message_size);

-- Covering index for email categories batch queries
CREATE INDEX IF NOT EXISTS idx_email_categories_coverage ON email_categories(email_id) 
  INCLUDE (category, confidence, detection_method);

-- Note: Trigram indexes require pg_trgm extension - enable manually if needed:
-- CREATE EXTENSION IF NOT EXISTS pg_trgm;
-- CREATE INDEX IF NOT EXISTS idx_emails_sender_email_gin ON emails USING gin(sender_email gin_trgm_ops);
-- CREATE INDEX IF NOT EXISTS idx_emails_subject_gin ON emails USING gin(subject gin_trgm_ops);

-- Update table statistics for better query planning
ANALYZE emails;
ANALYZE email_categories;
ANALYZE processing_jobs;
ANALYZE mailboxes;
ANALYZE folders;