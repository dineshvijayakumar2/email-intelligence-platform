"""
13.2 — Classify the ~116 active 'Not Selected' customers into a HUMAN-REVIEW list.
Read-only on the DB (writes industry_116_review.json only — NOTHING to qb_customers).

Population: companies with 12-mo revenue (active) whose best industry is NOT a usable industry
  (Not Selected / blank / 'Small Business or Individual' / 'Extinct'). Company grain (deck unit).
Inputs: name + email domain + POST-13.7 clean capability profile (caps_for_op precedence:
  capability_tags classifier-first, qb_capability_tag fills gaps). 13-bucket vocab only. Abstain allowed.
Output sorted abstain/low-confidence first. Reports high/low/abstain + 13-bucket distribution + cost.
"""
import os, sys, io, json, time, base64
from collections import defaultdict, Counter
from concurrent.futures import ThreadPoolExecutor
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, "backend")
from dotenv import load_dotenv
from supabase import create_client
HERE = os.path.dirname(__file__)
e = "backend/.env.production" if os.path.exists("backend/.env.production") else "backend/.env"
load_dotenv(e)
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
C8 = "241d7b99-f099-4557-96e5-212c4af10812"
MODEL = "gpt-4o-mini"
PRICE_IN, PRICE_OUT = 0.15 / 1e6, 0.60 / 1e6
BATCH = 20
ACTIVE_FROM = "2025-06-14"   # rolling 12 months from today 2026-06-14

VOCAB = ["Creative Arts & Design", "Advertising & Marketing", "Corporate & Professional",
         "Property & Real Estate", "Hospitality Food & Beverage", "Trade Printers", "Luxury Brands",
         "Retail & POS", "Government & NFP", "Industrial & Manufacturing", "Education & Training",
         "Healthcare & Medical", "Print Industry / Broker / Supplier"]
NO_INDUSTRY = {"", "not selected"}
WEAK = {"small business or individual", "extinct"}
CAP_ORDER = ["Hard Cover Books", "Soft Cover Books", "Wide Format", "Embellishment", "Display/Installation",
             "Flat Sheets", "Design Services", "Specialty Finishing"]


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


# ── OpenAI key from system_settings (base64) ──
kr = sb.table("system_settings").select("value,client_id").eq("key", "api_key_openai").execute().data or []
key = next((r["value"] for r in kr if r.get("client_id") == C8), kr[0]["value"] if kr else None)
try:
    key = base64.b64decode(key).decode()
except Exception:
    pass
from openai import OpenAI
oai = OpenAI(api_key=key)
USAGE = {"in": 0, "out": 0, "calls": 0}

SYSTEM = ("You classify B2B customers of Carbon8, a commercial print & finishing company in Sydney, Australia, "
          "into industries. Choose EXACTLY ONE industry per customer from this fixed list of 13 (use the exact string):\n"
          + "\n".join("- " + v for v in VOCAB) +
          "\nRules: Do NOT invent categories. Base it on the customer NAME, EMAIL DOMAIN, and what they ORDER. "
          "Set confidence 'high' only when the evidence clearly indicates the industry; otherwise 'low'. "
          "If you genuinely cannot tell, set industry to 'Uncertain' and confidence 'low' (do NOT guess — a wrong "
          "label misleads downstream filters). "
          "Hints: 'Trade Printers'/'Print Industry / Broker / Supplier' = other print shops/brokers/suppliers reselling print. "
          "'Luxury Brands' = high-end fashion/jewellery/beauty/watch brands. 'Corporate & Professional' = law/finance/"
          "consulting/insurance/general corporate. 'Creative Arts & Design' = design studios, photographers, artists, architects. "
          "'Government & NFP' = councils, government, not-for-profits, universities-as-institution. "
          "IMPORTANT: 'Design Services' in the orders is Carbon8's OWN prepress/artwork step that almost every "
          "customer uses — it does NOT indicate the customer is a design/creative firm. Judge Creative-vs-not from "
          "the NAME and DOMAIN, never from a 'Design Services' order. A bare personal name with no domain and a "
          "generic order mix is NOT evidence of Creative Arts & Design — abstain ('Uncertain') instead of guessing. "
          "Respond ONLY as JSON: {\"results\":[{\"id\":<int>,\"industry\":\"<one of the 13 or Uncertain>\","
          "\"confidence\":\"high|low\",\"reasoning\":\"<=12 words\"}]}.")


