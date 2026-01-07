-- Migration: Add user_integrations table for OAuth2 token storage
-- Purpose: Enable seamless Google Drive integration with backend token management
-- Run this in your Supabase SQL editor

-- Create the user_integrations table
CREATE TABLE IF NOT EXISTS user_integrations (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id TEXT NOT NULL,  -- User identifier (string format for flexibility)
    provider TEXT NOT NULL CHECK (provider IN ('google_drive', 'microsoft', 'dropbox')),
    access_token TEXT NOT NULL,     -- Current access token
    refresh_token TEXT NOT NULL,    -- Long-lived refresh token
    token_expires_at TIMESTAMPTZ,   -- When access token expires
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Ensure one integration per user per provider
    UNIQUE(user_id, provider)
);

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_user_integrations_user_provider 
ON user_integrations(user_id, provider);

-- Add updated_at trigger (reuse existing function)
CREATE TRIGGER update_user_integrations_updated_at BEFORE UPDATE
    ON user_integrations FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Add helpful comments
COMMENT ON TABLE user_integrations IS 'Stores OAuth2 tokens and integration status for external services like Google Drive';
COMMENT ON COLUMN user_integrations.user_id IS 'User identifier (string format for flexibility)';
COMMENT ON COLUMN user_integrations.provider IS 'Service provider (google_drive, microsoft, etc.)';
COMMENT ON COLUMN user_integrations.access_token IS 'Short-lived access token for API calls';
COMMENT ON COLUMN user_integrations.refresh_token IS 'Long-lived token for refreshing access tokens';

-- Grant necessary permissions for backend operations
GRANT ALL ON user_integrations TO service_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO service_role;

-- Enable RLS for security (optional - adjust based on your auth setup)
-- ALTER TABLE user_integrations ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY "Users can manage their own integrations" 
-- ON user_integrations FOR ALL 
-- USING (auth.uid()::text = user_id);

-- Verify table was created successfully
SELECT 'user_integrations table created successfully' AS status;