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
- [x] Migration 100: contact date backfill — `update_contact_email_counts_from_junction` RPC now also sets `first_contacted_at`/`last_contacted_at` from email dates (17,405 contacts updated)
- [x] Migration 101: persona classification v2 — champion rule (≥10 accepted OR ≥$50K jobs), shared_mailbox classification for non-person contacts, split active_relationship → active_buyer + warm_lead, `contact_type` column added to `contact_persona` view
- [x] Pipeline extraction_mode fix: startup sweep resume jobs now preserve original `extraction_mode` from interrupted job params (was defaulting to "full")
- [x] Company profile inline contacts: contacts table embedded in company detail page using `contact_persona` view (PersonaBadge, engagement, email stats, quotes)
- [x] Unified contacts views: contacts list page + company profile use consistent columns with shared `PersonaBadge` component

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
- [D] **Investigate before next bulk re-embed:** companies run required 4 manual clicks to reach 100%. Single job appears to terminate early without exhausting the table. Worth checking worker logs for completion semantics before any next sprint 615K operations re-embed. — deferred, not blocking
- [D] Spot-check semantic search quality on 20 known queries — deferred
- [D] Next sprint: revisit HNSW with raised `maintenance_work_mem` if IVFFlat recall proves insufficient — deferred
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
- [x] May 12: 217K/271K classified (99.9% overall). All mailboxes 99.7%+. Only 337 pending across all mailboxes
- [x] Top up OpenAI credit — classification effectively complete

### Pipeline + data integrity bugs (identified Apr 29–30)

- [x] **BUG FIX**: Manual extraction always ran as FULL mode — `extraction_mode` not passed in job parameters (commit `00ca6bb`)
- [x] **BUG FIX**: Emails inserted without `client_id` during sync — `batch_insert_emails` never set it, causing invisible rows in health RPC counts (commit `354dd1a`)
- [x] **BUG FIX**: `ai_email_intelligence` records written with NULL `client_id` when email lacked it — analyzer now resolves from mailbox table (commit `1adfff4`)
- [x] **BUG FIX**: NULL `client_id` data backfill — updated all existing NULL rows in both `emails` and `ai_email_intelligence` from mailbox's client_id
- [x] **QUICK WIN**: Moved `ai_classify` + `bucket_engine` to steps 2-3 in pipeline (was steps 6-7) — new emails get classified before heavy extraction steps that may timeout
- [x] **Pipeline reorder**: Moved `ai_classify` + `bucket_engine` to steps 1-2 (before `extract_and_link`) — classification now runs first with no extraction dependency
- [x] **email_categories cleanup**: Removed `_get_rule_based_skip_ids` and `_enrich_with_rule_based_tags` from AI analyzer — legacy file-import-only dependencies that added overhead for live-synced emails
- [x] **Removed PRE-CLASSIFICATION HINTS** from system prompt — no code populates `pre_classification` after email_categories cleanup
- [x] **Surgical fix**: Migration 098 adds `extracted_at` column to emails table + partial index. Incremental extraction now skips emails where `extracted_at IS NOT NULL`. After step 9, stamps `extracted_at` on all processed emails. Reduces incremental scope from ~270K to ~50/day steady state. (applied to prod Apr 30)
- [x] **Scoped extraction**: ContactExtractor and EmailLinker now receive only scoped email IDs in incremental mode. Previously scanned all 143K+ emails (117 min); now processes only new emails via `_get_emails_in_scope()`. Role classifier also benefits — fewer contacts = fewer signature lookups (commit `1b2bfd9`)
- [x] **BUG FIX**: `link_ai_refs` pipeline step re-processed ALL classified emails with extracted_references (6,412 for Ehab, 3,419 for hello@) on every run — 20K+ DB round-trips causing Server disconnected after 5-30min. Fixed: scoped to 7-day window via `processed_at` filter + batch validation (1-2 bulk queries instead of per-row). (commit `0edd402`)
- [x] **PERF**: `link_ai_refs` batch upsert — per-thread `_upsert_links` N+1 pattern (3,000+ individual calls = 9,000+ HTTP calls, 8min timeout) replaced with collect-then-batch-upsert in chunks of 200 (~15 calls). Total HTTP calls reduced ~85% (9,000→1,550). (commit `53303b2`)
- [x] **BUG FIX**: Step 6 QB enrichment had PostgREST 1000-row default limit — only enriching ~10% of matched records (9,657 companies, 12,772 contacts). Also did 22K per-row HTTP UPDATE calls (30+ min). Fixed: single SQL UPDATE...FROM join per table — processes all rows in seconds. (commit `f9970c0`)
- [x] **NULL `client_id` backfill for hello@**: 134K emails had NULL `client_id` causing health dashboard to show 159.2% coverage. Backfill complete (100,113 rows updated May 1)
- [x] **Script**: `scripts/db/_link_ai_refs_full.py` — on-demand QB reference linking for full mailbox history with `--lookback N` option
- [x] **PERF**: AI classification batch writes — `_mark_processing`, `_save_completed`, `_save_failed` all converted from per-row upserts to batch upserts (100 HTTP calls → 1-2 per batch). Classification write phase drops from 5-10s to <500ms. (commit `0e6e58e`)
- [x] **PERF**: Extraction orchestrator — `_link_orphan_contacts` grouped by company `.in_()`, `_step_update_company_stats` uses SQL `UPDATE...FROM VALUES` instead of per-company HTTP calls (commit `0e6e58e`)
- [x] **QB ref extraction prompt tightened**: min 4-6 digits for quotes, 5-6 for jobs, exclude placeholders (Q12345/J123456), add valid range caps (Q5-Q800000, J32-J500000). Updated in code + `ai_prompt_config` DB row for Carbon8 client. Eliminates 18% false positives (2,716 occurrences). (commit `74e04ef`)
- [x] **BUG FIX**: Data Health per-mailbox link stats — RPC 099 v2 adds lateral join through `emails → thread_qb_links` for per-mailbox linked/threads/link_rate. Was showing 0 linked across all mailboxes despite 6,142 total links. (commit `74e04ef`)
- [x] **Diagnostic**: `scripts/db/_diagnose_ref_gaps.py` — separates false positives (short digits, placeholders, above-range) from real sync gaps in unmatched QB references. Findings: 61.5% matched, 18% false positive, 20.4% real gaps
- [x] **HOW_IT_WORKS.md**: Full documentation of AI reference extraction + linking flow (Prompt → Store → Link phases, normalization, bulk validation, pipeline vs full mode, diagnostic findings)

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

