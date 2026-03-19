-- ============================================================================
-- Migration 032: QB Operations Table Cache + operations_table_id config
-- ============================================================================
-- Purpose: Cache the QuickBase Operations table (bvqsudnif) which holds
--          granular product/service detail per job — operation name, department,
--          machine, cost, quantity. Used by the recommendation engine and
--          customer profile page.
-- Run After: sprint3_migration_021_strategic_digest.sql (qb_sync_config exists)
-- ============================================================================

-- 1. Add operations_table_id to qb_sync_config
--    Pre-seeded with the known table ID so sync works without UI config change.
ALTER TABLE qb_sync_config
    ADD COLUMN IF NOT EXISTS operations_table_id TEXT DEFAULT 'bvqsudnif';

-- 2. qb_operations — Cached QuickBase Operations
CREATE TABLE IF NOT EXISTS qb_operations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id           UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,

    -- QB identifiers
    qb_record_id        TEXT NOT NULL,   -- field 3: Record ID# (QB internal)
    operation_id        TEXT,            -- field 6: Operation ID (business PK)
    qb_customer_id      TEXT,            -- field 14: Customer ID (FK to customers table)

    -- Job linkage
    job_no              TEXT,            -- field 7: Job No (FK to jobs table buziry2ri)
    quote_no            TEXT,            -- field 8: Quote No

    -- Product / operation detail (KEY FIELDS for recommendation engine)
    operation_name      TEXT,            -- field 9: Operation (e.g. "HP Indigo 4-col Process")
    machine             TEXT,            -- field 10: Machine name
    department          TEXT,            -- field 11: Department (e.g. "Press", "Finishing")
    finishing_type      TEXT,            -- field 26: Finishing Type (e.g. "Perfect Bind")
    job_title           TEXT,            -- field 19: Job/product description

    -- Dates
    date_accepted       DATE,            -- field 12: Date Accepted
    date_due            DATE,            -- field 13: Date Due
    first_invoice_no    TEXT,            -- field 27: First Invoice Number
    first_invoice_date  DATE,            -- field 28: First Invoice Date

    -- Customer info (denormalized)
    customer_name       TEXT,            -- field 16: Customer name
    customer_code       TEXT,            -- field 15: Customer code
    am_job              TEXT,            -- field 17: Account Manager (job)
    am_customer         TEXT,            -- field 18: Account Manager (customer)

    -- Quantities and financials
    quantity            INTEGER,         -- field 20: Units produced
    production_status   TEXT,            -- field 21: Production Status
    cost_price          DECIMAL(12,2),   -- field 22: Cost Price
    cost_plus_price     DECIMAL(12,2),   -- field 23: Cost+ Price (selling price)
    profit_amount       DECIMAL(12,2),   -- field 24: Profit $
    profit_pct          DECIMAL(5,2),    -- field 25: Profit %

    -- Platform matching
    matched_company_id  UUID REFERENCES customer_companies(id) ON DELETE SET NULL,

    -- Sync metadata
    qb_last_modified    TIMESTAMPTZ,
    synced_at           TIMESTAMPTZ DEFAULT NOW(),
    created_at          TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(client_id, qb_record_id)
);

-- Indexes for recommendation engine and profile queries
CREATE INDEX IF NOT EXISTS idx_qb_operations_company
    ON qb_operations(matched_company_id, date_accepted DESC);

CREATE INDEX IF NOT EXISTS idx_qb_operations_client_operation
    ON qb_operations(client_id, operation_name);

CREATE INDEX IF NOT EXISTS idx_qb_operations_client_department
    ON qb_operations(client_id, department);

CREATE INDEX IF NOT EXISTS idx_qb_operations_job
    ON qb_operations(job_no);

CREATE INDEX IF NOT EXISTS idx_qb_operations_customer
    ON qb_operations(qb_customer_id);

COMMENT ON TABLE qb_operations IS 'Cached QuickBase Operations table (bvqsudnif). Each row is one production operation within a job — the granular product/service detail used by the recommendation engine to identify cross-sell and upsell opportunities.';
COMMENT ON COLUMN qb_operations.operation_name IS 'The specific production operation (e.g. HP Indigo 4-col Process, Wide Format Print, Scodix Foiling). Primary product identifier for recommendation engine.';
COMMENT ON COLUMN qb_operations.department IS 'Production department grouping (e.g. Press, Finishing, Wide Format). Used for department-level recommendation affinity.';
