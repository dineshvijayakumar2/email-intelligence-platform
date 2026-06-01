"""
Throwaway runner for migration 112: backfill contacts to matched companies.
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

sql_path = os.path.join(os.path.dirname(__file__), '..', 'migrations', '112_backfill_contacts_to_matched_companies.sql')
with open(sql_path, 'r') as f:
    raw = f.read()

cleaned = re.sub(r'--[^\n]*', '', raw).strip().rstrip(';')

print("Executing migration 112 as single statement...")
print(f"  SQL length: {len(cleaned)} chars")
try:
    result = sb.rpc('exec_sql', {'query': cleaned}).execute()
    print("  [OK] Function created/replaced")
except Exception as e:
    print(f"  [FAIL] {e}")

print("\nReloading schema cache...")
try:
    sb.rpc('exec_sql', {'query': "NOTIFY pgrst, 'reload schema'"}).execute()
    print("  [OK] Schema cache reloaded")
except Exception as e:
    print(f"  [FAIL] {e}")

CLIENT_ID = '241d7b99-f099-4557-96e5-212c4af10812'
print(f"\nRunning backfill for client {CLIENT_ID}...")
try:
    result = sb.rpc('backfill_contacts_to_matched_companies', {'p_client_id': CLIENT_ID}).execute()
    print(f"  [OK] Result: {result.data}")
except Exception as e:
    print(f"  [FAIL] {e}")

print("\nRefreshing company email counts...")
try:
    result = sb.rpc('update_company_email_counts_from_junction', {'p_client_id': CLIENT_ID}).execute()
    print(f"  [OK] Updated {result.data} companies")
except Exception as e:
    print(f"  [FAIL] {e}")
