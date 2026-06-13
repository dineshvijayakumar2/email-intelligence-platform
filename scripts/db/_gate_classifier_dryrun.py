"""
Step 2 §10.12 GATE (READ-ONLY, no writes). Replicates the corrected production classifier
resolution exactly:
  1. exact (dept,op,machine) tuple match  -> its tag  (or NULL/silent for a (none) tuple)
  2. keyword fallback on combined text     -> first matching rule's tag   (only on exact MISS)
then applies the NEW precedence: cap = classifier_opinion ELSE qb_capability_tag (QB fills gaps).

Builds company baskets (>=2 distinct jobs per cap) and association rules, and checks whether it
reproduces the audit's clean numbers: 242 Embellishment companies, 183 Hard Cover, ~balanced rules.
If it does NOT, the gate FAILS — do not switch consumers.

Rules read from the BRANCH source of truth (corrected capability_classifier_data.json tuples +
corrected _KEYWORD_RULES code default) — NOT from live config, which is written only after the gate.
"""
import os, sys, io, json, time, re
from collections import defaultdict, Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, "backend")
sys.path.insert(0, "backend/src/services")
from dotenv import load_dotenv
from supabase import create_client
import capability_classifier as cc   # corrected _KEYWORD_RULES + _normalize

e = "backend/.env.production" if os.path.exists("backend/.env.production") else "backend/.env"
load_dotenv(e)
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
C8 = "241d7b99-f099-4557-96e5-212c4af10812"
SUPPORT_FLOOR, CONF_FLOOR, LIFT_FLOOR = 30, 0.25, 1.0
# §10.12 reference = capability_tag_audit.json corrected base RATES (the audit IS an unscoped
# op-name reclassification — structurally identical to this classifier). The deck's "242 / 11.1%"
# was a SCOPED CAP_LATERAL variant a qb-blind classifier cannot and should not reproduce.
AUDIT = json.load(open("scripts/db/capability_tag_audit.json", encoding="utf-8"))
TGT_EMB_PCT = AUDIT["base_rates"]["corrected"]["Embellishment"]       # 15.3
TGT_HC_PCT = AUDIT["base_rates"]["corrected"]["Hard Cover Books"]     # 8.3
TOL_PCT = 1.0   # pollution-cap base rate must land within 1.0pp of the audit

# ── build exact-tuple CTE from the corrected JSON (dedupe by key, last wins = dict semantics) ──
tuples = json.load(open("backend/src/services/capability_classifier_data.json", encoding="utf-8"))
exact = {}
for r in tuples:
    key = (cc._normalize(r.get("department")), cc._normalize(r.get("operation")), cc._normalize(r.get("machine")))
    tag = r.get("mvp_tag")
    if tag == "(none)":
        tag = None
    exact[key] = tag   # None => matched-but-silent (short-circuits keyword)


def q(s):
    return "'" + s.replace("'", "''") + "'"


values = []
for (d, o, m), tag in exact.items():
    values.append(f"({q(d)},{q(o)},{q(m)},{'NULL' if tag is None else q(tag)})")
exact_cte = "exact(dn,opn,mn,tag) AS (VALUES\n" + ",\n".join(values) + ")"

# ── keyword CASE from corrected _KEYWORD_RULES (priority order, substring == escaped regex) ──
kw_when = []
for kws, tag in cc._KEYWORD_RULES:
    alt = "|".join(re.escape(k) for k in kws)
    kw_when.append(f"      WHEN combined ~* '({alt})' THEN {q(tag)}")
keyword_case = "CASE\n" + "\n".join(kw_when) + "\n      ELSE NULL END"

def make_fn(name, kw_source):
    # kw_source: 'combined' (dept+op+machine, production classifier) or 'opn' (op-name only, audit-parity)
    kc = keyword_case.replace("combined ~*", f"{kw_source} ~*")
    return f"""CREATE OR REPLACE FUNCTION {name}(p_client uuid) RETURNS jsonb LANGUAGE sql STABLE
SET search_path=public SET statement_timeout='240s' AS $fn$
WITH {exact_cte},
op AS (
  SELECT o.matched_company_id cid, o.job_no,
    lower(regexp_replace(btrim(coalesce(o.department,'')),'\\s+',' ','g')) dn,
    lower(regexp_replace(btrim(coalesce(o.operation_name,'')),'\\s+',' ','g')) opn,
    lower(regexp_replace(btrim(coalesce(o.machine,'')),'\\s+',' ','g')) mn,
    nullif(btrim(coalesce(o.qb_capability_tag,'')),'') qb,
    lower(coalesce(o.department,'')||' '||coalesce(o.operation_name,'')||' '||coalesce(o.machine,'')) combined
  FROM qb_operations o
  WHERE o.client_id=p_client AND o.matched_company_id IS NOT NULL AND o.job_no IS NOT NULL),
m AS (
  SELECT op.cid, op.job_no, op.qb, op.combined, op.opn, e.tag exact_tag, (e.dn IS NOT NULL) matched
  FROM op LEFT JOIN exact e ON e.dn=op.dn AND e.opn=op.opn AND e.mn=op.mn),
classified AS (
  SELECT cid, job_no, qb,
    CASE
      WHEN matched THEN exact_tag
      ELSE {kc}
    END AS clf
  FROM m),
final AS (SELECT cid, job_no, COALESCE(clf, qb) cap FROM classified)
SELECT coalesce(jsonb_agg(jsonb_build_object('cid',cid,'cap',cap,'j',j)),'[]')
FROM (SELECT cid, cap, count(DISTINCT job_no) j FROM final
      WHERE cap IS NOT NULL AND length(cap)>1 GROUP BY 1,2) t;
$fn$;"""


