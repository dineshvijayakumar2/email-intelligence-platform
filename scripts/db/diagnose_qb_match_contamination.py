"""
Diagnose QB customer matching contamination.
Shows companies with multiple QB customers matched — likely false positives
from fuzzy name matching (Pass 3).
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
from dotenv import load_dotenv
from supabase import create_client

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
load_dotenv(env_path)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

CLIENT_ID = "241d7b99-f099-4557-96e5-212c4af10812"

# 1. Fetch all qb_customers with a match
print("[1/3] Fetching matched QB customers...")
all_matched = []
offset = 0
while True:
    page = sb.table('qb_customers').select(
        'id, customer_name, customer_code, customer_key_id, matched_company_id, total_invoiced'
    ).eq('client_id', CLIENT_ID).not_.is_(
        'matched_company_id', 'null'
    ).range(offset, offset + 999).execute()
    rows = page.data or []
    all_matched.extend(rows)
    if not rows:
        break
    offset += len(rows)

print(f"  Total QB customers with a match: {len(all_matched)}")

# 2. Group by matched_company_id
from collections import defaultdict
by_company: dict[str, list] = defaultdict(list)
for qc in all_matched:
    by_company[qc['matched_company_id']].append(qc)

multi_match = {cid: custs for cid, custs in by_company.items() if len(custs) > 1}
print(f"  Companies with >1 QB customer: {len(multi_match)}")
print(f"  Companies with exactly 1 QB customer: {len(by_company) - len(multi_match)}")

# 3. Fetch company names for multi-match companies
company_ids = list(multi_match.keys())
company_names = {}
for i in range(0, len(company_ids), 500):
    batch = company_ids[i:i+500]
    resp = sb.table('customer_companies').select('id, company_name').in_('id', batch).execute()
    for c in (resp.data or []):
        company_names[c['id']] = c.get('company_name', '?')

# 4. Print results sorted by contamination count
print(f"\n[2/3] Companies with multiple QB customers matched (top 50):")
print(f"{'Company':<35} {'Count':>5}  QB Customer Names")
print("-" * 120)

sorted_multi = sorted(multi_match.items(), key=lambda x: -len(x[1]))
total_excess = 0
for company_id, custs in sorted_multi[:50]:
    name = company_names.get(company_id, '?')[:34]
    qb_names = " | ".join(c.get('customer_name', '?')[:30] for c in custs[:5])
    if len(custs) > 5:
        qb_names += f" ... +{len(custs) - 5} more"
    total_excess += len(custs) - 1
    print(f"{name:<35} {len(custs):>5}  {qb_names}")

print(f"\n  Total excess matches (likely false positives): {sum(len(c) - 1 for c in multi_match.values())}")

# 5. Quick revenue impact — how much revenue is from contaminated matches?
print(f"\n[3/3] Revenue impact of multi-matched companies:")
contaminated_revenue = 0
clean_revenue = 0
for company_id, custs in by_company.items():
    total = sum(float(c.get('total_invoiced') or 0) for c in custs)
    if len(custs) > 1:
        contaminated_revenue += total
    else:
        clean_revenue += total

print(f"  Revenue from clean matches (1 QB customer):     ${clean_revenue:>12,.2f}")
print(f"  Revenue from contaminated matches (>1 QB cust): ${contaminated_revenue:>12,.2f}")
print(f"\nDone!")
