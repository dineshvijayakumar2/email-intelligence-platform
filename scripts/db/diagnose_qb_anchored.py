"""
QB-Anchored Diagnosis: QB is sole source of truth for company identity.

For every QB customer, determine:
  1. Does it already have a correct 1:1 SB company match?
  2. How many customer_contacts will need to move?
  3. Which SB companies become orphaned after reassignment?
  4. Which contacts have emails NOT in qb_unique_emails (can't be QB-linked)?

Read-only -- no writes.
"""
import os, sys
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


def fetch_all(table, select, filters=None, not_null=None, is_null=None):
    """Paginate through a Supabase table."""
    rows = []
    offset = 0
    while True:
        q = sb.table(table).select(select).eq('client_id', CLIENT_ID)
        if filters:
            for k, v in filters.items():
                q = q.eq(k, v)
        if not_null:
            for col in not_null:
                q = q.not_.is_(col, 'null')
        if is_null:
            for col in is_null:
                q = q.is_(col, 'null')
        resp = q.range(offset, offset + 999).execute()
        rows.extend(resp.data or [])
        if len(resp.data or []) < 1000:
            break
        offset += 1000
    return rows


def fetch_all_no_client(table, select, in_filter=None):
    """Paginate without client_id filter (for customer_companies which may not have it)."""
    rows = []
    offset = 0
    while True:
        q = sb.table(table).select(select)
        if in_filter:
            col, vals = in_filter
            q = q.in_(col, vals)
        resp = q.range(offset, offset + 999).execute()
        rows.extend(resp.data or [])
        if len(resp.data or []) < 1000:
            break
        offset += 1000
    return rows


print("=" * 100)
print("QB-ANCHORED DIAGNOSIS: QB as sole source of truth")
print("=" * 100)

# ─── Step 1: Fetch all QB customers ───────────────────────────────────────
print("\n1. Fetching QB customers...")
qb_customers = fetch_all('qb_customers',
    'customer_key_id, customer_name, total_invoiced, matched_company_id')
print(f"   {len(qb_customers)} QB customers")

qb_matched = [q for q in qb_customers if q.get('matched_company_id')]
qb_unmatched = [q for q in qb_customers if not q.get('matched_company_id')]
print(f"   {len(qb_matched)} currently matched to an SB company")
print(f"   {len(qb_unmatched)} unmatched (need SB company created)")

# ─── Step 2: Fetch qb_unique_emails (the QB truth) ───────────────────────
print("\n2. Fetching qb_unique_emails...")
qb_emails_raw = fetch_all('qb_unique_emails', 'qb_customer_id, email',
                           filters={'hide': False, 'email_invalid': False})
print(f"   {len(qb_emails_raw)} valid QB unique emails")

# Build: qb_customer_key -> set of emails
qb_to_emails = defaultdict(set)
all_qb_emails = set()
for qe in qb_emails_raw:
    qb_key = qe.get('qb_customer_id')
    email = (qe.get('email') or '').strip().lower()
    if qb_key and email:
        qb_to_emails[qb_key].add(email)
        all_qb_emails.add(email)

qb_with_emails = set(qb_to_emails.keys())
print(f"   {len(qb_with_emails)} QB customers have at least 1 email")
print(f"   {len(all_qb_emails)} distinct emails across all QB customers")

# ─── Step 3: Fetch all customer_contacts ──────────────────────────────────
print("\n3. Fetching customer_contacts...")
contacts_raw = fetch_all('customer_contacts',
    'id, email_address, customer_company_id')
print(f"   {len(contacts_raw)} total contacts")

contacts_with_company = [c for c in contacts_raw if c.get('customer_company_id')]
contacts_no_company = [c for c in contacts_raw if not c.get('customer_company_id')]
print(f"   {len(contacts_with_company)} assigned to an SB company")
print(f"   {len(contacts_no_company)} with no SB company")

# Build: email -> list of contacts (some emails may have multiple contact rows)
email_to_contacts = defaultdict(list)
for c in contacts_raw:
    email = (c.get('email_address') or '').strip().lower()
    if email:
        email_to_contacts[email].append(c)

# ─── Step 4: Which contacts are QB-linkable? ─────────────────────────────
print("\n4. Contact linkability via QB emails...")
qb_linkable_emails = set(email_to_contacts.keys()) & all_qb_emails
non_qb_emails = set(email_to_contacts.keys()) - all_qb_emails

