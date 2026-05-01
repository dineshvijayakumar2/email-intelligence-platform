"""
Throwaway migration runner for 085_events_notifications.sql
Apply via exec_sql RPC, verify via REST. Delete after verified.
"""
import os
import sys
import time
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from dotenv import load_dotenv
from supabase import create_client

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
load_dotenv(env_path)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

migration_path = os.path.join(os.path.dirname(__file__), '..', 'migrations', '085_events_notifications.sql')
with open(migration_path, 'r', encoding='utf-8') as f:
    raw_sql = f.read()

stripped = re.sub(r'^\s*BEGIN\s*;\s*$', '', raw_sql, flags=re.MULTILINE | re.IGNORECASE)
stripped = re.sub(r'^\s*COMMIT\s*;\s*$', '', stripped, flags=re.MULTILINE | re.IGNORECASE)

print("[1/3] Applying migration 085 via exec_sql...")
try:
    sb.rpc("exec_sql", {"query": stripped}).execute()
    print("  [ok] Migration applied")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print("[2/3] Reloading PostgREST schema cache...")
sb.rpc("exec_sql", {"query": "NOTIFY pgrst, 'reload schema';"}).execute()
time.sleep(3)

print("[3/3] Verifying tables...")
errors = []
for table in ["events", "notifications"]:
    try:
        resp = sb.table(table).select("id").limit(1).execute()
        print(f"  [ok] {table} table accessible ({len(resp.data)} rows)")
    except Exception as e:
        errors.append(f"{table}: {e}")
        print(f"  [FAIL] {table}: {e}")

if errors:
    print("  Retrying after 5s...")
    time.sleep(5)
    sb.rpc("exec_sql", {"query": "NOTIFY pgrst, 'reload schema';"}).execute()
    time.sleep(5)
    for table in ["events", "notifications"]:
        try:
            resp = sb.table(table).select("id").limit(1).execute()
            print(f"  [ok] {table} accessible after retry")
        except Exception as e2:
            print(f"  [FAIL] {table} still not accessible: {e2}")
            sys.exit(1)

print("\n[ok] Migration 085 applied and verified successfully")
