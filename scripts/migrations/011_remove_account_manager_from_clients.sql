-- Migration 011: Remove account_manager_id from clients table
--
-- Purpose: Remove the account_manager_id foreign key column from clients table.
-- Account managers are now managed through mailbox assignments (many-to-many relationship).
-- The relationship is derived from mailboxes.user_id where mailboxes.client_id matches.
--
-- Date: 2026-02-02

-- Step 1: Drop dependent views first
DROP VIEW IF EXISTS client_overview CASCADE;

-- Step 2: Drop the foreign key constraint (if it exists)
ALTER TABLE clients
DROP CONSTRAINT IF EXISTS clients_account_manager_id_fkey;

-- Step 3: Drop the index on account_manager_id (if it exists)
DROP INDEX IF EXISTS idx_clients_account_manager;

-- Step 4: Drop the account_manager_id column
ALTER TABLE clients
DROP COLUMN IF EXISTS account_manager_id;

-- Step 5: Add comment to document the change
COMMENT ON TABLE clients IS 'Client organizations. Account managers are derived from mailbox.user_id assignments. Many-to-many relationship managed at mailbox level.';

-- Note: If client_overview view is needed, recreate it without account_manager_id.
-- Example:
-- CREATE OR REPLACE VIEW client_overview AS
-- SELECT
--   c.*,
--   COUNT(DISTINCT m.id) as mailbox_count,
--   COUNT(DISTINCT cc.id) as company_count,
--   COUNT(DISTINCT ct.id) as contact_count
-- FROM clients c
-- LEFT JOIN mailboxes m ON m.client_id = c.id
-- LEFT JOIN customer_companies cc ON cc.client_id = c.id
-- LEFT JOIN customer_contacts ct ON ct.client_id = c.id
-- GROUP BY c.id;