def classify_batch(items):
    lines = []
    for it in items:
        dom = ", ".join(it["domains"][:3]) or "none"
        orders = ", ".join(it["caps"]) if it["caps"] else "no order history"
        lines.append(f"[{it['id']}] name=\"{it['name']}\" | domains: {dom} | orders: {orders}")
    for attempt in range(4):
        try:
            r = oai.chat.completions.create(
                model=MODEL, temperature=0, response_format={"type": "json_object"},
                messages=[{"role": "system", "content": SYSTEM},
                          {"role": "user", "content": "Classify these customers:\n" + "\n".join(lines)}])
            USAGE["in"] += r.usage.prompt_tokens; USAGE["out"] += r.usage.completion_tokens; USAGE["calls"] += 1
            return {x["id"]: x for x in json.loads(r.choices[0].message.content).get("results", [])}
        except Exception as ex:
            if attempt == 3:
                print(f"    batch failed: {type(ex).__name__} {str(ex)[:80]}", flush=True)
                return {}
            time.sleep(2 * (attempt + 1))


def cost():
    return round(USAGE["in"] * PRICE_IN + USAGE["out"] * PRICE_OUT, 4)


# ── load customers + company name/domains ──
print("loading qb_customers + customer_companies...", flush=True)
qc = fetch_all("qb_customers", "customer_key_id, industry, customer_name, matched_company_id")
cc = fetch_all("customer_companies", "id, company_name, email_domains")
comp_name = {r["id"]: r.get("company_name") for r in cc}
comp_dom = {r["id"]: [d for d in (r.get("email_domains") or []) if d] for r in cc}

# company best industry + the customer rows behind it (for writeback keys/names)
comp_ind, comp_rows = {}, defaultdict(list)
for r in qc:
    cid = r.get("matched_company_id")
    if not cid:
        continue
    r["ind"] = norm(r.get("industry"))
    comp_rows[cid].append(r)
    if cid not in comp_ind or (usable(r["ind"]) and not usable(comp_ind[cid])):
        comp_ind[cid] = r["ind"]

# ── POST-13.7 clean caps (>=1 job, classifier-first) + 12-mo revenue per company ──
CLEAN = """CASE WHEN jsonb_typeof(o.capability_tags)='array' AND jsonb_array_length(o.capability_tags)>0
              THEN o.capability_tags->>0
            WHEN btrim(coalesce(o.qb_capability_tag,''))<>'' THEN btrim(o.qb_capability_tag)
            ELSE NULL END"""
sb.rpc("exec_sql", {"query": f"""CREATE OR REPLACE FUNCTION _tmp_cr116(p uuid) RETURNS jsonb LANGUAGE sql STABLE
SET search_path=public SET statement_timeout='240s' AS $fn$
WITH pc AS (SELECT o.matched_company_id cid, {CLEAN} cap, count(DISTINCT o.job_no) j FROM qb_operations o
            WHERE o.client_id=p AND o.matched_company_id IS NOT NULL GROUP BY 1,2),
rev AS (SELECT matched_company_id cid, round(sum(cost_plus_price)::numeric,2) r12 FROM qb_operations
        WHERE client_id=p AND matched_company_id IS NOT NULL AND date_accepted >= DATE '{ACTIVE_FROM}'
        GROUP BY 1 HAVING sum(cost_plus_price) > 0)
SELECT coalesce(jsonb_agg(jsonb_build_object('cid',c.cid,
  'caps',(SELECT jsonb_agg(jsonb_build_object('cap',cap,'j',j) ORDER BY j DESC) FROM pc
          WHERE pc.cid=c.cid AND j>=1 AND cap IS NOT NULL AND length(cap)>1),
  'r12',coalesce((SELECT r12 FROM rev WHERE rev.cid=c.cid),0))),'[]')
FROM (SELECT DISTINCT cid FROM pc) c; $fn$;"""}).execute()
sb.rpc("exec_sql", {"query": "NOTIFY pgrst,'reload schema'"}).execute(); time.sleep(2)
cr = sb.rpc("_tmp_cr116", {"p": C8}).execute().data or []
sb.rpc("exec_sql", {"query": "DROP FUNCTION IF EXISTS _tmp_cr116(uuid)"}).execute()
comp_caps = {r["cid"]: (r.get("caps") or []) for r in cr}
comp_rev = {r["cid"]: float(r.get("r12") or 0) for r in cr}

