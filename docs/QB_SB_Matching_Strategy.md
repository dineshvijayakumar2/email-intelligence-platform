# QB ↔ Supabase Customer Matching — Technical Implementation Strategy

---

## 1. Current State

| Metric | Value |
|---|---|
| QB companies | 2,407 |
| Supabase `customer_companies` rows | 11,559 |
| SB rows with **any** `qb_` field populated | 546 |
| SB rows where `qb_customer_type` is populated | **0** |
| SB rows where `qb_growth_90d` is populated | **0** |
| QB companies with an exact name match in SB | 864 (36%) |
| SB rows with a non-generic, matchable email domain | 8,280 |
| SB rows with only generic domains (gmail, hotmail…) | 3,279 |

### What the 546 "partial" rows actually contain

These rows were written by an earlier sync attempt. They have `qb_account_manager`, `qb_tier`, and `qb_days_since_last_invoice` set, but `qb_customer_type`, `qb_growth_90d`, `qb_invoiced_ty`, and `qb_invoiced_ly` are mostly blank. This means the sync ran but mapped only a subset of fields — the pipeline is **incomplete, not absent**.

### What the analytics service expects

`CustomerAnalyticsService` queries `customer_intelligence_cache` keyed on `company_id`, which is the Supabase UUID. Every feature (strike rate, contact capabilities, seasonality, capability rhythm) fans out from that UUID via `matched_company_id` on `qb_quotes` and `qb_operations`. If a Supabase company row is not linked to the correct QB customer, all four analytics features silently return empty results for that company.

---

## 2. Data Gap Analysis

### QB fields that need to sync into Supabase

| QB source column | SB target column | Transform needed |
|---|---|---|
| `Name*` | — | Used only for matching |
| `Customer ID (key)` | (no SB column exists yet — see §4) | Store as `qb_customer_id` |
| `Code*` | (no SB column exists yet) | Store as `qb_customer_code` |
| `Invoiced Line Items $ TY` | `qb_invoiced_ty` | Strip `$` and commas → numeric |
| `Invoiced Line Items $ Y-1` | `qb_invoiced_ly` | Strip `$` and commas → numeric |
| `Total Invoiced Line Item $` | `qb_total_revenue` | Strip `$` and commas → numeric |
| `account Manager` | `qb_account_manager` | Direct string copy |
| `Recency.` | `qb_days_since_last_invoice` | Parse integer from HTML div (e.g. `8 d` → `8`) |
| `Product Group(s)` | `qb_customer_type` | Semicolon-delimited → array or primary tag |
| *(derived)* | `qb_growth_90d` | `(TY − LY) / LY × 100` rounded to 1 dp |
| *(derived)* | `qb_tier` | Revenue band logic (see §3) |

### The Recency field is HTML-wrapped

QB exports the recency as `<div style="background-color:#CCFFCC;">8 d</div>`. The integer must be extracted with a regex before writing to `qb_days_since_last_invoice`.

```python
import re
def parse_recency(html: str) -> int | None:
    m = re.search(r'(\d+)\s*d', html or '')
    return int(m.group(1)) if m else None
```

---

## 3. Matching Strategy — Three-Pass Pipeline

The core problem is that Supabase companies are **derived from email domains**, not imported from QB, so there is no shared key. Matching must be inferred. A three-pass approach maximises coverage while controlling false-positive risk.

### Pass 1 — Exact normalised name match *(~864 companies, high confidence)*

Normalise both sides: lowercase, strip all non-alphanumeric characters. Match on equality.

```python
def normalise(name: str) -> str:
    return re.sub(r'[^a-z0-9]', '', name.lower())

# Build QB lookup once
qb_lookup = {normalise(r['Name*']): r for r in qb_rows}

# For each SB company
sb_norm = normalise(sb_row['company_name'])
if sb_norm in qb_lookup:
    # → high-confidence match, write all qb_ fields
```

**Confidence:** HIGH. Write directly. No human review needed.

---

### Pass 2 — Email domain root match *(~200–400 additional companies, medium confidence)*

Extract the second-level domain from the SB `email_domains` array (e.g. `thepropertyagency.com.au` → `thepropertyagency`). Check whether this root string appears as a substring of any normalised QB name. Skip generic domains entirely.

```python
GENERIC_DOMAINS = {
    'gmail.com', 'hotmail.com', 'yahoo.com', 'outlook.com',
    'icloud.com', 'bigpond.com', 'me.com', 'hotmail.com.au',
}

def extract_domain_roots(domain_json: str) -> list[str]:
    domains = re.findall(r'[\w.-]+\.\w+', domain_json)
    roots = []
    for d in domains:
        if d in GENERIC_DOMAINS:
            continue
        parts = d.lower().split('.')
        root = parts[-2] if len(parts) >= 2 else parts[0]
        if len(root) >= 5:   # avoid short tokens ('app', 'con', 'us')
            roots.append(root)
    return roots

# Match
for root in extract_domain_roots(sb_row['email_domains']):
    for qb_norm_name, qb_row in qb_lookup.items():
        if root in qb_norm_name:
            # → medium-confidence match
```

