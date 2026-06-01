"""
Throwaway runner for migration 109: fix candidate unique index.
Delete this file after verification.
"""
import os, sys, re, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
from dotenv import load_dotenv
from supabase import create_client

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
load_dotenv(env_path)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

sql_path = os.path.join(os.path.dirname(__file__), '..', 'migrations', '109_fix_candidate_unique_index.sql')
with open(sql_path, 'r') as f:
    raw = f.read()

cleaned = re.sub(r'--[^\n]*\n', '\n', raw).strip()

# Split into separate statements (DROP then CREATE)
stmts = [s.strip() for s in cleaned.split(';') if s.strip()]

for i, stmt in enumerate(stmts, 1):
    print(f"Applying statement {i}/{len(stmts)}...")
    try:
        result = sb.rpc('exec_sql', {'query': stmt}).execute()
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

# Smoke test: verify the new index exists
CLIENT_ID = "241d7b99-f099-4557-96e5-212c4af10812"
print("\nSmoke test: insert two candidates with same qb_record_id but different sb_company_id...")
try:
    # Clean up any test rows first
    sb.table('qb_match_candidates').delete().eq(
        'client_id', CLIENT_ID
    ).eq('qb_record_id', '__test_109__').execute()

    sb.table('qb_match_candidates').insert([
        {
            'client_id': CLIENT_ID,
            'sb_company_id': '00000000-0000-0000-0000-000000000001',
            'sb_company_name': 'Test Co A',
            'qb_record_id': '__test_109__',
            'qb_customer_id': '__test_109__',
            'qb_name': 'Test QB',
            'match_score': 80,
            'match_method': 'email_multi_match',
        },
        {
            'client_id': CLIENT_ID,
            'sb_company_id': '00000000-0000-0000-0000-000000000002',
            'sb_company_name': 'Test Co B',
            'qb_record_id': '__test_109__',
            'qb_customer_id': '__test_109__',
            'qb_name': 'Test QB',
            'match_score': 75,
            'match_method': 'email_multi_match',
        },
    ]).execute()
    print("  [OK] Two candidates with same qb_record_id inserted successfully")

    # Clean up test rows
    sb.table('qb_match_candidates').delete().eq(
        'client_id', CLIENT_ID
    ).eq('qb_record_id', '__test_109__').execute()
    print("  [OK] Test rows cleaned up")
except Exception as e:
    print(f"  [FAIL] {e}")
    # Clean up on failure too
    try:
        sb.table('qb_match_candidates').delete().eq(
            'client_id', CLIENT_ID
        ).eq('qb_record_id', '__test_109__').execute()
    except Exception:
        pass
    sys.exit(1)

print("\nMigration 109 applied successfully!")
