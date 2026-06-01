# Buyer Quality & Quote Fodder Detection — Current State Audit

**Date:** June 1, 2026
**Scope:** Read-only investigation of strike rate, buying signals, quote timing, quote volume, and competitor mentions — what exists to distinguish legitimate buyers from window shoppers.

---

## 1. Per-Contact Strike Rate

### What Exists — Fully Implemented

Strike rate is computed at contact level via a non-materialized SQL view, sourced from QB data.

**Formula:** `accepted_quote_count / quote_count` (0.0–1.0 decimal)
- "Accepted" = `qb_quotes.date_accepted IS NOT NULL`
- Join: `LOWER(customer_contacts.email_address) = LOWER(qb_quotes.contact_email)` (case-insensitive, client-scoped)

### View Hierarchy

| View | Type | What It Computes |
|------|------|------------------|
| `contact_quote_metrics` | Regular | Per-contact: quote_count, accepted_quote_count, strike_rate, total_quote_value, avg_quote_value, total_job_value, avg_margin_pct, capability_count |
| `contact_persona` | Regular | Joins quote metrics + email metrics → persona classification + engagement score |
| `company_contact_summary` | Regular | Company-level: AVG(strike_rate) across all contacts |

### Separate Service-Layer Path

`CustomerAnalyticsService.get_strike_rate(company_id)` in `customer_analytics_service.py` (lines 83–195):
- Computes company total + per-contact breakdown + per-year trend
- Cached 24h in `customer_intelligence_cache`
- Returns: `{company_total, by_contact: [{contact_email, total_quotes, converted, strike_rate_pct}], by_year}`

### Frontend Display

| Location | What's Shown |
|----------|-------------|
| Contacts list (`contacts.tsx`) | "Quotes" column + "Strike %" column, sortable |
| PersonaCard (`PersonaCard.tsx`) | quote_count + strike_rate |
| StrikeRateCard (`StrikeRateCard.tsx`) | Company total + top 5 contacts with individual strike rates |
| Contact detail (`contact-detail.tsx`) | Quote count badge in header |

### Persona Classification Uses Strike Rate

| Persona | Strike Rate Involvement |
|---------|----------------------|
| `champion` | ≥5 quotes AND strike_rate ≥0.3 AND active (≤180d), OR ≥10 accepted, OR ≥$50K job value |
| `active_buyer` | Has accepted quotes AND recent emails (≤90d) |
| `prospect` | ≤2 quotes, zero acceptances |
| `inactive_buyer` | Has conversions but no recent emails (>90d) |

**Status: Production.** Contact-level strike rate is fully computed, cached, and surfaced.

---

## 2. Buying Signal Extraction & Aggregation

### Per-Email Extraction — Complete

Claude Haiku extracts per email:

| Field | Type | Description |
|-------|------|-------------|
| `buying_signals` | TEXT[] | Array of extracted phrases indicating buying intent |
| `budget_signals` | JSONB | Structured: {amount, timeframe, context} |
| `business_signal` | TEXT | Categorical: buying_intent, renewal_intent, expansion_interest, budget_discussion, churn_signal, competitive_evaluation, etc. |
| `has_buying_signal` | BOOLEAN | True if buying_signals array non-empty |
| `has_budget_signal` | BOOLEAN | True if budget_signals present |
| `business_signal_score` | INTEGER | Weighted 0–100 composite |

### Business Signal Score Formula

```
has_budget_signal:       +30
has_buying_signal:       +25
has_competitor_mention:  +15
has_deadline:            +10
business_signal field:
  buying_intent:         +20
  expansion_interest:    +15
  churn_signal:          +15
  budget_discussion:     +10
  competitive_evaluation: +10
```

### Action Bucket Usage

Buying signals feed into the `revenue_opportunity` bucket:
```
if business_signal in (expansion_interest, renewal_intent, buying_intent)
   or intent in (expansion_signal, pricing_inquiry):
     → revenue_opportunity action bucket
```

### Contact / Company Aggregation — NOT Built

| What Exists | What's Missing |
|-------------|---------------|
| Per-email buying_signals extraction | No contact-level "total buying signals count" |
| Per-email business_signal_score (0–100) | No contact-level "aggregate buyer intent score" |
| Entity-level rollup in `ai_business_entities` | No "buyer quality" or "purchase likelihood" metric |
| Action bucket classification per email | No relationship-level buying signal summary |

