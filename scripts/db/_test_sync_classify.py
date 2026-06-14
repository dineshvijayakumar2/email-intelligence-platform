"""
Step 5 verification (controlled, reversible): force a few known ops to the NULL sentinel,
run the ACTUAL QuickbaseSync._classify_operations, and confirm:
  - capability_tags = classifier output (cello -> Specialty, NOT the qb 'Embellishment' copy)
  - written as a proper jsonb ARRAY (migration-123 RPC path), not a double-encoded string
  - idempotent: a second run finds no NULL rows (returns 0)
Restores nothing destructive — the rows get correct classifier values (same as the full reclassify).
"""
import os, sys, io, json, time
sys.path.insert(0, "backend"); sys.path.insert(0, "backend/src"); sys.path.insert(0, "backend/src/services")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from dotenv import load_dotenv
from supabase import create_client
e = "backend/.env.production" if os.path.exists("backend/.env.production") else "backend/.env"
load_dotenv(e)
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
C8 = "241d7b99-f099-4557-96e5-212c4af10812"
from services.quickbase_sync import QuickbaseSync

cfg = sb.table("qb_sync_config").select("*").eq("client_id", C8).limit(1).execute().data[0]
svc = QuickbaseSync(sb, cfg)

# pick one row each: cello (qb=Embellishment), foil (classifier Embellishment), generic (empty)
targets = {}
for opname in ("Matt cello", "Hot foil stamping", "Guillotine"):
    r = sb.table("qb_operations").select("id, operation_name, capability_tags, qb_capability_tag").eq(
        "client_id", C8).eq("operation_name", opname).limit(1).execute().data
    if r:
        targets[opname] = r[0]
ids = [t["id"] for t in targets.values()]
print("BEFORE (current state):")
for nm, t in targets.items():
    print(f"  {nm!r:20} ct={t['capability_tags']}  qb={t['qb_capability_tag']}")

# force NULL sentinel (simulate newly-synced, unclassified)
for i in ids:
    sb.table("qb_operations").update({"capability_tags": None}).eq("id", i).execute()
print(f"\nforced {len(ids)} rows -> capability_tags = NULL (never-classified sentinel)")

# run the ACTUAL sync classify method
n = svc._classify_operations()
print(f"_classify_operations() pass 1 -> classified {n} rows")

# verify results + shape
print("\nAFTER classify:")
for nm, t in targets.items():
    row = sb.table("qb_operations").select("capability_tags, qb_capability_tag").eq("id", t["id"]).single().execute().data
    ct = row["capability_tags"]
    print(f"  {nm!r:20} ct={ct!r}  (py type={type(ct).__name__})  qb={row['qb_capability_tag']}")

# shape check via SQL (must be array, not string)
sb.rpc("exec_sql", {"query": f"""CREATE OR REPLACE FUNCTION _tmp_sh() RETURNS jsonb LANGUAGE sql STABLE
SET search_path=public AS $f$ SELECT jsonb_object_agg(t,n) FROM (SELECT jsonb_typeof(capability_tags) t, count(*) n
FROM qb_operations WHERE id = ANY(ARRAY{[str(i) for i in ids]}::uuid[]) GROUP BY 1) z $f$;"""}).execute()
sb.rpc("exec_sql", {"query": "NOTIFY pgrst,'reload schema'"}).execute(); time.sleep(2)
print("\nshape of the 3 rows:", sb.rpc("_tmp_sh", {}).execute().data)
sb.rpc("exec_sql", {"query": "DROP FUNCTION IF EXISTS _tmp_sh()"}).execute()

# idempotency: second run should find no NULL rows
n2 = svc._classify_operations()
print(f"\n_classify_operations() pass 2 (idempotency) -> classified {n2} rows (expect 0)")
