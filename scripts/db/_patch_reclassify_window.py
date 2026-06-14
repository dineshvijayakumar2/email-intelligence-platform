"""Patch the single chunk that failed during _reclassify_layer1 (transient WinError 10054 at
offset 528000). Re-reclassify a wide deterministic id-ordered window around it. Idempotent."""
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
cc.invalidate_cache(C8)
st = cc._get_client_state(sb, C8)
lookup, kw, rush = st["lookup"], st["keyword_rules"], st["rush_pattern"]
LO, HI = 527900, 528200   # wide window around the failed offset 528000+0..100


def classify(dept, op, machine, qb_row):
    key = (cc._normalize(dept), cc._normalize(op), cc._normalize(machine))
    m = lookup.get(key)
    if not m:
        comb = f"{dept or ''} {op or ''} {machine or ''}".lower()
        for kws, tag in kw:
            if any(k in comb for k in kws):
                m = {"tag": tag, "flags": [], "row_type": None}; break
    tags = [m["tag"]] if m and m.get("tag") else []
    flags = (m.get("flags") or []) if m else []
    return tags, flags, (qb_row or (m.get("row_type") if m else None) or None), (op or "").startswith(rush)


rows = sb.table("qb_operations").select(
    "id, department, operation_name, machine, qb_row_type_tag"
).eq("client_id", C8).order("id").range(LO, HI - 1).execute().data or []
ids, tg, co, sw, ou, ru, rt = [], [], [], [], [], [], []
for r in rows:
    qb_row = (r.get("qb_row_type_tag") or "").strip() or None
    tags, flags, row_type, am = classify(r.get("department"), r.get("operation_name"), r.get("machine"), qb_row)
    ids.append(r["id"]); tg.append(json.dumps(tags))  # JSON text; RPC casts text[]->jsonb (mig 123)
    co.append("has_coating" in flags); sw.append("has_sewing" in flags)
    ou.append("has_outsource_component" in flags); ru.append(am); rt.append(row_type)
written = 0
for ci in range(0, len(ids), 100):
    j = ci + 100
    sb.rpc("batch_update_classifications", {
        "p_ids": ids[ci:j], "p_capability_tags": tg[ci:j], "p_has_coating": co[ci:j],
        "p_has_sewing": sw[ci:j], "p_has_outsource_component": ou[ci:j],
        "p_am_rush": ru[ci:j], "p_row_type": rt[ci:j]}).execute()
    written += len(ids[ci:j]); time.sleep(0.05)
print(f"patched window [{LO},{HI}): {len(rows)} rows fetched, {written} rewritten")
