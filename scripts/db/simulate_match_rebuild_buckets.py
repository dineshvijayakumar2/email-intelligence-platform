"""
Categorize unmatched high-revenue companies into honest buckets.

Bucket 1: Generic name, no email link — needs manual confirmation
Bucket 2: Name mismatch but email link exists — algorithmically tractable
Bucket 3: True ambiguity — multiple QB customers, needs human disambiguation

Runs against the simulated post-rebuild state (all current matches cleared,
only email+name-confirmed auto-matches applied).
"""
import os, sys, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
from dotenv import load_dotenv
from supabase import create_client
from collections import defaultdict

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
load_dotenv(env_path)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
CLIENT_ID = "241d7b99-f099-4557-96e5-212c4af10812"

GENERIC_DOMAINS = frozenset({
    'gmail.com', 'hotmail.com', 'yahoo.com', 'outlook.com',
    'icloud.com', 'bigpond.com', 'me.com', 'hotmail.com.au',
    'yahoo.com.au', 'live.com', 'live.com.au', 'msn.com',
    'aol.com', 'mail.com', 'protonmail.com', 'zoho.com',
})

def _normalise(name):
    return re.sub(r'[^a-z0-9]', '', (name or '').lower())

def _extract_domain_roots(email_domains):
    if isinstance(email_domains, list):
        domains = email_domains
    else:
        domains = re.findall(r'[\w.-]+\.\w+', str(email_domains or ''))
    roots = []
    for d in domains:
        d_lower = d.lower()
        if d_lower in GENERIC_DOMAINS:
            continue
        parts = d_lower.split('.')
        root = parts[0] if parts else ''
        if len(root) >= 5:
            roots.append(root)
    return roots

def fetch_all(table, select, filters=None):
    rows = []
    offset = 0
    while True:
        q = sb.table(table).select(select).eq('client_id', CLIENT_ID)
        if filters:
            for f in filters:
                q = f(q)
        page = q.range(offset, offset + 999).execute()
        batch = page.data or []
        rows.extend(batch)
        if not batch:
            break
        offset += len(batch)
    return rows

def names_match(sb_name, qb_name):
    sn = _normalise(sb_name)
    qn = _normalise(qb_name)
    if not sn or not qn:
        return False
    return sn in qn or qn in sn

# ═══════════════════════════════════════════════════════════════════════
print("=" * 80)
print("  UNMATCHED REVENUE BUCKET ANALYSIS")
print("=" * 80)

# ── Load data ─────────────────────────────────────────────────────────
print("\n[1/4] Loading data...")

qb_unique_emails = fetch_all('qb_unique_emails', 'email, qb_customer_id', [
    lambda q: q.eq('hide', False),
    lambda q: q.eq('email_invalid', False),
    lambda q: q.not_.is_('qb_customer_id', 'null'),
])
customer_contacts = fetch_all('customer_contacts', 'id, email_address, customer_company_id', [
    lambda q: q.not_.is_('customer_company_id', 'null'),
])
qb_customers = fetch_all('qb_customers',
    'id, qb_record_id, customer_key_id, customer_name, customer_code, total_invoiced, matched_company_id')
sb_companies = fetch_all('customer_companies', 'id, company_name, email_domains')
qb_contacts = fetch_all('qb_contacts', 'id, email, matched_contact_id, qb_customer_id', [
    lambda q: q.not_.is_('matched_contact_id', 'null'),
])

# ── Build lookups ─────────────────────────────────────────────────────
print("[2/4] Building lookups...")

qb_by_record_id = {}
qb_by_key_id = {}
for qc in qb_customers:
    rid = qc.get('qb_record_id')
    kid = qc.get('customer_key_id')
    if rid: qb_by_record_id[str(rid)] = qc
    if kid: qb_by_key_id[str(kid)] = qc

sb_by_id = {c['id']: c for c in sb_companies}

contact_id_to_company = {}
for cc in customer_contacts:
    if cc.get('id') and cc.get('customer_company_id'):
        contact_id_to_company[cc['id']] = cc['customer_company_id']

