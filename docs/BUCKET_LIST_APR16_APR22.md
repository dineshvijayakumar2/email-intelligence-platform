# Implementation Roadmap: Multi-Worker + Contact Intelligence + Journey Tracking

**Created:** 2026-04-16
**Updated:** 2026-04-19
**Status:** Active — tracking implementation progress
**Source docs:** `docs/background-work-rfc.md`, `docs/contact-intelligence-design.md`, `docs/pipeline-design.md`

## Priority Order

1. Multi-worker infrastructure (Background Work RFC)
2. Thread-QB journey linking (emails trackable through to jobs + invoices)
3. Contact persona metrics + UI

---

## Current State (Updated 2026-04-17)

### Worker infrastructure — LIVE
- **Worker process** deployed on Railway as `job-worker` service (1 replica)
- **claim_next_job RPC** — `SELECT FOR UPDATE SKIP LOCKED`, 5-min lease, 30s heartbeat
- **Reconciler** — marks expired-lease jobs as `interrupted` every 10 min; extended to handle NULL-lease BackgroundTasks jobs stuck >2 hours (migration 084 updated 2026-04-17)
- **Multi-worker verified** — tested with 2 replicas, concurrent claiming works
- **Events + Notifications tables** — created (migrations 085, 086)
- **Thread-QB linking** — table + regex extractor + journey API + UI created

### Critical fixes shipped (2026-04-17, commit `b7f1486`)

1. **Pipeline auto-trigger fix** — Cron sync path (`_sync_user()`) in both Gmail and Outlook services was missing the `_trigger_post_sync_extraction()` call. Emails synced via cron were never classified/embedded. Now both `_sync_user()` and `_sync_mailbox()` trigger the extraction pipeline.
2. **8 hybrid callsites protected** — Endpoints that create jobs and execute via `BackgroundTasks` now set `initial_status="running"` to prevent the worker from claiming jobs it has no handler for. Affected: `gmail_date_range_fetch` (gmail.py, analytics.py), `outlook_date_range_fetch` (outlook.py, analytics.py), `reprocessing` (mailboxes.py, processing_jobs.py ×3), `analytics_rollup_daily` (internal_jobs.py).
3. **Reconciler extended for NULL-lease jobs** — Migration 084 updated: BackgroundTasks jobs (`lease_expires_at IS NULL`, `worker_id IS NULL`, stuck running >2 hours) are now caught and marked `interrupted`.
4. **Embed thread safety fix** — `_embed_new_emails()` in `extraction_orchestrator.py` replaced fragile `asyncio.get_event_loop().run_until_complete()` with `asyncio.run()`, which safely creates a new event loop in ThreadPoolExecutor threads (Python 3.13 compatibility).

### Email Pipeline Handler — ✅ DEPLOYED (2026-04-19)
- Design doc: `docs/pipeline-design.md`
- Handler: `backend/src/workers/handlers/email_pipeline.py`
- 8-step pipeline: extract_and_link → assign_threads → evaluate_threads → refresh_counts → embed_emails → ai_classify → bucket_engine → evaluate_threads_final
- **Single-flight dedup**: partial unique index `uq_email_pipeline_per_mailbox` (migration 087)
- **Resumable**: `completed_steps` persisted in `parameters` JSONB after every stage
- **Startup sweep**: worker auto-resumes interrupted pipelines on boot (preserves completed_steps)
- **Observability hardened**: `_persist_progress` retries 3x with backoff, raises `ProgressPersistError` on exhaustion (fail-fast preserves last-known-good checkpoint)
- **max_attempts=1**: no retry-from-scratch; startup sweep is the recovery path
- **extraction_mode='full'**: processes all unextracted emails (not limited to 7-day lookback)
- All 4 sync trigger points replaced (Gmail + Outlook, both `_sync_mailbox` and `_sync_user`)
- Date-range fetch auto-triggers pipeline; max_emails cap removed
- Analytics.py "Run" button rewired to pipeline

### Callsite migration status

