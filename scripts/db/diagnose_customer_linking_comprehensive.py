"""
Comprehensive diagnosis of customer linking issues between QuickBase and Supabase.
Covers: name mismatches, wrong matches, multi-QB contamination, orphans, pipeline issues.
"""
import os, sys, re, json
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

# ============================================================
# Helpers
# ============================================================

FREE_PROVIDERS = {
    'gmail.com', 'hotmail.com', 'yahoo.com', 'outlook.com', 'icloud.com',
    'live.com', 'live.com.au', 'aol.com', 'msn.com', 'me.com', 'mail.com',
    'yahoo.com.au', 'hotmail.com.au', 'outlook.com.au', 'bigpond.com',
    'bigpond.net.au', 'optusnet.com.au', 'protonmail.com', 'proton.me',
    'ymail.com', 'rocketmail.com', 'gmx.com', 'zoho.com',
}

STRIP_WORDS = {
    'pty', 'ltd', 'inc', 'co', 'group', 'australia', 'the', 'and', 'of',
    '&', 'trading', 'company', 'aust', 'services', 'design', 'print',
    'creative', 'au', 'nz', 'nsw', 'vic', 'qld', 'sa', 'wa', 'tas',
    'nt', 'act', 'limited', 'corporation', 'corp', 'llc', 'holdings',
    'international', 'solutions', 'enterprises', 'industries',
}


def paginate_all(table, select_cols, filters=None, not_null_col=None, is_null_col=None, order_col=None, order_desc=False):
    """Paginate through all rows of a Supabase table."""
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
        if order_col:
            q = q.order(order_col, desc=order_desc)
        q = q.range(offset, offset + 999)
        resp = q.execute()
        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000
    return rows


def get_count(table, filters=None, not_null_col=None, is_null_col=None):
    """Get exact count without fetching data."""
    q = sb.table(table).select('id', count='exact')
    if filters:
        for k, v in filters.items():
            q = q.eq(k, v)
    if not_null_col:
        q = q.not_.is_(not_null_col, 'null')
    if is_null_col:
        q = q.is_(is_null_col, 'null')
    resp = q.limit(0).execute()
    return resp.count


def normalize_name(name):
    """Normalize a company name for word-overlap comparison."""
    if not name:
        return set()
    name = name.lower()
    name = re.sub(r'[^\w\s]', ' ', name)  # strip punctuation
    words = name.split()
    words = [w for w in words if w not in STRIP_WORDS and len(w) > 1]
    return set(words)


def is_domain_derived(sb_name, domains):
    """Check if SB name looks like it was auto-created from a domain."""
    if not sb_name:
        return False
    sb_lower = sb_name.lower().strip()
    # Single word, all lowercase
    if ' ' not in sb_lower and sb_lower == sb_name.strip():
        return True
    # Matches a domain root (domain minus TLD)
    if domains:
        for d in (domains if isinstance(domains, list) else []):
            root = d.split('.')[0].lower() if '.' in d else d.lower()
            if sb_lower == root:
                return True
    return False


def is_person_name(name):
    """Check if a name looks like a person name (2-3 words, no business words)."""
    if not name:
        return False
    words = name.strip().split()
    if len(words) < 2 or len(words) > 3:
        return False
    business_words = {
        'pty', 'ltd', 'inc', 'co', 'group', 'trading', 'services', 'design',
        'print', 'creative', 'solutions', 'media', 'studio', 'digital',
        'consulting', 'industries', 'holdings', 'enterprises', 'corporation',
        'corp', 'llc', 'limited', 'australia', 'international', 'global',
        'systems', 'technology', 'tech', 'agency', 'associates', 'partners',
        'marketing', 'construction', 'engineering', 'logistics', 'transport',
        'electrical', 'mechanical', 'plumbing', 'building', 'developments',
        'properties', 'investments', 'capital', 'finance', 'insurance',
    }
    name_lower = name.lower()
    for bw in business_words:
        if bw in name_lower.split():
            return False
    # All words should be capitalized (title case)
    return all(w[0].isupper() for w in words if w)


