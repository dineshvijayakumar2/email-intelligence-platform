"""
THROWAWAY validation of outreach_cards_50.json. Read-only. Reuses the cached pool
email metadata (_outreach_cards_email_cache.json) where possible.

CHECK 1 — Embellishment finish-tag trap (the Geoff Letchford trap, DATA_ANALYSIS_GUIDELINES §5.1).
  The cards confirmed 0-order on capability=Embellishment (signals 1+2: qb_capability_tag /
  classifier capability_tags). This check tests signal 3: qb_embellishment_tag (Hot Foil, Spot
  UV, Deboss/Emboss, Digital Foil, Laser Cut ...) — the FINISH applied *within other jobs*.
  A customer with 0 standalone-Embellishment capability but who foils/embosses within their
  flat-sheet/book jobs ALREADY does embellishment -> the standalone pitch is weak/meaningless.
  For the 30 Embellishment-pitch customers: GENUINE GAP (0 finishes anywhere) vs ALREADY-
  EMBELLISHES (has finishes). For traps: best alternative genuine-0-order gap (conf x lift) or
  downgrade to retention.

CHECK 2 — Top-15 reconciliation against a fresh independent computation:
  (a) pitched capability genuinely 0-order at company grain (classifier-first qb-OR-classifier) — re-confirm;
  (b) rule conf/support/lift match a fresh full-base re-derivation;
  (c) value contact won-value + two-way counts (inbound>=3 AND outbound>=3) are real;
  (d) timing: days_since/n_orders on raw distinct order dates, p50/p90 on the gaps between ORDERING
      OCCASIONS (orders within BURST_DAYS collapsed into one occasion — matches the deck's RPC_GAPS),
      percentile_cont re-derived; optionally n_occasions.
  Any number that doesn't reconcile is flagged. Capability precedence here is the deck's caps_for_op
  (classifier capability_tags first, qb_capability_tag fills gaps; Task 13.7) so (a)/(b) don't drift.

Output: scripts/db/cards_validation.json
"""
import os, sys, io, json, time, math, statistics
from collections import defaultdict
from datetime import date, datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
from dotenv import load_dotenv
from supabase import create_client

HERE = os.path.dirname(__file__)
env = os.path.join(HERE, "..", "..", "backend", ".env.production")
if not os.path.exists(env):
    env = os.path.join(HERE, "..", "..", "backend", ".env")
load_dotenv(env)
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
C8 = "241d7b99-f099-4557-96e5-212c4af10812"
PAGE = 1000
TODAY = date(2026, 6, 15)   # must match the deck engine's TODAY (scripts/db/_outreach_cards_50.py)
CONF_FLOOR, SUPPORT_FLOOR, LIFT_FLOOR = 0.25, 30, 1.0
BURST_DAYS = 14  # orders within this many days collapse into one ordering occasion for the cadence
                 # p50/p90 — MUST match BURST_DAYS in _outreach_cards_50.py / _cadence_rank_diag.py
CARDS = json.load(open(os.path.join(HERE, "outreach_cards_50.json"), encoding="utf-8"))
EMAIL_CACHE = os.path.join(HERE, "_outreach_cards_email_cache.json")


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
            print(f"    retry {i+1} after {type(e).__name__}", flush=True)
            time.sleep(2 * (i + 1)); sb = _client()


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


def norm(e):
    return (e or "").strip().lower()


def normcap(c):
    import re
    return re.sub(r"\s*/\s*", "/", (c or "").strip())


def parse_date(s):
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo:
        d = d.astimezone(timezone.utc).replace(tzinfo=None)
    return d.date()


def emails_in(lst):
    out = []
    for x in (lst or []):
        if isinstance(x, dict):
            e = norm(x.get("email"))
        elif isinstance(x, str):
            e = norm(x)
        else:
            e = ""
        if e:
            out.append(e)
    return out


def pctile_cont(sorted_vals, p):
    """Match Postgres percentile_cont: linear interpolation on sorted values."""
    n = len(sorted_vals)
    if n == 0:
        return None
    if n == 1:
        return float(sorted_vals[0])
    rank = p * (n - 1)
    lo = int(math.floor(rank))
    frac = rank - lo
    if lo + 1 < n:
        return sorted_vals[lo] + frac * (sorted_vals[lo + 1] - sorted_vals[lo])
    return float(sorted_vals[lo])


