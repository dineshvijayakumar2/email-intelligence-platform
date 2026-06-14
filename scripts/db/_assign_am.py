"""
THROWAWAY (read-only). Step 1+2 for per-AM outreach docs.
 1) Assign each of the 50 cards to an AM via QB am_customer (MODE over the customer's
    operations = authority). Flag: no-AM, AM-outside-the-six, split-ownership. No guessing.
 2) Email-grounding per card from outreach_cards_50.json (value-contact engagement + timing
    + email presence). Confirms Mary/Peter (no AM mailbox) thin-contact concern.
Writes card_am_assignment.json; prints counts, grounding split, flags.
"""
import os, sys, io, json, time
from collections import defaultdict, Counter
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
SIX = ["Nic", "Linda", "Ehab", "Kenneth", "Mary", "Peter"]
FIRST = {n.lower(): n for n in SIX}
SPLIT_THRESHOLD = 0.60      # mode must hold >=60% of non-null AM ops, else flag split

CARDS = json.load(open(os.path.join(HERE, "outreach_cards_50.json"), encoding="utf-8"))["cards"]
cards = sorted(CARDS, key=lambda c: c["rank"])
cids = [c["company_id"] for c in cards]


def with_retry(build, tries=5):
    global sb
    for i in range(tries):
        try:
            return build()
        except Exception as e:
            if i == tries - 1:
                raise
            print(f"  retry {i+1} after {type(e).__name__}", flush=True)
            time.sleep(2 * (i + 1))
            sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


def exec_ddl(q):
    return with_retry(lambda: sb.rpc("exec_sql", {"query": q}).execute())


# Correction 2 (2026-06-12): assign by RECENCY-WEIGHTED JOB MANAGER (am_job, last 12 months),
# not am_customer-mode. Jeff: reps self-assign am_customer for commission, so the recent job
# manager is the truth. Basis ladder: am_job last-12mo -> am_job all-time -> am_customer. Ties
# broken by the single most-recent job's am_job. This auto-resolves the departed-AM accounts
# (Jet->Nic, Jefferies->Ehab, Forsight->Nic) and the active ones (Ball&Doggett->Kenneth, etc.).
CUT = "2025-06-11"   # 12 months before TODAY (2026-06-11)
RPC = f"""
CREATE OR REPLACE FUNCTION _tmp_am_recency(p_client uuid, p_cids uuid[])
RETURNS jsonb LANGUAGE sql STABLE
SET search_path = public SET statement_timeout = '120s' AS $fn$
WITH jb AS (
  SELECT matched_company_id cid, job_no,
         max(btrim(coalesce(am_job,''))) am_job,
         max(btrim(coalesce(am_customer,''))) am_cust,
         max(date_accepted) d
  FROM qb_operations
  WHERE client_id = p_client AND matched_company_id = ANY(p_cids) AND job_no IS NOT NULL
  GROUP BY 1, 2),
last12 AS (SELECT cid, am_job am, count(*) c FROM jb WHERE d >= DATE '{CUT}' AND am_job <> '' GROUP BY 1, 2),
allj   AS (SELECT cid, am_job am, count(*) c FROM jb WHERE am_job <> '' GROUP BY 1, 2),
custc  AS (SELECT cid, am_cust am, count(*) c FROM jb WHERE am_cust <> '' GROUP BY 1, 2),
recent AS (SELECT DISTINCT ON (cid) cid, am_job FROM jb WHERE am_job <> '' ORDER BY cid, d DESC),
ids    AS (SELECT DISTINCT cid FROM jb)
SELECT coalesce(jsonb_agg(jsonb_build_object(
  'cid', ids.cid,
  'last12', (SELECT jsonb_object_agg(am, c) FROM last12 WHERE last12.cid = ids.cid),
  'allj',   (SELECT jsonb_object_agg(am, c) FROM allj   WHERE allj.cid   = ids.cid),
  'cust',   (SELECT jsonb_object_agg(am, c) FROM custc  WHERE custc.cid  = ids.cid),
  'recent_am', (SELECT am_job FROM recent WHERE recent.cid = ids.cid))), '[]'::jsonb)
FROM ids;
$fn$;
"""
print("Creating throwaway RPC + pulling recency-weighted am_job...", flush=True)
exec_ddl(RPC)
exec_ddl("NOTIFY pgrst, 'reload schema'")
time.sleep(2)
am_json = with_retry(lambda: sb.rpc("_tmp_am_recency", {"p_client": C8, "p_cids": cids}).execute()).data or []
am_by_cid = {r["cid"]: r for r in am_json}


