"""
THROWAWAY analysis (11.1) — Next-Best-Outreach CARDS for 50 customers.

Read-only. QB (operations + quotes) is ground truth. Email pull is METADATA ONLY
(no body_text egress; DATA_ANALYSIS_GUIDELINES §7). Pool email pull is CACHED to a
local JSON so re-ranking is free (re-run with FORCE_EMAIL=1 to refresh).

DIFFERS from the earlier _outreach_prospects_50.py (which took top-50-BY-REVENUE):
  * Selection universe = ALL customers, ranked by OPPORTUNITY STRENGTH, take top 50,
    so a small high-confidence well-timed account can beat a big saturated one.
  * Candidate pitch picked by  confidence x lift  (not lift alone).
  * Timing = PERCENTILE-OF-OWN-GAPS (p50/p90 of the gaps between the customer's own ordering
    OCCASIONS — orders within BURST_DAYS collapsed into one occasion), not avg-interval. This
    matches the per-AM docs' cadence (_gen_am_docs_v2) so the deck's timing-driven ranking and the
    rep-facing reorder rhythm agree: several jobs in the same fortnight no longer read as a tiny
    median ("reorders every 4 days").
  * Gap is CONFIRMED at company grain = ZERO jobs in the pitched capability under the
    corrected qb-OR-classifier definition (caps_any, jobs>=1). The >=2-job basket
    threshold is only for rule-mining noise suppression; a 1-job cap is NOT a clean gap
    (this is the capability-tag bug the guidelines warn about — err toward "already has").
  * Output = two-sided cards {front, back} -> scripts/db/outreach_cards_50.json.

OPPORTUNITY STRENGTH = base x rev_weight x timing_factor
  base         = confidence x lift  (candidate-bearing) | RET_CONST (retention/no-gap)
  rev_weight   = log10(max(revenue,10))   <-- DAMPENED revenue. The spec literally says
                 "x customer revenue", but raw revenue (1000x dynamic range) swamps
                 conf/lift/timing (~10x) and collapses the ranking back to top-50-by-
                 revenue, defeating the stated "small but potent" goal. log10 lets the
                 other factors actually move the ranking. RAW revenue + all four factors
                 are stored on every card, so a raw-revenue re-rank is one re-sort away.
  timing_factor= rhythm(p50/p90) x seasonal x email-recency

HONESTY GUARDS (baked in):
  - Confidence stated as the real % (never rounded up / relabelled).
  - Pitched product verified as a genuine 0-order gap (qb-OR-classifier, company grain).
  - Deferred QB-conflict companies flagged; cards on them marked data_quality.
  - No archetype / no AM comparison / no scorecard in any output field.
"""
import os, sys, io, re, json, time, math, statistics
from collections import defaultdict
from datetime import date, datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
from dotenv import load_dotenv
from supabase import create_client

HERE = os.path.dirname(__file__)
env_path = os.path.join(HERE, "..", "..", "backend", ".env.production")
if not os.path.exists(env_path):
    env_path = os.path.join(HERE, "..", "..", "backend", ".env")
load_dotenv(env_path)
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
CARBON8 = "241d7b99-f099-4557-96e5-212c4af10812"

PAGE = 1000
TOPN = 50
POOL = 120                  # email-ground this many top-prelim companies, then re-rank to 50
WIN = 14
TODAY = date(2026, 6, 15)
MONTH_NAMES = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

SUPPORT_FLOOR = 30          # a pitch needs >=30 customers backing the rule (spec floor)
CONF_FLOOR = 0.25           # AND >=25% confidence (spec floor)
LIFT_FLOOR = 1.0            # positive association only
EMB_FINISH_FLOOR = 2        # suppress a standalone-Embellishment pitch if the company already
                            # applies >=2 embellishment FINISH jobs (qb_embellishment_tag: Hot Foil,
                            # Spot UV, Deboss/Emboss...). The Geoff Letchford trap — capability=
                            # Embellishment can be 0 while finishes-within-jobs are not. 1 finish job
                            # is thin evidence, so the floor is 2 (validated 2026-06-11).
RET_CONST = 0.30            # retention base for no-gap accounts (< a typical conf*lift ~0.45)
STALE_CONTACT_DAYS = 90     # value contact flagged "confirm contact" if last active > this
DORMANT_DAYS = 365
BURST_DAYS = 14             # orders within this many days collapse into ONE ordering occasion (a
                            # "project") for the reorder-cadence p50/p90, so several jobs in the same
                            # fortnight don't read as "reorders every 4 days". Must match the value in
                            # scripts/db/_gen_am_docs_v2.py (which reads the cadence back off these cards).
EMAIL_CACHE = os.path.join(HERE, "_outreach_cards_email_cache.json")
FORCE_EMAIL = os.environ.get("FORCE_EMAIL") == "1"

# Deferred QB-conflict company names (normalized) — flag, don't build clean cards on these.
CONFLICT_NORMS = {
    "melhuishco": "unresolved", "regroup": "unresolved",
    "cocogun": "unresolved", "azbcreative": "unresolved",
    "louisvuitton": "resolved_2026-06-08", "themakehaus": "resolved_2026-06-08",
}


def _client():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


def with_retry(build, tries=5):
    global sb
    for i in range(tries):
        try:
            return build()
        except Exception as e:
            if i == tries - 1:
                raise
            print(f"    retry {i+1} after {type(e).__name__}; recreate client", flush=True)
            time.sleep(2 * (i + 1))
            sb = _client()


def fetch_all(table, select, filters, page=PAGE):
    rows, off = [], 0
    while True:
        def build():
            q = sb.table(table).select(select)
            for fn in filters:
                q = fn(q)
            return q.order("id").range(off, off + page - 1).execute()
        b = with_retry(build).data or []
        rows.extend(b)
        if len(b) < page:
            break
        off += page
    return rows


def fnum(v):
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def parse_dt(s):
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo:
        d = d.astimezone(timezone.utc).replace(tzinfo=None)
    return d


def parse_date(s):
    dt = parse_dt(s)
    return dt.date() if dt else None


def emails_in(jsonb_list):
    out = []
    for x in (jsonb_list or []):
        if isinstance(x, dict):
            e = (x.get("email") or "").strip().lower()
            if e:
                out.append(e)
        elif isinstance(x, str):
            out.append(x.strip().lower())
    return out


def norm(e):
    return (e or "").strip().lower()


def normname(s):
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def normcap(c):
    # collapse the "Display / Installation" vs "Display/Installation" spelling variant
    return re.sub(r"\s*/\s*", "/", (c or "").strip())


def exec_sql(q):
    return with_retry(lambda: sb.rpc("exec_sql", {"query": q}).execute())


