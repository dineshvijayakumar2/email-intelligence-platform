-- Migration: Fix folder counts and mailbox permissions
-- Purpose: Grant execute permissions on update_folder_counts and ensure it updates mailbox totals
-- Issue: Email counts showing 0 in production, mailbox names showing as Unknown
-- Date: 2026-01-14

-- Grant execute permission on update_folder_counts function
GRANT EXECUTE ON FUNCTION update_folder_counts() TO anon, authenticated;

-- Add comment for documentation
COMMENT ON FUNCTION update_folder_counts() IS 'Updates message counts in folders table and total_emails in mailboxes table';

-- Run the function once to update existing data
SELECT update_folder_counts();

-- Verify mailbox totals are populated
DO $$
DECLARE
  mailbox_record RECORD;
BEGIN
  FOR mailbox_record IN SELECT id, name, total_emails FROM mailboxes
  LOOP
    RAISE NOTICE 'Mailbox: % - Total emails: %', mailbox_record.name, COALESCE(mailbox_record.total_emails, 0);
  END LOOP;
END $$;
