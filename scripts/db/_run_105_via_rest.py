"""
Throwaway runner for migration 105: cleanup name-based QB matches.
Execute each statement independently via exec_sql RPC.
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

sql_path = os.path.join(os.path.dirname(__file__), '..', 'migrations', '105_cleanup_name_based_qb_matches.sql')
with open(sql_path, 'r') as f:
    raw = f.read()

# Split into individual statements, strip comments
stmts = []
for s in raw.split(';'):
    cleaned = re.sub(r'--[^\n]*', '', s).strip()
    if cleaned:
        stmts.append(cleaned)

print(f"Found {len(stmts)} statements to execute\n")

for i, stmt in enumerate(stmts, 1):
    preview = stmt[:80].replace('\n', ' ')
    print(f"[{i}/{len(stmts)}] {preview}...")
    try:
        result = sb.rpc('exec_sql', {'query': stmt}).execute()
        print(f"  [OK] {result.data}")
    except Exception as e:
        print(f"  [FAIL] {e}")

print("\nDone! Verify with:")
print("  SELECT COUNT(*) FROM qb_customers WHERE matched_company_id IS NOT NULL;")
print("  SELECT COUNT(*) FROM qb_operations WHERE matched_company_id IS NOT NULL;")
print("  SELECT COUNT(*) FROM customer_companies WHERE qb_match_method IS NOT NULL;")
