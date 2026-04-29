# Bucket List: Actions Through May 14, 2026

**Purpose:** Tracking all planned work items for the pre-trip sprint.
**Not a schedule** — that's in SCOPE_LOCK_APR22_MAY14.md. This is a completeness checklist.
**Status convention:** [ ] not started / [~] in progress / [x] done + verified / [D] deferred post-trip

---

## Already shipped (Apr 22–23)

- [x] Migration 094: Pass 3 QB propagation (15,077 contacts updated)
- [x] Schema document (`DATABASE_DESIGN.md`)
- [x] Insight Engine Audit (`INSIGHT_ENGINE_AUDIT.md`)
- [x] Signature extraction code fix (`role_classifier.py:369-386`, 11 sign-off phrases added)
- [x] Shared-address pattern expansion (`contact_extractor.py:110-127`, 17 patterns added)
- [x] Pass 3 exclusion logic (`094_propagate_qb_from_company.sql:53-73`) — **FLAG:** 094 already ran in prod; must re-apply updated RPC via `CREATE OR REPLACE`
- [x] Migration 095 written (internal/shared contact QB tier nulling) — **not yet applied to prod**
- [x] AI backfill chunked loop (`ai_backfill.py:58-89`) — loops 10K chunks until exhaustion
- [x] Auth state audit (verdict: 3-5d feature; SMTP-less design eliminates biggest risk)
- [x] I/O budget investigation (Postgres buffer pool pressure — `shared_buffers` likely 256MB default)
- [x] Dropped threads investigation (likely expected — 30+ day inactivity threshold; verify migration 080 applied)
- [x] Integration tests (`test_data_hardening.py`) — 63 tests: sign-off rejection, shared-address detection, QB propagation exclusion
- [x] All above committed + pushed to prod (`ade0c45`)

---

## Data hardening — Week 1 core

### Embedding re-embed (added Apr 23 — priority)

- [x] Migration 096: add `embedding_model` + `embedded_at` to emails, qb_operations, customer_companies; drop HNSW; null stale embeddings (applied Apr 24)
- [x] Migration 097: update 3 batch RPCs with audit params; add embedding/audit cols to qb_quotes; create `batch_update_embeddings_quotes` RPC (applied Apr 24)
- [x] `vector_service.py`: audit columns on every embed write (all 4 tables), `_resolve_provider()` from env var, `_embedding_model_tag()` canonical format
- [x] Quality gate: `MIN_EMBED_TEXT_LEN = 20` across all embed methods; quotes also filtered by `matched_company_id IS NOT NULL` (~130K thin rows excluded)
- [x] `embed_quotes_batch()` with customer enrichment via `qb_customers.customer_key_id` join
- [x] 14 unit tests passing (`backend/tests/test_vector_service.py`)
- [x] Null-out: all stale mixed-provider embeddings cleared via DROP+ADD COLUMN (migration 096)
- [x] Reembed completed Apr 24-25: emails 258,453/258,472 + companies 14,735/14,978 (gaps are below MIN_EMBED_TEXT_LEN gate, expected)
- [x] Verification: all embedded rows tagged `openai/text-embedding-3-small-768`, zero untagged across both tables
- [x] qb_operations: 4,000 rows embedded by auto-trigger pipeline during re-embed window (not part of scoped run, but properly tagged — kept as-is)
- [ ] **Investigate before next bulk re-embed:** companies run required 4 manual clicks to reach 100%. Single job appears to terminate early without exhausting the table. Worth checking worker logs for completion semantics before any post-trip 615K operations re-embed.
- [x] IVFFlat index built on emails (lists=500, 1013 MB) — HNSW abandoned; fails on Supabase Pro at disk-spill phase
- [x] `ivfflat.probes = 10` set at database level via `ALTER DATABASE postgres SET ivfflat.probes = 10`
- [x] Functional test: top-10 similarity returns semantically related results (~140ms, probes=10)
- [x] `DATABASE_DESIGN.md` updated: vector embedding architecture (§5.5), index choice rationale (§5.6), build operations (§5.7), forbidden operations (§5.8), migration history 094–097
- [ ] Spot-check semantic search quality on 20 known queries
- [ ] Post-trip: revisit HNSW with raised `maintenance_work_mem` if IVFFlat recall proves insufficient
- [ ] Post-trip flag: investigate apparent duplicate emails surfaced during sanity test (rows `a9ad862f` and `f5714636` share identical subject + similarity score)
- [D] Operations embedding (615K) — not on MVP critical path, deferred
- [D] Quotes embedding (~19K matched) — untested hypothesis, exit criterion not yet met, deferred

