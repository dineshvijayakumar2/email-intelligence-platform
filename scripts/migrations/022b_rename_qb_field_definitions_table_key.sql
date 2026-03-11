-- Migration: 022b_rename_qb_field_definitions_table_key.sql
-- Purpose: Rename table_key → table_id in qb_field_definitions (use QB table ID as key)
-- Run this only if 022 was already applied with the old table_key column.
-- Safe to skip if running fresh (022 already has table_id).

DO $$
BEGIN
    -- Rename table_key → table_id if old column still exists
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'qb_field_definitions' AND column_name = 'table_key'
    ) THEN
        ALTER TABLE qb_field_definitions RENAME COLUMN table_key TO table_id;

        ALTER TABLE qb_field_definitions
            DROP CONSTRAINT IF EXISTS qb_field_definitions_client_id_table_key_field_id_key;
        ALTER TABLE qb_field_definitions
            ADD CONSTRAINT qb_field_definitions_client_id_table_id_field_id_key
            UNIQUE (client_id, table_id, field_id);

        DROP INDEX IF EXISTS idx_qb_field_definitions_client_table;
        CREATE INDEX idx_qb_field_definitions_client_table
            ON qb_field_definitions (client_id, table_id);
    END IF;

    -- Add table_name column if it doesn't exist yet
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'qb_field_definitions' AND column_name = 'table_name'
    ) THEN
        ALTER TABLE qb_field_definitions ADD COLUMN table_name TEXT;
        -- Back-fill existing rows with empty string (will be populated on next sync)
        UPDATE qb_field_definitions SET table_name = '' WHERE table_name IS NULL;
        ALTER TABLE qb_field_definitions ALTER COLUMN table_name SET NOT NULL;
    END IF;
END $$;
