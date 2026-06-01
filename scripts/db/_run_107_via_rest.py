"""
Throwaway runner for migration 107: qb_cleanup_dashboard_stats RPC.
Delete this file after verification.
"""
import os, sys, re, time, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
from dotenv import load_dotenv
from supabase import create_client

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
load_dotenv(env_path)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

sql_path = os.path.join(os.path.dirname(__file__), '..', 'migrations', '107_qb_cleanup_dashboard_stats.sql')
with open(sql_path, 'r') as f:
    raw = f.read()

# Strip SQL comments but keep $$ function body intact
cleaned = re.sub(r'--[^\n]*\n', '\n', raw).strip()
if cleaned.endswith(';'):
    cleaned = cleaned[:-1]

print("Executing migration 107: qb_cleanup_dashboard_stats RPC...")
try:
    result = sb.rpc('exec_sql', {'query': cleaned}).execute()
    print(f"  [OK] {result.data}")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print("\nRefreshing PostgREST schema cache...")
try:
    sb.rpc('exec_sql', {'query': "NOTIFY pgrst, 'reload schema'"}).execute()
    print("  [OK] Schema cache refreshed")
except Exception as e:
    print(f"  [WARN] NOTIFY failed: {e}")

print("Waiting 3s for cache refresh...")
time.sleep(3)

CLIENT_ID = "241d7b99-f099-4557-96e5-212c4af10812"
print(f"\nSmoke test with client {CLIENT_ID}...")
try:
    resp = sb.rpc('qb_cleanup_dashboard_stats', {'p_client_id': CLIENT_ID}).execute()
    print(json.dumps(resp.data, indent=2, default=str))
    print("\nMigration 107 applied successfully!")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print("\nDone! Delete this file after verification.")
