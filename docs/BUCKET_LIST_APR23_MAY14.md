# Bucket List: Actions Through May 14, 2026

**Purpose:** Tracking all planned work items for the current sprint.
**Status convention:** [ ] not started / [~] in progress / [x] done + verified / [D] deferred next sprint

---

## Week Allocation

| Week | Dates (Wed–Tue) | Hours | Focus |
|------|-----------------|-------|-------|
| Week 1 | Apr 23 – Apr 29 | ~20h | Data hardening, embedding re-embed, AI classification backfill |
| Week 2 | Apr 30 – May 6 | ~30h | Cross-Company Gaps end-to-end, Insights Review page shell, validation capture |
| Week 3 | May 7 – May 13 | ~30h | Seasonality integration, Due for Reorder, Invite User flow, stabilization starts |
| Week 4 | May 14 | ~10h | Final stabilization — smoke tests, buffer |

**Discipline:** Features freeze end of Week 3 (May 13). If Week 3 compresses, drop Due for Reorder first. If Week 2 compresses, keep Cross-Gap + Insights Review page minimum.

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
- [x] IVFFlat index built on emails (lists=500, 1013 MB) — HNSW abandoned; fails on Supabase Pro at disk-spill phase
- [x] `ivfflat.probes = 10` set at database level via `ALTER DATABASE postgres SET ivfflat.probes = 10`
- [x] Functional test: top-10 similarity returns semantically related results (~140ms, probes=10)
- [x] `DATABASE_DESIGN.md` updated: vector embedding architecture (§5.5), index choice rationale (§5.6), build operations (§5.7), forbidden operations (§5.8), migration history 094–097
- [ ] **Investigate before next bulk re-embed:** companies run required 4 manual clicks to reach 100%. Single job appears to terminate early without exhausting the table. Worth checking worker logs for completion semantics before any next sprint 615K operations re-embed.
- [ ] Spot-check semantic search quality on 20 known queries
- [ ] Next sprint: revisit HNSW with raised `maintenance_work_mem` if IVFFlat recall proves insufficient
- [ ] Next sprint: investigate apparent duplicate emails surfaced during sanity test (rows `a9ad862f` and `f5714636` share identical subject + similarity score)
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

- [x] Backfill handler: concurrent mailbox processing (CONCURRENCY=3, asyncio.gather + Semaphore), BATCH_SIZE 20→50→100 (OpenAI Tier 2 rate limits)
- [x] 4 production fixes mid-run: PyYAML/Python 3.13 wheel, ref-linking PostgREST limit, concurrent prefetch connection exhaustion, HTTP/2 trailer retry
- [x] Multi-slot backfill (SLOTS_PER_MAILBOX=2) — each mailbox gets 2 concurrent analyzers. Tuned CONCURRENCY 5→3 after Supabase pressure
- [x] Per-mailbox classify button on Data Health page (lightning bolt per row)
- [x] Fix: backfill skipping emails with NULL `sent_date` (commit `fdcd509`)
- [x] Backfill CHUNK reduced 10K→200 so stop_event is checked every ~2min instead of hours (commit `eb544a0`)
- [~] Apr 30: 162K/260K classified (75.7%). Nic, Jeff, Production PC at 100%. Remaining backlog: hello@ 46K, ehab@ 14K, kenneth@ 1.3K, Linda 828
- [ ] Top up OpenAI credit if burn rate × remaining > remaining balance

### Pipeline + data integrity bugs (identified Apr 29–30)

- [x] **BUG FIX**: Manual extraction always ran as FULL mode — `extraction_mode` not passed in job parameters (commit `00ca6bb`)
- [x] **BUG FIX**: Emails inserted without `client_id` during sync — `batch_insert_emails` never set it, causing invisible rows in health RPC counts (commit `354dd1a`)
- [x] **BUG FIX**: `ai_email_intelligence` records written with NULL `client_id` when email lacked it — analyzer now resolves from mailbox table (commit `1adfff4`)
- [x] **BUG FIX**: NULL `client_id` data backfill — updated all existing NULL rows in both `emails` and `ai_email_intelligence` from mailbox's client_id
- [x] **QUICK WIN**: Moved `ai_classify` + `bucket_engine` to steps 2-3 in pipeline (was steps 6-7) — new emails get classified before heavy extraction steps that may timeout
- [x] **Pipeline reorder**: Moved `ai_classify` + `bucket_engine` to steps 1-2 (before `extract_and_link`) — classification now runs first with no extraction dependency
- [x] **email_categories cleanup**: Removed `_get_rule_based_skip_ids` and `_enrich_with_rule_based_tags` from AI analyzer — legacy file-import-only dependencies that added overhead for live-synced emails
- [x] **Removed PRE-CLASSIFICATION HINTS** from system prompt — no code populates `pre_classification` after email_categories cleanup
- [x] **Surgical fix**: Migration 098 adds `extracted_at` column to emails table + partial index. Incremental extraction now skips emails where `extracted_at IS NOT NULL`. After step 9, stamps `extracted_at` on all processed emails. Reduces incremental scope from ~270K to ~50/day steady state.

### Worker infrastructure (Apr 29)

- [x] Fixed Railway health check killing worker services — removed global `healthcheckPath` from `railway.toml` (per-service config in `deploy/railway/railway.toml` already correct)
- [x] Verified: `WORKER_ID` env var not required — auto-generates from `{hostname}-{pid}`; job claiming has no worker-id filtering

### Known-issue cleanup (Week 1 fixes not yet done)

