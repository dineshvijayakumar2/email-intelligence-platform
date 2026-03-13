-- Migration: 025_add_system_settings.sql
-- Purpose: Global admin settings that persist across server restarts.
--          Currently used to store AI model preferences (cheap/strategic).
-- Date: March 2026

CREATE TABLE IF NOT EXISTS system_settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TIMESTAMPTZ DEFAULT now()
);

-- Seed default AI model preferences (can be overridden via AI Usage page)
INSERT INTO system_settings (key, value) VALUES
    ('ai_cheap_model',    'gemini'),
    ('ai_strategic_model', 'gemini')
ON CONFLICT (key) DO NOTHING;
