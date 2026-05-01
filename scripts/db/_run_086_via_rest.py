"""
Throwaway migration runner for 086_thread_qb_links.sql
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

with open(os.path.join(os.path.dirname(__file__), '..', 'migrations', '086_thread_qb_links.sql'), 'r') as f:
    raw_sql = f.read()

stripped = re.sub(r'^\s*BEGIN\s*;\s*$', '', raw_sql, flags=re.MULTILINE | re.IGNORECASE)
stripped = re.sub(r'^\s*COMMIT\s*;\s*$', '', stripped, flags=re.MULTILINE | re.IGNORECASE)

print("[1/3] Applying migration 086...")
try:
    sb.rpc("exec_sql", {"query": stripped}).execute()
    print("  [ok]")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print("[2/3] Schema reload...")
sb.rpc("exec_sql", {"query": "NOTIFY pgrst, 'reload schema';"}).execute()
time.sleep(3)

print("[3/3] Verifying...")
try:
    sb.table("thread_qb_links").select("id").limit(1).execute()
    print("  [ok] thread_qb_links accessible")
except Exception as e:
    print(f"  [FAIL] {e}")
    time.sleep(5)
    sb.rpc("exec_sql", {"query": "NOTIFY pgrst, 'reload schema';"}).execute()
    time.sleep(5)
    sb.table("thread_qb_links").select("id").limit(1).execute()
    print("  [ok] accessible after retry")

try:
    sb.table("ai_email_intelligence").select("extracted_references").limit(1).execute()
    print("  [ok] extracted_references column accessible")
except Exception as e:
    print(f"  [warn] extracted_references: {e}")

print("\n[ok] Migration 086 applied")