# ════════════════════════════ RPCs (server-side aggregation) ═══════════════
# Capability per op = the CORRECTED classifier output, read straight from the live
# capability_tags column via the caps_for_op precedence (Task 13.7): classifier tag
# first, qb_capability_tag fills gaps only when the classifier is silent. The old inline
# CORRECTION-3 / cello re-derivation is REMOVED — capability_tags is already clean
# (the Layer-1 classifier is the single source of truth; the deck must not re-derive its
# own correction or it drifts from the platform).
CAP_LATERAL = """
  CROSS JOIN LATERAL (
    SELECT CASE
      WHEN jsonb_typeof(o.capability_tags) = 'array' AND jsonb_array_length(o.capability_tags) > 0
        THEN o.capability_tags
      WHEN btrim(coalesce(o.qb_capability_tag,'')) <> '' THEN jsonb_build_array(btrim(o.qb_capability_tag))
      ELSE '[]'::jsonb END AS capsj
  ) d
  CROSS JOIN LATERAL jsonb_array_elements_text(d.capsj) AS u0(cap0)
  CROSS JOIN LATERAL (SELECT btrim(u0.cap0) AS cap) u
"""

RPC_BASKET = f"""
CREATE OR REPLACE FUNCTION _tmp_card_basket(p_client uuid)
RETURNS jsonb LANGUAGE sql STABLE
SET search_path = public SET statement_timeout = '240s' AS $fn$
WITH base AS (
  SELECT o.matched_company_id cid, btrim(u.cap) cap, o.job_no, o.cost_plus_price
  FROM qb_operations o
  {CAP_LATERAL}
  WHERE o.client_id = p_client AND o.matched_company_id IS NOT NULL
    AND length(btrim(u.cap)) > 1
),
percap AS (
  SELECT cid, cap, count(DISTINCT job_no) jobs,
         round(coalesce(sum(cost_plus_price),0)::numeric,2) rev
  FROM base GROUP BY cid, cap
),
basket AS (   -- jobs>=2 : rule-mining basket (noise-suppressed)
  SELECT cid,
         jsonb_agg(jsonb_build_object('cap',cap,'jobs',jobs,'rev',rev) ORDER BY rev DESC) caps,
         sum(rev) total_rev
  FROM percap WHERE jobs >= 2 GROUP BY cid
),
anyc AS (     -- jobs>=1 : genuine-gap confirmation set (a 1-job cap is NOT a clean gap)
  SELECT cid, jsonb_object_agg(cap, jobs) caps_any
  FROM percap WHERE jobs >= 1 GROUP BY cid
),
embj AS (     -- signal-3 finishes: distinct jobs with a qb_embellishment_tag (op-level, not the cap unnest)
  SELECT o.matched_company_id cid, count(DISTINCT o.job_no) emb_jobs
  FROM qb_operations o
  WHERE o.client_id = p_client AND o.matched_company_id IS NOT NULL
    AND btrim(coalesce(o.qb_embellishment_tag,'')) <> ''
  GROUP BY o.matched_company_id
)
SELECT coalesce(jsonb_agg(jsonb_build_object(
  'cid', b.cid, 'total_rev', b.total_rev, 'caps', b.caps,
  'caps_any', a.caps_any, 'emb_jobs', coalesce(e.emb_jobs, 0))), '[]'::jsonb)
FROM basket b JOIN anyc a USING (cid) LEFT JOIN embj e ON e.cid = b.cid;
$fn$;
"""

# Per-company order RHYTHM over ALL companies. Cadence (p50/p90) is measured on ORDERING OCCASIONS,
# not raw order dates: orders within BURST_DAYS of each other collapse into one occasion (a project),
# and p50/p90 are the percentiles of the gaps BETWEEN occasions. This is the same occasion collapse
# the per-AM docs use (_gen_am_docs_v2._tmp_cadence) — so a customer who placed several jobs in one
# fortnight reads as a real reorder rhythm, not "every 4 days", and the timing rhythm factor that
# drives the deck ranking agrees with the rep-facing line. first/last/n_orders and the monthly
# seasonality histogram stay on the RAW distinct order dates (days-since-last is the actual last order).
RPC_GAPS = f"""
CREATE OR REPLACE FUNCTION _tmp_card_gaps(p_client uuid)
RETURNS jsonb LANGUAGE sql STABLE
SET search_path = public SET statement_timeout = '240s' AS $fn$
WITH dates AS (
  SELECT DISTINCT o.matched_company_id cid, o.date_accepted d
  FROM qb_operations o
  WHERE o.client_id = p_client AND o.matched_company_id IS NOT NULL
    AND o.date_accepted IS NOT NULL
),
mk AS (   -- 1 marks the first order of a new occasion: the very first, or a gap > BURST_DAYS
  SELECT cid, d,
         CASE WHEN lag(d) OVER (PARTITION BY cid ORDER BY d) IS NULL
                   OR d - lag(d) OVER (PARTITION BY cid ORDER BY d) > {BURST_DAYS}
              THEN 1 ELSE 0 END AS newocc
  FROM dates
),
occ AS (   -- running occasion id per company
  SELECT cid, d, sum(newocc) OVER (PARTITION BY cid ORDER BY d) AS oid FROM mk
),
occd AS (  -- one row per occasion, dated by its first order
  SELECT cid, oid, min(d) AS odt FROM occ GROUP BY cid, oid
),
ogaps AS ( -- gap to the previous occasion (same-fortnight bursts collapsed); NULL for the first
  SELECT cid, (odt - lag(odt) OVER (PARTITION BY cid ORDER BY odt)) AS gap FROM occd
),
monthly AS (
  SELECT cid, extract(month from d)::int mo, count(*) c FROM dates GROUP BY cid, mo
),
meta AS (  -- raw-date facts: distinct order count + actual first/last order
  SELECT cid, count(*) n_orders, min(d) first_d, max(d) last_d FROM dates GROUP BY cid
),
agg AS (   -- occasion-based cadence
  SELECT cid,
         count(*) n_occ,
         percentile_cont(0.5) WITHIN GROUP (ORDER BY gap) p50,
         percentile_cont(0.9) WITHIN GROUP (ORDER BY gap) p90
  FROM ogaps GROUP BY cid
)
SELECT coalesce(jsonb_agg(jsonb_build_object(
  'cid', m.cid, 'n_orders', m.n_orders, 'n_occ', a.n_occ,
  'first', m.first_d, 'last', m.last_d, 'p50', a.p50, 'p90', a.p90,
  'monthly', (SELECT jsonb_object_agg(mo, c) FROM monthly mm WHERE mm.cid = m.cid))), '[]'::jsonb)
FROM meta m JOIN agg a USING (cid);
$fn$;
"""

# Per-(company,capability) last order date + jobs, POOL only — for "last ordered product".
RPC_LASTCAP = f"""
CREATE OR REPLACE FUNCTION _tmp_card_lastcap(p_client uuid, p_cids uuid[])
RETURNS jsonb LANGUAGE sql STABLE
SET search_path = public SET statement_timeout = '120s' AS $fn$
WITH base AS (
  SELECT o.matched_company_id cid, btrim(u.cap) cap, o.job_no, o.date_accepted
  FROM qb_operations o
  {CAP_LATERAL}
  WHERE o.client_id = p_client AND o.matched_company_id = ANY(p_cids)
    AND o.date_accepted IS NOT NULL AND length(btrim(u.cap)) > 1
)
SELECT coalesce(jsonb_agg(jsonb_build_object(
  'cid', cid, 'cap', cap, 'maxdate', maxdate, 'jobs', jobs)), '[]'::jsonb)
FROM (
  SELECT cid, cap, max(date_accepted) maxdate, count(DISTINCT job_no) jobs
  FROM base GROUP BY cid, cap
) t;
$fn$;
"""

