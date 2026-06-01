"""
For each QB customer, how many distinct SB companies do its emails resolve to?
Shows the fan-out distribution — 1:1 vs 1:many mapping.
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

print("=" * 90)
print("DIAGNOSIS: QB Customer -> SB Company Email Fan-Out")
print("=" * 90)

# Step 1: Fetch all QB unique emails
print("\n1. Fetching qb_unique_emails...")
qb_emails = []
offset = 0
while True:
    resp = sb.table('qb_unique_emails').select(
        'qb_customer_id, email'
    ).eq('client_id', CLIENT_ID).eq(
        'hide', False
    ).eq('email_invalid', False).range(offset, offset + 999).execute()
    qb_emails.extend(resp.data or [])
    if len(resp.data or []) < 1000:
        break
    offset += 1000
print(f"   {len(qb_emails)} valid QB unique emails")

# Step 2: Fetch all customer_contacts with company assignment
print("2. Fetching customer_contacts...")
contacts = []
offset = 0
while True:
    resp = sb.table('customer_contacts').select(
        'email_address, customer_company_id'
    ).eq('client_id', CLIENT_ID).not_.is_(
        'customer_company_id', 'null'
    ).range(offset, offset + 999).execute()
    contacts.extend(resp.data or [])
    if len(resp.data or []) < 1000:
        break
    offset += 1000
print(f"   {len(contacts)} contacts with company assignment")

# Step 3: Build email -> SB company mapping
email_to_sb = defaultdict(set)
for c in contacts:
    email = (c.get('email_address') or '').strip().lower()
    company_id = c.get('customer_company_id')
    if email and company_id:
        email_to_sb[email].add(company_id)

print(f"   {len(email_to_sb)} unique contact emails mapped to companies")

# Step 4: For each QB customer, find all SB companies its emails resolve to
qb_to_sb = defaultdict(set)  # qb_customer_id -> set of sb company IDs
qb_to_emails = defaultdict(set)  # qb_customer_id -> set of emails
qb_email_matches = 0

for qe in qb_emails:
    qb_cust_id = qe.get('qb_customer_id')
    email = (qe.get('email') or '').strip().lower()
    if not qb_cust_id or not email:
        continue
    qb_to_emails[qb_cust_id].add(email)
    if email in email_to_sb:
        qb_to_sb[qb_cust_id].update(email_to_sb[email])
        qb_email_matches += 1

print(f"   {len(qb_to_emails)} QB customers have emails")
print(f"   {len(qb_to_sb)} QB customers resolve to at least 1 SB company")
print(f"   {qb_email_matches} email matches found")

# Step 5: Distribution — how many SB companies per QB customer
print(f"\n3. FAN-OUT DISTRIBUTION (QB customer -> N distinct SB companies):")
print(f"   {'SB Companies':>15} {'QB Customers':>15}")
print(f"   {'-'*15} {'-'*15}")

fanout_dist = defaultdict(int)
for qb_id, sb_ids in qb_to_sb.items():
    fanout_dist[len(sb_ids)] += 1

# Also count QB customers with emails but no SB match
no_match = len(qb_to_emails) - len(qb_to_sb)
fanout_dist[0] = no_match

for n in sorted(fanout_dist.keys()):
    label = f"{n}" if n > 0 else "0 (no match)"
    print(f"   {label:>15} {fanout_dist[n]:>15}")

total_1to1 = fanout_dist.get(1, 0)
total_1tomany = sum(v for k, v in fanout_dist.items() if k > 1)
print(f"\n   1:1 (clean):     {total_1to1}")
print(f"   1:many (fan-out): {total_1tomany}")
print(f"   No match:         {no_match}")

# Step 6: Also show the reverse — SB company -> N distinct QB customers
print(f"\n4. REVERSE FAN-OUT (SB company -> N distinct QB customers):")
sb_to_qb = defaultdict(set)
for qb_id, sb_ids in qb_to_sb.items():
    for sb_id in sb_ids:
        sb_to_qb[sb_id].add(qb_id)

reverse_dist = defaultdict(int)
for sb_id, qb_ids in sb_to_qb.items():
    reverse_dist[len(qb_ids)] += 1

print(f"   {'QB Customers':>15} {'SB Companies':>15}")
print(f"   {'-'*15} {'-'*15}")
for n in sorted(reverse_dist.keys()):
    print(f"   {n:>15} {reverse_dist[n]:>15}")

# Step 7: Fetch QB customer names for the fan-out cases
print(f"\n5. EXAMPLES OF 1:MANY FAN-OUT (QB customer -> multiple SB companies):")

# Get QB customer names
multi_qb_ids = [qb_id for qb_id, sb_ids in qb_to_sb.items() if len(sb_ids) > 1]

if multi_qb_ids:
    # Fetch QB customer records by customer_key_id
    qb_name_map = {}
    for i in range(0, min(len(multi_qb_ids), 500), 500):
        batch = multi_qb_ids[i:i+500]
        resp = sb.table('qb_customers').select(
            'customer_key_id, customer_name, total_invoiced'
        ).eq('client_id', CLIENT_ID).in_('customer_key_id', batch).execute()
        for r in (resp.data or []):
            qb_name_map[r['customer_key_id']] = r

    # Fetch SB company names
    all_sb_ids = set()
    for sb_ids in qb_to_sb.values():
        all_sb_ids.update(sb_ids)
    sb_name_map = {}
    all_sb_list = list(all_sb_ids)
    for i in range(0, len(all_sb_list), 500):
        batch = all_sb_list[i:i+500]
        resp = sb.table('customer_companies').select(
            'id, company_name'
        ).in_('id', batch).execute()
        for r in (resp.data or []):
            sb_name_map[r['id']] = r.get('company_name', '?')

    # Sort by revenue
    multi_examples = []
    for qb_id in multi_qb_ids:
        qb_info = qb_name_map.get(qb_id, {})
        sb_ids = qb_to_sb[qb_id]
        sb_names = [sb_name_map.get(sid, '?') for sid in sb_ids]
        rev = float(qb_info.get('total_invoiced') or 0)
        multi_examples.append({
            'qb_name': qb_info.get('customer_name', qb_id),
            'revenue': rev,
            'sb_count': len(sb_ids),
            'sb_names': sb_names,
            'emails': list(qb_to_emails.get(qb_id, set()))[:5],
        })

    multi_examples.sort(key=lambda x: x['revenue'], reverse=True)

    for ex in multi_examples[:25]:
        print(f"\n   QB: {ex['qb_name']:<40} Rev: ${ex['revenue']:>10,.0f}  -> {ex['sb_count']} SB companies")
        for sn in ex['sb_names'][:5]:
            print(f"      SB: {sn}")
        for em in ex['emails'][:3]:
            print(f"      Email: {em}")

# Step 8: Show QB customers with emails but NO SB match
print(f"\n6. TOP UNMATCHED QB CUSTOMERS (have emails, no SB company resolves):")
no_match_ids = [qb_id for qb_id in qb_to_emails if qb_id not in qb_to_sb]
if no_match_ids:
    no_match_info = []
    for i in range(0, min(len(no_match_ids), 1000), 500):
        batch = no_match_ids[i:i+500]
        resp = sb.table('qb_customers').select(
            'customer_key_id, customer_name, total_invoiced'
        ).eq('client_id', CLIENT_ID).in_('customer_key_id', batch).execute()
        for r in (resp.data or []):
            no_match_info.append(r)

    no_match_info.sort(key=lambda x: float(x.get('total_invoiced') or 0), reverse=True)

    print(f"   {'QB Customer':<45} {'Revenue':>12} {'Emails':>8}")
    print(f"   {'-'*45} {'-'*12} {'-'*8}")
    for nm in no_match_info[:20]:
        email_count = len(qb_to_emails.get(nm.get('customer_key_id'), set()))
        rev = float(nm.get('total_invoiced') or 0)
        print(f"   {nm.get('customer_name','?')[:45]:<45} ${rev:>10,.0f} {email_count:>8}")

    # Why no match? Check if their emails exist in customer_contacts at all
    print(f"\n   WHY NO MATCH? Checking if their emails exist in customer_contacts...")
    sample_ids = [nm.get('customer_key_id') for nm in no_match_info[:10] if nm.get('customer_key_id')]
    for qb_id in sample_ids:
        emails = list(qb_to_emails.get(qb_id, set()))[:5]
        qb_info = next((nm for nm in no_match_info if nm.get('customer_key_id') == qb_id), {})
        print(f"\n   QB: {qb_info.get('customer_name','?')}")
        for em in emails:
            in_contacts = em in email_to_sb
            contact_resp = sb.table('customer_contacts').select(
                'id, email_address, customer_company_id'
            ).eq('client_id', CLIENT_ID).eq('email_address', em).execute()
            found = len(contact_resp.data or [])
            has_company = any(c.get('customer_company_id') for c in (contact_resp.data or []))
            print(f"      {em}: in_contacts={found>0}, has_company={has_company}")

print(f"\n{'='*90}")
print("SUMMARY")
print(f"{'='*90}")
print(f"  QB customers with emails:          {len(qb_to_emails)}")
print(f"  Resolve to at least 1 SB company:  {len(qb_to_sb)}")
print(f"  1:1 clean matches:                 {total_1to1}")
print(f"  1:many fan-out:                    {total_1tomany}")
print(f"  No SB match despite having emails: {no_match}")
print(f"{'='*90}")
