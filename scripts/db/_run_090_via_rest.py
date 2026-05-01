"""
Throwaway runner for 090_fix_embedding_rpc_timeout.sql
Adds SET statement_timeout = '30s' to all batch embedding RPCs.
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

with open(os.path.join(os.path.dirname(__file__), '..', 'migrations', '090_fix_embedding_rpc_timeout.sql'), 'r', encoding='utf-8') as f:
    raw_sql = f.read()

stripped = re.sub(r'^\s*BEGIN\s*;\s*$', '', raw_sql, flags=re.MULTILINE | re.IGNORECASE)
stripped = re.sub(r'^\s*COMMIT\s*;\s*$', '', stripped, flags=re.MULTILINE | re.IGNORECASE)

print("[1/3] Applying migration 090...")
try:
    sb.rpc("exec_sql", {"query": stripped}).execute()
    print("  [ok] All 3 embedding RPCs updated with 30s timeout")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print("[2/3] Schema reload...")
sb.rpc("exec_sql", {"query": "NOTIFY pgrst, 'reload schema';"}).execute()
time.sleep(3)

print("[3/3] Quick verification...")
try:
    resp = sb.rpc("batch_update_embeddings_emails", {
        "p_ids": [],
        "p_embeddings": [],
    }).execute()
    print(f"  [ok] batch_update_embeddings_emails callable (returned: {resp.data})")
except Exception as e:
    print(f"  [WARN] Verification failed: {e}")

print("\nDone. Delete this file after verification.")
