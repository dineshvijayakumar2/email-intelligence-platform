-- Migration 084: reconcile_stuck_jobs RPC
-- Marks jobs with expired leases as 'interrupted' so they can be reclaimed.
-- Called by worker reconciler loop every 10 minutes.
--
-- Handles two cases:
-- 1. Worker-managed jobs: lease_expires_at IS NOT NULL and expired
-- 2. BackgroundTasks jobs: lease_expires_at IS NULL, stuck running > 2 hours
--    (these have no heartbeat — if the API process restarted, they're orphaned)

CREATE OR REPLACE FUNCTION reconcile_stuck_jobs()
RETURNS INT AS $$
DECLARE
  v_count INT;
  v_bg_count INT;
BEGIN
  -- Case 1: Worker-managed jobs with expired leases
  UPDATE processing_jobs
  SET status = 'interrupted',
      completed_at = NOW()
  WHERE status = 'running'
    AND lease_expires_at IS NOT NULL
    AND lease_expires_at < NOW();

  GET DIAGNOSTICS v_count = ROW_COUNT;

  -- Case 2: BackgroundTasks jobs with no lease, stuck running > 2 hours
  UPDATE processing_jobs
  SET status = 'interrupted',
      completed_at = NOW()
  WHERE status = 'running'
    AND lease_expires_at IS NULL
    AND worker_id IS NULL
    AND started_at < NOW() - INTERVAL '2 hours';

  GET DIAGNOSTICS v_bg_count = ROW_COUNT;

  RETURN v_count + v_bg_count;
END;
$$ LANGUAGE plpgsql;