### Cross-Company Gaps — ✅ DONE

- [x] Integrated into `RecommendationEngine` (not revived as standalone `cross_gap_intelligence.py`). Revenue concentration + buyer decay risk analysis via `contact_persona` view
- [x] Data quality fixes: excluded shared/automated/mailing_list contacts, deduped by email, flagged domain mismatches (`08f71d3`)
- [x] Lifted from 48 raw operations to ~7 `qb_capability_tag` categories — `already_buys` + `untapped_capabilities` per contact (`f17b530`)
- [x] Revenue concentration risk: companies with >$100K revenue but ≤2 contacts producing orders. Buyer decay risk: top buyer persona = inactive_buyer
- [x] Portfolio-wide scan via `GET /customers/portfolio-insights` endpoint
- [x] Revenue insight + capability gaps surfaced on company profile (Sales Opportunities card)
- [x] Company profile reorganized: action-first layout, semantic widget pairs (Performance, Capabilities, Deep Dive) (`71858a1`)
- [x] AI Insights composite strategic summary: LLM now receives strike rate, seasonality, revenue risk, capability gaps as context → produces `strategic_summary` narrative (`24d90b2`)
- [x] Revenue framing fix: prompt + context labels clarified that figures = what we invoice TO the customer (`f0522d1`)
- [x] Migration 103: updated `insight_company` prompt in `ai_prompt_config` (global + Newbound + Carbon8 rows)

### Security — RLS Enforcement (added May 5) — ✅ DONE

