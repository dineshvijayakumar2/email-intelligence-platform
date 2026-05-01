"""
Throwaway migration runner for 084_reconcile_stuck_jobs.sql
Apply via exec_sql RPC, verify via REST. Delete after verified.
"""
import os
import sys
import time
import re
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from dotenv import load_dotenv
from supabase import create_client

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
load_dotenv(env_path)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

migration_path = os.path.join(os.path.dirname(__file__), '..', 'migrations', '084_reconcile_stuck_jobs.sql')
with open(migration_path, 'r', encoding='utf-8') as f:
    raw_sql = f.read()

stripped = re.sub(r'^\s*BEGIN\s*;\s*$', '', raw_sql, flags=re.MULTILINE | re.IGNORECASE)
stripped = re.sub(r'^\s*COMMIT\s*;\s*$', '', stripped, flags=re.MULTILINE | re.IGNORECASE)

print("[1/3] Applying migration 084 via exec_sql...")
try:
    sb.rpc("exec_sql", {"query": stripped}).execute()
    print("  [ok] Migration applied")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print("[2/3] Reloading PostgREST schema cache...")
sb.rpc("exec_sql", {"query": "NOTIFY pgrst, 'reload schema';"}).execute()
time.sleep(3)

print("[3/3] Verifying reconcile_stuck_jobs RPC...")
try:
    resp = sb.rpc("reconcile_stuck_jobs", {}).execute()
    print(f"  [ok] reconcile_stuck_jobs RPC exists (returned: {resp.data})")
except Exception as e:
    if "PGRST202" in str(e) or "Could not find" in str(e):
        print(f"  [FAIL] RPC not in schema cache: {e}")
        print("  Retrying after 5s...")
        time.sleep(5)
        sb.rpc("exec_sql", {"query": "NOTIFY pgrst, 'reload schema';"}).execute()
        time.sleep(5)
        try:
            resp = sb.rpc("reconcile_stuck_jobs", {}).execute()
            print(f"  [ok] reconcile_stuck_jobs accessible after retry (returned: {resp.data})")
        except Exception as e2:
            print(f"  [FAIL] Still not accessible: {e2}")
            sys.exit(1)
    else:
        print(f"  [ok] reconcile_stuck_jobs RPC exists (call returned: {e})")

print("\n[ok] Migration 084 applied and verified successfully")
