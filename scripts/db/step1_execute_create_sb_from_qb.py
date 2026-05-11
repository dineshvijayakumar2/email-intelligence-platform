"""
Step 1 Execute: Create SB companies from unmatched QB customers.

Three sub-steps:
  1a. Link 315 easy collisions (QB name exists as SB, SB not yet QB-matched)
  1b. Create ~8,519 new SB companies from QB customer names
  1c. Output 91 review cases (QB name exists as SB that's already QB-matched)

Writes to:
  - customer_companies (INSERT new rows, UPDATE matched ones)
  - qb_customers (UPDATE matched_company_id)

Audit: prints every action, outputs review cases to step1_review_cases.json
"""
import os, sys, json
from datetime import datetime, timezone
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
NOW_ISO = datetime.now(timezone.utc).isoformat()

DRY_RUN = "--execute" not in sys.argv


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


if DRY_RUN:
    print("=" * 100)
    print("DRY RUN -- pass --execute to write changes")
    print("=" * 100)
else:
    print("=" * 100)
    print("LIVE EXECUTION -- writing to database")
    print("=" * 100)

# ─── Load data ────────────────────────────────────────────────────────────
print("\nLoading data...")
qb_unmatched = fetch_all('qb_customers',
    'id, customer_key_id, qb_record_id, customer_name, customer_code, total_invoiced, matched_company_id',
    is_null=['matched_company_id'])
print(f"  {len(qb_unmatched)} unmatched QB customers")

qb_matched = fetch_all('qb_customers',
    'id, customer_key_id, qb_record_id, customer_name, matched_company_id',
    not_null=['matched_company_id'])
matched_sb_ids = set(q['matched_company_id'] for q in qb_matched)
print(f"  {len(qb_matched)} matched QB customers")

sb_companies = fetch_all('customer_companies', 'id, company_name')
print(f"  {len(sb_companies)} SB companies")

sb_name_lookup = defaultdict(list)
for c in sb_companies:
    name = (c.get('company_name') or '').strip().lower()
    if name:
        sb_name_lookup[name].append(c)

# ─── Classify each unmatched QB customer ──────────────────────────────────
easy_links = []      # SB exists, not QB-matched -> link directly
new_creates = []     # no SB with this name -> create
needs_review = []    # SB exists but already QB-matched

for qb in qb_unmatched:
    qb_name = (qb.get('customer_name') or '').strip()
    existing = sb_name_lookup.get(qb_name.lower(), [])

    if existing:
        sb_row = existing[0]
        if sb_row['id'] in matched_sb_ids:
            needs_review.append({'qb': qb, 'sb': sb_row})
        else:
            easy_links.append({'qb': qb, 'sb': sb_row})
    else:
        new_creates.append(qb)

print(f"\n  Easy links (SB exists, unmatched):  {len(easy_links)}")
print(f"  New creates (no SB exists):         {len(new_creates)}")
print(f"  Needs review (SB already matched):  {len(needs_review)}")

# ─── 1a. Easy links ──────────────────────────────────────────────────────
print(f"\n{'='*100}")
print(f"STEP 1a: Link {len(easy_links)} QB customers to existing SB companies")
print(f"{'='*100}")

linked_count = 0
link_errors = []

for item in easy_links:
    qb = item['qb']
    sb_row = item['sb']
    qb_name = qb.get('customer_name', '?')
    revenue = float(qb.get('total_invoiced') or 0)

    if not DRY_RUN:
        try:
            sb.table('qb_customers').update({
                'matched_company_id': sb_row['id'],
            }).eq('id', qb['id']).execute()

            sb.table('customer_companies').update({
                'qb_customer_id': qb.get('qb_record_id') or qb.get('customer_key_id'),
                'qb_customer_code': qb.get('customer_code'),
                'qb_match_method': 'qb_anchored_link',
                'qb_matched_at': NOW_ISO,
            }).eq('id', sb_row['id']).execute()

            linked_count += 1
        except Exception as e:
            link_errors.append({'qb_name': qb_name, 'error': str(e)})
            print(f"  ERROR linking {qb_name}: {e}")
    else:
        linked_count += 1

    if linked_count <= 10 or linked_count % 100 == 0:
        print(f"  [{linked_count}] {qb_name:<45} -> SB {sb_row['id'][:12]}...  ${revenue:>10,.0f}")

print(f"\n  Linked: {linked_count}, Errors: {len(link_errors)}")

# ─── 1b. Create new SB companies ─────────────────────────────────────────
print(f"\n{'='*100}")
print(f"STEP 1b: Create {len(new_creates)} new SB companies from QB customers")
print(f"{'='*100}")

created_count = 0
create_errors = []
BATCH_SIZE = 50

