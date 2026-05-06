-- Migration 102: Enable RLS on all public-schema tables
--
-- Supabase security alert: tables without RLS are readable/writable
-- by anyone with the project URL + anon key. This is critical because
-- several tables contain API keys, OAuth tokens, and business data.
--
-- SAFE because:
--   - Backend uses service_role key → bypasses RLS entirely
--   - Frontend uses Supabase ONLY for auth (zero direct table access)
--   - All data queries go through backend API → service_role key
--   - No RLS policies needed: no table is accessed via anon/authenticated roles
--
-- Tables that already have RLS enabled (no-op, included for completeness):
--   emails, mailboxes, user_profiles, user_client_assignments,
--   client_manager_assignments, extraction_jobs, email_response_metrics,
--   internal_domains, thread_status, unified_email_rules, audit_log

-- ====================================================================
-- CRITICAL: Tables containing secrets / tokens / API keys
-- ====================================================================

ALTER TABLE IF EXISTS clients ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS system_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS qb_sync_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS user_integrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS account_managers ENABLE ROW LEVEL SECURITY;

-- ====================================================================
-- Business data tables
-- ====================================================================

ALTER TABLE IF EXISTS customer_companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS customer_contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS customer_recognition_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS email_categories ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS email_enrichment ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS email_contact_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS folders ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS processing_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS job_errors ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS downloaded_files ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS free_email_providers ENABLE ROW LEVEL SECURITY;

-- ====================================================================
-- QuickBase sync tables
-- ====================================================================

ALTER TABLE IF EXISTS qb_customers ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS qb_contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS qb_quotes ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS qb_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS qb_operations ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS qb_sales_line_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS qb_unique_emails ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS qb_field_definitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS qb_sync_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS qb_match_candidates ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS qb_job_status_log ENABLE ROW LEVEL SECURITY;

-- ====================================================================
-- AI / intelligence tables
-- ====================================================================

ALTER TABLE IF EXISTS ai_email_intelligence ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS ai_daily_digests ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS ai_business_entities ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS ai_relationship_summaries ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS ai_usage_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS ai_prompt_config ENABLE ROW LEVEL SECURITY;

-- ====================================================================
-- Thread / event / notification tables
-- ====================================================================

ALTER TABLE IF EXISTS thread_qb_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS thread_merges ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS thread_status_override_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS events ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS notifications ENABLE ROW LEVEL SECURITY;

-- ====================================================================
-- Analytics / recommendation tables
-- ====================================================================

ALTER TABLE IF EXISTS metric_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS customer_recommendations ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS customer_intelligence_cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS client_taxonomy_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS product_affinities ENABLE ROW LEVEL SECURITY;

-- ====================================================================
-- Misc / config tables
-- ====================================================================

ALTER TABLE IF EXISTS app_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS gmail_filters ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS outlook_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS pending_invites ENABLE ROW LEVEL SECURITY;
