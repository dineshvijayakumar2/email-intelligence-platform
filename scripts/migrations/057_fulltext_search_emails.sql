-- Migration 057: Full-text search infrastructure for hybrid retrieval (Phase 2)
-- Adds a tsvector column + GIN index to emails for BM25-style keyword search.
-- Prerequisite for the hybrid retriever (vector + keyword + RRF fusion).

-- 1. Generated tsvector column — weighted: subject (A) > body_text (B)
ALTER TABLE emails ADD COLUMN IF NOT EXISTS search_text tsvector;

-- 2. GIN index for fast full-text queries
CREATE INDEX IF NOT EXISTS idx_emails_search_text
    ON emails USING GIN(search_text)
    WHERE search_text IS NOT NULL;

-- 3. Trigger to auto-populate search_text on INSERT/UPDATE
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

-- 4. Backfill existing rows (run once — may take a few minutes on large tables)
UPDATE emails
SET search_text =
    setweight(to_tsvector('english', COALESCE(subject, '')), 'A') ||
    setweight(to_tsvector('english', COALESCE(LEFT(body_text, 5000), '')), 'B') ||
    setweight(to_tsvector('english', COALESCE(sender_name, '')), 'C')
WHERE search_text IS NULL;

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
    -- Build tsquery: split words, join with & for AND semantics
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