**Tier 1 — Migrated to worker (handler exists, router creates pending job):**
| Job Type | Handler | Router | Verified |
|----------|---------|--------|----------|
| `ai_backfill` | `handlers/ai_backfill.py` | ai.py | ✅ Production verified: heartbeat, completion, worker_id |
| `ai_analysis` | `handlers/ai_analysis.py` | ai.py | Deployed, pending verification |
| `reembed` | `handlers/reembed.py` | — | Handler exists, router NOT migrated |
| `notification_dispatch` | `handlers/notification_dispatch.py` | — | ✅ Verified (sub-second jobs) |
| `reference_extraction` | `handlers/reference_extraction.py` | — | Handler exists, no UI trigger yet |

**Tier 2 — Still running via BackgroundTasks (protected with `initial_status="running"`):**
| Job Type | Callsite | Complexity | Notes |
|----------|----------|------------|-------|
| `reprocessing` | mailboxes.py:330, processing_jobs.py:350,451,708 | High | Outlook-only, OAuth tokens, extractor |
| `gmail_date_range_fetch` | gmail.py:623, analytics.py:3623 | High | OAuth tokens, GmailExtractor |
| `outlook_date_range_fetch` | outlook.py:624, analytics.py:3626 | High | OAuth tokens, OutlookExtractor |
| `strategic_digest` | ai.py:1282 | Medium | LangGraph agent, SSE streaming |
| `gmail_sync` | gmail.py:388,811,1173 | High | OAuth, incremental historyId |
| `outlook_sync` | outlook.py:403,504,1047 | High | OAuth, delta links |

**Tier 3 — Lightweight ops (no job tracking, low priority):**
| Operation | Callsite | Notes |
|-----------|----------|-------|
| Reanalysis | ai.py:333 | Re-classify emails with updated prompt |
| Rebucket | ai.py:508 | Re-run bucket engine |
| Thread resolve | analytics.py:182 | Resolve thread metadata |
| Recompute engagement | analytics.py:269 | Recalculate engagement scores |
| Backfill analytics | analytics.py:480 | Backfill response times |
| QB sync | quickbase.py:238 | Full QB table sync |
| QB affinity | quickbase.py:724 | Product affinity calculation |
| QB rematch | quickbase.py:835 | Re-run company matching |
| QB propagate | quickbase.py:1351 | Propagate QB data to contacts |
| Internal QB sync | internal_jobs.py:66 | Cron-triggered QB sync |
| Generic extraction | processing_jobs.py:383,735 | Email processing pipeline |

### Key lessons from worker migrations
1. **asyncio.to_thread() is mandatory** for sync blocking calls — without it, heartbeat starves and lease expires
2. **max_attempts=1 for long pipelines** — retry-from-scratch wastes hours of work; startup sweep with preserved `completed_steps` is the recovery path
3. **httpx INFO logs flood worker output** — suppressed to WARNING level
4. **notification_dispatch had wrong column name** (`user_id` vs `id` on user_profiles) and wrong filter syntax (string vs Python list for `.contains()`)
5. **BackgroundTasks jobs must use `initial_status="running"`** — otherwise worker claims them and fails with "Unknown job_type"
6. **`asyncio.run()` not `get_event_loop().run_until_complete()`** — the latter silently fails in ThreadPoolExecutor threads on Python 3.13
7. **No `except Exception: pass`** — silent swallowing hides observability failures; every handler must log or raise (audit found 13 locations, all hardened 2026-04-19)
8. **`_persist_progress` is the keystone** — if checkpoint writes fail silently, resume can't work; now retries 3x then raises `ProgressPersistError` (fail-fast)

---

## Phase W1: Worker Schema + Job Factory (Week 1-2)

**Goal:** Unified job creation and the DB schema that workers will claim from.

### W1.1 — Migration: processing_jobs extensions
- [x] Add columns: `last_heartbeat_at`, `worker_id`, `lease_expires_at`, `attempts`, `max_attempts`, `scheduled_for`, `triggered_by`
- [x] Add index: `idx_processing_jobs_claimable` (partial: pending OR expired lease)
- [x] Add index: `idx_processing_jobs_active_lease` (partial: running)
- [x] Add per-job-type dedup indexes (extend reembed pattern from migration 074)

