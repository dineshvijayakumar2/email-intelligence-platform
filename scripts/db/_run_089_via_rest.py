"""
Throwaway runner for 089_fix_classification_health_rpc.sql
Rewrites get_classification_health to use GROUP BY instead of LATERAL (fixes timeout).
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

with open(os.path.join(os.path.dirname(__file__), '..', 'migrations', '089_fix_classification_health_rpc.sql'), 'r', encoding='utf-8') as f:
    raw_sql = f.read()

stripped = re.sub(r'^\s*BEGIN\s*;\s*$', '', raw_sql, flags=re.MULTILINE | re.IGNORECASE)
stripped = re.sub(r'^\s*COMMIT\s*;\s*$', '', stripped, flags=re.MULTILINE | re.IGNORECASE)

print("[1/3] Applying migration 089...")
try:
    sb.rpc("exec_sql", {"query": stripped}).execute()
    print("  [ok] Function replaced")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print("[2/3] Schema reload...")
sb.rpc("exec_sql", {"query": "NOTIFY pgrst, 'reload schema';"}).execute()
time.sleep(3)

print("[3/3] Verifying RPC works...")
try:
    resp = sb.rpc("get_classification_health", {"p_client_id": None}).execute()
    rows = resp.data if resp.data else []
    if isinstance(rows, str):
        import json
        rows = json.loads(rows)
    print(f"  [ok] Returned {len(rows)} mailbox entries")
    for r in rows[:3]:
        print(f"    - {r.get('email_address','?')}: {r.get('total_emails',0)} emails, {r.get('classified',0)} classified")
except Exception as e:
    print(f"  [WARN] Verification failed: {e}")

print("\nDone. Delete this file after verification.")