**Confidence:** MEDIUM. Write all `qb_` fields but set a `match_method = 'domain_root'` flag so these can be audited.

**Known risk:** Generic sub-domain prefixes like `app.hubdoc.com` will extract `hubdoc`, not `app` — the minimum-length filter (≥5 chars) handles the worst cases. The SB company name `App` (matched to Hubdoc via domain) is a real example of this false positive; the length filter would suppress it.

---

### Pass 3 — Fuzzy name match *(~300–600 additional companies, requires review)*

For SB companies that still have no match after passes 1 and 2, use `difflib.SequenceMatcher` or `rapidfuzz` to compute similarity between the SB company name and every QB name. Threshold ≥ 0.82 produces candidates.

```python
from rapidfuzz import fuzz, process

def find_fuzzy_match(sb_name: str, qb_names: list[str], threshold=82):
    result = process.extractOne(
        normalise(sb_name),
        [normalise(n) for n in qb_names],
        scorer=fuzz.token_sort_ratio,
        score_cutoff=threshold,
    )
    return result  # (match, score, index) or None
```

**Confidence:** LOW-MEDIUM. Do **not** write automatically. Write to a staging table (`qb_match_candidates`) for human review before promotion. Include the score as a column.

---

### Pass summary

| Pass | Mechanism | Est. matches | Auto-write? |
|---|---|---|---|
| 1 | Exact normalised name | ~864 | ✅ Yes |
| 2 | Email domain root | ~200–400 | ✅ Yes (with flag) |
| 3 | Fuzzy name (≥0.82) | ~300–600 | ❌ Staging only |
| — | Generic domain / no signal | ~3,279 | ❌ Manual or leave |

---

## 4. Schema Changes Required

Two new columns are needed on `customer_companies` to make the link durable and auditable.

```sql
ALTER TABLE customer_companies
  ADD COLUMN qb_customer_id    TEXT,         -- QB "Customer ID (key)" e.g. "17541"
  ADD COLUMN qb_customer_code  TEXT,         -- QB "Code*" e.g. "C13039"
  ADD COLUMN qb_match_method   TEXT,         -- 'exact_name' | 'domain_root' | 'fuzzy' | 'manual'
  ADD COLUMN qb_matched_at     TIMESTAMPTZ;  -- when this link was written/last verified
```

A staging table for pass-3 candidates:

```sql
CREATE TABLE qb_match_candidates (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id       UUID NOT NULL,
  sb_company_id   UUID NOT NULL REFERENCES customer_companies(id),
  sb_company_name TEXT,
  qb_customer_id  TEXT,
  qb_name         TEXT,
  match_score     NUMERIC(5,2),
  match_method    TEXT,
  reviewed        BOOLEAN DEFAULT FALSE,
  accepted        BOOLEAN,
  reviewed_by     TEXT,
  reviewed_at     TIMESTAMPTZ,
  created_at      TIMESTAMPTZ DEFAULT now()
);
```

---

## 5. Sync Service Implementation

### Architecture

The sync is a one-way write from QB → Supabase. QB is the system of record for financial data. The sync should run on-demand (triggered manually or via cron) and use the three-pass pipeline.

```
QB CSV export
      │
      ▼
  parse_qb_rows()         — strip HTML, parse currency, derive growth_90d
      │
      ▼
  run_match_pipeline()    — Pass 1 → Pass 2 → Pass 3 (staging)
      │
      ├─ high/medium confidence → upsert customer_companies qb_ fields
      └─ low confidence         → insert qb_match_candidates
```

### Core sync function

