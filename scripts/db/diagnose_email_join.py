"""
Direct SQL-style join: customer_contacts.email_address = qb_unique_emails.email
Shows the resulting SB company -> QB customer mappings for inspection.
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

# 1. Fetch both sides of the join
print("[1/3] Fetching data...")
qb_emails = fetch_all('qb_unique_emails', 'email, qb_customer_id', [
    lambda q: q.eq('hide', False),
    lambda q: q.eq('email_invalid', False),
    lambda q: q.not_.is_('qb_customer_id', 'null'),
])
contacts = fetch_all('customer_contacts', 'email_address, customer_company_id', [
    lambda q: q.not_.is_('customer_company_id', 'null'),
])
print(f"  qb_unique_emails: {len(qb_emails)}")
print(f"  customer_contacts with company: {len(contacts)}")

# 2. Index by email
email_to_qb_cust: dict[str, set] = defaultdict(set)
for ue in qb_emails:
    email = (ue.get('email') or '').strip().lower()
    qb_cid = ue.get('qb_customer_id')
    if email and qb_cid:
        email_to_qb_cust[email].add(str(qb_cid).strip())

email_to_sb_company: dict[str, set] = defaultdict(set)
for cc in contacts:
    email = (cc.get('email_address') or '').strip().lower()
    cid = cc.get('customer_company_id')
    if email and cid:
        email_to_sb_company[email].add(cid)

# 3. JOIN on email
print("\n[2/3] Joining on email...")
# Result: (sb_company_id, qb_customer_id, email) triples
join_triples = []
matched_emails = set(email_to_qb_cust.keys()) & set(email_to_sb_company.keys())
print(f"  Emails in both tables: {len(matched_emails)}")

for email in matched_emails:
    for sb_cid in email_to_sb_company[email]:
        for qb_cid in email_to_qb_cust[email]:
            join_triples.append((sb_cid, qb_cid, email))

print(f"  Join triples (sb_company, qb_customer, email): {len(join_triples)}")

# Group: sb_company -> {qb_customer: [emails]}
sb_to_qb: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
for sb_cid, qb_cid, email in join_triples:
    sb_to_qb[sb_cid][qb_cid].append(email)

# Also group: qb_customer -> {sb_company: [emails]}
qb_to_sb: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
for sb_cid, qb_cid, email in join_triples:
    qb_to_sb[qb_cid][sb_cid].append(email)

print(f"  Unique SB companies in join: {len(sb_to_qb)}")
print(f"  Unique QB customers in join: {len(qb_to_sb)}")

# 1:1 vs 1:N vs N:1
sb_one_qb = sum(1 for v in sb_to_qb.values() if len(v) == 1)
sb_multi_qb = sum(1 for v in sb_to_qb.values() if len(v) > 1)
qb_one_sb = sum(1 for v in qb_to_sb.values() if len(v) == 1)
qb_multi_sb = sum(1 for v in qb_to_sb.values() if len(v) > 1)
print(f"\n  SB companies -> 1 QB customer: {sb_one_qb}")
print(f"  SB companies -> multiple QB customers: {sb_multi_qb}")
print(f"  QB customers -> 1 SB company: {qb_one_sb}")
print(f"  QB customers -> multiple SB companies: {qb_multi_sb}")

# Fetch names for display
print("\n[3/3] Fetching names for display...")
all_sb_ids = list(sb_to_qb.keys())
sb_names = {}
for i in range(0, len(all_sb_ids), 500):
    batch = all_sb_ids[i:i+500]
    resp = sb.table('customer_companies').select('id, company_name').in_('id', batch).execute()
    for c in (resp.data or []):
        sb_names[c['id']] = c.get('company_name', '?')

qb_info = {}
offset = 0
while True:
    page = sb.table('qb_customers').select(
        'qb_record_id, customer_key_id, customer_name, customer_code'
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

# Show 1:1 matches (highest confidence)
print(f"\n{'='*130}")
print(f"1:1 MATCHES (SB company -> exactly 1 QB customer, QB customer -> exactly 1 SB company)")
one_to_one = []
for sb_cid, qb_map in sb_to_qb.items():
    if len(qb_map) == 1:
        qb_cid = list(qb_map.keys())[0]
        if len(qb_to_sb.get(qb_cid, {})) == 1:
            one_to_one.append((sb_cid, qb_cid, qb_map[qb_cid]))

print(f"Count: {len(one_to_one)}")
print(f"\n{'SB Company':<30} {'QB Customer':<30} {'Code':<10} {'Emails':>6} Sample Email")
print("-" * 130)

# Categorise: name match vs name mismatch
name_match = []
name_mismatch = []
for sb_cid, qb_cid, emails in one_to_one:
    sb_name = sb_names.get(sb_cid, '?')
    qi = qb_info.get(qb_cid, {})
    qb_name = qi.get('customer_name', '?')
    sb_norm = _normalise(sb_name)
    qb_norm = _normalise(qb_name)
    if sb_norm and qb_norm and (sb_norm in qb_norm or qb_norm in sb_norm or sb_norm == qb_norm):
        name_match.append((sb_cid, qb_cid, emails))
    else:
        name_mismatch.append((sb_cid, qb_cid, emails))

print(f"\n  Name-confirmed 1:1 matches: {len(name_match)}")
print(f"  Name-mismatched 1:1 matches: {len(name_mismatch)}")

print(f"\n--- Name-confirmed (sample 20) ---")
for sb_cid, qb_cid, emails in name_match[:20]:
    sb_name = sb_names.get(sb_cid, '?')[:29]
    qi = qb_info.get(qb_cid, {})
    qb_name = qi.get('customer_name', '?')[:29]
    qb_code = qi.get('customer_code', '?')[:9]
    print(f"{sb_name:<30} {qb_name:<30} {qb_code:<10} {len(emails):>6} {emails[0]}")

print(f"\n--- Name-mismatched (sample 30) ---")
for sb_cid, qb_cid, emails in name_mismatch[:30]:
    sb_name = sb_names.get(sb_cid, '?')[:29]
    qi = qb_info.get(qb_cid, {})
    qb_name = qi.get('customer_name', '?')[:29]
    qb_code = qi.get('customer_code', '?')[:9]
    print(f"{sb_name:<30} {qb_name:<30} {qb_code:<10} {len(emails):>6} {emails[0]}")

print("\nDone!")
