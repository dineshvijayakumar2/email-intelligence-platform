-- Migration 060: Add unique constraint on thread_status to prevent duplicates
--
-- Root cause: save_thread_statuses uses upsert(on_conflict='thread_id') but
-- thread_id has no UNIQUE constraint, so every save creates new rows.
-- Duplicates accumulate with every sync cycle.
--
-- Fix: Add unique index on (mailbox_id, thread_id) so upsert actually merges.
-- Also add a subject_normalized column for cross-mailbox dedup at query time.

-- Step 1: Remove duplicates BEFORE adding unique constraint
-- Keep the row with highest message_count (or most recent updated_at)
DELETE FROM thread_status
WHERE id NOT IN (
    SELECT DISTINCT ON (mailbox_id, thread_id)
        id
    FROM thread_status
    ORDER BY mailbox_id, thread_id, message_count DESC NULLS LAST, updated_at DESC NULLS LAST
);

-- Step 2: Add unique constraint
ALTER TABLE thread_status
    ADD CONSTRAINT uq_thread_status_mailbox_thread
    UNIQUE (mailbox_id, thread_id);

-- Step 3: Add index for subject-based dedup queries
CREATE INDEX IF NOT EXISTS idx_thread_status_subject_norm
    ON thread_status (lower(subject));
