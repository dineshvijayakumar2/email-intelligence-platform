-- Migration: Fix update_folder_counts function with WHERE clause for RLS compatibility
-- Purpose: Add WHERE clause to UPDATE statements to satisfy RLS requirements
-- Issue: Function failing with "UPDATE requires a WHERE clause" error
-- Date: 2026-01-14

CREATE OR REPLACE FUNCTION update_folder_counts()
RETURNS void AS $$
BEGIN
  -- Update per-mailbox folder counts
  UPDATE folders f
  SET message_count = (
    SELECT COUNT(*)
    FROM emails e
    WHERE e.folder_path = f.folder_path
    AND e.mailbox_id = f.mailbox_id
  )
  WHERE f.id IS NOT NULL;  -- Add WHERE clause for RLS compatibility

  -- Update mailbox totals
  UPDATE mailboxes m
  SET total_emails = (
    SELECT COUNT(*)
    FROM emails e
    WHERE e.mailbox_id = m.id
  )
  WHERE m.id IS NOT NULL;  -- Add WHERE clause for RLS compatibility
END;
$$ LANGUAGE plpgsql;

-- Verify the function works
SELECT update_folder_counts();

-- Check results
SELECT id, name, total_emails FROM mailboxes;
SELECT folder_path, message_count FROM folders LIMIT 10;
