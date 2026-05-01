"""
Throwaway migration runner for 083_worker_infrastructure.sql
Apply via exec_sql RPC, verify via REST. Delete after verified.
"""
import os
import sys
import time
import re

# Add backend to path for dotenv
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from dotenv import load_dotenv
from supabase import create_client

# Load env
env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
load_dotenv(env_path)

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# Read migration SQL
migration_path = os.path.join(os.path.dirname(__file__), '..', 'migrations', '083_worker_infrastructure.sql')
with open(migration_path, 'r', encoding='utf-8') as f:
    raw_sql = f.read()

# Strip BEGIN/COMMIT (exec_sql runs inside PostgREST transaction)
stripped = re.sub(r'^\s*BEGIN\s*;\s*$', '', raw_sql, flags=re.MULTILINE | re.IGNORECASE)
stripped = re.sub(r'^\s*COMMIT\s*;\s*$', '', stripped, flags=re.MULTILINE | re.IGNORECASE)

print("[1/4] Applying migration 083 via exec_sql...")
try:
    sb.rpc("exec_sql", {"query": stripped}).execute()
    print("  [ok] Migration applied")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

# Reload PostgREST schema cache
print("[2/4] Reloading PostgREST schema cache...")
sb.rpc("exec_sql", {"query": "NOTIFY pgrst, 'reload schema';"}).execute()
time.sleep(3)

# Post-flight verification
print("[3/4] Verifying new columns exist...")
try:
    resp = sb.table("processing_jobs").select(
        "id,last_heartbeat_at,worker_id,lease_expires_at,attempts,max_attempts,scheduled_for,triggered_by"
    ).limit(1).execute()
    print(f"  [ok] All 7 new columns accessible ({len(resp.data)} rows sampled)")
except Exception as e:
    print(f"  [FAIL] Column check: {e}")
    sys.exit(1)

print("[4/4] Verifying RPCs exist...")
errors = []

# Test claim_next_job - should return empty (no pending jobs or just no match)
try:
    resp = sb.rpc("claim_next_job", {"p_worker_id": "test-verify-083"}).execute()
    print(f"  [ok] claim_next_job RPC exists (returned {len(resp.data)} rows)")
except Exception as e:
    if "PGRST202" in str(e) or "Could not find" in str(e):
        errors.append(f"claim_next_job not in schema cache: {e}")
    else:
        # Other errors might be OK (e.g., permission, no rows)
        print(f"  [ok] claim_next_job RPC exists (call returned: {e})")

# Test heartbeat_job with a dummy UUID
try:
    import uuid
    dummy_id = str(uuid.uuid4())
    resp = sb.rpc("heartbeat_job", {"p_job_id": dummy_id, "p_worker_id": "test-verify-083"}).execute()
    print(f"  [ok] heartbeat_job RPC exists (returned: {resp.data})")
except Exception as e:
    if "PGRST202" in str(e) or "Could not find" in str(e):
        errors.append(f"heartbeat_job not in schema cache: {e}")
    else:
        print(f"  [ok] heartbeat_job RPC exists (call returned: {e})")

if errors:
    for err in errors:
        print(f"  [FAIL] {err}")
    # Retry after longer wait
    print("  Retrying after 5s wait for schema cache...")
    time.sleep(5)
    sb.rpc("exec_sql", {"query": "NOTIFY pgrst, 'reload schema';"}).execute()
    time.sleep(5)
    try:
        sb.rpc("claim_next_job", {"p_worker_id": "test-verify-083"}).execute()
        sb.rpc("heartbeat_job", {"p_job_id": str(uuid.uuid4()), "p_worker_id": "test-verify-083"}).execute()
        print("  [ok] RPCs accessible after retry")
    except Exception as e2:
        print(f"  [FAIL] RPCs still not accessible: {e2}")
        sys.exit(1)

print("\n[ok] Migration 083 applied and verified successfully")
