-- Migration 019b: Backfill threading columns (batched, timeout-safe)
--
-- Processes 2000 rows per iteration to stay well under Supabase statement timeout.
-- Re-runnable: only touches rows where target columns are still NULL.
-- Run this AFTER 019 (schema + indexes).
--
-- For very large tables (500K+), run this multiple times until it reports 0 updated.
-- Each execution processes up to 100K rows (50 iterations × 2000 rows).

-- ============================================================================
-- Backfill 1: Extract headers from raw_headers JSONB
-- ============================================================================
DO $$
DECLARE
  _batch_size INT := 2000;
  _max_iterations INT := 50;
  _iteration INT := 0;
  _updated INT;
BEGIN
  LOOP
    _iteration := _iteration + 1;
    EXIT WHEN _iteration > _max_iterations;

    UPDATE emails SET
      internet_message_id = COALESCE(
        NULLIF(raw_headers->>'Message-ID', ''),
        NULLIF(raw_headers->>'Message-Id', ''),
        NULLIF(raw_headers->>'message-id', '')
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
      LIMIT _batch_size
    );

    GET DIAGNOSTICS _updated = ROW_COUNT;
    RAISE NOTICE 'Headers backfill iteration %: updated % rows', _iteration, _updated;
    EXIT WHEN _updated = 0;

    -- Small pause to reduce lock contention
    PERFORM pg_sleep(0.1);
  END LOOP;

  RAISE NOTICE 'Headers backfill complete after % iterations', _iteration;
END $$;

-- ============================================================================
-- Backfill 2: Normalize subjects
-- ============================================================================
DO $$
DECLARE
  _batch_size INT := 2000;
  _max_iterations INT := 50;
  _iteration INT := 0;
  _updated INT;
BEGIN
  LOOP
    _iteration := _iteration + 1;
    EXIT WHEN _iteration > _max_iterations;

    UPDATE emails SET
      subject_normalized = LOWER(TRIM(
        regexp_replace(subject, '^(\s*(RE|FW|FWD|AW|WG|SV|VS|TR|Re|Fw|Fwd|Aw|Wg)\s*:\s*)+', '', 'i')
      ))
    WHERE id IN (
      SELECT id FROM emails
      WHERE subject_normalized IS NULL
        AND subject IS NOT NULL
      LIMIT _batch_size
    );

    GET DIAGNOSTICS _updated = ROW_COUNT;
    RAISE NOTICE 'Subject norm iteration %: updated % rows', _iteration, _updated;
    EXIT WHEN _updated = 0;

    PERFORM pg_sleep(0.1);
  END LOOP;

  RAISE NOTICE 'Subject normalization complete after % iterations', _iteration;
END $$;

-- ============================================================================
-- If you see "50 iterations" in the output, run this file again.
-- Repeat until both report 0 updated on iteration 1.
-- ============================================================================
