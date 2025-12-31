-- Optimized indexes for email_categories table
-- This replaces multiple redundant indexes with essential ones only

-- Drop any duplicate or unnecessary indexes
DROP INDEX IF EXISTS idx_email_categories_email_id CASCADE;
DROP INDEX IF EXISTS idx_email_categories_category CASCADE;
DROP INDEX IF EXISTS idx_email_categories_tag_type CASCADE;
DROP INDEX IF EXISTS idx_email_categories_email_tag_type CASCADE;

-- Add tag_type column if not exists
ALTER TABLE email_categories ADD COLUMN IF NOT EXISTS tag_type TEXT;

-- Create ONLY essential indexes

-- 1. Email lookup (most common query: get all tags for an email)
CREATE INDEX IF NOT EXISTS idx_ec_email_id
ON email_categories(email_id);

-- 2. Tag filtering (filter emails by specific tag)
CREATE INDEX IF NOT EXISTS idx_ec_category
ON email_categories(category)
WHERE category NOT LIKE '_meta_%';

-- 3. Tag type filtering (optional, only if you query by tag_type frequently)
-- CREATE INDEX IF NOT EXISTS idx_ec_tag_type ON email_categories(tag_type);

-- Note: Composite indexes like (email_id, tag_type) are usually NOT needed
-- PostgreSQL can efficiently use single-column indexes with bitmap scans

COMMENT ON COLUMN email_categories.tag_type IS 'Tag classification: direction, thread_type, folder, classification, sender_type, priority, content, metadata';
COMMENT ON INDEX idx_ec_email_id IS 'Fast lookup of all tags for a specific email';
COMMENT ON INDEX idx_ec_category IS 'Fast filtering of emails by tag (excludes metadata tags)';