def fmt_revenue(val):
    """Format revenue safely."""
    return "${:,.0f}".format(float(val or 0))


# ============================================================
print("=" * 90)
print("COMPREHENSIVE CUSTOMER LINKING DIAGNOSIS")
print("=" * 90)

# ============================================================
# SECTION 1: Overall Landscape
# ============================================================
print("\n" + "=" * 90)
print("SECTION 1: OVERALL LANDSCAPE")
print("=" * 90)

# Total QB customers
total_qb = get_count('qb_customers', filters={'client_id': CLIENT_ID})
print(f"\n  Total QB customers:          {total_qb}")

# Matched QB customers
matched_qb_count = get_count('qb_customers', filters={'client_id': CLIENT_ID}, not_null_col='matched_company_id')
print(f"  Matched QB customers:        {matched_qb_count}")

# Unmatched QB customers
unmatched_qb_count = get_count('qb_customers', filters={'client_id': CLIENT_ID}, is_null_col='matched_company_id')
print(f"  Unmatched QB customers:      {unmatched_qb_count}")

# Total SB companies
total_sb = get_count('customer_companies', filters={'client_id': CLIENT_ID})
print(f"\n  Total SB companies:          {total_sb}")

# SB companies with QB link
sb_with_qb = get_count('customer_companies', filters={'client_id': CLIENT_ID}, not_null_col='qb_customer_id')
print(f"  SB companies WITH QB link:   {sb_with_qb}")

# SB companies without QB link (email-only)
sb_no_qb = get_count('customer_companies', filters={'client_id': CLIENT_ID}, is_null_col='qb_customer_id')
print(f"  SB companies NO QB link:     {sb_no_qb}")

# Revenue breakdown -- fetch all QB customers
print("\n  Fetching all QB customers for revenue analysis...")
all_qb = paginate_all(
    'qb_customers',
    'id, customer_name, total_invoiced, matched_company_id, customer_tier, customer_status, invoiced_ty, invoiced_ly',
    filters={'client_id': CLIENT_ID}
)
print(f"  Fetched {len(all_qb)} QB customers")

matched_qb = [q for q in all_qb if q.get('matched_company_id')]
unmatched_qb = [q for q in all_qb if not q.get('matched_company_id')]

matched_revenue = sum(float(q.get('total_invoiced') or 0) for q in matched_qb)
unmatched_revenue = sum(float(q.get('total_invoiced') or 0) for q in unmatched_qb)
total_revenue = matched_revenue + unmatched_revenue

print(f"\n  Matched revenue:             {fmt_revenue(matched_revenue)} ({len(matched_qb)} customers)")
print(f"  Unmatched revenue:           {fmt_revenue(unmatched_revenue)} ({len(unmatched_qb)} customers)")
print(f"  Total QB revenue:            {fmt_revenue(total_revenue)}")
if total_revenue > 0:
    print(f"  Matched revenue share:       {matched_revenue/total_revenue*100:.1f}%")

# ============================================================
# SECTION 2: Name Mismatch Classification
# ============================================================
print("\n" + "=" * 90)
print("SECTION 2: NAME MISMATCH CLASSIFICATION")
print("=" * 90)

# Get SB companies for all matched QB customers
company_ids = list({m['matched_company_id'] for m in matched_qb if m.get('matched_company_id')})
company_map = {}
print(f"\n  Fetching {len(company_ids)} SB companies...")
for i in range(0, len(company_ids), 500):
    batch = company_ids[i:i+500]
    resp = sb.table('customer_companies').select(
        'id, company_name, qb_match_method, email_domains, qb_customer_id, contact_count'
    ).in_('id', batch).execute()
    for c in (resp.data or []):
        company_map[c['id']] = c

# Compare names and classify
exact_matches = []
mismatches = []

