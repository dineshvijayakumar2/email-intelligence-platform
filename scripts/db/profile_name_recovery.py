"""
Read-only profile of the staged-for-review match candidates (qb_match_candidates,
reviewed=False) to size how many are auto-promotable via name normalization vs
need human review.

Unit of analysis = the SB company (1,306 distinct companies across 2,092
unreviewed candidate rows). For each SB company we look at its suggested QB
customer name(s) and classify:

  suffix_only        match after stripping legal suffixes (Pty Ltd, Ltd, Limited,
                     Inc, LLC, Co, Group) + normalising punctuation/whitespace/case.
                     -> auto-promotable.
  punctuation_abbrev match after &/and normalisation + common abbreviation
                     expansion + punctuation removal. -> likely auto-promotable,
                     lower confidence.
  fuzzy_close        rapidfuzz token_sort_ratio >= 90 but not mechanical.
                     -> manual confirm, easy.
  genuine_different  low similarity, OR the SB company suggests >1 distinct QB
                     name (ambiguous). -> human review required.
  no_suggestion      no QB candidate at all. -> name/fuzzy passes or manual.

Any SB company that maps to >1 distinct QB customer is forced to genuine_different
and is NEVER auto-promotable, even if one candidate normalises cleanly. Those are
flagged separately so they can be excluded from any auto-promotion.

Run with the backend venv (has rapidfuzz):
  backend/venv/Scripts/python.exe scripts/db/profile_name_recovery.py

Read-only. Changes no data. Writes name_recovery_profile.json.
"""
import os, sys, re, json
from collections import defaultdict
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

# Legal suffix tokens (per spec): Pty Ltd, Ltd, Limited, Inc, LLC, Co, Group
LEGAL_SUFFIXES = frozenset({
    'pty', 'ltd', 'limited', 'inc', 'llc', 'co', 'group',
})

# Conservative, well-known abbreviation expansions (lower-confidence bucket only)
ABBREV = {
    'intl': 'international', 'int': 'international',
    'aust': 'australia', 'aus': 'australia',
    'mgmt': 'management', 'mngmt': 'management',
    'assoc': 'associates', 'assocs': 'associates',
    'svcs': 'services', 'svc': 'services',
    'grp': 'group',
    'dept': 'department',
    'natl': 'national', 'nat': 'national',
    'corp': 'corporation',
    'mfg': 'manufacturing',
    'dist': 'distribution',
    'aust.': 'australia',
}

FUZZY_THRESHOLD = 90

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


