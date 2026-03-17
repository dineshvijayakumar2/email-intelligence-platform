-- ============================================================================
-- Migration 028: Client-scoped AI settings (models + API keys)
-- ============================================================================
-- Purpose: Make AI model selection and API keys configurable per-client.
--          No global defaults — each client must have their own settings.
--          Falls back to env vars / hardcoded defaults if no DB row.
-- ============================================================================

-- Remove old global rows (no longer needed)
DELETE FROM system_settings WHERE TRUE;

-- Drop old PK and restructure
ALTER TABLE system_settings DROP CONSTRAINT IF EXISTS system_settings_pkey;
ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS id UUID DEFAULT gen_random_uuid();
ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE;
ALTER TABLE system_settings ADD PRIMARY KEY (id);

-- One setting per key per client
CREATE UNIQUE INDEX IF NOT EXISTS idx_system_settings_client_key
    ON system_settings(client_id, key);
