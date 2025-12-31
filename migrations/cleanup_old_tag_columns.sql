-- Cleanup: Remove old tag-related columns from emails table if they exist
-- These are now stored in the email_categories table

-- Drop old columns if they exist (safe - won't error if columns don't exist)
ALTER TABLE emails DROP COLUMN IF EXISTS tags;
ALTER TABLE emails DROP COLUMN IF EXISTS is_spam;
ALTER TABLE emails DROP COLUMN IF EXISTS is_marketing;
ALTER TABLE emails DROP COLUMN IF EXISTS priority_score;
ALTER TABLE emails DROP COLUMN IF EXISTS sender_type;

-- Note: These columns should not have been created, but this migration
-- ensures they're removed if someone added them accidentally.

COMMENT ON TABLE emails IS 'Email metadata - tags/categories stored in email_categories table';
