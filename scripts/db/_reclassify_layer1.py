"""
Step 3b (PROD WRITE — gate passed): reclassify Carbon8 qb_operations.capability_tags as PURE
op-name classifier output (corrected v4 rules). Writes capability_tags + classifier flags;
PRESERVES row_type = qb_row_type_tag or classifier (does NOT clobber QB row_type, unlike the
stock reclassify_all). Does NOT touch qb_capability_tag (read-only QB source).

Idempotent: re-running yields the same tags. Normalizes the mixed string/array shape -> json arrays.
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

cc.invalidate_cache(C8)
state = cc._get_client_state(sb, C8)
lookup = state["lookup"]; keyword_rules = state["keyword_rules"]; rush = state["rush_pattern"]
print(f"classifier v{state['version']}: {len(lookup)} exact tuples, {len(keyword_rules)} keyword rules", flush=True)


def classify_row(dept, op, machine, qb_row):
    key = (cc._normalize(dept), cc._normalize(op), cc._normalize(machine))
    match = lookup.get(key)
    if not match:
        combined = f"{dept or ''} {op or ''} {machine or ''}".lower()
        for kws, tag in keyword_rules:
            if any(k in combined for k in kws):
                match = {"tag": tag, "flags": [], "row_type": None}
                break
    tags = [match["tag"]] if match and match.get("tag") else []
    flags = (match.get("flags") or []) if match else []
    clf_row = match.get("row_type") if match else None
    return tags, flags, (qb_row or clf_row or None), (op or "").startswith(rush)


total = 0; offset = 0; BATCH = 1000; CHUNK = 100; t0 = time.time()
while True:
    rows = sb.table("qb_operations").select(
        "id, department, operation_name, machine, qb_row_type_tag"
    ).eq("client_id", C8).order("id").range(offset, offset + BATCH - 1).execute().data or []
    if not rows:
        break
    ids, tags_a, coat, sew, outs, rush_a, rtype = [], [], [], [], [], [], []
    for r in rows:
        qb_row = (r.get("qb_row_type_tag") or "").strip() or None
        tags, flags, row_type, am_rush = classify_row(
            r.get("department"), r.get("operation_name"), r.get("machine"), qb_row)
        ids.append(r["id"]); tags_a.append(json.dumps(tags))
        coat.append("has_coating" in flags); sew.append("has_sewing" in flags)
        outs.append("has_outsource_component" in flags); rush_a.append(am_rush); rtype.append(row_type)
    for ci in range(0, len(ids), CHUNK):
        j = ci + CHUNK
        try:
            sb.rpc("batch_update_classifications", {
                "p_ids": ids[ci:j], "p_capability_tags": tags_a[ci:j],
                "p_has_coating": coat[ci:j], "p_has_sewing": sew[ci:j],
                "p_has_outsource_component": outs[ci:j], "p_am_rush": rush_a[ci:j],
                "p_row_type": rtype[ci:j],
            }).execute()
            total += len(ids[ci:j])
        except Exception as ex:
            print(f"  chunk write failed @offset {offset}+{ci}: {ex}", flush=True)
        time.sleep(0.05)
    offset += len(rows)
    if offset % 20000 == 0:
        print(f"  {offset} rows processed, {total} written, {int(time.time()-t0)}s", flush=True)
    if len(rows) < BATCH:
        break
print(f"DONE: {total} rows reclassified in {int(time.time()-t0)}s", flush=True)
