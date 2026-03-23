-- Migration 036: Widen qb_operations.profit_pct column
-- DECIMAL(5,2) max is ±999.99 — some QB operations have extreme profit/loss percentages
-- that overflow this. Widen to DECIMAL(8,2) to handle up to ±999999.99%.

ALTER TABLE qb_operations
  ALTER COLUMN profit_pct TYPE DECIMAL(8,2);