**Gap:** The architecture extracts buying signals per email and routes them to action buckets, but never aggregates to a contact-level "buyer quality" score. A contact who sends 20 emails with buying signals looks the same as one who sends 1 — there's no accumulation.

---

## 3. Quote-to-Acceptance Timing

### Finding: NOT Computed

The raw data exists but timing analysis is not implemented.

### Available Data

| Table | Column | Purpose |
|-------|--------|---------|
| `qb_quotes` | `date_created` | When quote was issued |
| `qb_quotes` | `date_accepted` | When quote was accepted |
| `qb_jobs` | `accepted_date` | When job was accepted |

`date_accepted - date_created` would give days-to-accept per quote. This is never computed.

### What's Missing

| Metric | Status |
|--------|--------|
| `days_to_accept` per quote | **Not computed** |
| `avg_days_to_acceptance` per contact | **Not computed** |
| `median_decision_time` per contact | **Not computed** |
| Decision velocity distribution | **Not computed** |
| Stalled quote detection (age > N days) | **Not computed** |
| Sales cycle benchmarking per industry | **Not computed** |

### Why This Matters for Buyer Quality

Quote-to-acceptance timing would directly distinguish:
- **Committed buyers** — consistent ~14-day decision cycle, high conversion
- **Speculative quoters** — long delays (60+ days), low conversion, many quotes abandoned
- **Window shoppers** — request quotes, never respond, no conversion

The data is sitting in QB (`date_created`, `date_accepted`) — it just needs a `days_to_accept` computed column and aggregation views.

---

## 4. Quote Volume Per Contact

### What Exists — Fully Tracked and Surfaced

Two parallel quote count columns:

| Source | Column | What It Counts |
|--------|--------|---------------|
| `contact_persona` view | `quote_count` | Total distinct quotes (from `qb_quotes` email join) |
| `customer_contacts` table | `qb_quotes_count` | Accepted quotes only (from `qb_contacts` sync) |

### Frontend Display

| Location | Column | Data |
|----------|--------|------|
| Contacts list | "Quotes" | `qb_quotes_count` — sortable descending |
| Contacts list | "Strike %" | `strike_rate` as percentage |
| Contact detail header | Badge | `"{qb_quotes_count} quotes"` |
| PersonaCard | Fields | `quote_count` + `strike_rate` |
| StrikeRateCard | Per-contact rows | `{contact_name} — {strike_rate_pct}% ({converted}/{total_quotes})` |

### The Peter Howie / RareID Pattern (514 quotes, 80 accepted, 15.6%)

**Is this identifiable today?** Yes, but requires manual inspection:

1. **Contacts list** → sort by "Quotes" descending → spot high-volume contacts → check Strike % column
2. **StrikeRateCard** on company detail → per-contact breakdown shows `15.6% (80/514)`

### What's Missing

| Gap | Description |
|-----|-------------|
| No explicit "heavy quoter" classification | No persona for high-volume-low-conversion contacts |
| No "speculative quoter" flag | System doesn't distinguish 514-quote-80-accepted from 5-quote-4-accepted |
| No quote velocity metric | No "quotes requested per month" independent of acceptance |
| No threshold-based alerting | No "this contact requests >X quotes/month with <Y% conversion" signal |

**Engagement score gap:** A contact with 15 quotes and 0% strike rate scores **80/100 on quote activity** in the persona engagement score (10+ quotes = 80 points regardless of conversion). This rewards volume without quality.

---

## 5. Competitor Mentions

### Extraction — Per-Email, Complete

| Field | Type | Description |
|-------|------|-------------|
| `competitors_mentioned` | TEXT[] | Array of company names extracted from email |
| `has_competitor_mention` | BOOLEAN | Fast-filter flag |

Indexed: `idx_ai_intel_competitor` on `has_competitor_mention = TRUE`.

### Entity-Level Aggregation — Complete

`ai_entity_aggregator.py` rolls up per-email mentions into `ai_business_entities`:

| Column | Description |
|--------|-------------|
| `entity_type` | "competitor" |
| `entity_name` | Display name |
| `normalized_name` | Lowercase for dedup |
| `mention_count` | Total mentions across all emails |
| `first_seen_at` / `last_seen_at` | Temporal range |
| `associated_company_ids` | UUID[] — which companies mentioned it |
| `context_snippets` | JSONB — up to 10 context strings |

