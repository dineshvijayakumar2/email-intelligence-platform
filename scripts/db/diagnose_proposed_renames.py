"""
Phase A: Proposed Renames Table.

For each QB customer with email history, find the majority SB company
via email overlap, classify confidence, and produce a rename proposal.

Read-only -- no writes.
"""
import os, sys, csv
from collections import defaultdict
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
from dotenv import load_dotenv
from supabase import create_client

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
load_dotenv(env_path)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
CLIENT_ID = "241d7b99-f099-4557-96e5-212c4af10812"

def fetch_all(table, select, filters=None, not_null=None):
    """Paginate through a Supabase table."""
    rows = []
    offset = 0
    while True:
        q = sb.table(table).select(select).eq('client_id', CLIENT_ID)
        if filters:
            for k, v in filters.items():
                q = q.eq(k, v)
        if not_null:
            for col in not_null:
                q = q.not_.is_(col, 'null')
        resp = q.range(offset, offset + 999).execute()
        rows.extend(resp.data or [])
        if len(resp.data or []) < 1000:
            break
        offset += 1000
    return rows

print("=" * 100)
print("PHASE A: PROPOSED RENAMES (read-only)")
print("=" * 100)

# 1. Fetch QB unique emails (valid, not hidden)
print("\n1. Fetching data...")
qb_emails_raw = fetch_all('qb_unique_emails', 'qb_customer_id, email',
                           filters={'hide': False, 'email_invalid': False})
print(f"   {len(qb_emails_raw)} valid QB unique emails")

# 2. Fetch customer_contacts with company assignment
contacts_raw = fetch_all('customer_contacts', 'email_address, customer_company_id',
                          not_null=['customer_company_id'])
print(f"   {len(contacts_raw)} contacts with company")

# 3. Build email -> sb_company_id map
email_to_sb = {}
for c in contacts_raw:
    email = (c.get('email_address') or '').strip().lower()
    cid = c.get('customer_company_id')
    if email and cid:
        email_to_sb[email] = cid

print(f"   {len(email_to_sb)} unique emails mapped to SB companies")

# 4. Join: for each QB customer, count contacts per SB company
#    qb_customer_id -> {sb_company_id: contact_count}
qb_to_sb_counts = defaultdict(lambda: defaultdict(int))
for qe in qb_emails_raw:
    qb_cid = qe.get('qb_customer_id')
    email = (qe.get('email') or '').strip().lower()
    if not qb_cid or not email:
        continue
    sb_cid = email_to_sb.get(email)
    if sb_cid:
        qb_to_sb_counts[qb_cid][sb_cid] += 1

print(f"   {len(qb_to_sb_counts)} QB customers resolve to at least 1 SB company")

# 5. Majority vote: for each QB customer, pick top SB company + compute confidence
proposals = []
for qb_cid, sb_counts in qb_to_sb_counts.items():
    total = sum(sb_counts.values())
    ranked = sorted(sb_counts.items(), key=lambda x: x[1], reverse=True)
    top_sb_id, top_count = ranked[0]
    pct = top_count / total if total else 0
    runner_up = ranked[1] if len(ranked) > 1 else None

    if pct >= 0.75:
        bucket = 'auto_rename'
    elif pct >= 0.50:
        bucket = 'review'
    else:
        bucket = 'low_confidence'

    proposals.append({
        'qb_customer_key_id': qb_cid,
        'sb_company_id': top_sb_id,
        'contact_count': top_count,
        'total_contacts': total,
        'pct': round(pct * 100),
        'bucket': bucket,
        'sb_company_count': len(ranked),
        'runner_up_id': runner_up[0] if runner_up else None,
        'runner_up_count': runner_up[1] if runner_up else 0,
    })

# 6. Fetch QB customer info (name, revenue, current match)
print("2. Fetching QB customer details...")
qb_key_ids = [p['qb_customer_key_id'] for p in proposals]
qb_info = {}
for i in range(0, len(qb_key_ids), 500):
    batch = qb_key_ids[i:i+500]
    resp = sb.table('qb_customers').select(
        'customer_key_id, customer_name, total_invoiced, matched_company_id'
    ).eq('client_id', CLIENT_ID).in_('customer_key_id', batch).execute()
    for r in (resp.data or []):
        qb_info[r['customer_key_id']] = r

# 7. Fetch SB company info (name)
print("3. Fetching SB company details...")
all_sb_ids = set()
for p in proposals:
    all_sb_ids.add(p['sb_company_id'])
    if p['runner_up_id']:
        all_sb_ids.add(p['runner_up_id'])
# Also add current matched companies
for qi in qb_info.values():
    if qi.get('matched_company_id'):
        all_sb_ids.add(qi['matched_company_id'])

sb_info = {}
all_sb_list = list(all_sb_ids)
for i in range(0, len(all_sb_list), 500):
    batch = all_sb_list[i:i+500]
    resp = sb.table('customer_companies').select(
        'id, company_name'
    ).in_('id', batch).execute()
    for r in (resp.data or []):
        sb_info[r['id']] = r.get('company_name', '?')

