"""
Throwaway runner for migration 106: qb_health_revenue_stats RPC.
Delete this file after verification.
"""
import os, sys, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
from dotenv import load_dotenv
from supabase import create_client

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
load_dotenv(env_path)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

sql_path = os.path.join(os.path.dirname(__file__), '..', 'migrations', '106_qb_health_revenue_stats.sql')
with open(sql_path, 'r') as f:
    raw = f.read()

# For CREATE OR REPLACE FUNCTION, send as a single statement (contains $$ delimiters)
# Strip leading comments but keep the function body intact
cleaned = re.sub(r'--[^\n]*\n', '\n', raw).strip()
# Remove trailing semicolon (exec_sql doesn't want it)
if cleaned.endswith(';'):
    cleaned = cleaned[:-1]

print("Executing migration 106: qb_health_revenue_stats RPC...")
try:
    result = sb.rpc('exec_sql', {'query': cleaned}).execute()
    print(f"  [OK] {result.data}")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

# Refresh PostgREST schema cache so the new function is visible
print("\nRefreshing PostgREST schema cache...")
try:
    sb.rpc('exec_sql', {'query': "NOTIFY pgrst, 'reload schema'"}).execute()
    print("  [OK] Schema cache refreshed")
except Exception as e:
    print(f"  [WARN] NOTIFY failed (may need manual refresh): {e}")

import time
print("Waiting 3s for cache refresh...")
time.sleep(3)

# Verify: call the new RPC
CLIENT_ID = "241d7b99-f099-4557-96e5-212c4af10812"
print(f"\nVerifying with client {CLIENT_ID}...")
try:
    resp = sb.rpc('qb_health_revenue_stats', {'p_client_id': CLIENT_ID}).execute()
    import json
    print(json.dumps(resp.data, indent=2))
except Exception as e:
    print(f"  [FAIL] {e}")

print("\nDone! Delete this file after verification.")
