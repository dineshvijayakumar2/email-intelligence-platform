-- Migration 086: Thread-QB Journey Links
-- Links email threads to QuickBase quotes, jobs, and invoices.
-- Populated by regex extraction, AI analysis, or manual AM linkage.

CREATE TABLE IF NOT EXISTS thread_qb_links (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id UUID NOT NULL REFERENCES clients(id),
  canonical_thread_id TEXT NOT NULL,
  link_type TEXT NOT NULL,
  qb_record_id TEXT NOT NULL,
  qb_reference TEXT,
  confidence FLOAT DEFAULT 1.0,
  source TEXT NOT NULL,
  verified BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(client_id, canonical_thread_id, link_type, qb_record_id)
);

CREATE INDEX idx_thread_qb_links_thread
  ON thread_qb_links(client_id, canonical_thread_id);

CREATE INDEX idx_thread_qb_links_record
  ON thread_qb_links(link_type, qb_record_id);

CREATE INDEX idx_thread_qb_links_unverified
  ON thread_qb_links(created_at)
  WHERE verified = FALSE AND confidence < 1.0;

-- Add extracted_references column to ai_email_intelligence for AI-sourced refs
ALTER TABLE ai_email_intelligence
  ADD COLUMN IF NOT EXISTS extracted_references JSONB;
