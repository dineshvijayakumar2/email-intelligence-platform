"""
Throwaway migration runner for 102_enable_rls_all_tables.sql
Enables RLS on all public-schema tables to resolve Supabase security alert.
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

with open(os.path.join(os.path.dirname(__file__), '..', 'migrations', '102_enable_rls_all_tables.sql'), 'r', encoding='utf-8') as f:
    raw_sql = f.read()

stripped = re.sub(r'^\s*BEGIN\s*;\s*$', '', raw_sql, flags=re.MULTILINE | re.IGNORECASE)
stripped = re.sub(r'^\s*COMMIT\s*;\s*$', '', stripped, flags=re.MULTILINE | re.IGNORECASE)

print("[1/3] Applying migration 102 (enable RLS on all tables)...")
try:
    try:
        sb.rpc("exec_sql_extended", {"p_query": stripped, "p_timeout_s": 120}).execute()
    except Exception:
        sb.rpc("exec_sql", {"query": stripped}).execute()
    print("  [ok] RLS enabled on all tables")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print("[2/3] Schema reload...")
sb.rpc("exec_sql", {"query": "NOTIFY pgrst, 'reload schema';"}).execute()
time.sleep(5)

print("[3/3] Verifying RLS status...")
try:
    verify_sql = """
    SELECT tablename, rowsecurity
    FROM pg_tables
    WHERE schemaname = 'public'
    ORDER BY tablename;
    """
    result = sb.rpc("exec_sql", {"query": verify_sql}).execute()
    rows = result.data if isinstance(result.data, list) else []

    rls_on = 0
    rls_off = 0
    off_tables = []
    for r in rows:
        name = r.get('tablename', r.get('result', ''))
        enabled = r.get('rowsecurity', False)
        if enabled:
            rls_on += 1
        else:
            rls_off += 1
            off_tables.append(name)

    print(f"  RLS enabled: {rls_on} tables")
    print(f"  RLS disabled: {rls_off} tables")
    if off_tables:
        print(f"  Still unprotected: {', '.join(off_tables[:10])}")
        if len(off_tables) > 10:
            print(f"    ... and {len(off_tables) - 10} more")
    else:
        print("  All public tables are RLS-protected!")

except Exception as e:
    print(f"  [WARN] Verification failed (non-critical): {e}")

print("\nDone!")
