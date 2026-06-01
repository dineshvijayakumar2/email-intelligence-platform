"""
Diagnose company name mismatches between QB customers and SB companies.
Shows scope of cleanup needed before creating companies from QB.
"""
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
from dotenv import load_dotenv
from supabase import create_client

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
load_dotenv(env_path)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
CLIENT_ID = "241d7b99-f099-4557-96e5-212c4af10812"

print("=" * 80)
print("DIAGNOSIS: Company Name Mismatches (QB vs Supabase)")
print("=" * 80)

# 1. Get all matched QB customers with their SB company
print("\n1. Fetching matched QB customers...")
matched = []
offset = 0
while True:
    resp = sb.table('qb_customers').select(
        'id, customer_name, total_invoiced, matched_company_id'
    ).eq('client_id', CLIENT_ID).not_.is_(
        'matched_company_id', 'null'
    ).range(offset, offset + 999).execute()
    matched.extend(resp.data or [])
    if len(resp.data or []) < 1000:
        break
    offset += 1000

print(f"   {len(matched)} matched QB customers")

# 2. Get the SB company names for those
company_ids = list({m['matched_company_id'] for m in matched if m.get('matched_company_id')})
company_map = {}
for i in range(0, len(company_ids), 500):
    batch = company_ids[i:i+500]
    resp = sb.table('customer_companies').select(
        'id, company_name, qb_match_method, email_domains'
    ).in_('id', batch).execute()
    for c in (resp.data or []):
        company_map[c['id']] = c

# 3. Compare names
mismatches = []
exact_matches = []
for m in matched:
    sb_company = company_map.get(m['matched_company_id'], {})
    qb_name = (m.get('customer_name') or '').strip()
    sb_name = (sb_company.get('company_name') or '').strip()

    if qb_name.lower() != sb_name.lower():
        mismatches.append({
            'qb_name': qb_name,
            'sb_name': sb_name,
            'sb_company_id': m['matched_company_id'],
            'revenue': float(m.get('total_invoiced') or 0),
            'match_method': sb_company.get('qb_match_method'),
            'domains': sb_company.get('email_domains', []),
        })
    else:
        exact_matches.append(qb_name)

mismatches.sort(key=lambda x: x['revenue'], reverse=True)

print(f"\n2. NAME COMPARISON:")
print(f"   Exact name match:  {len(exact_matches)}")
print(f"   Name MISMATCH:     {len(mismatches)}")
mismatch_revenue = sum(m['revenue'] for m in mismatches)
total_revenue = sum(float(m.get('total_invoiced') or 0) for m in matched)
print(f"   Mismatch revenue:  ${mismatch_revenue:,.0f} / ${total_revenue:,.0f} total matched")

print(f"\n3. TOP 30 MISMATCHES (by revenue):")
print(f"   {'QB Name':<35} {'SB Name':<35} {'Revenue':>12} {'Method':<15}")
print(f"   {'-'*35} {'-'*35} {'-'*12} {'-'*15}")
for m in mismatches[:30]:
    print(f"   {m['qb_name'][:35]:<35} {m['sb_name'][:35]:<35} ${m['revenue']:>10,.0f} {m['match_method'] or '-':<15}")

# 4. Check for potential duplicate names after rename
print(f"\n4. DUPLICATE CHECK (would QB rename create duplicates?)")
# Get all existing company names
all_companies_resp = sb.table('customer_companies').select(
    'id, company_name'
).eq('client_id', CLIENT_ID).execute()
existing_names = {}
for c in (all_companies_resp.data or []):
    key = (c.get('company_name') or '').strip().lower()
    if key not in existing_names:
        existing_names[key] = []
    existing_names[key].append(c['id'])

# Check which QB renames would collide with existing companies
collisions = []
for m in mismatches:
    qb_key = m['qb_name'].lower()
    if qb_key in existing_names:
        existing_ids = existing_names[qb_key]
        if m['sb_company_id'] not in existing_ids:
            collisions.append({
                'qb_name': m['qb_name'],
                'current_sb_name': m['sb_name'],
                'would_collide_with': existing_ids,
                'revenue': m['revenue'],
            })

if collisions:
    print(f"   {len(collisions)} renames would collide with existing companies:")
    for c in collisions[:15]:
        print(f"   - '{c['qb_name']}' (currently '{c['current_sb_name']}') -> would clash with {len(c['would_collide_with'])} existing")
else:
    print(f"   No collisions detected — safe to rename all {len(mismatches)} mismatches")

# 5. Categorize mismatches
print(f"\n5. MISMATCH CATEGORIES:")
person_like = []
case_only = []
substantive = []
for m in mismatches:
    qb_lower = m['qb_name'].lower()
    sb_lower = m['sb_name'].lower()
    # Case-only difference
    if qb_lower == sb_lower:
        case_only.append(m)
    # SB name looks like a person (2 words, both capitalized, no domain words)
    elif len(m['sb_name'].split()) == 2 and all(w[0].isupper() for w in m['sb_name'].split() if w):
        person_like.append(m)
    else:
        substantive.append(m)

print(f"   Person-name companies (like 'Daniel Bauer'):  {len(person_like)}")
print(f"   Substantive name differences:                 {len(substantive)}")
print(f"   Case-only differences:                        {len(case_only)}")

if person_like:
    print(f"\n   Person-name examples:")
    for m in person_like[:10]:
        print(f"   - SB: '{m['sb_name']}' -> QB: '{m['qb_name']}' (${m['revenue']:,.0f})")

# 6. Unmatched QB customers (no SB company at all)
print(f"\n6. UNMATCHED QB CUSTOMERS (no SB company):")
unmatched_resp = sb.table('qb_customers').select(
    'id', count='exact'
).eq('client_id', CLIENT_ID).is_(
    'matched_company_id', 'null'
).limit(0).execute()
unmatched_count = unmatched_resp.count

# Top unmatched by revenue
unmatched_top = sb.table('qb_customers').select(
    'customer_name, total_invoiced'
).eq('client_id', CLIENT_ID).is_(
    'matched_company_id', 'null'
).order('total_invoiced', desc=True).range(0, 9).execute()

print(f"   {unmatched_count} QB customers with NO Supabase company")
print(f"\n   Top 10 unmatched (by revenue):")
for u in (unmatched_top.data or []):
    print(f"   - {u['customer_name']:<40} ${float(u.get('total_invoiced') or 0):>10,.0f}")

print(f"\n{'='*80}")
print("SUMMARY")
print(f"{'='*80}")
print(f"  Matched QB customers:     {len(matched)}")
print(f"  Name mismatches to fix:   {len(mismatches)} (${mismatch_revenue:,.0f} revenue)")
print(f"  Rename collisions:        {len(collisions)}")
print(f"  Unmatched (need creation):{unmatched_count}")
print(f"{'='*80}")
