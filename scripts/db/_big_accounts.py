"""
Big-accounts saturation view (post-cello-fix). Top accounts by TRAILING-12-MONTH revenue;
per account: 12mo revenue, capabilities bought, and cross-sell status:
  has-real-gap (with the pitch) / saturated (broad basket, no meaningful gap) / retention-focus.
Complements the opportunity deck (which ranks by gap, not size). Read-only.
"""
import os, sys, io, json, time
from collections import defaultdict, Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, "backend")
from dotenv import load_dotenv
from supabase import create_client
HERE = os.path.dirname(__file__)
e = "backend/.env.production" if os.path.exists("backend/.env.production") else "backend/.env"
load_dotenv(e)
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
C8 = "241d7b99-f099-4557-96e5-212c4af10812"
CUT = "2025-06-14"            # trailing 12 months (rolling from today)
TOPN = 100                    # 13.8: extend to top 100 by 12mo revenue
SUPPORT_FLOOR, CONF_FLOOR, LIFT_FLOOR, EMB_FINISH_FLOOR = 30, 0.25, 1.0, 2
import re

# Post-13.7 CLEAN effective capability via the caps_for_op precedence: classifier capability_tags
# first, qb_capability_tag fills gaps. No inline re-derivation (the Layer-1 classifier is the source
# of truth; the old cello-fix CASE is removed so big-accounts matches the deck and the platform).
EFF = """CASE
   WHEN jsonb_typeof(o.capability_tags)='array' AND jsonb_array_length(o.capability_tags)>0 THEN o.capability_tags->>0
   WHEN btrim(coalesce(o.qb_capability_tag,''))<>'' THEN btrim(o.qb_capability_tag)
   ELSE NULL END"""


def ddl(q):
    return sb.rpc("exec_sql", {"query": q}).execute()


def normcap(c):
    return re.sub(r"\s*/\s*", "/", (c or "").strip())


# basket (all-time, cello-fixed) + emb-finish + 12mo revenue, per company
ddl(f"""
CREATE OR REPLACE FUNCTION _tmp_big(p_client uuid)
RETURNS jsonb LANGUAGE sql STABLE SET search_path=public SET statement_timeout='240s' AS $fn$
WITH op AS (
  SELECT o.matched_company_id cid, o.job_no, {EFF} eff, o.cost_plus_price cpp, o.date_accepted d,
         (btrim(coalesce(o.qb_embellishment_tag,''))<>'')::int embf
  FROM qb_operations o WHERE o.client_id=p_client AND o.matched_company_id IS NOT NULL AND o.job_no IS NOT NULL),
percap AS (SELECT cid, eff, count(DISTINCT job_no) jobs, round(coalesce(sum(cpp),0)::numeric,2) rev
           FROM op WHERE eff IS NOT NULL AND length(eff)>1 GROUP BY cid, eff),
rev12 AS (SELECT cid, round(coalesce(sum(cpp),0)::numeric,2) r12 FROM op WHERE d>=DATE '{CUT}' GROUP BY cid),
embf AS (SELECT cid, count(DISTINCT job_no) ej FROM op WHERE embf=1 GROUP BY cid),
-- owning AM = am_job of the most recent job in the trailing window, else am_customer
am AS (SELECT DISTINCT ON (o.matched_company_id) o.matched_company_id cid,
         coalesce(nullif(btrim(o.am_job),''), nullif(btrim(o.am_customer),'')) amname
       FROM qb_operations o WHERE o.client_id=p_client AND o.matched_company_id IS NOT NULL
         AND o.date_accepted >= DATE '{CUT}'
       ORDER BY o.matched_company_id, o.date_accepted DESC NULLS LAST)
SELECT coalesce(jsonb_agg(jsonb_build_object(
  'cid', c.cid, 'rev12', coalesce(rv.r12,0), 'emb_jobs', coalesce(ef.ej,0), 'am', am.amname,
  'caps', (SELECT jsonb_object_agg(eff, jsonb_build_object('jobs',jobs,'rev',rev)) FROM percap p WHERE p.cid=c.cid),
  'caps_any', (SELECT jsonb_agg(eff) FROM percap p WHERE p.cid=c.cid AND p.jobs>=1)
)), '[]'::jsonb)
FROM (SELECT DISTINCT cid FROM op) c
LEFT JOIN rev12 rv ON rv.cid=c.cid LEFT JOIN embf ef ON ef.cid=c.cid LEFT JOIN am ON am.cid=c.cid;
$fn$;""")
ddl("NOTIFY pgrst,'reload schema'"); time.sleep(2)
print("Pulling cello-fixed basket + 12mo revenue (full base)...", flush=True)
rows = sb.rpc("_tmp_big", {"p_client": C8}).execute().data or []
ddl("DROP FUNCTION IF EXISTS _tmp_big(uuid)")

