"""
How much of the top-revenue customer base does the 2,299 name+email
confirmed match set cover?
"""
import os, sys, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
from dotenv import load_dotenv
from supabase import create_client
from collections import defaultdict

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
load_dotenv(env_path)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
CLIENT_ID = "241d7b99-f099-4557-96e5-212c4af10812"

def _normalise(name):
    return re.sub(r'[^a-z0-9]', '', (name or '').lower())

def fetch_all(table, select, filters=None):
    rows = []
    offset = 0
    while True:
        q = sb.table(table).select(select).eq('client_id', CLIENT_ID)
        if filters:
            for f in filters:
                q = f(q)
        page = q.range(offset, offset + 999).execute()
        batch = page.data or []
        rows.extend(batch)
        if not batch:
            break
        offset += len(batch)
    return rows

# 1. Rebuild the name-confirmed 1:1 match set (same logic as diagnose_email_join.py)
print("[1/3] Building name-confirmed match set...")
qb_emails = fetch_all('qb_unique_emails', 'email, qb_customer_id', [
    lambda q: q.eq('hide', False),
    lambda q: q.eq('email_invalid', False),
    lambda q: q.not_.is_('qb_customer_id', 'null'),
])
contacts = fetch_all('customer_contacts', 'email_address, customer_company_id', [
    lambda q: q.not_.is_('customer_company_id', 'null'),
])

email_to_qb: dict[str, set] = defaultdict(set)
for ue in qb_emails:
    email = (ue.get('email') or '').strip().lower()
    qb_cid = ue.get('qb_customer_id')
    if email and qb_cid:
        email_to_qb[email].add(str(qb_cid).strip())

email_to_sb: dict[str, set] = defaultdict(set)
for cc in contacts:
    email = (cc.get('email_address') or '').strip().lower()
    cid = cc.get('customer_company_id')
    if email and cid:
        email_to_sb[email].add(cid)

sb_to_qb: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
qb_to_sb: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
for email in email_to_qb.keys() & email_to_sb.keys():
    for sb_cid in email_to_sb[email]:
        for qb_cid in email_to_qb[email]:
            sb_to_qb[sb_cid][qb_cid].append(email)
            qb_to_sb[qb_cid][sb_cid].append(email)

# Get 1:1 matches
one_to_one = []
for sb_cid, qb_map in sb_to_qb.items():
    if len(qb_map) == 1:
        qb_cid = list(qb_map.keys())[0]
        if len(qb_to_sb.get(qb_cid, {})) == 1:
            one_to_one.append((sb_cid, qb_cid, qb_map[qb_cid]))

# Fetch QB customer names
qb_info = {}
offset = 0
while True:
    page = sb.table('qb_customers').select(
        'qb_record_id, customer_key_id, customer_name, customer_code, total_invoiced'
    ).eq('client_id', CLIENT_ID).range(offset, offset + 999).execute()
    rows = page.data or []
    for r in rows:
        for key in ['qb_record_id', 'customer_key_id']:
            v = r.get(key)
            if v:
                qb_info[str(v)] = r
    if not rows:
        break
    offset += len(rows)

# Fetch SB company names
sb_ids = [x[0] for x in one_to_one]
sb_data = {}
for i in range(0, len(sb_ids), 500):
    batch = sb_ids[i:i+500]
    resp = sb.table('customer_companies').select('id, company_name').in_('id', batch).execute()
    for c in (resp.data or []):
        sb_data[c['id']] = c

# Filter to name-confirmed
name_confirmed_sb_ids = set()
name_confirmed_qb_ids = set()
name_confirmed_pairs = []
for sb_cid, qb_cid, emails in one_to_one:
    sb_name = sb_data.get(sb_cid, {}).get('company_name', '')
    qi = qb_info.get(qb_cid, {})
    qb_name = qi.get('customer_name', '')
    sb_norm = _normalise(sb_name)
    qb_norm = _normalise(qb_name)
    if sb_norm and qb_norm and (sb_norm in qb_norm or qb_norm in sb_norm or sb_norm == qb_norm):
        name_confirmed_sb_ids.add(sb_cid)
        name_confirmed_qb_ids.add(qb_cid)
        name_confirmed_pairs.append((sb_cid, qb_cid, emails, sb_name, qb_name, qi))

print(f"  Name-confirmed 1:1 matches: {len(name_confirmed_pairs)}")

