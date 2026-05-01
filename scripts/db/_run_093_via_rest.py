"""
Throwaway migration runner for 093_contact_deal_activity.sql
Creates the contact_deal_activity view aggregating thread_qb_links per contact.
"""
import os, sys, time, re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
from dotenv import load_dotenv
from supabase import create_client

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
load_dotenv(env_path)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

with open(os.path.join(os.path.dirname(__file__), '..', 'migrations', '093_contact_deal_activity.sql'), 'r', encoding='utf-8') as f:
    raw_sql = f.read()

stripped = re.sub(r'^\s*BEGIN\s*;\s*$', '', raw_sql, flags=re.MULTILINE | re.IGNORECASE)
stripped = re.sub(r'^\s*COMMIT\s*;\s*$', '', stripped, flags=re.MULTILINE | re.IGNORECASE)

print("[1/4] Applying migration 093...")
try:
    try:
        sb.rpc("exec_sql_extended", {"p_query": stripped, "p_timeout_s": 120}).execute()
    except Exception:
        sb.rpc("exec_sql", {"query": stripped}).execute()
    print("  [ok] Migration applied")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print("[2/4] Schema reload...")
sb.rpc("exec_sql", {"query": "NOTIFY pgrst, 'reload schema';"}).execute()
time.sleep(5)

print("[3/4] Verifying view is accessible...")
try:
    result = sb.table("contact_deal_activity").select("*").limit(3).execute()
    rows = result.data or []
    print(f"  [ok] contact_deal_activity: {len(rows)} sample row(s)")
    for row in rows:
        print(f"    contact_id={row.get('contact_id','?')[:8]}... "
              f"total_threads={row.get('total_threads',0)} "
              f"linked_threads={row.get('linked_threads',0)} "
              f"linked_quotes={row.get('linked_quotes',0)} "
              f"open_quotes={row.get('open_quotes',0)} "
              f"converted_quotes={row.get('converted_quotes',0)} "
              f"linked_jobs={row.get('linked_jobs',0)}")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print("[4/4] Checking column presence...")
expected_cols = [
    "contact_id", "client_id", "total_threads", "linked_threads",
    "linked_quotes", "converted_quotes", "open_quotes",
    "open_pipeline_value", "converted_value",
    "linked_jobs", "linked_job_revenue", "linked_margin",
]
if rows:
    missing = [c for c in expected_cols if c not in rows[0]]
    if missing:
        print(f"  [WARN] Missing columns: {missing}")
    else:
        print(f"  [ok] All {len(expected_cols)} expected columns present")
else:
    print("  [skip] No data to verify columns — view may be empty if no thread_qb_links exist")

print("\n=== Migration 093 complete ===")