# ── population: active + non-usable industry ──
pop_cids = [c for c in comp_ind if comp_rev.get(c, 0) > 0 and not usable(comp_ind[c])]
print(f"population (active + non-usable industry, company grain): {len(pop_cids)}")


def caps_ordered(cid):
    caps = comp_caps.get(cid, [])
    caps = sorted(caps, key=lambda x: -x["j"])
    return [c["cap"] for c in caps]


items = []
for i, cid in enumerate(pop_cids):
    rows = comp_rows.get(cid, [])
    name = comp_name.get(cid) or (rows[0]["customer_name"] if rows else "(unknown)")
    items.append({"id": i, "_cid": cid, "name": name,
                  "domains": comp_dom.get(cid, []),
                  "caps": caps_ordered(cid),
                  "rev12": comp_rev.get(cid, 0),
                  "existing_label": comp_ind.get(cid, ""),
                  "customer_key_ids": sorted({r["customer_key_id"] for r in rows if r.get("customer_key_id")})})

# ── classify ──
print(f"classifying {len(items)} via {MODEL}...", flush=True)
batches = [items[i:i + BATCH] for i in range(0, len(items), BATCH)]
pred = {}
with ThreadPoolExecutor(max_workers=6) as ex:
    for res in ex.map(classify_batch, batches):
        pred.update(res)

import re as _re
INTERNAL_RX = _re.compile(r"(cash account|carbon8|^c8 |\btest\b|internal|staff|sample account)", _re.I)


def review_flag(name, domains, caps):
    if INTERNAL_RX.search(name or ""):
        return "exclude: internal/cash/test account (not a real external customer)"
    if not domains and len([c for c in caps if c != "Design Services"]) == 0:
        return "weak: no domain + no non-generic orders — name-only guess, verify"
    return ""


rows_out = []
for it in items:
    p = pred.get(it["id"], {})
    pi = p.get("industry", "Uncertain")
    pi = pi if (pi in VOCAB or pi == "Uncertain") else "Uncertain"
    conf = p.get("confidence", "low")
    abstain = pi == "Uncertain"
    sig = "+".join([s for s, ok in (("name", it["name"]), ("domain", it["domains"]), ("orders", it["caps"])) if ok]) or "none"
    rows_out.append({
        "customer_name": it["name"],
        "company_id": it["_cid"],
        "customer_key_ids": it["customer_key_ids"],
        "existing_label": it["existing_label"] or "(blank)",
        "predicted_industry": pi,
        "confidence": ("abstain" if abstain else conf),
        "reasoning": p.get("reasoning", ""),
        "signals_used": sig,
        "review_flag": review_flag(it["name"], it["domains"], it["caps"]),
        "revenue_12mo": round(it["rev12"]),
        "capability_profile": [f"{c['cap']} ({c['j']})" for c in sorted(comp_caps.get(it["_cid"], []), key=lambda x: -x["j"])],
    })

# sort: flagged-exclude first (deal with non-customers), then abstain, low, high; revenue desc within
rank = {"abstain": 0, "low": 1, "high": 2}
rows_out.sort(key=lambda r: (0 if r["review_flag"].startswith("exclude") else 1,
                             rank.get(r["confidence"], 0), -r["revenue_12mo"]))