def map_am(raw):
    if not raw:
        return None
    return FIRST.get(raw.split()[0].lower())


# ── grounding from cards JSON ───────────────────────────────────────────────
def grounding(card):
    te = card["back"]["timing_evidence"]
    vc = card["back"]["contact_evidence"]["value_contact"]
    email_present = te["email_recency"]["days_since_last_email"] is not None
    timing_avail = te["days_since_last_order"] is not None
    if vc:
        active = (vc["em_from"] + vc["em_to"]) > 0
        contact_status = "engaged" if active else "qb_only_no_email"
    else:
        contact_status = "none"
    full = contact_status == "engaged" and timing_avail and email_present
    return {"email_present": email_present, "timing_available": timing_avail,
            "contact_status": contact_status, "email_grounded": full}


# ── assign (recency-weighted am_job) ────────────────────────────────────────
out_cards = []
per_am = defaultdict(list)
flags = {"no_am": [], "outside_six": [], "split": []}
for card in cards:
    cid = card["company_id"]
    name = card["front"]["customer"]
    r = am_by_cid.get(cid, {})
    last12 = r.get("last12") or {}
    allj = r.get("allj") or {}
    custd = r.get("cust") or {}
    recent_am = r.get("recent_am")
    if last12:
        basis, ams = "am_job_last12mo", last12
    elif allj:
        basis, ams = "am_job_alltime", allj
    else:
        basis, ams = "am_customer", custd
    g = grounding(card)
    rec = {"rank": card["rank"], "customer": name, "company_id": cid,
           "pitch": card["front"]["pitch"], "confidence": card["front"]["confidence"],
           "lift": card["factors"]["lift"], "timing_status": card["back"]["timing_evidence"]["status"],
           "timing_label": card["front"]["timing"],
           "am_basis": basis, "am_distribution": ams, "recent_job_am": recent_am,
           "grounding": g}
    nonnull = sum(ams.values())
    if nonnull == 0:
        rec["am"] = None
        rec["flag"] = "no_am"
        flags["no_am"].append(name)
        out_cards.append(rec)
        continue
    # mode of the recency basis; ties broken by the single most-recent job's manager
    items = sorted(ams.items(), key=lambda kv: -kv[1])
    maxc = items[0][1]
    tied = [a for a, c in items if c == maxc]
    mode_raw = recent_am if (len(tied) > 1 and recent_am in tied) else items[0][0]
    mode_share = ams[mode_raw] / nonnull
    mapped = map_am(mode_raw)
    rec["am_mode_raw"] = mode_raw
    rec["am_mode_share"] = round(mode_share, 3)
    if mapped is None:
        rec["am"] = None
        rec["flag"] = "outside_six"
        flags["outside_six"].append(f"{name} -> {mode_raw}")
        out_cards.append(rec)
        continue
    rec["am"] = mapped
    rec["flag"] = None
    if mode_share < SPLIT_THRESHOLD:
        rec["flag"] = "split"
        second = sorted(ams.items(), key=lambda kv: -kv[1])
        rec["split_detail"] = {k: v for k, v in second}
        flags["split"].append(f"{name}: " + ", ".join(f"{map_am(k) or k} {v}" for k, v in second))
    per_am[mapped].append(rec)
    out_cards.append(rec)

