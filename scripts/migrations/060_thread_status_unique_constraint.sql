-- Migration 060: Fix thread_status duplicate accumulation
--
-- Root cause: save_thread_statuses had no working unique constraint,
-- so every sync cycle created new rows instead of updating existing ones.
--
-- Fix: Add UNIQUE on thread_id (one row per logical thread).
-- The save code now deletes-then-inserts to avoid constraint issues.

-- Step 1: Remove ALL duplicates — keep one row per thread_id
-- (the one with highest message_count / most recent update)
DELETE FROM thread_status
WHERE id NOT IN (
    SELECT DISTINCT ON (thread_id)
        id
    FROM thread_status
    ORDER BY thread_id, message_count DESC NULLS LAST, updated_at DESC NULLS LAST
);

-- Step 2: Add unique constraint on thread_id
ALTER TABLE thread_status
    DROP CONSTRAINT IF EXISTS uq_thread_status_mailbox_thread;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_thread_status_thread_id'
    ) THEN
        ALTER TABLE thread_status
            ADD CONSTRAINT uq_thread_status_thread_id UNIQUE (thread_id);
    END IF;
END $$;

-- Step 3: Index for subject-based dedup at query time
CREATE INDEX IF NOT EXISTS idx_thread_status_subject_lower
    ON thread_status (lower(subject));