for q in matched_qb:
    sb_co = company_map.get(q['matched_company_id'], {})
    qb_name = (q.get('customer_name') or '').strip()
    sb_name = (sb_co.get('company_name') or '').strip()

    if qb_name.lower() == sb_name.lower():
        exact_matches.append(q)
    else:
        mismatches.append({
            'qb_name': qb_name,
            'sb_name': sb_name,
            'sb_company_id': q['matched_company_id'],
            'revenue': float(q.get('total_invoiced') or 0),
            'match_method': sb_co.get('qb_match_method'),
            'domains': sb_co.get('email_domains', []),
            'qb_id': q['id'],
        })

print(f"\n  Exact name match:   {len(exact_matches)}")
print(f"  Name MISMATCH:      {len(mismatches)}")
print(f"  Mismatch revenue:   {fmt_revenue(sum(m['revenue'] for m in mismatches))}")

# Classify mismatches
domain_derived = []
wrong_match = []
close_enough = []
person_name_sb = []

for m in mismatches:
    sb_name = m['sb_name']
    qb_name = m['qb_name']
    domains = m.get('domains') or []

    # Check if SB name is domain-derived
    if is_domain_derived(sb_name, domains):
        domain_derived.append(m)
        continue

    # Check if SB name is a person name
    if is_person_name(sb_name):
        person_name_sb.append(m)
        continue

    # Check word overlap
    qb_words = normalize_name(qb_name)
    sb_words = normalize_name(sb_name)

    if qb_words and sb_words and len(qb_words & sb_words) == 0:
        wrong_match.append(m)
    else:
        close_enough.append(m)

# Sort each category by revenue
domain_derived.sort(key=lambda x: x['revenue'], reverse=True)
wrong_match.sort(key=lambda x: x['revenue'], reverse=True)
close_enough.sort(key=lambda x: x['revenue'], reverse=True)
person_name_sb.sort(key=lambda x: x['revenue'], reverse=True)

print(f"\n  Classification breakdown:")
print(f"    Domain-derived SB name (safe rename):  {len(domain_derived)}  (rev: {fmt_revenue(sum(m['revenue'] for m in domain_derived))})")
print(f"    Wrong match (zero word overlap):        {len(wrong_match)}  (rev: {fmt_revenue(sum(m['revenue'] for m in wrong_match))})")
print(f"    Close enough (partial word overlap):    {len(close_enough)}  (rev: {fmt_revenue(sum(m['revenue'] for m in close_enough))})")
print(f"    Person-name SB company:                 {len(person_name_sb)}  (rev: {fmt_revenue(sum(m['revenue'] for m in person_name_sb))})")

print(f"\n  --- Top 20 WRONG MATCHES by revenue ---")
print(f"  {'QB Name':<35} {'SB Name':<35} {'Revenue':>12} {'Method':<15}")
print(f"  {'-'*35} {'-'*35} {'-'*12} {'-'*15}")
for m in wrong_match[:20]:
    print(f"  {m['qb_name'][:35]:<35} {m['sb_name'][:35]:<35} {fmt_revenue(m['revenue']):>12} {m['match_method'] or '-':<15}")

print(f"\n  --- Top 20 DOMAIN-DERIVED (safe rename) by revenue ---")
print(f"  {'QB Name':<35} {'SB Name':<35} {'Revenue':>12}")
print(f"  {'-'*35} {'-'*35} {'-'*12}")
for m in domain_derived[:20]:
    print(f"  {m['qb_name'][:35]:<35} {m['sb_name'][:35]:<35} {fmt_revenue(m['revenue']):>12}")

print(f"\n  --- Top 15 PERSON-NAME SB companies ---")
print(f"  {'QB Name':<35} {'SB Name':<35} {'Revenue':>12}")
print(f"  {'-'*35} {'-'*35} {'-'*12}")
for m in person_name_sb[:15]:
    print(f"  {m['qb_name'][:35]:<35} {m['sb_name'][:35]:<35} {fmt_revenue(m['revenue']):>12}")

# ============================================================
# SECTION 3: Wrong Match Deep Dive
# ============================================================
print("\n" + "=" * 90)
print("SECTION 3: WRONG MATCH DEEP DIVE -- shared emails causing bad matches")
print("=" * 90)

