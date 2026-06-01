"""Clean up stale candidates and contaminated company matches."""
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


# ── Fix 1: Mark stale candidates as reviewed ──
print("=" * 70)
print("FIX 1: STALE CANDIDATES")
print("=" * 70)

print("\nFetching unreviewed candidates...")
candidates = fetch_all('qb_match_candidates', 'id, qb_record_id', [
    lambda q: q.eq('reviewed', False),
])
print(f"  {len(candidates)} unreviewed candidates")

print("Fetching matched QB customers...")
qb_matched = fetch_all('qb_customers', 'qb_record_id, matched_company_id', [
    lambda q: q.not_.is_('matched_company_id', 'null'),
])
matched_qb_ids = {qc['qb_record_id'] for qc in qb_matched}

stale_ids = [c['id'] for c in candidates if c['qb_record_id'] in matched_qb_ids]
print(f"  {len(stale_ids)} stale candidates (QB already matched)")

if stale_ids:
    print(f"\nMarking {len(stale_ids)} stale candidates as reviewed...")
    marked = 0
    for i in range(0, len(stale_ids), 100):
        batch = stale_ids[i:i+100]
        sb.table('qb_match_candidates').update({
            'reviewed': True,
            'accepted': False,
        }).in_('id', batch).execute()
        marked += len(batch)
        print(f"  Batch {i//100 + 1}: marked {len(batch)} (total: {marked})")
    print(f"Done. Marked {marked} stale candidates as reviewed.")

# ── Fix 2: Decontaminate ──
print("\n" + "=" * 70)
print("FIX 2: DECONTAMINATION")
print("=" * 70)

print("\nBuilding company->QB mapping...")
company_to_qb = defaultdict(list)
for qc in qb_matched:
    company_to_qb[qc['matched_company_id']].append(qc)

contaminated = {cid: qcs for cid, qcs in company_to_qb.items() if len(qcs) > 1}
print(f"  {len(contaminated)} companies have >1 QB customer")

# For each contaminated company, keep the highest-revenue QB customer, unmatch the rest
print("\nFetching revenue data for contaminated QB customers...")
all_contaminated_qb_ids = []
for qcs in contaminated.values():
    all_contaminated_qb_ids.extend(qc['qb_record_id'] for qc in qcs)

qb_revenue = {}
for i in range(0, len(all_contaminated_qb_ids), 500):
    batch = all_contaminated_qb_ids[i:i+500]
    resp = sb.table('qb_customers').select('qb_record_id, total_invoiced, customer_name').eq(
        'client_id', CLIENT_ID
    ).in_('qb_record_id', batch).execute()
    for r in (resp.data or []):
        qb_revenue[r['qb_record_id']] = {
            'revenue': r.get('total_invoiced') or 0,
            'name': r.get('customer_name', ''),
        }

unmatched_count = 0
unmatched_ids = []
kept_count = 0

for cid, qcs in contaminated.items():
    # Sort by revenue descending, keep highest
    sorted_qcs = sorted(qcs, key=lambda x: qb_revenue.get(x['qb_record_id'], {}).get('revenue', 0), reverse=True)
    keeper = sorted_qcs[0]
    excess = sorted_qcs[1:]

    kept_count += 1
    for qc in excess:
        unmatched_ids.append(qc['qb_record_id'])

print(f"  Keeping {kept_count} highest-revenue QB matches")
print(f"  Unmatching {len(unmatched_ids)} excess QB customers")

if unmatched_ids:
    print(f"\nClearing matched_company_id on {len(unmatched_ids)} excess QB customers...")
    cleared = 0
    for i in range(0, len(unmatched_ids), 100):
        batch = unmatched_ids[i:i+100]
        sb.table('qb_customers').update({
            'matched_company_id': None,
        }).eq('client_id', CLIENT_ID).in_('qb_record_id', batch).execute()
        cleared += len(batch)
        print(f"  Batch {i//100 + 1}: cleared {len(batch)} (total: {cleared})")
    print(f"Done. Cleared {cleared} excess matches.")

# Also clear stale QB fields on the SB company if the kept match is for a different name
print(f"\n\nSummary:")
print(f"  Stale candidates dismissed: {len(stale_ids)}")
print(f"  Contaminated companies fixed: {len(contaminated)}")
print(f"  Excess QB matches cleared: {len(unmatched_ids)}")
