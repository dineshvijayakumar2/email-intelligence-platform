-- Migration 051: Add customer_key_id to qb_customers
-- Field 92 in QB Customers = "Customer ID (key)" — the ID that qb_unique_emails.qb_customer_id references.
-- Different from qb_record_id (field 3) which is the QB Record ID#.

ALTER TABLE qb_customers
    ADD COLUMN IF NOT EXISTS customer_key_id TEXT;

CREATE INDEX IF NOT EXISTS idx_qb_cust_key_id
    ON qb_customers(client_id, customer_key_id)
    WHERE customer_key_id IS NOT NULL;
