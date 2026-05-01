"""Check if HNSW index exists on emails.embedding."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
from dotenv import load_dotenv
import requests

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
from dotenv import dotenv_values
config = dotenv_values(env_path)

url = config["SUPABASE_URL"]
key = config["SUPABASE_SERVICE_KEY"]

headers = {
    "apikey": key,
    "Authorization": f"Bearer {key}",
    "Content-Type": "application/json",
}

sql = "SELECT indexname, pg_size_pretty(pg_relation_size(indexname::regclass)) as size FROM pg_indexes WHERE tablename = 'emails' AND indexname LIKE '%embedding%'"

resp = requests.post(
    f"{url}/rest/v1/rpc/exec_sql",
    headers=headers,
    json={"query": sql},
)
print(f"Status: {resp.status_code}")
print(f"Body: {resp.text}")
