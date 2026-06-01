"""
Diagnose contact misassignment: contacts linked to wrong companies.

Primary case: "Daniel Bauer" (domain: litera.design) has contacts bronwyn@litera.design
and areebah@litera.design — these belong to "Litera Design", not "Daniel Bauer".

Scale analysis: Find ALL cases where contact email domains don't match company domain,
and where person-named companies hold corporate-domain contacts.
"""
import os
import sys
import re
from collections import defaultdict

# Force UTF-8 output to handle accented names
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
from dotenv import load_dotenv
from supabase import create_client

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
load_dotenv(env_path)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
CLIENT_ID = "241d7b99-f099-4557-96e5-212c4af10812"

FREE_PROVIDERS = {
    'gmail.com', 'hotmail.com', 'yahoo.com', 'outlook.com', 'icloud.com',
    'live.com', 'live.com.au', 'aol.com', 'msn.com', 'me.com', 'mail.com',
    'yahoo.com.au', 'hotmail.com.au', 'outlook.com.au', 'bigpond.com',
    'bigpond.net.au', 'optusnet.com.au', 'protonmail.com', 'proton.me',
    'ymail.com', 'rocketmail.com', 'gmx.com', 'zoho.com',
}

PERSON_NAME_RE = re.compile(
    r'^[A-Z][a-z]+\s+[A-Z][a-z]+$'  # "First Last" — two capitalized words
)


def paginate_all(table, select_cols, filters=None, not_null_col=None, is_null_col=None):
    """Paginate through all rows."""
    rows = []
    offset = 0
    while True:
        q = sb.table(table).select(select_cols)
        if filters:
            for k, v in filters.items():
                q = q.eq(k, v)
        if not_null_col:
            q = q.not_.is_(not_null_col, 'null')
        if is_null_col:
            q = q.is_(is_null_col, 'null')
        q = q.range(offset, offset + 999)
        resp = q.execute()
        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000
    return rows


def extract_domain(email):
    """Extract domain from email address."""
    if not email or '@' not in email:
        return None
    return email.strip().lower().split('@')[1]


# ============================================================
print("=" * 80)
print("DIAGNOSIS: Contact Misassignment — Domain/Company Mismatch")
print("=" * 80)

# ============================================================
# 1. Find "Daniel Bauer" company
# ============================================================
print("\n" + "=" * 80)
print("1. SPECIFIC CASE: 'Daniel Bauer' company")
print("=" * 80)

daniel_resp = sb.table('customer_companies').select(
    'id, company_name, email_domains, qb_customer_id, qb_customer_code, qb_match_method, created_at'
).eq('client_id', CLIENT_ID).eq('company_name', 'Daniel Bauer').execute()

if daniel_resp.data:
    db = daniel_resp.data[0]
    print(f"   Company ID:      {db['id']}")
    print(f"   Name:            {db['company_name']}")
    print(f"   Email domains:   {db['email_domains']}")
    print(f"   QB customer ID:  {db.get('qb_customer_id')}")
    print(f"   QB customer code:{db.get('qb_customer_code')}")
    print(f"   QB match method: {db.get('qb_match_method')}")
    print(f"   Created at:      {db.get('created_at')}")
    daniel_id = db['id']
else:
    print("   NOT FOUND — 'Daniel Bauer' company does not exist")
    daniel_id = None

# ============================================================
# 2. Find QB customer C25549
# ============================================================
print("\n" + "=" * 80)
print("2. QB CUSTOMER C25549 (or search by name 'Daniel Bauer')")
print("=" * 80)

# Search by code
qb_code_resp = sb.table('qb_customers').select(
    'id, qb_record_id, customer_name, customer_code, total_invoiced, matched_company_id'
).eq('client_id', CLIENT_ID).eq('customer_code', 'C25549').execute()

if qb_code_resp.data:
    for qb in qb_code_resp.data:
        print(f"   QB Record ID:      {qb['qb_record_id']}")
        print(f"   Customer name:     {qb['customer_name']}")
        print(f"   Customer code:     {qb['customer_code']}")
        print(f"   Total invoiced:    ${float(qb.get('total_invoiced') or 0):,.2f}")
        print(f"   Matched company:   {qb['matched_company_id']}")
