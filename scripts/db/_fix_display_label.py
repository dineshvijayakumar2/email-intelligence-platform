"""
Align the classifier's Display label to QB's spelling: 'Display / Installation' -> 'Display/Installation'
(QB uses no spaces; a mismatch silently breaks Display joins/filters in the deck/cards).

Fixes all sources: JSON seed, live client_taxonomy_config (classifier_rules tuples + keyword_rules,
and the capability_tags UI metadata), and the existing 673 reclassified ops (in-place jsonb replace).
"""
import os, sys, io, json, time
sys.path.insert(0, "backend"); sys.path.insert(0, "backend/src/services")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from dotenv import load_dotenv
from supabase import create_client
import capability_classifier as cc
e = "backend/.env.production" if os.path.exists("backend/.env.production") else "backend/.env"
load_dotenv(e)
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
C8 = "241d7b99-f099-4557-96e5-212c4af10812"
OLD, NEW = "Display / Installation", "Display/Installation"

# 1. JSON seed
p = "backend/src/services/capability_classifier_data.json"
t = open(p, encoding="utf-8").read()
n_json = t.count(OLD)
open(p, "w", encoding="utf-8").write(t.replace(OLD, NEW))
print(f"JSON seed: {n_json} occurrences -> {NEW}")

# 2. live config classifier_rules (tuples + keyword_rules) + bump version
row = sb.table("client_taxonomy_config").select("id, config_data, version").eq(
    "client_id", C8).eq("config_type", "classifier_rules").single().execute().data
cfg = row["config_data"]
n_tuples = sum(1 for r in cfg.get("rules", []) if r.get("tag") == OLD)
for r in cfg.get("rules", []):
    if r.get("tag") == OLD:
        r["tag"] = NEW
n_kw = 0
for kr in cfg.get("keyword_rules", []):
    if kr.get("tag") == OLD:
        kr["tag"] = NEW; n_kw += 1
sb.table("client_taxonomy_config").update(
    {"config_data": cfg, "version": row["version"] + 1}).eq("id", row["id"]).execute()
print(f"live classifier_rules v{row['version']}->v{row['version']+1}: {n_tuples} tuples + {n_kw} keyword rule relabelled")

# 3. live config capability_tags (UI metadata)
try:
    ct = sb.table("client_taxonomy_config").select("id, config_data, version").eq(
        "client_id", C8).eq("config_type", "capability_tags").single().execute().data
    cd = ct["config_data"]; changed = 0
    for tg in cd.get("tags", []):
        if tg.get("name") == OLD:
            tg["name"] = NEW; changed += 1
    if changed:
        sb.table("client_taxonomy_config").update(
            {"config_data": cd, "version": ct["version"] + 1}).eq("id", ct["id"]).execute()
    print(f"live capability_tags UI metadata: {changed} name relabelled")
except Exception as ex:
    print(f"capability_tags metadata update skipped: {ex}")

cc.invalidate_cache(C8)

# 4. existing data: in-place jsonb replace for any Display element (handles any position)
sb.rpc("exec_sql", {"query": f"""CREATE OR REPLACE FUNCTION _tmp_disprelabel(p uuid) RETURNS integer
LANGUAGE plpgsql SET search_path=public SET statement_timeout='120s' AS $fn$
DECLARE n integer;
BEGIN
  UPDATE qb_operations
  SET capability_tags = replace(capability_tags::text, '{OLD}', '{NEW}')::jsonb
  WHERE client_id=p AND capability_tags::text LIKE '%{OLD}%';
  GET DIAGNOSTICS n = ROW_COUNT; RETURN n;
END $fn$;"""}).execute()
sb.rpc("exec_sql", {"query": "NOTIFY pgrst,'reload schema'"}).execute(); time.sleep(2)
n_rows = sb.rpc("_tmp_disprelabel", {"p": C8}).execute().data
sb.rpc("exec_sql", {"query": "DROP FUNCTION IF EXISTS _tmp_disprelabel(uuid)"}).execute()
print(f"existing ops relabelled in capability_tags: {n_rows}")