n = len(rows_out)
hi = [r for r in rows_out if r["confidence"] == "high"]
lo = [r for r in rows_out if r["confidence"] == "low"]
ab = [r for r in rows_out if r["confidence"] == "abstain"]
flagged_excl = [r for r in rows_out if r["review_flag"].startswith("exclude")]
flagged_weak = [r for r in rows_out if r["review_flag"].startswith("weak")]
dist = Counter(r["predicted_industry"] for r in rows_out)
# substantive skew = a real bucket dominating (distrust); Uncertain dominating = honest abstention (fine)
subst = Counter({k: v for k, v in dist.items() if k != "Uncertain"})
top_subst = subst.most_common(1)[0] if subst else ("", 0)
n_unc = dist.get("Uncertain", 0)
skew_warnings = []
if n and top_subst[1] / n > 0.30:
    skew_warnings.append(f"SUBSTANTIVE SKEW: {top_subst[0]} is {round(100*top_subst[1]/n)}% of the list — "
                         f"likely over-assigned; spot-check before trusting.")
if n and n_unc / n > 0.30:
    skew_warnings.append(f"{n_unc} ({round(100*n_unc/n)}%) abstained — EXPECTED for this unlabelled small/individual "
                         f"tail (honest 'unsure' beats a wrong label); these need a quick name/domain lookup or exclusion.")
if flagged_excl:
    skew_warnings.append(f"{len(flagged_excl)} rows are internal/cash/test accounts (not real customers) — exclude, do not label.")

out = {"generated": "2026-06-14", "task": "13.2", "model": MODEL, "grain": "company (matched_company_id)",
       "population_definition": "active (12-mo revenue>0 from 2025-06-14) AND industry not usable "
                                "(Not Selected/blank/Small Business or Individual/Extinct)",
       "count": n, "vocabulary": VOCAB,
       "summary": {"high": len(hi), "low": len(lo), "abstain": len(ab),
                   "flagged_exclude_internal": len(flagged_excl), "flagged_weak_nameonly": len(flagged_weak),
                   "distribution": dict(dist.most_common())},
       "skew_warnings": skew_warnings,
       "cost_usd": cost(), "cost_cents": round(cost() * 100, 2),
       "tokens": {"in": USAGE["in"], "out": USAGE["out"], "calls": USAGE["calls"]},
       "rows": rows_out}
json.dump(out, open(os.path.join(HERE, "industry_116_review.json"), "w", encoding="utf-8"), indent=2, default=str)

P = print
P("\n" + "=" * 96); P("13.2 — INDUSTRY REVIEW LIST (active 'Not Selected' customers, human-review)"); P("=" * 96)
P(f"  population: {n} companies (active + non-usable industry)")
P(f"  confidence: HIGH {len(hi)} | LOW {len(lo)} | ABSTAIN {len(ab)}   "
  f"(flagged: {len(flagged_excl)} internal/cash/test, {len(flagged_weak)} weak name-only)")
P(f"\n  predicted 13-bucket distribution:")
for k, c in dist.most_common():
    bar = ""
    if k == top_subst[0] and c / n > 0.30:
        bar = "  <-- substantive skew: spot-check"
    elif k == "Uncertain":
        bar = "  <-- abstained (honest unsure): lookup/exclude"
    P(f"     {k:<36} {c}{bar}")
for w in skew_warnings:
    P(f"  ! {w}")
P(f"\n  cost: {round(cost()*100,2)} cents  ({USAGE['calls']} calls, {USAGE['in']} in / {USAGE['out']} out tok)")
P(f"\n  attention-first preview (abstain + lowest-confidence, highest-revenue):")
for r in rows_out[:12]:
    caps = ", ".join(r["capability_profile"][:3]) or "no orders"
    P(f"    [{r['confidence']:<7}] {r['customer_name'][:28]:<29} -> {r['predicted_industry']:<26} ${r['revenue_12mo']:>8,}  {caps}")
P("\n  JSON -> scripts/db/industry_116_review.json   (NO writes to qb_customers)")
