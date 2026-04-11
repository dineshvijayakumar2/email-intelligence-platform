-- ============================================================================
-- Migration 063: Add created_at to system_settings + auto-update trigger
-- ============================================================================
-- Purpose: Track when settings were first created (not just last updated).
--          Add trigger to auto-update updated_at on every change.
--          Add changelog logging to audit_log on settings mutations.
-- ============================================================================

-- 1. Add created_at column (backfill existing rows with updated_at)
ALTER TABLE system_settings
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();

UPDATE system_settings
SET created_at = COALESCE(updated_at, now())
WHERE created_at IS NULL;

-- 2. Auto-update updated_at on every row change
CREATE OR REPLACE FUNCTION trg_system_settings_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS system_settings_updated_at ON system_settings;
CREATE TRIGGER system_settings_updated_at
    BEFORE UPDATE ON system_settings
    FOR EACH ROW
    EXECUTE FUNCTION trg_system_settings_updated_at();

-- 3. Changelog: log setting changes to audit_log (if table exists)
CREATE OR REPLACE FUNCTION trg_system_settings_changelog()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_TABLE_NAME = 'system_settings' AND EXISTS (
        SELECT 1 FROM information_schema.tables WHERE table_name = 'audit_log'
    ) THEN
        INSERT INTO audit_log (action, resource_type, resource_id, details)
        VALUES (
            CASE TG_OP
                WHEN 'INSERT' THEN 'setting_created'
                WHEN 'UPDATE' THEN 'setting_changed'
                WHEN 'DELETE' THEN 'setting_deleted'
            END,
            'system_settings',
            COALESCE(NEW.id, OLD.id)::text,
            jsonb_build_object(
                'key', COALESCE(NEW.key, OLD.key),
                'client_id', COALESCE(NEW.client_id, OLD.client_id),
                'old_value', CASE WHEN TG_OP != 'INSERT' THEN OLD.value ELSE NULL END,
                'new_value', CASE WHEN TG_OP != 'DELETE' THEN NEW.value ELSE NULL END
            )
        );
    END IF;
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS system_settings_changelog ON system_settings;
CREATE TRIGGER system_settings_changelog
    AFTER INSERT OR UPDATE OR DELETE ON system_settings
    FOR EACH ROW
    EXECUTE FUNCTION trg_system_settings_changelog();