# Email join: SB company -> {qb_customer_id: [emails]}
email_to_qb = {}
for ue in qb_unique_emails:
    email = (ue.get('email') or '').strip().lower()
    qb_cid = ue.get('qb_customer_id')
    if email and qb_cid:
        email_to_qb[email] = str(qb_cid).strip()

company_to_qb_via_email: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
for cc in customer_contacts:
    email = (cc.get('email_address') or '').strip().lower()
    cid = cc.get('customer_company_id')
    if not email or not cid:
        continue
    qb_cust_id = email_to_qb.get(email)
    if qb_cust_id:
        company_to_qb_via_email[cid][qb_cust_id].append(email)

qb_to_company_via_email: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
for cid, qb_map in company_to_qb_via_email.items():
    for qb_cid, emails in qb_map.items():
        qb_to_company_via_email[qb_cid][cid].extend(emails)

# Contact chain: qb_customer_key_id -> {company_id: count}
chain_qb_to_company: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
for qbc in qb_contacts:
    contact_id = qbc.get('matched_contact_id')
    qb_customer_id = qbc.get('qb_customer_id')
    if not contact_id or not qb_customer_id:
        continue
    company_id = contact_id_to_company.get(contact_id)
    if not company_id:
        continue
    try:
        norm_key = str(int(float(qb_customer_id)))
    except (ValueError, TypeError):
        norm_key = str(qb_customer_id)
    chain_qb_to_company[norm_key][company_id] += 1

# ── Simulate auto-matches (same as main simulation) ──────────────────
print("[3/4] Simulating auto-matches...")

auto_matched_companies = set()

# Pass 0a
for cid, qb_map in company_to_qb_via_email.items():
    if len(qb_map) != 1:
        continue
    qb_cust_id = list(qb_map.keys())[0]
    if len(qb_to_company_via_email.get(qb_cust_id, {})) != 1:
        continue
    try:
        norm_id = str(int(float(qb_cust_id)))
    except (ValueError, TypeError):
        norm_id = str(qb_cust_id)
    qb_cust = qb_by_record_id.get(norm_id) or qb_by_key_id.get(norm_id)
    if not qb_cust:
        continue
    sb_company = sb_by_id.get(cid)
    if not sb_company:
        continue
    if names_match(sb_company.get('company_name', ''), qb_cust.get('customer_name', '')):
        auto_matched_companies.add(cid)

# Pass 0b
auto_matched_qb_keys = set()
for qb_key_id_str, company_map in chain_qb_to_company.items():
    qb_cust = qb_by_key_id.get(qb_key_id_str)
    if not qb_cust or qb_cust.get('matched_company_id') in auto_matched_companies:
        continue
    if len(company_map) != 1:
        continue
    best_company = list(company_map.keys())[0]
    if best_company in auto_matched_companies:
        continue
    sb_company = sb_by_id.get(best_company)
    if not sb_company:
        continue
    if names_match(sb_company.get('company_name', ''), qb_cust.get('customer_name', '')):
        auto_matched_companies.add(best_company)

print(f"  Auto-matched companies: {len(auto_matched_companies)}")

# ── Build current revenue per company ─────────────────────────────────
current_company_rev: dict[str, float] = defaultdict(float)
current_company_qbs: dict[str, list] = defaultdict(list)
for qc in qb_customers:
    cid = qc.get('matched_company_id')
    if cid:
        current_company_rev[cid] += float(qc.get('total_invoiced') or 0)
        current_company_qbs[cid].append(qc)

# ── Categorize uncovered companies into buckets ───────────────────────
print("[4/4] Categorizing into buckets...\n")

uncovered = [
    (cid, rev) for cid, rev in sorted(current_company_rev.items(), key=lambda x: -x[1])
    if cid not in auto_matched_companies
]

bucket1 = []  # Generic name, no email link
bucket2 = []  # Name mismatch but email link exists
bucket3 = []  # True ambiguity (multi-QB or multi-SB)

