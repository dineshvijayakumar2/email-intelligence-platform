-- Migration 055: Canonical Thread Resolution
-- Adds canonical_thread_id to emails for authoritative cross-mailbox thread grouping.
-- The existing thread_id (provider-assigned) is kept for reference but no longer used for analytics.

-- 1. New columns on emails table
ALTER TABLE emails ADD COLUMN IF NOT EXISTS canonical_thread_id UUID;
ALTER TABLE emails ADD COLUMN IF NOT EXISTS thread_match_method TEXT;       -- 'message_id', 'references', 'subject_participant', 'provider', 'new'
ALTER TABLE emails ADD COLUMN IF NOT EXISTS thread_match_confidence REAL;

-- 2. Index for canonical thread grouping (primary analytics key)
CREATE INDEX IF NOT EXISTS idx_emails_canonical_thread
    ON emails(canonical_thread_id) WHERE canonical_thread_id IS NOT NULL;

-- Index for Message-ID lookups across all mailboxes (Tier 1/2 resolution)
CREATE INDEX IF NOT EXISTS idx_emails_internet_message_id
    ON emails(internet_message_id) WHERE internet_message_id IS NOT NULL AND internet_message_id != '__none__';

-- Index for In-Reply-To lookups
CREATE INDEX IF NOT EXISTS idx_emails_in_reply_to
    ON emails(in_reply_to) WHERE in_reply_to IS NOT NULL;

-- 3. Thread merge audit log
CREATE TABLE IF NOT EXISTS thread_merges (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_thread_id  UUID NOT NULL,
    to_thread_id    UUID NOT NULL,
    client_id       UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    merged_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    merge_reason    TEXT,               -- 'message_id', 'references', 'subject_participant'
    confidence      REAL,
    email_count     INTEGER DEFAULT 0,  -- emails moved in this merge
    reviewed        BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_thread_merges_client
    ON thread_merges(client_id);

-- 4. Update thread_status to use canonical_thread_id
ALTER TABLE thread_status ADD COLUMN IF NOT EXISTS canonical_thread_id UUID;
CREATE INDEX IF NOT EXISTS idx_thread_status_canonical
    ON thread_status(canonical_thread_id) WHERE canonical_thread_id IS NOT NULL;

-- 5. RPC for batch updating canonical_thread_id on emails
CREATE OR REPLACE FUNCTION batch_update_canonical_threads(p_updates JSONB)
RETURNS INTEGER
LANGUAGE plpgsql AS $$
DECLARE
    updated INTEGER := 0;
BEGIN
    UPDATE emails e
    SET canonical_thread_id = (u.canonical_thread_id)::UUID,
        thread_match_method = u.thread_match_method,
        thread_match_confidence = (u.thread_match_confidence)::REAL
    FROM jsonb_to_recordset(p_updates) AS u(
        email_id TEXT,
        canonical_thread_id TEXT,
        thread_match_method TEXT,
        thread_match_confidence TEXT
    )
    WHERE e.id = (u.email_id)::UUID;

    GET DIAGNOSTICS updated = ROW_COUNT;
    RETURN updated;
END;
$$;
