-- Migration 053: Many-to-many email ↔ contact/company linking
-- Previously emails had a single customer_contact_id FK, only linking to one recipient.
-- This junction table links each email to ALL participants (sender, TO, CC, BCC),
-- each with their contact and company, enabling accurate per-company email counts.

CREATE TABLE IF NOT EXISTS email_contact_links (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email_id        UUID NOT NULL REFERENCES emails(id) ON DELETE CASCADE,
    contact_id      UUID REFERENCES customer_contacts(id) ON DELETE SET NULL,
    company_id      UUID REFERENCES customer_companies(id) ON DELETE SET NULL,
    email_address   TEXT NOT NULL,           -- the actual email address (for display/debugging)
    role            TEXT NOT NULL,            -- 'sender', 'to', 'cc', 'bcc'
    client_id       UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Fast lookups by company (for "emails for this company" queries)
CREATE INDEX IF NOT EXISTS idx_ecl_company
    ON email_contact_links(company_id) WHERE company_id IS NOT NULL;

-- Fast lookups by contact
CREATE INDEX IF NOT EXISTS idx_ecl_contact
    ON email_contact_links(contact_id) WHERE contact_id IS NOT NULL;

-- Fast lookups by email
CREATE INDEX IF NOT EXISTS idx_ecl_email
    ON email_contact_links(email_id);

-- Prevent duplicate links (same email + same address + same role)
CREATE UNIQUE INDEX IF NOT EXISTS idx_ecl_unique
    ON email_contact_links(email_id, email_address, role);

-- Client filter for RLS and queries
CREATE INDEX IF NOT EXISTS idx_ecl_client
    ON email_contact_links(client_id);
