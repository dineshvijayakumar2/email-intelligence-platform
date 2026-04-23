-- Migration 094: Add qb_link_count to thread_status for sortable QB Links column.
-- Denormalized count from thread_qb_links, kept in sync by application code.

ALTER TABLE thread_status ADD COLUMN IF NOT EXISTS qb_link_count INTEGER DEFAULT 0;

UPDATE thread_status ts
SET qb_link_count = sub.cnt
FROM (
  SELECT canonical_thread_id, COUNT(*) AS cnt
  FROM thread_qb_links
  GROUP BY canonical_thread_id
) sub
WHERE ts.canonical_thread_id::text = sub.canonical_thread_id;

CREATE INDEX IF NOT EXISTS idx_thread_status_qb_link_count
  ON thread_status(qb_link_count)
  WHERE qb_link_count > 0;
