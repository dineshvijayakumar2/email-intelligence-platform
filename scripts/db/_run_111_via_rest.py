"""
Throwaway runner for migration 111: auto-rename SB company at match-write time.
Delete this file after verification.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
from dotenv import load_dotenv
from supabase import create_client

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
load_dotenv(env_path)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

sql_path = os.path.join(os.path.dirname(__file__), '..', 'migrations', '111_match_write_auto_rename.sql')
with open(sql_path, 'r') as f:
    raw = f.read()

# Strip comments but preserve $$ blocks — send entire function as one statement
import re
cleaned = re.sub(r'--[^\n]*', '', raw).strip().rstrip(';')

print(f"Executing migration 111 as single statement...")
print(f"  SQL length: {len(cleaned)} chars")
try:
    result = sb.rpc('exec_sql', {'query': cleaned}).execute()
    print(f"  [OK] Function created/replaced")
except Exception as e:
    print(f"  [FAIL] {e}")

print("\nReloading schema cache...")
try:
    sb.rpc('exec_sql', {'query': "NOTIFY pgrst, 'reload schema'"}).execute()
    print("  [OK] Schema cache reloaded")
except Exception as e:
    print(f"  [FAIL] {e}")
