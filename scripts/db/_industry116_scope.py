"""13.2 scope confirmation (read-only): how many active 'Not Selected' customers, at which grain.
Uses POST-13.7 clean capability precedence (capability_tags classifier-first, qb fills gaps)."""
import os, sys, io, time
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, "backend")
from dotenv import load_dotenv
from supabase import create_client
e = "backend/.env.production" if os.path.exists("backend/.env.production") else "backend/.env"
load_dotenv(e)
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
C8 = "241d7b99-f099-4557-96e5-212c4af10812"
NO_INDUSTRY = {"", "not selected"}
WEAK = {"small business or individual", "extinct"}


def norm(s):
    return " ".join((s or "").strip().split())


def fetch_all(table, select):
    rows, off = [], 0
    while True:
        b = sb.table(table).select(select).eq("client_id", C8).order("id").range(off, off + 999).execute().data or []
        rows += b
        if len(b) < 1000:
            break
        off += 1000
    return rows


qc = fetch_all("qb_customers", "industry, customer_name, matched_company_id")
for r in qc:
    r["ind"] = norm(r.get("industry"))

# 12-mo revenue per company (rolling from today 2026-06-14)
sb.rpc("exec_sql", {"query": """CREATE OR REPLACE FUNCTION _tmp_rev116(p uuid) RETURNS jsonb LANGUAGE sql STABLE
SET search_path=public SET statement_timeout='240s' AS $fn$
SELECT coalesce(jsonb_object_agg(cid, r12),'{}') FROM (
  SELECT matched_company_id cid, round(sum(cost_plus_price)::numeric,2) r12 FROM qb_operations
  WHERE client_id=p AND matched_company_id IS NOT NULL AND date_accepted >= DATE '2025-06-14'
  GROUP BY 1 HAVING sum(cost_plus_price) > 0) t; $fn$;"""}).execute()
sb.rpc("exec_sql", {"query": "NOTIFY pgrst,'reload schema'"}).execute(); time.sleep(2)
rev = sb.rpc("_tmp_rev116", {"p": C8}).execute().data or {}
sb.rpc("exec_sql", {"query": "DROP FUNCTION IF EXISTS _tmp_rev116(uuid)"}).execute()
comp_rev = {k: float(v) for k, v in rev.items()}


def is_notsel(ind):
    return ind.lower() in NO_INDUSTRY


def is_blank_or_weak(ind):
    return ind.lower() in NO_INDUSTRY or ind.lower() in WEAK


# company best-industry (prefer usable)
def usable(ind):
    lo = ind.lower()
    return ind and lo not in NO_INDUSTRY and lo not in WEAK


comp_ind = {}
for r in qc:
    cid = r.get("matched_company_id")
    if not cid:
        continue
    if cid not in comp_ind or (usable(r["ind"]) and not usable(comp_ind[cid])):
        comp_ind[cid] = r["ind"]

active_companies = set(comp_rev)  # companies with 12-mo revenue > 0
print(f"companies with 12-mo revenue (>0, from 2025-06-14): {len(active_companies)}")

# --- COMPANY grain ---
co_notsel_active = [c for c in active_companies if comp_ind.get(c, "").lower() in NO_INDUSTRY]
co_blankweak_active = [c for c in active_companies if is_blank_or_weak(comp_ind.get(c, ""))]
print(f"\nCOMPANY grain (matched_company_id):")
print(f"  active + industry 'Not Selected'/blank: {len(co_notsel_active)}")
print(f"  active + Not-Selected/blank/weak:       {len(co_blankweak_active)}")

# --- qb_customers grain ---
qc_notsel_active = [r for r in qc if r.get("matched_company_id") in active_companies and is_notsel(r["ind"])]
qc_blankweak_active = [r for r in qc if r.get("matched_company_id") in active_companies and is_blank_or_weak(r["ind"])]
# dedupe companies behind the customer rows
qc_notsel_companies = {r["matched_company_id"] for r in qc_notsel_active}
print(f"\nqb_customers grain (one row per customer):")
print(f"  active + 'Not Selected'/blank: {len(qc_notsel_active)} customer rows  ({len(qc_notsel_companies)} distinct companies)")
print(f"  active + Not-Selected/blank/weak: {len(qc_blankweak_active)} customer rows")

# revenue spread of the company-grain Not-Selected-active set
revs = sorted((comp_rev[c] for c in co_notsel_active), reverse=True)
print(f"\nrevenue of the {len(co_notsel_active)} company-grain Not-Selected-active companies:")
print(f"  total ${round(sum(revs)):,} | max ${round(revs[0]):,} | median ${round(revs[len(revs)//2]):,} | min ${round(revs[-1]):,}" if revs else "  (none)")
print(f"  >= $10k: {sum(1 for r in revs if r>=10000)} | >= $5k: {sum(1 for r in revs if r>=5000)} | >= $1k: {sum(1 for r in revs if r>=1000)}")
