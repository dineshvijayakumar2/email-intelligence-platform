"""
Read-only profile of the 582 ambiguous multi-QB staged SB companies
(qb_match_candidates, reviewed=False, where the SB company suggests >1 distinct
QB customer name). Goal: separate brokers (legitimately multi-customer) from
genuine single-company ambiguity, and size what a human review queue faces.

Per SB company:
  - Multi-customer spread: # distinct QB customers + via which method(s)
    (email_multi_match / domain_root / fuzzy). Distribution 2 / 3-5 / 6-10 / 10+.
  - Broker signal: do the linked QB customers share a name family (parent+subs =
    really one company) or are they unrelated (broker/agency serving many clients)?
      likely_broker      many / unrelated QB customers, or SB domain on the
                         flagged broker list (broker_split.json, spread>=3).
      likely_one_company few, name-related QB customers.
      unclear            in between.
  - Revenue concentration (likely_one_company + unclear): does one QB customer
    hold >70% of revenue (easy human confirm) or is it spread (hard)?
  - Cross-ref the flagged broker domains from the earlier link analysis.

Run with the backend venv (rapidfuzz):
  backend/venv/Scripts/python.exe scripts/db/profile_ambiguous_582.py

Read-only. Changes no data. Writes ambiguous_582_profile.json.
"""
import os, sys, re, json, itertools
from collections import defaultdict, Counter
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
from dotenv import load_dotenv
from supabase import create_client
from rapidfuzz import fuzz

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
load_dotenv(env_path)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
CLIENT_ID = "241d7b99-f099-4557-96e5-212c4af10812"

LEGAL_SUFFIXES = frozenset({'pty', 'ltd', 'limited', 'inc', 'llc', 'co', 'group'})
# Tokens too generic to imply a shared corporate family. A QB-name cluster that
# only shares one of these (e.g. "X Digital" / "Y Digital") is NOT one company.
GENERIC_TOKENS = LEGAL_SUFFIXES | frozenset({
    'the', 'and', 'australia', 'aust', 'australian', 'company', 'holdings',
    'services', 'service', 'solutions', 'global', 'international', 'group', 'au',
    'pty', 'enterprises', 'digital', 'creative', 'marketing', 'media', 'brand',
    'branding', 'studio', 'studios', 'design', 'designs', 'print', 'printing',
    'agency', 'national', 'consulting', 'partners', 'management', 'communications',
    'productions', 'production', 'technologies', 'technology', 'capital',
    'advisory', 'finance', 'systems', 'property', 'group', 'projects', 'project',
    'industries', 'australasia', 'sydney', 'melbourne', 'brisbane', 'perth',
})
GENERIC_DOMAINS = frozenset({
    'gmail.com', 'hotmail.com', 'yahoo.com', 'outlook.com', 'icloud.com',
    'bigpond.com', 'me.com', 'hotmail.com.au', 'yahoo.com.au', 'live.com',
    'live.com.au', 'msn.com', 'aol.com', 'mail.com', 'protonmail.com', 'zoho.com',
})