- [x] Migration 102: `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` on all 49 public tables (`6305727`, `b1641d4`)
- [x] Critical exposure closed: `system_settings` (API keys), `clients` (QB tokens), `qb_sync_config`, `user_integrations` (OAuth tokens) — all were readable via anon key
- [x] Verified: anon key returns 0 rows on all tested tables; service_role key retains full access
- [x] Views/matviews show UNRESTRICTED badge in Supabase dashboard (Postgres limitation) — inherit protection from RLS-enabled base tables
- [x] `DATABASE_DESIGN.md` §8 rewritten with full RLS status, views table, migration 102 (`20ca1ef`)
- [x] `BEST_PRACTICES.md` §9 added: RLS on every new table, SECURITY DEFINER search_path, secret exposure prevention

### Pipeline reliability fixes (May 5–6) — ✅ DONE

- [x] Classification health RPC 089 v2: overcounting fix — scoped by `mailbox_id` instead of `client_id` (hello@ showed 210.7%) (`1447c3e`)
- [x] `link_ai_refs` batch dedup: same QB number in multiple emails → "ON CONFLICT cannot affect row a second time" → added `seen_keys` set (`1447c3e`)
- [x] Extraction orchestrator: incremental mode with zero new emails raised ValueError → now completes gracefully with `skipped=True` (`c66c708`)

### Contact table enrichment (May 5) — ✅ DONE

- [x] Contacts list + company profile: added Strike %, Job Value columns (`8a1ad57`)
- [x] Backend: extended persona batch lookup to include `strike_rate`, `accepted_quote_count`, `total_job_value` from `contact_persona` view

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

### External cron registration — ✅ DONE

- [x] Configure Railway cron services (7 total): gmail-sync, outlook-sync, qb-sync, notification-dispatch, stuck-reconciler, refresh-persona-metrics, analytics-rollup
- [x] Set `CRON_SECRET` env var on all cron services + backend
- [x] `docs/CRON_SETUP.md` fully rewritten: step-by-step Railway cron creation, worker deployment section, env var reference
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

### Contact Persona Metrics (C1) — ✅ DONE

- [x] SQL views: `contact_quote_metrics`, `contact_email_metrics` (materialized), `contact_persona` (migration 088)
- [x] Rollup views: `company_contact_summary`, `industry_benchmarks` (migration 088)
- [x] Materialized view refresh job (daily + post-QB-sync) via `POST /internal/jobs/refresh-persona-metrics`
- [x] API endpoints: persona, contact-summary, industry-benchmarks (`contacts_intelligence.py`)
- [x] Persona classification v2 (migration 101): champion rule fix, shared_mailbox classification, active_buyer/warm_lead split
- [x] Contact date backfill (migration 100): `update_contact_email_counts_from_junction` RPC now sets `first_contacted_at`/`last_contacted_at`

### Contact Persona Frontend (C2) — ✅ DONE

- [x] Contact Profile Card (PersonaCard + DealActivityCard on contact detail page)
- [x] Company Profile: inline contacts table with persona badges, engagement, email stats, quotes
- [x] Unified contacts views: contacts list page + company profile contacts section use same columns and PersonaBadge component
- [x] PersonaBadge shared component: 8 classifications (champion, active_buyer, active_relationship, warm_lead, prospect, inactive_buyer, dormant, shared_mailbox)
- [ ] Industry Dashboard
- [ ] Journey Timeline integration on profile pages

### Status Transition Analytics (C3) — blocked until ~July 2026

- [ ] Time-in-phase metrics per job and per contact
- [ ] Bottleneck detection (status stuck > threshold)
- [ ] Production cycle time: quote acceptance → job completion

---

## QB Match Review Page + Data Cleanup — May 11 session + follow-up

### QB Match Review page enhancements (May 11) — ✅ DONE

- [x] Search box: real-time search across QB customer names and SB company names (300ms debounce, backend passthrough)
- [x] Email count sort: sortable EMAILS column header on matched and candidates views (in-memory sort with full-fetch)
- [x] Revenue sort fix: `qb_total_revenue` → `total_invoiced` mapping corrected for all views
- [x] Method filter dropdown on matched tab: filter by match method (Email, Contact chain, QB create, QB link, etc.)
- [x] Migration 109: candidate unique index fix — added `sb_company_id` to allow multi-match candidates per QB customer

### Data cleanup (May 11) — ✅ DONE

