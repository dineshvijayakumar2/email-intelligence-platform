-- Add app_config table for runtime configuration
-- Run this in Supabase SQL Editor

-- Create app_config table for storing application settings
CREATE TABLE IF NOT EXISTS app_config (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    config_key TEXT UNIQUE NOT NULL,
    config_value TEXT,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add helpful comments
COMMENT ON TABLE app_config IS 'Application configuration settings that can be updated at runtime';
COMMENT ON COLUMN app_config.config_key IS 'Unique key for the configuration setting (e.g., gmail_sync_interval)';
COMMENT ON COLUMN app_config.config_value IS 'Value of the configuration setting (stored as text)';

-- Grant permissions
GRANT SELECT, INSERT, UPDATE ON TABLE app_config TO anon, authenticated;

-- Insert default Gmail sync interval
INSERT INTO app_config (config_key, config_value, description)
VALUES ('gmail_sync_interval', '15', 'Gmail LIVE sync interval in minutes (1-1440)')
ON CONFLICT (config_key) DO NOTHING;

-- Verify
SELECT * FROM app_config;
