-- Make email_address optional in mailboxes table
-- This allows file-based mailboxes (MBOX/PST/OLM) to be created without an email address

ALTER TABLE mailboxes
ALTER COLUMN email_address DROP NOT NULL;

-- Add a comment explaining this change
COMMENT ON COLUMN mailboxes.email_address IS 'Optional email address - not required for file-based mailboxes (MBOX/PST/OLM)';