### Frontend Display

| Location | What's Shown |
|----------|-------------|
| Intelligence Inbox | Per-email competitor badges (warning color) |
| Opportunities → Competitors tab | Aggregated table: name, mention count, first/last seen, context |
| Strategic Digest | "Competitive Landscape" section with competitor mentions, price sensitivity signals, win/loss insights |

### Contact-Level Aggregation — NOT Built

| What Exists | What's Missing |
|-------------|---------------|
| Per-email extraction | No "contacts who mention competitors most" |
| Entity-level rollup (across all emails) | No per-contact competitor frequency |
| Associated company IDs on entity | No "which contacts at Company X mention Competitor Y" |
| Strategic digest landscape | No "shopping around" signal derived from competitor frequency |

**Gap for buyer quality:** A contact who mentions competitors in 8 of 10 emails is likely shopping around. This pattern is extractable from existing data (`ai_email_intelligence.competitors_mentioned` grouped by contact) but is not aggregated or surfaced today.

---

## Summary: What Exists vs. What's Needed for Q1 Spec

### Available Today

| Signal | Level | Source | UI |
|--------|-------|--------|----|
| Strike rate (conversion %) | Per-contact | `contact_persona` view from QB | Contacts list, PersonaCard, StrikeRateCard |
| Total quote count | Per-contact | `contact_persona` view from QB | Contacts list, PersonaCard |
| Accepted quote count | Per-contact | `contact_persona` view from QB | StrikeRateCard |
| Total job value | Per-contact | `contact_persona` view from QB | Contacts list |
| Buying signals per email | Per-email | AI classifier | Opportunities page |
| Business signal score | Per-email | Weighted formula | Opportunities page |
| Competitor mentions per email | Per-email | AI classifier | Inbox, Opportunities |
| Competitor aggregation | Entity-level (cross-email) | Entity aggregator | Competitors tab |
| Persona classification (8 types) | Per-contact | SQL view | Contacts list, PersonaCard |

### Missing for Buyer Quality / Quote Fodder Detection

| Signal | Impact | Data Available? | Effort |
|--------|--------|----------------|--------|
| Quote-to-acceptance timing (days_to_accept) | Distinguishes committed vs speculative buyers | Yes (`date_created`, `date_accepted` in qb_quotes) | **Low** — computed column + view |
| Decision velocity per contact (avg_days_to_accept) | Profiles buyer speed | Yes (aggregation of above) | **Low** — extend contact_quote_metrics view |
| Contact-level buying signal count | Identifies persistent intent vs one-off | Yes (aggregate ai_email_intelligence per contact) | **Low** — new aggregation query |
| Contact-level competitor mention frequency | "Shopping around" signal | Yes (aggregate competitors_mentioned per contact) | **Low** — new aggregation query |
| Quote velocity (quotes requested / month) | Distinguishes high-demand from speculative | Yes (qb_quotes.date_created per contact) | **Low** — extend view |
| Buyer quality composite score | Single metric combining strike rate + timing + signals | Derivable from above | **Medium** — weighted formula |
| "Heavy quoter, low converter" classification | Explicit persona for speculative quoters | Derivable (quote_count + strike_rate thresholds) | **Low** — add persona category |
| Stalled quote alerting (age > threshold) | Flags quotes going cold | Yes (qb_quotes.date_created vs today) | **Low** — query + action bucket |

### Architecture Gap

The fundamental gap is **contact-level aggregation of per-email intelligence**. Today:
- Per-email signals are extracted and stored ✓
- Entity-level (cross-email) aggregation exists for competitors ✓
- Contact-level strike rate exists via QB quote views ✓
- **But:** buying signals, competitor mentions, and business signal scores are NOT aggregated to contact level

A "buyer quality score" would combine:
1. Strike rate (from QB) — conversion ability
2. Decision velocity (from QB) — commitment speed
3. Buying signal density (from AI) — expressed intent frequency
4. Competitor mention frequency (from AI) — shopping-around indicator
5. Quote volume relative to conversion — speculative quoter flag

All data exists. The aggregation layer and composite scoring do not.