comp = {}
for r in rows:
    cid = r["cid"]
    caps = {normcap(k): {"jobs": int(v["jobs"]), "rev": float(v["rev"])} for k, v in (r.get("caps") or {}).items()}
    anyc = {normcap(x) for x in (r.get("caps_any") or [])}
    comp[cid] = {"rev12": float(r.get("rev12") or 0), "emb": int(r.get("emb_jobs") or 0),
                 "am": (r.get("am") or "(unassigned)").strip() or "(unassigned)",
                 "caps2": {k: v for k, v in caps.items() if v["jobs"] >= 2}, "any": anyc}

# industry per company (QB usable else 13.2 high-conf enriched) for context
NO_IND = {"", "not selected", "small business or individual", "extinct"}
_qci = []
_o = 0
while True:
    _b = sb.table("qb_customers").select("industry, industry_enriched, matched_company_id").eq(
        "client_id", C8).order("id").range(_o, _o + 999).execute().data or []
    _qci += _b
    if len(_b) < 1000:
        break
    _o += 1000
comp_ind = {}
for r in _qci:
    cid = r.get("matched_company_id")
    if not cid:
        continue
    qbi = (r.get("industry") or "").strip()
    if qbi and qbi.lower() not in NO_IND:
        comp_ind[cid] = qbi
    elif r.get("industry_enriched") and cid not in comp_ind:
        comp_ind[cid] = r["industry_enriched"].strip()

# association rules over the cello-fixed >=2-job baskets
basket2 = {cid: set(c["caps2"]) for cid, c in comp.items() if c["caps2"]}
ALL = sorted({k for b in basket2.values() for k in b})
N = len(basket2)
cc = Counter(); pair = defaultdict(int)
for b in basket2.values():
    for x in b:
        cc[x] += 1
    for x in b:
        for y in b:
            if x != y:
                pair[(x, y)] += 1
rules = {}
for X in ALL:
    for Y in ALL:
        if X == Y:
            continue
        both = pair.get((X, Y), 0)
        if both < SUPPORT_FLOOR or not cc[X] or not cc[Y]:
            continue
        conf = both / cc[X]; lift = conf / (cc[Y] / N)
        if lift >= LIFT_FLOOR:
            rules[(X, Y)] = {"support": both, "confidence": round(conf, 4), "lift": round(lift, 3)}


def all_cands(cid):
    """All genuine-0-order-gap candidates for a company, best rule per gap, sorted by score desc."""
    b = set(comp[cid]["caps2"]); anyset = comp[cid]["any"]; emb = comp[cid]["emb"]
    out = []
    for Y in ALL:
        if Y in b or Y in anyset:
            continue
        if Y == "Embellishment" and emb >= EMB_FINISH_FLOOR:
            continue
        best = None
        for X in b:
            r = rules.get((X, Y))
            if not r or r["confidence"] < CONF_FLOOR or r["support"] < SUPPORT_FLOOR:
                continue
            sc = r["confidence"] * r["lift"]
            if best is None or sc > best["score"]:
                best = {"Y": Y, "X": X, "score": sc, **r}
        if best:
            out.append(best)
    return sorted(out, key=lambda c: -c["score"])


def best_candidate(cid):
    c = all_cands(cid)
    return c[0] if c else None


# ── INDUSTRY-FIT FILTER (same spec as the deck, Task 13.3) ──
_assess = json.load(open(os.path.join(HERE, "industry_data_assessment.json"), encoding="utf-8"))
PROFILES = {ind: v["pct"] for ind, v in _assess["buying_mix"].items()}
if "Print Industry / Broker / Supplier" not in PROFILES and "Trade Printers" in PROFILES:
    PROFILES["Print Industry / Broker / Supplier"] = PROFILES["Trade Printers"]
DISCRIMINATING = {"Hard Cover Books", "Embellishment", "Wide Format"}
UNIVERSAL = {"Flat Sheets", "Specialty Finishing", "Design Services"}
FIT_HI, FIT_LO = 20, 10
_FIT_TIER = {"fits": 0, "universal": 1, "neutral": 1, "no_industry": 1, "suppress": 2}