def norm_basic(s):
    s = (s or '').lower()
    s = re.sub(r'[^a-z0-9]+', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()

def core_tokens(s):
    return [t for t in norm_basic(s).split() if t not in GENERIC_TOKENS and len(t) >= 3]

def fetch_all(table, select, filters=None):
    rows, offset = [], 0
    while True:
        q = sb.table(table).select(select).eq('client_id', CLIENT_ID)
        if filters:
            for f in filters:
                q = f(q)
        batch = q.range(offset, offset + 999).execute().data or []
        rows.extend(batch)
        if not batch:
            break
        offset += len(batch)
    return rows

def extract_full_domains(email_domains):
    if isinstance(email_domains, list):
        domains = email_domains
    else:
        domains = re.findall(r'[\w.-]+\.\w+', str(email_domains or ''))
    out = []
    for d in domains:
        dl = d.lower().strip()
        if dl and dl not in GENERIC_DOMAINS:
            out.append(dl)
    return out


# ── Flagged broker domains from the earlier link analysis ─────────────
bp = os.path.join(os.path.dirname(__file__), 'broker_split.json')
broker_doc = json.load(open(bp, encoding='utf-8'))
dr = broker_doc.get('domain_ranking', [])
flagged_all = {e['domain'].lower() for e in dr}
flagged_high = {e['domain'].lower() for e in dr if e['distinct_quote_customers'] >= 3}
flagged_spread = {e['domain'].lower(): e['distinct_quote_customers'] for e in dr}

print("=" * 80)
print("  AMBIGUOUS MULTI-QB PROFILE — 582 staged companies (read-only)")
print("=" * 80)
print(f"\n  Flagged broker domains loaded: {len(flagged_all)} total, {len(flagged_high)} with spread>=3")

# ── Load ──────────────────────────────────────────────────────────────
print("\n[1/5] Loading candidates, companies, QB revenue...")
cands = fetch_all('qb_match_candidates',
    'sb_company_id, sb_company_name, qb_record_id, qb_customer_id, qb_name, match_method, match_score',
    [lambda q: q.eq('reviewed', False)])
sb_companies = fetch_all('customer_companies', 'id, company_name, email_domains')
qb_customers = fetch_all('qb_customers', 'qb_record_id, total_invoiced')

sb_domains_by_id = {c['id']: extract_full_domains(c.get('email_domains')) for c in sb_companies}
sb_name_by_id = {c['id']: c.get('company_name') for c in sb_companies}
rev_by_record = {str(qc['qb_record_id']): float(qc.get('total_invoiced') or 0)
                 for qc in qb_customers if qc.get('qb_record_id') is not None}

by_company = defaultdict(list)
for c in cands:
    by_company[c['sb_company_id']].append(c)

# ── Select the 582 multi-QB companies (>1 distinct normalized qb_name) ─
print("\n[2/5] Selecting multi-QB companies...")
multi = {}
for cid, rows in by_company.items():
    names = {norm_basic(r.get('qb_name')) for r in rows if (r.get('qb_name') or '').strip()}
    if len(names) > 1:
        multi[cid] = rows
print(f"  multi-QB companies: {len(multi)}")


def distinct_qb(rows):
    """dict qb_record_id -> {name, revenue, methods}."""
    out = {}
    for r in rows:
        rid = str(r.get('qb_record_id'))
        if rid not in out:
            out[rid] = {'name': r.get('qb_name'), 'revenue': rev_by_record.get(rid, 0.0),
                        'methods': set()}
        out[rid]['methods'].add(r.get('match_method'))
    return out


def single_family(names):
    """True if all QB names plausibly belong to one corporate brand family.
    Requires a shared *distinctive* brand identity, not just a shared industry
    word — "Acme Sydney"/"Acme Pty" is family; "X Digital"/"Y Digital" is not."""
    names = [n for n in names if n]
    if len(names) <= 1:
        return True
    cores = [core_tokens(n) for n in names]
    # (a) shared distinctive LEADING brand token across ALL names
    leads = [c[0] for c in cores if c]
    if len(leads) == len(names) and len({l for l in leads}) == 1 and len(leads[0]) >= 4:
        return True
    # (b) substring containment chain on the distinctive core (drop generics)
    cores_joined = [''.join(c) for c in cores]
    if all(cores_joined):
        base = min(cores_joined, key=len)
        if len(base) >= 4 and all(base in x or x in base for x in cores_joined):
            return True
    # (c) all pairwise token_set_ratio very high -> tight single cluster
    for a, b in itertools.combinations(names, 2):
        if fuzz.token_set_ratio(norm_basic(a), norm_basic(b)) < 88:
            return False
    return True


def is_fragment_name(sb_name):
    """A junk/partial SB record: a single token that is generic or very short.
    These fuzzy/domain-match to many unrelated QB customers (not a real broker)."""
    toks = norm_basic(sb_name).split()
    if len(toks) == 1 and (toks[0] in GENERIC_TOKENS or len(toks[0]) <= 4):
        return True
    return False


# ── Classify ──────────────────────────────────────────────────────────
print("\n[3/5] Classifying broker vs one-company...")
results = []
for cid, rows in multi.items():
    sb_name = sb_name_by_id.get(cid) or rows[0].get('sb_company_name') or '?'
    qbs = distinct_qb(rows)
    n_qb = len(qbs)
    qb_names = [v['name'] for v in qbs.values()]
    total_rev = sum(v['revenue'] for v in qbs.values())
    methods = set()
    for v in qbs.values():
        methods |= v['methods']
    has_email = 'email_multi_match' in methods

    sb_doms = sb_domains_by_id.get(cid, [])
    on_flag_high = [d for d in sb_doms if d in flagged_high]
    on_flag_any = [d for d in sb_doms if d in flagged_all]

    related = single_family(qb_names)
    fragment = is_fragment_name(sb_name)

    if on_flag_high:
        bucket = 'likely_broker'; reason = f'SB domain on flagged broker list ({on_flag_high[0]})'
    elif related:
        bucket = 'likely_one_company'; reason = 'QB names share a brand family'
    elif n_qb >= 6:
        bucket = 'likely_broker'; reason = f'{n_qb} unrelated QB customers'
    elif n_qb >= 3:
        bucket = 'likely_broker'; reason = f'{n_qb} unrelated QB customers'
    else:  # n_qb == 2, unrelated
        bucket = 'unclear'; reason = '2 unrelated QB customers'

    # Within likely_broker, distinguish a genuine broker (shared mailbox/domain
    # links many real customers) from a junk fragment SB name that domain/fuzzy
    # matched many unrelated customers.
    broker_kind = None
    if bucket == 'likely_broker':
        if has_email or on_flag_any:
            broker_kind = 'genuine_broker_signal'
        elif fragment:
            broker_kind = 'name_fragment_noise'
        else:
            broker_kind = 'other_unrelated'

    # revenue concentration (dominant >70%)
    if total_rev > 0:
        top = max(v['revenue'] for v in qbs.values())
        dom_frac = top / total_rev
        conc = 'dominant' if dom_frac > 0.70 else 'spread'
    else:
        dom_frac = 0.0
        conc = 'no_revenue'

    results.append({
        'sb_company_id': cid, 'sb_name': sb_name, 'n_qb': n_qb,
        'qb_names': qb_names, 'revenue': total_rev, 'methods': sorted(methods),
        'bucket': bucket, 'broker_kind': broker_kind, 'reason': reason,
        'related': related, 'fragment': fragment,
        'concentration': conc, 'dominant_frac': round(dom_frac, 3),
        'sb_domains': sb_doms, 'on_flagged_broker': on_flag_any,
        'on_flagged_broker_high': on_flag_high,
    })

# ── Aggregate ─────────────────────────────────────────────────────────
print("\n[4/5] Aggregating...")

def spread_band(n):
    return '2' if n == 2 else '3-5' if n <= 5 else '6-10' if n <= 10 else '10+'

spread_dist = Counter(spread_band(r['n_qb']) for r in results)
spread_rev = defaultdict(float)
for r in results:
    spread_rev[spread_band(r['n_qb'])] += r['revenue']

method_dist = Counter()
for r in results:
    key = '+'.join(r['methods']) if len(r['methods']) > 1 else (r['methods'][0] if r['methods'] else 'none')
    method_dist[key] += 1

bucket_rev = defaultdict(float)
bucket_n = Counter()
for r in results:
    bucket_n[r['bucket']] += 1
    bucket_rev[r['bucket']] += r['revenue']

# Concentration within one_company + unclear
conc_n = Counter()
conc_rev = defaultdict(float)
for r in results:
    if r['bucket'] in ('likely_one_company', 'unclear'):
        conc_n[r['concentration']] += 1
        conc_rev[r['concentration']] += r['revenue']

# Cross-ref broker domains
broker_results = [r for r in results if r['bucket'] == 'likely_broker']
broker_on_flag = [r for r in broker_results if r['on_flagged_broker_high']]
broker_on_flag_any = [r for r in broker_results if r['on_flagged_broker']]

# ── Report ────────────────────────────────────────────────────────────
print(f"\n{'='*80}")
print("  RESULTS")
print(f"{'='*80}")

print(f"\n  Spread distribution (QB customers per SB company):")
print(f"    {'band':<8}{'companies':>10}{'revenue':>16}")
for b in ('2', '3-5', '6-10', '10+'):
    print(f"    {b:<8}{spread_dist.get(b,0):>10}${spread_rev.get(b,0):>14,.0f}")

print(f"\n  Linking method mix (per company):")
for k, v in method_dist.most_common():
    print(f"    {k:<40}{v:>6}")

print(f"\n  Broker-vs-one-company buckets:")
print(f"    {'bucket':<22}{'companies':>10}{'revenue':>16}")
for b in ('likely_broker', 'likely_one_company', 'unclear'):
    print(f"    {b:<22}{bucket_n.get(b,0):>10}${bucket_rev.get(b,0):>14,.0f}")
print(f"    {'TOTAL':<22}{len(results):>10}${sum(bucket_rev.values()):>14,.0f}")

broker_kind_n = Counter(r['broker_kind'] for r in results if r['bucket'] == 'likely_broker')
print(f"\n  likely_broker texture (is it a real broker, or a junk fragment SB name?):")
print(f"    genuine_broker_signal (shared mailbox/flagged domain): {broker_kind_n.get('genuine_broker_signal',0)}")
print(f"    name_fragment_noise   (single junk SB token, no email): {broker_kind_n.get('name_fragment_noise',0)}")
print(f"    other_unrelated       (3+ unrelated, no email/domain):  {broker_kind_n.get('other_unrelated',0)}")

print(f"\n  Revenue concentration (likely_one_company + unclear, {conc_n.total() if hasattr(conc_n,'total') else sum(conc_n.values())} companies):")
print(f"    {'>70% dominant (easy)':<24}{conc_n.get('dominant',0):>6}  ${conc_rev.get('dominant',0):,.0f}")
print(f"    {'spread (hard)':<24}{conc_n.get('spread',0):>6}  ${conc_rev.get('spread',0):,.0f}")
print(f"    {'no revenue (undet.)':<24}{conc_n.get('no_revenue',0):>6}  ${conc_rev.get('no_revenue',0):,.0f}")

print(f"\n  Cross-ref flagged broker domains (broker_split.json):")
print(f"    likely_broker companies: {len(broker_results)}")
print(f"    ...whose SB domain is on the flagged HIGH list (spread>=3): {len(broker_on_flag)}")
print(f"    ...whose SB domain is on the flagged ANY list:             {len(broker_on_flag_any)}")
if broker_on_flag:
    print(f"    matched flagged-high domains:")
    for r in sorted(broker_on_flag, key=lambda x: -x['n_qb'])[:20]:
        print(f"      {r['sb_name'][:34]:<35} domain={r['on_flagged_broker_high'][0]:<30} n_qb={r['n_qb']}")

# ── Samples ───────────────────────────────────────────────────────────
print("\n[5/5] Samples...")

def print_sample(bucket, title, n=15):
    items = sorted([r for r in results if r['bucket'] == bucket], key=lambda x: -x['n_qb'])[:n]
    print(f"\n  {title} — {n} samples (sorted by # QB customers):")
    for r in items:
        names = ', '.join((nm or '?')[:24] for nm in r['qb_names'][:6])
        more = '' if len(r['qb_names']) <= 6 else f" (+{len(r['qb_names'])-6} more)"
        flag = '  [FLAGGED]' if r['on_flagged_broker'] else ''
        meth = ','.join(m.replace('email_multi_match', 'email').replace('domain_root', 'domain') for m in r['methods'])
        kind = f" {r['broker_kind']}" if r.get('broker_kind') else ''
        print(f"    {r['sb_name'][:30]:<31} n={r['n_qb']:>2} ${r['revenue']:>10,.0f}  [{meth}]{kind}{flag}")
        print(f"        QB: {names}{more}")

print_sample('likely_broker', 'LIKELY_BROKER')
print_sample('likely_one_company', 'LIKELY_ONE_COMPANY')

# ── JSON ──────────────────────────────────────────────────────────────
def clean(r):
    return {k: v for k, v in r.items()}

out = {
    'params': {
        'client_id': CLIENT_ID,
        'source': 'qb_match_candidates reviewed=False, multi-QB subset',
        'multi_qb_companies': len(results),
        'broker_domains_flagged_total': len(flagged_all),
        'broker_domains_flagged_high': len(flagged_high),
    },
    'spread_distribution': {b: {'count': spread_dist.get(b, 0), 'revenue': spread_rev.get(b, 0)}
                            for b in ('2', '3-5', '6-10', '10+')},
    'method_mix': dict(method_dist),
    'buckets': {b: {'count': bucket_n.get(b, 0), 'revenue': bucket_rev.get(b, 0)}
                for b in ('likely_broker', 'likely_one_company', 'unclear')},
    'revenue_concentration_one_company_and_unclear': {
        'dominant_gt70': {'count': conc_n.get('dominant', 0), 'revenue': conc_rev.get('dominant', 0)},
        'spread': {'count': conc_n.get('spread', 0), 'revenue': conc_rev.get('spread', 0)},
        'no_revenue': {'count': conc_n.get('no_revenue', 0), 'revenue': conc_rev.get('no_revenue', 0)},
    },
    'broker_domain_crossref': {
        'likely_broker_companies': len(broker_results),
        'on_flagged_high': len(broker_on_flag),
        'on_flagged_any': len(broker_on_flag_any),
        'matched_domains': sorted({d for r in broker_on_flag_any for d in r['on_flagged_broker']}),
    },
    'companies': sorted([clean(r) for r in results], key=lambda x: (x['bucket'], -x['n_qb'])),
}
out_path = os.path.join(os.path.dirname(__file__), 'ambiguous_582_profile.json')
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(out, f, indent=2, default=str)
print(f"\n  Wrote {out_path}")
print("\nDone! Read-only profile. No data was changed.")
