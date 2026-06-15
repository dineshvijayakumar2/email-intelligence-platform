"""Read-only — mailbox-scoped metric counts per Carbon8 mailbox vs what the recompute inserted,
to find any box left with stale rows (client_id-scoped delete missed them)."""
import os, sys, io, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from dotenv import load_dotenv
from supabase import create_client
BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
load_dotenv(os.path.join(BACKEND, ".env.production"))
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
CARBON8 = "241d7b99-f099-4557-96e5-212c4af10812"
SAVED = {"5f3afeb3-a5f7-44b8-b657-ec972c92911d":("Nic",8034),
         "71ebdbc8-c3ca-4802-942e-948975c736ea":("Jeff",268),
         "e1abc287-805b-4cee-8f95-0b47e1cd8f99":("Linda",16190),
         "c1157f56-79a0-4f0b-9dcf-2db257f0d5c4":("Hello",15592),
         "1332eba5-9121-4b55-91db-a37dd81d5d85":("Kenneth",7967),
         "92eba92f-b6be-4fbf-8c49-9f3b7c72ea74":("Ehab",18888),
         "3e09b3d0-5fb2-4499-819f-cc5f0c35b94e":("Production",2160)}
ids = ",".join(f"'{k}'" for k in SAVED)
RPC = f"""
CREATE OR REPLACE FUNCTION _tmp_mbcount() RETURNS jsonb LANGUAGE sql STABLE
SET search_path=public SET statement_timeout='120s' AS $fn$
SELECT jsonb_object_agg(mb, jsonb_build_object('rows',c,'nonc8_emails',nc)) FROM (
  SELECT e.mailbox_id::text mb, count(*) c,
         count(*) FILTER (WHERE e.client_id IS DISTINCT FROM '{CARBON8}') nc
  FROM email_response_metrics m JOIN emails e ON e.id=m.email_id
  WHERE e.mailbox_id IN ({ids}) GROUP BY e.mailbox_id) z;
$fn$;"""
sb.rpc("exec_sql", {"query": RPC}).execute()
sb.rpc("exec_sql", {"query": "NOTIFY pgrst, 'reload schema'"}).execute()
time.sleep(3)
data = sb.rpc("_tmp_mbcount", {}).execute().data or {}
print(f"{'box':<12}{'saved':>9}{'current':>9}{'delta':>8}{'nonC8_in_pairs':>16}  status")
print("-"*70)
for mid,(nm,saved) in SAVED.items():
    d = data.get(mid, {"rows":0,"nonc8_emails":0})
    cur = d["rows"]; nc = d["nonc8_emails"]
    status = "CLEAN" if cur==saved else f"STALE (+{cur-saved})"
    print(f"{nm:<12}{saved:>9,}{cur:>9,}{cur-saved:>+8,}{nc:>16,}  {status}")
sb.rpc("exec_sql", {"query": "DROP FUNCTION IF EXISTS _tmp_mbcount()"}).execute()
sb.rpc("exec_sql", {"query": "NOTIFY pgrst, 'reload schema'"}).execute()
