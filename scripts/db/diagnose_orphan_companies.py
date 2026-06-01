"""Diagnose truly orphaned companies: no contacts, no emails, no junction links, no QB match."""
import os, sys
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


print("[1/6] Fetching all companies...")
companies = fetch_all('customer_companies', 'id, company_name, total_emails, contact_count, qb_customer_id, qb_match_method')
print(f"  {len(companies)} total companies")

print("[2/6] Fetching QB-matched company IDs...")
qb_matched = fetch_all('qb_customers', 'matched_company_id', [
    lambda q: q.not_.is_('matched_company_id', 'null'),
])
qb_matched_ids = {r['matched_company_id'] for r in qb_matched}
print(f"  {len(qb_matched_ids)} companies have QB match")

print("[3/6] Fetching companies with contacts...")
contacts = fetch_all('customer_contacts', 'customer_company_id', [
    lambda q: q.not_.is_('customer_company_id', 'null'),
])
has_contacts = {c['customer_company_id'] for c in contacts}
print(f"  {len(has_contacts)} companies have contacts")

print("[4/6] Fetching companies with emails...")
# Use email_contact_links which is the junction — faster than scanning emails table
all_company_ids = [c['id'] for c in companies]
has_emails = set()
for i in range(0, len(all_company_ids), 500):
    batch = all_company_ids[i:i+500]
    resp = sb.table('email_contact_links').select('company_id').in_('company_id', batch).limit(1000).execute()
    for r in (resp.data or []):
        if r.get('company_id'):
            has_emails.add(r['company_id'])
print(f"  {len(has_emails)} companies have junction links")

print("[5/6] Fetching match candidates pointing to companies...")
candidates = fetch_all('qb_match_candidates', 'sb_company_id', [
    lambda q: q.eq('reviewed', False),
])
has_candidates = {c['sb_company_id'] for c in candidates if c.get('sb_company_id')}
print(f"  {len(has_candidates)} companies have pending match candidates")

print("\n[6/6] Classifying...\n")

orphaned = []
has_qb_data_no_emails = []
has_qb_match_no_emails = []

for c in companies:
    cid = c['id']
    in_qb = cid in qb_matched_ids
    in_contacts = cid in has_contacts
    in_emails = cid in has_emails
    in_candidates = cid in has_candidates
    has_qb_id = bool(c.get('qb_customer_id'))

    if not in_contacts and not in_emails and not in_qb and not in_candidates and not has_qb_id:
        orphaned.append(c)
    elif in_qb and not in_contacts and not in_emails:
        has_qb_match_no_emails.append(c)

print("=" * 70)
print(f"{'Category':<45} {'Count':>10}")
print("=" * 70)
print(f"{'Total companies':<45} {len(companies):>10}")
print(f"{'QB-matched':<45} {len(qb_matched_ids):>10}")
print(f"{'Have contacts':<45} {len(has_contacts):>10}")
print(f"{'Have junction links':<45} {len(has_emails):>10}")
print(f"{'Have pending candidates':<45} {len(has_candidates):>10}")
print(f"{'ORPHANED (safe to delete)':<45} {len(orphaned):>10}")
print(f"{'QB-matched but no contacts/emails':<45} {len(has_qb_match_no_emails):>10}")
print("=" * 70)

if orphaned:
    print(f"\nSample orphaned companies (first 10):")
    for c in orphaned[:10]:
        print(f"  {c.get('company_name', 'N/A'):<40} method={c.get('qb_match_method', '-')}")

    print(f"\nDeleting {len(orphaned)} orphaned companies...")
    orphan_ids = [c['id'] for c in orphaned]
    deleted = 0
    for i in range(0, len(orphan_ids), 100):
        batch = orphan_ids[i:i+100]
        try:
            sb.table('customer_companies').delete().in_('id', batch).execute()
            deleted += len(batch)
            print(f"  Deleted batch {i//100 + 1}: {len(batch)} companies (total: {deleted})")
        except Exception as e:
            print(f"  Batch {i//100 + 1} failed: {e}")
    print(f"\nDone. Deleted {deleted} orphaned companies.")