else:
    print("   C25549 not found, searching by name 'Daniel Bauer'...")
    qb_name_resp = sb.table('qb_customers').select(
        'id, qb_record_id, customer_name, customer_code, total_invoiced, matched_company_id'
    ).eq('client_id', CLIENT_ID).ilike('customer_name', '%Daniel Bauer%').execute()
    for qb in (qb_name_resp.data or []):
        print(f"   QB Record ID:      {qb['qb_record_id']}")
        print(f"   Customer name:     {qb['customer_name']}")
        print(f"   Customer code:     {qb['customer_code']}")
        print(f"   Total invoiced:    ${float(qb.get('total_invoiced') or 0):,.2f}")
        print(f"   Matched company:   {qb['matched_company_id']}")
    if not (qb_name_resp.data or []):
        print("   No QB customer found for 'Daniel Bauer'")

# Also check QB unique emails for litera.design
print("\n   QB Unique Emails for litera.design:")
qb_emails_resp = sb.table('qb_unique_emails').select(
    'email, customer_name, qb_customer_id, hide, email_invalid'
).eq('client_id', CLIENT_ID).ilike('email', '%litera.design%').execute()

for e in (qb_emails_resp.data or []):
    print(f"   - {e['email']} -> QB Customer: {e['customer_name']} (ID: {e['qb_customer_id']}, hide={e.get('hide')}, invalid={e.get('email_invalid')})")
if not (qb_emails_resp.data or []):
    print("   No QB unique emails found for litera.design")

# ============================================================
# 3. Contacts on Daniel Bauer company
# ============================================================
print("\n" + "=" * 80)
print("3. CONTACTS ON 'DANIEL BAUER' COMPANY")
print("=" * 80)

if daniel_id:
    contacts_resp = sb.table('customer_contacts').select(
        'id, email_address, full_name, customer_company_id, created_at'
    ).eq('customer_company_id', daniel_id).execute()

    for c in (contacts_resp.data or []):
        domain = extract_domain(c['email_address'])
        print(f"   - {c['full_name'] or '(no name)':<30} {c['email_address']:<40} domain={domain}")
    if not (contacts_resp.data or []):
        print("   No contacts linked to this company")
else:
    print("   Skipped — Daniel Bauer company not found")

# ============================================================
# 4. Check if "Litera Design" or "Litera" exists separately
# ============================================================
print("\n" + "=" * 80)
print("4. DOES 'LITERA DESIGN' OR 'LITERA' EXIST AS SEPARATE COMPANY?")
print("=" * 80)

litera_resp = sb.table('customer_companies').select(
    'id, company_name, email_domains, qb_customer_id, qb_match_method'
).eq('client_id', CLIENT_ID).ilike('company_name', '%litera%').execute()

for c in (litera_resp.data or []):
    print(f"   - '{c['company_name']}' (ID: {c['id']})")
    print(f"     Domains: {c['email_domains']}, QB ID: {c.get('qb_customer_id')}, Method: {c.get('qb_match_method')}")
if not (litera_resp.data or []):
    print("   No company with 'litera' in name found")

# ============================================================
# 5. SCALE ANALYSIS: Domain mismatch across ALL companies
# ============================================================
print("\n" + "=" * 80)
print("5. SCALE ANALYSIS: Contact email domain != company domain")
print("=" * 80)

print("\n   Loading all companies with domains...")
all_companies = paginate_all(
    'customer_companies',
    'id, company_name, email_domains, qb_customer_id, qb_match_method',
    filters={'client_id': CLIENT_ID}
)
print(f"   Loaded {len(all_companies)} companies")

# Build company lookup
company_map = {}
for c in all_companies:
    company_map[c['id']] = c

print("   Loading all contacts...")
all_contacts = paginate_all(
    'customer_contacts',
    'id, email_address, full_name, customer_company_id',
    filters={'client_id': CLIENT_ID},
    not_null_col='customer_company_id'
)
print(f"   Loaded {len(all_contacts)} contacts with company links")

