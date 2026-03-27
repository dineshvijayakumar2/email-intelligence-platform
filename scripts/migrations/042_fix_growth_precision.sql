-- Migration 042: Widen growth columns to handle >1000% growth
-- qb_growth_90d on both qb_customers and customer_companies overflows at ±999.99

ALTER TABLE qb_customers
  ALTER COLUMN growth_90d TYPE DECIMAL(8,2);

ALTER TABLE customer_companies
  ALTER COLUMN qb_growth_90d TYPE DECIMAL(8,2);
