-- ============================================================================
-- Migration 021a: Platform Surgery — QB Enrichment Columns
-- Run BEFORE migration 021 (QB cache tables)
-- Adds Quickbase business context columns to existing tables
-- ============================================================================

-- 1. Add QB context to customer_companies
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS qb_customer_type TEXT;
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS qb_tier TEXT;
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS qb_total_revenue DECIMAL(12,2);
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS qb_invoiced_ty DECIMAL(12,2);
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS qb_invoiced_ly DECIMAL(12,2);
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS qb_growth_90d DECIMAL(8,2);
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS qb_days_since_last_invoice INTEGER;
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS qb_account_manager TEXT;

-- 2. Add QB context to customer_contacts
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS qb_quotes_count INTEGER DEFAULT 0;
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS qb_last_quote_date DATE;
ALTER TABLE customer_contacts ADD COLUMN IF NOT EXISTS qb_contact_recency_days INTEGER;

-- 3. Add customer_type to thread_status for priority sorting
ALTER TABLE thread_status ADD COLUMN IF NOT EXISTS qb_customer_type TEXT;
ALTER TABLE thread_status ADD COLUMN IF NOT EXISTS qb_customer_tier TEXT;

-- 4. Indexes for QB filtering/sorting
CREATE INDEX IF NOT EXISTS idx_companies_qb_tier ON customer_companies(qb_tier);
CREATE INDEX IF NOT EXISTS idx_companies_qb_customer_type ON customer_companies(qb_customer_type);
CREATE INDEX IF NOT EXISTS idx_companies_qb_total_revenue ON customer_companies(qb_total_revenue DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_threads_qb_customer_type ON thread_status(qb_customer_type);