```python
import re, csv
from datetime import datetime, timezone
from typing import Optional

GENERIC_DOMAINS = {
    'gmail.com', 'hotmail.com', 'yahoo.com', 'outlook.com',
    'icloud.com', 'bigpond.com', 'me.com', 'hotmail.com.au',
}

def parse_currency(value: str) -> Optional[float]:
    """'$1,234,567.89' → 1234567.89"""
    cleaned = re.sub(r'[^\d.]', '', value or '')
    return float(cleaned) if cleaned else None

def parse_recency(html: str) -> Optional[int]:
    """'<div ...>8 d</div>' → 8"""
    m = re.search(r'(\d+)\s*d', html or '')
    return int(m.group(1)) if m else None

def derive_growth(ty: Optional[float], ly: Optional[float]) -> Optional[float]:
    if ty is not None and ly and ly != 0:
        return round((ty - ly) / ly * 100, 1)
    return None

def normalise(name: str) -> str:
    return re.sub(r'[^a-z0-9]', '', (name or '').lower())

def extract_domain_roots(domain_json: str) -> list[str]:
    domains = re.findall(r'[\w.-]+\.\w+', domain_json or '')
    roots = []
    for d in domains:
        if d in GENERIC_DOMAINS:
            continue
        parts = d.lower().split('.')
        root = parts[-2] if len(parts) >= 2 else parts[0]
        if len(root) >= 5:
            roots.append(root)
    return roots


class QBSyncService:
    def __init__(self, supabase_client, client_id: str):
        self._sb = supabase_client
        self._client_id = client_id

    def run_sync(self, qb_csv_path: str, dry_run: bool = False) -> dict:
        qb_rows = list(csv.DictReader(open(qb_csv_path)))
        sb_companies = self._fetch_all_sb_companies()

        # Build lookup structures
        qb_by_norm  = {normalise(r['Name*']): r for r in qb_rows}
        qb_names    = list(qb_by_norm.keys())

        stats = {'pass1': 0, 'pass2': 0, 'pass3_staged': 0, 'unmatched': 0}

        for sb in sb_companies:
            sb_norm = normalise(sb['company_name'])
            matched_qb = None
            method = None

            # Pass 1: exact name
            if sb_norm in qb_by_norm:
                matched_qb = qb_by_norm[sb_norm]
                method = 'exact_name'
                stats['pass1'] += 1

            # Pass 2: domain root
            if not matched_qb:
                roots = extract_domain_roots(sb.get('email_domains', ''))
                for root in roots:
                    for qb_norm_name, qb_row in qb_by_norm.items():
                        if root in qb_norm_name:
                            matched_qb = qb_row
                            method = 'domain_root'
                            stats['pass2'] += 1
                            break
                    if matched_qb:
                        break

            # Pass 3: fuzzy (stage only)
            if not matched_qb:
                try:
                    from rapidfuzz import fuzz, process
                    result = process.extractOne(
                        sb_norm, qb_names,
                        scorer=fuzz.token_sort_ratio,
                        score_cutoff=82,
                    )
                    if result:
                        matched_qb = qb_by_norm[result[0]]
                        if not dry_run:
                            self._stage_candidate(sb, matched_qb, result[1])
                        stats['pass3_staged'] += 1
                except ImportError:
                    pass
                if not matched_qb:
                    stats['unmatched'] += 1
                continue  # do not write pass-3 matches automatically

            # Write confirmed match
            if not dry_run and matched_qb:
                self._write_qb_fields(sb['id'], matched_qb, method)

        return stats

    def _write_qb_fields(self, sb_id: str, qb_row: dict, method: str):
        ty  = parse_currency(qb_row.get('Invoiced Line Items $ TY', ''))
        ly  = parse_currency(qb_row.get('Invoiced Line Items $ Y-1', ''))
        tot = parse_currency(qb_row.get('Total Invoiced Line Item $', ''))
        
        payload = {
            'qb_customer_id':          qb_row.get('Customer ID (key)'),
            'qb_customer_code':        qb_row.get('Code*'),
            'qb_account_manager':      qb_row.get('account Manager'),
            'qb_total_revenue':        tot,
            'qb_invoiced_ty':          ty,
            'qb_invoiced_ly':          ly,
            'qb_growth_90d':           derive_growth(ty, ly),
            'qb_days_since_last_invoice': parse_recency(qb_row.get('Recency.', '')),
            'qb_customer_type':        qb_row.get('Product Group(s)', ''),
            'qb_tier':                 self._derive_tier(tot),
            'qb_match_method':         method,
            'qb_matched_at':           datetime.now(timezone.utc).isoformat(),
        }
        self._sb.table('customer_companies').update(payload).eq('id', sb_id).execute()

    @staticmethod
    def _derive_tier(total_revenue: Optional[float]) -> str:
        if total_revenue is None:
            return 'Unknown'
        if total_revenue >= 500_000:
            return 'Level 4 Enterprise'
        if total_revenue >= 100_000:
            return 'Level 3 Major'
        if total_revenue >= 20_000:
            return 'Level 2 Growth'
        return 'Level 1 Retail'

    def _stage_candidate(self, sb: dict, qb_row: dict, score: float):
        self._sb.table('qb_match_candidates').insert({
            'client_id':       self._client_id,
            'sb_company_id':   sb['id'],
            'sb_company_name': sb['company_name'],
            'qb_customer_id':  qb_row.get('Customer ID (key)'),
            'qb_name':         qb_row.get('Name*'),
            'match_score':     score,
            'match_method':    'fuzzy',
        }).execute()

    def _fetch_all_sb_companies(self) -> list[dict]:
        all_rows, offset = [], 0
        while True:
            result = self._sb.table('customer_companies').select(
                'id, company_name, email_domains'
            ).eq('client_id', self._client_id).range(offset, offset + 999).execute()
            rows = result.data or []
            all_rows.extend(rows)
            if len(rows) < 1000:
                break
            offset += 1000
        return all_rows
```

