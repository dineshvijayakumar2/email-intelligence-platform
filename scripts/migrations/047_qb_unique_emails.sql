-- Migration 047: QB Unique Emails Cache + Email-Based Matching
-- Adds unique_emails_table_id to qb_sync_config and creates qb_unique_emails cache table.
-- The QB "Unique Emails" table maps email addresses to QB Customer IDs via a foreign key,
-- enabling email-based matching as the primary method (replacing name-based heuristics).

-- 1. Add unique_emails_table_id to qb_sync_config (same pattern as migration 032 for operations)
ALTER TABLE qb_sync_config
    ADD COLUMN IF NOT EXISTS unique_emails_table_id TEXT DEFAULT 'bvmtc5re6';

-- Backfill existing rows
UPDATE qb_sync_config SET unique_emails_table_id = 'bvmtc5re6' WHERE unique_emails_table_id IS NULL;

-- 2. Cache table for QB Unique Emails
CREATE TABLE IF NOT EXISTS qb_unique_emails (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id        UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    qb_record_id     TEXT NOT NULL,           -- QB Record ID#
    email            TEXT NOT NULL,            -- field 6: email (PK in QB, unique)
    qb_customer_id   TEXT,                    -- field 23: "Customer ID (maint by pipeline)" FK to Customers
    customer_name    TEXT,                    -- field 24: lookup from customer record
    first_name       TEXT,                    -- field 44: formula
    last_name        TEXT,                    -- field 45: formula
    hide             BOOLEAN DEFAULT FALSE,   -- field 46: Hide? (filters internal/junk)
    quality          TEXT,                    -- field 49: good / risky / bad
    result           TEXT,                    -- field 50: ok / catch_all / invalid / unknown
    free             BOOLEAN DEFAULT FALSE,   -- field 51: free email provider?
    email_invalid    BOOLEAN DEFAULT FALSE,   -- field 53: Email Invalid? (formula)
    customer_type    TEXT,                    -- field 70: "Active A Customer", "Prospect", etc.
    customer_id_text TEXT,                    -- field 72: Customer ID (text calc)
    synced_at        TIMESTAMPTZ DEFAULT NOW(),
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(client_id, qb_record_id)
);

-- Fast email lookup for matching (lowercased for case-insensitive matching)
CREATE UNIQUE INDEX IF NOT EXISTS idx_qb_ue_client_email
    ON qb_unique_emails(client_id, lower(email));

-- Customer ID lookup for joining with qb_customers
CREATE INDEX IF NOT EXISTS idx_qb_ue_customer
    ON qb_unique_emails(client_id, qb_customer_id)
    WHERE qb_customer_id IS NOT NULL;

-- Partial index for valid-only emails (used during matching)
CREATE INDEX IF NOT EXISTS idx_qb_ue_valid
    ON qb_unique_emails(client_id)
    WHERE hide = FALSE AND email_invalid = FALSE;
