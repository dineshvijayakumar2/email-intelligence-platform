-- ============================================================================
-- Migration 021: Quickbase Cache + Strategic Digest + AM Performance
-- Run AFTER migration 021a (QB enrichment columns)
-- ============================================================================

-- 1. qb_sync_config — Per-client Quickbase connection settings
CREATE TABLE IF NOT EXISTS qb_sync_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    realm_hostname TEXT NOT NULL,
    app_id TEXT NOT NULL,
    user_token_encrypted TEXT NOT NULL,
    customers_table_id TEXT NOT NULL,
    contacts_table_id TEXT NOT NULL,
    quotes_table_id TEXT NOT NULL,
    jobs_table_id TEXT NOT NULL,
    sales_line_items_table_id TEXT NOT NULL,
    field_mappings JSONB NOT NULL DEFAULT '{}',
    sync_interval_hours INTEGER DEFAULT 6,
    last_sync_at TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(client_id)
);

-- 2. qb_customers — Cached Quickbase Customers
CREATE TABLE IF NOT EXISTS qb_customers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    qb_record_id TEXT NOT NULL,
    customer_name TEXT NOT NULL,
    customer_code TEXT,
    customer_tier TEXT,
    customer_status TEXT,
    account_manager TEXT,
    industry TEXT,
    active BOOLEAN DEFAULT TRUE,
    total_invoiced DECIMAL(12,2),
    invoiced_ty DECIMAL(12,2),
    invoiced_ly DECIMAL(12,2),
    invoiced_l90d DECIMAL(12,2),
    invoiced_l12m DECIMAL(12,2),
    recency_days INTEGER,
    cadence_score DECIMAL(5,2),
    growth_90d DECIMAL(8,2),
    days_since_last_invoice INTEGER,
    matched_company_id UUID REFERENCES customer_companies(id) ON DELETE SET NULL,
    qb_last_modified TIMESTAMPTZ,
    synced_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(client_id, qb_record_id)
);

-- 3. qb_contacts — Cached Quickbase Contacts
CREATE TABLE IF NOT EXISTS qb_contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    qb_record_id TEXT NOT NULL,
    qb_customer_id TEXT,
    first_name TEXT,
    surname TEXT,
    email TEXT,
    phone TEXT,
    active BOOLEAN DEFAULT TRUE,
    contact_recency_days INTEGER,
    quotes_accepted_count INTEGER DEFAULT 0,
    most_recent_quote_date DATE,
    matched_contact_id UUID REFERENCES customer_contacts(id) ON DELETE SET NULL,
    qb_last_modified TIMESTAMPTZ,
    synced_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(client_id, qb_record_id)
);

-- 4. qb_quotes — Cached Quickbase Quotes
CREATE TABLE IF NOT EXISTS qb_quotes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    qb_record_id TEXT NOT NULL,
    qb_customer_id TEXT,
    quote_no TEXT,
    quote_am_name TEXT,
    sell_ex_tax DECIMAL(12,2),
    date_created DATE,
    date_accepted DATE,
    category TEXT,
    contact_email TEXT,
    contact_name TEXT,
    job_no TEXT,
    has_job BOOLEAN DEFAULT FALSE,
    quantity INTEGER,
    kinds INTEGER,
    total_quantity INTEGER,
    matched_company_id UUID REFERENCES customer_companies(id) ON DELETE SET NULL,
    qb_last_modified TIMESTAMPTZ,
    synced_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(client_id, qb_record_id)
);

-- 5. qb_jobs — Cached Quickbase Jobs
CREATE TABLE IF NOT EXISTS qb_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    qb_record_id TEXT NOT NULL,
    qb_customer_id TEXT,
    job_no TEXT,
    quote_no TEXT,
    job_status TEXT,
    retail_sale DECIMAL(12,2),
    invoiced_margin DECIMAL(12,2),
    margin_pct DECIMAL(5,2),
    accepted_date DATE,
    due_date DATE,
    factory_rush_level TEXT,
    pieces_ordered INTEGER,
    kinds_ordered INTEGER,
    total_qty_ordered INTEGER,
    matched_company_id UUID REFERENCES customer_companies(id) ON DELETE SET NULL,
    qb_last_modified TIMESTAMPTZ,
    synced_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(client_id, qb_record_id)
);

-- 6. qb_sales_line_items — Cached Quickbase Sales (invoiced revenue)
CREATE TABLE IF NOT EXISTS qb_sales_line_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    qb_record_id TEXT NOT NULL,
    qb_customer_id TEXT,
    invoice_id TEXT,
    invoice_no TEXT,
    job_no TEXT,
    job_am_name TEXT,
    customer_name TEXT,
    inv_date DATE,
    subtotal DECIMAL(12,2),
    total DECIMAL(12,2),
    product_group TEXT,
    industry TEXT,
    job_title TEXT,
    matched_company_id UUID REFERENCES customer_companies(id) ON DELETE SET NULL,
    qb_last_modified TIMESTAMPTZ,
    synced_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(client_id, qb_record_id)
);