print("Creating throwaway aggregation RPCs...", flush=True)
exec_sql(RPC_BASKET)
exec_sql(RPC_GAPS)
exec_sql(RPC_LASTCAP)
exec_sql("NOTIFY pgrst, 'reload schema'")
time.sleep(3)

# ════════════════════════════ PART 1: basket + rules (full base) ═══════════
print("Calling _tmp_card_basket (full base)...", flush=True)
basket_json = with_retry(lambda: sb.rpc("_tmp_card_basket", {"p_client": CARBON8}).execute()).data or []
print(f"  companies with a rule-eligible basket: {len(basket_json)}", flush=True)

comp_caps = {}      # cid -> {cap: {jobs,rev}}   (jobs>=2 basket)
comp_any = {}       # cid -> {cap: jobs}          (jobs>=1, for gap confirmation)
comp_rev = {}       # cid -> total revenue
comp_emb_finish = {}  # cid -> distinct jobs with a qb_embellishment_tag finish (signal 3)
for row in basket_json:
    cid = row["cid"]
    caps = {}
    for c in (row.get("caps") or []):
        cap = normcap(c["cap"])
        e = caps.setdefault(cap, {"jobs": 0, "rev": 0.0})
        e["jobs"] += int(c["jobs"]); e["rev"] += fnum(c["rev"])
    comp_caps[cid] = caps
    anyc = {}
    for cap, jobs in (row.get("caps_any") or {}).items():
        anyc[normcap(cap)] = anyc.get(normcap(cap), 0) + int(jobs)
    comp_any[cid] = anyc
    comp_rev[cid] = fnum(row.get("total_rev"))
    comp_emb_finish[cid] = int(row.get("emb_jobs") or 0)

ALL_CAPS = sorted({cap for caps in comp_caps.values() for cap in caps})
N = len(comp_caps)
cap_count = {c: 0 for c in ALL_CAPS}
pair_count = defaultdict(int)
for caps in comp_caps.values():
    present = list(caps)
    for c in present:
        cap_count[c] += 1
    for i in range(len(present)):
        for j in range(len(present)):
            if i != j:
                pair_count[(present[i], present[j])] += 1

rules = {}   # (X,Y) -> {support, confidence, lift, py}
for X in ALL_CAPS:
    for Y in ALL_CAPS:
        if X == Y:
            continue
        both = pair_count.get((X, Y), 0)
        if both < SUPPORT_FLOOR or cap_count[X] == 0 or cap_count[Y] == 0:
            continue
        conf = both / cap_count[X]
        lift = conf / (cap_count[Y] / N)
        if lift < LIFT_FLOOR:
            continue
        rules[(X, Y)] = {"support": both, "confidence": round(conf, 4),
                         "lift": round(lift, 3), "py": round(cap_count[Y] / N, 4)}

print(f"\n-- Capability base rates (of {N} customers with a basket) --")
for c in sorted(ALL_CAPS, key=lambda x: -cap_count[x]):
    print(f"   {c:<22} {cap_count[c]:>6}  ({cap_count[c]/N*100:4.1f}%)")
print(f"\n-- Rules kept (support>={SUPPORT_FLOOR}, lift>={LIFT_FLOOR}): {len(rules)} --")
for (X, Y), r in sorted(rules.items(), key=lambda kv: -(kv[1]["confidence"] * kv[1]["lift"]))[:20]:
    print(f"   {X:<18} -> {Y:<18} conf {r['confidence']:.3f}  lift {r['lift']:>5}  supp {r['support']:>4}")


def all_candidates(cid):
    """All viable genuine-0-order-gap pitches (best rule per gap cap), sorted by conf x lift desc."""
    basket = set(comp_caps[cid])
    anyset = comp_any.get(cid, {})
    emb_finish = comp_emb_finish.get(cid, 0)
    cands = []
    for Y in ALL_CAPS:
        if Y in basket:
            continue
        if anyset.get(Y, 0) > 0:          # genuine-gap guard: any job in Y -> not a clean gap
            continue
        if Y == "Embellishment" and emb_finish >= EMB_FINISH_FLOOR:
            continue                      # already applies finishes within jobs (Geoff Letchford trap)
        best = None
        for X in basket:
            r = rules.get((X, Y))
            if not r or r["confidence"] < CONF_FLOOR or r["support"] < SUPPORT_FLOOR:
                continue
            score = r["confidence"] * r["lift"]
            if best is None or score > best["score"]:
                best = {"capability": Y, "from": X, "score": score, **r}
        if best:
            cands.append(best)
    return sorted(cands, key=lambda c: -c["score"])


def best_candidate(cid):
    c = all_candidates(cid)
    return c[0] if c else None


# ════════════════════════════ INDUSTRY-FIT FILTER (Task 13.3) ══════════════
# Checks each statistically-suggested pitch against the customer's industry buying-profile.
# FILTER, not generative. Acts ONLY on the 3 DISCRIMINATING caps; the 3 UNIVERSAL caps carry
# no industry signal and are never filtered. Spec: docs/design/INDUSTRY_FIT_FILTER_DESIGN.md.
_assess = json.load(open(os.path.join(HERE, "industry_data_assessment.json"), encoding="utf-8"))
PROFILES = {ind: v["pct"] for ind, v in _assess["buying_mix"].items()}   # industry -> {cap: %buying}
if "Print Industry / Broker / Supplier" not in PROFILES and "Trade Printers" in PROFILES:
    PROFILES["Print Industry / Broker / Supplier"] = PROFILES["Trade Printers"]   # synonym/adjacency
DISCRIMINATING = {"Hard Cover Books", "Embellishment", "Wide Format"}
UNIVERSAL = {"Flat Sheets", "Specialty Finishing", "Design Services"}
FIT_HI, FIT_LO = 20, 10   # >=20% FITS, <10% SUPPRESS, 10-20% NEUTRAL (real gap in the data, not tuned)
NO_IND = {"", "not selected", "small business or individual", "extinct"}


def _ind_usable(s):
    return bool(s) and s.strip().lower() not in NO_IND


# company -> (industry, source): QB industry first, else 13.2 high-conf enriched, else skip filter
print("Loading industry (QB + 13.2 enriched) for the fit filter...", flush=True)
_qc_ind = fetch_all("qb_customers", "industry, industry_enriched, matched_company_id",
                    [lambda q: q.eq("client_id", CARBON8)])
comp_industry = {}
for r in _qc_ind:
    cid = r.get("matched_company_id")
    if not cid:
        continue
    cur = comp_industry.get(cid)
    if _ind_usable(r.get("industry")):
        comp_industry[cid] = (r["industry"].strip(), "qb")
    elif r.get("industry_enriched") and (not cur or cur[1] != "qb"):
        comp_industry[cid] = (r["industry_enriched"].strip(), "enriched")
print(f"  companies with a usable industry: {len(comp_industry)} "
      f"(QB {sum(1 for v in comp_industry.values() if v[1]=='qb')}, enriched {sum(1 for v in comp_industry.values() if v[1]=='enriched')})")