def exec_ddl(q):
    return with_retry(lambda: sb.rpc("exec_sql", {"query": q}).execute())


# Capability per op uses the deck's caps_for_op precedence (Task 13.7): the corrected classifier
# capability_tags FIRST, qb_capability_tag fills gaps only when the classifier is silent (empty/absent
# array). MUST match CAP_LATERAL in _outreach_cards_50.py — the old qb-tag-first order false-failed
# the rule-reconciliation check on the ~15% of ops the Layer-1 classifier reclassified.
CAP_LATERAL = """
  CROSS JOIN LATERAL (
    SELECT CASE
      WHEN jsonb_typeof(o.capability_tags) = 'array' AND jsonb_array_length(o.capability_tags) > 0
        THEN o.capability_tags
      WHEN btrim(coalesce(o.qb_capability_tag,'')) <> '' THEN jsonb_build_array(btrim(o.qb_capability_tag))
      ELSE '[]'::jsonb END AS capsj
  ) d
  CROSS JOIN LATERAL jsonb_array_elements_text(d.capsj) AS u(cap)
"""

RPC_CAPJOBS = f"""
CREATE OR REPLACE FUNCTION _tmp_val_capjobs(p_client uuid, p_cids uuid[])
RETURNS jsonb LANGUAGE sql STABLE
SET search_path = public SET statement_timeout = '180s' AS $fn$
WITH ops AS (
  SELECT o.matched_company_id cid, o.job_no, o.qb_embellishment_tag emb,
         o.qb_capability_tag, o.capability_tags
  FROM qb_operations o
  WHERE o.client_id = p_client AND o.matched_company_id = ANY(p_cids)
),
capbase AS (
  SELECT o.cid, btrim(u.cap) cap, o.job_no
  FROM ops o
  CROSS JOIN LATERAL (
    SELECT CASE     -- caps_for_op precedence: classifier first, qb tag fills gaps (matches the deck)
      WHEN jsonb_typeof(o.capability_tags) = 'array' AND jsonb_array_length(o.capability_tags) > 0
        THEN o.capability_tags
      WHEN btrim(coalesce(o.qb_capability_tag,'')) <> '' THEN jsonb_build_array(btrim(o.qb_capability_tag))
      ELSE '[]'::jsonb END capsj) d
  CROSS JOIN LATERAL jsonb_array_elements_text(d.capsj) u(cap)
  WHERE length(btrim(u.cap)) > 1
),
capjobs AS (SELECT cid, cap, count(DISTINCT job_no) jobs FROM capbase GROUP BY cid, cap),
embj AS (
  SELECT cid, count(DISTINCT job_no) emb_jobs,
         jsonb_agg(DISTINCT btrim(emb)) FILTER (WHERE btrim(coalesce(emb,'')) <> '') tags
  FROM ops WHERE btrim(coalesce(emb,'')) <> '' GROUP BY cid
)
SELECT coalesce(jsonb_agg(jsonb_build_object(
  'cid', c.cid,
  'capjobs', (SELECT jsonb_object_agg(cap, jobs) FROM capjobs cj WHERE cj.cid = c.cid),
  'emb_jobs', coalesce((SELECT emb_jobs FROM embj e WHERE e.cid = c.cid), 0),
  'emb_tags', coalesce((SELECT tags FROM embj e WHERE e.cid = c.cid), '[]'::jsonb)
)), '[]'::jsonb)
FROM (SELECT DISTINCT cid FROM ops) c;
$fn$;
"""

RPC_MATRIX = f"""
CREATE OR REPLACE FUNCTION _tmp_val_matrix(p_client uuid)
RETURNS jsonb LANGUAGE sql STABLE
SET search_path = public SET statement_timeout = '240s' AS $fn$
WITH base AS (
  SELECT o.matched_company_id cid, btrim(u.cap) cap, o.job_no
  FROM qb_operations o
  {CAP_LATERAL}
  WHERE o.client_id = p_client AND o.matched_company_id IS NOT NULL AND length(btrim(u.cap)) > 1
),
percap AS (SELECT cid, cap, count(DISTINCT job_no) jobs FROM base GROUP BY cid, cap),
comp AS (SELECT cid, jsonb_agg(cap) caps FROM percap WHERE jobs >= 2 GROUP BY cid)
SELECT coalesce(jsonb_agg(jsonb_build_object('cid', cid, 'caps', caps)), '[]'::jsonb) FROM comp;
$fn$;
"""

