-- Migration 020: Fix thread_status CHECK constraint and backfill mailbox_id
--
-- The thread tracker writes statuses like 'awaiting_response', 'awaiting_our_response',
-- 'ongoing' which violate the original CHECK constraint. Also mailbox_id was never set.

-- 1. Drop the old CHECK constraint and add an expanded one
ALTER TABLE thread_status DROP CONSTRAINT IF EXISTS thread_status_status_check;
ALTER TABLE thread_status ADD CONSTRAINT thread_status_status_check
  CHECK (status IN (
    'complete', 'awaiting_reply', 'overdue', 'dropped', 'outbound_pending', 'stale',
    'ongoing', 'awaiting_response', 'awaiting_our_response'
  ));

-- 2. Backfill mailbox_id from emails table for existing thread_status records
UPDATE thread_status ts SET
  mailbox_id = (
    SELECT DISTINCT e.mailbox_id
    FROM emails e
    WHERE e.thread_id = ts.thread_id
    LIMIT 1
  )
WHERE ts.mailbox_id IS NULL;

-- Done. Re-run extraction to repopulate with correct statuses.
