-- Migration 109: Fix candidate unique index to allow multiple SB company options per QB customer.
--
-- The old index (client_id, qb_record_id) WHERE reviewed = FALSE only allows ONE
-- unreviewed candidate per QB customer. But multi-match staging legitimately creates
-- multiple candidates (one per SB company option) for the same QB customer.
--
-- New index: (client_id, qb_record_id, sb_company_id) WHERE reviewed = FALSE
-- This allows multiple SB company options while still preventing exact duplicates.

DROP INDEX IF EXISTS idx_qmc_unique_unreviewed;

CREATE UNIQUE INDEX idx_qmc_unique_unreviewed
  ON qb_match_candidates(client_id, qb_record_id, sb_company_id) WHERE reviewed = FALSE;
