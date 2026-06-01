"""
Diagnose: Why did QB-linked emails drop from 84,269 to 70,076 (-14,193)?

The dashboard RPC (migration 107) counts emails as "with_qb_company" using:
    COUNT(CASE WHEN co.qb_customer_id IS NOT NULL THEN 1 END)
where co = customer_companies joined via emails.customer_company_id.

This script fetches the relevant data via Supabase REST API and does
in-memory analysis to find the root cause.
"""
import os
import sys
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


def fetch_all(table, select, filters=None, not_null=None, is_null=None, extra_filters=None):
    """Paginated fetch from Supabase REST API."""
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
        if extra_filters:
            for fn in extra_filters:
                q = fn(q)
        resp = q.range(offset, offset + 999).execute()
        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000
    return rows


def fetch_count(table, filters=None, not_null=None, is_null=None, extra_filters=None):
    """Count rows using HEAD with exact count."""
    q = sb.table(table).select('id', count='exact').eq('client_id', CLIENT_ID)
    if filters:
        for k, v in filters.items():
            q = q.eq(k, v)
    if not_null:
        for col in not_null:
            q = q.not_.is_(col, 'null')
    if is_null:
        for col in is_null:
            q = q.is_(col, 'null')
    if extra_filters:
        for fn in extra_filters:
            q = fn(q)
    resp = q.limit(0).execute()
    return resp.count if resp.count is not None else len(fetch_all(table, 'id', filters, not_null, is_null, extra_filters))


print("=" * 100)
print("DIAGNOSE: QB-Linked Email Drop (84,269 -> 70,076 = -14,193)")
print("=" * 100)

# ──────────────────────────────────────────────────────────────────────────────
# SECTION 1: Reproduce the dashboard RPC counts
# ──────────────────────────────────────────────────────────────────────────────
print("\n[1] REPRODUCING DASHBOARD RPC COUNTS...")

rpc_resp = sb.rpc('qb_cleanup_dashboard_stats', {'p_client_id': CLIENT_ID}).execute()
stats = rpc_resp.data
email_stats = stats.get('emails', {})
company_stats = stats.get('companies', {})
contact_stats = stats.get('contacts', {})

print(f"  Email stats:")
print(f"    Total emails:          {email_stats.get('total', '?'):>10,}")
print(f"    With QB company:       {email_stats.get('with_qb_company', '?'):>10,}")
print(f"    With non-QB company:   {email_stats.get('with_non_qb_company', '?'):>10,}")
print(f"    No company:            {email_stats.get('no_company', '?'):>10,}")

print(f"\n  Company stats:")
print(f"    Total SB companies:    {company_stats.get('total_sb_companies', '?'):>10,}")
print(f"    QB-anchored SB:        {company_stats.get('qb_anchored_sb', '?'):>10,}")
print(f"    Contaminated SB:       {company_stats.get('contaminated_sb', '?'):>10,}")
print(f"    Total QB customers:    {company_stats.get('total_qb_customers', '?'):>10,}")
print(f"    Matched QB customers:  {company_stats.get('matched_qb_customers', '?'):>10,}")

# ──────────────────────────────────────────────────────────────────────────────
# SECTION 2: Load core data for in-memory analysis
# ──────────────────────────────────────────────────────────────────────────────
print(f"\n{'='*100}")
print("[2] LOADING CORE DATA...")
print("=" * 100)

# Load SB companies
print("  Loading customer_companies...")
all_companies = fetch_all('customer_companies', 'id, company_name, qb_customer_id, qb_customer_code, qb_match_method')
company_map = {c['id']: c for c in all_companies}
print(f"    {len(all_companies):,} SB companies loaded")

# Load QB customers (only matched ones and all for contamination check)
print("  Loading qb_customers...")
all_qb = fetch_all('qb_customers', 'id, customer_key_id, customer_name, matched_company_id, total_invoiced')
print(f"    {len(all_qb):,} QB customers loaded")

# Build QB -> SB map
qb_matched = [q for q in all_qb if q.get('matched_company_id')]
sb_to_qb = defaultdict(list)
for q in qb_matched:
    sb_to_qb[q['matched_company_id']].append(q)
