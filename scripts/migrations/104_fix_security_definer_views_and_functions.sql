-- ============================================================================
-- Migration 104: Fix SECURITY DEFINER issues flagged by Supabase Advisor
-- ============================================================================
-- Two categories:
--   A) Views defaulting to security_definer — set security_invoker = on
--      so they run as the calling user and respect RLS.
--   B) Functions declared SECURITY DEFINER without SET search_path — add it
--      to prevent search_path hijacking.
-- ============================================================================

-- ═══════════════════════════════════════════════════════════════════════════
-- A) VIEWS — enable security_invoker
-- ═══════════════════════════════════════════════════════════════════════════

ALTER VIEW public.folder_stats              SET (security_invoker = on);
ALTER VIEW public.daily_email_volume        SET (security_invoker = on);
ALTER VIEW public.top_correspondents        SET (security_invoker = on);
ALTER VIEW public.thread_stats              SET (security_invoker = on);
ALTER VIEW public.customer_engagement_summary SET (security_invoker = on);
ALTER VIEW public.customer_industry_segments SET (security_invoker = on);
ALTER VIEW public.contact_quote_metrics     SET (security_invoker = on);
ALTER VIEW public.contact_persona           SET (security_invoker = on);
ALTER VIEW public.company_contact_summary   SET (security_invoker = on);
ALTER VIEW public.industry_benchmarks       SET (security_invoker = on);
ALTER VIEW public.contact_deal_activity     SET (security_invoker = on);

-- ═══════════════════════════════════════════════════════════════════════════
-- B) FUNCTIONS — add SET search_path = public
-- ═══════════════════════════════════════════════════════════════════════════

-- Auth / RBAC helpers (010, 012, 014)
ALTER FUNCTION public.get_user_accessible_mailboxes(UUID) SET search_path = public;
ALTER FUNCTION public.user_has_role(UUID, TEXT)            SET search_path = public;

-- DB performance RPCs (067)
ALTER FUNCTION public.get_db_slow_queries(INTEGER) SET search_path = public;
ALTER FUNCTION public.get_db_table_stats()         SET search_path = public;
ALTER FUNCTION public.get_db_index_stats()         SET search_path = public;
ALTER FUNCTION public.get_db_cache_stats()         SET search_path = public;
ALTER FUNCTION public.reset_db_stats()             SET search_path = public;

-- DDL / bulk ops (071, 072)
ALTER FUNCTION public.exec_sql(TEXT)                   SET search_path = public;
ALTER FUNCTION public.exec_sql_extended(TEXT, INTEGER)  SET search_path = public;

-- Materialized view refresh (088)
ALTER FUNCTION public.refresh_contact_email_metrics()   SET search_path = public;