RPC_DATES = """
CREATE OR REPLACE FUNCTION _tmp_val_dates(p_client uuid, p_cids uuid[])
RETURNS jsonb LANGUAGE sql STABLE
SET search_path = public SET statement_timeout = '120s' AS $fn$
SELECT coalesce(jsonb_agg(jsonb_build_object('cid', cid, 'dates', dates)), '[]'::jsonb)
FROM (
  SELECT matched_company_id cid, jsonb_agg(DISTINCT date_accepted ORDER BY date_accepted) dates
  FROM qb_operations
  WHERE client_id = p_client AND matched_company_id = ANY(p_cids) AND date_accepted IS NOT NULL
  GROUP BY matched_company_id
) t;
$fn$;
"""

print("Creating throwaway validation RPCs...", flush=True)
exec_ddl(RPC_CAPJOBS); exec_ddl(RPC_MATRIX); exec_ddl(RPC_DATES)
exec_ddl("NOTIFY pgrst, 'reload schema'")
time.sleep(3)

# ── card subsets ────────────────────────────────────────────────────────────
cards = CARDS["cards"]
emb_cards = [c for c in cards if (c["front"]["pitch"] or "").split(" —")[0].strip() == "Embellishment"]
top15 = sorted(cards, key=lambda c: c["rank"])[:15]
emb_cids = [c["company_id"] for c in emb_cards]
top15_cids = [c["company_id"] for c in top15]
scoped = sorted(set(emb_cids) | set(top15_cids))
print(f"Embellishment-pitch cards: {len(emb_cards)} | top15: {len(top15)} | scoped companies: {len(scoped)}", flush=True)

# ── RPC A: per-company capability jobs + embellishment finishes (scoped) ────
capjobs_json = with_retry(lambda: sb.rpc("_tmp_val_capjobs", {"p_client": C8, "p_cids": scoped}).execute()).data or []
comp_capjobs, comp_emb, comp_embtags = {}, {}, {}
for r in capjobs_json:
    cid = r["cid"]
    cj = {}
    for cap, jobs in (r.get("capjobs") or {}).items():
        cj[normcap(cap)] = cj.get(normcap(cap), 0) + int(jobs)
    comp_capjobs[cid] = cj
    comp_emb[cid] = int(r.get("emb_jobs") or 0)
    comp_embtags[cid] = sorted({normcap(t) for t in (r.get("emb_tags") or [])})

# ── RPC B: fresh full-base capability matrix (for rule re-derivation) ────────
print("Calling _tmp_val_matrix (fresh full-base matrix)...", flush=True)
matrix_json = with_retry(lambda: sb.rpc("_tmp_val_matrix", {"p_client": C8}).execute()).data or []
fresh_caps = {}
for r in matrix_json:
    fresh_caps[r["cid"]] = {normcap(c) for c in (r.get("caps") or [])}
Nf = len(fresh_caps)
fcap_count = defaultdict(int)
fpair = defaultdict(int)
for caps in fresh_caps.values():
    cl = list(caps)
    for c in cl:
        fcap_count[c] += 1
    for i in range(len(cl)):
        for j in range(len(cl)):
            if i != j:
                fpair[(cl[i], cl[j])] += 1


def fresh_rule(X, Y):
    both = fpair.get((X, Y), 0)
    if both == 0 or fcap_count[X] == 0 or fcap_count[Y] == 0:
        return None
    conf = both / fcap_count[X]
    lift = conf / (fcap_count[Y] / Nf)
    return {"support": both, "confidence": round(conf, 4), "lift": round(lift, 3),
            "py": round(fcap_count[Y] / Nf, 4)}


# global rules from the card JSON (for alternative-gap search)
RULES = {(r["from"], r["to"]): r for r in CARDS["association_rules"]}
ALL_CAPS = sorted(CARDS["capability_base_rates"])


