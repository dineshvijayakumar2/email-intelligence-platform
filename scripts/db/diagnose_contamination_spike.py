"""
Diagnose contamination spike: SB companies with >1 QB customer matched.
Contaminated companies jumped from 1,478 to 2,523 after full QB sync + re-match.

Answers:
  1. What types of contamination exist? (same-entity, junk collision, true conflict)
  2. Which match methods are creating the most contamination?
  3. Did re-match re-contaminate companies we already cleaned?
  4. Top 20 contaminated companies by revenue.
  5. Is this NEW contamination or pre-existing contamination revealed?

Read-only -- no writes.
"""
import os, sys, re
from collections import defaultdict
from difflib import SequenceMatcher

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
from dotenv import load_dotenv
from supabase import create_client

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
load_dotenv(env_path)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
CLIENT_ID = "241d7b99-f099-4557-96e5-212c4af10812"

# Revenue threshold: QB customers with $0 or less are considered "junk"
JUNK_THRESHOLD = 0


def fetch_all(table, select, filters=None, not_null=None, is_null=None, extra_filter=None):
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
        if extra_filter:
            q = extra_filter(q)
        resp = q.range(offset, offset + 999).execute()
        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000
    return rows


def normalise(name: str) -> str:
    """Lowercase, strip all non-alphanumeric characters."""
    return re.sub(r'[^a-z0-9]', '', (name or '').lower())


SUFFIXES = re.compile(
    r'\b(pty|ltd|limited|inc|incorporated|corp|corporation|llc|'
    r'group|holdings|australia|aust|aus|nz|services|solutions|'
    r'engineering|enterprises|international|intl|co)\b', re.IGNORECASE
)


def strip_suffixes(name: str) -> str:
    """Strip common business suffixes for comparison."""
    cleaned = SUFFIXES.sub('', name or '')
    return re.sub(r'[^a-z0-9]', '', cleaned.lower()).strip()