for cid, rev in uncovered[:100]:
    sb_company = sb_by_id.get(cid, {})
    sb_name = sb_company.get('company_name', '?')
    num_qb = len(current_company_qbs.get(cid, []))
    has_email = cid in company_to_qb_via_email

    entry = {
        'company_id': cid,
        'sb_name': sb_name,
        'revenue': rev,
        'num_qb': num_qb,
        'has_email': has_email,
        'detail': '',
        'qb_names': [],
    }

    if has_email:
        qb_map = company_to_qb_via_email[cid]
        is_multi_sb_to_qb = len(qb_map) > 1
        best_qb_id = max(qb_map, key=lambda k: len(qb_map[k]))

        try:
            norm_id = str(int(float(best_qb_id)))
        except (ValueError, TypeError):
            norm_id = str(best_qb_id)
        qb_cust = qb_by_record_id.get(norm_id) or qb_by_key_id.get(norm_id) or {}
        qb_name = qb_cust.get('customer_name', '?')

        is_multi_qb_to_sb = len(qb_to_company_via_email.get(best_qb_id, {})) > 1
        name_ok = names_match(sb_name, qb_name)

        # Collect all QB customer names linked via email
        for qid in qb_map:
            try:
                nid = str(int(float(qid)))
            except (ValueError, TypeError):
                nid = str(qid)
            qc = qb_by_record_id.get(nid) or qb_by_key_id.get(nid) or {}
            entry['qb_names'].append(qc.get('customer_name', f'key={qid}'))

        if is_multi_sb_to_qb or is_multi_qb_to_sb:
            # Bucket 3: ambiguity
            if is_multi_sb_to_qb:
                entry['detail'] = f"SB maps to {len(qb_map)} QB customers"
            else:
                n_sb = len(qb_to_company_via_email.get(best_qb_id, {}))
                other_sbs = []
                for other_cid in qb_to_company_via_email[best_qb_id]:
                    if other_cid != cid:
                        other_sbs.append(sb_by_id.get(other_cid, {}).get('company_name', '?'))
                entry['detail'] = f"QB '{qb_name}' also links to: {', '.join(other_sbs[:3])}"
            bucket3.append(entry)
        elif not name_ok:
            # Bucket 2: name mismatch with email link
            entry['detail'] = f"'{sb_name}' vs QB '{qb_name}'"
            linking_emails = qb_map[best_qb_id][:3]
            entry['emails'] = linking_emails
            bucket2.append(entry)
        else:
            # Should have matched -- edge case or bug
            entry['detail'] = f"BUG: 1:1 + name match but missed. QB='{qb_name}'"
            bucket2.append(entry)
    else:
        # No email link at all
        qb_names_current = [qc.get('customer_name', '?') for qc in current_company_qbs.get(cid, [])[:5]]
        entry['qb_names'] = qb_names_current
        entry['detail'] = f"Currently matched to: {', '.join(qb_names_current[:3])}"
        bucket1.append(entry)

# ═══════════════════════════════════════════════════════════════════════
# Report
# ═══════════════════════════════════════════════════════════════════════

b1_rev = sum(e['revenue'] for e in bucket1)
b2_rev = sum(e['revenue'] for e in bucket2)
b3_rev = sum(e['revenue'] for e in bucket3)
total_uncovered = b1_rev + b2_rev + b3_rev

print("=" * 100)
print("  BUCKET SUMMARY (top 100 uncovered companies)")
print("=" * 100)
print(f"")
print(f"  Bucket 1 - No email link, needs manual match:     {len(bucket1):>4} companies  ${b1_rev:>12,.0f}  ({b1_rev/total_uncovered*100:.0f}%)")
print(f"  Bucket 2 - Email link, name mismatch (fixable):   {len(bucket2):>4} companies  ${b2_rev:>12,.0f}  ({b2_rev/total_uncovered*100:.0f}%)")
print(f"  Bucket 3 - True ambiguity (multi-match):          {len(bucket3):>4} companies  ${b3_rev:>12,.0f}  ({b3_rev/total_uncovered*100:.0f}%)")
print(f"  {'':45}  {'':>4}             ${total_uncovered:>12,.0f}")

