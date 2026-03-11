-- Migration: 022c_fix_qb_field_definitions_data.sql
-- Purpose: Clear stale rows where table_id holds the logical name instead of the QB table ID.
--          Rows will be re-populated on next field fetch (cache-aside via GET /v1/quickbase/fields).
-- Date: March 2026

TRUNCATE TABLE qb_field_definitions;
