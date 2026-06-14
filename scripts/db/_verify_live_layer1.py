"""
Step 3c VERIFY (READ-ONLY): confirm the LIVE capability_tags column (post-reclassify) reproduces
the gate numbers under the NEW precedence — classifier opinion ELSE qb_capability_tag.
This reads what was actually WRITTEN (not an in-memory recompute), the §10.12 materialized-layer
check. Pollution caps must match the audit: Embellishment 15.3%, Hard Cover 8.3% (tol 1.0pp).
"""
import os, sys, io, json, time
from collections import defaultdict, Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, "backend")
from dotenv import load_dotenv
from supabase import create_client
e = "backend/.env.production" if os.path.exists("backend/.env.production") else "backend/.env"
load_dotenv(e)
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
C8 = "241d7b99-f099-4557-96e5-212c4af10812"
SUPPORT_FLOOR, CONF_FLOOR, LIFT_FLOOR = 30, 0.25, 1.0
AUDIT = json.load(open("scripts/db/capability_tag_audit.json", encoding="utf-8"))
TGT = {"Embellishment": AUDIT["base_rates"]["corrected"]["Embellishment"],
       "Hard Cover Books": AUDIT["base_rates"]["corrected"]["Hard Cover Books"]}
TOL = 1.0

# NEW precedence in SQL, reading the live written column
CT0 = """CASE WHEN jsonb_typeof(o.capability_tags)='array' AND jsonb_array_length(o.capability_tags)>0
              THEN o.capability_tags->>0
            WHEN jsonb_typeof(o.capability_tags)='string' THEN o.capability_tags#>>'{}'
            ELSE NULL END"""
QB = "nullif(btrim(coalesce(o.qb_capability_tag,'')),'')"

FN = f"""CREATE OR REPLACE FUNCTION _tmp_vlive(p uuid) RETURNS jsonb LANGUAGE sql STABLE
SET search_path=public SET statement_timeout='240s' AS $fn$
WITH op AS (
  SELECT o.matched_company_id cid, o.job_no, COALESCE({CT0}, {QB}) cap
  FROM qb_operations o
  WHERE o.client_id=p AND o.matched_company_id IS NOT NULL AND o.job_no IS NOT NULL)
SELECT coalesce(jsonb_agg(jsonb_build_object('cid',cid,'cap',cap,'j',j)),'[]')
FROM (SELECT cid, cap, count(DISTINCT job_no) j FROM op
      WHERE cap IS NOT NULL AND length(cap)>1 GROUP BY 1,2) t;
$fn$;"""
# (a) coverage + (b) shape-normalization check over ALL rows
SHAPE_FN = f"""CREATE OR REPLACE FUNCTION _tmp_vshape(p uuid) RETURNS jsonb LANGUAGE sql STABLE
SET search_path=public SET statement_timeout='120s' AS $fn$
SELECT jsonb_build_object(
  'total', count(*),
  'array', count(*) FILTER (WHERE jsonb_typeof(o.capability_tags)='array'),
  'string_legacy', count(*) FILTER (WHERE jsonb_typeof(o.capability_tags)='string'),
  'null_or_other', count(*) FILTER (WHERE o.capability_tags IS NULL OR jsonb_typeof(o.capability_tags) NOT IN ('array','string')),
  'empty_array', count(*) FILTER (WHERE o.capability_tags='[]'::jsonb)
) FROM qb_operations o WHERE o.client_id=p;
$fn$;"""
sb.rpc("exec_sql", {"query": FN}).execute()
sb.rpc("exec_sql", {"query": SHAPE_FN}).execute()
sb.rpc("exec_sql", {"query": "NOTIFY pgrst,'reload schema'"}).execute(); time.sleep(2)
rows = sb.rpc("_tmp_vlive", {"p": C8}).execute().data or []
shape = sb.rpc("_tmp_vshape", {"p": C8}).execute().data
sb.rpc("exec_sql", {"query": "DROP FUNCTION IF EXISTS _tmp_vlive(uuid)"}).execute()
sb.rpc("exec_sql", {"query": "DROP FUNCTION IF EXISTS _tmp_vshape(uuid)"}).execute()

comp = defaultdict(dict)
for r in rows:
    comp[r["cid"]][r["cap"]] = int(r["j"])
basket = {cid: {c for c, j in caps.items() if j >= 2} for cid, caps in comp.items()}
basket = {cid: b for cid, b in basket.items() if b}
N = len(basket)
cc = Counter(); pair = defaultdict(int)
for b in basket.values():
    for x in b:
        cc[x] += 1
    for x in b:
        for y in b:
            if x != y:
                pair[(x, y)] += 1
base = {c: (cc[c], round(100 * cc[c] / N, 1)) for c in cc}
rules = []
for X in cc:
    for Y in cc:
        if X == Y or pair.get((X, Y), 0) < SUPPORT_FLOOR:
            continue
        conf = pair[(X, Y)] / cc[X]; lift = conf / (cc[Y] / N)
        if lift >= LIFT_FLOOR and conf >= CONF_FLOOR:
            rules.append({"from": X, "to": Y, "conf": round(conf * 100, 1), "support": pair[(X, Y)], "lift": round(lift, 2)})

ok = {}
for cap, tgt in TGT.items():
    pct = base.get(cap, (0, 0.0))[1]
    ok[cap] = abs(pct - tgt) <= TOL
rates_ok = all(ok.values())
# (a) coverage: every row carries a written capability_tags (none left NULL/other) ;
# (b) shape: zero legacy string scalars remain (all normalized to json arrays)
coverage_ok = (shape["string_legacy"] == 0 and shape["null_or_other"] == 0)
shape_ok = (shape["string_legacy"] == 0)
gate = rates_ok and coverage_ok and shape_ok
json.dump({"universe": N, "base_rates": {k: {"companies": v[0], "pct": v[1]} for k, v in base.items()},
           "rule_count": len(rules), "audit_targets": TGT, "shape": shape,
           "rates_ok": rates_ok, "coverage_ok": coverage_ok, "shape_ok": shape_ok, "pass": gate},
          open("scripts/db/verify_live_layer1.json", "w", encoding="utf-8"), indent=2)

P = print
P("=" * 86); P("STEP 3c — LIVE capability_tags verification (reads written column, new precedence)"); P("=" * 86)
P(f"  (a) coverage: total={shape['total']}  array={shape['array']}  empty_array={shape['empty_array']}")
P(f"  (b) shape:    legacy_string_scalars={shape['string_legacy']} (must be 0)  null/other={shape['null_or_other']} (must be 0)")
P(f"  basket universe: {N}")
for c, (n, p) in sorted(base.items(), key=lambda kv: -kv[1][0]):
    flag = ""
    if c in TGT:
        flag = f"   <- audit {TGT[c]}% ({'OK' if ok[c] else 'MISS'})"
    P(f"  {c:<22}{n:>9}{p:>8}%{flag}")
P(f"\n  surviving rules: {len(rules)}")
P(f"  checks: rates {'OK' if rates_ok else 'MISS'} | coverage {'OK' if coverage_ok else 'FAIL'} | shape {'OK' if shape_ok else 'FAIL'}")
P(f"  VERDICT: {'PASS — live column reproduces the audit; safe to flip consumer precedence' if gate else 'FAIL — STOP'}")
P("  JSON -> scripts/db/verify_live_layer1.json")