**File:** `scripts/migrations/083_worker_infrastructure.sql`

### W1.2 — Job Factory
- [x] Create `backend/src/services/jobs/factory.py` — `JobSpec` model + `create_job()` entry point
- [x] Handle dedup (catch unique violation -> `JobAlreadyActive`)
- [x] Handle defaults, validation, audit

### W1.3 — Migrate callsites to factory
- [x] `reembed` (reembed_job_state.py)
- [x] `ai_analysis` / `ai_backfill` (ai.py)
- [x] `strategic_digest` (ai.py)
- [x] `reprocessing` (mailboxes.py, processing_jobs.py) — uses factory but runs via BackgroundTasks
- [x] `gmail_sync` / `outlook_sync` (sync services) — uses factory but runs via BackgroundTasks
- [x] `gmail_date_range_fetch` / `outlook_date_range_fetch` — uses factory but runs via BackgroundTasks
- [x] Generic extraction (processing_jobs.py) — uses factory but runs via BackgroundTasks

---

## Phase W2: Worker Process (Week 2-3)

**Goal:** Standalone worker process that claims and executes jobs from the DB.

### W2.1 — Worker core
- [x] Create `backend/src/workers/job_runner.py` — main loop (claim, execute, heartbeat)
- [x] Claim query: `SELECT FOR UPDATE SKIP LOCKED`
- [x] Lease: 5 min, heartbeat every 30s
- [x] Graceful shutdown: SIGTERM sets flag, current job completes

### W2.2 — Job handler registry
- [x] Create `backend/src/workers/handlers/__init__.py` — `JOB_HANDLERS` dict
- [x] Map each `job_type` to handler function

### W2.3 — Stuck-job reconciler
- [x] `reconcile_stuck_jobs` RPC (migration 084) marking expired-lease jobs as `interrupted`
- [x] Reconciler loop in worker process (runs every 10 min)
- [x] Extended reconciler for NULL-lease BackgroundTasks jobs (stuck running >2h with no worker_id)

### W2.4 — Migrate first job type to worker
- [x] Extract `reembed` execution into worker handler (`handlers/reembed.py`)
- [x] Keep BackgroundTasks as fallback for remaining types

---

## Phase W3: Scheduler (Week 3-4)

**Goal:** Automated job scheduling via external cron (Railway/cron-job.org).

### W3.1 — Verify pg_cron + pg_net on Supabase
- [x] Checked: pg_cron and pg_net NOT available on current Supabase tier
- [x] Decision: use external HTTP cron instead (same pattern as Gmail/Outlook sync)

### W3.2 — Internal endpoints
- [x] Create `backend/src/routers/internal_jobs.py`
- [x] `POST /internal/jobs/qb-sync` (hourly)
- [x] `POST /internal/jobs/analytics-rollup` (daily 2am)
- [x] `POST /internal/jobs/stuck-reconciler` (every 10 min)
- [x] Auth via `verify_cron_secret` dependency in `auth.py`

### W3.3 — External cron registration
- [x] `POST /internal/jobs/notification-dispatch` endpoint (every 2 min)
- [x] Cron setup documentation: `docs/CRON_SETUP.md` with full schedule and examples
- [ ] Configure Railway cron or cron-job.org to call internal endpoints
- [ ] Set `CRON_SECRET` env var in production

---

## Phase W4: Notifications — Phase A (Week 4-5)

**Goal:** In-app notifications via WebSocket, event-driven.

### W4.1 — Events + Notifications schema
- [x] Migration `085_events_notifications.sql` (events + notifications tables)
- [x] `events` table with `dispatched_at` flag column
- [x] `notifications` table with per-recipient delivery tracking

### W4.2 — Event emission
- [x] Create `backend/src/services/events.py` — `emit_event()` + `emit_job_event()`
- [x] Worker emits on job state changes (started, completed, failed, stopped)

### W4.3 — Notification dispatcher
- [x] Create `backend/src/workers/handlers/notification_dispatch.py`
- [x] Registered in JOB_HANDLERS, triggered via internal endpoint or cron