def fit_status(industry, cap):
    """('fits'|'suppress'|'neutral'|'universal'|'no_industry', rate)."""
    if cap in UNIVERSAL:
        return "universal", None
    if cap not in DISCRIMINATING:
        return "neutral", None             # Soft Cover / Display: no industry filter
    if not industry:
        return "no_industry", None
    prof = PROFILES.get(industry)
    if not prof:
        return "neutral", None
    rate = prof.get(cap)
    if rate is None:
        return "neutral", None
    if rate >= FIT_HI:
        return "fits", rate
    if rate < FIT_LO:
        return "suppress", rate
    return "neutral", rate


_FIT_TIER = {"fits": 0, "universal": 1, "neutral": 1, "no_industry": 1, "suppress": 2}


def filtered_pick(cid):
    """Industry-fit pick. Re-ranks the customer's candidate pitches fits > neutral > suppressed and
    RETAINS the demoted stats-#1 as the first-class 'Not pitched' line. GUARDRAIL: candidates are
    already genuine 0-order gaps (all_candidates), so a cap the customer already buys is never here —
    the filter shapes NEW pitches only. Returns {kept, suppressed, industry, industry_source, all}."""
    cands = all_candidates(cid)
    industry, source = comp_industry.get(cid, (None, None))
    for c in cands:
        c["fit_status"], c["fit_rate"] = fit_status(industry, c["capability"])
    if not cands:
        return {"kept": None, "suppressed": None, "industry": industry, "industry_source": source, "all": []}
    if not industry:
        # no industry claim either way (§10.13: a wrong suppression is worse than none) — clean stats pick
        return {"kept": cands[0], "suppressed": None, "industry": None, "industry_source": None, "all": cands}
    ranked = sorted(cands, key=lambda c: (_FIT_TIER[c["fit_status"]], -c["score"]))
    kept = ranked[0]
    top_by_score = cands[0]
    suppressed = top_by_score if (top_by_score is not kept and top_by_score["fit_status"] == "suppress") else None
    if kept["fit_status"] == "suppress":
        # every gap for this industry is implausible -> don't pitch one; fall to retention, surface the set-aside
        suppressed = kept
        kept = None
    return {"kept": kept, "suppressed": suppressed, "industry": industry, "industry_source": source, "all": cands}


# ════════════════════════════ PART 1.5: rhythm/timing (all companies) ═════
print("\nCalling _tmp_card_gaps (all companies, occasion-based cadence)...", flush=True)
gaps_json = with_retry(lambda: sb.rpc("_tmp_card_gaps", {"p_client": CARBON8}).execute()).data or []
comp_gap = {}     # cid -> {n_orders,n_occ,first,last,p50,p90,monthly}  (p50/p90 = occasion gaps)
for r in gaps_json:
    comp_gap[r["cid"]] = {
        "n_orders": int(r.get("n_orders") or 0),
        "n_occ": int(r.get("n_occ") or 0),
        "first": parse_date(r.get("first")), "last": parse_date(r.get("last")),
        "p50": fnum(r.get("p50")) if r.get("p50") is not None else None,
        "p90": fnum(r.get("p90")) if r.get("p90") is not None else None,
        "monthly": {int(k): int(v) for k, v in (r.get("monthly") or {}).items()},
    }


def seasonal(cid):
    """Approach-window seasonality from the company's monthly order histogram."""
    mh = comp_gap.get(cid, {}).get("monthly", {})
    if len(mh) < 3:
        return False, None, None
    vals = list(mh.values())
    mu = statistics.mean(vals)
    sd = statistics.stdev(vals) if len(vals) > 1 else 0
    thr = max(sd * 0.5, mu * 0.15)
    peaks = [m for m, v in mh.items() if v > mu + thr]
    if not peaks:
        return False, None, None
    appm = lambda pm: (pm - 1) if pm > 1 else 12
    peak = sorted(peaks, key=lambda pm: ((appm(pm) - TODAY.month) % 12))[0]
    am = appm(peak)
    return (am == TODAY.month), peak, am


def timing_for(cid, recency_factor=None):
    """percentile-of-own-gaps window label + factor. recency_factor None => prelim (no email)."""
    g = comp_gap.get(cid)
    is_app, peak, am = seasonal(cid)
    out = {"label": "no strong timing signal", "status": "unknown", "rhythm_factor": 1.0,
           "days_since_last": None, "p50": None, "p90": None, "last_order": None,
           "n_orders": g["n_orders"] if g else 0, "n_occasions": g["n_occ"] if g else 0,
           "approaching": False,
           "peak_month": peak, "approach_month": am, "math": "no order-date history"}
    if not g or not g["last"]:
        rf = 1.0
    else:
        days = (TODAY - g["last"]).days
        p50, p90 = g["p50"], g["p90"]
        out.update({"days_since_last": days, "p50": round(p50) if p50 is not None else None,
                    "p90": round(p90) if p90 is not None else None,
                    "last_order": g["last"].isoformat()})
        if days > DORMANT_DAYS:
            out["status"], rf = "dormant", 0.55
            out["label"] = f"dormant — last order {days}d (~{days/365:.1f}y) ago; reactivation, not a warm reorder"
            out["math"] = f"days_since={days} > {DORMANT_DAYS} (1y)"
        elif p90 is not None and days >= p90:
            out["status"], rf = "overdue", 1.3
            out["label"] = f"overdue — {days}d since last order vs p90 gap {round(p90)}d"
            out["math"] = f"days_since={days} >= p90={round(p90)}d (over 90% of own gaps)"
        elif p50 is not None and days >= p50:
            out["status"], rf = "due_soon", 1.15
            out["label"] = f"due soon — {days}d since last order vs p50 gap {round(p50)}d"
            out["math"] = f"p50={round(p50)}d <= days_since={days} < p90={round(p90) if p90 else '—'}d"
        elif p50 is not None:
            out["status"], rf = "in_cadence", 1.0
            out["label"] = f"in cadence — {days}d since last order, under p50 gap {round(p50)}d; no strong reorder signal"
            out["math"] = f"days_since={days} < p50={round(p50)}d"
        else:
            out["status"], rf = "single_occasion", 1.0
            if g["n_orders"] > 1:
                out["label"] = (f"single ordering occasion on record ({days}d ago), "
                                f"{g['n_orders']} orders clustered within {BURST_DAYS}d — no reorder rhythm to read")
            else:
                out["label"] = f"single order on record ({days}d ago) — no cadence to read"
            out["math"] = f"n_orders={g['n_orders']}, n_occasions={g['n_occ']}, no inter-occasion gap"
    out["approaching"] = bool(is_app and out["status"] != "dormant")
    seas_mult = 1.15 if out["approaching"] else 1.0
    if out["approaching"]:
        out["label"] += f"; approaching {MONTH_NAMES[peak]} seasonal peak"
    out["rhythm_factor"] = rf
    rec = recency_factor if recency_factor is not None else 1.0
    out["timing_factor"] = round(rf * seas_mult * rec, 4)
    return out


def revenue_weight(rev):
    return math.log10(max(rev, 10))


# ════════════════════════════ PART 2: prelim opp + pool selection ═════════
def opp_strength(base, rev, tf):
    return round(base * revenue_weight(rev) * tf, 4)


