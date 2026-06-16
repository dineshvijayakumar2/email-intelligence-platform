"""
Pre-flight simulation (QB-SIDE DOMAIN variant): the naive domain-confirm gate
(simulate_match_rebuild_domainconfirm.py) failed because it matched the LINKING
email's domain root, which belongs to the SB-side contact (often a broker) — so
it endorsed broker traffic (Good Practice -> Bulgari, etc.).

This prototype tests confirming the *QB customer's own* domain against the SB
company's domain, from sources OTHER than the linking email:

  Variant A — QB-side contact domain:
    qb_domain_match = SB company's email_domains roots intersect the QB customer's
    OWN qb_contacts email domain roots. The broker's email is not (usually) the
    QB end-customer's own contact, so this rejects broker links.

  Variant B — promiscuity-guarded linking domain (T = 1,2,3,5):
    Keep the linking-domain match BUT reject if the shared root is "promiscuous"
    — i.e. it links to more than T distinct QB customers across qb_unique_emails.
    A genuine company domain links to ~1 QB customer; a broker domain links to many.

Gate compared in every case keeps the 1:1 requirement:
  old:        is_1to1 AND name_ok
  variant A:  is_1to1 AND (name_ok OR qb_domain_match)
  variant B:  is_1to1 AND (name_ok OR (linking_domain_match AND promiscuity<=T))

For each variant: additional auto-matches vs old gate, revenue, and — critically —
how many of the 333 naive-domain false-positives it correctly REJECTS / keeps.
20-row sample for the recommended variant. Read-only. Writes qbdomain_sim.json.
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
    email = (email or '').strip().lower()
    if '@' not in email:
        return None
    domain = email.rsplit('@', 1)[1]
    if not domain or domain in GENERIC_DOMAINS:
        return None
    parts = domain.split('.')
    root = parts[0] if parts else ''
    return root if len(root) >= 5 else None

def _norm_qb_id(raw):
    try:
        return str(int(float(raw)))
    except (ValueError, TypeError):
        return str(raw)

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


print("=" * 80)
print("  QB MATCH REBUILD SIMULATION — QB-SIDE DOMAIN (read-only)")
print("=" * 80)

# ── Load data ─────────────────────────────────────────────────────────
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
# ALL qb_contacts (not just matched) — needed for QB-side own domains
qb_contacts_all = fetch_all('qb_contacts', 'id, email, qb_customer_id', [
    lambda q: q.not_.is_('email', 'null'),
])

print(f"  qb_unique_emails:  {len(qb_unique_emails):>6}")
print(f"  customer_contacts: {len(customer_contacts):>6}")
print(f"  qb_customers:      {len(qb_customers):>6}")
print(f"  customer_companies:{len(sb_companies):>6}")
print(f"  qb_contacts (all w/ email): {len(qb_contacts_all):>6}")

# ── Lookups ───────────────────────────────────────────────────────────
print("\n[2/6] Building lookups...")
qb_by_record_id = {}
qb_by_key_id = {}
for qc in qb_customers:
    rid = qc.get('qb_record_id')
    kid = qc.get('customer_key_id')
    if rid: qb_by_record_id[str(rid)] = qc
    if kid: qb_by_key_id[str(kid)] = qc

def resolve_qb(raw):
    n = _norm_qb_id(raw)
    return qb_by_record_id.get(n) or qb_by_key_id.get(n)

sb_by_id = {c['id']: c for c in sb_companies}
qb_rev = {qc['id']: float(qc.get('total_invoiced') or 0) for qc in qb_customers}

total_qb_revenue = sum(qb_rev.values())
current_matches = {qc['id']: qc['matched_company_id'] for qc in qb_customers if qc.get('matched_company_id')}
current_revenue = sum(qb_rev[u] for u in current_matches)

# QB customer's OWN domain roots, from its qb_contacts (qb_customer_id -> key_id)
qb_own_roots: dict[str, set] = defaultdict(set)
for qbc in qb_contacts_all:
    root = _email_domain_root(qbc.get('email'))
    if not root:
        continue
    qb = qb_by_key_id.get(_norm_qb_id(qbc.get('qb_customer_id')))
    if qb:
        qb_own_roots[qb['id']].add(root)

# Domain-root promiscuity: how many distinct QB customers does each root link to
# across qb_unique_emails? (a broker domain links to many; a real company ~1)
root_to_qbcusts: dict[str, set] = defaultdict(set)
for ue in qb_unique_emails:
    root = _email_domain_root(ue.get('email'))
    if not root:
        continue
    qb = resolve_qb(ue.get('qb_customer_id'))
    if qb:
        root_to_qbcusts[root].add(qb['id'])
promiscuity = {r: len(s) for r, s in root_to_qbcusts.items()}

print(f"  Current matches: {len(current_matches)}")
print(f"  QB customers with own contact-domain roots: {len(qb_own_roots)}")
print(f"  Distinct linking-domain roots: {len(promiscuity)}")

def names_match(sb_name, qb_name):
    sn = _normalise(sb_name)
    qn = _normalise(qb_name)
    if not sn or not qn:
        return False
    return sn in qn or qn in sn

# ── Build Pass 0a candidates (same as original) ───────────────────────
print("\n[3/6] Building Pass 0a candidates...")
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

company_best_qb = {}
for company_id, qb_map in company_to_qb_via_email.items():
    best = max(qb_map, key=lambda k: len(qb_map[k]))
    company_best_qb[company_id] = (best, qb_map[best])

records = []
for company_id, (qb_cust_id, emails) in company_best_qb.items():
    qb_cust = resolve_qb(qb_cust_id)
    if not qb_cust:
        continue
    sb_company = sb_by_id.get(company_id)
    if not sb_company:
        continue

    is_1to1 = (len(company_to_qb_via_email.get(company_id, {})) == 1
               and len(qb_to_company_via_email.get(qb_cust_id, {})) == 1)
    sb_name = sb_company.get('company_name', '?')
    qb_name = qb_cust.get('customer_name', '?')
    name_ok = names_match(sb_name, qb_name)

    sb_roots = set(_extract_domain_roots(sb_company.get('email_domains')))
    linking_roots = {_email_domain_root(e) for e in emails}
    linking_roots.discard(None)
    link_shared = sb_roots & linking_roots
    link_domain_match = bool(link_shared)
    link_root = sorted(link_shared)[0] if link_shared else None
    # promiscuity of the matched linking root (max across shared roots = worst case;
    # use the least promiscuous shared root to be generous to genuine matches)
    link_prom = min((promiscuity.get(r, 0) for r in link_shared), default=0)

    # Variant A: QB customer's OWN contact domains vs SB domains
    qb_roots = qb_own_roots.get(qb_cust['id'], set())
    qb_shared = sb_roots & qb_roots
    qb_domain_match = bool(qb_shared)
    qb_root = sorted(qb_shared)[0] if qb_shared else None

    records.append({
        'company_id': company_id, 'qb_uuid': qb_cust['id'],
        'is_1to1': is_1to1, 'name_ok': name_ok,
        'sb_name': sb_name, 'qb_name': qb_name,
        'link_domain_match': link_domain_match, 'link_root': link_root, 'link_prom': link_prom,
        'qb_domain_match': qb_domain_match, 'qb_root': qb_root,
        'revenue': qb_rev.get(qb_cust['id'], 0.0),
    })

print(f"  Candidates (1:1 or not): {len(records)}")

# ── Evaluate gates ────────────────────────────────────────────────────
print("\n[4/6] Evaluating gates...")

def auto_set(predicate):
    """Return dict qb_uuid -> record for candidates passing 1:1 AND predicate."""
    out = {}
    for r in records:
        if r['is_1to1'] and predicate(r):
            out[r['qb_uuid']] = r
    return out

old_auto = auto_set(lambda r: r['name_ok'])
naive_auto = auto_set(lambda r: r['name_ok'] or r['link_domain_match'])
varA_auto = auto_set(lambda r: r['name_ok'] or r['qb_domain_match'])

naive_additional = {u: r for u, r in naive_auto.items() if u not in old_auto}   # the 333 FPs
varA_additional = {u: r for u, r in varA_auto.items() if u not in old_auto}

# Variant B threshold sweep
varB = {}
for T in (1, 2, 3, 5):
    a = auto_set(lambda r, T=T: r['name_ok'] or (r['link_domain_match'] and 0 < r['link_prom'] <= T))
    add = {u: rr for u, rr in a.items() if u not in old_auto}
    varB[T] = {'auto': a, 'additional': add}

def rev(d):
    return sum(qb_rev[u] for u in d)

print(f"  old gate (name only) auto:      {len(old_auto):>5}  ${rev(old_auto):>13,.0f}")
print(f"  naive linking-domain auto:      {len(naive_auto):>5}  ${rev(naive_auto):>13,.0f}  (+{len(naive_additional)} FPs)")
print(f"  variant A (QB contact domain):  {len(varA_auto):>5}  ${rev(varA_auto):>13,.0f}  (+{len(varA_additional)})")
for T in (1, 2, 3, 5):
    a = varB[T]['auto']; add = varB[T]['additional']
    print(f"  variant B (promiscuity<= {T}):    {len(a):>5}  ${rev(a):>13,.0f}  (+{len(add)})")

# ── How does each variant treat the 333 naive false-positives? ────────
print("\n[5/6] How each variant handles the naive additions...")
naive_ids = set(naive_additional)
varA_keep = naive_ids & set(varA_additional)
print(f"  naive additions (suspected mostly broker FPs): {len(naive_ids)}")
print(f"    variant A keeps:    {len(varA_keep):>4}  rejects: {len(naive_ids - varA_keep):>4}")
for T in (1, 2, 3, 5):
    keep = naive_ids & set(varB[T]['additional'])
    print(f"    variant B(<= {T}) keeps: {len(keep):>4}  rejects: {len(naive_ids - keep):>4}")

# Promiscuity distribution of the naive additions' linking root
prom_hist = defaultdict(int)
for u, r in naive_additional.items():
    p = r['link_prom']
    bucket = '1' if p == 1 else '2' if p == 2 else '3-5' if p <= 5 else '6-20' if p <= 20 else '20+'
    prom_hist[bucket] += 1
print(f"  Linking-root promiscuity of the {len(naive_additional)} naive additions:")
for b in ('1', '2', '3-5', '6-20', '20+'):
    print(f"    links to {b:<5} QB customers: {prom_hist.get(b,0):>4}")

# ── Samples to eyeball ────────────────────────────────────────────────
print("\n[6/6] Samples (verify same company)...")

print(f"\n  Variant A additions ({len(varA_additional)}) — top by revenue:")
print(f"    {'SB company':<30}{'QB customer':<30}{'qb root':<16}{'revenue':>11}")
print(f"    {'-'*86}")
for r in sorted(varA_additional.values(), key=lambda x: -x['revenue'])[:20]:
    print(f"    {r['sb_name'][:29]:<30}{r['qb_name'][:29]:<30}{(r['qb_root'] or '?'):<16}${r['revenue']:>10,.0f}")

b1 = varB[1]['additional']
print(f"\n  Variant B(promiscuity==1) additions ({len(b1)}) — top by revenue:")
print(f"    {'SB company':<30}{'QB customer':<30}{'root':<16}{'revenue':>11}")
print(f"    {'-'*86}")
for r in sorted(b1.values(), key=lambda x: -x['revenue'])[:20]:
    print(f"    {r['sb_name'][:29]:<30}{r['qb_name'][:29]:<30}{(r['link_root'] or '?'):<16}${r['revenue']:>10,.0f}")

# ── JSON ──────────────────────────────────────────────────────────────
def recs(d):
    return [
        {'sb_name': r['sb_name'], 'qb_name': r['qb_name'],
         'link_root': r['link_root'], 'link_prom': r['link_prom'],
         'qb_root': r['qb_root'], 'revenue': r['revenue']}
        for r in sorted(d.values(), key=lambda x: -x['revenue'])
    ]

out = {
    'params': {
        'client_id': CLIENT_ID,
        'total_qb_customers': len(qb_customers),
        'total_qb_revenue': total_qb_revenue,
        'current_matched_count': len(current_matches),
        'current_matched_revenue': current_revenue,
    },
    'gates': {
        'old_name_only': {'count': len(old_auto), 'revenue': rev(old_auto)},
        'naive_linking_domain': {'count': len(naive_auto), 'revenue': rev(naive_auto),
                                 'additional': len(naive_additional), 'additional_revenue': rev(naive_additional)},
        'variant_A_qb_contact_domain': {'count': len(varA_auto), 'revenue': rev(varA_auto),
                                        'additional': len(varA_additional), 'additional_revenue': rev(varA_additional)},
        'variant_B_promiscuity': {
            str(T): {'count': len(varB[T]['auto']), 'revenue': rev(varB[T]['auto']),
                     'additional': len(varB[T]['additional']), 'additional_revenue': rev(varB[T]['additional'])}
            for T in (1, 2, 3, 5)
        },
    },
    'naive_fp_handling': {
        'naive_additions': len(naive_ids),
        'variant_A_keeps': len(varA_keep),
        'variant_B_keeps': {str(T): len(naive_ids & set(varB[T]['additional'])) for T in (1, 2, 3, 5)},
        'naive_addition_promiscuity_hist': dict(prom_hist),
    },
    'variant_A_additions': recs(varA_additional),
    'variant_B1_additions': recs(b1),
}
out_path = os.path.join(os.path.dirname(__file__), 'qbdomain_sim.json')
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(out, f, indent=2, default=str)
print(f"\n  Wrote {out_path}")
print("\nDone! Read-only simulation. No data was changed.")
