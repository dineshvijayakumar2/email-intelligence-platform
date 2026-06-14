"""
13.3 pre-check (read-only): industry-label coverage of the ACTUAL deck / top-100 population.
Three states per company: already labelled in QB | newly enrichable (confident 13.2 guess) | still none.
If coverage is high, the industry filter acts on most cards -> proceed. If low, reconsider scope.
"""
import os, sys, io, json, time
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, "backend")
from dotenv import load_dotenv
from supabase import create_client
HERE = os.path.dirname(__file__)
e = "backend/.env.production" if os.path.exists("backend/.env.production") else "backend/.env"
load_dotenv(e)
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
C8 = "241d7b99-f099-4557-96e5-212c4af10812"
NO_INDUSTRY = {"", "not selected"}
WEAK = {"small business or individual", "extinct"}


def norm(s):
    return " ".join((s or "").strip().split())


def usable(ind):
    lo = (ind or "").lower()
    return ind and lo not in NO_INDUSTRY and lo not in WEAK


def fetch_all(table, select):
    rows, off = [], 0
    while True:
        b = sb.table(table).select(select).eq("client_id", C8).order("id").range(off, off + 999).execute().data or []
        rows += b
        if len(b) < 1000:
            break
        off += 1000
    return rows


# company -> best QB industry (prefer a usable value)
qc = fetch_all("qb_customers", "industry, matched_company_id")
comp_ind = {}
for r in qc:
    cid = r.get("matched_company_id")
    if not cid:
        continue
    ind = norm(r.get("industry"))
    if cid not in comp_ind or (usable(ind) and not usable(comp_ind[cid])):
        comp_ind[cid] = ind

# 13.2 enrichment: company -> (predicted, confidence, flagged)
rev116 = json.load(open(os.path.join(HERE, "industry_116_review.json"), encoding="utf-8"))
enr = {}
for r in rev116["rows"]:
    enr[r["company_id"]] = {"pred": r["predicted_industry"], "conf": r["confidence"],
                            "excl": r["review_flag"].startswith("exclude")}

# 12-mo revenue per company -> top-100 population
sb.rpc("exec_sql", {"query": """CREATE OR REPLACE FUNCTION _tmp_rev100(p uuid) RETURNS jsonb LANGUAGE sql STABLE
SET search_path=public SET statement_timeout='240s' AS $fn$
SELECT coalesce(jsonb_object_agg(cid, r12),'{}') FROM (
  SELECT matched_company_id cid, round(sum(cost_plus_price)::numeric,2) r12 FROM qb_operations
  WHERE client_id=p AND matched_company_id IS NOT NULL AND date_accepted >= DATE '2025-06-14'
  GROUP BY 1 HAVING sum(cost_plus_price) > 0) t; $fn$;"""}).execute()
sb.rpc("exec_sql", {"query": "NOTIFY pgrst,'reload schema'"}).execute(); time.sleep(2)
rev = {k: float(v) for k, v in (sb.rpc("_tmp_rev100", {"p": C8}).execute().data or {}).items()}
sb.rpc("exec_sql", {"query": "DROP FUNCTION IF EXISTS _tmp_rev100(uuid)"}).execute()

top100 = [c for c, _ in sorted(rev.items(), key=lambda kv: -kv[1])[:100]]
deck = json.load(open(os.path.join(HERE, "outreach_cards_50.json"), encoding="utf-8"))["cards"]
deck_cids = [c["company_id"] for c in deck]


def classify_state(cid):
    if usable(comp_ind.get(cid, "")):
        return "qb_labelled"
    e2 = enr.get(cid)
    if e2 and e2["excl"]:
        return "exclude_noncustomer"
    if e2 and e2["pred"] != "Uncertain" and e2["conf"] == "high":
        return "enriched_high"
    if e2 and e2["pred"] != "Uncertain" and e2["conf"] == "low":
        return "enriched_low"
    return "none"   # abstained, or active-but-not-in-116, or no signal


def report(name, cids):
    states = Counter(classify_state(c) for c in cids)
    n = len(cids)
    qb = states["qb_labelled"]
    eh = states["enriched_high"]
    el = states["enriched_low"]
    none = states["none"]
    excl = states["exclude_noncustomer"]
    cov_strict = round(100 * (qb + eh) / n, 1) if n else 0          # QB + confident enrichment
    cov_loose = round(100 * (qb + eh + el) / n, 1) if n else 0      # + tentative low-conf
    print(f"\n  {name} (n={n}):")
    print(f"     already QB-labelled      {qb:>4}  ({round(100*qb/n)}%)")
    print(f"     newly enrichable (high)  {eh:>4}")
    print(f"     newly enrichable (low)   {el:>4}")
    print(f"     still none / abstained   {none:>4}")
    print(f"     internal/exclude         {excl:>4}")
    print(f"     => COVERAGE QB+high = {cov_strict}%   (incl. low-conf = {cov_loose}%)")
    return {"n": n, "qb_labelled": qb, "enriched_high": eh, "enriched_low": el, "none": none,
            "exclude": excl, "coverage_qb_plus_high_pct": cov_strict, "coverage_incl_low_pct": cov_loose}


print("=" * 90)
print("INDUSTRY-LABEL COVERAGE of the deck / top-100 (before applying the 13.3 industry filter)")
print("=" * 90)
out = {"deck_50": report("Deck (50 cards)", deck_cids),
       "top_100_by_revenue": report("Top 100 by 12-mo revenue", top100)}
# also the broad active base for context
active = list(rev.keys())
out["all_active_companies"] = report(f"All active companies (context)", active)
json.dump(out, open(os.path.join(HERE, "deck_industry_coverage.json"), "w", encoding="utf-8"), indent=2)
print("\n  JSON -> scripts/db/deck_industry_coverage.json")