# names (for conflict flag + labels) + EXCLUDE internal/cash-sale/test buckets from the deck entirely
# (same JUNK filter the big-accounts engine uses). Without this an internal bucket like
# "Cash Account - Kenneth" surfaces as a rep-facing outreach card.
name_rows = fetch_all("customer_companies", "id, company_name",
                      [lambda q: q.eq("client_id", CARBON8)])
cid_name = {r["id"]: (r.get("company_name") or "") for r in name_rows}
JUNK = re.compile(r"cash account|cash sale|sundry|walk[- ]?in|miscellaneous|\bmisc\b|internal|no customer|"
                  r"test account|carbon8|^delivery$|freight|postage|courier|^general|on account|^samples?$", re.I)
JUNK_CIDS = {cid for cid in comp_caps if JUNK.search(cid_name.get(cid, ""))}
if JUNK_CIDS:
    print(f"Excluding {len(JUNK_CIDS)} internal/cash/test companies from the deck: "
          f"{sorted(cid_name.get(c) for c in JUNK_CIDS)[:8]}", flush=True)

prelim = []
for cid in comp_caps:
    if cid in JUNK_CIDS:
        continue
    rev = comp_rev[cid]
    cand = filtered_pick(cid)["kept"]             # industry-fit pick drives pool selection
    tm = timing_for(cid)                          # prelim: no recency
    base = (cand["confidence"] * cand["lift"]) if cand else RET_CONST
    prelim.append((cid, opp_strength(base, rev, tm["timing_factor"]), cand))
prelim.sort(key=lambda x: -x[1])
pool_cids = [cid for cid, _, _ in prelim[:POOL]]
print(f"\nPrelim ranking done over {len(prelim)} companies. Email-grounding top {len(pool_cids)}.", flush=True)

# QB customer key map for pool (for quote linkage / value contact)
qbcust = fetch_all("qb_customers", "matched_company_id, customer_key_id",
                   [lambda q: q.eq("client_id", CARBON8),
                    lambda q, p=pool_cids: q.in_("matched_company_id", p)])
key_to_cid = {}
for r in qbcust:
    cid, k = r.get("matched_company_id"), r.get("customer_key_id")
    if cid and k:
        key_to_cid[str(k)] = cid
keys = list(key_to_cid)

# quotes for those keys (value contact + strike)
print(f"Pulling quotes for {len(keys)} customer keys...", flush=True)
qrows = []
for i in range(0, len(keys), 50):
    chunk = keys[i:i + 50]
    qrows += fetch_all("qb_quotes",
                       "quote_no, sell_ex_tax, date_created, has_job, job_no, contact_email, contact_name, qb_customer_id",
                       [lambda q: q.eq("client_id", CARBON8),
                        lambda q, ch=chunk: q.in_("qb_customer_id", ch)])
cid_quotes = defaultdict(dict)
contact_name = {}
for r in qrows:
    cid = key_to_cid.get(str(r.get("qb_customer_id")))
    qno = r.get("quote_no")
    if not cid or not qno:
        continue
    e = cid_quotes[cid].setdefault(qno, {"won": False, "value": 0.0, "email": None})
    if r.get("has_job") or r.get("job_no"):
        e["won"] = True
    e["value"] = max(e["value"], fnum(r.get("sell_ex_tax")))
    ce = norm(r.get("contact_email"))
    if ce:
        e["email"] = e["email"] or ce
        if r.get("contact_name") and ce not in contact_name:
            contact_name[ce] = r["contact_name"]

# last-ordered capability per pool company
lastcap_json = with_retry(lambda: sb.rpc("_tmp_card_lastcap",
                          {"p_client": CARBON8, "p_cids": pool_cids}).execute()).data or []
comp_lastcap = defaultdict(list)
for r in lastcap_json:
    md = parse_date(r.get("maxdate"))
    if md:
        comp_lastcap[r["cid"]].append((normcap(r["cap"]), md, int(r.get("jobs") or 0)))

# ── email metadata for pool (the main read) — cached ───────────────────────
cache_emails = {}   # cid -> list of email rows (incremental; pool shifts across runs)
if os.path.exists(EMAIL_CACHE) and not FORCE_EMAIL:
    try:
        cache_emails = json.load(open(EMAIL_CACHE, encoding="utf-8")).get("emails", {})
    except (ValueError, OSError):
        cache_emails = {}
missing = [cid for cid in pool_cids if cid not in cache_emails]
if missing:
    print(f"Pulling email metadata for {len(missing)} uncached pool companies (main read)...", flush=True)
    new_rows = []
    for i in range(0, len(missing), 50):
        chunk = missing[i:i + 50]
        new_rows += fetch_all("emails",
                              "id, customer_company_id, sender_email, recipients, cc_list, sent_date, is_outbound",
                              [lambda q: q.eq("client_id", CARBON8),
                               lambda q, ch=chunk: q.in_("customer_company_id", ch)])
    for cid in missing:
        cache_emails.setdefault(cid, [])    # mark pulled-but-empty so we don't re-pull
    for e in new_rows:
        cache_emails.setdefault(e.get("customer_company_id"), []).append(e)
    json.dump({"emails": cache_emails}, open(EMAIL_CACHE, "w", encoding="utf-8"), default=str)
    print(f"  pulled {len(new_rows)} rows; cache now covers {len(cache_emails)} companies", flush=True)
else:
    print("Using cached pool email metadata (all pool companies cached).", flush=True)
erows = [e for cid in pool_cids for e in cache_emails.get(cid, [])]
print(f"  emails available for pool: {len(erows)}", flush=True)

comp_emails = defaultdict(list)
for e in erows:
    dt = parse_dt(e.get("sent_date"))
    if not dt:
        continue
    outb = bool(e.get("is_outbound"))
    if outb:
        parts = set(emails_in(e.get("recipients")) + emails_in(e.get("cc_list")))
    else:
        s = norm(e.get("sender_email"))
        parts = {s} if s else set()
    comp_emails[e.get("customer_company_id")].append({"dt": dt, "out": outb, "parts": parts})


def ground_company(cid):
    recs = sorted(comp_emails.get(cid, []), key=lambda r: r["dt"])
    cidx = defaultdict(list)
    for i, r in enumerate(recs):
        for p in r["parts"]:
            cidx[p].append(i)
    last_email = recs[-1]["dt"].date() if recs else None
    dse = (TODAY - last_email).days if last_email else None

    def engagement(em):
        idxs = cidx.get(em, [])
        frm = sum(1 for i in idxs if not recs[i]["out"])      # inbound from contact
        to = sum(1 for i in idxs if recs[i]["out"])
        last_active = max((recs[i]["dt"].date() for i in idxs), default=None)
        # genuine two-way needs BOTH directions present (not just high inbound volume):
        # a contact who only ever emails us — to=0 — is one-directional, not engaged.
        two_way = frm >= 3 and to >= 3
        return frm, to, two_way, last_active

    # value contact: highest won-value, prefer two-way engaged
    qcontact = defaultdict(lambda: {"q": 0, "won": 0, "won_val": 0.0})
    for d in cid_quotes.get(cid, {}).values():
        em = d["email"]
        if not em:
            continue
        qcontact[em]["q"] += 1
        if d["won"]:
            qcontact[em]["won"] += 1
            qcontact[em]["won_val"] += d["value"]
    who = None
    for em, qc in sorted(qcontact.items(), key=lambda kv: -kv[1]["won_val"]):
        if qc["won_val"] <= 0:
            continue
        frm, to, two_way, la = engagement(em)
        cand = {"email": em, "name": contact_name.get(em),
                "won_val": round(qc["won_val"]), "won": qc["won"], "quotes": qc["q"],
                "strike": round(qc["won"] / qc["q"] * 100, 1) if qc["q"] else 0,
                "em_from": frm, "em_to": to, "two_way": two_way,
                "last_active": la.isoformat() if la else None,
                "stale": (la is None) or ((TODAY - la).days > STALE_CONTACT_DAYS)}
        if who is None:
            who = cand
        if two_way:
            who = cand
            break

    # volume leader (loudest inbound contact) for the value-vs-volume contrast
    vol = sorted(((em, len(idxs)) for em, idxs in cidx.items()), key=lambda x: -x[1])
    volume_leader = None
    for em, n in vol:
        frm = sum(1 for i in cidx[em] if not recs[i]["out"])
        if frm > 0:
            volume_leader = {"email": em, "emails": n, "inbound": frm}
            break
    return who, volume_leader, dse, (last_email.isoformat() if last_email else None)