# ── report ──────────────────────────────────────────────────────────────────
print("\n" + "=" * 92)
print("STEP 1 — AM ASSIGNMENT (recency-weighted am_job: last-12mo -> all-time -> am_customer)")
print("=" * 92)
assigned = sum(len(v) for v in per_am.values())
for am in SIX:
    lst = per_am.get(am, [])
    print(f"  {am:<9} {len(lst):>2} customers" + ("   (no mailbox — see Step 2)" if am in ("Mary", "Peter") else ""))
print(f"  {'TOTAL':<9} {assigned:>2} assigned to the six")
print(f"  unassigned/flagged: no_am={len(flags['no_am'])}  outside_six={len(flags['outside_six'])}")

print("\n  customer -> AM:")
for rec in out_cards:
    f = f"  ⚠{rec['flag']}" if rec.get("flag") else ""
    print(f"   #{rec['rank']:>2} {rec['customer'][:34]:<35} -> {str(rec.get('am')):<8} "
          f"(mode {rec.get('am_mode_raw','—')}, {int(rec.get('am_mode_share',0)*100)}%)" + f)

print("\n" + "=" * 92)
print("STEP 2 — EMAIL-GROUNDING per AM (email-grounded = engaged value-contact + timing + email present)")
print("=" * 92)
print(f"  {'AM':<9} {'cust':>4} {'grounded':>9} {'pitch-only':>11} {'any-email':>10}")
grounding_split = {}
for am in SIX:
    lst = per_am.get(am, [])
    if not lst:
        continue
    grounded = sum(1 for r in lst if r["grounding"]["email_grounded"])
    pitchonly = len(lst) - grounded
    anyemail = sum(1 for r in lst if r["grounding"]["email_present"])
    grounding_split[am] = {"customers": len(lst), "email_grounded": grounded,
                           "pitch_only": pitchonly, "any_email_data": anyemail}
    print(f"  {am:<9} {len(lst):>4} {grounded:>9} {pitchonly:>11} {anyemail:>10}")

# Mary/Peter explicit email-data confirmation
for am in ("Mary", "Peter"):
    lst = per_am.get(am, [])
    if not lst:
        print(f"\n  {am}: no customers assigned.")
        continue
    anyemail = sum(1 for r in lst if r["grounding"]["email_present"])
    print(f"\n  {am}: {len(lst)} customers; {anyemail} have ANY email data in the system "
          + ("→ some email data exists (shared/other mailbox)" if anyemail else "→ NO email data at all (no mailbox)"))

print("\n" + "=" * 92)
print("FLAGS")
print("=" * 92)
print(f"  no AM ({len(flags['no_am'])}): {flags['no_am'] or '-'}")
print(f"  AM outside the six ({len(flags['outside_six'])}): {flags['outside_six'] or '-'}")
print(f"  split ownership ({len(flags['split'])}):")
for s in flags["split"]:
    print(f"     {s}")
print(f"\n  accounted for: {len(out_cards)}/50  (assigned {assigned} + no_am {len(flags['no_am'])} + outside_six {len(flags['outside_six'])})")

result = {"generated_for": "per-AM outreach docs", "six_ams": SIX,
          "split_threshold": SPLIT_THRESHOLD,
          "per_am_counts": {am: len(per_am.get(am, [])) for am in SIX},
          "grounding_split": grounding_split,
          "flags": flags, "assignment_basis": "recency-weighted am_job (last-12mo -> all-time -> am_customer)",
          "basis_counts": dict(Counter(c.get("am_basis") for c in out_cards)),
          "cards": out_cards}
json.dump(result, open(os.path.join(HERE, "card_am_assignment.json"), "w", encoding="utf-8"), indent=2, default=str)
print("\nJSON -> scripts/db/card_am_assignment.json")
exec_ddl("DROP FUNCTION IF EXISTS _tmp_am_recency(uuid, uuid[])")
exec_ddl("NOTIFY pgrst, 'reload schema'")
print("Done.")
