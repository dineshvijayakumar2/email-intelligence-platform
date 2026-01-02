-- Update mailbox_type constraint to support MBOX, PST, and OLM
-- Remove old constraint and add new one

-- Drop the old constraint
ALTER TABLE mailboxes
DROP CONSTRAINT IF EXISTS mailboxes_mailbox_type_check;

-- Add new constraint with MBOX, PST, OLM support
ALTER TABLE mailboxes
ADD CONSTRAINT mailboxes_mailbox_type_check
CHECK (mailbox_type IN ('mbox', 'pst', 'olm'));

-- Add a comment explaining the supported types
COMMENT ON COLUMN mailboxes.mailbox_type IS 'Mailbox type: mbox (universal), pst (Windows Outlook), or olm (Mac Outlook)';
