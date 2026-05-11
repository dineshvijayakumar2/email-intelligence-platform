"""
Step 3 Pre-flight: Classify contaminated SB companies.

2,207 SB companies have >1 QB customer matched. Classify each:
  - auto_resolvable_1real: 1 QB with revenue > 0, rest are $0 junk -> auto-fix
  - needs_review_multi_real: 2+ QB with revenue > 0 -> manual review
  - all_junk: all QB customers have $0 revenue -> separate decision

For auto-resolvable cases, the fix is:
  - Keep the real QB customer linked to this SB
  - Un-link the junk QB customers (set matched_company_id = NULL)
  - The junk QB customers already got new SB companies from Step 1

Read-only -- no writes.
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
print("STEP 3 PRE-FLIGHT: Classify contaminated SB companies")
print("=" * 100)

# ─── 1. Find contaminated SB companies ───────────────────────────────────
print("\n1. Loading matched QB customers...")
qb_matched = fetch_all('qb_customers',
    'id, customer_key_id, qb_record_id, customer_name, customer_code, total_invoiced, matched_company_id',
    not_null=['matched_company_id'])
print(f"   {len(qb_matched)} matched QB customers")

sb_to_qb_list = defaultdict(list)
for q in qb_matched:
    sb_to_qb_list[q['matched_company_id']].append(q)

contaminated = {sb_id: qb_list for sb_id, qb_list in sb_to_qb_list.items() if len(qb_list) > 1}
print(f"   {len(contaminated)} contaminated SB companies (>1 QB customer)")

# ─── 2. Load SB company names ────────────────────────────────────────────
print("\n2. Loading SB company names...")
contaminated_ids = list(contaminated.keys())
sb_name_map = {}
for i in range(0, len(contaminated_ids), 500):
    batch = contaminated_ids[i:i+500]
    resp = sb.table('customer_companies').select('id, company_name').in_('id', batch).execute()
    for r in (resp.data or []):
        sb_name_map[r['id']] = r.get('company_name', '?')
print(f"   {len(sb_name_map)} names loaded")

# ─── 3. Classify ─────────────────────────────────────────────────────────
print("\n3. Classifying contamination patterns...")

auto_resolvable = []    # 1 real QB + N junk $0
needs_review = []       # 2+ real QB
all_junk = []           # all QB are $0
REVENUE_THRESHOLD = 0   # $0 = junk

for sb_id, qb_list in contaminated.items():
    qb_with_revenue = [q for q in qb_list if float(q.get('total_invoiced') or 0) > REVENUE_THRESHOLD]
    qb_without_revenue = [q for q in qb_list if float(q.get('total_invoiced') or 0) <= REVENUE_THRESHOLD]
    total_revenue = sum(float(q.get('total_invoiced') or 0) for q in qb_list)

    entry = {
        'sb_id': sb_id,
        'sb_name': sb_name_map.get(sb_id, '?'),
        'qb_count': len(qb_list),
        'qb_with_revenue': qb_with_revenue,
        'qb_without_revenue': qb_without_revenue,
        'total_revenue': total_revenue,
    }

    if len(qb_with_revenue) == 0:
        all_junk.append(entry)
    elif len(qb_with_revenue) == 1:
        auto_resolvable.append(entry)
    else:
        needs_review.append(entry)

print(f"\n   Auto-resolvable (1 real + N junk): {len(auto_resolvable)}")
print(f"   Needs review (2+ real):            {len(needs_review)}")
print(f"   All junk ($0):                     {len(all_junk)}")
print(f"   Total:                             {len(contaminated)}")

# ─── 4. Auto-resolvable detail ───────────────────────────────────────────
print(f"\n{'='*100}")
print(f"AUTO-RESOLVABLE: {len(auto_resolvable)} SB companies")
print(f"{'='*100}")

auto_resolvable.sort(key=lambda x: x['total_revenue'], reverse=True)
junk_to_unlink = 0
for entry in auto_resolvable:
    junk_to_unlink += len(entry['qb_without_revenue'])

print(f"  Total junk QB customers to unlink: {junk_to_unlink}")
print(f"\n  Top 20:")
for entry in auto_resolvable[:20]:
    real = entry['qb_with_revenue'][0]
    print(f"  SB: {entry['sb_name'][:40]:<40}  KEEP: {real['customer_name'][:30]:<30} ${float(real.get('total_invoiced') or 0):>10,.0f}")
    for junk in entry['qb_without_revenue'][:3]:
        print(f"    {'':40}  UNLINK: {junk['customer_name'][:30]:<30} ${float(junk.get('total_invoiced') or 0):>10,.0f}")

# ─── 5. Needs review detail ──────────────────────────────────────────────
if needs_review:
    print(f"\n{'='*100}")
    print(f"NEEDS REVIEW: {len(needs_review)} SB companies with 2+ revenue-bearing QB customers")
    print(f"{'='*100}")

    needs_review.sort(key=lambda x: x['total_revenue'], reverse=True)
    for entry in needs_review[:20]:
        print(f"\n  SB: {entry['sb_name'][:50]:<50} ({entry['qb_count']} QB custs, ${entry['total_revenue']:>10,.0f} rev)")
        for q in sorted(entry['qb_with_revenue'], key=lambda x: float(x.get('total_invoiced') or 0), reverse=True):
            print(f"    QB: {q['customer_name'][:45]:<45} ${float(q.get('total_invoiced') or 0):>10,.0f}")
        for q in entry['qb_without_revenue'][:2]:
            print(f"    QB: {q['customer_name'][:45]:<45} ${float(q.get('total_invoiced') or 0):>10,.0f}  (junk)")

# ─── 6. All junk detail ──────────────────────────────────────────────────
if all_junk:
    print(f"\n{'='*100}")
    print(f"ALL JUNK: {len(all_junk)} SB companies where every QB customer has $0 revenue")
    print(f"{'='*100}")
    print(f"  These can have all QB links removed (back to unmatched).")
    total_junk_qb = sum(entry['qb_count'] for entry in all_junk)
    print(f"  Total junk QB customers: {total_junk_qb}")
    print(f"\n  Sample (first 10):")
    for entry in all_junk[:10]:
        names = [q['customer_name'] for q in entry['qb_without_revenue']]
        print(f"  SB: {entry['sb_name'][:40]:<40} QB: {', '.join(n[:25] for n in names[:3])}")

# ─── Decision ─────────────────────────────────────────────────────────────
print(f"\n{'='*100}")
print("DECISION GATE")
print(f"{'='*100}")
print(f"  Auto-resolvable: {len(auto_resolvable):>5} SB companies ({junk_to_unlink} junk QB to unlink)")
print(f"  Needs review:    {len(needs_review):>5} SB companies (manual decision needed)")
print(f"  All junk:        {len(all_junk):>5} SB companies (can unlink all)")
print(f"\n  RECOMMENDED:")
print(f"    3a. Auto-resolve {len(auto_resolvable)} (unlink junk, keep real QB)")
print(f"    3b. Unlink all-junk {len(all_junk)} (remove matched_company_id)")
print(f"    3c. Stage {len(needs_review)} for manual review")
print(f"{'='*100}")
