"""
Part A writeback (13.2): apply migration 125 (enriched columns) and write Dinesh's approved
industry labels to qb_customers.industry_enriched for the listed customer_key_ids.
Never touches qb_customers.industry (QB source of truth). Skips abstained (null) + excluded.
"""
import os, sys, io, json, time
sys.path.insert(0, "backend")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from dotenv import load_dotenv
from supabase import create_client
HERE = os.path.dirname(__file__)
e = "backend/.env.production" if os.path.exists("backend/.env.production") else "backend/.env"
load_dotenv(e)
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
C8 = "241d7b99-f099-4557-96e5-212c4af10812"
NOW = "2026-06-14T00:00:00Z"   # fixed stamp (Date.now unavailable; deterministic)

# apply migration 125
sql = open(os.path.join(HERE, "..", "migrations", "125_qb_customers_industry_enriched.sql"), encoding="utf-8").read()
sb.rpc("exec_sql", {"query": sql}).execute()
sb.rpc("exec_sql", {"query": "NOTIFY pgrst,'reload schema'"}).execute(); time.sleep(2)
print("migration 125 applied (industry_enriched / industry_source / industry_enriched_at)")

ap = json.load(open(os.path.join(HERE, "industry_116_approved.json"), encoding="utf-8"))

# collect writeback rows from the three approved sections, with provenance
writeback = []
for sect, src in [("corrections_from_review", "human_corrected"),
                  ("low_confidence_promoted_to_approved", "human_promoted"),
                  ("high_confidence_approved_as_is", "llm_high_conf")]:
    for r in ap.get(sect, []):
        lbl = r.get("approved_industry")
        if not lbl:   # skip null/abstained
            continue
        for kid in (r.get("customer_key_ids") or []):
            writeback.append({"customer_key_id": str(kid), "label": lbl, "source": src,
                              "name": r.get("customer_name", "")})

excluded_keys = {str(k) for r in ap.get("excluded_not_customers", []) for k in (r.get("customer_key_ids") or [])}
print(f"approved labels to write: {len(writeback)} customer_key_ids "
      f"({len({w['customer_key_id'] for w in writeback})} distinct) | excluded (skipped): {len(excluded_keys)} keys")

written, missing = 0, []
for w in writeback:
    if w["customer_key_id"] in excluded_keys:
        continue
    resp = sb.table("qb_customers").update({
        "industry_enriched": w["label"], "industry_source": w["source"], "industry_enriched_at": NOW
    }).eq("client_id", C8).eq("customer_key_id", w["customer_key_id"]).execute()
    if resp.data:
        written += len(resp.data)
    else:
        missing.append((w["customer_key_id"], w["name"]))

print(f"\nWRITTEN: {written} qb_customers rows updated with industry_enriched")
if missing:
    print(f"  WARNING: {len(missing)} customer_key_ids not found in qb_customers:")
    for k, nm in missing[:10]:
        print(f"    key={k} ({nm})")

# verify
ver = sb.table("qb_customers").select("customer_key_id, industry, industry_enriched, industry_source").eq(
    "client_id", C8).not_.is_("industry_enriched", "null").execute().data or []
print(f"\nverify: {len(ver)} rows now carry industry_enriched. QB 'industry' untouched (sample):")
from collections import Counter
for src, c in Counter(v["industry_source"] for v in ver).most_common():
    print(f"   source {src}: {c}")
for v in ver[:5]:
    print(f"   key={v['customer_key_id']} qb_industry={v['industry']!r} -> enriched={v['industry_enriched']!r} ({v['industry_source']})")
