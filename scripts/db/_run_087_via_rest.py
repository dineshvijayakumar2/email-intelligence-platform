"""
Throwaway migration runner for 087_email_pipeline_dedup.sql

NOTE: CREATE INDEX CONCURRENTLY cannot run inside a transaction, so we
strip the CONCURRENTLY keyword when running via exec_sql RPC. The index
is small (only active pipeline rows), so a non-concurrent build is fine.
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

with open(os.path.join(os.path.dirname(__file__), '..', 'migrations', '087_email_pipeline_dedup.sql'), 'r') as f:
    raw_sql = f.read()

# Strip transaction wrappers
stripped = re.sub(r'^\s*BEGIN\s*;\s*$', '', raw_sql, flags=re.MULTILINE | re.IGNORECASE)
stripped = re.sub(r'^\s*COMMIT\s*;\s*$', '', stripped, flags=re.MULTILINE | re.IGNORECASE)
# Strip CONCURRENTLY — cannot use inside exec_sql transaction
stripped = stripped.replace(' CONCURRENTLY ', ' ')

print("[1/3] Applying migration 087...")
try:
    sb.rpc("exec_sql", {"query": stripped}).execute()
    print("  [ok]")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print("[2/3] Schema reload...")
sb.rpc("exec_sql", {"query": "NOTIFY pgrst, 'reload schema';"}).execute()
time.sleep(3)

print("[3/3] Verifying index exists...")
try:
    result = sb.rpc("exec_sql", {"query": """
        SELECT indexname FROM pg_indexes
        WHERE indexname = 'uq_email_pipeline_per_mailbox';
    """}).execute()
    if result.data and len(result.data) > 0:
        print("  [ok] uq_email_pipeline_per_mailbox index exists")
    else:
        print("  [WARN] Index not found in pg_indexes")
except Exception as e:
    print(f"  [FAIL] {e}")