qb_anchored_via_qb_customers = set(sb_to_qb.keys())
print(f"    {len(qb_matched):,} matched QB customers -> {len(qb_anchored_via_qb_customers):,} unique SB companies")

# Load emails (just company linkage)
print("  Loading emails (customer_company_id)...")
all_emails = fetch_all('emails', 'id, customer_company_id')
print(f"    {len(all_emails):,} emails loaded")

# ──────────────────────────────────────────────────────────────────────────────
# SECTION 3: QB-anchored analysis (the dashboard's definition)
# ──────────────────────────────────────────────────────────────────────────────
print(f"\n{'='*100}")
print("[3] QB-ANCHORED: customer_companies.qb_customer_id")
print("=" * 100)

sb_with_qb_cid = [c for c in all_companies if c.get('qb_customer_id')]
sb_without_qb_cid = [c for c in all_companies if not c.get('qb_customer_id')]
qb_anchored_via_column = set(c['id'] for c in sb_with_qb_cid)

print(f"  SB companies total:               {len(all_companies):>8,}")
print(f"  SB with qb_customer_id set:       {len(sb_with_qb_cid):>8,}")
print(f"  SB without qb_customer_id:        {len(sb_without_qb_cid):>8,}")

# ──────────────────────────────────────────────────────────────────────────────
# SECTION 4: Cross-check the two QB-anchored definitions
# ──────────────────────────────────────────────────────────────────────────────
print(f"\n{'='*100}")
print("[4] CROSS-CHECK: qb_customer_id column vs qb_customers.matched_company_id")
print("=" * 100)

# SBs in column set but NOT in qb_customers set
orphaned_anchors = qb_anchored_via_column - qb_anchored_via_qb_customers
# SBs in qb_customers set but NOT in column set
reverse_orphans = qb_anchored_via_qb_customers - qb_anchored_via_column
# In both
consistent = qb_anchored_via_column & qb_anchored_via_qb_customers

print(f"  SB with BOTH qb_customer_id AND qb_customers match:            {len(consistent):>8,}")
print(f"  SB with qb_customer_id but NO qb_customers match (stale):      {len(orphaned_anchors):>8,}")
print(f"  SB with qb_customers match but qb_customer_id IS NULL (gap):   {len(reverse_orphans):>8,}")

# ──────────────────────────────────────────────────────────────────────────────
# SECTION 5: Email breakdown by company QB status
# ──────────────────────────────────────────────────────────────────────────────
print(f"\n{'='*100}")
print("[5] EMAIL BREAKDOWN BY COMPANY QB STATUS")
print("=" * 100)

emails_no_company = 0
emails_qb_linked = 0       # dashboard definition: qb_customer_id set
emails_non_qb = 0
emails_dangling = 0         # company_id set but company doesn't exist
emails_alt_qb_linked = 0   # alternative: qb_customers.matched_company_id
emails_stale_anchor = 0    # qb_customer_id set but no qb_customers match
emails_on_gap_sbs = 0      # qb_customers match exists but no qb_customer_id

for e in all_emails:
    cid = e.get('customer_company_id')
    if not cid:
        emails_no_company += 1
        continue

    company = company_map.get(cid)
    if not company:
        emails_dangling += 1
        continue

    has_qb_cid = bool(company.get('qb_customer_id'))
    has_qb_match = cid in qb_anchored_via_qb_customers

    if has_qb_cid:
        emails_qb_linked += 1
        if not has_qb_match:
            emails_stale_anchor += 1
    else:
        emails_non_qb += 1
        if has_qb_match:
            emails_on_gap_sbs += 1

    if has_qb_match:
        emails_alt_qb_linked += 1

total = len(all_emails)
print(f"  Total emails:                       {total:>10,}")
print(f"  No customer_company_id:             {emails_no_company:>10,}")
print(f"  Dangling (company deleted):         {emails_dangling:>10,}")
print(f"  On SB with qb_customer_id (dash):   {emails_qb_linked:>10,}")
print(f"  On SB without qb_customer_id:       {emails_non_qb:>10,}")
print(f"  Sanity: {emails_qb_linked} + {emails_non_qb} + {emails_no_company} + {emails_dangling} = {emails_qb_linked + emails_non_qb + emails_no_company + emails_dangling} (should = {total})")

