-- Migration 056: Add date filters to vector search RPC functions
-- Adds p_date_from and p_date_to params so semantic search can be time-scoped.
-- Without these, "what happened last quarter" queries return results from
-- the entire corpus — the date params in the Python caller are silently ignored.

-- search_emails: filter on e.sent_date
CREATE OR REPLACE FUNCTION search_emails(
    query_embedding vector(768),
    match_threshold float DEFAULT 0.7,
    match_count int DEFAULT 10,
    p_client_id uuid DEFAULT NULL,
    p_date_from timestamptz DEFAULT NULL,
    p_date_to   timestamptz DEFAULT NULL
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
      AND (p_date_from IS NULL OR e.sent_date >= p_date_from)
      AND (p_date_to   IS NULL OR e.sent_date <= p_date_to)
      AND 1 - (e.embedding <=> query_embedding) > match_threshold
    ORDER BY e.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;


-- search_companies: filter on c.last_contact_date
CREATE OR REPLACE FUNCTION search_companies(
    query_embedding vector(768),
    match_threshold float DEFAULT 0.7,
    match_count int DEFAULT 10,
    p_client_id uuid DEFAULT NULL,
    p_date_from timestamptz DEFAULT NULL,
    p_date_to   timestamptz DEFAULT NULL
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
      AND (p_date_from IS NULL OR c.last_contact_date >= p_date_from)
      AND (p_date_to   IS NULL OR c.last_contact_date <= p_date_to)
      AND 1 - (c.embedding <=> query_embedding) > match_threshold
    ORDER BY c.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
