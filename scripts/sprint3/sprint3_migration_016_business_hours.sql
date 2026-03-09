-- ============================================================================
-- Migration 016: Business Hours Metrics
-- ============================================================================
-- Adds timezone and business hours configuration to user_profiles.
-- Adds business_hours_response_time_seconds to email_response_metrics so both
-- wall-clock and business-hours response times are stored side by side.
--
-- Run After: sprint3_migration_015_digest_type.sql
-- Duration: < 5 seconds
-- ============================================================================

-- 1. Add timezone and business hours config to user_profiles
ALTER TABLE user_profiles
ADD COLUMN IF NOT EXISTS timezone TEXT NOT NULL DEFAULT 'UTC';

ALTER TABLE user_profiles
ADD COLUMN IF NOT EXISTS business_hours_start INTEGER NOT NULL DEFAULT 9
CHECK (business_hours_start >= 0 AND business_hours_start <= 23);

ALTER TABLE user_profiles
ADD COLUMN IF NOT EXISTS business_hours_end INTEGER NOT NULL DEFAULT 18
CHECK (business_hours_end >= 0 AND business_hours_end <= 23);

-- business_days: array of ISO weekday numbers (1=Monday .. 7=Sunday)
-- Default: Monday-Friday
ALTER TABLE user_profiles
ADD COLUMN IF NOT EXISTS business_days INTEGER[] NOT NULL DEFAULT '{1,2,3,4,5}';

-- 2. Add business hours response time to email_response_metrics
ALTER TABLE email_response_metrics
ADD COLUMN IF NOT EXISTS business_hours_response_time_seconds INTEGER;

-- 3. Index for fast lookup of user settings by mailbox owner
-- (mailboxes.user_id → user_profiles.id)
CREATE INDEX IF NOT EXISTS idx_user_profiles_timezone
    ON user_profiles(id) WHERE timezone != 'UTC';

DO $$ BEGIN RAISE NOTICE 'Migration 016 complete: business hours config added to user_profiles, business_hours_response_time_seconds added to email_response_metrics'; END $$;