def norm_basic(s):
    """lowercase, punctuation -> space, collapse whitespace."""
    s = (s or '').lower()
    s = re.sub(r'[^a-z0-9]+', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def strip_suffix_tokens(tokens):
    out = [t for t in tokens if t not in LEGAL_SUFFIXES]
    return out if out else tokens  # never strip to empty


def key_suffix(s):
    """Suffix-stripped, despaced key for suffix_only comparison."""
    toks = strip_suffix_tokens(norm_basic(s).split())
    return ''.join(toks)


def key_abbrev(s):
    """&/and + abbreviation-expanded + suffix-stripped despaced key."""
    s = (s or '').lower().replace('&', ' and ')
    s = re.sub(r'[^a-z0-9]+', ' ', s)
    toks = [ABBREV.get(t, t) for t in s.split()]
    toks = strip_suffix_tokens(toks)
    return ''.join(toks)


# ── Load ──────────────────────────────────────────────────────────────
print("=" * 78)
print("  NAME-RECOVERY PROFILE — staged candidates (reviewed=False, read-only)")
print("=" * 78)

print("\n[1/4] Loading candidates + QB revenue...")
cands = fetch_all('qb_match_candidates',
    'id, sb_company_id, sb_company_name, qb_record_id, qb_customer_id, qb_name, match_score, match_method',
    [lambda q: q.eq('reviewed', False)])

qb_customers = fetch_all('qb_customers', 'qb_record_id, customer_key_id, total_invoiced')
rev_by_record = {}
for qc in qb_customers:
    rid = qc.get('qb_record_id')
    if rid is not None:
        rev_by_record[str(rid)] = float(qc.get('total_invoiced') or 0)

def cand_rev(c):
    for key in (c.get('qb_record_id'), c.get('qb_customer_id')):
        if key is not None and str(key) in rev_by_record:
            return rev_by_record[str(key)]
    return 0.0

print(f"  unreviewed candidates: {len(cands)}")
print(f"  distinct SB companies: {len({c['sb_company_id'] for c in cands})}")

# ── Group by SB company ───────────────────────────────────────────────
print("\n[2/4] Grouping by SB company + classifying...")
by_company = defaultdict(list)
for c in cands:
    by_company[c['sb_company_id']].append(c)


def classify_pair(sb_name, qb_name):
    """Return (bucket, detail-dict) for a single sb<->qb name pair."""
    ks_sb, ks_qb = key_suffix(sb_name), key_suffix(qb_name)
    if ks_sb and ks_qb and ks_sb == ks_qb:
        return 'suffix_only', {'norm_sb': ks_sb, 'norm_qb': ks_qb}
    ka_sb, ka_qb = key_abbrev(sb_name), key_abbrev(qb_name)
    if ka_sb and ka_qb and ka_sb == ka_qb:
        return 'punctuation_abbrev', {'norm_sb': ka_sb, 'norm_qb': ka_qb}
    score = fuzz.token_sort_ratio(norm_basic(sb_name), norm_basic(qb_name))
    if score >= FUZZY_THRESHOLD:
        return 'fuzzy_close', {'ratio': round(score, 1)}
    return 'genuine_different', {'ratio': round(score, 1)}


buckets = defaultdict(list)          # bucket -> list of result dicts (one per SB company)
ambiguous_flag = []                  # multi-QB SB companies that HAD a mechanical match

for sb_company_id, rows in by_company.items():
    sb_name = rows[0].get('sb_company_name') or '?'
    distinct_qb = {}                 # normalized qb_name -> representative row
    for r in rows:
        qn = (r.get('qb_name') or '').strip()
        if not qn:
            continue
        k = norm_basic(qn)
        if k not in distinct_qb or (r.get('match_score') or 0) > (distinct_qb[k].get('match_score') or 0):
            distinct_qb[k] = r

    n_distinct = len(distinct_qb)
    company_rev = sum({str(r.get('qb_record_id')): cand_rev(r) for r in distinct_qb.values()}.values())

    if n_distinct == 0:
        buckets['no_suggestion'].append({
            'sb_company_id': sb_company_id, 'sb_name': sb_name,
            'qb_name': None, 'n_qb': 0, 'revenue': 0.0,
        })
        continue

    if n_distinct > 1:
        # Ambiguous -> human review. But check if any candidate WOULD have been
        # mechanically promotable, to flag it explicitly.
        mech = []
        for r in distinct_qb.values():
            b, d = classify_pair(sb_name, r.get('qb_name'))
            if b in ('suffix_only', 'punctuation_abbrev'):
                mech.append({'qb_name': r.get('qb_name'), 'bucket': b, **d})
        rec = {
            'sb_company_id': sb_company_id, 'sb_name': sb_name,
            'qb_names': [r.get('qb_name') for r in distinct_qb.values()],
            'n_qb': n_distinct, 'revenue': company_rev,
            'reason': 'multi_qb_ambiguous',
        }
        buckets['genuine_different'].append(rec)
        if mech:
            ambiguous_flag.append({**rec, 'mechanical_candidates': mech})
        continue

    # Exactly one distinct QB suggestion
    r = next(iter(distinct_qb.values()))
    qb_name = r.get('qb_name')
    bucket, detail = classify_pair(sb_name, qb_name)
    buckets[bucket].append({
        'sb_company_id': sb_company_id, 'sb_name': sb_name, 'qb_name': qb_name,
        'n_qb': 1, 'revenue': company_rev, 'match_method': r.get('match_method'),
        'match_score': r.get('match_score'), **detail,
    })

# ── Report ────────────────────────────────────────────────────────────
print("\n[3/4] Bucket summary...")
ORDER = ['suffix_only', 'punctuation_abbrev', 'fuzzy_close', 'genuine_different', 'no_suggestion']
LABEL = {
    'suffix_only': 'suffix_only        (auto-promotable)',
    'punctuation_abbrev': 'punctuation_abbrev (auto, lower-conf)',
    'fuzzy_close': 'fuzzy_close        (manual, easy)',
    'genuine_different': 'genuine_different  (human review)',
    'no_suggestion': 'no_suggestion      (name/fuzzy/manual)',
}

total_n = total_rev = 0
print(f"\n  {'bucket':<40}{'companies':>10}{'revenue':>16}")
print(f"  {'-'*66}")
for b in ORDER:
    items = buckets.get(b, [])
    n = len(items)
    rv = sum(x['revenue'] for x in items)
    total_n += n
    total_rev += rv
    print(f"  {LABEL[b]:<40}{n:>10}${rv:>14,.0f}")
print(f"  {'-'*66}")
print(f"  {'TOTAL SB companies':<40}{total_n:>10}${total_rev:>14,.0f}")

auto_n = len(buckets['suffix_only']) + len(buckets['punctuation_abbrev'])
auto_rev = sum(x['revenue'] for x in buckets['suffix_only']) + sum(x['revenue'] for x in buckets['punctuation_abbrev'])
print(f"\n  Auto-promotable (suffix_only + punctuation_abbrev): {auto_n} companies, ${auto_rev:,.0f}")
print(f"  Ambiguous multi-QB companies with a tempting mechanical match (DO NOT auto-promote): {len(ambiguous_flag)}")

# ── Samples ───────────────────────────────────────────────────────────
print("\n[4/4] Samples for verification...")

def print_sample(bucket, title):
    items = sorted(buckets[bucket], key=lambda x: -x['revenue'])[:25]
    print(f"\n  {title} — top 25 by revenue:")
    print(f"    {'sb_name':<30}{'qb_name':<30}{'norm_sb':<20}{'norm_qb':<20}{'rev':>10}")
    print(f"    {'-'*108}")
    for x in items:
        print(f"    {(x['sb_name'] or '')[:29]:<30}{(x['qb_name'] or '')[:29]:<30}"
              f"{(x.get('norm_sb') or '')[:19]:<20}{(x.get('norm_qb') or '')[:19]:<20}${x['revenue']:>9,.0f}")

print_sample('suffix_only', 'BUCKET 1: suffix_only')
print_sample('punctuation_abbrev', 'BUCKET 2: punctuation_abbrev')

# ── Write JSON ────────────────────────────────────────────────────────
out = {
    'params': {
        'client_id': CLIENT_ID,
        'source': 'qb_match_candidates (reviewed=False)',
        'unreviewed_candidate_rows': len(cands),
        'distinct_sb_companies': total_n,
        'fuzzy_threshold': FUZZY_THRESHOLD,
        'legal_suffixes': sorted(LEGAL_SUFFIXES),
        'abbreviations': ABBREV,
    },
    'buckets': {
        b: {
            'count': len(buckets.get(b, [])),
            'revenue': sum(x['revenue'] for x in buckets.get(b, [])),
            'companies': sorted(buckets.get(b, []), key=lambda x: -x['revenue']),
        }
        for b in ORDER
    },
    'auto_promotable': {'count': auto_n, 'revenue': auto_rev},
    'ambiguous_multi_qb_with_mechanical_match': ambiguous_flag,
}
out_path = os.path.join(os.path.dirname(__file__), 'name_recovery_profile.json')
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(out, f, indent=2, default=str)
print(f"\n  Wrote {out_path}")
print("\nDone! Read-only profile. No data was changed.")
