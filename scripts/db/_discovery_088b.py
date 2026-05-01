"""
Phase 1 Discovery (part 2) — fill in missing schemas.
Creates a persistent discovery function, reloads schema, then queries.
"""
import os, sys, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
from dotenv import load_dotenv
from supabase import create_client

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
load_dotenv(env_path)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

# Step 1: Create a persistent discovery RPC that takes the SQL as a parameter
create_fn = """
CREATE OR REPLACE FUNCTION discovery_query(p_sql text)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE result jsonb;
BEGIN
    EXECUTE format(
        'SELECT coalesce(jsonb_agg(row_to_json(t)), ''[]''::jsonb) FROM (%s) t',
        p_sql
    ) INTO result;
    RETURN result;
END;
$$;
"""
sb.rpc("exec_sql", {"query": create_fn}).execute()
sb.rpc("exec_sql", {"query": "NOTIFY pgrst, 'reload schema';"}).execute()
print("Created discovery_query function, waiting for schema reload...")
time.sleep(4)

def query(sql, label=""):
    try:
        resp = sb.rpc("discovery_query", {"p_sql": sql}).execute()
        if label:
            print(f"\n=== {label} ===")
        data = resp.data
        if data and isinstance(data, list):
            for row in data:
                print(json.dumps(row, default=str))
        elif data:
            print(json.dumps(data, default=str, indent=2))
        else:
            print("(no rows)")
        return data
    except Exception as e:
        print(f"ERROR [{label}]: {e}")
        return None

# ─── MISSING FROM FIRST RUN ───

query("""
    SELECT column_name, data_type, is_nullable
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'customer_contacts'
    ORDER BY ordinal_position
""", "SCHEMA: customer_contacts")

query("""
    SELECT column_name, data_type, is_nullable
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'customer_companies'
    ORDER BY ordinal_position
""", "SCHEMA: customer_companies")

query("""
    SELECT column_name, data_type, is_nullable
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'email_response_metrics'
    ORDER BY ordinal_position
""", "SCHEMA: email_response_metrics")

# Client ID distribution for contacts
query("""
    SELECT client_id, count(*) as cnt
    FROM customer_contacts
    GROUP BY client_id
    ORDER BY cnt DESC LIMIT 10
""", "CLIENT_ID DISTRIBUTION (contacts)")

# RLS status
query("""
    SELECT schemaname, tablename, rowsecurity
    FROM pg_tables
    WHERE schemaname = 'public'
      AND tablename IN ('customer_contacts', 'customer_companies', 'qb_quotes',
                         'qb_jobs', 'email_contact_links', 'email_response_metrics', 'emails')
    ORDER BY tablename
""", "RLS STATUS")

# Sample email_response_metrics
query("""
    SELECT * FROM email_response_metrics LIMIT 3
""", "SAMPLE: email_response_metrics")

# Sample customer_contacts - check QB fields
query("""
    SELECT id, email_address, full_name, client_id, customer_company_id, job_title
    FROM customer_contacts LIMIT 3
""", "SAMPLE: customer_contacts (basic)")

# Check which QB-related columns exist on customer_contacts
query("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'customer_contacts'
      AND column_name LIKE 'qb%'
    ORDER BY column_name
""", "CUSTOMER_CONTACTS QB COLUMNS")

# Check customer_companies QB columns
query("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'customer_companies'
      AND (column_name LIKE 'qb%' OR column_name IN ('industry', 'customer_type', 'company_name'))
    ORDER BY column_name
""", "CUSTOMER_COMPANIES QB/KEY COLUMNS")

# Sample companies with tier
query("""
    SELECT id, company_name, client_id, qb_tier, qb_customer_type, industry
    FROM customer_companies
    WHERE qb_tier IS NOT NULL
    LIMIT 5
""", "SAMPLE COMPANIES WITH QB_TIER")

# Check if qb_quotes has a status column with different name
query("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'qb_quotes'
      AND (column_name LIKE '%status%' OR column_name LIKE '%accept%' OR column_name = 'has_job')
    ORDER BY column_name
""", "QB_QUOTES STATUS-RELATED COLUMNS")

# Join test: contacts to quotes via email_address
query("""
    SELECT cc.email_address, qq.contact_email, qq.quote_no, qq.sell_ex_tax
    FROM customer_contacts cc
    JOIN qb_quotes qq ON lower(cc.email_address) = lower(qq.contact_email)
    LIMIT 5
""", "JOIN TEST: contacts -> qb_quotes via email")

# Check seniority / is_primary on contacts
query("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'customer_contacts'
      AND column_name IN ('seniority', 'is_primary', 'is_primary_contact', 'contact_seniority')
    ORDER BY column_name
""", "CONTACTS: seniority/is_primary CHECK")

# Check for any existing persona/intelligence views
query("""
    SELECT table_name
    FROM information_schema.views
    WHERE table_schema = 'public'
      AND (table_name LIKE '%persona%' OR table_name LIKE '%intelligence%' OR table_name LIKE '%contact_quote%')
""", "EXISTING PERSONA/INTELLIGENCE VIEWS")

# Cleanup
sb.rpc("exec_sql", {"query": "DROP FUNCTION IF EXISTS discovery_query(text);"}).execute()
print("\n\nDiscovery function cleaned up.")
print("=== DISCOVERY COMPLETE ===")
