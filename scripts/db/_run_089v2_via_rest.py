"""
Throwaway migration runner for 089 v2 — fix classification health RPC.
Switches from client_id filter to mailbox_id scope so emails with NULL
client_id are counted correctly.
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

with open(os.path.join(os.path.dirname(__file__), '..', 'migrations', '089_fix_classification_health_rpc.sql'), 'r', encoding='utf-8') as f:
    raw_sql = f.read()

stripped = re.sub(r'^\s*BEGIN\s*;\s*$', '', raw_sql, flags=re.MULTILINE | re.IGNORECASE)
stripped = re.sub(r'^\s*COMMIT\s*;\s*$', '', stripped, flags=re.MULTILINE | re.IGNORECASE)

print("[1/3] Applying migration 089 v2 (classification health RPC)...")
try:
    try:
        sb.rpc("exec_sql_extended", {"p_query": stripped, "p_timeout_s": 120}).execute()
    except Exception:
        sb.rpc("exec_sql", {"query": stripped}).execute()
    print("  [ok] RPC replaced")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print("[2/3] Schema reload...")
sb.rpc("exec_sql", {"query": "NOTIFY pgrst, 'reload schema';"}).execute()
time.sleep(5)

print("[3/3] Verifying counts...")
try:
    result = sb.rpc("get_classification_health", {"p_client_id": None}).execute()
    rows = result.data or []
    print(f"  {len(rows)} mailboxes:")
    for r in rows:
        addr = r.get('email_address', '?')[:30]
        total = r.get('total_emails', 0)
        classified = r.get('classified', 0)
        pending = r.get('pending', 0)
        failed = r.get('failed', 0)
        pct = (classified / total * 100) if total else 0
        print(f"    {addr:30s}  total={total:>7,d}  classified={classified:>7,d}  "
              f"pending={pending:>6,d}  failed={failed:>5,d}  coverage={pct:.1f}%")
except Exception as e:
    print(f"  [FAIL] {e}")

print("\nDone!")