qb_linkable_contacts = []
non_qb_contacts = []
for email in qb_linkable_emails:
    qb_linkable_contacts.extend(email_to_contacts[email])
for email in non_qb_emails:
    non_qb_contacts.extend(email_to_contacts[email])

print(f"   {len(qb_linkable_emails)} contact emails found in qb_unique_emails -> {len(qb_linkable_contacts)} contacts")
print(f"   {len(non_qb_emails)} contact emails NOT in qb_unique_emails -> {len(non_qb_contacts)} contacts")

# ─── Step 5: For QB-linkable contacts, determine correct SB company ──────
print("\n5. Determining correct company for each QB-linkable contact...")

# For each contact email in QB, find which QB customer(s) own it
email_to_qb_keys = defaultdict(set)
for qb_key, emails in qb_to_emails.items():
    for email in emails:
        email_to_qb_keys[email].add(qb_key)

# Build QB customer key -> matched SB company
qb_key_to_sb = {}
qb_key_to_info = {}
for q in qb_customers:
    key = q.get('customer_key_id')
    if key:
        qb_key_to_info[key] = q
        if q.get('matched_company_id'):
            qb_key_to_sb[key] = q['matched_company_id']

# For each QB-linkable contact, what SHOULD its company be?
contacts_correct = 0
contacts_need_move = 0
contacts_need_move_but_no_sb = 0  # QB customer has no SB company yet
contacts_ambiguous = 0  # email owned by multiple QB customers

move_details = []  # (contact_id, current_sb, target_sb, email, qb_name)

for email in qb_linkable_emails:
    qb_keys = email_to_qb_keys[email]
    contacts = email_to_contacts[email]

    if len(qb_keys) > 1:
        contacts_ambiguous += len(contacts)
        continue

    qb_key = list(qb_keys)[0]
    target_sb = qb_key_to_sb.get(qb_key)  # could be None if QB unmatched

    for c in contacts:
        current_sb = c.get('customer_company_id')
        if target_sb and current_sb == target_sb:
            contacts_correct += 1
        elif target_sb:
            contacts_need_move += 1
            move_details.append({
                'contact_id': c['id'],
                'current_sb': current_sb,
                'target_sb': target_sb,
                'email': email,
                'qb_key': qb_key,
            })
        else:
            contacts_need_move_but_no_sb += 1

print(f"   Already on correct SB company:     {contacts_correct}")
print(f"   Need to MOVE to different SB:      {contacts_need_move}")
print(f"   QB customer has no SB yet:         {contacts_need_move_but_no_sb}")
print(f"   Ambiguous (email in 2+ QB custs):  {contacts_ambiguous}")

# ─── Step 6: SB company impact ───────────────────────────────────────────
print("\n6. SB company impact analysis...")

# Which SB companies are "QB-anchored" (have at least 1 QB customer matched to them)?
qb_anchored_sbs = set(q['matched_company_id'] for q in qb_matched)
print(f"   {len(qb_anchored_sbs)} SB companies currently have a QB match")

# How many QB customers per SB company? (contamination check)
sb_to_qb_count = defaultdict(int)
for q in qb_matched:
    sb_to_qb_count[q['matched_company_id']] += 1

multi_qb_sbs = {sb: count for sb, count in sb_to_qb_count.items() if count > 1}
print(f"   {len(multi_qb_sbs)} SB companies have >1 QB customer matched (contaminated)")
if multi_qb_sbs:
    dist = defaultdict(int)
    for count in multi_qb_sbs.values():
        dist[count] += 1
    for n in sorted(dist.keys()):
        print(f"      {n} QB customers -> {dist[n]} SB companies")

# All SB companies for this client
print("\n   Fetching all SB companies...")
all_sb_companies = fetch_all('customer_companies', 'id, company_name', filters={})
all_sb_ids = set(c['id'] for c in all_sb_companies)
print(f"   {len(all_sb_companies)} total SB companies")

# After reassignment, which SB companies lose all QB-linkable contacts?
# SB companies that currently have contacts but won't after QB-anchored moves
sbs_losing_contacts = defaultdict(int)  # sb_id -> count of contacts being moved away
sbs_gaining_contacts = defaultdict(int)  # sb_id -> count of contacts being moved in

