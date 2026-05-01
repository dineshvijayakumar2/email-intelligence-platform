"""
Phase 1 Discovery for migration 088 — Contact Persona Views.
Verifies actual column names, row counts, and multi-tenancy patterns.
Uses Supabase table API for reads since exec_sql returns void.
"""
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
from dotenv import load_dotenv
from supabase import create_client

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
load_dotenv(env_path)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

def exec_sql_json(sql):
    """Create a temp function that returns JSON, execute, then drop."""
    # Create a function that returns the query as JSON
    create_fn = f"""
    CREATE OR REPLACE FUNCTION _temp_discovery()
    RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER AS $$
    DECLARE result jsonb;
    BEGIN
        EXECUTE $q$ SELECT coalesce(jsonb_agg(row_to_json(t)), '[]'::jsonb) FROM ({sql}) t $q$ INTO result;
        RETURN result;
    END;
    $$;
    """
    sb.rpc("exec_sql", {"query": create_fn}).execute()
    resp = sb.rpc("_temp_discovery", {}).execute()
    sb.rpc("exec_sql", {"query": "DROP FUNCTION IF EXISTS _temp_discovery();"}).execute()
    return resp.data

def query(sql, label=""):
    try:
        data = exec_sql_json(sql)
        if label:
            print(f"\n=== {label} ===")
        if data:
            if isinstance(data, list):
                for row in data:
                    print(json.dumps(row, default=str))
            else:
                print(json.dumps(data, default=str, indent=2))
        else:
            print("(no rows)")
        return data
    except Exception as e:
        print(f"ERROR [{label}]: {e}")
        return None

# ─────────────────────────────────────────────────────────
# 1. Full schema for each target table
# ─────────────────────────────────────────────────────────
for table in ['customer_contacts', 'customer_companies', 'qb_quotes', 'qb_jobs',
              'email_response_metrics', 'email_contact_links', 'emails']:
    query(f"""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = '{table}'
        ORDER BY ordinal_position
    """, f"SCHEMA: {table}")

# ─────────────────────────────────────────────────────────
# 2. Row counts
# ─────────────────────────────────────────────────────────
query("""
    SELECT
        (SELECT count(*) FROM customer_contacts) as contacts,
        (SELECT count(*) FROM customer_companies) as companies,
        (SELECT count(*) FROM qb_quotes) as quotes,
        (SELECT count(*) FROM qb_jobs) as jobs,
        (SELECT count(*) FROM email_response_metrics) as response_metrics,
        (SELECT count(*) FROM email_contact_links) as contact_links,
        (SELECT count(*) FROM emails) as emails
""", "ROW COUNTS")

# ─────────────────────────────────────────────────────────
# 3. Client ID distribution
# ─────────────────────────────────────────────────────────
query("""
    SELECT client_id, count(*) as cnt
    FROM customer_contacts
    GROUP BY client_id
    ORDER BY cnt DESC LIMIT 10
""", "CLIENT_ID DISTRIBUTION (contacts)")

query("""
    SELECT client_id, count(*) as cnt
    FROM customer_companies
    GROUP BY client_id
    ORDER BY cnt DESC LIMIT 10
""", "CLIENT_ID DISTRIBUTION (companies)")

# ─────────────────────────────────────────────────────────
# 4. RLS status
# ─────────────────────────────────────────────────────────
query("""
    SELECT schemaname, tablename, rowsecurity
    FROM pg_tables
    WHERE schemaname = 'public'
      AND tablename IN ('customer_contacts', 'customer_companies', 'qb_quotes',
                         'qb_jobs', 'email_contact_links', 'email_response_metrics', 'emails')
    ORDER BY tablename
""", "RLS STATUS")

# ─────────────────────────────────────────────────────────
# 5. Sample qb_quotes (3 rows, all columns)
# ─────────────────────────────────────────────────────────
query("""
    SELECT * FROM qb_quotes LIMIT 3
""", "SAMPLE QB_QUOTES")

# ─────────────────────────────────────────────────────────
# 6. Sample qb_jobs (3 rows, all columns)
# ─────────────────────────────────────────────────────────
query("""
    SELECT * FROM qb_jobs LIMIT 3
""", "SAMPLE QB_JOBS")

# ─────────────────────────────────────────────────────────
# 7. Sample email_contact_links (3 rows)
# ─────────────────────────────────────────────────────────
query("""
    SELECT * FROM email_contact_links LIMIT 3
""", "SAMPLE EMAIL_CONTACT_LINKS")

# ─────────────────────────────────────────────────────────
# 8. Sample email_response_metrics (3 rows)
# ─────────────────────────────────────────────────────────
query("""
    SELECT * FROM email_response_metrics LIMIT 3
""", "SAMPLE EMAIL_RESPONSE_METRICS")

# ─────────────────────────────────────────────────────────
# 9. Check how contacts link to qb_quotes (join field)
# ─────────────────────────────────────────────────────────
query("""
    SELECT cc.email_address, cc.qb_contact_id, qq.contact_email
    FROM customer_contacts cc
    JOIN qb_quotes qq ON lower(cc.email_address) = lower(qq.contact_email)
    LIMIT 5
""", "JOIN TEST: contacts -> qb_quotes via email")

# ─────────────────────────────────────────────────────────
# 10. Check existing views
# ─────────────────────────────────────────────────────────
query("""
    SELECT table_name
    FROM information_schema.views
    WHERE table_schema = 'public'
    ORDER BY table_name
""", "EXISTING VIEWS")

# ─────────────────────────────────────────────────────────
# 11. QB data fill rates on customer_contacts
# ─────────────────────────────────────────────────────────
query("""
    SELECT
        count(*) as total,
        count(qb_contact_id) as has_qb_contact_id,
        count(qb_quote_count) as has_qb_quote_count,
        count(qb_capabilities_used) as has_qb_capabilities
    FROM customer_contacts
""", "QB DATA FILL RATES")

# ─────────────────────────────────────────────────────────
# 12. Customer companies key columns
# ─────────────────────────────────────────────────────────
query("""
    SELECT id, company_name, client_id, qb_tier, customer_type, industry
    FROM customer_companies
    WHERE qb_tier IS NOT NULL
    LIMIT 5
""", "SAMPLE COMPANIES WITH QB_TIER")

print("\n\n=== DISCOVERY COMPLETE ===")