# For each wrong match, find the shared emails
# We need: qb_unique_emails (email, qb_customer_id) and customer_contacts (email_address, customer_company_id)
# The link was made because a qb_unique_email matched a customer_contact email

# Gather the QB record IDs and SB company IDs for wrong matches
wrong_qb_ids = [m['qb_id'] for m in wrong_match]
wrong_sb_ids = list({m['sb_company_id'] for m in wrong_match})

# Get QB unique emails for wrong-match QB customers (via qb_customer_id field in qb_unique_emails)
# qb_unique_emails.qb_customer_id links to qb_customers.qb_record_id? No -- let's check
# Actually qb_unique_emails.qb_customer_id is the QB-side customer ID text field
# We need to join by fetching qb_customers.id -> get their qb_record_id or customer_key_id

# Let's get the qb_unique_emails for wrong match QB customers
# qb_unique_emails.qb_customer_id matches qb_customers.customer_key_id (NOT qb_record_id)
print("\n  Fetching QB customer_key_ids for wrong-match customers...")
wrong_qb_details = {}
for i in range(0, len(wrong_qb_ids), 500):
    batch = wrong_qb_ids[i:i+500]
    resp = sb.table('qb_customers').select('id, customer_key_id, customer_name').in_('id', batch).execute()
    for r in (resp.data or []):
        wrong_qb_details[r['id']] = r

# Get qb_unique_emails for these QB customers
# qb_unique_emails.qb_customer_id = qb_customers.customer_key_id
qb_key_ids = [str(d['customer_key_id']) for d in wrong_qb_details.values() if d.get('customer_key_id')]

print(f"  Fetching qb_unique_emails for {len(qb_key_ids)} QB customers...")
qb_emails_by_customer = defaultdict(list)  # customer_key_id -> [emails]
for i in range(0, len(qb_key_ids), 500):
    batch = qb_key_ids[i:i+500]
    resp = sb.table('qb_unique_emails').select(
        'email, qb_customer_id, customer_name, free'
    ).eq('client_id', CLIENT_ID).in_('qb_customer_id', batch).execute()
    for r in (resp.data or []):
        qb_emails_by_customer[str(r['qb_customer_id'])].append(r)

# Get customer_contacts for wrong-match SB companies
print(f"  Fetching contacts for {len(wrong_sb_ids)} SB companies...")
sb_contacts_by_company = defaultdict(list)  # company_id -> [contacts]
for i in range(0, len(wrong_sb_ids), 500):
    batch = wrong_sb_ids[i:i+500]
    resp = sb.table('customer_contacts').select(
        'email_address, customer_company_id'
    ).in_('customer_company_id', batch).execute()
    for r in (resp.data or []):
        sb_contacts_by_company[r['customer_company_id']].append(r)

# Now find shared emails for each wrong match
free_provider_caused = 0
wrong_match_with_shared = 0
wrong_match_no_shared = 0
domain_correct_name_wrong = 0  # SB has the right domain but wrong name
truly_wrong_match = 0

print(f"\n  --- Wrong matches with shared email analysis ---")
print(f"  {'QB Name':<28} {'SB Name':<28} {'Shared Email(s)':<32} {'Free?':<5} {'Diagnosis':<20} {'Rev':>10}")
print(f"  {'-'*28} {'-'*28} {'-'*32} {'-'*5} {'-'*20} {'-'*10}")

