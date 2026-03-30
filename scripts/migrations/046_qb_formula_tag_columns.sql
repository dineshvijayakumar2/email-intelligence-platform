-- 046: Add 6 QB formula tag columns to qb_operations
-- These are formula fields computed by QB, synced as TEXT.
-- Our capability_classifier becomes a fallback for operations where QB tags are blank.

ALTER TABLE qb_operations
    ADD COLUMN IF NOT EXISTS qb_process_tag       TEXT,
    ADD COLUMN IF NOT EXISTS qb_capability_tag     TEXT,
    ADD COLUMN IF NOT EXISTS qb_machine_tier_tag   TEXT,
    ADD COLUMN IF NOT EXISTS qb_row_type_tag       TEXT,
    ADD COLUMN IF NOT EXISTS qb_blank_reason_tag   TEXT,
    ADD COLUMN IF NOT EXISTS qb_embellishment_tag  TEXT;

-- Indexes for analytics queries
CREATE INDEX IF NOT EXISTS idx_qb_operations_qb_capability_tag
    ON qb_operations(client_id, qb_capability_tag)
    WHERE qb_capability_tag IS NOT NULL AND qb_capability_tag != '';

CREATE INDEX IF NOT EXISTS idx_qb_operations_qb_process_tag
    ON qb_operations(client_id, qb_process_tag)
    WHERE qb_process_tag IS NOT NULL AND qb_process_tag != '';
