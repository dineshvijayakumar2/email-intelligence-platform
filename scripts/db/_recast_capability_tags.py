"""
Repair existing double-encoded capability_tags: rows stored as a jsonb STRING "[\"X\"]"
-> proper jsonb array ["X"]. Values are already correct (classifier output); only the
encoding is wrong. Batched server-side to avoid a long exclusive lock. Idempotent.
"""
import os, sys, io, time
sys.path.insert(0, "backend")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from dotenv import load_dotenv
from supabase import create_client
e = "backend/.env.production" if os.path.exists("backend/.env.production") else "backend/.env"
load_dotenv(e)
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
C8 = "241d7b99-f099-4557-96e5-212c4af10812"

# batched re-cast function: unwrap up to p_lim string-typed rows, return count updated
sb.rpc("exec_sql", {"query": """
CREATE OR REPLACE FUNCTION _tmp_recast(p uuid, p_lim int) RETURNS integer
LANGUAGE plpgsql SET search_path=public SET statement_timeout='120s' AS $fn$
DECLARE n integer;
BEGIN
  WITH c AS (SELECT id FROM qb_operations
             WHERE client_id=p AND jsonb_typeof(capability_tags)='string'
             LIMIT p_lim FOR UPDATE SKIP LOCKED)
  UPDATE qb_operations o SET capability_tags = (o.capability_tags #>> '{}')::jsonb
  FROM c WHERE o.id=c.id;
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END $fn$;"""}).execute()
sb.rpc("exec_sql", {"query": "NOTIFY pgrst,'reload schema'"}).execute(); time.sleep(2)

total = 0
t0 = time.time()
while True:
    n = sb.rpc("_tmp_recast", {"p": C8, "p_lim": 25000}).execute().data
    n = int(n or 0)
    total += n
    print(f"  re-cast {total} rows ({int(time.time()-t0)}s)", flush=True)
    if n == 0:
        break
    time.sleep(0.1)

sb.rpc("exec_sql", {"query": "DROP FUNCTION IF EXISTS _tmp_recast(uuid,int)"}).execute()
print(f"DONE: {total} rows re-cast to jsonb arrays in {int(time.time()-t0)}s")