# Group contacts by company
contacts_by_company = defaultdict(list)
for c in all_contacts:
    contacts_by_company[c['customer_company_id']].append(c)

# Analyze mismatches
mismatched_companies = []  # (company, matching_contacts, mismatched_contacts)

for company_id, contacts in contacts_by_company.items():
    company = company_map.get(company_id)
    if not company:
        continue

    company_domains = set()
    for d in (company.get('email_domains') or []):
        company_domains.add(d.lower())

    if not company_domains:
        continue  # Can't check mismatch without known domains

    matching = []
    mismatched = []

    for contact in contacts:
        contact_domain = extract_domain(contact['email_address'])
        if not contact_domain:
            continue
        if contact_domain in FREE_PROVIDERS:
            continue  # Free provider contacts are expected anywhere
        if contact_domain in company_domains:
            matching.append(contact)
        else:
            mismatched.append(contact)

    if mismatched:
        mismatched_companies.append({
            'company': company,
            'matching_contacts': matching,
            'mismatched_contacts': mismatched,
            'mismatch_count': len(mismatched),
            'total_contacts': len(contacts),
        })

mismatched_companies.sort(key=lambda x: x['mismatch_count'], reverse=True)

print(f"\n   RESULTS:")
print(f"   Companies with domain set:          {sum(1 for c in all_companies if c.get('email_domains'))}")
print(f"   Companies with mismatched contacts: {len(mismatched_companies)}")
total_mismatched_contacts = sum(m['mismatch_count'] for m in mismatched_companies)
print(f"   Total mismatched contacts:          {total_mismatched_contacts}")

print(f"\n   TOP 20 WORST CASES (most mismatched contacts):")
print(f"   {'Company':<35} {'Domains':<25} {'Match':>5} {'Mis':>5} {'QB Method':<15} Mismatched Emails")
print(f"   {'-'*35} {'-'*25} {'-'*5} {'-'*5} {'-'*15} {'-'*40}")

for m in mismatched_companies[:20]:
    comp = m['company']
    domains = ', '.join(comp.get('email_domains') or [])[:24]
    mis_emails = [extract_domain(c['email_address']) for c in m['mismatched_contacts']]
    unique_mis_domains = sorted(set(d for d in mis_emails if d))
    print(
        f"   {comp['company_name'][:35]:<35} "
        f"{domains:<25} "
        f"{len(m['matching_contacts']):>5} "
        f"{m['mismatch_count']:>5} "
        f"{(comp.get('qb_match_method') or '-'):<15} "
        f"{', '.join(unique_mis_domains[:5])}"
    )

# Show detail for "Daniel Bauer" if it's in the list
daniel_in_list = [m for m in mismatched_companies if m['company'].get('company_name') == 'Daniel Bauer']
if daniel_in_list:
    print(f"\n   DETAIL — 'Daniel Bauer' mismatched contacts:")
    for c in daniel_in_list[0]['mismatched_contacts']:
        print(f"   - {c.get('full_name', '(no name)'):<30} {c['email_address']}")

# ============================================================
# 6. Person-named companies with corporate-domain contacts
# ============================================================
print("\n" + "=" * 80)
print("6. PERSON-NAMED COMPANIES WITH CORPORATE-DOMAIN CONTACTS")
print("=" * 80)

person_companies = []

for company_id, contacts in contacts_by_company.items():
    company = company_map.get(company_id)
    if not company:
        continue

    name = (company.get('company_name') or '').strip()
    if not PERSON_NAME_RE.match(name):
        continue

    # This company is named like a person (e.g., "Daniel Bauer")
    # Check if contacts have corporate domains
    corporate_contacts = []
    for contact in contacts:
        contact_domain = extract_domain(contact['email_address'])
        if not contact_domain:
            continue
        if contact_domain in FREE_PROVIDERS:
            continue
        corporate_contacts.append(contact)

    if corporate_contacts:
        # Get unique corporate domains
        corp_domains = sorted(set(
            extract_domain(c['email_address'])
            for c in corporate_contacts
            if extract_domain(c['email_address'])
        ))
        person_companies.append({
            'company': company,
            'corporate_contacts': corporate_contacts,
            'corporate_domains': corp_domains,
            'total_contacts': len(contacts),
        })

