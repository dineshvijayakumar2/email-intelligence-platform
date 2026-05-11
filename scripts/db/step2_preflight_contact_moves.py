"""
Step 2 Pre-flight: Preview contact moves before executing.

For contacts whose email appears in qb_unique_emails, shows:
  - Current SB company name (what they're on now)
  - Target SB company name (where QB says they belong)
  - QB customer name + revenue

Decision gate: eyeball whether current_sb_name is real business (bad move)
vs person-name/junk/domain-derived (correct move).

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


print("=" * 100)
print("STEP 2 PRE-FLIGHT: Contact move preview")
print("=" * 100)

# ─── 1. Load QB truth ────────────────────────────────────────────────────
print("\n1. Loading QB unique emails (truth source)...")
qb_emails_raw = fetch_all('qb_unique_emails', 'qb_customer_id, email',
                           filters={'hide': False, 'email_invalid': False})
print(f"   {len(qb_emails_raw)} valid QB unique emails")

email_to_qb_key = {}
qb_key_to_emails = defaultdict(set)
for qe in qb_emails_raw:
    email = (qe.get('email') or '').strip().lower()
    qb_key = qe.get('qb_customer_id')
    if email and qb_key:
        qb_key_to_emails[qb_key].add(email)
        if email not in email_to_qb_key:
            email_to_qb_key[email] = qb_key

# ─── 2. Load QB customers (now with matched_company_id after Step 1) ────
print("\n2. Loading QB customers...")
qb_customers = fetch_all('qb_customers',
    'customer_key_id, customer_name, total_invoiced, matched_company_id')

qb_key_to_info = {}
for q in qb_customers:
    key = q.get('customer_key_id')
    if key:
        qb_key_to_info[key] = q

qb_matched_count = sum(1 for q in qb_customers if q.get('matched_company_id'))
print(f"   {len(qb_customers)} total QB customers ({qb_matched_count} matched)")

# ─── 3. Load all contacts ────────────────────────────────────────────────
print("\n3. Loading contacts...")
contacts = fetch_all('customer_contacts', 'id, email_address, customer_company_id')
print(f"   {len(contacts)} contacts")

# ─── 4. Load SB company names for display ────────────────────────────────
print("\n4. Loading SB company names...")
sb_companies = fetch_all('customer_companies', 'id, company_name')
sb_id_to_name = {c['id']: c.get('company_name', '?') for c in sb_companies}
print(f"   {len(sb_companies)} SB companies")

# ─── 5. Compute moves ────────────────────────────────────────────────────
print("\n5. Computing contact moves...")

moves = []
already_correct = 0
no_sb_yet = 0
ambiguous = 0

email_to_qb_keys = defaultdict(set)
for qb_key, emails in qb_key_to_emails.items():
    for email in emails:
        email_to_qb_keys[email].add(qb_key)

for c in contacts:
    email = (c.get('email_address') or '').strip().lower()
    if not email or email not in email_to_qb_key:
        continue

    qb_keys = email_to_qb_keys.get(email, set())
    if len(qb_keys) > 1:
        ambiguous += 1
        continue

    qb_key = list(qb_keys)[0]
    qb_info = qb_key_to_info.get(qb_key)
    if not qb_info:
        continue

    target_sb = qb_info.get('matched_company_id')
    current_sb = c.get('customer_company_id')

    if not target_sb:
        no_sb_yet += 1
        continue

    if current_sb == target_sb:
        already_correct += 1
        continue

    moves.append({
        'contact_id': c['id'],
        'email': email,
        'current_sb_id': current_sb,
        'current_sb_name': sb_id_to_name.get(current_sb, '(none)') if current_sb else '(none)',
        'target_sb_id': target_sb,
        'target_sb_name': sb_id_to_name.get(target_sb, '?'),
        'qb_customer_name': qb_info.get('customer_name', '?'),
        'qb_revenue': float(qb_info.get('total_invoiced') or 0),
    })

print(f"\n   Already correct:  {already_correct:>6}")
print(f"   Need to MOVE:     {len(moves):>6}")
print(f"   No SB yet:        {no_sb_yet:>6}")
print(f"   Ambiguous:        {ambiguous:>6}")

# ─── 6. Sample moves ─────────────────────────────────────────────────────
moves_sorted = sorted(moves, key=lambda x: x['qb_revenue'], reverse=True)

print(f"\n{'='*100}")
print(f"Top 50 contact moves by QB revenue (eyeball: current_sb should be junk/person name)")
print(f"{'='*100}")
print(f"  {'Email':<35} {'Current SB':<30} {'->':>2} {'Target SB (QB)':<30} {'Revenue':>10}")
print(f"  {'-'*35} {'-'*30} {'--':>2} {'-'*30} {'-'*10}")

for m in moves_sorted[:50]:
    print(f"  {m['email'][:35]:<35} {m['current_sb_name'][:30]:<30} -> {m['target_sb_name'][:30]:<30} ${m['qb_revenue']:>8,.0f}")

# ─── 7. Classify current SB names ────────────────────────────────────────
print(f"\n{'='*100}")
print("Current SB name patterns for contacts being moved")
print(f"{'='*100}")

from_null = sum(1 for m in moves if m['current_sb_id'] is None)
from_named = [m for m in moves if m['current_sb_id'] is not None]

# Heuristic: person-name companies tend to be short, no Pty/Ltd/Inc
person_name_indicators = 0
domain_derived = 0
legitimate_business = 0

for m in from_named:
    name = m['current_sb_name']
    name_lower = name.lower()
    if any(kw in name_lower for kw in ['pty', 'ltd', 'inc', 'group', 'agency', 'studio', 'media',
                                        'print', 'design', 'solutions', 'services', 'australia',
                                        'international', 'consulting', 'partners', 'holdings']):
        legitimate_business += 1
    elif len(name.split()) <= 3 and not any(c.isdigit() for c in name):
        person_name_indicators += 1
    else:
        domain_derived += 1

print(f"  From NULL (unassigned):           {from_null:>6}")
print(f"  From person-name SB:              {person_name_indicators:>6}")
print(f"  From domain-derived SB:           {domain_derived:>6}")
print(f"  From legitimate business name SB: {legitimate_business:>6}")

if legitimate_business > 0:
    print(f"\n  WARNING: {legitimate_business} contacts are being moved FROM companies that look like real businesses.")
    print(f"  Sample (first 15):")
    legit_moves = [m for m in from_named if any(kw in m['current_sb_name'].lower()
                   for kw in ['pty', 'ltd', 'inc', 'group', 'agency', 'studio', 'media',
                              'print', 'design', 'solutions', 'services', 'australia',
                              'international', 'consulting', 'partners', 'holdings'])]
    legit_moves.sort(key=lambda x: x['qb_revenue'], reverse=True)
    for m in legit_moves[:15]:
        same = " (SAME NAME)" if m['current_sb_name'].lower().strip() == m['target_sb_name'].lower().strip() else ""
        print(f"    {m['email'][:30]:<30} FROM: {m['current_sb_name'][:25]:<25} TO: {m['target_sb_name'][:25]:<25}{same}")

# ─── 8. Unique SB companies affected ─────────────────────────────────────
print(f"\n{'='*100}")
print("SB companies affected by moves")
print(f"{'='*100}")

losing_sbs = defaultdict(int)
gaining_sbs = defaultdict(int)
for m in moves:
    if m['current_sb_id']:
        losing_sbs[m['current_sb_id']] += 1
    gaining_sbs[m['target_sb_id']] += 1

print(f"  {len(losing_sbs)} SB companies will lose contacts")
print(f"  {len(gaining_sbs)} SB companies will gain contacts")

print(f"\n  Top 10 SB companies losing most contacts:")
losing_sorted = sorted(losing_sbs.items(), key=lambda x: x[1], reverse=True)
for sb_id, count in losing_sorted[:10]:
    print(f"    {sb_id_to_name.get(sb_id, '?')[:45]:<45} losing {count} contacts")

# ─── Decision ─────────────────────────────────────────────────────────────
print(f"\n{'='*100}")
print("DECISION GATE")
print(f"{'='*100}")
print(f"  {len(moves)} contacts ready to move")
print(f"  {already_correct} already on correct SB")
print(f"  Eyeball the top 50 moves above.")
print(f"  If current SB names are mostly person-names/domain-derived -> safe to proceed.")
print(f"  If many look like real businesses being LOST -> investigate before executing.")
print(f"{'='*100}")
