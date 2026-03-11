-- Migration: 022_add_qb_field_definitions.sql
-- Purpose: Cache QB field definitions per client/table to avoid repeated QB API calls
-- Date: March 2026

CREATE TABLE IF NOT EXISTS qb_field_definitions (
    id              UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    client_id       TEXT        NOT NULL,
    table_id        TEXT        NOT NULL,   -- QB table ID e.g. buzhzbv39
    table_name      TEXT        NOT NULL,   -- logical name e.g. customers
    field_id        INTEGER     NOT NULL,
    field_label     TEXT        NOT NULL,
    field_type      TEXT,
    synced_at       TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (client_id, table_id, field_id)
);

CREATE INDEX IF NOT EXISTS idx_qb_field_definitions_client_table
    ON qb_field_definitions (client_id, table_id);
