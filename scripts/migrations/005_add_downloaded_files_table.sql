-- Migration: Add downloaded_files table for tracking cached downloads
-- Stage 2: File Caching for Re-processing
-- Date: January 22, 2026

-- =========================================================================
-- Downloaded Files Table (Cache Tracking)
-- =========================================================================

-- Tracks downloaded files to avoid re-downloading when re-processing
-- Works with both local development and cloud storage (Railway)
CREATE TABLE IF NOT EXISTS downloaded_files (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

  -- Source identification
  google_drive_file_id TEXT NOT NULL,
  file_name TEXT NOT NULL,
  file_size BIGINT NOT NULL,

  -- Storage location
  -- For local: file path (e.g., C:\temp\file.olm)
  -- For cloud: storage URL (e.g., s3://bucket/path or supabase storage URL)
  storage_type TEXT NOT NULL DEFAULT 'local',  -- local, s3, r2, supabase
  storage_path TEXT NOT NULL,

  -- Integrity
  checksum TEXT,  -- MD5 or SHA256 for verification

  -- Association
  mailbox_id UUID REFERENCES mailboxes(id) ON DELETE SET NULL,
  last_job_id UUID REFERENCES processing_jobs(id) ON DELETE SET NULL,

  -- Lifecycle
  downloaded_at TIMESTAMPTZ DEFAULT NOW(),
  last_used_at TIMESTAMPTZ DEFAULT NOW(),
  expires_at TIMESTAMPTZ,  -- Optional auto-cleanup
  keep_file BOOLEAN DEFAULT FALSE,  -- If true, don't auto-delete

  -- Status
  is_valid BOOLEAN DEFAULT TRUE,  -- Set to false if file is deleted/corrupted

  -- Timestamps
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),

  -- Unique constraint: one entry per Google Drive file
  UNIQUE(google_drive_file_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_downloaded_files_gdrive_id ON downloaded_files(google_drive_file_id);
CREATE INDEX IF NOT EXISTS idx_downloaded_files_mailbox ON downloaded_files(mailbox_id);
CREATE INDEX IF NOT EXISTS idx_downloaded_files_valid ON downloaded_files(is_valid) WHERE is_valid = TRUE;
CREATE INDEX IF NOT EXISTS idx_downloaded_files_expires ON downloaded_files(expires_at) WHERE expires_at IS NOT NULL;

-- Trigger for updated_at
CREATE TRIGGER update_downloaded_files_updated_at BEFORE UPDATE
    ON downloaded_files FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE downloaded_files TO anon, authenticated;

-- Comments
COMMENT ON TABLE downloaded_files IS 'Tracks downloaded files to enable re-processing without re-downloading';
COMMENT ON COLUMN downloaded_files.storage_type IS 'Where file is stored: local, s3, r2, supabase';
COMMENT ON COLUMN downloaded_files.storage_path IS 'Full path or URL to the stored file';
COMMENT ON COLUMN downloaded_files.keep_file IS 'If true, do not auto-delete after processing';

-- Function to check if a cached file exists and is valid
CREATE OR REPLACE FUNCTION get_cached_download(p_google_drive_file_id TEXT)
RETURNS TABLE (
  id UUID,
  file_name TEXT,
  file_size BIGINT,
  storage_type TEXT,
  storage_path TEXT,
  downloaded_at TIMESTAMPTZ,
  last_used_at TIMESTAMPTZ,
  is_valid BOOLEAN,
  age_hours NUMERIC
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    df.id,
    df.file_name,
    df.file_size,
    df.storage_type,
    df.storage_path,
    df.downloaded_at,
    df.last_used_at,
    df.is_valid,
    EXTRACT(EPOCH FROM (NOW() - df.downloaded_at)) / 3600 as age_hours
  FROM downloaded_files df
  WHERE df.google_drive_file_id = p_google_drive_file_id
    AND df.is_valid = TRUE
    AND (df.expires_at IS NULL OR df.expires_at > NOW())
  LIMIT 1;
$$;

GRANT EXECUTE ON FUNCTION get_cached_download(TEXT) TO anon, authenticated;

-- Function to mark a download as used (updates last_used_at)
CREATE OR REPLACE FUNCTION mark_download_used(p_download_id UUID)
RETURNS VOID
LANGUAGE sql
AS $$
  UPDATE downloaded_files
  SET last_used_at = NOW()
  WHERE id = p_download_id;
$$;

GRANT EXECUTE ON FUNCTION mark_download_used(UUID) TO anon, authenticated;

-- Function to invalidate a cached download
CREATE OR REPLACE FUNCTION invalidate_download(p_download_id UUID)
RETURNS VOID
LANGUAGE sql
AS $$
  UPDATE downloaded_files
  SET is_valid = FALSE
  WHERE id = p_download_id;
$$;

GRANT EXECUTE ON FUNCTION invalidate_download(UUID) TO anon, authenticated;

-- Update statistics
ANALYZE downloaded_files;
