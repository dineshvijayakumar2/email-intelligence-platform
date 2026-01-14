-- Migration: Fix email_categories and other table permissions
-- Purpose: Grant INSERT permissions on email_categories and other tables for email processing
-- Issue: Tagging not working in production - anon/authenticated roles lack INSERT permission
-- Date: 2026-01-14

-- Grant table permissions for email processing
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE emails TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE email_categories TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE folders TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE mailboxes TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE processing_jobs TO anon, authenticated;

-- Verify email_categories has tags by checking a sample
SELECT
  e.subject,
  ec.category,
  ec.confidence,
  ec.detection_method
FROM emails e
LEFT JOIN email_categories ec ON e.id = ec.email_id
WHERE ec.category IS NOT NULL
LIMIT 20;

-- Count total tags
SELECT
  COUNT(DISTINCT email_id) as emails_with_tags,
  COUNT(*) as total_tags
FROM email_categories;