for m in move_details:
    if m['current_sb']:
        sbs_losing_contacts[m['current_sb']] += 1
    sbs_gaining_contacts[m['target_sb']] += 1

print(f"\n   {len(sbs_losing_contacts)} SB companies will lose contacts")
print(f"   {len(sbs_gaining_contacts)} SB companies will gain contacts")

# Which SB companies become fully orphaned?
# An SB company is orphaned if: no QB customer points to it AND all its contacts move away
sb_contact_counts = defaultdict(int)
for c in contacts_with_company:
    sb_contact_counts[c['customer_company_id']] += 1

potential_orphans = []
for sb_id in all_sb_ids:
    has_qb_match = sb_id in qb_anchored_sbs
    current_contacts = sb_contact_counts.get(sb_id, 0)
    losing = sbs_losing_contacts.get(sb_id, 0)
    remaining_contacts = current_contacts - losing

    if not has_qb_match and remaining_contacts <= 0 and current_contacts > 0:
        potential_orphans.append(sb_id)

no_contacts_no_qb = [sb_id for sb_id in all_sb_ids
                      if sb_id not in qb_anchored_sbs
                      and sb_contact_counts.get(sb_id, 0) == 0]

print(f"\n   SB companies with no QB match AND no contacts currently: {len(no_contacts_no_qb)}")
print(f"   SB companies that will become orphaned after moves:      {len(potential_orphans)}")

# ─── Step 7: What about non-QB contacts? ─────────────────────────────────
print("\n7. Non-QB contacts (emails not in qb_unique_emails)...")
non_qb_with_company = [c for c in non_qb_contacts if c.get('customer_company_id')]
non_qb_no_company = [c for c in non_qb_contacts if not c.get('customer_company_id')]
print(f"   {len(non_qb_with_company)} have an SB company assignment")
print(f"   {len(non_qb_no_company)} have no SB company")

# How many of these are on QB-anchored SB companies?
non_qb_on_qb_anchored = [c for c in non_qb_with_company
                          if c['customer_company_id'] in qb_anchored_sbs]
non_qb_on_non_anchored = [c for c in non_qb_with_company
                           if c['customer_company_id'] not in qb_anchored_sbs]
print(f"   {len(non_qb_on_qb_anchored)} are on QB-anchored SB companies (they stay)")
print(f"   {len(non_qb_on_non_anchored)} are on non-QB SB companies (orphan candidates)")

# ─── Step 8: QB customers needing new SB companies ───────────────────────
print("\n8. QB customers that need NEW SB companies created...")
need_new_sb = [q for q in qb_unmatched]
need_new_with_emails = [q for q in need_new_sb if q['customer_key_id'] in qb_with_emails]
need_new_no_emails = [q for q in need_new_sb if q['customer_key_id'] not in qb_with_emails]
print(f"   {len(need_new_sb)} QB customers with no SB match")
print(f"   {len(need_new_with_emails)} of those have emails (contacts can be linked)")
print(f"   {len(need_new_no_emails)} have no emails at all (empty SB shell)")

# Revenue breakdown
rev_need_new_with = sum(float(q.get('total_invoiced') or 0) for q in need_new_with_emails)
rev_need_new_without = sum(float(q.get('total_invoiced') or 0) for q in need_new_no_emails)
print(f"   Revenue (with emails):    ${rev_need_new_with:>12,.0f}")
print(f"   Revenue (no emails):      ${rev_need_new_without:>12,.0f}")

# Top 15 unmatched by revenue
need_new_sb_sorted = sorted(need_new_sb, key=lambda q: float(q.get('total_invoiced') or 0), reverse=True)
print(f"\n   Top 15 unmatched QB customers by revenue:")
print(f"   {'QB Customer':<45} {'Revenue':>12} {'Has Emails':>10}")
print(f"   {'-'*45} {'-'*12} {'-'*10}")
for q in need_new_sb_sorted[:15]:
    rev = float(q.get('total_invoiced') or 0)
    has_em = 'Yes' if q['customer_key_id'] in qb_with_emails else 'No'
    print(f"   {(q.get('customer_name') or '?')[:45]:<45} ${rev:>10,.0f} {has_em:>10}")

# ─── Step 9: Contaminated SB companies detail ────────────────────────────
print("\n9. Contaminated SB companies (>1 QB customer matched)...")

