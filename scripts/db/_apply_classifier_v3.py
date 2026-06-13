"""
Step 3a (FIRST PROD WRITE — gate passed): write corrected classifier rules to the LIVE
client_taxonomy_config for Carbon8 (classifier_rules v2 -> v3).

  - applies the same exact-tuple corrections to the LIVE tuples (preserves any UI edits)
  - adds config-driven keyword_rules (the corrected taxonomy)
  - bumps version so the in-memory classifier cache reloads
Does NOT touch qb_capability_tag. Does NOT run reclassify (separate step).
"""
import os, sys, io, json
sys.path.insert(0, "backend"); sys.path.insert(0, "backend/src/services")
sys.path.insert(0, "scripts/db")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from dotenv import load_dotenv
from supabase import create_client
import capability_classifier as cc
from _fix_classifier_tuples import corrected_tag   # shape-agnostic correction (JSON + live)

e = "backend/.env.production" if os.path.exists("backend/.env.production") else "backend/.env"
load_dotenv(e)
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
C8 = "241d7b99-f099-4557-96e5-212c4af10812"

row = sb.table("client_taxonomy_config").select("id, config_data, version").eq(
    "client_id", C8).eq("config_type", "classifier_rules").single().execute().data
cfg = row["config_data"] or {}
rules = cfg.get("rules", [])
old_ver = row["version"]
print(f"live classifier_rules v{old_ver}: {len(rules)} tuples (keys: {sorted(rules[0].keys())})")

# apply exact-tuple corrections to the LIVE tuples (live shape: op/tag/dept), write back to 'tag'
changes = []
for r in rules:
    new = corrected_tag(r.get("dept"), r.get("op"), r.get("tag"))
    if new and new != r.get("tag"):
        changes.append((r.get("dept"), r.get("op"), r.get("tag"), new))
        r["tag"] = new
print(f"exact-tuple corrections applied to live rules: {len(changes)}")
for dept, op, old, new in changes:
    print(f"   [{dept}] {(op or '')[:46]!r}: {old} -> {new}")

keyword_rules = [{"keywords": kws, "tag": tag} for kws, tag in cc._KEYWORD_RULES]
new_cfg = {"rules": rules, "keyword_rules": keyword_rules}
new_ver = old_ver + 1

sb.table("client_taxonomy_config").update({
    "config_data": new_cfg,
    "version": new_ver,
    "description": f"Classifier rules — {len(rules)} tuples + {len(keyword_rules)} keyword rules "
                   f"(Layer-1 capability correction: cello->Specialty, fuse->Specialty, "
                   f"Printing/SwissQ->WideFormat, oversew/section->SoftCover)",
}).eq("id", row["id"]).execute()
print(f"\nwritten: classifier_rules v{old_ver} -> v{new_ver}  (+{len(keyword_rules)} keyword_rules)")

# invalidate in-memory cache + confirm reload picks up v3
cc.invalidate_cache(C8)
state = cc._get_client_state(sb, C8)
print(f"classifier reloaded: version={state['version']}, exact lookup={len(state['lookup'])}, "
      f"keyword_rules={len(state['keyword_rules'])}")