def recency_factor(dse):
    if dse is None:
        return 0.5
    d = max(0, dse)
    return 1.0 if d <= 45 else (0.85 if d <= 180 else (0.7 if d <= 365 else 0.5))


# ════════════════════════════ PART 3: compose cards + final rank ═══════════
print("\nComposing cards...", flush=True)
cards = []
for cid in pool_cids:
    name = cid_name.get(cid, cid)
    rev = comp_rev[cid]
    pick = filtered_pick(cid)
    cand = pick["kept"]
    who, volume_leader, dse, last_email = ground_company(cid)
    rf = recency_factor(dse)
    tm = timing_for(cid, recency_factor=rf)
    conflict = CONFLICT_NORMS.get(normname(name))

    base = (cand["confidence"] * cand["lift"]) if cand else RET_CONST
    opp = opp_strength(base, rev, tm["timing_factor"])

    # basket summary (caps by revenue), last-ordered capability
    bs = sorted(comp_caps[cid].items(), key=lambda kv: -kv[1]["rev"])
    basket_summary = [{"capability": c, "jobs": d["jobs"], "revenue": round(d["rev"])} for c, d in bs]
    lc = sorted(comp_lastcap.get(cid, []), key=lambda x: -x[1].toordinal())
    last_order = ({"capability": lc[0][0], "date": lc[0][1].isoformat()} if lc else None)

    data_quality = []
    if conflict:
        data_quality.append(f"deferred QB-conflict set ({conflict}) — resolution may be unreliable")
    if not who:
        data_quality.append("no QB-won contact identified from quotes")
    if (comp_gap.get(cid, {}) or {}).get("n_orders", 0) < 2:
        data_quality.append("thin order history (<2 orders) — timing unreliable")

    # ── INDUSTRY-FIT (Task 13.3): fit claim for the kept pitch + retained 'Not pitched' line ──
    ind, ind_src = pick["industry"], pick["industry_source"]
    sup = pick["suppressed"]
    if cand and cand.get("fit_status") == "fits":
        fit_line = f"Fits their business: {ind} firms regularly buy {cand['capability']} ({cand['fit_rate']}% do)."
    elif cand and ind:
        fit_line = f"Neutral fit — {cand['capability']} carries no strong industry signal for {ind}; pitched on the statistics."
    elif cand:
        fit_line = "No industry on file — clean statistical pitch, no industry-fit claim (filter skipped)."
    elif ind:
        fit_line = (f"No industry-appropriate cross-sell — every statistical gap is one {ind} firms rarely buy; "
                    f"defaulting to retention/reorder rather than pitch a poor fit.")
    else:
        fit_line = "No eligible cross-sell — retention/reorder."
    not_pitched = None
    suppressed_detail = None
    if sup:
        not_pitched = (f"Not pitched: {sup['capability']} (~{sup['confidence']*100:.0f}% by the numbers) — "
                       f"{ind} firms rarely buy it ({sup['fit_rate']}%), set aside.")
        suppressed_detail = {"capability": sup["capability"], "confidence_pct": round(sup["confidence"] * 100, 1),
                             "lift": sup["lift"], "support_n": sup["support"], "industry_buy_rate_pct": sup["fit_rate"],
                             "suppression_reason": f"{ind} firms buy {sup['capability']} only {sup['fit_rate']}% of the "
                                                   f"time (below the {FIT_LO}% suppress floor)"}
    industry_fit = {
        "industry": ind or "unknown (no industry filter applied)",
        "industry_source": ind_src,
        "kept_pitch": (cand["capability"] if cand else None),
        "fit": fit_line,
        "not_pitched": not_pitched,
        "suppressed_detail": suppressed_detail,
    }

    # ── FRONT (the recommendation) ──────────────────────────────────────────
    if cand:
        Y, X = cand["capability"], cand["from"]
        conf_pct = cand["confidence"] * 100
        pitch = Y
        pitch_conf = (f"~{conf_pct:.0f}% of customers who buy {X} also buy {Y} "
                      f"(lift {cand['lift']}, n={cand['support']} customers; base rate {cand['py']*100:.0f}%)")
        gap_rationale = {
            "pitched": Y, "predicted_by": X,
            "confidence_pct": round(conf_pct, 1), "lift": cand["lift"], "support_n": cand["support"],
            "base_rate_pct": round(cand["py"] * 100, 1),
            "current_basket": sorted(comp_caps[cid]),
            "fact": f"buys {X} ({comp_caps[cid][X]['jobs']} jobs) but has 0 jobs in {Y}",
        }
    else:
        Y = None
        # retention / reorder fallback keyed off timing
        if tm["status"] in ("overdue", "due_soon"):
            anchor = last_order["capability"] if last_order else (bs[0][0] if bs else "their core work")
            pitch = f"no high-confidence cross-sell — reorder nudge on {anchor} ({tm['status'].replace('_',' ')})"
        elif tm["status"] == "dormant":
            pitch = "no high-confidence cross-sell — reactivation outreach (dormant account)"
        else:
            pitch = "no high-confidence cross-sell — retention check-in (account already buys its predicted set)"
        pitch_conf = "n/a — no rule clears conf>=25% & support>=30 over a genuine 0-order gap"
        gap_rationale = {"pitched": None, "reason": "no eligible cross-sell candidate",
                         "current_basket": sorted(comp_caps[cid])}

    if who:
        nm = who["name"] or who["email"]
        fresh = "confirm contact — stale >90d" if who["stale"] else "active"
        to_whom = (f"{nm} <{who['email']}> — {fresh}"
                   + (f" (last active {who['last_active']})" if who["last_active"] else " (no email activity on record)"))
    else:
        to_whom = "no QB-won value contact identified — confirm decision-maker before outreach"

    front = {
        "customer": name,
        "pitch": pitch,
        "confidence": (round(cand["confidence"] * 100, 1) if cand else None),
        "confidence_stated": pitch_conf,
        "to_whom": to_whom,
        "context": {
            "last_order": last_order,
            "basket_summary": [f"{b['capability']} ({b['jobs']} jobs, ${b['revenue']:,})" for b in basket_summary],
            "gap_rationale": gap_rationale,
        },
        "timing": tm["label"],
        "industry_fit": industry_fit,
    }

    # ── BACK (audit trail) ──────────────────────────────────────────────────
    back = {
        "pitch_evidence": ({
            "rule": {"from_basket_item": cand["from"], "consequent": cand["capability"],
                     "confidence": cand["confidence"], "support_n": cand["support"],
                     "lift": cand["lift"], "base_rate_py": cand["py"]},
            "gap_confirmation": {"company_jobs_in_pitch": comp_any.get(cid, {}).get(cand["capability"], 0),
                                 "definition": "qb-OR-classifier (qb_capability_tag else classifier capability_tags)",
                                 "is_genuine_zero_order_gap": comp_any.get(cid, {}).get(cand["capability"], 0) == 0},
        } if cand else {"note": "no eligible rule — retention/reorder card"}),
        "contact_evidence": ({
            "value_contact": who,
            "volume_leader": volume_leader,
            "contrast_note": ((f"value contact ({who['email']}) is NOT the loudest contact "
                               f"({volume_leader['email']}, {volume_leader['emails']} emails) — pitch to value, not volume")
                              if (who and volume_leader and who["email"] != volume_leader["email"])
                              else ("value contact is also the most active contact" if who else None)),
        }),
        "context_evidence": {
            "last_order": last_order,
            "basket_summary": basket_summary,
            "gap_rationale": gap_rationale,
        },
        "timing_evidence": {
            "p50_gap_days": tm["p50"], "p90_gap_days": tm["p90"],   # OCCASION gaps (BURST_DAYS collapse)
            "days_since_last_order": tm["days_since_last"], "n_orders": tm["n_orders"],
            "n_occasions": tm["n_occasions"],
            "window_label": tm["label"], "status": tm["status"], "percentile_math": tm["math"],
            "seasonal": {"approaching": tm["approaching"], "peak_month": (MONTH_NAMES[tm["peak_month"]] if tm["peak_month"] else None),
                         "approach_month": (MONTH_NAMES[tm["approach_month"]] if tm["approach_month"] else None)},
            "email_recency": {"days_since_last_email": dse, "last_email": last_email, "recency_factor": rf},
        },
    }

    cards.append({
        "company_id": cid, "front": front, "back": back,
        "conflict_flag": conflict, "data_quality": data_quality,
        "embellishment_finish_jobs": comp_emb_finish.get(cid, 0),
        "factors": {"confidence": (cand["confidence"] if cand else None),
                    "lift": (cand["lift"] if cand else None),
                    "base": round(base, 4), "revenue": round(rev),
                    "revenue_weight": round(revenue_weight(rev), 4),
                    "timing_factor": tm["timing_factor"]},
        "opportunity_strength": opp,
        "_rev": rev,
    })

