"""
Apply migration 099 (v2) via exec_sql RPC. Delete after verified.

Updates get_ai_link_ref_health() to include per-mailbox link stats
(total_links, quote_links, job_links, threads_linked, link_rate_pct).
"""
import os, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
from dotenv import load_dotenv
from supabase import create_client

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
load_dotenv(env_path)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


def run(label, sql, timeout_s=60):
    t0 = time.time()
    print(f"  {label}...", end="", flush=True)
    try:
        try:
            sb.rpc("exec_sql_extended", {"p_query": sql, "p_timeout_s": timeout_s}).execute()
        except Exception:
            sb.rpc("exec_sql", {"query": sql}).execute()
        print(f" OK ({time.time() - t0:.1f}s)")
    except Exception as e:
        print(f" FAILED: {e}")
        sys.exit(1)


print("[1/2] Create get_ai_link_ref_health RPC (v2 — with per-mailbox link stats)")

run("get_ai_link_ref_health", """
CREATE OR REPLACE FUNCTION get_ai_link_ref_health(
    p_client_id UUID DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
AS $fn$
DECLARE
    mb_data JSONB;
    link_totals JSONB;
BEGIN
    -- Per-mailbox extraction stats + link stats
    SELECT jsonb_agg(row_data)
    INTO mb_data
    FROM (
        SELECT jsonb_build_object(
            'mailbox_id',          m.id,
            'email_address',       COALESCE(m.email_address, m.name, 'Unknown'),
            'total_classified',    COALESCE(cls.total, 0),
            'emails_with_refs',    COALESCE(ref_stats.with_refs, 0),
            'total_refs_found',    COALESCE(ref_stats.total_refs, 0),
            'total_quote_refs',    COALESCE(ref_stats.quote_refs, 0),
            'total_job_refs',      COALESCE(ref_stats.job_refs, 0),
            'total_links',         COALESCE(lk.total_links, 0),
            'quote_links',         COALESCE(lk.quote_links, 0),
            'job_links',           COALESCE(lk.job_links, 0),
            'threads_linked',      COALESCE(lk.threads_linked, 0),
            'link_rate_pct',       CASE WHEN COALESCE(ref_stats.total_refs, 0) > 0
                                        THEN ROUND(COALESCE(lk.total_links, 0)::numeric / ref_stats.total_refs * 100, 1)
                                        ELSE 0 END
        ) AS row_data
        FROM mailboxes m
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS total
            FROM ai_email_intelligence ai
            WHERE ai.mailbox_id = m.id
              AND ai.processing_status = 'completed'
        ) cls ON TRUE
        LEFT JOIN LATERAL (
            SELECT
                COUNT(*) AS with_refs,
                COALESCE(SUM(jsonb_array_length(ai.extracted_references)), 0) AS total_refs,
                COALESCE(SUM(
                    (SELECT COUNT(*) FROM jsonb_array_elements(ai.extracted_references) elem
                     WHERE elem->>'type' = 'quote')
                ), 0) AS quote_refs,
                COALESCE(SUM(
                    (SELECT COUNT(*) FROM jsonb_array_elements(ai.extracted_references) elem
                     WHERE elem->>'type' = 'job')
                ), 0) AS job_refs
            FROM ai_email_intelligence ai
            WHERE ai.mailbox_id = m.id
              AND ai.processing_status = 'completed'
              AND ai.extracted_references IS NOT NULL
              AND jsonb_array_length(ai.extracted_references) > 0
        ) ref_stats ON TRUE
        LEFT JOIN LATERAL (
            SELECT
                COUNT(*)                              AS total_links,
                COUNT(*) FILTER (WHERE tql.link_type = 'quote') AS quote_links,
                COUNT(*) FILTER (WHERE tql.link_type = 'job')   AS job_links,
                COUNT(DISTINCT tql.canonical_thread_id)          AS threads_linked
            FROM thread_qb_links tql
            WHERE tql.source = 'ai'
              AND tql.canonical_thread_id IN (
                  SELECT DISTINCT e.canonical_thread_id::text
                  FROM emails e
                  WHERE e.mailbox_id = m.id
                    AND e.canonical_thread_id IS NOT NULL
              )
              AND (p_client_id IS NULL OR tql.client_id = p_client_id)
        ) lk ON TRUE
        WHERE (p_client_id IS NULL OR m.client_id = p_client_id)
          AND COALESCE(cls.total, 0) > 0
        ORDER BY COALESCE(ref_stats.with_refs, 0) DESC
    ) sub;

    -- Client-wide link totals (from thread_qb_links)
    SELECT jsonb_build_object(
        'threads_linked',  COUNT(DISTINCT canonical_thread_id),
        'total_links',     COUNT(*),
        'quote_links',     COUNT(*) FILTER (WHERE link_type = 'quote'),
        'job_links',       COUNT(*) FILTER (WHERE link_type = 'job'),
        'last_link_at',    MAX(created_at)
    )
    INTO link_totals
    FROM thread_qb_links
    WHERE source = 'ai'
      AND (p_client_id IS NULL OR client_id = p_client_id);

    RETURN jsonb_build_object(
        'mailboxes',    COALESCE(mb_data, '[]'::jsonb),
        'link_totals',  COALESCE(link_totals, '{}'::jsonb)
    );
END;
$fn$;
""", timeout_s=60)

print("\n[2/2] Grant permissions")
run("grant", "GRANT EXECUTE ON FUNCTION get_ai_link_ref_health(UUID) TO anon, authenticated")

# Schema reload
sb.rpc("exec_sql", {"query": "NOTIFY pgrst, 'reload schema';"}).execute()
time.sleep(3)

# Verification
print("\n=== Verification ===")
try:
    resp = sb.rpc("get_ai_link_ref_health", {}).execute()
    raw = resp.data
    if isinstance(raw, list) and len(raw) > 0:
        data = raw[0] if isinstance(raw[0], dict) else raw
    elif isinstance(raw, dict):
        data = raw
    else:
        data = {}

    mailboxes = data.get("mailboxes", [])
    links = data.get("link_totals", {})
    print(f"  [ok] RPC returned {len(mailboxes)} mailbox(es)")
    for mb in mailboxes[:3]:
        addr = mb.get("email_address", "?")
        refs = mb.get("total_refs_found", 0)
        linked = mb.get("total_links", 0)
        threads = mb.get("threads_linked", 0)
        rate = mb.get("link_rate_pct", 0)
        print(f"       {addr}: {refs} refs, {linked} linked, {threads} threads, {rate}%")
    print(f"  [ok] Client totals: {links.get('total_links', 0)} links across {links.get('threads_linked', 0)} threads")
except Exception as e:
    print(f"  [FAIL] RPC call failed: {e}")

print("\n=== Migration 099 v2 complete ===")