-- 7. relationship_context_cache — Pre-computed relationship summaries
CREATE TABLE IF NOT EXISTS relationship_context_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    company_id UUID NOT NULL REFERENCES customer_companies(id) ON DELETE CASCADE,
    customer_type TEXT,
    customer_tier TEXT,
    account_manager TEXT,
    engagement_trajectory TEXT,
    engagement_scores_history JSONB DEFAULT '[]',
    communication_health JSONB DEFAULT '{}',
    key_contacts JSONB DEFAULT '[]',
    active_threads_summary JSONB DEFAULT '[]',
    ai_signals_summary JSONB DEFAULT '{}',
    qb_financial_summary JSONB DEFAULT '{}',
    computed_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(client_id, company_id)
);

-- 8. ai_strategic_digests — Strategic digest output (flexible periods)
CREATE TABLE IF NOT EXISTS ai_strategic_digests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES clients(id) ON DELETE SET NULL,
    digest_date DATE NOT NULL,
    period_type TEXT NOT NULL CHECK (period_type IN ('weekly', 'monthly', 'quarterly', 'ytd', 'custom')),
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    comparison_period_start DATE,
    comparison_period_end DATE,
    executive_summary TEXT,
    relationship_health JSONB DEFAULT '[]',
    pipeline_intelligence JSONB DEFAULT '{}',
    risk_alerts JSONB DEFAULT '[]',
    opportunities JSONB DEFAULT '[]',
    competitive_landscape JSONB DEFAULT '{}',
    am_performance JSONB DEFAULT '{}',
    action_items JSONB DEFAULT '[]',
    companies_analyzed INTEGER DEFAULT 0,
    contacts_analyzed INTEGER DEFAULT 0,
    emails_analyzed INTEGER DEFAULT 0,
    qb_orders_included INTEGER DEFAULT 0,
    qb_quotes_included INTEGER DEFAULT 0,
    model_used TEXT,
    total_input_tokens INTEGER DEFAULT 0,
    total_output_tokens INTEGER DEFAULT 0,
    total_cost_usd DECIMAL(8,6) DEFAULT 0,
    chain_steps_completed INTEGER DEFAULT 0,
    prompt_version TEXT DEFAULT 'v1.0',
    raw_ai_responses JSONB,
    generation_time_ms INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(client_id, digest_date, period_type)
);

-- 9. am_performance_snapshots — AM performance per period (computed, not AI)
CREATE TABLE IF NOT EXISTS am_performance_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    account_manager TEXT NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    total_revenue DECIMAL(12,2) DEFAULT 0,
    revenue_change_pct DECIMAL(5,2),
    customer_count INTEGER DEFAULT 0,
    avg_revenue_per_customer DECIMAL(12,2) DEFAULT 0,
    quotes_sent INTEGER DEFAULT 0,
    quotes_accepted INTEGER DEFAULT 0,
    quote_conversion_rate DECIMAL(5,2),
    avg_quote_value DECIMAL(12,2),
    avg_response_time_hours DECIMAL(8,2),
    avg_bh_response_time_hours DECIMAL(8,2),
    emails_sent INTEGER DEFAULT 0,
    emails_received INTEGER DEFAULT 0,
    active_customers INTEGER DEFAULT 0,
    churned_customers INTEGER DEFAULT 0,
    new_customers INTEGER DEFAULT 0,
    retention_rate DECIMAL(5,2),
    computed_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(client_id, account_manager, period_start, period_end)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_qb_customers_matched ON qb_customers(matched_company_id);
CREATE INDEX IF NOT EXISTS idx_qb_customers_client ON qb_customers(client_id);
CREATE INDEX IF NOT EXISTS idx_qb_contacts_matched ON qb_contacts(matched_contact_id);
CREATE INDEX IF NOT EXISTS idx_qb_contacts_email ON qb_contacts(email);
CREATE INDEX IF NOT EXISTS idx_qb_quotes_company ON qb_quotes(matched_company_id, date_created DESC);
CREATE INDEX IF NOT EXISTS idx_qb_quotes_status ON qb_quotes(client_id, date_accepted);
CREATE INDEX IF NOT EXISTS idx_qb_jobs_company ON qb_jobs(matched_company_id, accepted_date DESC);
CREATE INDEX IF NOT EXISTS idx_qb_sales_company ON qb_sales_line_items(matched_company_id, inv_date DESC);
CREATE INDEX IF NOT EXISTS idx_qb_sales_am ON qb_sales_line_items(job_am_name, inv_date DESC);
CREATE INDEX IF NOT EXISTS idx_rel_cache_client ON relationship_context_cache(client_id, computed_at DESC);
CREATE INDEX IF NOT EXISTS idx_strategic_digest_client ON ai_strategic_digests(client_id, digest_date DESC);
CREATE INDEX IF NOT EXISTS idx_am_perf_client ON am_performance_snapshots(client_id, period_start DESC);
