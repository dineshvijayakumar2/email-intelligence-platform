"""
Pre-flight simulation (DOMAIN-CONFIRM variant): would loosening the Pass 0a
auto-gate from `is_1to1 AND name_ok` to `is_1to1 AND (name_ok OR domain_root_match)`
auto-resolve currently-staged matches without losing safety?

Copy of simulate_match_rebuild.py. ONLY Pass 0a changes:
  - For each Pass 0a candidate (company<->QB customer via email, 1:1), also compute
    whether the LINKING email's domain root matches one of the SB company's
    email_domains roots (reuse _extract_domain_roots, skip GENERIC_DOMAINS).
  - New auto-gate: is_1to1 AND (name_ok OR domain_root_match).
  - 1:1 requirement UNCHANGED — multi-mappings are never auto-matched.

Pass 0b and the name-based passes are unchanged from the original.

Reports:
  - ADDITIONAL companies auto-matched under domain confirmation (vs old name-only gate)
    + their revenue.
  - New total auto-match count + revenue coverage % (before/after).
  - 20-row sample of additional domain-confirmed matches (sb_name, qb_name, shared root).
  - Re-classification of remaining staged/unmatched: genuine multi-match (1:N),
    name-only-no-email, no-link (+ residual email-1:1-unconfirmed) with counts + revenue.

Read-only. Changes no data. Full detail written to domainconfirm_sim.json.
"""
import os, sys, re, json
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

def _email_domain_root(email):
    """Domain root of a single email address, using the same rules as
    _extract_domain_roots (skip generic providers, root = first label, len >= 5)."""
    email = (email or '').strip().lower()
    if '@' not in email:
        return None
    domain = email.rsplit('@', 1)[1]
    if not domain or domain in GENERIC_DOMAINS:
        return None
    parts = domain.split('.')
    root = parts[0] if parts else ''
    return root if len(root) >= 5 else None

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
print("  QB MATCH REBUILD SIMULATION — DOMAIN CONFIRM (read-only)")
print("=" * 80)

# ── Load all data ─────────────────────────────────────────────────────
print("\n[1/6] Loading data...")

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
print("\n[2/6] Building lookups...")

qb_by_record_id = {}
qb_by_key_id = {}
for qc in qb_customers:
    rid = qc.get('qb_record_id')
    kid = qc.get('customer_key_id')
    if rid: qb_by_record_id[str(rid)] = qc
    if kid: qb_by_key_id[str(kid)] = qc

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

contact_email_to_company = {}
contact_id_to_company = {}
for cc in customer_contacts:
    email = (cc.get('email_address') or '').strip().lower()
    cid = cc.get('customer_company_id')
    if email and cid:
        contact_email_to_company[email] = cid
    if cc.get('id') and cid:
        contact_id_to_company[cc['id']] = cid

# Revenue + name lookups keyed by qb_customer uuid (fast, avoids O(n) scans)
qb_rev = {qc['id']: float(qc.get('total_invoiced') or 0) for qc in qb_customers}
qb_name_by_uuid = {qc['id']: (qc.get('customer_name') or '?') for qc in qb_customers}

current_matches = {}
for qc in qb_customers:
    if qc.get('matched_company_id'):
        current_matches[qc['id']] = qc['matched_company_id']

total_qb_revenue = sum(qb_rev.values())
current_revenue = sum(qb_rev[qc['id']] for qc in qb_customers if qc.get('matched_company_id'))

print(f"  Current matches: {len(current_matches)}")

def names_match(sb_name, qb_name):
    sn = _normalise(sb_name)
    qn = _normalise(qb_name)
    if not sn or not qn:
        return False
    return sn in qn or qn in sn

# ── Simulate Pass 0a: unique email matching (+ domain confirmation) ────
print("\n[3/6] Simulating Pass 0a (email matching + domain confirmation)...")

email_to_qb_cust = {}
for ue in qb_unique_emails:
    email = (ue.get('email') or '').strip().lower()
    qb_cid = ue.get('qb_customer_id')
    if email and qb_cid:
        email_to_qb_cust[email] = str(qb_cid).strip()

company_to_qb_via_email: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
for cc in customer_contacts:
    email = (cc.get('email_address') or '').strip().lower()
    company_id = cc.get('customer_company_id')
    if not email or not company_id:
        continue
    qb_cust_id = email_to_qb_cust.get(email)
    if qb_cust_id:
        company_to_qb_via_email[company_id][qb_cust_id].append(email)

