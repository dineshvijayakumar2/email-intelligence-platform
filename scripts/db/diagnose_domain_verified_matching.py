"""
Simulate domain-verified email matching.
Shows what would auto-match (domain root in QB customer name) vs stage for review.
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

GENERIC_DOMAINS = frozenset({
    'gmail.com', 'hotmail.com', 'yahoo.com', 'outlook.com',
    'icloud.com', 'bigpond.com', 'me.com', 'hotmail.com.au',
    'yahoo.com.au', 'live.com', 'live.com.au', 'msn.com',
    'aol.com', 'mail.com', 'protonmail.com', 'zoho.com',
})

def _normalise(name):
    return re.sub(r'[^a-z0-9]', '', (name or '').lower())

# 1. Fetch QB unique emails
print("[1/5] Fetching QB unique emails...")
all_ue = []
offset = 0
while True:
    page = sb.table('qb_unique_emails').select(
        'email, qb_customer_id'
    ).eq('client_id', CLIENT_ID).eq(
        'hide', False
    ).eq(
        'email_invalid', False
    ).not_.is_('qb_customer_id', 'null').range(offset, offset + 999).execute()
    rows = page.data or []
    all_ue.extend(rows)
    if not rows:
        break
    offset += len(rows)
print(f"  QB unique emails: {len(all_ue)}")

email_to_qb = {}
for ue in all_ue:
    email = (ue.get('email') or '').strip().lower()
    qb_cid = ue.get('qb_customer_id')
    if email and qb_cid:
        email_to_qb[email] = str(qb_cid).strip()

# 2. Fetch SB contacts
print("[2/5] Fetching customer contacts...")
all_cc = []
offset = 0
while True:
    page = sb.table('customer_contacts').select(
        'email_address, customer_company_id'
    ).eq('client_id', CLIENT_ID).not_.is_(
        'customer_company_id', 'null'
    ).range(offset, offset + 999).execute()
    rows = page.data or []
    all_cc.extend(rows)
    if not rows:
        break
    offset += len(rows)
print(f"  Customer contacts: {len(all_cc)}")

# 3. Build company -> {qb_customer_id: [emails]}
print("[3/5] Building company -> QB customer links...")
company_to_qb: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
for cc in all_cc:
    email = (cc.get('email_address') or '').strip().lower()
    cid = cc.get('customer_company_id')
    if not email or not cid:
        continue
    qb_cust_id = email_to_qb.get(email)
    if qb_cust_id:
        company_to_qb[cid][qb_cust_id].append(email)

# Resolve to best QB customer per company (majority vote)
company_best: dict[str, tuple[str, list]] = {}
for cid, qb_map in company_to_qb.items():
    best = max(qb_map, key=lambda k: len(qb_map[k]))
    company_best[cid] = (best, qb_map[best])

print(f"  Companies with email links: {len(company_best)}")

# 4. Fetch QB customer names
print("[4/5] Fetching QB customer names...")
qb_names = {}
offset = 0
while True:
    page = sb.table('qb_customers').select(
        'qb_record_id, customer_name, customer_code'
    ).eq('client_id', CLIENT_ID).range(offset, offset + 999).execute()
    rows = page.data or []
    for r in rows:
        rid = r.get('qb_record_id')
        if rid:
            qb_names[str(rid)] = r
    if not rows:
        break
    offset += len(rows)

# Fetch SB company names
company_ids = list(company_best.keys())
sb_names = {}
for i in range(0, len(company_ids), 500):
    batch = company_ids[i:i+500]
    resp = sb.table('customer_companies').select('id, company_name').in_('id', batch).execute()
    for c in (resp.data or []):
        sb_names[c['id']] = c.get('company_name', '?')

# 5. Apply domain verification
print("[5/5] Applying domain verification gate...\n")
verified = []
unverified = []

for cid, (qb_id, emails) in company_best.items():
    try:
        norm_id = str(int(float(qb_id)))
    except (ValueError, TypeError):
        norm_id = str(qb_id)

    qb_info = qb_names.get(norm_id, {})
    qb_name = qb_info.get('customer_name', '?')
    qb_name_norm = _normalise(qb_name)
    sb_name = sb_names.get(cid, '?')

    domain_match = False
    matching_domain = None
    if qb_name_norm:
        for email in emails:
            domain = email.split('@')[-1].lower() if '@' in email else ''
            if domain in GENERIC_DOMAINS or not domain:
                continue
            domain_root = domain.split('.')[0]
            if len(domain_root) >= 3 and domain_root in qb_name_norm:
                domain_match = True
                matching_domain = domain_root
                break

    entry = {
        'sb_name': sb_name,
        'qb_name': qb_name,
        'qb_code': qb_info.get('customer_code', '?'),
        'emails': emails[:3],
        'domain': matching_domain,
    }

    if domain_match:
        verified.append(entry)
    else:
        unverified.append(entry)

print(f"DOMAIN-VERIFIED (auto-match): {len(verified)}")
print(f"UNVERIFIED (stage for review): {len(unverified)}")
print(f"Total: {len(verified) + len(unverified)}")

print(f"\n{'='*120}")
print(f"SAMPLE DOMAIN-VERIFIED MATCHES (first 30):")
print(f"{'SB Company':<28} {'QB Customer':<28} {'Code':<10} {'Domain':<15} Email")
print("-" * 120)
for e in verified[:30]:
    email_str = e['emails'][0] if e['emails'] else '?'
    print(f"{e['sb_name'][:27]:<28} {e['qb_name'][:27]:<28} {e['qb_code'][:9]:<10} {(e['domain'] or '?')[:14]:<15} {email_str}")

print(f"\n{'='*120}")
print(f"SAMPLE UNVERIFIED MATCHES (first 30):")
print(f"{'SB Company':<28} {'QB Customer':<28} {'Code':<10} Email(s)")
print("-" * 120)
for e in unverified[:30]:
    email_str = " ; ".join(e['emails'][:2])
    print(f"{e['sb_name'][:27]:<28} {e['qb_name'][:27]:<28} {e['qb_code'][:9]:<10} {email_str}")

# Check: any companies with >1 QB customer in verified set?
verified_company_to_qb: dict[str, set] = defaultdict(set)
for cid, (qb_id, _) in company_best.items():
    qb_info = qb_names.get(str(int(float(qb_id))), {})
    qb_name_norm = _normalise(qb_info.get('customer_name'))
    for email in _:
        domain = email.split('@')[-1].lower() if '@' in email else ''
        if domain in GENERIC_DOMAINS or not domain:
            continue
        domain_root = domain.split('.')[0]
        if len(domain_root) >= 3 and qb_name_norm and domain_root in qb_name_norm:
            verified_company_to_qb[cid].add(qb_id)
            break

multi = {k: v for k, v in verified_company_to_qb.items() if len(v) > 1}
print(f"\nVerified matches with >1 QB customer per company: {len(multi)}")

print("\nDone!")