print(f"\n  Alternative QB-linked (via qb_customers.matched_company_id): {emails_alt_qb_linked:>10,}")
print(f"  Dashboard QB-linked (via qb_customer_id column):             {emails_qb_linked:>10,}")
print(f"  Delta:                                                       {emails_qb_linked - emails_alt_qb_linked:>10,}")

print(f"\n  STALE: emails on SB with qb_customer_id but NO qb_customers match: {emails_stale_anchor:>10,}")
print(f"  GAP:   emails on SB with qb_customers match but NO qb_customer_id:  {emails_on_gap_sbs:>10,}")

# ──────────────────────────────────────────────────────────────────────────────
# SECTION 6: Characterize the gap SB companies (have qb_customers match but no qb_customer_id)
# ──────────────────────────────────────────────────────────────────────────────
print(f"\n{'='*100}")
print("[6] GAP SB COMPANIES: qb_customers match but qb_customer_id IS NULL")
print("=" * 100)

gap_companies = []
for sb_id in reverse_orphans:
    company = company_map.get(sb_id)
    if not company:
        continue
    email_count = sum(1 for e in all_emails if e.get('customer_company_id') == sb_id)
    qb_list = sb_to_qb.get(sb_id, [])
    gap_companies.append({
        'id': sb_id,
        'name': company.get('company_name', '?'),
        'qb_match_method': company.get('qb_match_method'),
        'email_count': email_count,
        'qb_count': len(qb_list),
        'qb_names': [q.get('customer_name', '?') for q in qb_list],
        'qb_revenue': sum(float(q.get('total_invoiced') or 0) for q in qb_list),
    })

gap_companies.sort(key=lambda x: x['email_count'], reverse=True)

total_gap_emails = sum(g['email_count'] for g in gap_companies)
total_gap_revenue = sum(g['qb_revenue'] for g in gap_companies)
print(f"  Total gap SB companies: {len(gap_companies):>8,}")
print(f"  Total emails on gap SBs: {total_gap_emails:>10,}")
print(f"  Total QB revenue on gap SBs: ${total_gap_revenue:>12,.0f}")

# Method breakdown
gap_by_method = defaultdict(lambda: {'count': 0, 'emails': 0})
for g in gap_companies:
    method = g['qb_match_method'] or '(null)'
    gap_by_method[method]['count'] += 1
    gap_by_method[method]['emails'] += g['email_count']

print(f"\n  Gap by qb_match_method on SB company:")
print(f"    {'Method':<30} {'Companies':>10} {'Emails':>10}")
for method, data in sorted(gap_by_method.items(), key=lambda x: -x[1]['emails']):
    print(f"    {method:<30} {data['count']:>10,} {data['emails']:>10,}")

print(f"\n  Top 20 gap SBs by email count:")
for g in gap_companies[:20]:
    qb_names_str = ', '.join(g['qb_names'][:3])
    if len(g['qb_names']) > 3:
        qb_names_str += f' (+{len(g["qb_names"])-3} more)'
    print(f"    {g['email_count']:>6,} emails | {g['name'][:40]:<40} | method={g['qb_match_method'] or 'null'} | QB: {qb_names_str[:50]}")

# ──────────────────────────────────────────────────────────────────────────────
# SECTION 7: Characterize stale-anchored SB companies
# ──────────────────────────────────────────────────────────────────────────────
print(f"\n{'='*100}")
print("[7] STALE-ANCHORED SB COMPANIES: qb_customer_id set but NO qb_customers match")
print("=" * 100)

stale_companies = []
for sb_id in orphaned_anchors:
    company = company_map.get(sb_id)
    if not company:
        continue
    email_count = sum(1 for e in all_emails if e.get('customer_company_id') == sb_id)
    stale_companies.append({
        'id': sb_id,
        'name': company.get('company_name', '?'),
        'qb_customer_id': company.get('qb_customer_id'),
        'qb_match_method': company.get('qb_match_method'),
        'email_count': email_count,
    })

