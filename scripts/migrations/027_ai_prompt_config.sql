-- ============================================================================
-- Migration 027: Configurable AI Prompts
-- ============================================================================
-- Purpose: Store AI prompts in DB so they can be tuned per-client without
--          code changes. Falls back to hardcoded defaults if no row exists.
-- ============================================================================

CREATE TABLE IF NOT EXISTS ai_prompt_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    prompt_key TEXT NOT NULL,
    prompt_text TEXT NOT NULL,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    version TEXT NOT NULL DEFAULT 'v1.0',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(client_id, prompt_key)
);

-- NULL client_id = global default (applies to all clients without a specific override)
CREATE UNIQUE INDEX IF NOT EXISTS idx_prompt_config_global
    ON ai_prompt_config(prompt_key) WHERE client_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_prompt_config_client
    ON ai_prompt_config(client_id, prompt_key) WHERE is_active = TRUE;

COMMENT ON TABLE ai_prompt_config IS 'Configurable AI prompts — per-client overrides with global defaults. On first use, builtin defaults are auto-seeded as global rows (client_id IS NULL) so all prompts are editable via the playground from day one.';
