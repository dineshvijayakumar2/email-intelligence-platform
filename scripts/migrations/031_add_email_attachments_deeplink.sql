-- Migration 031: Add attachment metadata and provider deep link to emails
--
-- Purpose:
--   • attachments JSONB — store [{filename, size, mimetype}] extracted at sync time
--     (Gmail: populated from MIME parts; Outlook: currently [] pending attachment API call)
--   • provider_web_link TEXT — ready-to-open URL in provider's web app
--     (Gmail: https://mail.google.com/mail/u/0/#all/{gmail_id}; Outlook: webLink from Graph API)
--
-- No re-extraction needed for cc_list / bcc_list — those are already stored.
-- Re-extraction IS needed for historical emails to populate attachments / provider_web_link.

ALTER TABLE emails
  ADD COLUMN IF NOT EXISTS attachments       JSONB NOT NULL DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS provider_web_link TEXT;

-- Index for non-null deep links (used when opening from UI)
CREATE INDEX IF NOT EXISTS idx_emails_provider_web_link
  ON emails(id)
  WHERE provider_web_link IS NOT NULL;

COMMENT ON COLUMN emails.attachments       IS 'Attachment metadata [{filename, size, mimetype}] extracted at sync time';
COMMENT ON COLUMN emails.provider_web_link IS 'Direct URL to open this email in Gmail or Outlook Web';