### Signature re-extraction (titles)

- [ ] Validation pass: 50-100 known-case emails through GPT-4o-mini, compare to expected
- [ ] Scope query: contacts with `title` matching 11 sign-off phrases (surgical, not full)
- [ ] Snapshot table: `(contact_id, old_title, snapshotted_at)` before overwrite
- [ ] Idempotent runner (completed_steps pattern)
- [ ] Verification SQL before kickoff
- [ ] Run + verify
- [ ] Consider: should signature re-extraction also populate a `title_extracted_model` column for future audits?

### Internal / shared contact propagation

- [ ] Re-apply migration 094 (updated RPC with Pass 3 guards) — `CREATE OR REPLACE` via runner
- [ ] Apply migration 095 (one-time cleanup) via runner
- [ ] Verification SQL: zero internal contacts with Carbon8 QB tier, zero shared addresses with inherited QB data
- [ ] Spot-check: Carbon8 employees, `accounts@`, `hello@`, `noreply@` contacts
- [ ] Run `test_data_hardening.py` with `TEST_CLIENT_ID=<carbon8>` to exercise DB-level test

### AI classification coverage

- [x] Backfill handler: concurrent mailbox processing (CONCURRENCY=3, asyncio.gather + Semaphore), BATCH_SIZE 20→50 (commit `bc7606d`)
- [x] 4 production fixes mid-run: PyYAML/Python 3.13 wheel, ref-linking PostgREST limit, concurrent prefetch connection exhaustion, HTTP/2 trailer retry
- [x] Multi-slot backfill (SLOTS_PER_MAILBOX=2) — each mailbox gets 2 concurrent analyzers. Tuned CONCURRENCY 5→3 after Supabase pressure
- [x] Per-mailbox classify button on Data Health page (lightning bolt per row)
- [~] Tuesday Apr 29: 155K/260K classified (72.4% all-time). Last 90 days: 5/7 mailboxes at 95%+, ehab@ at 82%, hello@ at 99.9%
- [ ] Top up OpenAI credit if burn rate × remaining > remaining balance

### Extraction pipeline bugs (identified Apr 29)

- [x] **BUG FIX**: Manual extraction always ran as FULL mode — `extraction_mode` not passed in job parameters (commit `00ca6bb`)
- [ ] **Deeper issue**: Even in incremental mode, pipeline steps (contact upsert, signature fetch, role classification) reprocess ALL emails within scope — no per-record "already extracted" tracking. Incremental only narrows the date window (7-day lookback), not the record set. Acceptable for now since 7-day window is small enough (~500-1000 emails).
- [ ] Consider: add `last_extraction_at`-based filtering so incremental skips emails processed since last run, not just a fixed lookback window

### Known-issue cleanup (Week 1 fixes not yet done)

- [ ] `hello@carbon8.com.au` mailbox at 5.4% coverage — [D] deferred post-trip per scope doc
- [ ] 14 Carbon8 domain variants — [D] deferred post-trip per scope doc
- [ ] 21 weekdays with no email data investigation — [D] deferred post-trip

---

## AI config page hardening (added Apr 23)

- [x] Resolved dual-source-of-truth: `EMBEDDING_PROVIDER` env var is sole source of truth
- [x] Removed embedding model dropdown from AI config page (commit `f460729`)
- [x] Read-only status line shows `model_tag` from env (e.g. `openai/text-embedding-3-small-768`)
- [x] PUT `/embedding-config` endpoint removed; GET returns env var value only
- [x] LLM dropdowns kept (Email Analysis, Daily Digest, Strategic Digest, Entity Insights)
- [x] Grep verified: zero code paths read `embedding_provider`/`embedding_model` from system_settings
- [D] Consider storing model name on classification / digest / extraction rows for audit (post-trip)

---

## Insight engine — Week 2 core

### Cross-Company Gaps

