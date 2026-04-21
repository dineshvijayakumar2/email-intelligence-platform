-- =============================================================================
-- Migration 088a: Add 'interrupted' to extraction_jobs status constraint
-- Date: 2026-04-21
-- Purpose: The extraction orchestrator sets status='interrupted' when a pipeline
--          is stopped via StopPipeline, but the original Sprint 2 check constraint
--          only allowed (pending, processing, completed, failed, cancelled).
--          This aligns extraction_jobs with processing_jobs which already supports
--          'interrupted' as a valid status.
-- =============================================================================

ALTER TABLE extraction_jobs DROP CONSTRAINT IF EXISTS extraction_jobs_status_check;
ALTER TABLE extraction_jobs ADD CONSTRAINT extraction_jobs_status_check
  CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'cancelled', 'interrupted'));
