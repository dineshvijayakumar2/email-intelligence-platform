-- Migration 118 (Option A, Phase 1 — NON-DESTRUCTIVE): add the canonical key-id-space
-- shadow column for customer_companies.qb_customer_id.
--
-- qb_customer_id is a MIXED space (record-id in practice) that collides with the
-- customer_key_id space (QB field 3 vs field 92), causing cross-customer contamination
-- (Blainey<->Louis Vuitton, themakehaus<->Payce, etc.). This column holds the name-aware
-- resolution of qb_customer_id to the canonical customer_key_id. Backfilled by the
-- Phase-1 script (mirrors scripts/db/_option_a_plan.py resolve_qb).
--
-- NOTHING reads this column yet — zero behavior change. Phase 2 repoints the 3 read-joins
-- + 5 write-paths to it; Phase 3 drops the old qb_customer_id. Fully reversible (drop col).
ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS qb_customer_key_id text;

COMMENT ON COLUMN customer_companies.qb_customer_key_id IS
  'Option A shadow (mig 118): canonical customer_key_id-space resolution of qb_customer_id, name-aware. Not yet read by code. NULL = ambiguous/unresolved (needs review).';
