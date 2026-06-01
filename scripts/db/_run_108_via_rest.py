"""
Throwaway runner for migration 108: match guard + company rename.
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

sql_path = os.path.join(os.path.dirname(__file__), '..', 'migrations', '108_fix_match_guard_and_company_rename.sql')
with open(sql_path, 'r') as f:
    raw = f.read()

# Split into two functions (separated by the second CREATE OR REPLACE)
parts = raw.split('CREATE OR REPLACE FUNCTION batch_propagate_qb_data')
func1 = parts[0]
func2 = 'CREATE OR REPLACE FUNCTION batch_propagate_qb_data' + parts[1]

for label, sql in [("batch_write_qb_matches (guard)", func1), ("batch_propagate_qb_data (rename)", func2)]:
    cleaned = re.sub(r'--[^\n]*\n', '\n', sql).strip()
    if cleaned.endswith(';'):
        cleaned = cleaned[:-1]
    if not cleaned:
        continue
    print(f"Applying: {label}...")
    try:
        result = sb.rpc('exec_sql', {'query': cleaned}).execute()
        print(f"  [OK] {result.data}")
    except Exception as e:
        print(f"  [FAIL] {e}")
        sys.exit(1)

print("\nRefreshing PostgREST schema cache...")
try:
    sb.rpc('exec_sql', {'query': "NOTIFY pgrst, 'reload schema'"}).execute()
    print("  [OK]")
except Exception as e:
    print(f"  [WARN] {e}")

print("Waiting 3s for cache refresh...")
time.sleep(3)

# Smoke test: propagation with qb_customer_name
CLIENT_ID = "241d7b99-f099-4557-96e5-212c4af10812"
print(f"\nSmoke test: propagation RPC accepts qb_customer_name field...")
try:
    resp = sb.rpc('batch_propagate_qb_data', {
        'p_client_id': CLIENT_ID,
        'p_data': [{'company_id': '00000000-0000-0000-0000-000000000000', 'qb_customer_name': 'Test'}],
    }).execute()
    print(f"  [OK] RPC accepts new field (returned: {resp.data})")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print("\nMigration 108 applied successfully!")
