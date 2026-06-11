-- Migration 119: Make qb_operations.profit_pct unbounded NUMERIC
-- ----------------------------------------------------------------------------
-- qb_operations is a faithful cache of QuickBase's Operations table. profit_pct
-- (field 25, "Profit %") is a QB-computed percentage that explodes when cost
-- approaches zero — e.g. a $500 sale with $0.01 cost computes ~5,000,000%.
--
-- The column started as DECIMAL(5,2) (±999.99), was widened to DECIMAL(8,2)
-- (±999,999.99) in migration 036, and is now overflowing again on values
-- >= 10^6 ("numeric field overflow ... precision 8, scale 2"). Picking any
-- new fixed precision just moves the ceiling; QB can produce an arbitrarily
-- large percentage.
--
-- profit_pct is display-only (shown in the QB data table; never aggregated or
-- used in computation), so there is no downstream reason to bound it. Drop the
-- precision/scale entirely so the cache mirrors whatever QB sends without ever
-- overflowing. NUMERIC keeps fractional precision (unlike a widened DECIMAL we
-- would have to keep bumping).

ALTER TABLE qb_operations
  ALTER COLUMN profit_pct TYPE NUMERIC;

COMMENT ON COLUMN qb_operations.profit_pct IS 'QB Profit % (field 25). Unbounded NUMERIC — QB computes astronomically large percentages when cost approaches zero. Display-only, never aggregated. See migration 119.';
