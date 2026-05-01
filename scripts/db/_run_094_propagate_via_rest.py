"""
Throwaway migration runner for 094_propagate_qb_from_company.sql
Re-applies the batch_propagate_qb_data_to_contacts RPC with updated Pass 3
guards (excludes internal, shared, automated, mailing_list contacts).
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

with open(os.path.join(os.path.dirname(__file__), '..', 'migrations', '094_propagate_qb_from_company.sql'), 'r', encoding='utf-8') as f:
    raw_sql = f.read()

stripped = re.sub(r'^\s*BEGIN\s*;\s*$', '', raw_sql, flags=re.MULTILINE | re.IGNORECASE)
stripped = re.sub(r'^\s*COMMIT\s*;\s*$', '', stripped, flags=re.MULTILINE | re.IGNORECASE)

print("[1/3] Re-applying migration 094 (CREATE OR REPLACE with Pass 3 guards)...")
try:
    try:
        sb.rpc("exec_sql_extended", {"p_query": stripped, "p_timeout_s": 120}).execute()
    except Exception:
        sb.rpc("exec_sql", {"query": stripped}).execute()
    print("  [ok] RPC replaced")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print("[2/3] Schema reload...")
sb.rpc("exec_sql", {"query": "NOTIFY pgrst, 'reload schema';"}).execute()
time.sleep(3)

print("[3/3] Verifying RPC exists and comment updated...")
try:
    result = sb.rpc("exec_sql", {"query": """
        SELECT obj_description(oid, 'pg_proc') AS comment
        FROM pg_proc
        WHERE proname = 'batch_propagate_qb_data_to_contacts';
    """}).execute()
    comment = (result.data or [{}])[0].get("comment", "")
    if "contact-type guards" in comment:
        print(f"  [ok] RPC comment confirms updated version")
    else:
        print(f"  [WARN] Comment doesn't mention guards: {comment[:100]}")
except Exception as e:
    print(f"  [WARN] Could not verify comment: {e}")

print("\n=== Migration 094 (propagate) re-apply complete ===")
