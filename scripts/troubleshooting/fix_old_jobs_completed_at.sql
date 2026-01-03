-- ONE-TIME FIX: Set completed_at for old jobs that are missing it
--
-- WHEN TO USE:
--   - After upgrading to commit 3557e72e or later
--   - If you see failed/stopped jobs with running duration timers
--   - Only needed once for historical data cleanup
--
-- BACKGROUND:
--   Before commit 3557e72e, failed/stopped jobs didn't always set completed_at
--   This caused duration timers to keep running in the UI
--   New code sets completed_at automatically, but old jobs need fixing
--
-- HOW TO RUN:
--   Option 1 (Supabase): Copy/paste into SQL Editor and run
--   Option 2 (psql): psql -d <database> -f scripts/troubleshooting/fix_old_jobs_completed_at.sql
--
-- WHAT IT DOES:
--   For terminal jobs without completed_at, set it to updated_at (best guess)

UPDATE processing_jobs
SET completed_at = updated_at
WHERE status IN ('completed', 'failed', 'stopped')
  AND completed_at IS NULL
  AND updated_at IS NOT NULL;

-- For jobs without even updated_at, use created_at + 1 hour as fallback
UPDATE processing_jobs
SET completed_at = created_at + INTERVAL '1 hour'
WHERE status IN ('completed', 'failed', 'stopped')
  AND completed_at IS NULL
  AND updated_at IS NULL;

-- Show what was updated
SELECT
  id,
  status,
  created_at,
  started_at,
  completed_at,
  updated_at
FROM processing_jobs
WHERE status IN ('completed', 'failed', 'stopped')
ORDER BY created_at DESC
LIMIT 10;