### W4.4 — WebSocket: user-scoped rooms + notification API
- [x] Add `notifications` room (auto-subscribed on connect) to `manager.py`
- [x] Add `push_notification()` method for per-user delivery
- [x] Notifications router: GET /notifications, GET /unread-count, POST /read, POST /read-all

### W4.5 — Frontend notification component
- [x] `NotificationBell.tsx` — bell icon, unread badge, popover with mark-read
- [x] `notificationService.ts` — API client for notifications
- [x] Integrated into layout header

---

## Phase W5: Monitoring + Deploy (Week 5)

### W5.1-W5.5
- [x] Health diagnostic endpoint (`GET /internal/jobs/health`)
- [x] Railway deployment config: `job-worker` service with 2 replicas
- [x] Local dev mode (`python -m src.dev_runner` — API + worker in single process)
- [ ] Staged rollout: analytics -> QB sync -> reembed -> remaining
- [ ] Set `CRON_SECRET` and `WORKER_ID` env vars in Railway

---

## Phase C0: Contact-QB Metadata Linking (Week 6)

**Status:** Migration 081 committed, backfill pending.

- [x] Execute `batch_propagate_qb_data_to_contacts()` backfill (7,119/21,076 contacts linked)
- [x] Verify AI prompt enrichment reads real values (not NULLs)
- [x] Wire propagation into QB sync pipeline (auto-run in `trigger_sync` after each sync)

---

## Phase T1: Thread-QB Journey Linking (Week 6-8)

**Goal:** Emails/threads trackable through to jobs, production, and invoices.

### T1.1 — Migration: thread_qb_links table
- [x] `scripts/migrations/086_thread_qb_links.sql` (applied)
- [x] Schema: `client_id`, `canonical_thread_id`, `link_type`, `qb_record_id`, `qb_reference`, `confidence`, `source`, `verified`
- [x] Indexes for thread lookup, job lookup, unverified suggestions
- [x] `extracted_references JSONB` column added to `ai_email_intelligence`

