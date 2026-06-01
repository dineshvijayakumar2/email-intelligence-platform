"""
Verify email-based QB matching quality.
Traces the email matching path to see if any company would get
multiple QB customers — and whether those are legitimate (same entity)
or contaminated (different entities).

Path: qb_unique_emails.email -> customer_contacts.email -> customer_company_id
      -> set qb_customers.matched_company_id for the parent QB customer.
"""
import os, sys
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

# 1. Fetch all qb_unique_emails (these link QB customers to emails)
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
print(f"  Total QB unique emails: {len(all_ue)}")

# 2. Fetch all customer_contacts with their company
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
print(f"  Total customer contacts with company: {len(all_cc)}")

# Build email -> company_id lookup
email_to_company: dict[str, str] = {}
for cc in all_cc:
    email = (cc.get('email_address') or '').lower().strip()
    if email and cc.get('customer_company_id'):
        email_to_company[email] = cc['customer_company_id']

print(f"  Unique emails with company links: {len(email_to_company)}")

# 3. Trace: QB unique email -> contact email -> company
#    Group by: qb_customer_id -> set of company_ids
print("[3/4] Tracing email -> company links...")
qb_cust_to_companies: dict[str, set] = defaultdict(set)
matched_emails = 0
for ue in all_ue:
    email = (ue.get('email') or '').lower().strip()
    qb_cust_id = ue.get('qb_customer_id')
    if not email or not qb_cust_id:
        continue
    company_id = email_to_company.get(email)
    if company_id:
        qb_cust_to_companies[str(qb_cust_id)].add(company_id)
        matched_emails += 1

print(f"  QB emails with a company match: {matched_emails}")
print(f"  QB customers with at least one email match: {len(qb_cust_to_companies)}")

# Check: any QB customer mapping to MULTIPLE companies?
multi_company_custs = {k: v for k, v in qb_cust_to_companies.items() if len(v) > 1}
print(f"  QB customers mapping to >1 company (conflict): {len(multi_company_custs)}")

# 4. Now flip: group by company_id -> set of qb_customer_ids
company_to_qb: dict[str, set] = defaultdict(set)
for qb_cust_id, company_ids in qb_cust_to_companies.items():
    for cid in company_ids:
        company_to_qb[cid].add(qb_cust_id)

multi_qb = {cid: custs for cid, custs in company_to_qb.items() if len(custs) > 1}
print(f"\n  Companies with exactly 1 QB customer (via email): {len(company_to_qb) - len(multi_qb)}")
print(f"  Companies with >1 QB customer (via email): {len(multi_qb)}")

# Fetch company names for multi-match companies
if multi_qb:
    company_ids = list(multi_qb.keys())
    company_names = {}
    for i in range(0, len(company_ids), 500):
        batch = company_ids[i:i+500]
        resp = sb.table('customer_companies').select('id, company_name').in_('id', batch).execute()
        for c in (resp.data or []):
            company_names[c['id']] = c.get('company_name', '?')

    # Fetch QB customer names for context
    all_qb_ids_flat = set()
    for custs in multi_qb.values():
        all_qb_ids_flat.update(custs)

    qb_names = {}
    qb_ids_list = list(all_qb_ids_flat)
    for i in range(0, len(qb_ids_list), 500):
        batch = qb_ids_list[i:i+500]
        resp = sb.table('qb_customers').select(
            'customer_key_id, customer_name'
        ).eq('client_id', CLIENT_ID).in_(
            'customer_key_id', [int(x) for x in batch if x.isdigit()]
        ).execute()
        for c in (resp.data or []):
            qb_names[str(c.get('customer_key_id'))] = c.get('customer_name', '?')

    print(f"\n[4/4] Companies with multiple QB customers via EMAIL matching:")
    print(f"{'Company':<35} {'Count':>5}  QB Customer Names")
    print("-" * 120)

    sorted_multi = sorted(multi_qb.items(), key=lambda x: -len(x[1]))
    for company_id, custs in sorted_multi[:30]:
        name = company_names.get(company_id, '?')[:34]
        cust_names = " | ".join(
            qb_names.get(c, f"key={c}")[:30] for c in sorted(custs)[:5]
        )
        if len(custs) > 5:
            cust_names += f" ... +{len(custs) - 5} more"
        print(f"{name:<35} {len(custs):>5}  {cust_names}")

    total_excess = sum(len(c) - 1 for c in multi_qb.values())
    print(f"\n  Total excess matches via email: {total_excess}")
else:
    print("\n[4/4] No companies with multiple QB customers via email — clean!")

print("\nDone!")
