-- ============================================================================
-- Migration 124: capability_tags never-classified sentinel = NULL (was '[]')
-- ============================================================================
-- _classify_operations (sync enrichment) selects unclassified ops with
-- `capability_tags = '[]'`. After the Layer-1 full reclassify, an empty array '[]'
-- is now a LEGITIMATE classifier result (413k generic ops the classifier has no
-- opinion on), so '[]' can no longer mean "needs classifying" — the sync would
-- re-process those 413k rows on every run.
--
-- Fix: make the never-classified sentinel NULL. New synced operations arrive NULL
-- (column default) and the sync filters `capability_tags IS NULL`; once classified
-- they become '[]' or ["X"] (non-null) and are never reprocessed. Existing rows are
-- unchanged (all already classified, non-null). Consumers (capability_resolution.
-- caps_for_op) already treat NULL as "no opinion -> fall back to qb tag".
-- ============================================================================

ALTER TABLE qb_operations ALTER COLUMN capability_tags SET DEFAULT NULL;
