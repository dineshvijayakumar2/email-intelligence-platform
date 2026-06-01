"""
Throwaway runner for migration 110: company_name CITEXT.
Sends each statement separately since exec_sql wraps in implicit transactions.
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

sql_path = os.path.join(os.path.dirname(__file__), '..', 'migrations', '110_company_name_citext.sql')
with open(sql_path, 'r') as f:
    raw = f.read()

cleaned = re.sub(r'--[^\n]*', '', raw)

# Split on semicolons but handle CREATE VIEW bodies containing semicolons in CASE/WHEN
# Strategy: split into logical statements by finding top-level semicolons
stmts = []
current = []
paren_depth = 0
for line in cleaned.split('\n'):
    stripped = line.strip()
    if not stripped:
        current.append(line)
        continue
    paren_depth += line.count('(') - line.count(')')
    if stripped.endswith(';') and paren_depth <= 0:
        current.append(line.rstrip().rstrip(';'))
        stmt = '\n'.join(current).strip()
        if stmt:
            stmts.append(stmt)
        current = []
        paren_depth = 0
    else:
        current.append(line)

# Any leftover
if current:
    stmt = '\n'.join(current).strip().rstrip(';')
    if stmt:
        stmts.append(stmt)

print(f"Found {len(stmts)} statements to execute")
for i, stmt in enumerate(stmts, 1):
    label = stmt[:80].replace('\n', ' ').strip()
    print(f"\n[{i}/{len(stmts)}] {label}...")
    try:
        result = sb.rpc('exec_sql', {'query': stmt}).execute()
        print(f"  [OK]")
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

# Smoke test
CLIENT_ID = "241d7b99-f099-4557-96e5-212c4af10812"
print("\nSmoke test: case-insensitive unique constraint...")
try:
    sb.table('customer_companies').upsert({
        'client_id': CLIENT_ID,
        'company_name': '__CITEXT_TEST_110__',
        'email_domains': [],
    }, on_conflict='client_id,company_name').execute()

    sb.table('customer_companies').upsert({
        'client_id': CLIENT_ID,
        'company_name': '__citext_test_110__',
        'email_domains': [],
    }, on_conflict='client_id,company_name').execute()

    count = sb.table('customer_companies').select('id', count='exact').eq(
        'client_id', CLIENT_ID
    ).ilike('company_name', '%citext_test_110%').limit(0).execute()

    if count.count == 1:
        print(f"  [OK] CITEXT working (count={count.count})")
    else:
        print(f"  [WARN] Expected 1 row, got {count.count}")

    sb.table('customer_companies').delete().eq(
        'client_id', CLIENT_ID
    ).ilike('company_name', '%citext_test_110%').execute()
    print("  [OK] Cleaned up")
except Exception as e:
    print(f"  [FAIL] {e}")
    try:
        sb.table('customer_companies').delete().eq(
            'client_id', CLIENT_ID
        ).ilike('company_name', '%citext_test_110%').execute()
    except Exception:
        pass
    sys.exit(1)

print("\nMigration 110 applied successfully!")
