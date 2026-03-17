-- ============================================================================
-- Migration 029: Drop rigid CHECK constraints on ai_email_intelligence
-- ============================================================================
-- Purpose: Custom prompts return custom intent/sentiment values that don't
--          match the hardcoded CHECK constraints. Drop them to allow flexibility.
-- ============================================================================

-- Drop intent check (custom prompts: quote_request, job_approval, artwork_submission, etc.)
ALTER TABLE ai_email_intelligence DROP CONSTRAINT IF EXISTS ai_email_intelligence_intent_check;

-- Drop sentiment check (custom prompts use 'mixed' which isn't in the original list)
ALTER TABLE ai_email_intelligence DROP CONSTRAINT IF EXISTS ai_email_intelligence_sentiment_check;
