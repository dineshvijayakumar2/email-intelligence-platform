# AM Behaviour Tracking — Current State Audit

**Date:** June 1, 2026
**Scope:** Read-only investigation of AM proactiveness, outbound email analysis, complaint lifecycle, engagement-revenue correlation, and customer assignment — beyond what's in am_performance_snapshots.

---

## 1. Proactiveness Tracking

### What Exists

**Initiation ratio** — a per-contact metric (0.0–1.0) stored on `customer_contacts.initiation_ratio`:
- `0.0` = contact always initiates (AM always responds)
- `1.0` = AM always initiates (contact always responds)
- `0.5` = balanced

**How it's computed** — RPC `calculate_all_contact_initiation_ratios()` (migration 009):
- For each thread, finds first email by `sent_date`
- If first email `is_outbound = TRUE` → thread initiated by AM
- Counts `threads_initiated_by_us` vs `threads_initiated_by_them`
- Called during comm pattern analysis (`comm_pattern_analyzer.py`)

**AI thread_role** — `ai_email_intelligence.thread_role` column with values:
- `initial`, `reply`, `forward`, `auto_reply`, `cc_addition`, `internal`
- Set by Claude Haiku during classification
- **NOT currently used** to compute initiation metrics — the deterministic first-email-by-date logic is used instead

**Seasonality outreach windows** — suggests proactive timing (1 month before peak) but does NOT track whether AM actually followed through.

### What's Missing

| Gap | Description |
|-----|-------------|
| No `is_proactive_outreach` flag | No persistent per-thread boolean marking AM-initiated threads |
| No `first_sender` stored | First-email-in-thread computed on demand via RPC, not persisted |
| No outreach follow-through | Seasonality windows suggest timing but don't track AM execution |
| No proactiveness score | No composite metric combining initiation ratio + timing alignment |
| No window-aligned tracking | Can't answer "did AM contact customer before their peak month?" |

### What CAN Be Derived

- From `initiation_ratio > 0.7` → AM tends to initiate with this contact
- From `thread_status.last_sender_is_outbound` → last message direction (but not first)
- From `ai_email_intelligence.thread_role = 'initial'` on outbound emails → AI guess at proactive outreach

---

## 2. Outbound Email Classification

### Key Finding: Outbound Emails ARE Fully Classified

Outbound emails flow through the **same AI pipeline** as inbound. They receive:
- Intent, sentiment, urgency, confidence scoring
- Entity extraction (competitors, products, budget signals, people, dates, action items)
- Business signals (buying_intent, renewal_intent, churn_signal, etc.)
- Thread context analysis
- AI-generated summary

### What's Different for Outbound