---

## 6. Field Derivation Rules

### `qb_tier` — revenue band logic

| Total Revenue | Tier label |
|---|---|
| ≥ $500,000 | Level 4 Enterprise |
| $100,000–$499,999 | Level 3 Major |
| $20,000–$99,999 | Level 2 Growth |
| < $20,000 | Level 1 Retail |

This mirrors the pattern already seen in the 546 partial rows (`Level 1 Retail` etc.).

### `qb_growth_90d` — derivation

This field is currently 0% populated. It should be derived as:

```
qb_growth_90d = (invoiced_ty − invoiced_ly) / invoiced_ly × 100
```

Note: the QB export gives full-year TY vs LY, not a true 90-day window. The field name in Supabase implies 90-day scope, but based on the available export this will be an annual growth proxy. If a true 90-day figure is needed, it requires a direct QB API call or a more granular export.

### `qb_customer_type` — from Product Groups

QB stores semicolon-delimited product groups (`Books;Flat Sheets;Wide Format`). The four most common values are: Flat Sheets (338), Books (212), Wide Format (106), Casebound Books (25). Options:

- Store the full semicolon string as-is — simplest, preserves all data
- Store as a Postgres array — enables `@>` containment queries
- Store only the primary (first) group — loses data

**Recommendation:** store the full string. The analytics service does not currently query this field; it is display metadata only.

---

## 7. What the Analytics Service Needs to Work

The `CustomerAnalyticsService` does not read `customer_companies` `qb_` fields directly. It queries `qb_quotes` and `qb_operations` filtered by `matched_company_id`. The `qb_` sync populates the company card in the UI and the intelligence layer, but the analytics engine depends on `qb_quotes.matched_company_id` and `qb_operations.matched_company_id` being set to the correct Supabase UUID.

**Implication:** completing the `qb_customer_id` → SB UUID link (this sync) is a prerequisite for populating those `matched_company_id` foreign keys correctly. Without it, analytics features return empty for any company not already linked.

---

## 8. Implementation Phases

### Phase 1 — Schema migration *(1 day)*

Add the four new columns to `customer_companies` (`qb_customer_id`, `qb_customer_code`, `qb_match_method`, `qb_matched_at`) and create the `qb_match_candidates` staging table.

### Phase 2 — Run Pass 1 + 2 sync *(1 day)*

Run `QBSyncService.run_sync()` in dry-run mode first to audit the match log. Then run live. Expected outcome: ~1,000–1,200 SB companies fully enriched with all `qb_` fields.

### Phase 3 — Review staging table *(0.5 day)*

Export `qb_match_candidates` to a spreadsheet. Account managers review and mark `accepted = TRUE/FALSE` for each fuzzy candidate. A promotion script reads accepted rows and writes them to `customer_companies`.

### Phase 4 — Invalidate stale cache *(0.5 day)*

After the sync, delete all rows from `customer_intelligence_cache` so that the next analytics request recomputes with the enriched data.

```sql
DELETE FROM customer_intelligence_cache
WHERE client_id = '<your_client_id>'
  AND cache_type IN ('strike_rate', 'contact_capability_profile',
                     'seasonality_profile', 'capability_rhythm');
```

### Phase 5 — Ongoing sync cadence

QB exports are a CSV pull, not a live API. The sync should be scheduled weekly or triggered on-demand after a QB export is uploaded. Consider adding a simple admin endpoint: `POST /admin/sync/qb` that accepts a CSV upload and runs the pipeline.

---

## 9. Known Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| False-positive name match (two distinct companies with similar names) | Wrong financials shown for a company | `qb_match_method` flag makes these auditable; pass-3 goes to staging |
| SB company name is a contact's personal name, not a company | No match possible | Accept as unmatched; generic-domain companies (3,279) will largely fall here |
| QB Recency HTML format changes in a future export | `qb_days_since_last_invoice` silently becomes NULL | Add a validation check: warn if >10% of QB rows parse to NULL |
| `qb_growth_90d` is misleadingly named (it's annual, not 90-day) | Confusion in the UI | Document it; rename to `qb_growth_annual` if the column is not yet in production use |
| Duplicate SB companies for the same QB customer | One gets matched, the other stays blank | De-duplicate SB companies as a separate cleanup pass |