def fit_status(industry, cap):
    if cap in UNIVERSAL:
        return "universal", None
    if cap not in DISCRIMINATING:
        return "neutral", None
    if not industry:
        return "no_industry", None
    prof = PROFILES.get(industry)
    if not prof or prof.get(cap) is None:
        return "neutral", None
    rate = prof[cap]
    return ("fits" if rate >= FIT_HI else "suppress" if rate < FIT_LO else "neutral"), rate


def filtered_candidate(cid):
    """Returns (kept_gap|None, raw_best, suppressed_info). kept=None means every gap is
    industry-implausible for this account (raw best existed but was suppressed with no alternative)."""
    cands = all_cands(cid)
    if not cands:
        return None, None, None
    industry = comp_ind.get(cid)
    for c in cands:
        c["fit_status"], c["fit_rate"] = fit_status(industry, c["Y"])
    raw_best = cands[0]
    if not industry:
        return raw_best, raw_best, None
    ranked = sorted(cands, key=lambda c: (_FIT_TIER[c["fit_status"]], -c["score"]))
    kept = ranked[0]
    if kept["fit_status"] == "suppress":
        return None, raw_best, {"cap": kept["Y"], "rate": kept["fit_rate"], "industry": industry}
    return kept, raw_best, None


# names (paginate - customer_companies is ~15k rows, default cap is 1000)
names = {}
_off = 0
while True:
    _b = sb.table("customer_companies").select("id, company_name").eq("client_id", C8)\
        .order("id").range(_off, _off + 999).execute().data or []
    for r in _b:
        names[r["id"]] = r.get("company_name") or ""
    if len(_b) < 1000:
        break
    _off += 1000
JUNK = re.compile(r"cash account|cash sale|sundry|walk[- ]?in|miscellaneous|\bmisc\b|internal|no customer|"
                  r"test account|carbon8|^delivery$|freight|postage|courier|^general|on account|^samples?$", re.I)

# rank by trailing-12mo revenue, drop junk buckets, take top N with a real basket
ranked = sorted((cid for cid in comp if comp[cid]["caps2"] and not JUNK.search(names.get(cid, ""))),
                key=lambda cid: -comp[cid]["rev12"])[:TOPN]

PRODUCTS = {"Flat Sheets", "Soft Cover Books", "Hard Cover Books", "Wide Format", "Display/Installation", "Embellishment"}
big = []
dropped = []   # accounts whose raw gap was suppressed as industry-implausible
changed = []   # accounts whose surfaced gap shifted to a fitting alternative
for cid in ranked:
    c = comp[cid]
    kept, raw_best, supp = filtered_candidate(cid)
    basket = sorted(c["caps2"])
    nprod = len(set(basket) & PRODUCTS)
    ind = comp_ind.get(cid, "(none)")
    fit_note = None
    if kept:
        status = "has-real-gap"
        fs, fr = kept.get("fit_status"), kept.get("fit_rate")
        fit_note = (f"fits {ind} ({fr}%)" if fs == "fits" else
                    f"neutral for {ind}" + (f" ({fr}%)" if fr is not None else "") if fs in ("neutral", "universal") else
                    "no industry on file")
        pitch = f"{kept['Y']} ({int(kept['confidence']*100)}% via {kept['X']}, lift {kept['lift']}, n={kept['support']})"
        if raw_best and raw_best["Y"] != kept["Y"]:
            changed.append((names.get(cid) or cid, ind, raw_best["Y"], kept["Y"]))
    elif raw_best and supp:
        # had a statistical gap, but it's industry-implausible -> not an opportunity
        status = "gap-suppressed"
        pitch = (f"{supp['cap']} suggested by the numbers but {supp['industry']} firms buy it only "
                 f"{supp['rate']}% (<{FIT_LO}%) — set aside, not an industry-appropriate gap")
        dropped.append({"customer": names.get(cid) or cid, "am": c["am"], "rev_12mo": round(c["rev12"]),
                        "industry": ind, "suppressed_gap": supp["cap"], "industry_buy_rate_pct": supp["rate"]})
    elif nprod >= 5:
        status, pitch = "saturated", "buys the full predicted product set - no meaningful gap"
    else:
        status, pitch = "retention-focus", "no rule clears the floor over a 0-order gap - retention/reorder"
    big.append({"customer": names.get(cid) or cid, "company_id": cid, "rev_12mo": round(c["rev12"]),
                "am": c["am"], "industry": ind, "n_caps": len(basket), "n_products": nprod, "basket": basket,
                "status": status, "pitch": pitch, "industry_fit": fit_note})