### T1.2 — Reference number extraction (regex)
- [x] Create `backend/src/services/reference_extractor.py`
- [x] Patterns: Q\d+, J\d+ (and Quote #, Job #, QT, JB variants)
- [x] Validate against `qb_quotes.quote_no` / `qb_jobs.job_no`
- [x] Run as worker job type: `reference_extraction` (handler registered)

### T1.3 — AI extraction enhancement
- [x] Add `qb_references` field + QB REFERENCE EXTRACTION instructions to classification prompt
- [x] `QBReference` Pydantic model + `qb_references` field on `EmailClassificationResult`
- [x] `post_process_classification()` writes `extracted_references` to `ai_email_intelligence`
- [x] Post-classification linker in `ai_analysis` worker handler: validates AI refs against QB, writes `thread_qb_links` with `source='ai'`, `confidence=0.9`
- [x] Updated `ai_prompt_config` DB rows (email_analysis_user + email_analysis_system) to v1.3

### T1.4 — Journey API endpoints
- [x] Create `backend/src/routers/journey.py`
- [x] `GET /journey/threads/{thread_id}` — thread -> quotes -> jobs -> ops -> invoices -> status log
- [x] `GET /journey/jobs/{job_no}` — job -> linked threads + full chain
- [x] `GET /journey/companies/{id}/timeline` — all journeys for company
- [x] `POST /journey/links` — manual linking
- [x] `DELETE /journey/links/{id}` — remove link

### T1.5 — Manual linking UI
- [x] `ThreadJourneyPanel.tsx` — display journey with QB links, quotes, jobs, ops, invoices, status timeline
- [x] `ManualLinkDialog.tsx` — AM associates thread with quote/job
- [x] `journeyService.ts` — API client

---

## Phase W6: Email Pipeline Handler (Week 6-7) ✅ COMPLETE

**Goal:** Replace implicit post-sync chain with explicit `email_pipeline` worker job — per-step progress tracking, resume-from-failure, single-flight per mailbox.

**Design doc:** `docs/pipeline-design.md`

### W6.1 — Pipeline handler implementation
- [x] Create `backend/src/workers/handlers/email_pipeline.py`
- [x] 8-step sequential pipeline: extract_and_link → assign_threads → evaluate_threads → refresh_counts → embed_emails → ai_classify → bucket_engine → evaluate_threads_final
- [x] Per-step progress updates to `processing_jobs.parameters.completed_steps`
- [x] Resume from last completed step (skip completed steps)
- [x] Worker singletons: handler creates its own `ExtractionOrchestrator`, `VectorService`, `AIEmailAnalyzer`, `ActionBucketEngine` instances
- [x] Startup sweep: `_resume_interrupted_pipelines()` on worker boot auto-resumes pipelines with preserved `completed_steps`
- [x] Observability hardening: `_persist_progress` retries 3x, raises on exhaustion; all handlers log errors (no `except: pass`)

### W6.2 — Single-flight dedup
- [x] Migration 087: partial unique index `uq_email_pipeline_per_mailbox` on `(mailbox_id) WHERE status IN ('pending','running')`
- [x] Register `email_pipeline` in `JOB_HANDLERS`

### W6.3 — Trigger integration
- [x] Gmail sync `_sync_mailbox()` + `_sync_user()` → creates `email_pipeline` pending job
- [x] Outlook sync `_sync_mailbox()` + `_sync_user()` → same
- [x] Date-range fetch (Gmail + Outlook) → auto-triggers pipeline after completion
- [x] Manual extraction trigger (analytics.py "Run" button) → creates pipeline job
- [x] `_trigger_post_sync_extraction()` deprecated (2026-04-17, remove after 2026-04-24)

### W6.4 — Resolved decisions
1. **Full mode** — `extraction_mode='full'` processes all unextracted emails (incremental+7d was silently skipping older emails from date-range fetches)
2. **client_id from mailbox lookup** — handler resolves via `_resolve_client_id(sb, mailbox_id)`
3. **max_attempts=1** — retry-from-scratch wastes hours; startup sweep with preserved `completed_steps` is the recovery path
4. **Zero-email sync: skip** — pipeline only triggered when `processed > 0` (sync) or unconditionally (manual/date-range)

---

## Phase W7: Operations Center UI Consolidation (Week 7-8)

**Goal:** Merge Extraction page, Data Health page, and operational parts of AI Usage page into a single holistic operations dashboard.

### W7.1 — Audit and plan
- [x] Audited Extraction page: 5 features (run extraction, resync metadata, cancel job, monitor progress, job history)
- [x] Audited Data Health page: 6 actions + extensive diagnostics
- [x] Audited AI Usage page: AI controls + cost monitoring + embedding management + re-analysis
- [ ] Final merge plan: which features stay, which retire, which consolidate

### W7.2 — Consolidated Data Health & Operations page
- [ ] Move operational triggers from AI Usage (re-analysis, re-embed, re-bucket) into Data Health
- [ ] Move extraction features from Extraction page into Data Health
- [ ] Add pipeline status monitoring (email_pipeline jobs per mailbox)
- [ ] Retire standalone Extraction page (redirect to Data Health)
- [ ] AI Usage page keeps only: config/model selection, cost monitoring, prompt templates

### W7.3 — Holistic job orchestration
- [ ] "Run Full Pipeline" button (creates `email_pipeline` job for selected mailbox)
- [ ] Pipeline progress visualization (8 steps with completion status)
- [ ] Job history timeline showing all job types for a mailbox

---

## Phase C1: Contact Persona Metrics (Week 8-10)

### C1.1-C1.4
- [ ] SQL views: `contact_quote_metrics`, `contact_email_metrics` (materialized), `contact_persona`
- [ ] Rollup views: `company_contact_summary`, `industry_benchmarks`
- [ ] Materialized view refresh job (daily + post-QB-sync)
- [ ] API endpoints: persona, contact-summary, industry-benchmarks

**Migration:** `087_contact_persona_views.sql`
**Router:** `backend/src/routers/contacts_intelligence.py`

---

## Phase C2: Frontend — Contact Persona UI (Week 10-12)

- [ ] Contact Profile Card (identity + QB metrics + email behavior + persona + benchmarks)
- [ ] Company Profile: "Contact Breakdown" section
- [ ] Industry Dashboard
- [ ] Journey Timeline integration on profile pages

---

## Phase C3: Status Transition Analytics (Week 12+ / When Data Available)

**Blocked on:** 2-3 months of job_status_log data (started 2026-04-15, earliest useful: July 2026).

- [ ] Time-in-phase metrics per job and per contact
- [ ] Bottleneck detection (status stuck > threshold)
- [ ] Production cycle time: quote acceptance -> job completion

---

## Dependency Graph

```
W1 (Schema + Factory) ✅
 |
 v
W2 (Worker Process) ✅
 |
 v
W3 (Scheduler) ✅ (endpoints + docs done, external cron config pending)
 |
 v
W4 (Notifications) ✅
 |
 v
W5 (Deploy + Rollout) — partially done (health check ✅, staged rollout pending)
 |
 v
W6 (Email Pipeline Handler) ✅ — resumable, single-flight, auto-triggered
 |
 v
W7 (Operations Center UI) ← NEXT — depends on W6 for pipeline job type
 |
 v
T1 (Thread-QB Journey) ✅ Complete (including AI extraction T1.3)
 |
 v
C0 (Contact Backfill) ✅
 |
 v
C1 (Persona Metrics)   <--- depends on C0 + T1
 |
 v
C2 (Frontend UI)
 |
 v
C3 (Status Analytics)  <--- blocked on data (~3 months from Apr 15)
```

## Migrations Sequence

| # | Name | Phase | Status | Description |
|---|------|-------|--------|-------------|
| 083 | worker_infrastructure | W1 | ✅ Applied | processing_jobs extensions + dedup indexes |
| 084 | reconcile_stuck_jobs | W2 | ✅ Applied (updated 04-17) | Stuck-job reconciler RPC — now handles NULL-lease BackgroundTasks jobs |
| 085 | events_notifications | W4 | ✅ Applied | Events + notifications tables |
| 086 | thread_qb_links | T1 | ✅ Applied | Thread-to-QB linking table + extracted_references on ai_email_intelligence |
| 087 | email_pipeline_dedup | W6 | ✅ Applied | Partial unique index for email_pipeline single-flight per mailbox |
| 088 | contact_persona_views | C1 | Planned | Persona metric views (regular + materialized) |

## Effort Summary

| Phase | Description | Effort | Status |
|-------|-------------|--------|--------|
| W1 | Schema + Factory + Callsite migration | 1.5-2 weeks | ✅ Complete |
| W2 | Worker process + first handler | 1-1.5 weeks | ✅ Complete |
| W3 | Scheduler (external cron) | 3-4 days | ✅ Endpoints + CRON_SETUP.md done, external config pending |
| W4 | Notifications (in-app only) | 1-1.5 weeks | ✅ Complete |
| W5 | Monitoring + deploy + staged rollout | 1 week | 🔶 Health check done, staged rollout pending |
| C0 | Contact-QB metadata backfill | 2-3 days | ✅ Complete |
| T1 | Thread-QB journey linking | 2-2.5 weeks | ✅ Complete (including AI extraction T1.3) |
| **W6** | **Email pipeline handler** | **1-1.5 weeks** | **✅ Complete — deployed + observability hardened** |
| **W7** | **Operations center UI consolidation** | **1-1.5 weeks** | **Audit complete, implementation pending** |
| C1 | Contact persona metrics | 2 weeks | Not started |
| C2 | Frontend persona UI | 2.5 weeks | Not started |
| C3 | Status transition analytics | 1-2 weeks | Blocked on data (~3 months from Apr 15) |

**Worker in production:** ✅ Complete (ai_backfill, ai_analysis, notification_dispatch, email_pipeline verified)
**Thread-QB journey queryable:** ✅ Complete (regex extraction, journey API, manual linking UI)
**Email pipeline:** ✅ Complete — 8-stage resumable pipeline, startup sweep, observability hardened
**Next milestone:** Operations center UI (W7) → Contact persona (C1)
**Full roadmap remaining:** ~6-8 weeks (W7 through C3)
