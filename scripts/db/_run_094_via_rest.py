"""
Throwaway migration runner for 094_thread_status_qb_link_count.sql
Adds qb_link_count column to thread_status, backfills from thread_qb_links.
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

with open(os.path.join(os.path.dirname(__file__), '..', 'migrations', '094_thread_status_qb_link_count.sql'), 'r', encoding='utf-8') as f:
    raw_sql = f.read()

stripped = re.sub(r'^\s*BEGIN\s*;\s*$', '', raw_sql, flags=re.MULTILINE | re.IGNORECASE)
stripped = re.sub(r'^\s*COMMIT\s*;\s*$', '', stripped, flags=re.MULTILINE | re.IGNORECASE)

print("[1/3] Applying migration 094...")
try:
    sb.rpc("exec_sql", {"query": stripped}).execute()
    print("  [ok] Migration applied")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print("[2/3] Schema reload...")
sb.rpc("exec_sql", {"query": "NOTIFY pgrst, 'reload schema';"}).execute()
time.sleep(5)

print("[3/3] Verifying qb_link_count column...")
try:
    result = sb.table("thread_status").select("canonical_thread_id, qb_link_count").gt("qb_link_count", 0).limit(10).execute()
    count = len(result.data) if result.data else 0
    print(f"  [ok] {count} threads with qb_link_count > 0 (showing up to 10)")
    for row in (result.data or []):
        print(f"    thread={row['canonical_thread_id'][:16]}... count={row['qb_link_count']}")
except Exception as e:
    print(f"  [FAIL] {e}")

print("\n[ok] Migration 094 complete. Delete this file after verification.")