shown = 0
for m in wrong_match[:50]:  # analyze top 50
    qb_detail = wrong_qb_details.get(m['qb_id'], {})
    qb_key_id = str(qb_detail.get('customer_key_id', ''))
    qb_emails_list = qb_emails_by_customer.get(qb_key_id, [])
    qb_email_set = {e['email'].lower().strip() for e in qb_emails_list if e.get('email')}

    sb_contacts_list = sb_contacts_by_company.get(m['sb_company_id'], [])
    sb_email_set = {c['email_address'].lower().strip() for c in sb_contacts_list if c.get('email_address')}

    # Check if SB company domains match QB email domains
    sb_domains = set()
    for d in (m.get('domains') or []):
        if isinstance(d, str):
            sb_domains.add(d.lower())
    qb_domains = set()
    for e in qb_email_set:
        if '@' in e:
            qb_domains.add(e.split('@')[1])

    domain_overlap = sb_domains & qb_domains
    non_free_domain_overlap = domain_overlap - FREE_PROVIDERS

    shared = qb_email_set & sb_email_set
    any_free = False
    if shared:
        wrong_match_with_shared += 1
        if non_free_domain_overlap:
            # Domain matches but SB company has wrong name -> name contamination
            domain_correct_name_wrong += 1
            diagnosis = "SB name wrong"
        else:
            # Shared email is free provider -> wrong match via shared person
            for email in shared:
                domain = email.split('@')[1] if '@' in email else ''
                if domain in FREE_PROVIDERS:
                    any_free = True
                    free_provider_caused += 1
            if any_free:
                diagnosis = "FREE email match"
                truly_wrong_match += 1
            else:
                diagnosis = "biz email match"
                domain_correct_name_wrong += 1

        if shown < 30:
            sample_email = list(shared)[0]
            print(f"  {m['qb_name'][:28]:<28} {m['sb_name'][:28]:<28} {sample_email[:32]:<32} {'Y' if any_free else 'n':<5} {diagnosis:<20} {fmt_revenue(m['revenue']):>10}")
            shown += 1
    else:
        wrong_match_no_shared += 1
        # No shared email -> check domain overlap
        if non_free_domain_overlap:
            domain_correct_name_wrong += 1
            diagnosis = "SB name wrong"
        else:
            truly_wrong_match += 1
            diagnosis = "TRULY WRONG"
        if shown < 30:
            qb_domain_sample = list(qb_domains)[:1]
            print(f"  {m['qb_name'][:28]:<28} {m['sb_name'][:28]:<28} {'QB:'+str(qb_domain_sample):<32} {'-':<5} {diagnosis:<20} {fmt_revenue(m['revenue']):>10}")
            shown += 1

print(f"\n  Wrong matches analyzed:             {min(len(wrong_match), 50)}")
print(f"  With shared email found:            {wrong_match_with_shared}")
print(f"  No shared email found:              {wrong_match_no_shared}")
print(f"  Caused by free-provider email:      {free_provider_caused}")
print(f"  Domain correct but SB name wrong:   {domain_correct_name_wrong}  (match OK, just rename SB)")
print(f"  Truly wrong match:                  {truly_wrong_match}  (need to unlink)")

# ============================================================
# SECTION 4: Multi-QB-to-One-SB (Contamination Check)
# ============================================================
print("\n" + "=" * 90)
print("SECTION 4: MULTI-QB-TO-ONE-SB (CONTAMINATION CHECK)")
print("=" * 90)

# Count how many QB customers point to each SB company
sb_to_qb_count = defaultdict(list)
for q in matched_qb:
    cid = q.get('matched_company_id')
    if cid:
        sb_to_qb_count[cid].append({
            'qb_name': q.get('customer_name', ''),
            'revenue': float(q.get('total_invoiced') or 0),
        })

multi_match = {k: v for k, v in sb_to_qb_count.items() if len(v) > 1}
print(f"\n  SB companies with >1 QB customer:  {len(multi_match)}")
print(f"  SB companies with exactly 1 QB:    {len(sb_to_qb_count) - len(multi_match)}")

# Sort by number of QB customers
multi_sorted = sorted(multi_match.items(), key=lambda x: len(x[1]), reverse=True)

