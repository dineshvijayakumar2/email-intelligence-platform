-- ============================================================================
-- Migration 037: Vector Embeddings Infrastructure (pgvector)
-- ============================================================================
-- Purpose: Enable semantic search across emails, companies, and operations
-- using pgvector (pre-installed on Supabase) with Google text-embedding-004
-- (768 dimensions).
--
-- Embeddings are independent of AI analysis — they embed raw source data:
--   emails.embedding       ← subject + body_text + sender
--   customer_companies     ← name + industry + domains + QB data
--   qb_operations          ← operation + dept + machine + capabilities
-- ============================================================================

-- 1. Enable pgvector extension (idempotent on Supabase)
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Add embedding columns (768 dims = Google text-embedding-004)
--    emails table — raw email content, independent of AI pipeline
ALTER TABLE emails
    ADD COLUMN IF NOT EXISTS embedding vector(768);

-- Remove from ai_email_intelligence if previously added (cleanup)
-- ALTER TABLE ai_email_intelligence DROP COLUMN IF EXISTS embedding;

ALTER TABLE customer_companies
    ADD COLUMN IF NOT EXISTS embedding vector(768);

ALTER TABLE qb_operations
    ADD COLUMN IF NOT EXISTS embedding vector(768);

-- 3. HNSW indexes for approximate nearest-neighbor search
--    m=16, ef_construction=64 are good defaults for <1M rows
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

-- 4. RPC function for email semantic search (searches raw emails table)
DROP FUNCTION IF EXISTS search_email_intelligence;
DROP FUNCTION IF EXISTS search_emails(vector, float, int, uuid);

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
        e.id,
        e.subject,
        e.sender_email,
        e.sender_name,
        e.sent_date,
        e.is_outbound,
        1 - (e.embedding <=> query_embedding) AS similarity
    FROM emails e
    WHERE e.embedding IS NOT NULL
      AND (p_client_id IS NULL OR e.client_id = p_client_id)
      AND 1 - (e.embedding <=> query_embedding) > match_threshold
    ORDER BY e.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- 5. RPC function for company semantic search
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
        c.id,
        c.company_name,
        c.industry,
        c.email_domains,
        c.qb_tier,
        c.qb_total_revenue,
        1 - (c.embedding <=> query_embedding) AS similarity
    FROM customer_companies c
    WHERE c.embedding IS NOT NULL
      AND (p_client_id IS NULL OR c.client_id = p_client_id)
      AND 1 - (c.embedding <=> query_embedding) > match_threshold
    ORDER BY c.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- 6. RPC function for operations semantic search
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
        o.id,
        o.operation_name,
        o.department,
        o.machine,
        o.customer_name,
        o.capability_tags,
        o.row_type,
        1 - (o.embedding <=> query_embedding) AS similarity
    FROM qb_operations o
    WHERE o.embedding IS NOT NULL
      AND (p_client_id IS NULL OR o.client_id = p_client_id)
      AND 1 - (o.embedding <=> query_embedding) > match_threshold
    ORDER BY o.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
