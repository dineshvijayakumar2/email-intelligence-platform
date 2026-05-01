"""
Throwaway runner for 091_fix_company_count_refresh_rpc.sql
Rewrites company count refresh from per-company loop to bulk CTE.
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

with open(os.path.join(os.path.dirname(__file__), '..', 'migrations', '091_fix_company_count_refresh_rpc.sql'), 'r', encoding='utf-8') as f:
    raw_sql = f.read()

stripped = re.sub(r'^\s*BEGIN\s*;\s*$', '', raw_sql, flags=re.MULTILINE | re.IGNORECASE)
stripped = re.sub(r'^\s*COMMIT\s*;\s*$', '', stripped, flags=re.MULTILINE | re.IGNORECASE)

print("[1/3] Applying migration 091...")
try:
    sb.rpc("exec_sql", {"query": stripped}).execute()
    print("  [ok] Both count refresh RPCs updated")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print("[2/3] Schema reload...")
sb.rpc("exec_sql", {"query": "NOTIFY pgrst, 'reload schema';"}).execute()
time.sleep(3)

print("[3/3] Verifying company count refresh...")
try:
    t0 = time.time()
    resp = sb.rpc("update_company_email_counts_from_junction", {
        "p_client_id": "241d7b99-f099-4557-96e5-212c4af10812",
    }).execute()
    elapsed = round(time.time() - t0, 2)
    print(f"  [ok] Updated {resp.data} companies in {elapsed}s")
except Exception as e:
    print(f"  [WARN] Verification failed: {e}")

print("\nDone. Delete this file after verification.")
