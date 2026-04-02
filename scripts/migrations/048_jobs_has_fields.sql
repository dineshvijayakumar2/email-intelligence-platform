-- Migration 048: Add "Has X?" embellishment flag columns to qb_jobs
-- These are Formula-Text fields in QB that indicate whether a job uses specific embellishments.

ALTER TABLE qb_jobs
    ADD COLUMN IF NOT EXISTS has_hot_foil TEXT,
    ADD COLUMN IF NOT EXISTS has_spot_uv TEXT,
    ADD COLUMN IF NOT EXISTS has_special_substrate TEXT,
    ADD COLUMN IF NOT EXISTS has_digital_foil TEXT,
    ADD COLUMN IF NOT EXISTS has_de_emboss TEXT,
    ADD COLUMN IF NOT EXISTS has_raised_ink TEXT,
    ADD COLUMN IF NOT EXISTS has_laser_cut TEXT,
    ADD COLUMN IF NOT EXISTS has_white_ink TEXT;
