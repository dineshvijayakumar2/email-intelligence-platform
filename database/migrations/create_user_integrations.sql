-- Migration: Create user_integrations table for OAuth2 token storage
-- Run this in your Supabase SQL editor

-- Create the user_integrations table
CREATE TABLE IF NOT EXISTS user_integrations (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID NOT NULL, -- References auth.users(id) but not enforced for simplicity
    provider VARCHAR(50) NOT NULL, -- 'google_drive', 'microsoft', etc.
    access_token TEXT NOT NULL,     -- Current access token
    refresh_token TEXT NOT NULL,    -- Long-lived refresh token
    token_expires_at TIMESTAMP,     -- When access token expires
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    -- Ensure one integration per user per provider
    UNIQUE(user_id, provider)
);

-- Create index for faster lookups
CREATE INDEX idx_user_integrations_user_provider 
ON user_integrations(user_id, provider);

-- Enable Row Level Security (RLS)
ALTER TABLE user_integrations ENABLE ROW LEVEL SECURITY;

-- Create RLS policy - users can only access their own integrations
-- Note: This assumes you're using Supabase auth and auth.uid() function
CREATE POLICY "Users can manage their own integrations" 
ON user_integrations 
FOR ALL 
USING (auth.uid()::text = user_id);

-- Grant necessary permissions (adjust based on your setup)
-- This allows the service role to read/write for backend operations
GRANT ALL ON user_integrations TO service_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO service_role;

-- Insert a comment for documentation
COMMENT ON TABLE user_integrations IS 'Stores OAuth2 tokens and integration status for external services like Google Drive';
COMMENT ON COLUMN user_integrations.user_id IS 'User identifier (string format for flexibility)';
COMMENT ON COLUMN user_integrations.provider IS 'Service provider (google_drive, microsoft, etc.)';
COMMENT ON COLUMN user_integrations.access_token IS 'Short-lived access token for API calls';
COMMENT ON COLUMN user_integrations.refresh_token IS 'Long-lived token for refreshing access tokens';

-- Example query to check the table was created successfully
-- SELECT table_name, column_name, data_type FROM information_schema.columns 
-- WHERE table_name = 'user_integrations' ORDER BY ordinal_position;