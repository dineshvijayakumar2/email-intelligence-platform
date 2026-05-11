"""
Step 1 Pre-flight: Check name collisions before creating SB rows from QB customers.

For the 8,925 unmatched QB customers (matched_company_id IS NULL), how many
already have an identically-named SB company in customer_companies?

Decision gate:
  - <5% collision → safe to bulk-create, collisions handled as "link existing"
  - >=5% collision → need a "link existing SB to QB" path first

Read-only — no writes.
"""
import os, sys, json
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


print("=" * 100)
print("STEP 1 PRE-FLIGHT: Name collision check for unmatched QB customers")
print("=" * 100)

# ─── 1. Fetch unmatched QB customers ─────────────────────────────────────
print("\n1. Fetching unmatched QB customers (matched_company_id IS NULL)...")
qb_unmatched = fetch_all('qb_customers',
    'customer_key_id, customer_name, total_invoiced, matched_company_id',
    is_null=['matched_company_id'])
print(f"   {len(qb_unmatched)} unmatched QB customers")

# Also fetch matched for context
qb_matched = fetch_all('qb_customers',
    'customer_key_id, customer_name, total_invoiced, matched_company_id',
    not_null=['matched_company_id'])
print(f"   {len(qb_matched)} matched QB customers (for reference)")

# ─── 2. Fetch all existing SB company names ──────────────────────────────
print("\n2. Fetching all SB company names...")
sb_companies = fetch_all('customer_companies', 'id, company_name')
print(f"   {len(sb_companies)} SB companies")

# Build lookup: normalized name → list of SB company records
sb_name_lookup = defaultdict(list)
for c in sb_companies:
    name = (c.get('company_name') or '').strip().lower()
    if name:
        sb_name_lookup[name].append(c)

# ─── 3. Check collisions ─────────────────────────────────────────────────
print("\n3. Checking name collisions...")

collisions = []
no_collision = []

for qb in qb_unmatched:
    qb_name = (qb.get('customer_name') or '').strip()
    qb_name_lower = qb_name.lower()
    revenue = float(qb.get('total_invoiced') or 0)

    existing = sb_name_lookup.get(qb_name_lower, [])
    if existing:
        collisions.append({
            'qb_key': qb['customer_key_id'],
            'qb_name': qb_name,
            'revenue': revenue,
            'sb_matches': existing,
        })
    else:
        no_collision.append({
            'qb_key': qb['customer_key_id'],
            'qb_name': qb_name,
            'revenue': revenue,
        })

collision_rate = len(collisions) / len(qb_unmatched) * 100 if qb_unmatched else 0
collision_revenue = sum(c['revenue'] for c in collisions)
no_collision_revenue = sum(c['revenue'] for c in no_collision)

print(f"\n   COLLISIONS:    {len(collisions):>6}  ({collision_rate:.1f}%)  ${collision_revenue:>12,.0f} revenue")
print(f"   NO COLLISION:  {len(no_collision):>6}  ({100 - collision_rate:.1f}%)  ${no_collision_revenue:>12,.0f} revenue")

# ─── 4. Collision detail ─────────────────────────────────────────────────
if collisions:
    collisions_sorted = sorted(collisions, key=lambda x: x['revenue'], reverse=True)

    print(f"\n4. Top 30 collisions by revenue:")
    print(f"   {'QB Customer Name':<45} {'QB Revenue':>12} {'SB Company ID':>38}")
    print(f"   {'-'*45} {'-'*12} {'-'*38}")
    for c in collisions_sorted[:30]:
        sb_id = c['sb_matches'][0]['id'] if c['sb_matches'] else '?'
        print(f"   {c['qb_name'][:45]:<45} ${c['revenue']:>10,.0f}  {sb_id}")

    # Check if collision SB companies are already matched to a DIFFERENT QB customer
    print(f"\n5. Collision SB companies — are they already QB-matched?")
    collision_sb_ids = set()
    for c in collisions:
        for sb_match in c['sb_matches']:
            collision_sb_ids.add(sb_match['id'])

    # Check which of these SB IDs appear in qb_matched
    matched_sb_ids = set(q['matched_company_id'] for q in qb_matched if q.get('matched_company_id'))
    already_matched = collision_sb_ids & matched_sb_ids
    not_matched = collision_sb_ids - matched_sb_ids

    print(f"   {len(collision_sb_ids)} unique SB companies involved in collisions")
    print(f"   {len(already_matched)} already matched to a different QB customer (LINK-ONLY, no create)")
    print(f"   {len(not_matched)} not matched to any QB customer (can link directly)")

    # For collisions where SB is not yet QB-matched, these are easy: just link
    easy_link = []
    needs_review = []
    for c in collisions:
        sb_id = c['sb_matches'][0]['id']
        if sb_id in not_matched:
            easy_link.append(c)
        else:
            needs_review.append(c)

    print(f"\n   Easy link (SB exists, not QB-matched):  {len(easy_link)}")
    print(f"   Needs review (SB already QB-matched):   {len(needs_review)}")

    if needs_review:
        print(f"\n   Top 10 needing review:")
        needs_review_sorted = sorted(needs_review, key=lambda x: x['revenue'], reverse=True)
        for c in needs_review_sorted[:10]:
            sb_id = c['sb_matches'][0]['id']
            print(f"   QB: {c['qb_name'][:40]:<40} ${c['revenue']:>10,.0f}  SB: {sb_id}")
else:
    print("\n   No collisions — all QB customer names are unique in SB!")

# ─── 6. Revenue distribution of no-collision customers ────────────────────
print(f"\n6. No-collision QB customers — revenue distribution:")
no_collision_sorted = sorted(no_collision, key=lambda x: x['revenue'], reverse=True)

brackets = [
    (100000, float('inf'), "$100K+"),
    (10000, 100000, "$10K-$100K"),
    (1000, 10000, "$1K-$10K"),
    (1, 1000, "$1-$1K"),
    (0, 1, "$0"),
]
for lo, hi, label in brackets:
    count = sum(1 for c in no_collision if lo <= c['revenue'] < hi)
    rev = sum(c['revenue'] for c in no_collision if lo <= c['revenue'] < hi)
    print(f"   {label:<15} {count:>6} customers  ${rev:>12,.0f}")

# ─── DECISION ─────────────────────────────────────────────────────────────
print(f"\n{'='*100}")
print("DECISION GATE")
print(f"{'='*100}")

if collision_rate < 5:
    print(f"\n  PASS -- Collision rate {collision_rate:.1f}% is below 5% threshold")
    print(f"  Safe to bulk-create {len(no_collision)} new SB companies")
    if collisions:
        print(f"  {len(easy_link)} collisions can be resolved by linking existing SB -> QB")
        if needs_review:
            print(f"  {len(needs_review)} collisions need manual review (SB already QB-matched)")
    print(f"\n  RECOMMENDED EXECUTION ORDER:")
    print(f"    1a. Link {len(easy_link)} collision SB companies to their QB customer")
    print(f"    1b. Create {len(no_collision)} new SB companies from QB customer names")
    print(f"    1c. Review {len(needs_review)} multi-match collisions manually")
else:
    print(f"\n  FAIL -- Collision rate {collision_rate:.1f}% exceeds 5% threshold")
    print(f"  Need a 'link existing SB to QB' strategy before bulk creation")
    print(f"  {len(collisions)} QB customers need linking, not creation")

print(f"\n{'='*100}")
