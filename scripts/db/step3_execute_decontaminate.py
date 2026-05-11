"""
Step 3 Execute: Resolve contaminated SB companies.

Three sub-steps:
  3a. Auto-resolve: 1 real QB + N junk $0 -> unlink junk QB from this SB
  3b. All-junk: every QB is $0 -> unlink all from this SB
  3c. Multi-real: output for manual review (no auto action)

"Unlink" means: set qb_customers.matched_company_id = NULL for the junk QB.
The junk QB customers should already have their OWN SB company from Step 1
(if name didn't collide) or be in the review queue.

Writes to:
  - qb_customers (UPDATE matched_company_id = NULL for junk)
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

DRY_RUN = "--execute" not in sys.argv
REVENUE_THRESHOLD = 0


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
qb_matched = fetch_all('qb_customers',
    'id, customer_key_id, qb_record_id, customer_name, customer_code, total_invoiced, matched_company_id',
    not_null=['matched_company_id'])
print(f"  {len(qb_matched)} matched QB customers")

sb_to_qb_list = defaultdict(list)
for q in qb_matched:
    sb_to_qb_list[q['matched_company_id']].append(q)

contaminated = {sb_id: qb_list for sb_id, qb_list in sb_to_qb_list.items() if len(qb_list) > 1}
print(f"  {len(contaminated)} contaminated SB companies")

# Classify
auto_resolvable = []
needs_review = []
all_junk = []

for sb_id, qb_list in contaminated.items():
    qb_with_rev = [q for q in qb_list if float(q.get('total_invoiced') or 0) > REVENUE_THRESHOLD]
    qb_no_rev = [q for q in qb_list if float(q.get('total_invoiced') or 0) <= REVENUE_THRESHOLD]

    if len(qb_with_rev) == 0:
        all_junk.append((sb_id, qb_list))
    elif len(qb_with_rev) == 1:
        auto_resolvable.append((sb_id, qb_with_rev[0], qb_no_rev))
    else:
        needs_review.append((sb_id, qb_list))

print(f"  Auto-resolvable: {len(auto_resolvable)}")
print(f"  All-junk:        {len(all_junk)}")
print(f"  Needs review:    {len(needs_review)}")

# ─── 3a. Auto-resolve ────────────────────────────────────────────────────
print(f"\n{'='*100}")
print(f"STEP 3a: Unlink junk QB from {len(auto_resolvable)} auto-resolvable SB companies")
print(f"{'='*100}")

unlinked_count = 0
unlink_errors = []

for sb_id, real_qb, junk_qbs in auto_resolvable:
    for junk in junk_qbs:
        if not DRY_RUN:
            try:
                sb.table('qb_customers').update({
                    'matched_company_id': None,
                }).eq('id', junk['id']).execute()
                unlinked_count += 1
            except Exception as e:
                unlink_errors.append({
                    'qb_name': junk.get('customer_name', '?'),
                    'error': str(e),
                })
        else:
            unlinked_count += 1

        if unlinked_count <= 5 or unlinked_count % 200 == 0:
            print(f"  [{unlinked_count}] Unlink: {junk['customer_name'][:40]:<40} (was on SB with {real_qb['customer_name'][:25]})")

print(f"\n  Unlinked: {unlinked_count}, Errors: {len(unlink_errors)}")

# ─── 3b. All-junk ────────────────────────────────────────────────────────
print(f"\n{'='*100}")
print(f"STEP 3b: Unlink all QB from {len(all_junk)} all-junk SB companies")
print(f"{'='*100}")

junk_unlinked = 0
junk_errors = []

for sb_id, qb_list in all_junk:
    for q in qb_list:
        if not DRY_RUN:
            try:
                sb.table('qb_customers').update({
                    'matched_company_id': None,
                }).eq('id', q['id']).execute()
                junk_unlinked += 1
            except Exception as e:
                junk_errors.append({
                    'qb_name': q.get('customer_name', '?'),
                    'error': str(e),
                })
        else:
            junk_unlinked += 1

        if junk_unlinked <= 5 or junk_unlinked % 200 == 0:
            print(f"  [{junk_unlinked}] Unlink junk: {q['customer_name'][:50]}")

print(f"\n  Unlinked: {junk_unlinked}, Errors: {len(junk_errors)}")

# ─── 3c. Manual review ───────────────────────────────────────────────────
print(f"\n{'='*100}")
print(f"STEP 3c: {len(needs_review)} SB companies need manual review (2+ revenue-bearing QB)")
print(f"{'='*100}")

# Load names for review output
review_sb_ids = [sb_id for sb_id, _ in needs_review]
sb_name_map = {}
for i in range(0, len(review_sb_ids), 500):
    batch = review_sb_ids[i:i+500]
    resp = sb.table('customer_companies').select('id, company_name').in_('id', batch).execute()
    for r in (resp.data or []):
        sb_name_map[r['id']] = r.get('company_name', '?')

review_data = []
for sb_id, qb_list in needs_review:
    review_data.append({
        'sb_id': sb_id,
        'sb_name': sb_name_map.get(sb_id, '?'),
        'qb_customers': [{
            'qb_id': q['id'],
            'qb_name': q.get('customer_name', '?'),
            'qb_revenue': float(q.get('total_invoiced') or 0),
            'qb_record_id': q.get('qb_record_id'),
        } for q in qb_list],
        'total_revenue': sum(float(q.get('total_invoiced') or 0) for q in qb_list),
    })

review_data.sort(key=lambda x: x['total_revenue'], reverse=True)

review_path = os.path.join(os.path.dirname(__file__), 'step3_review_cases.json')
with open(review_path, 'w') as f:
    json.dump(review_data, f, indent=2, default=str)
print(f"  Written to {review_path}")

for item in review_data[:10]:
    qb_names = [f"{q['qb_name']} (${q['qb_revenue']:,.0f})" for q in item['qb_customers']]
    print(f"  SB: {item['sb_name'][:40]:<40} QB: {' | '.join(qb_names)}")

# ─── Summary ──────────────────────────────────────────────────────────────
print(f"\n{'='*100}")
print("STEP 3 SUMMARY")
print(f"{'='*100}")
print(f"  Auto-resolved (junk unlinked): {unlinked_count:>6} QB customers {'(dry run)' if DRY_RUN else 'executed'}")
print(f"  All-junk unlinked:             {junk_unlinked:>6} QB customers {'(dry run)' if DRY_RUN else 'executed'}")
print(f"  Manual review:                 {len(needs_review):>6} SB companies (step3_review_cases.json)")
print(f"  Errors:                        {len(unlink_errors) + len(junk_errors):>6}")
if DRY_RUN:
    print(f"\n  Run with --execute to apply changes")
print(f"{'='*100}")