for batch_start in range(0, len(new_creates), BATCH_SIZE):
    batch = new_creates[batch_start:batch_start + BATCH_SIZE]

    insert_rows = []
    for qb in batch:
        qb_name = (qb.get('customer_name') or '').strip()
        if not qb_name:
            continue
        insert_rows.append({
            'client_id': CLIENT_ID,
            'company_name': qb_name,
            'email_domains': [],
            'qb_customer_id': qb.get('qb_record_id') or qb.get('customer_key_id'),
            'qb_customer_code': qb.get('customer_code'),
            'qb_match_method': 'qb_anchored_create',
            'qb_matched_at': NOW_ISO,
            'created_at': NOW_ISO,
            'updated_at': NOW_ISO,
        })

    if not insert_rows:
        continue

    if not DRY_RUN:
        try:
            resp = sb.table('customer_companies').insert(insert_rows).execute()
            new_rows = resp.data or []

            new_id_map = {}
            for row in new_rows:
                new_id_map[row['company_name'].strip().lower()] = row['id']

            for qb in batch:
                qb_name = (qb.get('customer_name') or '').strip()
                new_sb_id = new_id_map.get(qb_name.lower())
                if new_sb_id:
                    sb.table('qb_customers').update({
                        'matched_company_id': new_sb_id,
                    }).eq('id', qb['id']).execute()
                    created_count += 1
                else:
                    create_errors.append({
                        'qb_name': qb_name,
                        'error': 'Insert succeeded but ID not found in response',
                    })
        except Exception as e:
            error_str = str(e)
            if '23505' in error_str or 'duplicate key' in error_str:
                for qb in batch:
                    qb_name = (qb.get('customer_name') or '').strip()
                    try:
                        resp = sb.table('customer_companies').insert({
                            'client_id': CLIENT_ID,
                            'company_name': qb_name,
                            'email_domains': [],
                            'qb_customer_id': qb.get('qb_record_id') or qb.get('customer_key_id'),
                            'qb_customer_code': qb.get('customer_code'),
                            'qb_match_method': 'qb_anchored_create',
                            'qb_matched_at': NOW_ISO,
                            'created_at': NOW_ISO,
                            'updated_at': NOW_ISO,
                        }).execute()
                        new_sb_id = resp.data[0]['id'] if resp.data else None
                        if new_sb_id:
                            sb.table('qb_customers').update({
                                'matched_company_id': new_sb_id,
                            }).eq('id', qb['id']).execute()
                            created_count += 1
                    except Exception as e2:
                        create_errors.append({'qb_name': qb_name, 'error': str(e2)})
            else:
                for qb in batch:
                    create_errors.append({
                        'qb_name': (qb.get('customer_name') or '?'),
                        'error': error_str,
                    })
    else:
        created_count += len(insert_rows)

    batch_num = batch_start // BATCH_SIZE + 1
    total_batches = (len(new_creates) + BATCH_SIZE - 1) // BATCH_SIZE
    if batch_num <= 3 or batch_num % 20 == 0 or batch_num == total_batches:
        print(f"  Batch {batch_num}/{total_batches}: {created_count} created so far, {len(create_errors)} errors")

print(f"\n  Created: {created_count}, Errors: {len(create_errors)}")

if create_errors:
    print(f"\n  First 10 errors:")
    for err in create_errors[:10]:
        print(f"    {err['qb_name']}: {err['error'][:80]}")

# ─── 1c. Review cases ────────────────────────────────────────────────────
print(f"\n{'='*100}")
print(f"STEP 1c: {len(needs_review)} QB customers need manual review")
print(f"{'='*100}")

review_data = []
for item in needs_review:
    qb = item['qb']
    sb_row = item['sb']
    review_data.append({
        'qb_id': qb.get('id'),
        'qb_key_id': qb.get('customer_key_id'),
        'qb_name': qb.get('customer_name'),
        'qb_revenue': float(qb.get('total_invoiced') or 0),
        'sb_id': sb_row['id'],
        'sb_name': sb_row.get('company_name'),
        'reason': 'SB company already QB-matched to a different QB customer',
    })

review_data.sort(key=lambda x: x['qb_revenue'], reverse=True)

review_path = os.path.join(os.path.dirname(__file__), 'step1_review_cases.json')
with open(review_path, 'w') as f:
    json.dump(review_data, f, indent=2, default=str)
print(f"  Written to {review_path}")

for item in review_data[:15]:
    print(f"  QB: {item['qb_name'][:40]:<40} ${item['qb_revenue']:>10,.0f}  SB: {item['sb_name'][:30]}")

# ─── Summary ──────────────────────────────────────────────────────────────
print(f"\n{'='*100}")
print("STEP 1 SUMMARY")
print(f"{'='*100}")
print(f"  Easy links:      {linked_count:>6} {'(dry run)' if DRY_RUN else 'executed'}")
print(f"  New creates:     {created_count:>6} {'(dry run)' if DRY_RUN else 'executed'}")
print(f"  Review cases:    {len(needs_review):>6} (written to step1_review_cases.json)")
print(f"  Link errors:     {len(link_errors):>6}")
print(f"  Create errors:   {len(create_errors):>6}")
total = linked_count + created_count
print(f"  Total resolved:  {total:>6} of {len(qb_unmatched)} unmatched QB customers")
if DRY_RUN:
    print(f"\n  Run with --execute to apply changes")
print(f"{'='*100}")
