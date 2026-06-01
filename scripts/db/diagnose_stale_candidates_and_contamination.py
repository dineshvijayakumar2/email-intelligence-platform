"""Diagnose stale candidates and contamination for cleanup."""
import os, sys
from collections import defaultdict
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
from dotenv import load_dotenv
from supabase import create_client

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
load_dotenv(env_path)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
CLIENT_ID = '241d7b99-f099-4557-96e5-212c4af10812'


def fetch_all(table, select, filters=None):
    rows, offset = [], 0
    while True:
        q = sb.table(table).select(select).eq('client_id', CLIENT_ID)
        if filters:
            for f in filters:
                q = f(q)
        batch = q.range(offset, offset + 999).execute().data or []
        rows.extend(batch)
        if not batch:
            break
        offset += len(batch)
    return rows


# ── Issue 1: Stale candidates ──
print("=" * 70)
print("ISSUE 1: STALE CANDIDATES (already-matched QB customers with unreviewed candidates)")
print("=" * 70)

print("\n[1a] Fetching unreviewed candidates...")
candidates = fetch_all('qb_match_candidates', 'id, qb_record_id, sb_company_id, match_score, match_method', [
    lambda q: q.eq('reviewed', False),
])
print(f"  {len(candidates)} total unreviewed candidates")

print("[1b] Fetching matched QB customers...")
qb_matched = fetch_all('qb_customers', 'qb_record_id, matched_company_id, customer_name', [
    lambda q: q.not_.is_('matched_company_id', 'null'),
])
matched_qb_ids = {qc['qb_record_id'] for qc in qb_matched}

stale = [c for c in candidates if c['qb_record_id'] in matched_qb_ids]
active = [c for c in candidates if c['qb_record_id'] not in matched_qb_ids]
print(f"\n  Stale (QB already matched): {len(stale)}")
print(f"  Active (QB still unmatched): {len(active)}")

# ── Issue 3: Contamination ──
print("\n" + "=" * 70)
print("ISSUE 3: CONTAMINATION (SB companies with >1 QB customer)")
print("=" * 70)

print("\n[3a] Building company->QB mapping...")
company_to_qb = defaultdict(list)
qb_by_record = {qc['qb_record_id']: qc for qc in qb_matched}

for qc in qb_matched:
    company_to_qb[qc['matched_company_id']].append(qc)

contaminated = {cid: qcs for cid, qcs in company_to_qb.items() if len(qcs) > 1}
print(f"  {len(contaminated)} companies have >1 QB customer (contaminated)")

# Classify contamination
multi_2 = sum(1 for qcs in contaminated.values() if len(qcs) == 2)
multi_3 = sum(1 for qcs in contaminated.values() if len(qcs) == 3)
multi_4plus = sum(1 for qcs in contaminated.values() if len(qcs) >= 4)
total_excess = sum(len(qcs) - 1 for qcs in contaminated.values())

print(f"  2 QB customers: {multi_2}")
print(f"  3 QB customers: {multi_3}")
print(f"  4+ QB customers: {multi_4plus}")
print(f"  Total excess matches to clear: {total_excess}")

# Fetch company names for top contaminated
print("\n[3b] Fetching company details for worst cases...")
worst = sorted(contaminated.items(), key=lambda x: len(x[1]), reverse=True)[:10]
worst_ids = [cid for cid, _ in worst]
if worst_ids:
    resp = sb.table('customer_companies').select('id, company_name, total_emails').in_('id', worst_ids).execute()
    company_names = {r['id']: r for r in (resp.data or [])}

    print("\nTop 10 contaminated companies:")
    for cid, qcs in worst:
        comp = company_names.get(cid, {})
        qb_names = [qc['customer_name'] for qc in qcs]
        print(f"  {comp.get('company_name', 'N/A')} ({len(qcs)} QB): {', '.join(qb_names[:5])}")

# Strategy for decontamination
print("\n[3c] Decontamination strategy analysis...")
# For each contaminated company, the fix is: keep the highest-revenue QB customer,
# unmatch the rest. But we need to check if the "excess" QB customers have their
# own legitimate SB company matches elsewhere.
print("  For each contaminated company:")
print("  - Keep the QB customer with highest total_invoiced")
print("  - Unmatch the rest (set matched_company_id = NULL)")
print("  - The unmatched ones become available for re-matching to correct companies")
