-- Migration 084: reconcile_stuck_jobs RPC
-- Marks jobs with expired leases as 'interrupted' so they can be reclaimed.
-- Called by worker reconciler loop every 10 minutes.

CREATE OR REPLACE FUNCTION reconcile_stuck_jobs()
RETURNS INT AS $$
DECLARE
  v_count INT;
BEGIN
  UPDATE processing_jobs
  SET status = 'interrupted',
      completed_at = NOW()
  WHERE status = 'running'
    AND lease_expires_at IS NOT NULL
    AND lease_expires_at < NOW();

  GET DIAGNOSTICS v_count = ROW_COUNT;
  RETURN v_count;
END;
$$ LANGUAGE plpgsql;
