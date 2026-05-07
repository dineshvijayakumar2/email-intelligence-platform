"""
Throwaway migration runner for 103_update_insight_company_prompt.sql
Updates all insight_company prompt rows to include strategic_summary field.
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

with open(os.path.join(os.path.dirname(__file__), '..', 'migrations', '103_update_insight_company_prompt.sql'), 'r', encoding='utf-8') as f:
    raw_sql = f.read()

stripped = re.sub(r'^\s*BEGIN\s*;\s*$', '', raw_sql, flags=re.MULTILINE | re.IGNORECASE)
stripped = re.sub(r'^\s*COMMIT\s*;\s*$', '', stripped, flags=re.MULTILINE | re.IGNORECASE)

print("[1/3] Applying migration 103 (update insight_company prompt)...")
try:
    try:
        sb.rpc("exec_sql_extended", {"p_query": stripped, "p_timeout_s": 30}).execute()
    except Exception:
        sb.rpc("exec_sql", {"query": stripped}).execute()
    print("  [ok] Migration applied")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print("[2/3] Verifying updated rows...")
try:
    result = sb.table("ai_prompt_config").select("id, prompt_key, client_id, updated_at").eq("prompt_key", "insight_company").eq("is_active", True).execute()
    for row in (result.data or []):
        client = row.get("client_id") or "GLOBAL"
        print(f"  [ok] {client}: updated_at={row.get('updated_at')}")
    print(f"  Total rows updated: {len(result.data or [])}")
except Exception as e:
    print(f"  [WARN] Verification failed: {e}")

print("[3/3] Done.")