# final rank by opportunity strength; conflict-flagged sink below clean cards of equal merit
cards.sort(key=lambda c: (1 if c["conflict_flag"] == "unresolved" else 0, -c["opportunity_strength"]))
cards = cards[:TOPN]
for i, c in enumerate(cards, 1):
    c["rank"] = i

# ── industry-fit change summary (for the 13.3 HARD-STOP report) ──
pitch_dist = {}
for c in cards:
    kp = c["front"]["industry_fit"]["kept_pitch"] or "retention/none"
    pitch_dist[kp] = pitch_dist.get(kp, 0) + 1
fit_summary = {
    "pitch_type_distribution": dict(sorted(pitch_dist.items(), key=lambda kv: -kv[1])),
    "cards_with_suppression_line": sum(1 for c in cards if c["front"]["industry_fit"]["not_pitched"]),
    "cards_with_fit_claim": sum(1 for c in cards if "Fits their business" in (c["front"]["industry_fit"]["fit"] or "")),
    "cards_neutral_or_no_industry": sum(1 for c in cards if c["front"]["industry_fit"]["kept_pitch"]
                                        and "Fits their business" not in (c["front"]["industry_fit"]["fit"] or "")),
    "retention_cards_no_industry_fit": sum(1 for c in cards if c["front"]["industry_fit"]["kept_pitch"] is None),
}

# ════════════════════════════ OUTPUT ══════════════════════════════════════
out = {
    "generated": TODAY.isoformat(), "client": "Carbon8",
    "method": {
        "capability_definition": "Read straight from the corrected capability_tags column via the caps_for_op precedence (Task 13.7: classifier tag first, qb_capability_tag fills gaps). No inline re-derivation — the Layer-1 classifier is the single source of truth (the old CORRECTION-3/cello CASE was removed so the deck cannot drift from the platform). >=2 jobs for the rule basket.",
        "candidate_pick": "genuine-0-order-gap pitches by confidence x lift, then INDUSTRY-FIT re-ranked (Task 13.3): a pitch that fits the customer's industry buying-profile outranks a neutral one outranks a suppressed one; the demoted stats-#1 is retained as the 'Not pitched' line (front.industry_fit.not_pitched).",
        "industry_fit_filter": ("FILTER not generative (docs/design/INDUSTRY_FIT_FILTER_DESIGN.md). Acts ONLY on the 3 "
                                "discriminating caps (Hard Cover/Embellishment/Wide Format), never the universal caps "
                                "(Flat Sheets/Specialty/Design). Industry = qb_customers.industry else 13.2 high-conf "
                                "industry_enriched; no-industry customers skip the filter (clean statistical pitch). "
                                "Thresholds from check-4 buying profiles: >=20% fits / <10% suppress / 10-20% neutral. "
                                "Guardrail: only NEW pitches (genuine 0-order gaps) are filtered — a cap the customer "
                                "already buys is never suppressed."),
        "embellishment_finish_gate": (f"standalone-Embellishment pitch suppressed when the company already applies "
                                      f">={EMB_FINISH_FLOOR} qb_embellishment_tag finish jobs (Hot Foil/Spot UV/Deboss...). "
                                      "Signal-3 check beyond the 0-order gap-confirm — the Geoff Letchford trap; validated in cards_validation.json."),
        "floors": {"confidence": CONF_FLOOR, "support": SUPPORT_FLOOR, "lift": LIFT_FLOOR},
        "timing": "percentile-of-own-gaps (p50/p90 of the gaps between the customer's ordering OCCASIONS — orders within BURST_DAYS=14 days collapsed into one occasion, so clustered same-project jobs don't read as a 4-day reorder cycle) + seasonality + email recency",
        "opportunity_strength": "base(conf*lift | RET_CONST) x log10(revenue) x timing_factor",
        "revenue_weight": "log10(revenue) — DAMPENED so conf/lift/timing can move the rank (raw revenue stored in factors.revenue for a raw re-rank)",
        "selection": f"all {len(prelim)} companies ranked by prelim opportunity; top {POOL} email-grounded; final top {TOPN}",
        "confidence_semantics": ("confidence on each card = best single-antecedent rule P(Y|X) where X is the basket "
                                 "item that most strongly predicts the gap Y (not full-basket-conditioned P(Y|all basket "
                                 "items), which is too sparse). Card text states it plainly: 'customers who buy X also buy Y'."),
    },
    "n_customers_base": N,
    "industry_fit_summary": fit_summary,
    "capability_base_rates": {c: cap_count[c] for c in ALL_CAPS},
    "association_rules": [{"from": X, "to": Y, **r} for (X, Y), r in
                          sorted(rules.items(), key=lambda kv: -(kv[1]["confidence"] * kv[1]["lift"]))],
    "cards": cards,
    "honesty_guards": [
        "Confidence is the real rule % (P(Y|X)), never rounded up or relabelled.",
        "Every pitch verified as a genuine 0-order gap at company grain under qb-OR-classifier (back.pitch_evidence.gap_confirmation).",
        "No archetype / no AM comparison / no scorecard in any front or back field.",
        "Deferred QB-conflict companies flagged (conflict_flag + data_quality); unresolved ones sunk in ranking.",
    ],
    "caveats": [
        "PROVISIONAL card set (per task 11.1): final once mailbox data is complete.",
        "Email recency/timing for Ehab-managed accounts may be UNDERSTATED — Ehab mailbox is ~2 weeks unsynced "
        "(DATA_ANALYSIS_GUIDELINES s0.3); a stale-looking recency on his accounts can be a sync gap, not silence.",
        f"Email-recency factor is computed only for the {POOL}-company email-grounded pool the final {TOPN} are drawn "
        "from; prelim ranking over all companies uses order-rhythm timing without email recency.",
        "Revenue weight = log10(revenue), a deliberate dampening of the literal 'x customer revenue' so conf/lift/timing "
        "can move the ranking; raw revenue + all four factors are on every card (factors.*) for a raw-revenue re-rank.",
        "Pitch-type concentration is now broken by the industry-fit filter (13.3), not an arbitrary cap: a high-confidence "
        "but industry-implausible pitch (e.g. Hard Cover to an Education firm that buys it 9% of the time) is demoted "
        "below a fitting pitch and shown as the 'Not pitched' line. Remaining concentration reflects real industry fit.",
        f"Standalone-Embellishment pitches are gated on signal-3 finishes (qb_embellishment_tag): suppressed when the "
        f"company already applies >={EMB_FINISH_FLOOR} finish jobs. In validation (cards_validation.json) this caught the "
        "Geoff Letchford trap; 9 heavy-embellisher cards were repitched or downgraded, 8 marginal (1-finish) kept.",
        "Two-way engagement requires BOTH inbound>=3 and outbound>=3; a purely inbound contact is not counted as engaged.",
    ],
}
for c in cards:
    c.pop("_rev", None)