qb_to_company_via_email: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
for company_id, qb_map in company_to_qb_via_email.items():
    for qb_cid, emails in qb_map.items():
        qb_to_company_via_email[qb_cid][company_id].extend(emails)

company_best_qb: dict[str, tuple[str, list]] = {}
for company_id, qb_map in company_to_qb_via_email.items():
    best = max(qb_map, key=lambda k: len(qb_map[k]))
    company_best_qb[company_id] = (best, qb_map[best])

# Per-candidate records. One per company that has a best-QB email link.
pass0a_records = []   # dicts: company_id, qb_uuid, is_1to1, name_ok, domain_match, shared_root, sb_name, qb_name, revenue

for company_id, (qb_cust_id, emails) in company_best_qb.items():
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

    is_1to1_sb = len(company_to_qb_via_email.get(company_id, {})) == 1
    is_1to1_qb = len(qb_to_company_via_email.get(qb_cust_id, {})) == 1
    is_1to1 = is_1to1_sb and is_1to1_qb

    sb_name = sb_company.get('company_name', '?')
    qb_name = qb_cust.get('customer_name', '?')
    name_ok = names_match(sb_name, qb_name)

    # Domain confirmation: does any linking email's domain root match the SB
    # company's known email_domains roots?
    sb_roots = set(_extract_domain_roots(sb_company.get('email_domains')))
    linking_roots = {_email_domain_root(e) for e in emails}
    linking_roots.discard(None)
    shared = sb_roots & linking_roots
    domain_match = bool(shared)
    shared_root = sorted(shared)[0] if shared else None

    pass0a_records.append({
        'company_id': company_id,
        'qb_uuid': qb_cust['id'],
        'is_1to1': is_1to1,
        'is_1to1_sb': is_1to1_sb,
        'is_1to1_qb': is_1to1_qb,
        'name_ok': name_ok,
        'domain_match': domain_match,
        'shared_root': shared_root,
        'sb_name': sb_name,
        'qb_name': qb_name,
        'revenue': qb_rev.get(qb_cust['id'], 0.0),
    })

# Old gate (name only) vs new gate (name OR domain)
pass0a_auto_old = {}   # qb_uuid -> company_id
pass0a_auto_new = {}   # qb_uuid -> company_id
pass0a_additional = [] # records newly auto under domain confirm (were staged before)
for r in pass0a_records:
    old_auto = r['is_1to1'] and r['name_ok']
    new_auto = r['is_1to1'] and (r['name_ok'] or r['domain_match'])
    if old_auto:
        pass0a_auto_old[r['qb_uuid']] = r['company_id']
    if new_auto:
        pass0a_auto_new[r['qb_uuid']] = r['company_id']
    if new_auto and not old_auto:
        pass0a_additional.append(r)

print(f"  Email links found: {len(company_best_qb)} companies -> QB customers")
print(f"  Auto (old gate, name only):        {len(pass0a_auto_old)}")
print(f"  Auto (new gate, name OR domain):   {len(pass0a_auto_new)}")
print(f"  ADDITIONAL via domain confirm:     {len(pass0a_additional)}")

# ── Simulate Pass 0b: contact chain matching (UNCHANGED) ──────────────
print("\n[4/6] Simulating Pass 0b (contact chain matching, unchanged)...")

# 0b runs after 0a auto; mirror original which skips 0a auto-matched.
# Use the NEW 0a auto set as "already matched" so the pipeline is consistent.
already_matched = set(pass0a_auto_new.keys())

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
pass0b_staged = {}   # qb_uuid -> (company_id, is_1to1)
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
        pass0b_staged[qb_cust['id']] = (best_company, is_1to1)

print(f"  Contact chain links: {len(chain_qb_to_company)} QB customers")
print(f"  Auto-match (1:1 + name): {len(pass0b_auto)}")
print(f"  Staged for review:       {len(pass0b_staged)}")

# ── Before/after auto-match totals + revenue ──────────────────────────
before_auto = set(pass0a_auto_old) | set(pass0b_auto)
after_auto = set(pass0a_auto_new) | set(pass0b_auto)
additional_uuids = after_auto - before_auto