def ddl(query):
    return sb.rpc("exec_sql", {"query": query}).execute()


VARIANT = os.environ.get("KW_SOURCE", "combined")  # 'combined' (prod) or 'opn' (audit-parity)
print(f"exact tuples: {len(exact)}  keyword rules: {len(cc._KEYWORD_RULES)}  kw_source={VARIANT}  building gate fn...", flush=True)
ddl(make_fn("_tmp_gate", VARIANT))
ddl("NOTIFY pgrst,'reload schema'"); time.sleep(2)
rows = sb.rpc("_tmp_gate", {"p_client": C8}).execute().data or []
ddl("DROP FUNCTION IF EXISTS _tmp_gate(uuid)")
ddl("NOTIFY pgrst,'reload schema'")

# ── build baskets + base rates + rules (audit thresholds) ──
comp = defaultdict(dict)
for r in rows:
    comp[r["cid"]][r["cap"]] = int(r["j"])
basket = {cid: {c for c, j in caps.items() if j >= 2} for cid, caps in comp.items()}
basket = {cid: b for cid, b in basket.items() if b}
N = len(basket)
cc_cnt = Counter()
pair = defaultdict(int)
for b in basket.values():
    for x in b:
        cc_cnt[x] += 1
    for x in b:
        for y in b:
            if x != y:
                pair[(x, y)] += 1
base = {c: (cc_cnt[c], round(100 * cc_cnt[c] / N, 1)) for c in cc_cnt}
rules = []
for X in cc_cnt:
    for Y in cc_cnt:
        if X == Y:
            continue
        both = pair.get((X, Y), 0)
        if both < SUPPORT_FLOOR or not cc_cnt[X] or not cc_cnt[Y]:
            continue
        conf = both / cc_cnt[X]
        lift = conf / (cc_cnt[Y] / N)
        if lift >= LIFT_FLOOR and conf >= CONF_FLOOR:
            rules.append({"from": X, "to": Y, "conf": round(conf * 100, 1), "support": both, "lift": round(lift, 2)})
rules.sort(key=lambda r: -r["conf"])

emb_n, emb_pct = base.get("Embellishment", (0, 0.0))
hc_n, hc_pct = base.get("Hard Cover Books", (0, 0.0))
emb_ok = abs(emb_pct - TGT_EMB_PCT) <= TOL_PCT
hc_ok = abs(hc_pct - TGT_HC_PCT) <= TOL_PCT
gate_pass = emb_ok and hc_ok

out = {"universe": N, "base_rates": {k: {"companies": v[0], "pct": v[1]} for k, v in base.items()},
       "rule_count": len(rules), "rules": rules,
       "audit_reference": {"embellishment_pct": TGT_EMB_PCT, "hard_cover_pct": TGT_HC_PCT, "tol_pct": TOL_PCT},
       "actual": {"embellishment_companies": emb_n, "embellishment_pct": emb_pct,
                  "hard_cover_companies": hc_n, "hard_cover_pct": hc_pct},
       "gate_pass": gate_pass}
json.dump(out, open("scripts/db/gate_classifier_dryrun.json", "w", encoding="utf-8"), indent=2)

P = print
P("=" * 92)
P("STEP 2 §10.12 GATE — corrected classifier (dry-run, NEW precedence), live data")
P("=" * 92)
P(f"  basket universe: {N} companies")
P(f"\n  {'capability':<22}{'companies':>11}{'base %':>9}")
for c, (n, p) in sorted(base.items(), key=lambda kv: -kv[1][0]):
    flag = ""
    if c == "Embellishment":
        flag = f"   <- audit {TGT_EMB_PCT}% ({'OK' if emb_ok else 'MISS'})"
    if c == "Hard Cover Books":
        flag = f"   <- audit {TGT_HC_PCT}% ({'OK' if hc_ok else 'MISS'})"
    P(f"  {c:<22}{n:>11}{p:>8}%{flag}")
P(f"\n  surviving rules (supp>=30, conf>=25%, lift>=1.0): {len(rules)}")
for r in rules[:40]:
    P(f"     {r['from']:<20} -> {r['to']:<20} conf {r['conf']:>5}%  n={r['support']:>4}  lift {r['lift']}")
P("\n" + "=" * 92)
P(f"  GATE (vs audit corrected base rates, tol {TOL_PCT}pp):")
P(f"    Embellishment {emb_pct}% vs audit {TGT_EMB_PCT}%  ({'OK' if emb_ok else 'MISS'})  [{emb_n} companies]")
P(f"    Hard Cover    {hc_pct}% vs audit {TGT_HC_PCT}%  ({'OK' if hc_ok else 'MISS'})  [{hc_n} companies]")
P(f"  VERDICT: {'PASS — reproduces the audit; safe to proceed to reclassify + consumer switch' if gate_pass else 'FAIL — STOP, do not switch consumers'}")
P("  JSON -> scripts/db/gate_classifier_dryrun.json")