- [D] `hello@carbon8.com.au` mailbox at 5.4% coverage — deferred next sprint
- [D] 14 Carbon8 domain variants — deferred next sprint
- [D] 21 weekdays with no email data investigation — deferred next sprint

---

## AI config page hardening (added Apr 23)

- [x] Resolved dual-source-of-truth: `EMBEDDING_PROVIDER` env var is sole source of truth
- [x] Removed embedding model dropdown from AI config page (commit `f460729`)
- [x] Read-only status line shows `model_tag` from env (e.g. `openai/text-embedding-3-small-768`)
- [x] PUT `/embedding-config` endpoint removed; GET returns env var value only
- [x] LLM dropdowns kept (Email Analysis, Daily Digest, Strategic Digest, Entity Insights)
- [x] Grep verified: zero code paths read `embedding_provider`/`embedding_model` from system_settings
- [D] Consider storing model name on classification / digest / extraction rows for audit (next sprint)

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
- [ ] **First to drop if Week 3 compresses**

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
- [x] UI framework decision: Tailwind + shadcn/ui (matches migration direction)
- [ ] OAuth email-mismatch UX: what does user see when they sign in with a different email than the invite?
- [ ] Test matrix: 3 paths × 3 providers × 4 states (valid/expired/revoked/already-accepted)

---

## Stabilization — Week 3 tail + Week 4

- [ ] Smoke test checklist for daily partner use
- [ ] Confirm cron-based sync runs autonomously
- [ ] Confirm two-worker Railway Pro setup handles peak load unattended
- [ ] Deploy freeze after May 13 EOD

---

## Carryover from Apr 16–22 sprint (to be prioritised)

Items moved from `BUCKET_LIST_APR16_APR22.md` — not yet scheduled into a specific week.

### External cron registration

- [ ] Configure Railway cron or cron-job.org to call internal endpoints (qb-sync hourly, analytics-rollup daily, stuck-reconciler 10min, notification-dispatch 2min)
- [ ] Set `CRON_SECRET` env var in production
- [ ] Verify: cron-based sync runs autonomously (overlaps with stabilization checklist)

### Staged worker rollout

- [ ] Staged rollout: analytics → QB sync → reembed → remaining job types
- [ ] Verify all Tier 2 BackgroundTasks callsites work correctly alongside workers

### Operations Center UI consolidation (W7)

- [ ] Final merge plan: which features stay, which retire, which consolidate
- [ ] Move operational triggers from AI Usage (re-analysis, re-embed, re-bucket) into Data Health
- [ ] Move extraction features from Extraction page into Data Health
- [ ] Add pipeline status monitoring (email_pipeline jobs per mailbox)
- [ ] Retire standalone Extraction page (redirect to Data Health)
- [ ] AI Usage page keeps only: config/model selection, cost monitoring, prompt templates
- [ ] "Run Full Pipeline" button (creates `email_pipeline` job for selected mailbox)
- [ ] Pipeline progress visualization (8 steps with completion status)

### Contact Persona Metrics (C1)

- [ ] SQL views: `contact_quote_metrics`, `contact_email_metrics` (materialized), `contact_persona`
- [ ] Rollup views: `company_contact_summary`, `industry_benchmarks`
- [ ] Materialized view refresh job (daily + post-QB-sync)
- [ ] API endpoints: persona, contact-summary, industry-benchmarks

### Contact Persona Frontend (C2)

- [ ] Contact Profile Card (identity + QB metrics + email behavior + persona + benchmarks)
- [ ] Company Profile: "Contact Breakdown" section
- [ ] Industry Dashboard
- [ ] Journey Timeline integration on profile pages

### Status Transition Analytics (C3) — blocked until ~July 2026

- [ ] Time-in-phase metrics per job and per contact
- [ ] Bottleneck detection (status stuck > threshold)
- [ ] Production cycle time: quote acceptance → job completion

---

## Deferred to next sprint

- [D] Industry Gap Analysis (Insight 2) — including its Week 1 distribution query validation
- [D] Real-time action signal alerts / Action Signal Engine
- [D] Role change notifications
- [D] Smart inbox revival
- [D] Vector search revival as user-facing feature
- [D] LinkedIn prospect replication
- [D] Daily/Strategic digest as user-facing features
- [D] AU seasonal calendar integration
- [D] Classification/digest model audit columns
- [x] `email_categories` AI analyzer cleanup — removed `_get_rule_based_skip_ids` and `_enrich_with_rule_based_tags` dependencies from classification path. Table + tagger + display routes kept for file-imported email data.
- [D] `hello@carbon8.com.au` classification coverage
- [D] 14 Carbon8 domain variant cleanup
- [D] 21-weekdays-no-data investigation
- [D] I/O budget fix (shared_buffers tuning, Redis caching for dashboard)
- [D] Dropped threads cleanup (thread recompute post-migration-080 verification)

---

## Flags / risks being tracked

- ~~**Pipeline throughput**~~: **RESOLVED** — ai_classify moved to step 1 (runs before extraction), `extracted_at` column added so incremental extraction skips already-processed emails, email_categories legacy dependency removed from classification path
- **Classification backlog**: 62K emails pending (hello@ 46K, ehab@ 14K). At current rate (~330/hr), needs ~190 hours of continuous backfill
- Cross-Gap revival may expand if join fixes reveal deeper schema issues
- Week 3 is doing 3 features + starting stabilization in 30h — tight
- Week 4 is 2 days of handoff only, not a full stabilization week
- Invite User realistic estimate (8-9d) larger than Week 3 allocation can absorb
- Carryover items (W7, C1, C2) are substantial features — need explicit prioritisation decision before Week 2 starts