cnt = Counter(b["status"] for b in big)
# OPPORTUNITY SURFACING (13.8): big accounts with a REAL post-correction gap — the rank-50 deck
# cutoff hides these (they rank by gap strength x log-revenue, so a saturated whale outranks a
# big account whose single gap is lower-confidence). Surface them per AM.
opportunities = [b for b in big if b["status"] == "has-real-gap"]
opportunities.sort(key=lambda b: -b["rev_12mo"])

by_am = defaultdict(lambda: {"accounts": 0, "rev": 0, "has_gap": 0, "saturated": 0, "retention": 0})
for b in big:
    a = by_am[b["am"]]
    a["accounts"] += 1; a["rev"] += b["rev_12mo"]
    a["has_gap"] += b["status"] == "has-real-gap"
    a["saturated"] += b["status"] == "saturated"
    a["retention"] += b["status"] == "retention-focus"

print("\n" + "=" * 110)
print(f"BIG ACCOUNTS — top {len(big)} by trailing-12-month revenue (post-13.7 clean caps). Per AM + opportunity-surfacing.")
print("=" * 110)
print(f"  status mix: " + " | ".join(f"{k} {v}" for k, v in cnt.most_common()))
print(f"\n  per-AM split of the top {len(big)}:")
print(f"     {'AM':<20}{'accts':>6}{'12mo rev':>13}{'has-gap':>9}{'saturated':>11}{'retention':>11}")
for am, a in sorted(by_am.items(), key=lambda kv: -kv[1]["rev"]):
    print(f"     {am[:19]:<20}{a['accounts']:>6}${a['rev']:>11,}{a['has_gap']:>9}{a['saturated']:>11}{a['retention']:>11}")

# industry-fit survive/drop on the gaps (raw best existed)
n_raw_gap = len(opportunities) + len(dropped)
print(f"\n  INDUSTRY-FIT on big-account gaps: {n_raw_gap} accounts had a statistical gap -> "
      f"{len(opportunities)} survive (industry-appropriate), {len(dropped)} DROPPED (implausible), "
      f"{len(changed)} shifted to a better-fitting gap.")
if dropped:
    print(f"\n  DROPPED — gap suppressed as industry-implausible (confirm each is genuinely a poor fit):")
    print(f"     {'customer':<32}{'AM':<14}{'12mo rev':>11}  {'industry':<22} suppressed gap (industry buy-rate)")
    print("     " + "-" * 104)
    for b in sorted(dropped, key=lambda x: -x["rev_12mo"]):
        print(f"     {b['customer'][:31]:<32}{b['am'][:13]:<14}${b['rev_12mo']:>10,}  {b['industry'][:21]:<22} "
              f"{b['suppressed_gap']} ({b['industry_buy_rate_pct']}%)")
if changed:
    print(f"\n  SHIFTED — surfaced gap changed to a better-fitting alternative:")
    for cust, ind, raw, kept in sorted(changed, key=lambda x: x[0])[:15]:
        print(f"     {cust[:31]:<32} [{ind[:20]:<21}] {raw} -> {kept}")

print(f"\n  OPPORTUNITY-SURFACING — {len(opportunities)} big accounts with an industry-appropriate gap "
      f"the deck cutoff may hide:")
print(f"     {'customer':<32}{'AM':<14}{'12mo rev':>11}  {'industry':<22} gap")
print("     " + "-" * 100)
for b in opportunities[:30]:
    print(f"     {b['customer'][:31]:<32}{b['am'][:13]:<14}${b['rev_12mo']:>10,}  {b['industry'][:21]:<22} {b['pitch'][:34]}")

json.dump({"generated": "2026-06-14", "trailing_12mo_since": CUT, "top_n": len(big),
           "status_mix": dict(cnt),
           "industry_fit_on_gaps": {"raw_gap_accounts": n_raw_gap, "survived": len(opportunities),
                                    "dropped_implausible": len(dropped), "shifted_to_better_fit": len(changed)},
           "dropped_implausible_gaps": sorted(dropped, key=lambda x: -x["rev_12mo"]),
           "shifted_gaps": [{"customer": c, "industry": i, "raw_gap": r, "fitting_gap": k} for c, i, r, k in changed],
           "per_am": {am: a for am, a in sorted(by_am.items(), key=lambda kv: -kv[1]["rev"])},
           "opportunities_big_with_gap": opportunities,
           "accounts": big},
          open(os.path.join(HERE, "big_accounts.json"), "w", encoding="utf-8"), indent=2, default=str)
ddl("NOTIFY pgrst,'reload schema'")
print("\nJSON -> scripts/db/big_accounts.json")
