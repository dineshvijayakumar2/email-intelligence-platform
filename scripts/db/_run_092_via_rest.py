"""
Throwaway runner for 092_fix_interrupted_completed_at.sql
Removes completed_at from reconcile_stuck_jobs interrupted transition.
Also cleans up existing bad data.
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

with open(os.path.join(os.path.dirname(__file__), '..', 'migrations', '092_fix_interrupted_completed_at.sql'), 'r', encoding='utf-8') as f:
    raw_sql = f.read()

stripped = re.sub(r'^\s*BEGIN\s*;\s*$', '', raw_sql, flags=re.MULTILINE | re.IGNORECASE)
stripped = re.sub(r'^\s*COMMIT\s*;\s*$', '', stripped, flags=re.MULTILINE | re.IGNORECASE)

print("[1/4] Applying migration 092...")
try:
    sb.rpc("exec_sql", {"query": stripped}).execute()
    print("  [ok] reconcile_stuck_jobs updated")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print("[2/4] Schema reload...")
sb.rpc("exec_sql", {"query": "NOTIFY pgrst, 'reload schema';"}).execute()
time.sleep(3)

print("[3/4] Cleaning up existing bad data...")
try:
    cleanup = """
    UPDATE processing_jobs
    SET completed_at = NULL
    WHERE status = 'interrupted'
      AND completed_at IS NOT NULL;
    """
    sb.rpc("exec_sql", {"query": cleanup}).execute()
    print("  [ok] Cleared completed_at on interrupted jobs")
except Exception as e:
    print(f"  [WARN] Cleanup failed: {e}")

print("[4/4] Verifying...")
try:
    resp = (
        sb.table("processing_jobs")
        .select("id", count="exact")
        .eq("status", "interrupted")
        .not_.is_("completed_at", "null")
        .execute()
    )
    count = resp.count or 0
    if count == 0:
        print(f"  [ok] No interrupted jobs have completed_at set")
    else:
        print(f"  [WARN] {count} interrupted jobs still have completed_at")
except Exception as e:
    print(f"  [WARN] Verification failed: {e}")

print("\nDone. Delete this file after verification.")