def best_alt_gap(cid, exclude):
    """Best alternative genuine-0-order cross-sell for a company, by conf x lift."""
    basket = {normcap(c) for c in (comp_capjobs.get(cid) or {}) if comp_capjobs[cid][c] >= 2}
    cj = comp_capjobs.get(cid, {})
    best = None
    for Y in ALL_CAPS:
        if Y in basket or Y == exclude or cj.get(Y, 0) > 0:   # genuine 0-order only
            continue
        for X in basket:
            r = RULES.get((X, Y))
            if not r or r["confidence"] < CONF_FLOOR or r["support"] < SUPPORT_FLOOR or r["lift"] <= LIFT_FLOOR:
                continue
            score = r["confidence"] * r["lift"]
            if best is None or score > best["score"]:
                best = {"capability": Y, "from": X, "score": round(score, 4), **r}
    return best


# ════════════════════════════ CHECK 1 ═════════════════════════════════════
check1 = []
genuine = trap = 0
for c in sorted(emb_cards, key=lambda x: x["rank"]):
    cid = c["company_id"]; name = c["front"]["customer"]
    emb_jobs = comp_emb.get(cid, 0)
    tags = comp_embtags.get(cid, [])
    if emb_jobs == 0:
        genuine += 1
        check1.append({"rank": c["rank"], "customer": name, "company_id": cid,
                       "verdict": "GENUINE_GAP", "embellishment_finish_jobs": 0,
                       "finishes": [], "corrected_pitch": "Embellishment (unchanged — confirmed genuine)"})
    else:
        trap += 1
        alt = best_alt_gap(cid, exclude="Embellishment")
        if alt:
            corrected = (f"{alt['capability']} (alt gap: {int(alt['confidence']*100)}% via {alt['from']}, "
                         f"lift {alt['lift']}, n={alt['support']})")
            action = "REPLACE_PITCH"
        else:
            corrected = "downgrade to retention/reorder — no alternative genuine 0-order gap"
            action = "DOWNGRADE"
        check1.append({"rank": c["rank"], "customer": name, "company_id": cid,
                       "verdict": "ALREADY_EMBELLISHES", "embellishment_finish_jobs": emb_jobs,
                       "finishes": tags, "action": action, "corrected_pitch": corrected,
                       "alternative": alt})

# ════════════════════════════ CHECK 2 ═════════════════════════════════════
# fresh quotes for top-15 (value-contact won value + strike)
qbcust = fetch_all("qb_customers", "matched_company_id, customer_key_id",
                   [lambda q: q.eq("client_id", C8),
                    lambda q: q.in_("matched_company_id", top15_cids)])
key_to_cid = {str(r["customer_key_id"]): r["matched_company_id"]
              for r in qbcust if r.get("customer_key_id") and r.get("matched_company_id")}
keys = list(key_to_cid)
qrows = []
for i in range(0, len(keys), 50):
    ch = keys[i:i + 50]
    qrows += fetch_all("qb_quotes", "quote_no, sell_ex_tax, has_job, job_no, contact_email, qb_customer_id",
                       [lambda q: q.eq("client_id", C8), lambda q, c=ch: q.in_("qb_customer_id", c)])
cid_quotes = defaultdict(dict)
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
    if ce and not e["email"]:
        e["email"] = ce

# cached emails for two-way recompute
cache = json.load(open(EMAIL_CACHE, encoding="utf-8")) if os.path.exists(EMAIL_CACHE) else {"emails": {}}
cache_emails = cache.get("emails", {})


def recompute_contact(cid, email):
    frm = to = 0
    won_val = 0.0
    for qno, d in cid_quotes.get(cid, {}).items():
        if d["email"] == email and d["won"]:
            won_val += d["value"]
    for e in cache_emails.get(cid, []):
        outb = bool(e.get("is_outbound"))
        if outb:
            if email in set(emails_in(e.get("recipients")) + emails_in(e.get("cc_list"))):
                to += 1
        else:
            if norm(e.get("sender_email")) == email:
                frm += 1
    return round(won_val), frm, to

# dates for top-15 timing re-derivation
dates_json = with_retry(lambda: sb.rpc("_tmp_val_dates", {"p_client": C8, "p_cids": top15_cids}).execute()).data or []
comp_dates = {}
for r in dates_json:
    ds = sorted(d for d in (parse_date(x) for x in (r.get("dates") or [])) if d)
    comp_dates[r["cid"]] = ds