print(f"\n  --- Worst offenders (most QB customers per SB company) ---")
print(f"  {'SB Company':<40} {'QB Count':>8} {'QB Names (first 3)':<60}")
print(f"  {'-'*40} {'-'*8} {'-'*60}")
for sb_id, qb_list in multi_sorted[:25]:
    sb_co = company_map.get(sb_id, {})
    sb_name = (sb_co.get('company_name') or 'UNKNOWN')[:40]
    qb_names = ', '.join([q['qb_name'][:25] for q in qb_list[:3]])
    total_rev = sum(q['revenue'] for q in qb_list)
    print(f"  {sb_name:<40} {len(qb_list):>8} {qb_names[:60]:<60}  rev: {fmt_revenue(total_rev)}")

# Distribution
dist = defaultdict(int)
for k, v in sb_to_qb_count.items():
    dist[len(v)] += 1
print(f"\n  Distribution of QB-per-SB:")
for n in sorted(dist.keys()):
    print(f"    {n} QB customer(s) -> {dist[n]} SB companies")

# ============================================================
# SECTION 5: Orphaned SB Companies
# ============================================================
print("\n" + "=" * 90)
print("SECTION 5: ORPHANED SB COMPANIES")
print("=" * 90)

# Get all SB companies
print("\n  Fetching all SB companies...")
all_sb_companies = paginate_all(
    'customer_companies',
    'id, company_name, qb_customer_id, contact_count, total_emails, email_domains, qb_match_method',
    filters={'client_id': CLIENT_ID}
)
print(f"  Fetched {len(all_sb_companies)} SB companies")

# Categorize
no_qb_no_contacts = []
no_qb_with_contacts = []
no_qb_person_name = []
has_qb = []

for c in all_sb_companies:
    qb_id = c.get('qb_customer_id')
    contacts = int(c.get('contact_count') or 0)
    name = c.get('company_name', '')
    emails = int(c.get('total_emails') or 0)

    if qb_id:
        has_qb.append(c)
    else:
        if contacts == 0 and emails == 0:
            no_qb_no_contacts.append(c)
        elif is_person_name(name):
            no_qb_person_name.append(c)
        else:
            no_qb_with_contacts.append(c)

print(f"\n  SB companies WITH QB link:               {len(has_qb)}")
print(f"  SB companies NO QB, NO contacts/emails:  {len(no_qb_no_contacts)}  (deletion candidates)")
print(f"  SB companies NO QB, WITH contacts:        {len(no_qb_with_contacts)}  (email-only)")
print(f"  SB companies NO QB, person-name:          {len(no_qb_person_name)}")

# Show deletion candidates
if no_qb_no_contacts:
    print(f"\n  --- Sample deletion candidates (no QB, no contacts, no emails) ---")
    for c in no_qb_no_contacts[:20]:
        print(f"    - {c['company_name'][:50]:<50} domains: {c.get('email_domains', [])}")

# Show person-name orphans
if no_qb_person_name:
    print(f"\n  --- Person-name SB companies (no QB link) ---")
    for c in no_qb_person_name[:20]:
        contacts = int(c.get('contact_count') or 0)
        emails = int(c.get('total_emails') or 0)
        print(f"    - {c['company_name'][:40]:<40} contacts={contacts} emails={emails}")

# ============================================================
# SECTION 6: QB Customer Quality
# ============================================================
print("\n" + "=" * 90)
print("SECTION 6: QB CUSTOMER QUALITY")
print("=" * 90)

# Revenue tier breakdown for unmatched
tiers = {
    '$0': 0,
    '$1-$1K': 0,
    '$1K-$10K': 0,
    '$10K-$100K': 0,
    '$100K+': 0,
}
tier_revenue = {k: 0.0 for k in tiers}

for q in unmatched_qb:
    rev = float(q.get('total_invoiced') or 0)
    if rev == 0:
        tiers['$0'] += 1
    elif rev < 1000:
        tiers['$1-$1K'] += 1
        tier_revenue['$1-$1K'] += rev
    elif rev < 10000:
        tiers['$1K-$10K'] += 1
        tier_revenue['$1K-$10K'] += rev
    elif rev < 100000:
        tiers['$10K-$100K'] += 1
        tier_revenue['$10K-$100K'] += rev
    else:
        tiers['$100K+'] += 1
        tier_revenue['$100K+'] += rev

