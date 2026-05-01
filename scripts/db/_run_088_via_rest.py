"""
Throwaway migration runner for 088_contact_persona_views.sql
Creates 5 views (1 materialized) + refresh function for contact persona metrics.
"""
import os, sys, time, re, json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
from dotenv import load_dotenv
from supabase import create_client

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
load_dotenv(env_path)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

with open(os.path.join(os.path.dirname(__file__), '..', 'migrations', '088_contact_persona_views.sql'), 'r', encoding='utf-8') as f:
    raw_sql = f.read()

stripped = re.sub(r'^\s*BEGIN\s*;\s*$', '', raw_sql, flags=re.MULTILINE | re.IGNORECASE)
stripped = re.sub(r'^\s*COMMIT\s*;\s*$', '', stripped, flags=re.MULTILINE | re.IGNORECASE)

print("[1/5] Applying migration 088...")
try:
    # The materialized view creation may take time due to the joins
    # Use exec_sql_extended if available, fall back to exec_sql
    try:
        sb.rpc("exec_sql_extended", {"p_query": stripped, "p_timeout_s": 300}).execute()
    except Exception:
        # Fallback: exec_sql with default timeout (may timeout for large datasets)
        sb.rpc("exec_sql", {"query": stripped}).execute()
    print("  [ok] Migration applied")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print("[2/5] Schema reload...")
sb.rpc("exec_sql", {"query": "NOTIFY pgrst, 'reload schema';"}).execute()
time.sleep(5)

print("[3/5] Verifying views are accessible...")
views = [
    "contact_quote_metrics",
    "contact_email_metrics",
    "contact_persona",
    "company_contact_summary",
    "industry_benchmarks",
]
for view in views:
    try:
        result = sb.table(view).select("*").limit(1).execute()
        row_count = len(result.data) if result.data else 0
        print(f"  [ok] {view} — {row_count} row(s) returned")
    except Exception as e:
        print(f"  [FAIL] {view}: {e}")
        # Retry after another schema reload
        sb.rpc("exec_sql", {"query": "NOTIFY pgrst, 'reload schema';"}).execute()
        time.sleep(5)
        try:
            result = sb.table(view).select("*").limit(1).execute()
            print(f"  [ok] {view} — accessible after retry")
        except Exception as e2:
            print(f"  [FAIL] {view} still not accessible: {e2}")

print("[4/5] Verifying refresh function...")
try:
    sb.rpc("refresh_contact_email_metrics", {}).execute()
    print("  [ok] refresh_contact_email_metrics() executed successfully")
except Exception as e:
    print(f"  [FAIL] refresh function: {e}")

print("[5/5] Sample data from contact_persona...")
try:
    result = sb.table("contact_persona").select(
        "contact_id, name, email, company_name, persona_classification, engagement_score, "
        "quote_count, strike_rate, email_total, email_velocity_30d"
    ).not_.is_("name", "null").limit(5).execute()
    if result.data:
        for row in result.data:
            print(f"  {row.get('name', '?'):30s} | {row.get('persona_classification', '?'):20s} | "
                  f"score={row.get('engagement_score', 0):3d} | "
                  f"quotes={row.get('quote_count', 0):4d} | "
                  f"strike={row.get('strike_rate') or 'N/A':>5s} | "
                  f"emails={row.get('email_total', 0):5d} | "
                  f"vel30d={row.get('email_velocity_30d', 0):3d}")
    else:
        print("  (no rows with non-null names)")
except Exception as e:
    print(f"  [FAIL] Sample query: {e}")

print("\n[ok] Migration 088 complete")