stale_companies.sort(key=lambda x: x['email_count'], reverse=True)
total_stale_emails = sum(s['email_count'] for s in stale_companies)
print(f"  Total stale-anchored SB companies: {len(stale_companies):>8,}")
print(f"  Total emails on stale SBs: {total_stale_emails:>10,}")

if stale_companies:
    print(f"\n  Top 10 stale-anchored SBs:")
    for s in stale_companies[:10]:
        print(f"    {s['email_count']:>6,} emails | {s['name'][:40]:<40} | qb_cid={s['qb_customer_id']} | method={s['qb_match_method'] or 'null'}")

# ──────────────────────────────────────────────────────────────────────────────
# SECTION 8: Contamination status
# ──────────────────────────────────────────────────────────────────────────────
print(f"\n{'='*100}")
print("[8] CONTAMINATION STATUS")
print("=" * 100)

contaminated = {sb_id: qb_list for sb_id, qb_list in sb_to_qb.items() if len(qb_list) > 1}
print(f"  SB companies still contaminated (>1 QB match): {len(contaminated):>8,}")

# How many emails on contaminated SBs
contam_emails = sum(
    sum(1 for e in all_emails if e.get('customer_company_id') == sb_id)
    for sb_id in contaminated
)
print(f"  Emails on contaminated SBs: {contam_emails:>10,}")

# ──────────────────────────────────────────────────────────────────────────────
# SECTION 9: qb_match_method distribution
# ──────────────────────────────────────────────────────────────────────────────
print(f"\n{'='*100}")
print("[9] SB COMPANY qb_match_method DISTRIBUTION")
print("=" * 100)

method_dist = defaultdict(lambda: {'total': 0, 'with_qb_cid': 0, 'without_qb_cid': 0})
for c in all_companies:
    method = c.get('qb_match_method') or '(null)'
    method_dist[method]['total'] += 1
    if c.get('qb_customer_id'):
        method_dist[method]['with_qb_cid'] += 1
    else:
        method_dist[method]['without_qb_cid'] += 1

print(f"  {'Method':<30} {'Total':>8} {'Has qb_cid':>10} {'No qb_cid':>10}")
for method, data in sorted(method_dist.items(), key=lambda x: -x[1]['total']):
    print(f"  {method:<30} {data['total']:>8,} {data['with_qb_cid']:>10,} {data['without_qb_cid']:>10,}")

# ──────────────────────────────────────────────────────────────────────────────
# SECTION 10: Non-QB companies with most emails (top contributors to 86K non-QB)
# ──────────────────────────────────────────────────────────────────────────────
print(f"\n{'='*100}")
print("[10] TOP NON-QB COMPANIES BY EMAIL COUNT")
print("=" * 100)

non_qb_email_counts = defaultdict(int)
for e in all_emails:
    cid = e.get('customer_company_id')
    if cid and cid in company_map and not company_map[cid].get('qb_customer_id'):
        non_qb_email_counts[cid] += 1

top_non_qb = sorted(non_qb_email_counts.items(), key=lambda x: -x[1])[:25]
print(f"  {'Emails':>8} {'Company':<50} {'Method':<20} {'Has QB match':>12}")
for cid, count in top_non_qb:
    c = company_map[cid]
    has_match = 'YES' if cid in qb_anchored_via_qb_customers else 'no'
    print(f"  {count:>8,} {(c.get('company_name') or '?')[:50]:<50} {(c.get('qb_match_method') or 'null'):<20} {has_match:>12}")

# ──────────────────────────────────────────────────────────────────────────────
# SECTION 11: Potential fix analysis
# ──────────────────────────────────────────────────────────────────────────────
print(f"\n{'='*100}")
print("[11] POTENTIAL FIX: Sync qb_customer_id from qb_customers.matched_company_id")
print("=" * 100)

