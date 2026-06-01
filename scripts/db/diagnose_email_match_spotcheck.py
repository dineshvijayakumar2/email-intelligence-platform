"""
Spot-check email-based matching quality for single-match companies.
Traces: qb_unique_emails.email -> customer_contacts.email_address -> company
Shows the actual email that created the link so we can verify it's correct.
"""
import os, sys, random
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

# 1. Fetch all qb_unique_emails
print("[1/4] Fetching QB unique emails...")
all_ue = []
offset = 0
while True:
    page = sb.table('qb_unique_emails').select(
        'qb_record_id, email, qb_customer_id'
    ).eq('client_id', CLIENT_ID).range(offset, offset + 999).execute()
    rows = page.data or []
    all_ue.extend(rows)
    if not rows:
        break
    offset += len(rows)

# 2. Fetch all customer_contacts with company
print("[2/4] Fetching customer contacts...")
all_cc = []
offset = 0
while True:
    page = sb.table('customer_contacts').select(
        'id, email_address, customer_company_id'
    ).eq('client_id', CLIENT_ID).not_.is_(
        'customer_company_id', 'null'
    ).range(offset, offset + 999).execute()
    rows = page.data or []
    all_cc.extend(rows)
    if not rows:
        break
    offset += len(rows)

email_to_company: dict[str, str] = {}
for cc in all_cc:
    email = (cc.get('email_address') or '').lower().strip()
    if email and cc.get('customer_company_id'):
        email_to_company[email] = cc['customer_company_id']

# 3. Trace email links: qb_customer_id -> {company_id: [emails]}
print("[3/4] Tracing email -> company links...")
qb_cust_links: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
for ue in all_ue:
    email = (ue.get('email') or '').lower().strip()
    qb_cust_id = ue.get('qb_customer_id')
    if not email or not qb_cust_id:
        continue
    company_id = email_to_company.get(email)
    if company_id:
        qb_cust_links[str(qb_cust_id)][company_id].append(email)

# Group by company -> qb_customers
company_to_qb: dict[str, set] = defaultdict(set)
for qb_cust_id, companies in qb_cust_links.items():
    for cid in companies:
        company_to_qb[cid].add(qb_cust_id)

# Filter to single-match companies
single_match = {cid: list(custs)[0] for cid, custs in company_to_qb.items() if len(custs) == 1}
print(f"  Single-match companies: {len(single_match)}")

# 4. Spot-check 30 random single-match companies
sample_ids = random.sample(list(single_match.keys()), min(30, len(single_match)))

# Fetch company names
company_names = {}
for i in range(0, len(sample_ids), 500):
    batch = sample_ids[i:i+500]
    resp = sb.table('customer_companies').select('id, company_name').in_('id', batch).execute()
    for c in (resp.data or []):
        company_names[c['id']] = c.get('company_name', '?')

# Fetch QB customer names
qb_cust_ids = [single_match[cid] for cid in sample_ids]
qb_names = {}
for i in range(0, len(qb_cust_ids), 500):
    batch = qb_cust_ids[i:i+500]
    int_batch = []
    for x in batch:
        try:
            int_batch.append(int(x))
        except (ValueError, TypeError):
            pass
    if int_batch:
        resp = sb.table('qb_customers').select(
            'customer_key_id, customer_name, customer_code'
        ).eq('client_id', CLIENT_ID).in_('customer_key_id', int_batch).execute()
        for c in (resp.data or []):
            qb_names[str(c.get('customer_key_id'))] = {
                'name': c.get('customer_name', '?'),
                'code': c.get('customer_code', '?'),
            }

print(f"\n[4/4] Spot-check: 30 random single-match companies")
print(f"{'SB Company':<30} {'QB Customer':<30} {'QB Code':<10} Linking Email(s)")
print("-" * 120)

for cid in sample_ids:
    sb_name = company_names.get(cid, '?')[:29]
    qb_cust_id = single_match[cid]
    qb_info = qb_names.get(qb_cust_id, {'name': f'key={qb_cust_id}', 'code': '?'})
    qb_name = qb_info['name'][:29]
    qb_code = qb_info['code'][:9]
    emails = qb_cust_links[qb_cust_id].get(cid, [])
    email_str = " ; ".join(emails[:3])
    if len(emails) > 3:
        email_str += f" +{len(emails)-3} more"
    print(f"{sb_name:<30} {qb_name:<30} {qb_code:<10} {email_str}")

print("\nDone!")
