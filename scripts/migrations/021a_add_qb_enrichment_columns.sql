-- Migration: 021a_add_qb_enrichment_columns.sql
-- Purpose: Add QB enrichment columns to customer_companies, customer_contacts,
--          and thread_status so Sprint 3 analytics queries don't fail with
--          "column does not exist" errors.
-- Date: March 2026

-- ── customer_companies ──────────────────────────────────────────────────────
-- These are populated by quickbase_sync.propagate_qb_data_to_companies()
-- after QB customers are matched to companies.

ALTER TABLE customer_companies
    ADD COLUMN IF NOT EXISTS qb_customer_type       TEXT,
    ADD COLUMN IF NOT EXISTS qb_tier                TEXT,
    ADD COLUMN IF NOT EXISTS qb_total_revenue       NUMERIC,
    ADD COLUMN IF NOT EXISTS qb_invoiced_ty         NUMERIC,
    ADD COLUMN IF NOT EXISTS qb_invoiced_ly         NUMERIC,
    ADD COLUMN IF NOT EXISTS qb_growth_90d          NUMERIC,
    ADD COLUMN IF NOT EXISTS qb_days_since_last_invoice INTEGER,
    ADD COLUMN IF NOT EXISTS qb_account_manager     TEXT;

-- ── customer_contacts ────────────────────────────────────────────────────────
-- Read by analytics endpoints; currently no propagate step writes these —
-- they are present for future enrichment from qb_contacts.

ALTER TABLE customer_contacts
    ADD COLUMN IF NOT EXISTS qb_customer_type       TEXT,
    ADD COLUMN IF NOT EXISTS qb_tier                TEXT,
    ADD COLUMN IF NOT EXISTS qb_total_revenue       NUMERIC,
    ADD COLUMN IF NOT EXISTS qb_quotes_count        INTEGER,
    ADD COLUMN IF NOT EXISTS qb_last_quote_date     DATE,
    ADD COLUMN IF NOT EXISTS qb_contact_recency_days INTEGER;

-- ── thread_status ────────────────────────────────────────────────────────────
-- Read by thread list and overdue-threads analytics queries.

ALTER TABLE thread_status
    ADD COLUMN IF NOT EXISTS qb_customer_type       TEXT,
    ADD COLUMN IF NOT EXISTS qb_customer_tier       TEXT;
