"""
For top revenue companies NOT covered by name-confirmed email matches,
find what QB customers they're currently matched to and why the name check fails.
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

# 1. Rebuild email join (same as before)
print("[1/4] Building email join...")
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

# 2. Get current QB customer matches and revenue
print("[2/4] Fetching QB customers with matches...")
all_qb = fetch_all('qb_customers', 'id, qb_record_id, customer_key_id, customer_name, customer_code, total_invoiced, matched_company_id')

company_revenue: dict[str, float] = defaultdict(float)
company_qb_custs: dict[str, list] = defaultdict(list)
for qc in all_qb:
    cid = qc.get('matched_company_id')
    rev = float(qc.get('total_invoiced') or 0)
    if cid:
        company_revenue[cid] += rev
        company_qb_custs[cid].append(qc)

qb_by_id = {}
for qc in all_qb:
    for key in ['qb_record_id', 'customer_key_id']:
        v = qc.get(key)
        if v:
            qb_by_id[str(v)] = qc

# 3. Identify name-confirmed set
print("[3/4] Identifying name-confirmed set...")
sb_ids = list(set(list(sb_to_qb.keys()) + [cid for cid, _ in sorted(company_revenue.items(), key=lambda x: -x[1])[:100]]))
sb_data = {}
for i in range(0, len(sb_ids), 500):
    batch = sb_ids[i:i+500]
    resp = sb.table('customer_companies').select('id, company_name').in_('id', batch).execute()
    for c in (resp.data or []):
        sb_data[c['id']] = c.get('company_name', '?')

name_confirmed_sb_ids = set()
for sb_cid, qb_map in sb_to_qb.items():
    if len(qb_map) == 1:
        qb_cid = list(qb_map.keys())[0]
        if len(qb_to_sb.get(qb_cid, {})) == 1:
            sb_name = sb_data.get(sb_cid, '')
            qb_name = qb_by_id.get(qb_cid, {}).get('customer_name', '')
            sb_norm = _normalise(sb_name)
            qb_norm = _normalise(qb_name)
            if sb_norm and qb_norm and (sb_norm in qb_norm or qb_norm in sb_norm):
                name_confirmed_sb_ids.add(sb_cid)

# 4. Top 50 uncovered companies - deep dive
print("[4/4] Deep dive on uncovered top revenue companies...\n")
top_sorted = sorted(company_revenue.items(), key=lambda x: -x[1])

uncovered = [(cid, rev) for cid, rev in top_sorted if cid not in name_confirmed_sb_ids]

print(f"{'Rank':>4} {'SB Company':<25} {'SB Norm':<20} {'Revenue':>12} {'#QB':>4} {'QB Customer Name':<28} {'QB Norm':<20} {'Email Link?':<12} Why Failed")
print("-" * 170)

for rank, (cid, rev) in enumerate(uncovered[:50], 1):
    sb_name = sb_data.get(cid, '?')
    sb_norm = _normalise(sb_name)
    matched_qbs = company_qb_custs.get(cid, [])
    num_qb = len(matched_qbs)

    # Check if this company has any email links
    email_qb_map = sb_to_qb.get(cid, {})
    has_email = len(email_qb_map) > 0

    # Show each QB customer matched to this company
    if matched_qbs:
        for i, qc in enumerate(matched_qbs[:3]):
            qb_name = qc.get('customer_name', '?')
            qb_norm = _normalise(qb_name)
            qb_rev = float(qc.get('total_invoiced') or 0)

            # Diagnose why name check failed
            reason = ''
            if not sb_norm or not qb_norm:
                reason = 'empty norm'
            elif sb_norm == qb_norm:
                reason = 'BUG: should match!'
            elif sb_norm in qb_norm:
                reason = 'BUG: substring match!'
            elif qb_norm in sb_norm:
                reason = 'BUG: substring match!'
            else:
                # Show what's different
                # Check if there's partial overlap
                common = set(re.findall(r'[a-z]+', sb_norm)) & set(re.findall(r'[a-z]+', qb_norm))
                if common:
                    reason = f'partial: {",".join(sorted(common)[:3])}'
                else:
                    reason = f'no overlap'

            # Is this specific QB customer in the email join?
            qb_rid = str(qc.get('qb_record_id', ''))
            qb_kid = str(qc.get('customer_key_id', ''))
            in_email = qb_rid in email_qb_map or qb_kid in email_qb_map

            if i == 0:
                print(f"{rank:>4} {sb_name[:24]:<25} {sb_norm[:19]:<20} ${rev:>11,.0f} {num_qb:>4} {qb_name[:27]:<28} {qb_norm[:19]:<20} {'email+' if in_email else 'no email':<12} {reason}")
            else:
                print(f"{'':>4} {'':25} {'':20} {'':12} {'':4} {qb_name[:27]:<28} {qb_norm[:19]:<20} {'email+' if in_email else 'no email':<12} {reason}")
    else:
        print(f"{rank:>4} {sb_name[:24]:<25} {sb_norm[:19]:<20} ${rev:>11,.0f} {num_qb:>4} {'(no QB match)':28} {'':20} {'':12}")

    if len(matched_qbs) > 3:
        print(f"{'':>4} {'':25} {'':20} {'':12} {'':4} ... +{len(matched_qbs)-3} more QB customers")

print("\nDone!")
