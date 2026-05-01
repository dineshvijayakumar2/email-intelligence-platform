"""Fix heartbeat_job RPC type mismatch. Delete after verified."""
import os, sys, time, uuid
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
from dotenv import load_dotenv
from supabase import create_client

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
load_dotenv(env_path)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

fix_sql = """
CREATE OR REPLACE FUNCTION heartbeat_job(
    p_job_id UUID,
    p_worker_id TEXT
) RETURNS BOOLEAN
LANGUAGE plpgsql
AS $fn$
DECLARE
    v_count INT;
BEGIN
    UPDATE processing_jobs
    SET last_heartbeat_at = NOW(),
        lease_expires_at = NOW() + INTERVAL '5 minutes'
    WHERE id = p_job_id
      AND worker_id = p_worker_id
      AND status = 'running';
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count > 0;
END;
$fn$;
"""

print("Fixing heartbeat_job RPC...")
sb.rpc("exec_sql", {"query": fix_sql}).execute()
sb.rpc("exec_sql", {"query": "NOTIFY pgrst, 'reload schema';"}).execute()
time.sleep(3)

resp = sb.rpc("heartbeat_job", {"p_job_id": str(uuid.uuid4()), "p_worker_id": "test"}).execute()
print(f"heartbeat_job returned: {resp.data}")
print("[ok] Fix applied")