person_companies.sort(key=lambda x: len(x['corporate_contacts']), reverse=True)

print(f"   Person-named companies total:                   {sum(1 for c in all_companies if PERSON_NAME_RE.match((c.get('company_name') or '').strip()))}")
print(f"   Person-named companies with corporate contacts: {len(person_companies)}")
total_corp = sum(len(p['corporate_contacts']) for p in person_companies)
print(f"   Total corporate contacts on person-companies:   {total_corp}")

print(f"\n   ALL CASES (person name + corporate emails):")
print(f"   {'Person Company':<30} {'Company Domains':<25} {'Corp Contacts':>13} {'Corporate Domains'}")
print(f"   {'-'*30} {'-'*25} {'-'*13} {'-'*40}")

for p in person_companies:
    comp = p['company']
    domains = ', '.join(comp.get('email_domains') or [])[:24]
    print(
        f"   {comp['company_name'][:30]:<30} "
        f"{domains:<25} "
        f"{len(p['corporate_contacts']):>13} "
        f"{', '.join(p['corporate_domains'][:5])}"
    )
    # Show the contacts
    for c in p['corporate_contacts']:
        print(f"      - {c.get('full_name', '(no name)'):<28} {c['email_address']}")

# ============================================================
# 7. Root cause analysis
# ============================================================
print("\n" + "=" * 80)
print("7. ROOT CAUSE ANALYSIS")
print("=" * 80)

# Check what match methods are associated with mismatched companies
method_counts = defaultdict(int)
for m in mismatched_companies:
    method = m['company'].get('qb_match_method') or 'none'
    method_counts[method] += 1

print("\n   Match methods on mismatched companies:")
for method, count in sorted(method_counts.items(), key=lambda x: -x[1]):
    print(f"   - {method:<20}: {count} companies")

# Check: are mismatched contacts coming from QB email lookup?
print("\n   Checking if mismatched contacts appear in qb_unique_emails...")
# Sample: take first 50 mismatched emails to check
sample_emails = []
for m in mismatched_companies[:30]:
    for c in m['mismatched_contacts'][:3]:
        sample_emails.append(c['email_address'].lower())

if sample_emails:
    # Check a batch
    found_in_qb = 0
    not_in_qb = 0
    for email in sample_emails[:50]:
        resp = sb.table('qb_unique_emails').select(
            'email, customer_name, qb_customer_id'
        ).eq('client_id', CLIENT_ID).eq('email', email).execute()
        if resp.data:
            found_in_qb += 1
        else:
            not_in_qb += 1

    print(f"   Sample of {found_in_qb + not_in_qb} mismatched contact emails:")
    print(f"   - Found in QB unique emails: {found_in_qb}")
    print(f"   - NOT in QB unique emails:   {not_in_qb}")
    print(f"   → {'QB email lookup is a likely cause' if found_in_qb > not_in_qb else 'Domain-based resolution is the likely cause'}")

# ============================================================
# Summary
# ============================================================
print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print(f"  Companies with domain mismatch:         {len(mismatched_companies)}")
print(f"  Total mismatched contacts:              {total_mismatched_contacts}")
print(f"  Person-named companies w/ corp emails:  {len(person_companies)}")
print(f"  Total corp contacts on person-companies:{total_corp}")
print()
if len(mismatched_companies) > 5:
    print("  VERDICT: This is a SYSTEMATIC pattern, not a one-off.")
    print("  The CompanyResolver's QB email lookup assigns contacts to whichever")
    print("  QB customer 'owns' that email in qb_unique_emails, regardless of")
    print("  whether the contact's email domain matches the company's domain.")
    print()
    print("  Person-named companies (like 'Daniel Bauer') are QB customers that")
    print("  are individuals — their QB record holds emails from companies they")
    print("  work at (e.g., litera.design), creating cross-domain assignments.")
else:
    print("  VERDICT: This appears to be a limited/one-off issue.")
print("=" * 80)