check2 = []
for c in top15:
    cid = c["company_id"]; name = c["front"]["customer"]
    pe = c["back"]["pitch_evidence"]
    flags = []

    # (a) 0-order re-confirm
    pitched = (pe.get("rule") or {}).get("consequent")
    fresh_jobs_in_pitch = comp_capjobs.get(cid, {}).get(normcap(pitched), 0) if pitched else None
    a_pass = (fresh_jobs_in_pitch == 0) if pitched else None
    if pitched and not a_pass:
        flags.append(f"gap0: fresh {fresh_jobs_in_pitch} jobs in {pitched} (card claimed 0)")

    # (b) rule re-derivation
    b_pass, b_detail = None, None
    if pe.get("rule"):
        X, Y = pe["rule"]["from_basket_item"], pe["rule"]["consequent"]
        fr = fresh_rule(normcap(X), normcap(Y))
        if fr is None:
            b_pass = False; b_detail = "fresh rule not found"
            flags.append(f"rule: {X}->{Y} not reproducible")
        else:
            dconf = abs(fr["confidence"] - pe["rule"]["confidence"])
            dlift = abs(fr["lift"] - pe["rule"]["lift"])
            dsupp = abs(fr["support"] - pe["rule"]["support_n"])
            b_pass = dconf <= 0.02 and dlift <= 0.05 and dsupp <= max(3, 0.03 * pe["rule"]["support_n"])
            b_detail = {"card": {"conf": pe["rule"]["confidence"], "supp": pe["rule"]["support_n"], "lift": pe["rule"]["lift"]},
                        "fresh": {"conf": fr["confidence"], "supp": fr["support"], "lift": fr["lift"]}}
            if not b_pass:
                flags.append(f"rule: {X}->{Y} card(conf {pe['rule']['confidence']},supp {pe['rule']['support_n']},lift {pe['rule']['lift']}) "
                             f"vs fresh(conf {fr['confidence']},supp {fr['support']},lift {fr['lift']})")

    # (c) value contact
    c_pass, c_detail = None, None
    vc = c["back"]["contact_evidence"]["value_contact"]
    if vc:
        wv, frm, to = recompute_contact(cid, vc["email"])
        two_way_fresh = frm >= 3 and to >= 3
        # won value tolerance 1% (quote collapse identical method)
        dwv = abs(wv - vc["won_val"])
        c_pass = (dwv <= max(50, 0.01 * max(vc["won_val"], 1)) and frm == vc["em_from"]
                  and to == vc["em_to"] and two_way_fresh == vc["two_way"])
        c_detail = {"card": {"won_val": vc["won_val"], "frm": vc["em_from"], "to": vc["em_to"], "two_way": vc["two_way"]},
                    "fresh": {"won_val": wv, "frm": frm, "to": to, "two_way": two_way_fresh}}
        if not c_pass:
            flags.append(f"contact: card(won ${vc['won_val']},{vc['em_from']}/{vc['em_to']},2w {vc['two_way']}) "
                         f"vs fresh(won ${wv},{frm}/{to},2w {two_way_fresh})")
    else:
        c_pass = None  # no contact to verify (already data-quality flagged)

    # (d) timing — cadence is measured on ORDERING OCCASIONS (orders within BURST_DAYS collapsed into
    #     one occasion), matching the deck's RPC_GAPS / _cadence_rank_diag._tmp_o. n_orders stays the raw
    #     distinct-date count; days_since stays the actual last order. p50/p90 are percentiles of the gaps
    #     between occasion start-dates.
    d_pass, d_detail = None, None
    ds = comp_dates.get(cid, [])
    te = c["back"]["timing_evidence"]
    if len(ds) >= 1:
        last = ds[-1]
        days_since = (TODAY - last).days
        # collapse distinct order dates into occasion start-dates: a gap > BURST_DAYS from the previous
        # order opens a new occasion, dated by its first order (= min order date of the occasion).
        occ_dates = [ds[0]]
        for i in range(1, len(ds)):
            if (ds[i] - ds[i - 1]).days > BURST_DAYS:
                occ_dates.append(ds[i])
        gaps = sorted((occ_dates[i] - occ_dates[i - 1]).days for i in range(1, len(occ_dates)))
        p50 = pctile_cont(gaps, 0.5) if gaps else None
        p90 = pctile_cont(gaps, 0.9) if gaps else None
        fp50 = round(p50) if p50 is not None else None
        fp90 = round(p90) if p90 is not None else None
        n_occ_card = te.get("n_occasions")
        occ_ok = (n_occ_card is None) or (len(occ_dates) == n_occ_card)
        d_pass = (days_since == te["days_since_last_order"]
                  and fp50 == te["p50_gap_days"] and fp90 == te["p90_gap_days"]
                  and len(ds) == te["n_orders"] and occ_ok)
        d_detail = {"card": {"days_since": te["days_since_last_order"], "p50": te["p50_gap_days"],
                             "p90": te["p90_gap_days"], "n_orders": te["n_orders"], "n_occasions": n_occ_card},
                    "fresh": {"days_since": days_since, "p50": fp50, "p90": fp90,
                              "n_orders": len(ds), "n_occasions": len(occ_dates)}}
        if not d_pass:
            flags.append(f"timing: card(ds {te['days_since_last_order']},p50 {te['p50_gap_days']},p90 {te['p90_gap_days']},n {te['n_orders']},occ {n_occ_card}) "
                         f"vs fresh(ds {days_since},p50 {fp50},p90 {fp90},n {len(ds)},occ {len(occ_dates)})")

    overall = "PASS" if not flags else "FAIL"
    check2.append({"rank": c["rank"], "customer": name, "company_id": cid, "pitch": pitched,
                   "overall": overall,
                   "checks": {"gap0_zero_order": a_pass, "rule_reconciles": b_pass,
                              "contact_reconciles": c_pass, "timing_reconciles": d_pass},
                   "detail": {"gap0_fresh_jobs": fresh_jobs_in_pitch, "rule": b_detail,
                              "contact": c_detail, "timing": d_detail},
                   "flags": flags})