| Aspect | Inbound | Outbound |
|--------|---------|----------|
| `action_type` | Normal classification | Forced to `no_action` (AM is the sender) |
| `suggested_action` | "Respond to [contact]" | "Await reply", "Follow up in N days" |
| Response urgency bucket | Eligible | **Skipped** (direction check in bucket engine) |
| Retention risk bucket | Eligible | **Skipped** |
| New relationship bucket | Eligible | **Skipped** |
| Deal at risk bucket | Eligible | Eligible (doesn't check direction) |
| Revenue opportunity bucket | Eligible | Eligible (doesn't check direction) |

### What's NOT Analysed on Outbound

| Missing | Description |
|---------|-------------|
| AM email quality | No tone, clarity, or persuasiveness assessment |
| Proposal quality | No scoring of proposals or quotes sent |
| Follow-up effectiveness | No tracking of whether AM follow-up drove expected customer action |
| Writing style patterns | No communication style analysis across AM's emails |
| Promise tracking | No detection of "I'll send this by Friday" → did they? |

**Design intent:** The system is built around detecting inbound customer signals and surfacing what actions the AM should take — not assessing how well the AM executes through their written communication.

---

## 3. Complaint Tracking

### What Exists — Classification Only

**AI classification:**
- `complaint` is a first-class intent value in the LLM prompt
- Distinguished from `churn_risk`: complaints are "customer reporting a bug or issue they want fixed"
- Stored in `ai_email_intelligence.intent`

**Thread status override:**
- Priority 10 rule `complaint_or_churn_urgent` (migration 077) → complaint threads automatically become `urgent` effective status

**Action bucket signaling:**
- `response_urgency`: complaints with high/critical urgency trigger immediate AM attention
- `retention_risk`: at-risk/dormant customers with complaints trigger retention risk
- `deal_at_risk`: complaints + churn signals on high-revenue customers (>$5K)
- High-value customer boost: Tier A / >$50K revenue complaints get +0.1 confidence

### What's Missing — No Lifecycle

| Gap | Description |
|-----|-------------|
| No complaint state machine | No `complaint_status` column (open → acknowledged → investigating → resolved → closed) |
| No resolution tracking | Can't answer "how long did complaint take to resolve?" |
| No follow-up workflow | No auto-escalation if complaint unresolved after N days |
| No complaint categorization | No subcategories (product_quality, delivery, billing, service) |
| No re-opening detection | Same issue mentioned in follow-up not linked to original complaint |
| No complaint metrics | No closure rate, avg resolution time, reopened rate |
| No SLA enforcement | Complaints trigger "urgent" but no deadline column |
| No sentiment recovery | No re-analysis post-resolution to confirm customer satisfaction |
| No complaint history on contact/company | No "X complaints in past 30 days" metric |
| No AM resolution actions | No "mark as resolved" or "escalate to manager" in UI |

**Architectural note:** Complaints are treated as an **intent classification** (per-email), not a **stateful workflow** (per-thread). Once classified, they flow into generic action buckets without complaint-specific handling.

---

## 4. Engagement-Revenue Correlation per AM

### Finding: No Correlation Analysis Exists

The platform stores AM behaviour metrics and revenue **independently**. There is **zero statistical correlation logic**.

### What's Stored (Independent Metrics)

**AM Efficiency Analyzer** computes per AM per period:

| Metric Category | Fields |
|----------------|--------|
| Response | `avg_response_time_hours`, `avg_bh_response_time_hours`, `response_rate_pct` |
| Volume | `emails_sent`, `emails_received`, `after_hours_email_pct` |
| Revenue | `revenue_attributed` (simple sum from QB sales line items) |
| Quotes | `quotes_sent`, `quotes_accepted`, `quote_conversion_rate` |

**`am_performance_snapshots.revenue_change_pct`** — column exists in schema but is **never populated** (always NULL).

### What's Not Built

| Gap | Description |
|-----|-------------|
| No statistical libraries | Zero imports of scipy, statsmodels, numpy correlation, sklearn |
| No regression analysis | No modeling of revenue as function of AM behaviour |
| No correlation coefficients | No R-squared, p-values, or significance tests |
| No feature importance | No analysis of which AM metrics most influence revenue |
| No predictive modeling | No "AMs who respond within 4h generate X% more revenue" |
| No A/B comparison | No statistical comparison of high-performing vs low-performing AMs |
| `revenue_change_pct` dead column | Exists in schema since migration 021, never populated |

**Design intent:** The system focuses on operational reporting (AM dashboard KPIs), not predictive analytics.

---

## 5. AM Customer Assignment

### Architecture: Derived, Not Direct

AM-to-customer assignment is **NOT stored directly** on `customer_companies`. It is **derived from email traffic** through the mailbox→user chain.

### The Assignment Chain

```
customer_companies
    ↑ (emails.customer_company_id)
emails
    ↓ (emails.mailbox_id)
mailboxes (user_id = AM assignment)
    ↓ (mailboxes.user_id)
user_profiles (the AM's identity)
```

### Key Tables

| Table | AM-Relevant Column | Purpose |
|-------|-------------------|---------|
| `user_profiles` | `roles` (TEXT[]) | Contains 'account_manager' role |
| `mailboxes` | `user_id` (UUID FK) | **This IS the AM assignment** — at mailbox level |
| `user_client_assignments` | `user_id`, `client_id` | Which users access which clients |
| `customer_companies` | — | **No AM column** — by design |
| `qb_customers` | `account_manager` (TEXT) | QB's internal AM name (freeform text) |
| `relationship_context_cache` | `am_user_id`, `account_manager` | Cached AM resolution (computed at digest time) |

### How "Primary AM" Is Resolved

**Strategic context builder** (`_get_primary_am()` in `strategic_context_builder.py`):
1. Query emails where `customer_company_id = company_id`
2. Count emails by `mailbox_id`
3. Mailbox with most emails = primary communication channel
4. Resolve `mailbox.user_id → user_profiles.name`
5. Cache in `relationship_context_cache`

**Fallback:** If no email traffic, uses `qb_customers.account_manager` (text field).

```python
# strategic_context_builder.py line 150
"account_manager": am_info.get("am_name") or company_data.get("qb_account_manager"),
```

### QB AM Name Mismatch (Confirmed Prior Session)

QB stores names like "Ehab Kamel" while platform stores "Ehab Kamel | Carbon8" — **zero matches** between the two systems. AM2 would need a mapping table or normalization.

### RBAC Enforcement

`get_user_accessible_mailboxes()` RPC (migration 010) scopes AM access:
- `admin` → all active mailboxes
- `account_manager` → own mailboxes + assigned client mailboxes
- `client_manager` → assigned client mailboxes

### What's Missing

| Gap | Description |
|-----|-------------|
| No direct `am_user_id` on `customer_companies` | AM derived from email volume, not explicitly assigned |
| No customer reassignment workflow | Can't formally transfer customer from one AM to another |
| No AM territory concept | No geographic/segment-based assignment |
| No multi-AM support | One company → one "primary" AM (highest email volume), no secondary AM |
| QB name mapping | Zero matches between QB `account_manager` and platform `user_profiles.name` |
| No assignment history | Can't answer "when did this customer move from AM1 to AM2?" |

---

## Summary Table

| Capability | What Exists | What's Missing | Status |
|------------|------------|----------------|--------|
| Proactiveness tracking | Initiation ratio per contact + AI thread_role | Persistent per-thread flag, outreach follow-through | **Partial** — derivable but not persisted |
| Outbound email analysis | Full AI classification (intent, sentiment, entities) | AM email quality, proposal scoring, promise tracking | **Partial** — classified but not quality-assessed |
| Complaint lifecycle | Single-email intent classification + urgent override | State machine, resolution tracking, SLA, categorization | **Classification only** — no lifecycle |
| AM-revenue correlation | Independent metric storage in am_performance_snapshots | Any statistical correlation, regression, or feature importance | **Not built** — raw storage only |
| AM customer assignment | Email-volume-derived via mailbox chain + QB fallback | Direct FK, reassignment workflow, territory, multi-AM, history | **Derived** — no formal assignment |
