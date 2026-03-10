-- Migration 018: Audit Log Table
-- Tracks key user and system actions for compliance and debugging.

CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    user_email TEXT,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT,
    details JSONB DEFAULT '{}'::jsonb,
    ip_address TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_user ON audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_log_resource ON audit_log(resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_created ON audit_log(created_at DESC);

ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;

-- Only admins and service_role can read audit logs
CREATE POLICY "Service role full access on audit_log"
    ON audit_log FOR ALL TO service_role USING (true);

CREATE POLICY "Admins can read audit_log"
    ON audit_log FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM user_profiles
            WHERE user_profiles.id = auth.uid()
            AND 'admin' = ANY(user_profiles.roles)
        )
    );

GRANT SELECT, INSERT ON TABLE audit_log TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE audit_log TO service_role;

COMMENT ON TABLE audit_log IS 'Tracks key user and system actions for compliance and debugging';
COMMENT ON COLUMN audit_log.action IS 'Action type: login, sync, analyze, extract, settings_change, mailbox_create, mailbox_delete, user_invite, etc.';
COMMENT ON COLUMN audit_log.resource_type IS 'Resource type: mailbox, client, user, extraction_job, ai_analysis, digest, settings';
COMMENT ON COLUMN audit_log.details IS 'Additional context as JSON (e.g. changed fields, counts, errors)';