if multi_qb_sbs:
    # Fetch names for contaminated SB companies
    contaminated_ids = list(multi_qb_sbs.keys())[:200]
    sb_name_map = {}
    for i in range(0, len(contaminated_ids), 500):
        batch = contaminated_ids[i:i+500]
        resp = sb.table('customer_companies').select('id, company_name').in_('id', batch).execute()
        for r in (resp.data or []):
            sb_name_map[r['id']] = r.get('company_name', '?')

    # For each contaminated SB, list its QB customers
    sb_to_qb_names = defaultdict(list)
    for q in qb_matched:
        sb_id = q['matched_company_id']
        if sb_id in multi_qb_sbs:
            sb_to_qb_names[sb_id].append({
                'name': q.get('customer_name', '?'),
                'revenue': float(q.get('total_invoiced') or 0),
                'key': q.get('customer_key_id'),
            })

    # Sort by total revenue at risk
    contaminated_list = []
    for sb_id, qb_list in sb_to_qb_names.items():
        total_rev = sum(q['revenue'] for q in qb_list)
        contaminated_list.append({
            'sb_id': sb_id,
            'sb_name': sb_name_map.get(sb_id, '?'),
            'qb_count': len(qb_list),
            'total_revenue': total_rev,
            'qb_customers': sorted(qb_list, key=lambda x: x['revenue'], reverse=True),
        })
    contaminated_list.sort(key=lambda x: x['total_revenue'], reverse=True)

    print(f"\n   Top 20 contaminated SB companies:")
    for item in contaminated_list[:20]:
        print(f"\n   SB: {item['sb_name'][:50]:<50} ({item['qb_count']} QB custs, ${item['total_revenue']:>10,.0f} rev)")
        for qb in item['qb_customers'][:5]:
            print(f"      QB: {qb['name'][:45]:<45} ${qb['revenue']:>10,.0f}")
        if len(item['qb_customers']) > 5:
            print(f"      ... and {len(item['qb_customers']) - 5} more")

# ─── SUMMARY ─────────────────────────────────────────────────────────────
total_rev = sum(float(q.get('total_invoiced') or 0) for q in qb_customers)
matched_rev = sum(float(q.get('total_invoiced') or 0) for q in qb_matched)

print(f"\n{'='*100}")
print("SUMMARY: QB-ANCHORED CLEANUP SCOPE")
print(f"{'='*100}")
print(f"\n  QB CUSTOMERS")
print(f"  Total:                         {len(qb_customers):>8}   ${total_rev:>14,.0f}")
print(f"  Already matched to SB:         {len(qb_matched):>8}   ${matched_rev:>14,.0f}")
print(f"  Need new SB company:           {len(qb_unmatched):>8}   ${total_rev - matched_rev:>14,.0f}")
print(f"    - with emails (linkable):    {len(need_new_with_emails):>8}   ${rev_need_new_with:>14,.0f}")
print(f"    - no emails (shell only):    {len(need_new_no_emails):>8}   ${rev_need_new_without:>14,.0f}")

print(f"\n  CONTACTS")
print(f"  Total contacts:                {len(contacts_raw):>8}")
print(f"  QB-linkable (email in QB):     {len(qb_linkable_contacts):>8}")
print(f"    - already correct:           {contacts_correct:>8}")
print(f"    - need to MOVE:              {contacts_need_move:>8}")
print(f"    - QB has no SB yet:          {contacts_need_move_but_no_sb:>8}")
print(f"    - ambiguous (multi-QB):      {contacts_ambiguous:>8}")
print(f"  Non-QB contacts:               {len(non_qb_contacts):>8}")
print(f"    - on QB-anchored SB:         {len(non_qb_on_qb_anchored):>8}  (stay put)")
print(f"    - on non-QB SB:              {len(non_qb_on_non_anchored):>8}  (orphan risk)")

print(f"\n  SB COMPANIES")
print(f"  Total:                         {len(all_sb_companies):>8}")
print(f"  QB-anchored (have QB match):   {len(qb_anchored_sbs):>8}")
print(f"  Contaminated (>1 QB):          {len(multi_qb_sbs):>8}")
print(f"  Will lose contacts:            {len(sbs_losing_contacts):>8}")
print(f"  Already empty + no QB:         {len(no_contacts_no_qb):>8}")
print(f"  Will become orphaned:          {len(potential_orphans):>8}")

print(f"\n{'='*100}")
