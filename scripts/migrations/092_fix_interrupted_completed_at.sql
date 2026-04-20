-- ============================================================================
-- Migration 092: Don't set completed_at on interrupted jobs
-- ============================================================================
-- Problem: reconcile_stuck_jobs sets completed_at = NOW() when marking jobs
-- as 'interrupted'. Interrupted jobs are not completed — they may be resumed.
-- completed_at should only be set on terminal states (completed, failed).
-- ============================================================================

CREATE OR REPLACE FUNCTION reconcile_stuck_jobs()
RETURNS INT AS $$
DECLARE
  v_count INT;
  v_bg_count INT;
BEGIN
  -- Case 1: Worker-managed jobs with expired leases
  UPDATE processing_jobs
  SET status = 'interrupted'
  WHERE status = 'running'
    AND lease_expires_at IS NOT NULL
    AND lease_expires_at < NOW();

  GET DIAGNOSTICS v_count = ROW_COUNT;

  -- Case 2: BackgroundTasks jobs with no lease, stuck running > 2 hours
  UPDATE processing_jobs
  SET status = 'interrupted'
  WHERE status = 'running'
    AND lease_expires_at IS NULL
    AND worker_id IS NULL
    AND started_at < NOW() - INTERVAL '2 hours';

  GET DIAGNOSTICS v_bg_count = ROW_COUNT;

  RETURN v_count + v_bg_count;
END;
$$ LANGUAGE plpgsql;
