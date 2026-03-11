-- Migration 019b: Backfill threading columns
-- SPLIT into 4 independent scripts. Run each one separately in Supabase SQL editor.
-- Each script processes ~10K rows and completes in <30 seconds.
-- Re-run each script until it reports "updated 0 rows" on iteration 1.

-- ============================================================================
-- SCRIPT 1 of 4: Extract Message-ID from raw_headers (10K per run)
-- ============================================================================
DO $$
DECLARE
  _updated INT;
  _total INT := 0;
  _i INT := 0;
BEGIN
  FOR _i IN 1..5 LOOP
    UPDATE emails SET
      internet_message_id = COALESCE(
        NULLIF(raw_headers->>'Message-ID', ''),
        NULLIF(raw_headers->>'Message-Id', ''),
        NULLIF(raw_headers->>'message-id', ''),
        '__none__'
      ),
      in_reply_to = COALESCE(
        NULLIF(raw_headers->>'In-Reply-To', ''),
        NULLIF(raw_headers->>'in-reply-to', '')
      ),
      references_header = COALESCE(
        NULLIF(raw_headers->>'References', ''),
        NULLIF(raw_headers->>'references', '')
      )
    WHERE id IN (
      SELECT id FROM emails
      WHERE internet_message_id IS NULL
        AND raw_headers IS NOT NULL
        AND raw_headers != '{}'::jsonb
      LIMIT 2000
    );
    GET DIAGNOSTICS _updated = ROW_COUNT;
    _total := _total + _updated;
    RAISE NOTICE 'Iter %: % rows (total %)', _i, _updated, _total;
    EXIT WHEN _updated = 0;
  END LOOP;
END $$;
-- Re-run until "Iter 1: 0 rows"


-- ============================================================================
-- SCRIPT 2 of 4: Mark emails with no raw_headers as __none__ (25K per run)
-- ============================================================================
DO $$
DECLARE
  _updated INT;
  _total INT := 0;
  _i INT := 0;
BEGIN
  FOR _i IN 1..5 LOOP
    UPDATE emails SET internet_message_id = '__none__'
    WHERE id IN (
      SELECT id FROM emails
      WHERE internet_message_id IS NULL
        AND (raw_headers IS NULL OR raw_headers = '{}'::jsonb)
      LIMIT 5000
    );
    GET DIAGNOSTICS _updated = ROW_COUNT;
    _total := _total + _updated;
    RAISE NOTICE 'Iter %: % rows (total %)', _i, _updated, _total;
    EXIT WHEN _updated = 0;
  END LOOP;
END $$;
-- Re-run until "Iter 1: 0 rows"


-- ============================================================================
-- SCRIPT 3 of 4: Mark emails that HAVE headers but no Message-ID (25K per run)
-- ============================================================================
-- This is the big one (145K rows). Just marks them so they stop being "missing".
DO $$
DECLARE
  _updated INT;
  _total INT := 0;
  _i INT := 0;
BEGIN
  FOR _i IN 1..5 LOOP
    UPDATE emails SET internet_message_id = '__none__'
    WHERE id IN (
      SELECT id FROM emails
      WHERE internet_message_id IS NULL
        AND raw_headers IS NOT NULL
        AND raw_headers != '{}'::jsonb
        AND raw_headers->>'Message-ID' IS NULL
        AND raw_headers->>'Message-Id' IS NULL
        AND raw_headers->>'message-id' IS NULL
      LIMIT 5000
    );
    GET DIAGNOSTICS _updated = ROW_COUNT;
    _total := _total + _updated;
    RAISE NOTICE 'Iter %: % rows (total %)', _i, _updated, _total;
    EXIT WHEN _updated = 0;
  END LOOP;
END $$;
-- Re-run until "Iter 1: 0 rows"


-- ============================================================================
-- SCRIPT 4 of 4: Normalize subjects (10K per run)
-- ============================================================================
DO $$
DECLARE
  _updated INT;
  _total INT := 0;
  _i INT := 0;
BEGIN
  FOR _i IN 1..5 LOOP
    UPDATE emails SET
      subject_normalized = LOWER(TRIM(
        regexp_replace(subject, '^(\s*(RE|FW|FWD|AW|WG|SV|VS|TR|Re|Fw|Fwd|Aw|Wg)\s*:\s*)+', '', 'i')
      ))
    WHERE id IN (
      SELECT id FROM emails
      WHERE subject_normalized IS NULL AND subject IS NOT NULL
      LIMIT 2000
    );
    GET DIAGNOSTICS _updated = ROW_COUNT;
    _total := _total + _updated;
    RAISE NOTICE 'Iter %: % rows (total %)', _i, _updated, _total;
    EXIT WHEN _updated = 0;
  END LOOP;
END $$;
-- Re-run until "Iter 1: 0 rows"


-- ============================================================================
-- VERIFICATION (run after all scripts complete):
-- ============================================================================
-- SELECT
--   COUNT(*) FILTER (WHERE internet_message_id IS NOT NULL AND internet_message_id != '__none__') AS has_real_msg_id,
--   COUNT(*) FILTER (WHERE internet_message_id = '__none__') AS no_msg_id_available,
--   COUNT(*) FILTER (WHERE internet_message_id IS NULL) AS still_pending,
--   COUNT(*) FILTER (WHERE subject_normalized IS NOT NULL) AS has_subject_norm,
--   COUNT(*) FILTER (WHERE subject_normalized IS NULL) AS missing_subject_norm
-- FROM emails;