- [ ] Revive `cross_gap_intelligence.py`
- [ ] Fix data joins (specific fixes TBD from code review)
- [ ] Verify output on 5 known Carbon8 companies
- [ ] Natural-language summary via digest prompt templates
- [ ] Time-box the revival: if join fixes exceed 6h, explicit rewrite-vs-patch decision

### Insights Review page shell

- [ ] Migration: `insight_validations` table
- [ ] Backend endpoint: list insights per contact / per company
- [ ] Backend endpoint: record validation (correct / partial / incorrect + notes)
- [ ] Frontend page: list view with NL summary + source data link per insight
- [ ] Frontend: validation buttons + optional notes field
- [ ] Source data link wiring: traceback to emails / quotes / jobs

---

## Insight engine — Week 3 core

### Seasonality Patterns

- [ ] Query design: annual ordering cycle per customer from QB quotes/jobs (10yr history)
- [ ] Backend endpoint
- [ ] Integration into Insights Review page
- [ ] Spot-check on 5 known seasonal customers

### Due for Reorder

- [ ] Query design: per-customer typical reorder cycle, approaching-window flag
- [ ] Backend endpoint
- [ ] Integration into Insights Review page
- [ ] Per scope doc: **first to drop if Week 3 compresses**

---

## Invite User flow — Week 3

- [ ] Migration 014: `pending_invites` + user table columns + RLS policies
- [ ] **RLS policy design:** anon-readable by token only, admin-listable via backend auth (flagged in earlier audit)
- [ ] Backend: 6 endpoints per design doc (`invites.py`)
- [ ] Frontend: InviteUserModal (two-step)
- [ ] Frontend: InviteAcceptPage (Paths A/B/C)
- [ ] Auth callback: invite detection hook
- [ ] Frontend: Users.tsx integration (pending invites merged into table, resend/revoke actions)
- [ ] Supabase config: `/invite/accept` and `/auth/callback` redirect URLs
- [ ] Tailwind+shadcn vs Ant Design decision (design doc is Ant; migration is ongoing)
- [ ] OAuth email-mismatch UX: what does user see when they sign in with a different email than the invite?
- [ ] Test matrix: 3 paths × 3 providers × 4 states (valid/expired/revoked/already-accepted)

---

## Stabilization — Week 3 tail + Week 4

- [ ] Runbook: how partner adds a new mailbox/user without your involvement
- [ ] Runbook: common failure modes and recovery (pipeline jobs, sync issues)
- [ ] Smoke test checklist for daily partner use
- [ ] Confirm cron-based sync runs autonomously during trip window
- [ ] Confirm two-worker Railway Pro setup handles peak load unattended
- [ ] Pre-trip freeze: no deploys after May 13 EOD

---

## Deferred to post-trip (explicit)

- [D] Industry Gap Analysis (Insight 2) — including its Week 1 distribution query validation
- [D] Real-time action signal alerts / Action Signal Engine
- [D] Role change notifications
- [D] Smart inbox revival
- [D] Vector search revival as user-facing feature
- [D] LinkedIn prospect replication
- [D] Daily/Strategic digest as user-facing features
- [D] AU seasonal calendar integration
- [x] Embedding config UI: dropdown removed, read-only status from env var (shipped Apr 24)
- [D] Classification/digest model audit columns
- [D] `hello@carbon8.com.au` classification coverage
- [D] 14 Carbon8 domain variant cleanup
- [D] 21-weekdays-no-data investigation
- [D] I/O budget fix (shared_buffers tuning, Redis caching for dashboard)
- [D] Dropped threads cleanup (thread recompute post-migration-080 verification)

---

## Open decisions (need answers before moving forward)

- [ ] Invite User UI: Ant Design (match design doc) or Tailwind+shadcn (match migration direction)
- [ ] Parent visit specific days — **still unresolved from scope lock doc**
- [x] Re-embed run scheduling: triggered Apr 24 evening; emails running, companies next; operations + quotes deferred

---

## Flags / risks being tracked

- Re-embed + title re-extraction + classification backfill = three big re-processing jobs stacked in Week 1 during a parent-visit week
- Cross-Gap revival may expand if join fixes reveal deeper schema issues
- Week 3 is doing 3 features + starting stabilization in 30h — tight
- Week 4 is 2 days of handoff only, not a full stabilization week
- Invite User realistic estimate (8-9d per my read) larger than Week 3 allocation can absorb; decision deferred per user