# 8. Enrich proposals
for p in proposals:
    qi = qb_info.get(p['qb_customer_key_id'], {})
    p['qb_name'] = qi.get('customer_name', '?')
    p['revenue'] = float(qi.get('total_invoiced') or 0)
    p['current_match_id'] = qi.get('matched_company_id')
    p['current_sb_name'] = sb_info.get(qi.get('matched_company_id'), None)
    p['proposed_sb_name'] = sb_info.get(p['sb_company_id'], '?')
    p['runner_up_name'] = sb_info.get(p['runner_up_id'], None) if p['runner_up_id'] else None

    # Classify the rename action
    if p['current_match_id'] == p['sb_company_id']:
        if p['qb_name'].lower().strip() == p['proposed_sb_name'].lower().strip():
            p['action'] = 'no_change'
        else:
            p['action'] = 'rename_only'
    elif p['current_match_id'] is None:
        p['action'] = 'new_match'
    else:
        p['action'] = 'rematch+rename'

proposals.sort(key=lambda x: x['revenue'], reverse=True)

# 9. Summary stats
print(f"\n{'='*100}")
print("SUMMARY")
print(f"{'='*100}")

bucket_stats = defaultdict(lambda: {'count': 0, 'revenue': 0})
action_stats = defaultdict(lambda: {'count': 0, 'revenue': 0})
for p in proposals:
    bucket_stats[p['bucket']]['count'] += 1
    bucket_stats[p['bucket']]['revenue'] += p['revenue']
    action_stats[p['action']]['count'] += 1
    action_stats[p['action']]['revenue'] += p['revenue']

print(f"\n  CONFIDENCE BUCKETS:")
print(f"  {'Bucket':<20} {'Count':>8} {'Revenue':>15}")
print(f"  {'-'*20} {'-'*8} {'-'*15}")
for b in ['auto_rename', 'review', 'low_confidence']:
    s = bucket_stats[b]
    print(f"  {b:<20} {s['count']:>8} ${s['revenue']:>13,.0f}")
print(f"  {'TOTAL':<20} {sum(s['count'] for s in bucket_stats.values()):>8} ${sum(s['revenue'] for s in bucket_stats.values()):>13,.0f}")

print(f"\n  ACTIONS NEEDED:")
print(f"  {'Action':<20} {'Count':>8} {'Revenue':>15}")
print(f"  {'-'*20} {'-'*8} {'-'*15}")
for a in ['no_change', 'rename_only', 'new_match', 'rematch+rename']:
    s = action_stats[a]
    print(f"  {a:<20} {s['count']:>8} ${s['revenue']:>13,.0f}")

# 10. Display tables by bucket
for bucket_name in ['auto_rename', 'review', 'low_confidence']:
    bucket_items = [p for p in proposals if p['bucket'] == bucket_name]
    if not bucket_items:
        continue

    print(f"\n{'='*100}")
    print(f"  {bucket_name.upper()} ({len(bucket_items)} proposals)")
    print(f"{'='*100}")
    print(f"  {'QB Name':<32} {'Current SB Name':<28} {'Proposed SB':<28} {'Rev':>10} {'Pct':>4} {'Contacts':>8} {'Action':<16}")
    print(f"  {'-'*32} {'-'*28} {'-'*28} {'-'*10} {'-'*4} {'-'*8} {'-'*16}")

    shown = 0
    for p in bucket_items:
        if shown >= 60:
            print(f"  ... and {len(bucket_items) - shown} more")
            break
        current = (p['current_sb_name'] or '-')[:28]
        proposed = p['proposed_sb_name'][:28]
        marker = '' if p['action'] == 'no_change' else ' *'
        print(f"  {p['qb_name'][:32]:<32} {current:<28} {proposed:<28} ${p['revenue']:>8,.0f} {p['pct']:>3}% {p['contact_count']:>3}/{p['total_contacts']:<4} {p['action']:<16}{marker}")
        shown += 1

# 11. Show "rematch+rename" cases (currently matched to WRONG SB company)
rematch_cases = [p for p in proposals if p['action'] == 'rematch+rename']
if rematch_cases:
    print(f"\n{'='*100}")
    print(f"  REMATCH NEEDED: {len(rematch_cases)} QB customers matched to wrong SB company")
    print(f"{'='*100}")
    print(f"  {'QB Name':<30} {'Currently Matched To':<28} {'Should Be':<28} {'Rev':>10} {'Pct':>4} {'Bucket':<15}")
    print(f"  {'-'*30} {'-'*28} {'-'*28} {'-'*10} {'-'*4} {'-'*15}")
    for p in rematch_cases[:40]:
        print(f"  {p['qb_name'][:30]:<30} {(p['current_sb_name'] or '-')[:28]:<28} {p['proposed_sb_name'][:28]:<28} ${p['revenue']:>8,.0f} {p['pct']:>3}% {p['bucket']:<15}")

# 12. Export full table to CSV
csv_path = os.path.join(os.path.dirname(__file__), 'proposed_renames.csv')
with open(csv_path, 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['qb_customer_key_id', 'qb_name', 'revenue', 'sb_company_id', 'current_sb_name',
                'proposed_sb_name', 'contact_count', 'total_contacts', 'pct_match',
                'bucket', 'action', 'sb_company_count', 'runner_up_name', 'runner_up_count',
                'current_match_id'])
    for p in proposals:
        w.writerow([
            p['qb_customer_key_id'], p['qb_name'], p['revenue'], p['sb_company_id'],
            p['current_sb_name'] or '', p['proposed_sb_name'], p['contact_count'],
            p['total_contacts'], p['pct'], p['bucket'], p['action'],
            p['sb_company_count'], p['runner_up_name'] or '', p['runner_up_count'],
            p['current_match_id'] or '',
        ])
print(f"\n  Full table exported to: {csv_path}")
print(f"{'='*100}")