before_revenue = sum(qb_rev[u] for u in before_auto)
after_revenue = sum(qb_rev[u] for u in after_auto)
additional_revenue = sum(qb_rev[u] for u in additional_uuids)

before_companies = set(pass0a_auto_old.values()) | set(pass0b_auto.values())
after_companies = set(pass0a_auto_new.values()) | set(pass0b_auto.values())
additional_companies = after_companies - before_companies

# ── Re-classify remaining (non-auto) QB customers ─────────────────────
print("\n[5/6] Re-classifying remaining staged/unmatched...")

# bucket per qb uuid: auto / multi / email_1to1_unconfirmed / name_only / no_link
qb_bucket = {qc['id']: 'no_link' for qc in qb_customers}

for u in after_auto:
    qb_bucket[u] = 'auto'

# Pass 0a residuals (not auto under new gate)
for r in pass0a_records:
    u = r['qb_uuid']
    if qb_bucket[u] == 'auto':
        continue
    if not r['is_1to1']:
        qb_bucket[u] = 'multi'
    else:
        # 1:1 email link but neither name nor domain confirmed
        if qb_bucket[u] not in ('multi',):
            qb_bucket[u] = 'email_1to1_unconfirmed'

# Pass 0b residuals (contact chain, not auto). Don't override a stronger 0a verdict.
for u, (company_id, is_1to1) in pass0b_staged.items():
    if qb_bucket.get(u) in ('auto', 'multi'):
        continue
    if not is_1to1:
        qb_bucket[u] = 'multi'
    elif qb_bucket.get(u) == 'no_link':
        qb_bucket[u] = 'email_1to1_unconfirmed'

# Name-based passes: for anything still 'no_link', see if name matches (Pass 1/2)
for qc in qb_customers:
    u = qc['id']
    if qb_bucket[u] != 'no_link':
        continue
    qb_norm = _normalise(qc.get('customer_name'))
    if not qb_norm:
        continue
    if qb_norm in sb_by_norm:
        qb_bucket[u] = 'name_only'
        continue
    for root in sb_by_domain_root:
        if root in qb_norm:
            qb_bucket[u] = 'name_only'
            break

def bucket_stats(name):
    uuids = [u for u, b in qb_bucket.items() if b == name]
    return len(uuids), sum(qb_rev[u] for u in uuids)

multi_n, multi_rev = bucket_stats('multi')
unconf_n, unconf_rev = bucket_stats('email_1to1_unconfirmed')
nameonly_n, nameonly_rev = bucket_stats('name_only')
nolink_n, nolink_rev = bucket_stats('no_link')
auto_n, auto_rev = bucket_stats('auto')

# ── Build 20-row sample of additional domain-confirmed matches ────────
sample = sorted(pass0a_additional, key=lambda r: -r['revenue'])[:20]

# ═══════════════════════════════════════════════════════════════════════
# REPORT
# ═══════════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("  RESULTS — DOMAIN CONFIRMATION DELTA")
print(f"{'='*80}")

print(f"\n  ADDITIONAL auto-matches unlocked by domain confirmation:")
print(f"    QB customers:  {len(additional_uuids):>6}")
print(f"    Companies:     {len(additional_companies):>6}")
print(f"    Revenue:       ${additional_revenue:>14,.0f}")

print(f"\n  Auto-match totals (Pass 0a + 0b):")
print(f"    {'':<24}{'count':>8}{'revenue':>18}{'% total QB rev':>16}")
print(f"    {'Before (name only)':<24}{len(before_auto):>8}${before_revenue:>16,.0f}{before_revenue/total_qb_revenue*100:>15.1f}%")
print(f"    {'After (name OR domain)':<24}{len(after_auto):>8}${after_revenue:>16,.0f}{after_revenue/total_qb_revenue*100:>15.1f}%")
print(f"    {'Delta':<24}{len(additional_uuids):>8}${additional_revenue:>16,.0f}{(after_revenue-before_revenue)/total_qb_revenue*100:>15.1f}%")

print(f"\n  Coverage vs current contaminated state (${current_revenue:,.0f}):")
print(f"    Before: {before_revenue/current_revenue*100:>6.1f}%   After: {after_revenue/current_revenue*100:>6.1f}%")