json.dump(out, open(os.path.join(HERE, "outreach_cards_50.json"), "w", encoding="utf-8"), indent=2, default=str)

# ── industry-fit summary (13.3 proof) ──────────────────────────────────────
print("\n" + "=" * 116)
print("INDUSTRY-FIT FILTER — deck summary (13.3)")
print("=" * 116)
print("  pitch-type distribution (kept pitch):")
for k, v in fit_summary["pitch_type_distribution"].items():
    print(f"     {k:<28} {v}")
print(f"  cards with a 'Not pitched' suppression line: {fit_summary['cards_with_suppression_line']}")
print(f"  cards with a positive industry-fit claim:    {fit_summary['cards_with_fit_claim']}")
print(f"  neutral / no-industry pitches:               {fit_summary['cards_neutral_or_no_industry']}")
print(f"  retention (no industry-appropriate cross-sell): {fit_summary['retention_cards_no_industry_fit']}")

# ── compact 50 table ───────────────────────────────────────────────────────
print("\n" + "=" * 116)
print("50 NEXT-BEST-OUTREACH CARDS (ranked by opportunity strength)")
print("=" * 116)
print(f"{'#':>3}  {'customer':<30} {'pitch':<26} {'conf':>5}  {'contact':<26} timing")
print("-" * 116)
for c in cards:
    f = c["front"]
    pitch = f["pitch"][:25] if f["pitch"] else "—"
    conf = f"{f['confidence']:.0f}%" if f["confidence"] is not None else "—"
    who = c["back"]["contact_evidence"]["value_contact"]
    contact = (who["email"][:25] if who else "—")
    tlabel = f["timing"].split(" — ")[0].split(";")[0]
    flag = " ⚠" if c["conflict_flag"] else ""
    print(f"{c['rank']:>3}  {f['customer'][:29]:<30} {pitch:<26} {conf:>5}  {contact:<26} {tlabel}{flag}")

# ── top 15 fully expanded (front + full back) ──────────────────────────────
print("\n" + "=" * 116)
print("TOP 15 — FULLY EXPANDED (front + verification back)")
print("=" * 116)
for c in cards[:15]:
    f, b = c["front"], c["back"]
    print(f"\n#{c['rank']}  {f['customer']}   (opp-strength {c['opportunity_strength']}"
          f", QB revenue ${c['factors']['revenue']:,})"
          + (f"   ⚠ CONFLICT[{c['conflict_flag']}]" if c["conflict_flag"] else ""))
    if c["data_quality"]:
        print(f"     ⚑ data-quality: {'; '.join(c['data_quality'])}")
    print(f"     PITCH : {f['pitch']}")
    print(f"             confidence: {f['confidence_stated']}")
    if b["pitch_evidence"].get("gap_confirmation"):
        gc = b["pitch_evidence"]["gap_confirmation"]
        print(f"             gap-confirm: {gc['company_jobs_in_pitch']} jobs in pitch (genuine 0-order gap = {gc['is_genuine_zero_order_gap']})")
    print(f"     WHOM  : {f['to_whom']}")
    who = b["contact_evidence"]["value_contact"]
    if who:
        print(f"             won ${who['won_val']:,} over {who['won']}/{who['quotes']} quotes "
              f"(strike {who['strike']}%), email {who['em_from']}↑/{who['em_to']}↓, "
              f"two-way={who['two_way']}")
    if b["contact_evidence"]["contrast_note"]:
        print(f"             {b['contact_evidence']['contrast_note']}")
    lo = f["context"]["last_order"]
    print(f"     CONTEXT: last order = {(lo['capability'] + ' on ' + lo['date']) if lo else 'n/a'}")
    print(f"             basket = {', '.join(f['context']['basket_summary'])}")
    te = b["timing_evidence"]
    print(f"     TIMING: {f['timing']}")
    print(f"             p50={te['p50_gap_days']}d  p90={te['p90_gap_days']}d  days_since={te['days_since_last_order']}d  "
          f"n_orders={te['n_orders']}  [{te['percentile_math']}]")
    print(f"             factors: conf={c['factors']['confidence']} x lift={c['factors']['lift']} "
          f"x revw={c['factors']['revenue_weight']} x timing={c['factors']['timing_factor']} "
          f"=> opp {c['opportunity_strength']}")

print("\nJSON -> scripts/db/outreach_cards_50.json")

# ── drop throwaway RPCs ────────────────────────────────────────────────────
print("Dropping throwaway RPCs...", flush=True)
exec_sql("DROP FUNCTION IF EXISTS _tmp_card_basket(uuid)")
exec_sql("DROP FUNCTION IF EXISTS _tmp_card_gaps(uuid)")
exec_sql("DROP FUNCTION IF EXISTS _tmp_card_lastcap(uuid, uuid[])")
exec_sql("NOTIFY pgrst, 'reload schema'")
print("Done.")