# 2. Fetch top-revenue companies (current matched data)
print("\n[2/3] Fetching current QB revenue data...")
all_qb_custs = fetch_all('qb_customers', 'id, qb_record_id, customer_key_id, customer_name, customer_code, total_invoiced, matched_company_id')

# Current matches: company -> total revenue
current_company_revenue: dict[str, float] = defaultdict(float)
for qc in all_qb_custs:
    cid = qc.get('matched_company_id')
    rev = float(qc.get('total_invoiced') or 0)
    if cid and rev:
        current_company_revenue[cid] += rev

# Name-confirmed matches: company -> total revenue
confirmed_company_revenue: dict[str, float] = defaultdict(float)
for sb_cid, qb_cid, emails, sb_name, qb_name, qi in name_confirmed_pairs:
    rev = float(qi.get('total_invoiced') or 0)
    confirmed_company_revenue[sb_cid] += rev

# 3. Revenue coverage analysis
print("\n[3/3] Revenue coverage analysis...")

# Top 100 by current matched revenue
top_current = sorted(current_company_revenue.items(), key=lambda x: -x[1])[:100]
top_current_ids = {cid for cid, _ in top_current}
top_current_covered = top_current_ids & name_confirmed_sb_ids

print(f"\n  Current top 100 revenue companies (by existing matches):")
print(f"    Covered by name-confirmed set: {len(top_current_covered)}/{len(top_current)}")
total_top100_rev = sum(r for _, r in top_current)
covered_rev = sum(r for cid, r in top_current if cid in name_confirmed_sb_ids)
print(f"    Revenue covered: ${covered_rev:,.0f} / ${total_top100_rev:,.0f} ({covered_rev/total_top100_rev*100:.1f}%)")

# Overall revenue coverage
total_matched_rev = sum(current_company_revenue.values())
total_confirmed_rev = sum(confirmed_company_revenue.values())
print(f"\n  Overall revenue:")
print(f"    Current matched (all methods):  ${total_matched_rev:>14,.0f}")
print(f"    Name-confirmed email matches:   ${total_confirmed_rev:>14,.0f} ({total_confirmed_rev/total_matched_rev*100:.1f}%)")

# Show top 30 revenue companies and their coverage status
print(f"\n  Top 30 revenue companies - coverage check:")
print(f"  {'Rank':>4} {'Company':<30} {'Revenue':>14} {'Covered?':<10} QB Customer")
print(f"  {'-'*100}")

# Get SB names for top companies
top_ids = [cid for cid, _ in top_current[:30]]
top_names = {}
for i in range(0, len(top_ids), 500):
    batch = top_ids[i:i+500]
    resp = sb.table('customer_companies').select('id, company_name').in_('id', batch).execute()
    for c in (resp.data or []):
        top_names[c['id']] = c.get('company_name', '?')

for rank, (cid, rev) in enumerate(top_current[:30], 1):
    sb_name = top_names.get(cid, '?')[:29]
    covered = 'YES' if cid in name_confirmed_sb_ids else 'NO'
    # Find matched QB customer name if covered
    qb_match = ''
    if cid in name_confirmed_sb_ids:
        for sb_c, qb_c, _, _, qn, _ in name_confirmed_pairs:
            if sb_c == cid:
                qb_match = qn[:30]
                break
    print(f"  {rank:>4} {sb_name:<30} ${rev:>13,.0f} {covered:<10} {qb_match}")

# Revenue bands
print(f"\n  Revenue band coverage:")
bands = [
    ('>$500K', 500000),
    ('>$200K', 200000),
    ('>$100K', 100000),
    ('>$50K', 50000),
    ('>$10K', 10000),
    ('All', 0),
]
for label, threshold in bands:
    companies_in_band = {cid for cid, rev in current_company_revenue.items() if rev > threshold}
    covered = companies_in_band & name_confirmed_sb_ids
    band_rev = sum(r for cid, r in current_company_revenue.items() if r > threshold)
    covered_band_rev = sum(confirmed_company_revenue.get(cid, 0) for cid in covered)
    pct = len(covered)/len(companies_in_band)*100 if companies_in_band else 0
    rev_pct = covered_band_rev/band_rev*100 if band_rev else 0
    print(f"    {label:<10} {len(covered):>5}/{len(companies_in_band):<5} companies ({pct:>5.1f}%)  "
          f"${covered_band_rev:>12,.0f}/${band_rev:>12,.0f} revenue ({rev_pct:>5.1f}%)")

print("\nDone!")