print(f"\n  Sample of 20 additional domain-confirmed matches (verify same company):")
print(f"    {'SB company':<32}{'QB customer':<32}{'shared root':<16}{'revenue':>12}")
print(f"    {'-'*92}")
for r in sample:
    print(f"    {r['sb_name'][:31]:<32}{r['qb_name'][:31]:<32}{(r['shared_root'] or '?'):<16}${r['revenue']:>11,.0f}")

print(f"\n  Remaining staged/unmatched triage (all non-auto QB customers):")
print(f"    {'bucket':<34}{'count':>8}{'revenue':>18}")
print(f"    {'-'*60}")
print(f"    {'genuine multi-match (1:N)':<34}{multi_n:>8}${multi_rev:>16,.0f}")
print(f"    {'name-only-no-email':<34}{nameonly_n:>8}${nameonly_rev:>16,.0f}")
print(f"    {'no-link':<34}{nolink_n:>8}${nolink_rev:>16,.0f}")
print(f"    {'(residual) email 1:1 unconfirmed':<34}{unconf_n:>8}${unconf_rev:>16,.0f}")
print(f"    {'-'*60}")
print(f"    {'auto-matched (for reference)':<34}{auto_n:>8}${auto_rev:>16,.0f}")
remaining_total = multi_n + nameonly_n + nolink_n + unconf_n
print(f"    {'TOTAL non-auto':<34}{remaining_total:>8}${multi_rev+nameonly_rev+nolink_rev+unconf_rev:>16,.0f}")
print(f"    {'TOTAL QB customers':<34}{len(qb_customers):>8}${total_qb_revenue:>16,.0f}")

# ── Write full detail to JSON ─────────────────────────────────────────
print("\n[6/6] Writing domainconfirm_sim.json...")

out = {
    'params': {
        'client_id': CLIENT_ID,
        'old_gate': 'is_1to1 AND name_ok',
        'new_gate': 'is_1to1 AND (name_ok OR domain_root_match)',
        'total_qb_customers': len(qb_customers),
        'total_qb_revenue': total_qb_revenue,
        'current_matched_count': len(current_matches),
        'current_matched_revenue': current_revenue,
    },
    'additional_auto_matches': {
        'qb_customer_count': len(additional_uuids),
        'company_count': len(additional_companies),
        'revenue': additional_revenue,
        'records': [
            {
                'sb_name': r['sb_name'],
                'qb_name': r['qb_name'],
                'shared_root': r['shared_root'],
                'company_id': r['company_id'],
                'qb_uuid': r['qb_uuid'],
                'revenue': r['revenue'],
            }
            for r in sorted(pass0a_additional, key=lambda x: -x['revenue'])
        ],
    },
    'sample_20': [
        {'sb_name': r['sb_name'], 'qb_name': r['qb_name'],
         'shared_root': r['shared_root'], 'revenue': r['revenue']}
        for r in sample
    ],
    'auto_totals': {
        'before': {'count': len(before_auto), 'revenue': before_revenue,
                   'pct_total_qb': before_revenue/total_qb_revenue*100,
                   'pct_current': before_revenue/current_revenue*100},
        'after': {'count': len(after_auto), 'revenue': after_revenue,
                  'pct_total_qb': after_revenue/total_qb_revenue*100,
                  'pct_current': after_revenue/current_revenue*100},
        'delta': {'count': len(additional_uuids), 'revenue': additional_revenue},
        'pass0a_auto_old': len(pass0a_auto_old),
        'pass0a_auto_new': len(pass0a_auto_new),
        'pass0b_auto': len(pass0b_auto),
    },
    'remaining_buckets': {
        'genuine_multi_match': {'count': multi_n, 'revenue': multi_rev},
        'name_only_no_email': {'count': nameonly_n, 'revenue': nameonly_rev},
        'no_link': {'count': nolink_n, 'revenue': nolink_rev},
        'email_1to1_unconfirmed_residual': {'count': unconf_n, 'revenue': unconf_rev},
        'auto_matched_reference': {'count': auto_n, 'revenue': auto_rev},
    },
}

out_path = os.path.join(os.path.dirname(__file__), 'domainconfirm_sim.json')
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(out, f, indent=2, default=str)

print(f"  Wrote {out_path}")
print("\nDone! Read-only simulation. No data was changed.")