def name_similarity(a: str, b: str) -> float:
    """Return 0-1 similarity score between two company names."""
    na = strip_suffixes(a)
    nb = strip_suffixes(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    # Check if one is a prefix/substring of the other
    if na in nb or nb in na:
        return 0.9
    return SequenceMatcher(None, na, nb).ratio()


SAME_ENTITY_THRESHOLD = 0.75


# ═══════════════════════════════════════════════════════════════════════════
print("=" * 110)
print("CONTAMINATION SPIKE DIAGNOSIS")
print("SB companies with >1 QB customer matched via matched_company_id")
print("=" * 110)

# ─── 1. Fetch all matched QB customers ───────────────────────────────────
print("\n[1/7] Fetching matched QB customers...")
qb_matched = fetch_all(
    'qb_customers',
    'id, customer_key_id, qb_record_id, customer_name, customer_code, total_invoiced, matched_company_id',
    not_null=['matched_company_id']
)
print(f"  Total matched QB customers: {len(qb_matched)}")

# Group by matched_company_id
sb_to_qb: dict[str, list] = defaultdict(list)
for qc in qb_matched:
    sb_to_qb[qc['matched_company_id']].append(qc)

contaminated = {sb_id: custs for sb_id, custs in sb_to_qb.items() if len(custs) > 1}
clean = {sb_id: custs for sb_id, custs in sb_to_qb.items() if len(custs) == 1}
print(f"  SB companies with >1 QB customer (contaminated): {len(contaminated)}")
print(f"  SB companies with exactly 1 QB customer (clean):  {len(clean)}")
print(f"  Excess QB-to-SB links (above 1:1):               {sum(len(c) - 1 for c in contaminated.values())}")

# Distribution of contamination depth
depth_dist = defaultdict(int)
for custs in contaminated.values():
    depth_dist[len(custs)] += 1
print(f"\n  Contamination depth distribution:")
for depth in sorted(depth_dist.keys()):
    print(f"    {depth} QB customers -> {depth_dist[depth]} SB companies")

# ─── 2. Fetch SB company names + match methods ──────────────────────────
print("\n[2/7] Fetching SB company names and match metadata...")
contaminated_ids = list(contaminated.keys())
sb_info: dict[str, dict] = {}

for i in range(0, len(contaminated_ids), 500):
    batch = contaminated_ids[i:i+500]
    resp = sb.table('customer_companies').select(
        'id, company_name, qb_match_method, qb_customer_id, qb_matched_at'
    ).in_('id', batch).execute()
    for r in (resp.data or []):
        sb_info[r['id']] = r

print(f"  Fetched info for {len(sb_info)} contaminated SB companies")

# ─── 3. Classify contamination type ─────────────────────────────────────
print("\n[3/7] Classifying contamination...")

# Categories
same_entity = []     # Multiple QB records for essentially the same company
junk_collision = []  # One real customer + junk $0 records
true_conflict = []   # Two+ different real companies with revenue

same_entity_junk = []  # Same entity but some are $0 junk variants

for sb_id, qb_list in contaminated.items():
    sb_name = sb_info.get(sb_id, {}).get('company_name', '?')
    qb_names = [q.get('customer_name', '?') for q in qb_list]
    qb_revenues = [float(q.get('total_invoiced') or 0) for q in qb_list]

    with_revenue = [(q, float(q.get('total_invoiced') or 0)) for q in qb_list
                    if float(q.get('total_invoiced') or 0) > JUNK_THRESHOLD]
    without_revenue = [(q, float(q.get('total_invoiced') or 0)) for q in qb_list
                       if float(q.get('total_invoiced') or 0) <= JUNK_THRESHOLD]

    entry = {
        'sb_id': sb_id,
        'sb_name': sb_name,
        'qb_list': qb_list,
        'qb_names': qb_names,
        'with_revenue': with_revenue,
        'without_revenue': without_revenue,
        'total_revenue': sum(qb_revenues),
        'qb_match_method': sb_info.get(sb_id, {}).get('qb_match_method'),
    }

    if len(with_revenue) <= 1 and len(without_revenue) > 0:
        # 0 or 1 real customer + junk: check if names are similar
        if len(with_revenue) == 0:
            junk_collision.append(entry)
        else:
            junk_collision.append(entry)
    elif len(with_revenue) > 1:
        # Multiple revenue-bearing QB customers: are they the same entity?
        all_similar = True
        for i_idx in range(len(qb_names)):
            for j_idx in range(i_idx + 1, len(qb_names)):
                sim = name_similarity(qb_names[i_idx], qb_names[j_idx])
                if sim < SAME_ENTITY_THRESHOLD:
                    all_similar = False
                    break
            if not all_similar:
                break

        if all_similar:
            same_entity.append(entry)
        else:
            true_conflict.append(entry)
    else:
        # Should not happen (single with_revenue, no without = not contaminated)
        same_entity.append(entry)

print(f"\n  Contamination classification (threshold: similarity >= {SAME_ENTITY_THRESHOLD}):")
print(f"  +{'-'*41}+{'-'*12}+{'-'*18}+")
print(f"  | {'Category':<39} | {'SB Cos':>10} | {'Total Revenue':>16} |")
print(f"  +{'-'*41}+{'-'*12}+{'-'*18}+")
for label, entries in [
    ("Same Entity (name variants, OK)", same_entity),
    ("Junk Collision (real + $0 junk)", junk_collision),
    ("True Conflict (2+ different cos)", true_conflict),
]:
    rev = sum(e['total_revenue'] for e in entries)
    print(f"  | {label:<39} | {len(entries):>10} | ${rev:>14,.0f} |")
print(f"  +{'-'*41}+{'-'*12}+{'-'*18}+")
total_rev = sum(e['total_revenue'] for e in same_entity + junk_collision + true_conflict)
print(f"  | {'TOTAL':<39} | {len(contaminated):>10} | ${total_rev:>14,.0f} |")
print(f"  +{'-'*41}+{'-'*12}+{'-'*18}+")

# ─── 4. Match method analysis on contaminated companies ──────────────────
print("\n[4/7] Match method analysis on contaminated SB companies...")

method_counts = defaultdict(int)
method_revenue = defaultdict(float)
method_by_category = defaultdict(lambda: defaultdict(int))

for category_name, entries in [
    ("same_entity", same_entity),
    ("junk_collision", junk_collision),
    ("true_conflict", true_conflict),
]:
    for e in entries:
        method = e.get('qb_match_method') or 'NULL/unknown'
        method_counts[method] += 1
        method_revenue[method] += e['total_revenue']
        method_by_category[method][category_name] += 1

print(f"\n  Match method on contaminated SB companies (from customer_companies.qb_match_method):")
print(f"  +{'-'*26}+{'-'*9}+{'-'*18}+{'-'*34}+")
print(f"  | {'Method':<24} | {'Count':>7} | {'Revenue':>16} | {'same/junk/conflict':<32} |")
print(f"  +{'-'*26}+{'-'*9}+{'-'*18}+{'-'*34}+")
for method in sorted(method_counts.keys(), key=lambda m: method_counts[m], reverse=True):
    cats = method_by_category[method]
    cat_str = f"s={cats.get('same_entity',0)} j={cats.get('junk_collision',0)} c={cats.get('true_conflict',0)}"
    print(f"  | {method:<24} | {method_counts[method]:>7} | ${method_revenue[method]:>14,.0f} | {cat_str:<32} |")
print(f"  +{'-'*26}+{'-'*9}+{'-'*18}+{'-'*34}+")

# Also look at match methods for ALL SB companies (not just contaminated)
print(f"\n  For comparison, match methods across ALL matched SB companies:")
all_sb_ids = list(sb_to_qb.keys())
all_sb_info: dict[str, dict] = {}
for i in range(0, len(all_sb_ids), 500):
    batch = all_sb_ids[i:i+500]
    resp = sb.table('customer_companies').select(
        'id, qb_match_method'
    ).in_('id', batch).execute()
    for r in (resp.data or []):
        all_sb_info[r['id']] = r

all_method_counts = defaultdict(int)
contaminated_method_counts = defaultdict(int)
for sb_id, info in all_sb_info.items():
    method = info.get('qb_match_method') or 'NULL/unknown'
    all_method_counts[method] += 1
    if sb_id in contaminated:
        contaminated_method_counts[method] += 1

print(f"  +{'-'*26}+{'-'*12}+{'-'*14}+{'-'*14}+")
print(f"  | {'Method':<24} | {'Total SB':>10} | {'Contaminated':>12} | {'Contam Rate':>12} |")
print(f"  +{'-'*26}+{'-'*12}+{'-'*14}+{'-'*14}+")
for method in sorted(all_method_counts.keys(), key=lambda m: all_method_counts[m], reverse=True):
    total_m = all_method_counts[method]
    contam_m = contaminated_method_counts.get(method, 0)
    rate = (contam_m / total_m * 100) if total_m > 0 else 0
    print(f"  | {method:<24} | {total_m:>10} | {contam_m:>12} | {rate:>10.1f}% |")
print(f"  +{'-'*26}+{'-'*12}+{'-'*14}+{'-'*14}+")

# ─── 5. Check if re-match re-contaminated previously cleaned companies ──
print("\n[5/7] Checking for re-contamination of previously cleaned companies...")
print("  Looking for SB companies where qb_match_method = 'email_lookup' that are contaminated...")

email_lookup_contaminated = [
    e for e in same_entity + junk_collision + true_conflict
    if e.get('qb_match_method') == 'email_lookup'
]
non_email_contaminated = [
    e for e in same_entity + junk_collision + true_conflict
    if (e.get('qb_match_method') or '') != 'email_lookup'
]

print(f"  Contaminated via email_lookup:      {len(email_lookup_contaminated)}")
print(f"  Contaminated via other methods:     {len(non_email_contaminated)}")

# Check if qb_matched_at is recent (indicating re-match activity)
recent_count = 0
old_count = 0
no_date_count = 0
for e in same_entity + junk_collision + true_conflict:
    matched_at = sb_info.get(e['sb_id'], {}).get('qb_matched_at')
    if not matched_at:
        no_date_count += 1
    elif '2026-05-11' in str(matched_at) or '2026-05-10' in str(matched_at):
        recent_count += 1
    else:
        old_count += 1

print(f"\n  Match timing on contaminated SB companies:")
print(f"    Matched today/yesterday (re-match):  {recent_count}")
print(f"    Matched earlier:                     {old_count}")
print(f"    No match date:                       {no_date_count}")

# ─── 5b. Deep check: how many QB customers have NULL matched_company_id
# that COULD create contamination if re-matched ─────────────────────────
print("\n  Checking unmatched QB customers that share emails with matched ones...")
# This reveals potential future contamination from email overlap
qb_unmatched = fetch_all(
    'qb_customers',
    'id, customer_key_id, customer_name, total_invoiced',
    is_null=['matched_company_id']
)
print(f"  Unmatched QB customers: {len(qb_unmatched)}")

# ─── 6. Mechanism analysis: HOW does email matching create contamination?
print("\n[6/7] Mechanism analysis: how email_lookup creates contamination...")
print("  Tracing email paths for a sample of contaminated companies...")

# For contaminated companies with email_lookup method, trace the email path
# Fetch qb_unique_emails for a sample
sample_contaminated = sorted(
    same_entity + junk_collision + true_conflict,
    key=lambda e: e['total_revenue'],
    reverse=True
)[:50]

# Get all QB customer_key_ids in the sample
sample_qb_keys = set()
sample_qb_key_to_sb = {}
for e in sample_contaminated:
    for q in e['qb_list']:
        key = q.get('customer_key_id')
        if key:
            sample_qb_keys.add(str(key))
            sample_qb_key_to_sb[str(key)] = e['sb_id']

# Fetch unique emails for these QB customers
print(f"  Fetching QB unique emails for {len(sample_qb_keys)} QB customers...")
sample_qb_emails = []
sample_keys_list = list(sample_qb_keys)
for i in range(0, len(sample_keys_list), 200):
    batch = sample_keys_list[i:i+200]
    resp = sb.table('qb_unique_emails').select(
        'qb_customer_id, email'
    ).eq('client_id', CLIENT_ID).in_('qb_customer_id', batch).execute()
    sample_qb_emails.extend(resp.data or [])

# Build QB customer -> emails map
qb_key_to_emails: dict[str, set] = defaultdict(set)
for ue in sample_qb_emails:
    qb_key = str(ue.get('qb_customer_id', ''))
    email = (ue.get('email') or '').strip().lower()
    if qb_key and email:
        qb_key_to_emails[qb_key].add(email)

# For each contaminated SB company, check if the multiple QB customers share emails
shared_email_count = 0
no_shared_emails_count = 0
no_emails_at_all = 0

print(f"\n  Email overlap analysis for top 50 contaminated companies by revenue:")
shown = 0
for e in sample_contaminated:
    qb_emails_per_cust = {}
    for q in e['qb_list']:
        key = str(q.get('customer_key_id', ''))
        qb_emails_per_cust[q.get('customer_name', '?')] = qb_key_to_emails.get(key, set())

    all_email_sets = list(qb_emails_per_cust.values())
    if not any(all_email_sets):
        no_emails_at_all += 1
        continue

    # Check for email overlap between different QB customers
    all_emails_flat = set()
    has_overlap = False
    for es in all_email_sets:
        overlap = all_emails_flat & es
        if overlap:
            has_overlap = True
        all_emails_flat |= es

    if has_overlap:
        shared_email_count += 1
    else:
        no_shared_emails_count += 1

    if shown < 10:
        shown += 1
        rev_str = f"${e['total_revenue']:>10,.0f}"
        method = e.get('qb_match_method') or 'NULL'
        overlap_str = "SHARED EMAILS" if has_overlap else "NO email overlap"
        print(f"\n    SB: {e['sb_name'][:50]:<50} {rev_str}  method={method}")
        for qb_name, emails in qb_emails_per_cust.items():
            email_str = ', '.join(sorted(emails)[:3])
            if len(emails) > 3:
                email_str += f" +{len(emails)-3} more"
            rev_q = next((float(q.get('total_invoiced') or 0) for q in e['qb_list']
                          if q.get('customer_name') == qb_name), 0)
            print(f"      QB: {qb_name[:40]:<40} ${rev_q:>10,.0f}  emails: {email_str or 'NONE'}")
        print(f"      --> {overlap_str}")

print(f"\n  Email overlap summary (top 50 by revenue):")
print(f"    QB customers SHARE emails with each other:  {shared_email_count}")
print(f"    QB customers have NO email overlap:         {no_shared_emails_count}")
print(f"    QB customers have NO emails at all:         {no_emails_at_all}")

# ─── 6b. Trace the actual email path for top contaminated cases ─────────
print(f"\n  MECHANISM TRACE: How do unrelated QB customers land on the same SB company?")
print(f"  Fetching contact-to-company links for contaminated SB companies...")

# For a few true_conflict cases, trace: which contact email is the bridge?
trace_cases = [e for e in sample_contaminated if len(e['qb_list']) == 2][:10]

# Collect all emails from the QB customers in these cases
trace_qb_keys = set()
for e in trace_cases:
    for q in e['qb_list']:
        key = str(q.get('customer_key_id', ''))
        if key:
            trace_qb_keys.add(key)

# Get all emails for these QB customers (already in qb_key_to_emails from above)
# Now fetch customer_contacts that belong to these SB companies
trace_sb_ids = [e['sb_id'] for e in trace_cases]
trace_contacts = []
for i in range(0, len(trace_sb_ids), 50):
    batch = trace_sb_ids[i:i+50]
    resp = sb.table('customer_contacts').select(
        'email_address, customer_company_id'
    ).eq('client_id', CLIENT_ID).in_('customer_company_id', batch).execute()
    trace_contacts.extend(resp.data or [])

# Build SB company -> set of contact emails
sb_to_contact_emails: dict[str, set] = defaultdict(set)
for c in trace_contacts:
    email = (c.get('email_address') or '').strip().lower()
    sb_id = c.get('customer_company_id')
    if email and sb_id:
        sb_to_contact_emails[sb_id].add(email)

print(f"\n  Email path trace for top contaminated cases:")
for e in trace_cases[:5]:
    sb_emails = sb_to_contact_emails.get(e['sb_id'], set())
    print(f"\n    SB: {e['sb_name'][:50]:<50} ({len(sb_emails)} contacts)")
    for q in e['qb_list']:
        key = str(q.get('customer_key_id', ''))
        qb_emails = qb_key_to_emails.get(key, set())
        bridge_emails = sb_emails & qb_emails
        rev = float(q.get('total_invoiced') or 0)
        print(f"      QB: {q['customer_name'][:40]:<40} ${rev:>10,.0f}")
        print(f"          QB emails: {len(qb_emails)}, SB contacts: {len(sb_emails)}, BRIDGE emails: {len(bridge_emails)}")
        if bridge_emails:
            for be in sorted(bridge_emails)[:5]:
                print(f"          BRIDGE: {be}")
            if len(bridge_emails) > 5:
                print(f"          ... +{len(bridge_emails)-5} more bridge emails")
        else:
            print(f"          NO bridge emails -- this QB customer was likely matched by name, not email")

# ─── 7. Top 20 contaminated companies by revenue ────────────────────────
print(f"\n[7/7] Top 20 contaminated companies by total combined revenue:")
print(f"  {'#':>3} {'SB Company':<45} {'QB Count':>8} {'Revenue':>14} {'Category':<18} {'Method':<16}")
print(f"  {'-'*3} {'-'*45} {'-'*8} {'-'*14} {'-'*18} {'-'*16}")

all_entries = []
for entries, cat_name in [(same_entity, "same_entity"), (junk_collision, "junk_collision"), (true_conflict, "true_conflict")]:
    for e in entries:
        e['category'] = cat_name
        all_entries.append(e)

all_entries.sort(key=lambda e: e['total_revenue'], reverse=True)

for idx, e in enumerate(all_entries[:20], 1):
    method = e.get('qb_match_method') or 'NULL'
    print(f"  {idx:>3} {e['sb_name'][:45]:<45} {len(e['qb_list']):>8} ${e['total_revenue']:>12,.0f} {e['category']:<18} {method:<16}")
    for q in sorted(e['qb_list'], key=lambda x: float(x.get('total_invoiced') or 0), reverse=True)[:5]:
        rev = float(q.get('total_invoiced') or 0)
        code = q.get('customer_code') or ''
        print(f"      +- {q['customer_name'][:42]:<42} {code:<10} ${rev:>12,.0f}")
    if len(e['qb_list']) > 5:
        print(f"      +- ... and {len(e['qb_list']) - 5} more QB customers")

# ─── 8. Infer new vs pre-existing contamination ─────────────────────────
print(f"\n{'='*110}")
print("ANALYSIS: NEW vs PRE-EXISTING CONTAMINATION")
print(f"{'='*110}")

# The key insight: email_lookup matches are auto-written during sync.
# They set qb_customers.matched_company_id but DON'T check if the SB company
# already has another QB customer. This is the contamination vector.

# Count how many contaminated SB companies have ONLY email_lookup QB customers
# vs mixed methods
email_only_contaminated = 0
mixed_contaminated = 0
name_only_contaminated = 0

# To determine match method per QB customer (not per SB company), we need
# to check the qb_match_candidates table or infer from the flow.
# The customer_companies.qb_match_method only stores ONE value.
# Let's check match_candidates for the contaminated QB customers.

print("\n  Fetching match candidates for contaminated QB customers...")
contaminated_qb_record_ids = set()
for e in all_entries:
    for q in e['qb_list']:
        rid = q.get('qb_record_id')
        if rid:
            contaminated_qb_record_ids.add(str(rid))

# Fetch candidates in batches
all_candidates = []
rid_list = list(contaminated_qb_record_ids)
for i in range(0, len(rid_list), 200):
    batch = rid_list[i:i+200]
    try:
        resp = sb.table('qb_match_candidates').select(
            'qb_record_id, match_method, match_score, accepted, reviewed'
        ).eq('client_id', CLIENT_ID).in_('qb_record_id', batch).execute()
        all_candidates.extend(resp.data or [])
    except Exception as ex:
        print(f"    Warning: batch {i}-{i+len(batch)} failed: {ex}")

candidate_methods = defaultdict(set)  # qb_record_id -> set of methods
for c in all_candidates:
    rid = c.get('qb_record_id')
    method = c.get('match_method', '?')
    if rid:
        candidate_methods[str(rid)].add(method)

print(f"  Found {len(all_candidates)} match candidate rows for contaminated QB customers")

# For each contaminated SB, determine if the QB customers went through candidates or were auto-matched
for e in all_entries:
    methods_found = set()
    for q in e['qb_list']:
        rid = str(q.get('qb_record_id', ''))
        if rid in candidate_methods:
            methods_found.update(candidate_methods[rid])
        else:
            # Not in candidates = was auto-matched (email_lookup or direct)
            methods_found.add('auto_matched')

    if methods_found == {'auto_matched'}:
        email_only_contaminated += 1
    elif 'auto_matched' in methods_found:
        mixed_contaminated += 1
    else:
        name_only_contaminated += 1

print(f"\n  Contamination source (per SB company):")
print(f"    All QB customers were auto-matched (no candidates):  {email_only_contaminated}")
print(f"    Mix of auto-matched + candidate-based:               {mixed_contaminated}")
print(f"    All QB customers went through candidates:            {name_only_contaminated}")

# ─── FINAL SUMMARY ──────────────────────────────────────────────────────
print(f"\n{'='*110}")
print("FINAL SUMMARY")
print(f"{'='*110}")
print(f"""
  CONTAMINATION OVERVIEW
  Total contaminated SB companies:        {len(contaminated):>6}
  Total excess QB links (above 1:1):      {sum(len(c) - 1 for c in contaminated.values()):>6}

  CLASSIFICATION
  Same Entity (variants of same co):      {len(same_entity):>6}  ({len(same_entity)/len(contaminated)*100:.1f}%)
  Junk Collision (real + $0 dead):        {len(junk_collision):>6}  ({len(junk_collision)/len(contaminated)*100:.1f}%)
  True Conflict (different real cos):     {len(true_conflict):>6}  ({len(true_conflict)/len(contaminated)*100:.1f}%)

  MATCH METHOD (on SB company)
  email_lookup contaminated:              {len(email_lookup_contaminated):>6}
  other methods contaminated:             {len(non_email_contaminated):>6}

  KEY FINDING
  The re-match (email_lookup) auto-writes qb_customers.matched_company_id
  for EVERY QB customer whose emails match contacts on an SB company.
  It does NOT check whether that SB company already has another QB customer.
  This is the primary contamination vector.

  Junk collision ({len(junk_collision)} cases) = easily fixable by re-running Step 3 decontamination.
  Same entity ({len(same_entity)} cases) = harmless duplicates, could merge QB records.
  True conflict ({len(true_conflict)} cases) = require investigation / manual review.
""")

print("Done!")