# ════════════════════════════ OUTPUT ══════════════════════════════════════
out = {"generated": TODAY.isoformat(), "validates": "outreach_cards_50.json",
       "fresh_matrix_n_companies": Nf,
       "check1_embellishment": {"n": len(emb_cards), "genuine": genuine, "trap": trap, "cards": check1},
       "check2_top15_reconciliation": check2}
json.dump(out, open(os.path.join(HERE, "cards_validation.json"), "w", encoding="utf-8"), indent=2, default=str)

print("\n" + "=" * 100)
print(f"CHECK 1 — EMBELLISHMENT FINISH-TAG TRAP   ({len(emb_cards)} Embellishment pitches)")
print("=" * 100)
print(f"  GENUINE GAP (0 finishes anywhere): {genuine}     ALREADY-EMBELLISHES (trap): {trap}")
print("-" * 100)
for r in check1:
    if r["verdict"] == "GENUINE_GAP":
        print(f"  #{r['rank']:>2} {r['customer'][:34]:<35} GENUINE   (0 finish jobs)")
    else:
        print(f"  #{r['rank']:>2} {r['customer'][:34]:<35} ⚠ TRAP    {r['embellishment_finish_jobs']} finish jobs "
              f"[{', '.join(r['finishes'])}]")
        print(f"        → corrected: {r['corrected_pitch']}")

print("\n" + "=" * 100)
print("CHECK 2 — TOP-15 RECONCILIATION vs raw QB")
print("=" * 100)
print(f"  {'#':>2} {'customer':<32} {'gap0':>5} {'rule':>5} {'cont':>5} {'time':>5}   overall")
print("-" * 100)
def mark(v):
    return "—" if v is None else ("✓" if v else "✗")
for r in check2:
    ch = r["checks"]
    print(f"  {r['rank']:>2} {r['customer'][:31]:<32} {mark(ch['gap0_zero_order']):>5} {mark(ch['rule_reconciles']):>5} "
          f"{mark(ch['contact_reconciles']):>5} {mark(ch['timing_reconciles']):>5}   {r['overall']}")
    for f in r["flags"]:
        print(f"        ⚠ {f}")

print("\nJSON -> scripts/db/cards_validation.json")
print("Dropping throwaway RPCs...", flush=True)
exec_ddl("DROP FUNCTION IF EXISTS _tmp_val_capjobs(uuid, uuid[])")
exec_ddl("DROP FUNCTION IF EXISTS _tmp_val_matrix(uuid)")
exec_ddl("DROP FUNCTION IF EXISTS _tmp_val_dates(uuid, uuid[])")
exec_ddl("NOTIFY pgrst, 'reload schema'")
print("Done.")
