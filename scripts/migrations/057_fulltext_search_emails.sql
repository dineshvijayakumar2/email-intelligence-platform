-- Migration 057: Full-text search infrastructure for hybrid retrieval (Phase 2)
-- Adds a tsvector column + GIN index to emails for BM25-style keyword search.
-- Prerequisite for the hybrid retriever (vector + keyword + RRF fusion).
--
-- RUN STEPS 1-3 and 5 first (instant). Then run step 4 separately in batches.

-- 1. Generated tsvector column — weighted: subject (A) > body_text (B)
ALTER TABLE emails ADD COLUMN IF NOT EXISTS search_text tsvector;

-- 2. GIN index for fast full-text queries
CREATE INDEX IF NOT EXISTS idx_emails_search_text
    ON emails USING GIN(search_text)
    WHERE search_text IS NOT NULL;

-- 3. Trigger to auto-populate search_text on INSERT/UPDATE
--    New emails get search_text automatically — only existing rows need backfill.
CREATE OR REPLACE FUNCTION emails_search_text_trigger() RETURNS trigger AS $$
BEGIN
    NEW.search_text :=
        setweight(to_tsvector('english', COALESCE(NEW.subject, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(LEFT(NEW.body_text, 5000), '')), 'B') ||
        setweight(to_tsvector('english', COALESCE(NEW.sender_name, '')), 'C');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_emails_search_text ON emails;
CREATE TRIGGER trg_emails_search_text
    BEFORE INSERT OR UPDATE OF subject, body_text, sender_name
    ON emails FOR EACH ROW
    EXECUTE FUNCTION emails_search_text_trigger();

-- 4. Backfill existing rows — RUN SEPARATELY in batches of 10K to avoid timeout.
--    The RPC below processes one batch per call. Run repeatedly until it returns 0.

-- Returns TABLE so PostgREST can expose it properly (scalar returns are problematic)
CREATE OR REPLACE FUNCTION backfill_search_text(p_batch_size int DEFAULT 10000)
RETURNS TABLE(updated_count int)
LANGUAGE plpgsql AS $$
BEGIN
    WITH batch AS (
        SELECT id FROM emails
        WHERE search_text IS NULL
        LIMIT p_batch_size
        FOR UPDATE SKIP LOCKED
    )
    UPDATE emails e
    SET search_text =
        setweight(to_tsvector('english', COALESCE(e.subject, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(LEFT(e.body_text, 5000), '')), 'B') ||
        setweight(to_tsvector('english', COALESCE(e.sender_name, '')), 'C')
    FROM batch
    WHERE e.id = batch.id;

    GET DIAGNOSTICS updated_count = ROW_COUNT;
    RETURN NEXT;
END;
$$;

-- To backfill, call this RPC repeatedly until it returns 0:
--   SELECT backfill_search_text(10000);  -- processes 10K rows per call
--   SELECT backfill_search_text(10000);  -- repeat until returns 0

-- 5. Keyword search RPC — returns BM25-ranked results using ts_rank_cd
CREATE OR REPLACE FUNCTION keyword_search_emails(
    p_query      text,
    p_client_id  uuid    DEFAULT NULL,
    p_date_from  timestamptz DEFAULT NULL,
    p_date_to    timestamptz DEFAULT NULL,
    p_limit      int     DEFAULT 20
)
RETURNS TABLE (
    id           uuid,
    subject      text,
    sender_email text,
    sender_name  text,
    sent_date    timestamptz,
    is_outbound  boolean,
    rank_score   float
)
LANGUAGE plpgsql
AS $$
DECLARE
    tsq tsquery;
BEGIN
    tsq := websearch_to_tsquery('english', p_query);

    RETURN QUERY
    SELECT
        e.id, e.subject, e.sender_email, e.sender_name,
        e.sent_date, e.is_outbound,
        ts_rank_cd(e.search_text, tsq, 32)::float AS rank_score
    FROM emails e
    WHERE e.search_text IS NOT NULL
      AND e.search_text @@ tsq
      AND (p_client_id IS NULL OR e.client_id = p_client_id)
      AND (p_date_from IS NULL OR e.sent_date >= p_date_from)
      AND (p_date_to   IS NULL OR e.sent_date <= p_date_to)
    ORDER BY rank_score DESC
    LIMIT p_limit;
END;
$$;