print(f"\n  Unmatched QB customers by revenue tier:")
print(f"  {'Tier':<15} {'Count':>8} {'Revenue':>15}")
print(f"  {'-'*15} {'-'*8} {'-'*15}")
for tier_name in ['$0', '$1-$1K', '$1K-$10K', '$10K-$100K', '$100K+']:
    print(f"  {tier_name:<15} {tiers[tier_name]:>8} {fmt_revenue(tier_revenue[tier_name]):>15}")

# QB customers with vs without unique emails
print(f"\n  Checking QB customers with unique emails in qb_unique_emails...")
# Get all distinct qb_customer_ids from qb_unique_emails
qb_ue_customer_ids = set()
offset = 0
while True:
    resp = sb.table('qb_unique_emails').select(
        'qb_customer_id'
    ).eq('client_id', CLIENT_ID).range(offset, offset + 999).execute()
    batch = resp.data or []
    for r in batch:
        if r.get('qb_customer_id'):
            qb_ue_customer_ids.add(str(r['qb_customer_id']))
    if len(batch) < 1000:
        break
    offset += 1000

# Match against QB customers via customer_key_id (which maps to qb_unique_emails.qb_customer_id)
print(f"  Fetching customer_key_ids for all QB customers...")
all_qb_key_ids = {}
for i in range(0, len(all_qb), 500):
    batch_ids = [q['id'] for q in all_qb[i:i+500]]
    resp = sb.table('qb_customers').select('id, customer_key_id').in_('id', batch_ids).execute()
    for r in (resp.data or []):
        all_qb_key_ids[r['id']] = str(r.get('customer_key_id', ''))

qb_with_ue = 0
qb_without_ue = 0
unmatched_with_ue = 0
unmatched_without_ue = 0

for q in all_qb:
    key_id = all_qb_key_ids.get(q['id'], '')
    has_ue = key_id in qb_ue_customer_ids
    if has_ue:
        qb_with_ue += 1
    else:
        qb_without_ue += 1
    if not q.get('matched_company_id'):
        if has_ue:
            unmatched_with_ue += 1
        else:
            unmatched_without_ue += 1

print(f"\n  QB customers WITH unique emails:      {qb_with_ue}")
print(f"  QB customers WITHOUT unique emails:   {qb_without_ue}")
print(f"  Unmatched + WITH unique emails:       {unmatched_with_ue} (match opportunity!)")
print(f"  Unmatched + WITHOUT unique emails:    {unmatched_without_ue} (no email to match on)")

# Person-name vs business-name QB customers
person_qb = []
business_qb = []
for q in all_qb:
    name = q.get('customer_name', '')
    if is_person_name(name):
        person_qb.append(q)
    else:
        business_qb.append(q)

print(f"\n  QB customers that look like person names:   {len(person_qb)}")
print(f"  QB customers that look like businesses:     {len(business_qb)}")

# Top unmatched by revenue
unmatched_sorted = sorted(unmatched_qb, key=lambda x: float(x.get('total_invoiced') or 0), reverse=True)
print(f"\n  --- Top 15 UNMATCHED QB customers by revenue ---")
print(f"  {'Customer Name':<45} {'Revenue':>12} {'Tier':<10} {'Status':<10}")
print(f"  {'-'*45} {'-'*12} {'-'*10} {'-'*10}")
for q in unmatched_sorted[:15]:
    key_id = all_qb_key_ids.get(q['id'], '')
    has_ue = key_id in qb_ue_customer_ids
    ue_flag = " [has emails]" if has_ue else " [NO emails]"
    print(f"  {(q.get('customer_name','')[:42] + ue_flag):<58} {fmt_revenue(q.get('total_invoiced')):>12} {(q.get('customer_tier') or '-'):<10} {(q.get('customer_status') or '-'):<10}")

# ============================================================
# SECTION 7: Company Creation Pipeline Issues
# ============================================================
print("\n" + "=" * 90)
print("SECTION 7: COMPANY CREATION PIPELINE ISSUES")
print("=" * 90)