# ── Bucket 1 ──────────────────────────────────────────────────────────
print(f"\n{'='*100}")
print(f"  BUCKET 1: NO EMAIL LINK ({len(bucket1)} companies, ${b1_rev:,.0f})")
print(f"  Action: Linda manually confirms in Match Review UI")
print(f"{'='*100}")
print(f"  {'Rank':>4} {'SB Company':<25} {'Revenue':>12} {'#QB':>4} Currently Matched To")
print(f"  {'-'*95}")
for i, e in enumerate(bucket1, 1):
    qbs = ', '.join(n[:25] for n in e['qb_names'][:3])
    if len(e['qb_names']) > 3:
        qbs += f' +{len(e["qb_names"])-3} more'
    print(f"  {i:>4} {e['sb_name'][:24]:<25} ${e['revenue']:>11,.0f} {e['num_qb']:>4} {qbs}")

# ── Bucket 2 ──────────────────────────────────────────────────────────
print(f"\n{'='*100}")
print(f"  BUCKET 2: EMAIL LINK + NAME MISMATCH ({len(bucket2)} companies, ${b2_rev:,.0f})")
print(f"  Action: Improve name matching (token overlap, alias-aware) or auto-stage for quick review")
print(f"{'='*100}")
print(f"  {'Rank':>4} {'SB Company':<22} {'Revenue':>12} {'QB Customer':<25} {'Why Failed'}")
print(f"  {'-'*95}")
for i, e in enumerate(bucket2, 1):
    qb_names_str = ', '.join(n[:24] for n in e['qb_names'][:2])
    emails_str = ''
    if e.get('emails'):
        emails_str = f" via {e['emails'][0]}"
    print(f"  {i:>4} {e['sb_name'][:21]:<22} ${e['revenue']:>11,.0f} {qb_names_str[:24]:<25} {e['detail'][:45]}{emails_str}")

# ── Bucket 3 ──────────────────────────────────────────────────────────
print(f"\n{'='*100}")
print(f"  BUCKET 3: TRUE AMBIGUITY ({len(bucket3)} companies, ${b3_rev:,.0f})")
print(f"  Action: Stage for human disambiguation in Match Review UI")
print(f"{'='*100}")
print(f"  {'Rank':>4} {'SB Company':<22} {'Revenue':>12} {'Ambiguity Detail'}")
print(f"  {'-'*95}")
for i, e in enumerate(bucket3, 1):
    qb_names_str = ' | '.join(n[:20] for n in e['qb_names'][:4])
    if len(e['qb_names']) > 4:
        qb_names_str += f' +{len(e["qb_names"])-4}'
    print(f"  {i:>4} {e['sb_name'][:21]:<22} ${e['revenue']:>11,.0f} {e['detail']}")
    print(f"  {'':>4} {'':22} {'':>12} QB names: {qb_names_str}")

# ── What would closing Bucket 2 buy? ─────────────────────────────────
print(f"\n{'='*100}")
print(f"  IMPACT PROJECTION")
print(f"{'='*100}")
auto_rev = sum(current_company_rev.get(cid, 0) for cid in auto_matched_companies)
print(f"  Auto-matched (current):                       ${auto_rev:>12,.0f}")
print(f"  + Bucket 2 (algorithm fix):                   ${b2_rev:>12,.0f}")
print(f"  = Total with improved matching:                ${auto_rev + b2_rev:>12,.0f}  ({(auto_rev+b2_rev)/sum(current_company_rev.values())*100:.1f}% of current)")
print(f"  + Bucket 1 (Linda reviews ~{len(bucket1)} companies):  ${b1_rev:>12,.0f}")
print(f"  + Bucket 3 (Linda disambiguates ~{len(bucket3)} cases): ${b3_rev:>12,.0f}")
print(f"  = Total potential:                             ${auto_rev + b1_rev + b2_rev + b3_rev:>12,.0f}  ({(auto_rev+b1_rev+b2_rev+b3_rev)/sum(current_company_rev.values())*100:.1f}% of current)")

print("\nDone! This was a read-only analysis. No data was changed.")
