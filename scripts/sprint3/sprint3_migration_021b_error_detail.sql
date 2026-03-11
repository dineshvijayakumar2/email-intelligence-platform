-- Migration 021b: Add error_detail column to ai_usage_log
-- Stores the full error message (e.g., "credit balance too low") for display in UI
ALTER TABLE ai_usage_log ADD COLUMN IF NOT EXISTS error_detail TEXT;