# Domain-derived company names (single lowercase word)
domain_created = 0
person_created = 0
has_qb_metadata = 0

for c in all_sb_companies:
    name = c.get('company_name', '')
    # Single lowercase word = likely domain-derived
    if ' ' not in name.strip() and name == name.lower():
        domain_created += 1
    # Person name pattern
    if is_person_name(name):
        person_created += 1
    # Has QB metadata
    if c.get('qb_customer_id') or c.get('qb_match_method'):
        has_qb_metadata += 1

print(f"\n  SB companies with domain-derived name (single lowercase word): {domain_created}")
print(f"  SB companies with person-name pattern:                         {person_created}")
print(f"  SB companies with QB metadata set:                             {has_qb_metadata}")
print(f"  SB companies without QB metadata:                              {len(all_sb_companies) - has_qb_metadata}")

# Match method distribution
method_dist = defaultdict(int)
for c in all_sb_companies:
    method = c.get('qb_match_method') or 'none'
    method_dist[method] += 1

print(f"\n  QB match method distribution:")
for method, count in sorted(method_dist.items(), key=lambda x: x[1], reverse=True):
    print(f"    {method:<25} {count:>6}")

# Show some domain-derived company names
domain_companies = [c for c in all_sb_companies if ' ' not in c.get('company_name', '').strip() and c.get('company_name', '') == c.get('company_name', '').lower()]
domain_companies.sort(key=lambda c: int(c.get('total_emails') or 0), reverse=True)
print(f"\n  --- Top 15 domain-derived SB companies by email volume ---")
for c in domain_companies[:15]:
    emails = int(c.get('total_emails') or 0)
    contacts = int(c.get('contact_count') or 0)
    has_qb_flag = "QB-linked" if c.get('qb_customer_id') else "no QB"
    print(f"    {c['company_name'][:30]:<30} emails={emails:>5} contacts={contacts:>3} {has_qb_flag}")


# ============================================================
# FINAL SUMMARY
# ============================================================
print("\n" + "=" * 90)
print("FINAL SUMMARY")
print("=" * 90)

print(f"""
  LANDSCAPE
    QB customers:                  {total_qb}
    SB companies:                  {total_sb}
    Matched:                       {matched_qb_count} QB -> {len(sb_to_qb_count)} SB companies
    Unmatched QB:                  {unmatched_qb_count} ({fmt_revenue(unmatched_revenue)} revenue)
    Email-only SB (no QB):         {sb_no_qb}

  NAME MISMATCHES ({len(mismatches)} total)
    Domain-derived (safe rename):  {len(domain_derived)}
    Wrong match (ZERO overlap):    {len(wrong_match)}  <-- NEEDS INVESTIGATION
    Close enough (partial match):  {len(close_enough)}
    Person-name SB company:        {len(person_name_sb)}

  WRONG MATCH ROOT CAUSES (top 50 analyzed)
    Shared email found:                {wrong_match_with_shared}
    No shared email found:             {wrong_match_no_shared}
    Free-provider email matches:       {free_provider_caused}
    Domain correct, SB name wrong:     {domain_correct_name_wrong}  (match OK, just rename)
    Truly wrong match (need unlink):   {truly_wrong_match}

  CONTAMINATION
    SB companies with >1 QB customer: {len(multi_match)}

  ORPHANS
    SB: no QB + no contacts/emails:  {len(no_qb_no_contacts)} (delete candidates)
    SB: person-name, no QB:          {len(no_qb_person_name)}

  MATCH OPPORTUNITY
    Unmatched QB WITH emails:        {unmatched_with_ue} (can try re-matching)
    Unmatched QB WITHOUT emails:     {unmatched_without_ue} (need manual or fuzzy)

  PIPELINE QUALITY
    Domain-derived SB names:         {domain_created}
    Person-name SB companies:        {person_created}
    Companies with QB metadata:      {has_qb_metadata} / {len(all_sb_companies)}
""")

print("=" * 90)
print("END OF DIAGNOSIS")
print("=" * 90)
