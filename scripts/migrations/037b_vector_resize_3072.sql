-- ============================================================================
-- Migration 037b: Reset vector columns to 768 dims (with HNSW indexes)
-- ============================================================================
-- gemini-embedding-001 natively outputs 3072 dims, but pgvector HNSW/IVFFlat
-- indexes have a 2000-dim limit. We use output_dimensionality=768 in the
-- Python embedding model to truncate to 768 dims — same quality for search,
-- 4x less storage, and fast HNSW indexing.
-- ============================================================================

-- 1. Drop existing indexes (may be wrong size or type from prior attempts)
DROP INDEX IF EXISTS idx_emails_embedding;
DROP INDEX IF EXISTS idx_companies_embedding;
DROP INDEX IF EXISTS idx_operations_embedding;

-- 2. Drop and re-add columns as vector(768) — instant, no data rewrite
ALTER TABLE emails DROP COLUMN IF EXISTS embedding;
ALTER TABLE emails ADD COLUMN embedding vector(768);

ALTER TABLE customer_companies DROP COLUMN IF EXISTS embedding;
ALTER TABLE customer_companies ADD COLUMN embedding vector(768);

ALTER TABLE qb_operations DROP COLUMN IF EXISTS embedding;
ALTER TABLE qb_operations ADD COLUMN embedding vector(768);

-- 3. Recreate HNSW indexes (supports up to 2000 dims, 768 is well within range)
CREATE INDEX IF NOT EXISTS idx_emails_embedding
    ON emails
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_companies_embedding
    ON customer_companies
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_operations_embedding
    ON qb_operations
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- 4. Update RPC functions to accept vector(768)
DROP FUNCTION IF EXISTS search_emails(vector, float, int, uuid);
DROP FUNCTION IF EXISTS search_emails(vector(3072), float, int, uuid);
CREATE OR REPLACE FUNCTION search_emails(
    query_embedding vector(768),
    match_threshold float DEFAULT 0.7,
    match_count int DEFAULT 10,
    p_client_id uuid DEFAULT NULL
)
RETURNS TABLE (
    id uuid,
    subject text,
    sender_email text,
    sender_name text,
    sent_date timestamptz,
    is_outbound boolean,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        e.id, e.subject, e.sender_email, e.sender_name,
        e.sent_date, e.is_outbound,
        1 - (e.embedding <=> query_embedding) AS similarity
    FROM emails e
    WHERE e.embedding IS NOT NULL
      AND (p_client_id IS NULL OR e.client_id = p_client_id)
      AND 1 - (e.embedding <=> query_embedding) > match_threshold
    ORDER BY e.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

DROP FUNCTION IF EXISTS search_companies(vector, float, int, uuid);
DROP FUNCTION IF EXISTS search_companies(vector(3072), float, int, uuid);
CREATE OR REPLACE FUNCTION search_companies(
    query_embedding vector(768),
    match_threshold float DEFAULT 0.7,
    match_count int DEFAULT 10,
    p_client_id uuid DEFAULT NULL
)
RETURNS TABLE (
    id uuid,
    company_name text,
    industry text,
    email_domains jsonb,
    qb_tier text,
    qb_total_revenue numeric,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.id, c.company_name, c.industry, c.email_domains,
        c.qb_tier, c.qb_total_revenue,
        1 - (c.embedding <=> query_embedding) AS similarity
    FROM customer_companies c
    WHERE c.embedding IS NOT NULL
      AND (p_client_id IS NULL OR c.client_id = p_client_id)
      AND 1 - (c.embedding <=> query_embedding) > match_threshold
    ORDER BY c.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

DROP FUNCTION IF EXISTS search_operations(vector, float, int, uuid);
DROP FUNCTION IF EXISTS search_operations(vector(3072), float, int, uuid);
CREATE OR REPLACE FUNCTION search_operations(
    query_embedding vector(768),
    match_threshold float DEFAULT 0.7,
    match_count int DEFAULT 10,
    p_client_id uuid DEFAULT NULL
)
RETURNS TABLE (
    id uuid,
    operation_name text,
    department text,
    machine text,
    customer_name text,
    capability_tags jsonb,
    row_type varchar,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        o.id, o.operation_name, o.department, o.machine,
        o.customer_name, o.capability_tags, o.row_type,
        1 - (o.embedding <=> query_embedding) AS similarity
    FROM qb_operations o
    WHERE o.embedding IS NOT NULL
      AND (p_client_id IS NULL OR o.client_id = p_client_id)
      AND 1 - (o.embedding <=> query_embedding) > match_threshold
    ORDER BY o.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
