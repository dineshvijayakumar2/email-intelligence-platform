"""Verify migration 090 took effect — check statement_timeout on embedding RPCs."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
from dotenv import load_dotenv
from supabase import create_client

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
load_dotenv(env_path)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

# Create a temp query function that returns JSON
create_fn = """
CREATE OR REPLACE FUNCTION _temp_query_090()
RETURNS json LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE result json;
BEGIN
    SELECT json_agg(row_to_json(t))
    INTO result
    FROM (
        SELECT p.proname, p.proconfig
        FROM pg_proc p
        JOIN pg_namespace n ON p.pronamespace = n.oid
        WHERE p.proname LIKE 'batch_update_embeddings%'
        AND n.nspname = 'public'
    ) t;
    RETURN result;
END; $$;
GRANT EXECUTE ON FUNCTION _temp_query_090() TO authenticated;
"""

print("[1] Creating temp query function...")
try:
    sb.rpc("exec_sql", {"query": create_fn}).execute()
    print("  ok")
except Exception as e:
    print(f"  {e}")
    sys.exit(1)

import time
time.sleep(2)
sb.rpc("exec_sql", {"query": "NOTIFY pgrst, 'reload schema';"}).execute()
time.sleep(3)

print("[2] Querying function configs...")
try:
    resp = sb.rpc("_temp_query_090", {}).execute()
    print(f"  Result: {resp.data}")
except Exception as e:
    print(f"  {e}")

print("[3] Testing actual timeout behavior...")
import time as _time
# Call with empty arrays — should complete instantly
t0 = _time.time()
try:
    resp = sb.rpc("batch_update_embeddings_emails", {
        "p_ids": [],
        "p_embeddings": [],
    }).execute()
    print(f"  Empty call OK in {_time.time()-t0:.2f}s, returned: {resp.data}")
except Exception as e:
    print(f"  Empty call failed: {e}")

print("[4] Checking connection-level timeout...")
# Create another temp fn to check the runtime timeout
check_fn = """
CREATE OR REPLACE FUNCTION _temp_check_timeout()
RETURNS json LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE result json;
BEGIN
    SELECT json_build_object(
        'statement_timeout', current_setting('statement_timeout'),
        'lock_timeout', current_setting('lock_timeout')
    ) INTO result;
    RETURN result;
END; $$;
GRANT EXECUTE ON FUNCTION _temp_check_timeout() TO authenticated;
"""
try:
    sb.rpc("exec_sql", {"query": check_fn}).execute()
    _time.sleep(2)
    sb.rpc("exec_sql", {"query": "NOTIFY pgrst, 'reload schema';"}).execute()
    _time.sleep(3)
    resp = sb.rpc("_temp_check_timeout", {}).execute()
    print(f"  Connection settings: {resp.data}")
except Exception as e:
    print(f"  {e}")
finally:
    try:
        sb.rpc("exec_sql", {"query": "DROP FUNCTION IF EXISTS _temp_check_timeout(); DROP FUNCTION IF EXISTS _temp_query_090();"}).execute()
        print("  Cleanup done")
    except:
        pass
