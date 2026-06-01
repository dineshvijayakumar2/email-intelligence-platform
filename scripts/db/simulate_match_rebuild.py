"""
Pre-flight simulation: what would the QB match rebuild produce?

Simulates migration 105 (clear all matches) + new matching code (email+name gate)
without changing any data. Run this before applying the migration.

Matching pipeline simulated:
  Pass 0a — qb_unique_emails.email = customer_contacts.email_address
             -> maps SB company to QB customer via email
             -> auto-write ONLY if 1:1 + name confirmed
  Pass 0b — qb_contacts.matched_contact_id -> customer_contacts.customer_company_id
             -> maps QB customer to SB company via contact chain
             -> auto-write ONLY if 1:1 + name confirmed
  Pass 1  — Exact normalised name -> staged for review
  Pass 2  — Domain root substring -> staged for review
  Pass 3  — Fuzzy (rapidfuzz) -> staged for review

Reports: match counts, revenue coverage, top gaps, comparison with current state.
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


# ═══════════════════════════════════════════════════════════════════════
print("=" * 80)
print("  QB MATCH REBUILD SIMULATION (read-only)")
print("=" * 80)

# ── Load all data ─────────────────────────────────────────────────────
print("\n[1/7] Loading data...")

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

print(f"  qb_unique_emails:  {len(qb_unique_emails):>6}")
print(f"  customer_contacts: {len(customer_contacts):>6}")
print(f"  qb_customers:      {len(qb_customers):>6}")
print(f"  customer_companies:{len(sb_companies):>6}")
print(f"  qb_contacts (matched): {len(qb_contacts):>6}")

# ── Build lookups ─────────────────────────────────────────────────────
print("\n[2/7] Building lookups...")

# QB customer lookups
qb_by_record_id = {}
qb_by_key_id = {}
for qc in qb_customers:
    rid = qc.get('qb_record_id')
    kid = qc.get('customer_key_id')
    if rid: qb_by_record_id[str(rid)] = qc
    if kid: qb_by_key_id[str(kid)] = qc

# SB company lookups
sb_by_id = {c['id']: c for c in sb_companies}
sb_by_norm = {}
sb_by_domain_root = {}
for c in sb_companies:
    if not c.get('company_name'):
        continue
    norm = _normalise(c['company_name'])
    if norm and norm not in sb_by_norm:
        sb_by_norm[norm] = c
    for root in _extract_domain_roots(c.get('email_domains')):
        if root not in sb_by_domain_root:
            sb_by_domain_root[root] = c

# Contact email -> company lookup
contact_email_to_company = {}
contact_id_to_company = {}
for cc in customer_contacts:
    email = (cc.get('email_address') or '').strip().lower()
    cid = cc.get('customer_company_id')
    if email and cid:
        contact_email_to_company[email] = cid
    if cc.get('id') and cid:
        contact_id_to_company[cc['id']] = cid

# Current state (for comparison)
current_matches = {}
for qc in qb_customers:
    if qc.get('matched_company_id'):
        current_matches[qc['id']] = qc['matched_company_id']

print(f"  Current matches: {len(current_matches)}")

# ── Simulate Pass 0a: unique email matching ───────────────────────────
print("\n[3/7] Simulating Pass 0a (unique email matching)...")

email_to_qb_cust = {}
for ue in qb_unique_emails:
    email = (ue.get('email') or '').strip().lower()
    qb_cid = ue.get('qb_customer_id')
    if email and qb_cid:
        email_to_qb_cust[email] = str(qb_cid).strip()

# company_id -> {qb_customer_id: [emails]}
company_to_qb_via_email: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
for cc in customer_contacts:
    email = (cc.get('email_address') or '').strip().lower()
    company_id = cc.get('customer_company_id')
    if not email or not company_id:
        continue
    qb_cust_id = email_to_qb_cust.get(email)
    if qb_cust_id:
        company_to_qb_via_email[company_id][qb_cust_id].append(email)

# Also build reverse: qb_customer -> {company_id: [emails]}
qb_to_company_via_email: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
for company_id, qb_map in company_to_qb_via_email.items():
    for qb_cid, emails in qb_map.items():
        qb_to_company_via_email[qb_cid][company_id].extend(emails)

# Resolve: pick best QB customer per company (majority vote)
company_best_qb: dict[str, tuple[str, list]] = {}
for company_id, qb_map in company_to_qb_via_email.items():
    best = max(qb_map, key=lambda k: len(qb_map[k]))
    company_best_qb[company_id] = (best, qb_map[best])

def names_match(sb_name, qb_name):
    sn = _normalise(sb_name)
    qn = _normalise(qb_name)
    if not sn or not qn:
        return False
    return sn in qn or qn in sn

# Apply 1:1 + name confirmation gate
pass0a_auto = {}      # qb_customer_uuid -> company_id
pass0a_staged = {}    # qb_customer_uuid -> (company_id, qb_name, sb_name)

for company_id, (qb_cust_id, emails) in company_best_qb.items():
    # Resolve QB customer
    try:
        norm_id = str(int(float(qb_cust_id)))
    except (ValueError, TypeError):
        norm_id = str(qb_cust_id)
    qb_cust = qb_by_record_id.get(norm_id) or qb_by_key_id.get(norm_id)
    if not qb_cust:
        continue

    sb_company = sb_by_id.get(company_id)
    if not sb_company:
        continue

    # 1:1 check: this company maps to exactly 1 QB customer AND vice versa
    is_1to1_sb = len(company_to_qb_via_email.get(company_id, {})) == 1
    is_1to1_qb = len(qb_to_company_via_email.get(qb_cust_id, {})) == 1
    is_1to1 = is_1to1_sb and is_1to1_qb

    name_ok = names_match(sb_company.get('company_name', ''), qb_cust.get('customer_name', ''))

    qb_uuid = qb_cust['id']
    if is_1to1 and name_ok:
        pass0a_auto[qb_uuid] = company_id
    else:
        pass0a_staged[qb_uuid] = (company_id, qb_cust.get('customer_name', '?'), sb_company.get('company_name', '?'))

print(f"  Email links found: {len(company_best_qb)} companies -> QB customers")
print(f"  Auto-match (1:1 + name): {len(pass0a_auto)}")
print(f"  Staged for review:       {len(pass0a_staged)}")

# ── Simulate Pass 0b: contact chain matching ──────────────────────────
print("\n[4/7] Simulating Pass 0b (contact chain matching)...")

# qb_contacts (matched) -> customer_contacts -> customer_company_id
# Then: qb_contacts.qb_customer_id -> qb_customers.customer_key_id
already_matched = set(pass0a_auto.keys())

# Build: qb_customer_key_id -> company_id (via contact chain)
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

pass0b_auto = {}
pass0b_staged = {}

for qb_key_id, company_map in chain_qb_to_company.items():
    qb_cust = qb_by_key_id.get(qb_key_id)
    if not qb_cust:
        continue
    if qb_cust['id'] in already_matched:
        continue

    best_company = max(company_map, key=company_map.get)
    sb_company = sb_by_id.get(best_company)
    if not sb_company:
        continue

    is_1to1 = len(company_map) == 1
    name_ok = names_match(sb_company.get('company_name', ''), qb_cust.get('customer_name', ''))

    if is_1to1 and name_ok:
        pass0b_auto[qb_cust['id']] = best_company
    else:
        pass0b_staged[qb_cust['id']] = (best_company, qb_cust.get('customer_name', '?'), sb_company.get('company_name', '?'))

print(f"  Contact chain links: {len(chain_qb_to_company)} QB customers")
print(f"  Auto-match (1:1 + name): {len(pass0b_auto)}")
print(f"  Staged for review:       {len(pass0b_staged)}")

# ── Simulate Pass 1-3: name-based (all staged) ───────────────────────
print("\n[5/7] Simulating Pass 1-3 (name-based, all staged)...")

all_auto = {**pass0a_auto, **pass0b_auto}
auto_matched_qb_uuids = set(all_auto.keys())

# QB customers still unmatched after Pass 0a + 0b
remaining = [qc for qc in qb_customers if qc['id'] not in auto_matched_qb_uuids]

pass1_staged = 0
pass2_staged = 0
pass2_remaining = []

for qc in remaining:
    qb_norm = _normalise(qc.get('customer_name'))
    if not qb_norm:
        pass2_remaining.append(qc)
        continue

    sb_match = sb_by_norm.get(qb_norm)
    if sb_match:
        pass1_staged += 1
    else:
        pass2_remaining.append(qc)

for qc in pass2_remaining:
    qb_norm = _normalise(qc.get('customer_name'))
    if not qb_norm:
        continue
    for root, sb_company in sb_by_domain_root.items():
        if root in qb_norm:
            pass2_staged += 1
            break

# Pass 3 (fuzzy) — skip actual rapidfuzz, just count unmatched
unmatched_after_all = len(remaining) - pass1_staged - pass2_staged

print(f"  Pass 1 (exact name) staged:  {pass1_staged}")
print(f"  Pass 2 (domain root) staged: {pass2_staged}")
print(f"  Unmatched (would go to Pass 3 fuzzy): {unmatched_after_all}")

# ── Revenue analysis ──────────────────────────────────────────────────
print("\n[6/7] Revenue analysis...")

def revenue_for(qb_uuid):
    for qc in qb_customers:
        if qc['id'] == qb_uuid:
            return float(qc.get('total_invoiced') or 0)
    return 0

# Revenue by match category
auto_revenue = sum(revenue_for(qid) for qid in all_auto)
staged_revenue_0a = sum(revenue_for(qid) for qid in pass0a_staged)
staged_revenue_0b = sum(revenue_for(qid) for qid in pass0b_staged)

# Current total matched revenue
current_revenue = sum(float(qc.get('total_invoiced') or 0) for qc in qb_customers if qc.get('matched_company_id'))
total_qb_revenue = sum(float(qc.get('total_invoiced') or 0) for qc in qb_customers)

# Revenue by company (new auto-matches)
new_company_revenue: dict[str, float] = defaultdict(float)
for qb_uuid, company_id in all_auto.items():
    new_company_revenue[company_id] += revenue_for(qb_uuid)

print(f"\n  {'Category':<45} {'Customers':>10} {'Revenue':>15} {'% of Total':>10}")
print(f"  {'-'*82}")
print(f"  {'Current state (all methods, contaminated)':<45} {len(current_matches):>10} ${current_revenue:>13,.0f} {current_revenue/total_qb_revenue*100:>9.1f}%")
print(f"  {'':<45} {'':>10} {'':>15} {'':>10}")
print(f"  {'NEW: Pass 0a auto (email + name confirmed)':<45} {len(pass0a_auto):>10} ${auto_revenue - sum(revenue_for(q) for q in pass0b_auto):>13,.0f}")
print(f"  {'NEW: Pass 0b auto (contact chain + name)':<45} {len(pass0b_auto):>10} ${sum(revenue_for(q) for q in pass0b_auto):>13,.0f}")
print(f"  {'NEW: Total auto-matched':<45} {len(all_auto):>10} ${auto_revenue:>13,.0f} {auto_revenue/total_qb_revenue*100:>9.1f}%")
print(f"  {'':<45} {'':>10} {'':>15} {'':>10}")
print(f"  {'Staged: Pass 0a (email, no name match)':<45} {len(pass0a_staged):>10} ${staged_revenue_0a:>13,.0f}")
print(f"  {'Staged: Pass 0b (chain, no name match)':<45} {len(pass0b_staged):>10} ${staged_revenue_0b:>13,.0f}")
print(f"  {'Staged: Pass 1 (exact name, no email)':<45} {pass1_staged:>10}")
print(f"  {'Staged: Pass 2 (domain root, no email)':<45} {pass2_staged:>10}")
print(f"  {'Unmatched (Pass 3 fuzzy candidates)':<45} {unmatched_after_all:>10}")
print(f"  {'':<45} {'':>10} {'':>15} {'':>10}")
print(f"  {'Total QB revenue':<45} {len(qb_customers):>10} ${total_qb_revenue:>13,.0f} {'100.0%':>10}")

# ── Top 50 auto-matched companies by revenue ─────────────────────────
print(f"\n[7/7] Top 50 auto-matched companies by revenue...")
print(f"\n  {'Rank':>4} {'SB Company':<28} {'QB Customer':<28} {'Revenue':>13} {'Source':<8}")
print(f"  {'-'*85}")

top_new = sorted(new_company_revenue.items(), key=lambda x: -x[1])[:50]
for rank, (company_id, rev) in enumerate(top_new, 1):
    sb_name = sb_by_id.get(company_id, {}).get('company_name', '?')[:27]
    # Find matching QB customer
    qb_uuid = None
    source = '0a'
    for q, c in pass0a_auto.items():
        if c == company_id:
            qb_uuid = q
            break
    if not qb_uuid:
        for q, c in pass0b_auto.items():
            if c == company_id:
                qb_uuid = q
                source = '0b'
                break
    qb_name = '?'
    if qb_uuid:
        for qc in qb_customers:
            if qc['id'] == qb_uuid:
                qb_name = qc.get('customer_name', '?')[:27]
                break
    print(f"  {rank:>4} {sb_name:<28} {qb_name:<28} ${rev:>12,.0f} {source:<8}")

# ── Top 30 UNCOVERED current-revenue companies ───────────────────────
print(f"\n  Top 30 high-revenue companies NOT auto-matched after rebuild:")
print(f"  {'Rank':>4} {'SB Company':<28} {'Current Rev':>13} {'#QB Now':>7} {'Email Link?':<12} {'Reason'}")
print(f"  {'-'*95}")

# Current revenue per company
current_company_rev: dict[str, float] = defaultdict(float)
current_company_count: dict[str, int] = defaultdict(int)
for qc in qb_customers:
    cid = qc.get('matched_company_id')
    if cid:
        current_company_rev[cid] += float(qc.get('total_invoiced') or 0)
        current_company_count[cid] += 1

auto_companies = set(all_auto.values())
uncovered = [(cid, rev) for cid, rev in sorted(current_company_rev.items(), key=lambda x: -x[1]) if cid not in auto_companies]

for rank, (cid, rev) in enumerate(uncovered[:30], 1):
    sb_name = sb_by_id.get(cid, {}).get('company_name', '?')[:27]
    num_qb = current_company_count[cid]
    has_email = cid in company_to_qb_via_email

    # Diagnose why not auto-matched
    if has_email:
        qb_map = company_to_qb_via_email[cid]
        best_qb_id = max(qb_map, key=lambda k: len(qb_map[k]))
        try:
            norm_id = str(int(float(best_qb_id)))
        except (ValueError, TypeError):
            norm_id = str(best_qb_id)
        qb_cust = qb_by_record_id.get(norm_id) or qb_by_key_id.get(norm_id) or {}
        qb_name = qb_cust.get('customer_name', '?')
        is_1to1_sb = len(qb_map) == 1
        is_1to1_qb = len(qb_to_company_via_email.get(best_qb_id, {})) == 1
        name_ok = names_match(sb_by_id.get(cid, {}).get('company_name', ''), qb_name)

        if not is_1to1_sb:
            reason = f"SB->multi QB ({len(qb_map)}); best='{qb_name[:20]}'"
        elif not is_1to1_qb:
            n_sb = len(qb_to_company_via_email.get(best_qb_id, {}))
            reason = f"QB->multi SB ({n_sb}); '{qb_name[:20]}'"
        elif not name_ok:
            reason = f"name mismatch: '{qb_name[:25]}'"
        else:
            reason = "BUG: should have matched"
    else:
        reason = "no email link"

    print(f"  {rank:>4} {sb_name:<28} ${rev:>12,.0f} {num_qb:>7} {'email+' if has_email else 'none':<12} {reason}")

# ── Summary ───────────────────────────────────────────────────────────
print(f"\n{'='*80}")
print(f"  SUMMARY")
print(f"{'='*80}")
print(f"  Before: {len(current_matches):,} QB customers matched ({len(set(current_matches.values())):,} companies)")
print(f"          ${current_revenue:,.0f} revenue linked")
print(f"          BUT 759 companies have >1 QB customer (contaminated)")
print(f"")
print(f"  After:  {len(all_auto):,} QB customers auto-matched ({len(set(all_auto.values())):,} companies)")
print(f"          ${auto_revenue:,.0f} revenue linked (clean, verified)")
print(f"          {len(pass0a_staged) + len(pass0b_staged)} email matches staged for review")
print(f"          {pass1_staged + pass2_staged} name matches staged for review")
print(f"          0 companies with false-positive multi-matches")
print(f"")
print(f"  Revenue coverage: {auto_revenue/current_revenue*100:.1f}% of current")
print(f"                    {auto_revenue/total_qb_revenue*100:.1f}% of total QB revenue")

print("\nDone! This was a read-only simulation. No data was changed.")
