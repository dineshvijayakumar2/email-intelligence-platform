-- Migration: 023_add_qb_sync_log.sql
-- Purpose: Per-table sync audit log — tracks record count and timestamp for each QB table sync
-- Date: March 2026

CREATE TABLE IF NOT EXISTS qb_sync_log (
    id            UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    client_id     TEXT        NOT NULL,
    table_name    TEXT        NOT NULL,   -- logical name: 'customers', 'contacts', etc.
    table_id      TEXT,                   -- QB table ID e.g. buzhzbv39 (FK to qb_field_definitions.table_id)
    record_count  INTEGER     NOT NULL DEFAULT 0,
    synced_at     TIMESTAMPTZ DEFAULT NOW(),
    status        TEXT        NOT NULL DEFAULT 'success',   -- 'success' | 'error'
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_qb_sync_log_client_table_time
    ON qb_sync_log (client_id, table_name, synced_at DESC);

-- Cross-reference index: look up field definitions for a given sync log entry
CREATE INDEX IF NOT EXISTS idx_qb_sync_log_client_table_id
    ON qb_sync_log (client_id, table_id);