print(f"  SB companies fixable (have qb_customers match but no qb_customer_id): {len(reverse_orphans):>8,}")
print(f"  Emails that would become QB-linked after fix: {emails_on_gap_sbs:>10,}")
print(f"  Current QB-linked:  {emails_qb_linked:>10,}")
print(f"  After fix:          {emails_qb_linked + emails_on_gap_sbs:>10,}")
print(f"  Original count:     {84269:>10,}")
gap_remaining = 84269 - (emails_qb_linked + emails_on_gap_sbs)
print(f"  Remaining gap:      {gap_remaining:>10,} {'(FULLY ACCOUNTED!)' if gap_remaining <= 0 else '(still unaccounted)'}")

# ──────────────────────────────────────────────────────────────────────────────
# SECTION 12: The actual root cause chain
# ──────────────────────────────────────────────────────────────────────────────
print(f"\n{'='*100}")
print("[12] ROOT CAUSE ANALYSIS")
print("=" * 100)

# Check if Step 3 (decontaminate) left SBs with qb_customers match but cleared qb_customer_id
# by looking at SBs that have a QB match via qb_customers BUT lost their qb_customer_id column
# These would be SBs where the auto-matching in QB sync set matched_company_id on qb_customers
# but the propagation to customer_companies.qb_customer_id didn't happen

# Count SBs in each state
both_set = len(consistent)
column_only = len(orphaned_anchors)
match_only = len(reverse_orphans)
neither = len(all_companies) - both_set - column_only - match_only

print(f"""
  State matrix (SB companies):
  +-----------------------------+------------------+------------------+
  |                             | qb_customer_id   | qb_customer_id   |
  |                             | IS NOT NULL      | IS NULL          |
  +-----------------------------+------------------+------------------+
  | qb_customers match EXISTS   | {both_set:>10,}      | {match_only:>10,}      |
  | qb_customers match NONE     | {column_only:>10,}      | {neither:>10,}      |
  +-----------------------------+------------------+------------------+

  The dashboard uses qb_customer_id column. The {match_only:,} SBs in the
  upper-right cell have legitimate QB matches but are counted as non-QB.
  Those {match_only:,} SBs account for {emails_on_gap_sbs:,} "missing" QB-linked emails.

  Meanwhile, {column_only:,} SBs have qb_customer_id set but NO actual
  qb_customers match. Those stale anchors inflate the QB-linked count
  by {emails_stale_anchor:,} emails.

  NET: The dashboard is OVER-counting by {emails_stale_anchor - emails_on_gap_sbs:,}
  (stale anchors {emails_stale_anchor:,} - gap emails {emails_on_gap_sbs:,})
""")

# ──────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ──────────────────────────────────────────────────────────────────────────────
print(f"{'='*100}")
print("DIAGNOSIS SUMMARY")
print("=" * 100)
print(f"""
  ORIGINAL QB-linked emails:  84,269
  CURRENT QB-linked emails:   {emails_qb_linked:>10,}  (drop of {84269 - emails_qb_linked:,})
  EXPECTED after fix:         {emails_qb_linked + emails_on_gap_sbs:>10,}

  Breakdown of the {84269 - emails_qb_linked:,} drop:
    Emails on gap SBs (qb_customers match, no qb_customer_id): {emails_on_gap_sbs:>10,}
    Dangling refs (company deleted, email not relinked):        {emails_dangling:>10,}
    Remaining unexplained:                                     {84269 - emails_qb_linked - emails_on_gap_sbs - emails_dangling:>10,}

  ROOT CAUSE:
    The QB sync sets qb_customers.matched_company_id when a match is found,
    but the propagation step that copies this into customer_companies.qb_customer_id
    (which the dashboard RPC checks) is out of sync for {len(reverse_orphans):,} companies.

    Step 3 (decontaminate) only updated qb_customers.matched_company_id.
    It did NOT update customer_companies.qb_customer_id in lockstep.

  FIX: Propagate qb_customer_id from qb_customers to customer_companies
  for the {len(reverse_orphans):,} gap companies. This would recover {emails_on_gap_sbs:,} emails.
""")
