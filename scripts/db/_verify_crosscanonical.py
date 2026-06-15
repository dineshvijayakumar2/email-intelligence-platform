"""Read-only — confirm the rebuilt email_response_metrics has NO cross-canonical-thread pairs
for the 4 AM mailboxes (fix airtight), and diagnose any residual for the shared box."""
import os, sys, io, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from dotenv import load_dotenv
from supabase import create_client
BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
load_dotenv(os.path.join(BACKEND, ".env.production"))
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
CARBON8 = "241d7b99-f099-4557-96e5-212c4af10812"
RPC = """
CREATE OR REPLACE FUNCTION _tmp_xcanon(p_client uuid)
RETURNS jsonb LANGUAGE sql STABLE SET search_path=public SET statement_timeout='120s' AS $fn$
WITH p AS (
  SELECT o.mailbox_id mb,
         (o.canonical_thread_id IS DISTINCT FROM i.canonical_thread_id) xthread,
         (o.canonical_thread_id IS NULL OR i.canonical_thread_id IS NULL) anynull
  FROM email_response_metrics m
  JOIN emails o ON o.id=m.email_id
  JOIN emails i ON i.id=m.responding_to_email_id
  WHERE o.client_id=p_client)
SELECT jsonb_object_agg(coalesce(mb::text,'<none>'), j) FROM (
  SELECT mb, jsonb_build_object('pairs',count(*),
     'cross_canonical',count(*) FILTER (WHERE xthread),
     'any_null_ct',count(*) FILTER (WHERE anynull)) j
  FROM p GROUP BY mb) z;
$fn$;"""
sb.rpc("exec_sql", {"query": RPC}).execute()
sb.rpc("exec_sql", {"query": "NOTIFY pgrst, 'reload schema'"}).execute()
time.sleep(3)
data = sb.rpc("_tmp_xcanon", {"p_client": CARBON8}).execute().data or {}
mboxes = sb.table("mailboxes").select("id,user_id").eq("client_id",CARBON8).execute().data or []
profs = {p["id"]:p.get("name") for p in sb.table("user_profiles").select("id,name").execute().data or []}
disp = {m["id"]: (profs.get(m.get("user_id")) or "<box>") for m in mboxes}
print(f"{'mailbox':<28}{'pairs':>9}{'cross_canon':>13}{'any_null_ct':>13}")
print("-"*63)
for mid, d in data.items():
    print(f"{disp.get(mid, mid)[:27]:<28}{d['pairs']:>9,}{d['cross_canonical']:>13,}{d['any_null_ct']:>13,}")
sb.rpc("exec_sql", {"query": "DROP FUNCTION IF EXISTS _tmp_xcanon(uuid)"}).execute()
sb.rpc("exec_sql", {"query": "NOTIFY pgrst, 'reload schema'"}).execute()
