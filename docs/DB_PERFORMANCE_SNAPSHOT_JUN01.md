# Database Performance Snapshot — 1 June 2026

**Purpose:** Point-in-time snapshot of database performance metrics. Reference for measuring impact of remediation work.
**Source:** Performance analysis run 1 June 2026 (post-trip return)
**Next snapshot:** After Platform Stabilisation track items land

---

## Top-line metrics

| Metric | Value | Notes |
|--------|-------|-------|
| Database size | 12.44 GB | of 22 GB provisioned (57% full) |
| Shared buffers | 1.79 GB | Insufficient for 9.71 GB emails table |
| Cache hit rate (overall) | 87.05% | Target: 99%+ |
| Statement timeouts | Triggering in production | Confirmed in code + git history |
| Total slow queries identified | 243 | Cumulative hours of CPU time |

## Quota status (1 June 2026)

Supabase organization exceeded **egress quota** in previous billing cycle. Grace period until 11 June 2026.

**Current cycle (as of 1 June):**
- Egress: 51.828 / 250 GB (21%)
- Cached egress: 0 / 250 GB
- Storage: 0 / 100 GB (well under)
- Compute hours: 319 hours ($6.57)
- All other dimensions at 0

**Important:** The grace period covers the *previous* billing cycle overage. Current cycle is well within quota. No immediate hard wall — but the trajectory needs attention.

**Implication for remediation priority:** egress is the dimension to optimise, not compute or storage. This changes which remediation items matter most:
- **Highest impact for egress:** email body_text vertical partition (currently every emails SELECT pulls body_text over the wire)
- **High impact:** keyset pagination on heavy endpoints (eliminates count-then-fetch double-reads)
- **Medium impact:** application-side narrower SELECTs (audit for SELECT * patterns)
- **Lower impact for egress:** RLS auth fixes, GIN operator fixes, unused index cleanup (these help CPU/storage but not significantly egress)

---

## Top-5 largest objects

| Object | Size | % of DB |
|--------|------|---------|
| public.emails (table) | 9.71 GB | 78.05% |
| public.idx_emails_embedding | 1.77 GB | 14.24% |
| public.qb_operations | 854 MB | 6.71% |
| public.ai_email_intelligence | 642 MB | 5.04% |
| public.idx_emails_body_fts | 313 MB | 2.46% |

---

## Top slow queries (ranked by impact)

### 1. update_company_email_counts_from_junction
- Calls: 1,907 – 1,912 per period
- Mean time: 5,411 – 10,321 ms
- Max time: 15,859 – 27,857 ms
- Total time consumed: ~14% of all DB time
- Self-imposed statement_timeout: 30 seconds (team aware of risk)

### 2. PostgREST pagination on qb_operations (factory_rush filter)
- Calls: 155,442
- Mean: 168 ms, Max: 2,763 ms
- Cache hit: 54.78%

### 3. emails table wide-column SELECT (heaviest volume)
- Calls: 136,351 (highest of all queries)
- Mean: 365 ms, Max: 39,770 ms
- Total time: 21.9% of measured DB time
- Cache hit: 99.13% (but 1% of 136K = 1,363 cold-cache hits with severe tail latency)

### 4. PostgREST pagination on qb_operations (contact_email filter)
- Calls: 58,972
- Mean: 188 ms, Max: 3,051 ms
- Cache hit: 33.73%

### 5. UPDATE on customers (QB match fields)
- Calls: 2,227,842 (highest of any query)
- Rows: 22,274,842 total
- Mean: 3 ms, Max: 7,842 ms
- Cache hit: 95.69%
- Pattern: high-frequency individual updates via JSON payload

### 6. update_contact_email_counts_from_junction
- Mean: 3,203 ms, Max: 58,920 ms
- Pattern: similar full-recompute aggregate as #1

### 7. qb_operations capability_tags filter (GIN index misuse)
- Calls: 31,440, Mean: 416 ms
- Cache hit: 22.17%
- Issue: equality operator (=) on GIN index designed for containment (@>)

---

## Performance Advisor findings

- **34 RLS warnings** — Auth function init plan issues on emails, mailboxes, audit_log, email_response_metrics, user_client_assignments, user_profiles, client_manager_assignments
- **Multiple permissive RLS policies** — overlapping policies on user_client_assignments, user_profiles, client_manager_assignments
- **185 unindexed foreign keys** — across ai_business_entities, ai_daily_digests, ai_relationship_summaries, ai_usage_log, customer_intelligence_cache, customer_recommendations, downloaded_files, events, extraction_jobs, folders, notifications, qb_match_candidates, relationship_context_cache, system_settings
- **Unused indexes** — on emails (×2), account_managers (×2), thread_status_override_rules, ai_email_intelligence, ai_relationship_summaries

---

## Confirmed production symptoms

- supabase_client.py explicitly handles `canceling statement due to statement timeout (SQLSTATE 57014)` as retryable
- gmail.py commit log: "Reduce batch_size from 25 to 10 — 25 still triggers statement timeout"
- update_company_email_counts_from_junction hardcoded 30-second statement_timeout
- recently committed emails.py change: "Fix Supabase Disk IO budget: replace Python pagination loops with DB-..."

---

## Identified remediation work (1 June)

Priority order revised after seeing quota dimension is **egress**. All items remain within current Supabase tier.

| # | Action | Primary Impact | Effort |
|---|--------|----------------|--------|
| 1 | **Email body_text vertical partition (egress focus)** | Largest egress reduction — body_text no longer pulled with every list query | 2-3 days |
| 2 | Keyset pagination on heavy endpoints | Eliminates pg_catalog.count + fetch double-read pattern (egress + CPU) | 1-2 days |
| 3 | Audit frontend/backend for `SELECT *` patterns; narrow columns | Reduces egress per query | 1 day to audit, variable to fix |
| 4 | Convert update_company_email_counts to incremental/scheduled | Removes ~14% of DB time (CPU, not egress) | 1 day |
| 5 | RLS auth function pattern fix — wrap auth.uid() in (SELECT auth.uid()) | Eliminates per-row auth overhead (CPU) | SQL-only, ~1 hour |
| 6 | Capability tags GIN operator fix (= → @>) | Fixes 22% cache-hit query (CPU, marginal egress) | ~1 hour |
| 7 | Drop unused indexes on emails table | Reclaims buffer cache, storage (not egress) | ~30 min + verification |
| 8 | Add FK indexes for 185 flagged tables | Eliminate sequential scan risk (CPU) | 1 day, CONCURRENTLY |
| 9 | Consolidate multiple permissive RLS policies | Reduce policy evaluation overhead (CPU) | ~1 hour |

**Highest priority for the egress concern: items 1, 2, 3.**

Items 4-9 are still valuable for general database health but don't directly address the egress dimension that triggered the quota issue.

---

## What this snapshot establishes

- Current state of the database under production load on 1 June 2026
- Specific queries and tables driving the slowness
- Specific remediation items with effort estimates
- Quota status (exceeded, grace period until 11 June)

## What to track in next snapshot

After remediation work completes:
- **Egress trajectory** (primary metric given current quota concern)
- Cache hit rate change
- Statement timeout frequency
- Top-5 slow query times
- Database size (should reduce after unused index drops + body_text partition if data archived)
- Quota status — has grace period been extended, was it cleared, is current cycle on track