- [x] Merged 35 case-variant duplicate companies via bulk merge script (`scripts/db/bulk_merge_case_dupes.py`)
- [x] Migration 110: CITEXT on `customer_companies.company_name` — prevents future case-variant duplicates (dropped/recreated 5 dependent views)
- [x] Code guard in `company_resolver.py`: upsert preserves existing DB name casing on update
- [x] Decontamination re-run: 2,642 junk links auto-unlinked, 565 multi-revenue cases flagged for manual review
- [x] Revenue match coverage at 95.5% ($58.1M / $60.8M)

### Follow-up (May 12+)

- [ ] **Email-method SB name correction** — ~4,250 email-matched QB customers have wrong SB company names (Carbon8 staff emails create false links between unrelated QB customers and SB companies). Needs: name-similarity guard on email_lookup + batch correction script
- [ ] **Method filter dropdown fix** — dropdown values are stale (`exact_name`, `domain_root`, `qb_anchored_link`, `qb_anchored_create` don't match actual DB values `qb_create`, `qb_link`). Also 2 "unknown" method records to investigate/fix
- [ ] **Automate candidate review** — 972 staged candidates (exact name, domain, fuzzy matches) could be auto-promoted where confidence is high (e.g. exact name + same domain = auto-accept), reducing manual review backlog
- [ ] **Contamination cleanup** — 727 contaminated companies remaining (down from 1,059), 565 multi-revenue cases need manual review or smarter heuristics (e.g. pick highest-revenue QB customer as primary)
- [ ] **Build Top-N page** — from Insights Review shell; frontend page listing top customers with NL insight summaries + source data links
- [ ] **Ship validation buttons on insights** — from Insights Review shell; correct/partial/incorrect buttons + optional notes on insight cards
- [ ] **Manual spot-check 5-10 customer profile pages** — verify data accuracy, insight quality, QB data display after all cleanup
- [ ] **Update HOW_IT_WORKS.md** — CITEXT migration, match method changes, decontamination process
- [ ] **Update DATABASE_DESIGN.md** — CITEXT column type on company_name, migration 109-110

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
- [x] `hello@carbon8.com.au` classification coverage — 99.9% (114,075/144,672 classified, 149 pending, May 12)
- [D] 14 Carbon8 domain variant cleanup
- [D] 21-weekdays-no-data investigation
- [D] I/O budget fix (shared_buffers tuning, Redis caching for dashboard)
- [D] Dropped threads cleanup (thread recompute post-migration-080 verification)

---

## Flags / risks being tracked

- ~~**Pipeline throughput**~~: **RESOLVED** — ai_classify moved to step 1 (runs before extraction), `extracted_at` column added so incremental extraction skips already-processed emails, email_categories legacy dependency removed, `link_ai_refs` scoped to 7-day window + batch validation
- ~~**Classification backlog**~~: **RESOLVED** — 99.9% coverage (217K/271K), only 337 pending across all mailboxes (May 12)
- ~~**hello@ client_id backfill**~~: **RESOLVED** — 134K emails backfilled (May 1), all mailboxes at 0 NULL
- ~~**AI Link References per-mailbox view**~~: **RESOLVED** — RPC 099 v2 adds per-mailbox link stats. ehab@ 36.6%, Linda 38.8%, hello@ 27.2%
- **AI ref extraction quality**: Prompt tightened May 5. 20.4% of refs are "real gaps" (valid QB numbers not in synced data — ~32K quotes not synced). Improvement requires QB sync scope expansion or acceptance
- ~~**Cross-Gap revival**~~: **RESOLVED** — Integrated into RecommendationEngine at capability level. Revenue concentration + buyer decay risk analysis added. AI Insights now produces composite strategic summary
- ~~**RLS security exposure**~~: **RESOLVED** — Migration 102 enables RLS on all 49 public tables. Anon key returns 0 rows everywhere
- ~~**Classification health overcounting**~~: **RESOLVED** — RPC 089 v2 scoped by mailbox_id, link_ai_refs dedup, extraction zero-email graceful skip
- Week 3 is doing 3 features + starting stabilization in 30h — tight (Cross-Gap now done, frees ~10h)
- Week 4 is 2 days of handoff only, not a full stabilization week
- Invite User realistic estimate (8-9d) larger than Week 3 allocation can absorb
- Carryover items (W7, C1, C2) are substantial features — need explicit prioritisation decision
