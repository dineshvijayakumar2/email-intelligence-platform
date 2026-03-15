-- ============================================================================
-- Migration 028: Client-scoped AI settings (models + API keys)
-- ============================================================================
-- Purpose: Make AI model selection and API keys configurable per-client.
--          Falls back to global defaults (client_id IS NULL) if not set.
--
-- After running this migration, the existing global rows (client_id=NULL)
-- become the fallback defaults. Per-client rows override them.
-- ============================================================================

-- Add client_id column (NULL = global default)
ALTER TABLE system_settings
    ADD COLUMN IF NOT EXISTS client_id UUID REFERENCES clients(id) ON DELETE CASCADE;

-- Drop old PK (just on 'key') and add unique constraint for (client_id, key)
ALTER TABLE system_settings DROP CONSTRAINT IF EXISTS system_settings_pkey;
ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS id UUID DEFAULT gen_random_uuid();
ALTER TABLE system_settings ADD PRIMARY KEY (id);

-- Unique constraint: one setting per key per client (NULL client = global)
CREATE UNIQUE INDEX IF NOT EXISTS idx_system_settings_client_key
    ON system_settings(key, client_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_system_settings_global_key
    ON system_settings(key) WHERE client_id IS NULL;
