# Implementation Roadmap: Multi-Worker + Contact Intelligence + Journey Tracking

**Created:** 2026-04-16
**Status:** Active — tracking implementation progress
**Source docs:** `docs/background-work-rfc.md`, `docs/contact-intelligence-design.md`

## Priority Order

1. Multi-worker infrastructure (Background Work RFC)
2. Thread-QB journey linking (emails trackable through to jobs + invoices)
3. Contact persona metrics + UI

---

## Current State

### What exists today
- **14 job creation callsites** scattered across 8 files — all run via FastAPI `BackgroundTasks` (die on uvicorn reload)
- **processing_jobs table** — basic schema (id, job_type, status, mailbox_id, records, error_log, parameters, current_stage, client_id)
- **ReembedJobState** (`backend/src/services/reembed_job_state.py`) — most mature pattern: single-flight via partial unique index, RPC-based atomic progress, cancellation polling
- **JobQueueManager** (`backend/src/database/redis_client.py:407-468`) — dead code, never called
- **WebSocket** — job-scoped rooms only (`jobs:{job_id}`, `mailbox:{mailbox_id}`), no user-scoped rooms
- **Railway** — already has `email-worker` service with 2 replicas in `deploy/railway/railway.toml`
- **QB sync** — manual trigger only, no cron endpoint
- **Migration 081** — Contact-QB linking committed, columns NULL (backfill not run)
- **Migration 082** — Job Status Log table, syncing from 2026-04-15
- **QB join chain** — fully linked: quotes -> jobs -> operations -> sales_line_items -> job_status_log (all via `job_no`)
- **Thread-QB gap** — no `thread_qb_links` table, no reference extraction from emails

### Job types in the system
| Job Type | Callsite | Current Pattern |
|----------|----------|-----------------|
| `ai_analysis` | ai.py:156 | BackgroundTasks |
| `ai_backfill` | ai.py:392 | BackgroundTasks |
| `strategic_digest` | ai.py:1256 | BackgroundTasks |
| `gmail_date_range_fetch` | gmail.py:634 | BackgroundTasks |
| `outlook_date_range_fetch` | outlook.py:635 | BackgroundTasks |
| `gmail_sync` | gmail_sync_service.py:640 | Service + BackgroundTasks |
| `outlook_sync` | outlook_sync_service.py:578 | Service + BackgroundTasks |
| `reprocessing` | mailboxes.py:338, processing_jobs.py:466 | BackgroundTasks |
| `reembed` | reembed_job_state.py:103 | DB state machine + BackgroundTasks |
| Generic extraction | processing_jobs.py:737 | BackgroundTasks |

---

## Phase W1: Worker Schema + Job Factory (Week 1-2)

**Goal:** Unified job creation and the DB schema that workers will claim from.

### W1.1 — Migration: processing_jobs extensions
- [ ] Add columns: `last_heartbeat_at`, `worker_id`, `lease_expires_at`, `attempts`, `max_attempts`, `scheduled_for`, `triggered_by`
- [ ] Add index: `idx_processing_jobs_claimable` (partial: pending OR expired lease)
- [ ] Add index: `idx_processing_jobs_active_lease` (partial: running)
- [ ] Add per-job-type dedup indexes (extend reembed pattern from migration 074)

**File:** `scripts/migrations/083_worker_infrastructure.sql`

### W1.2 — Job Factory
- [ ] Create `backend/src/services/jobs/factory.py` — `JobSpec` model + `create_job()` entry point
- [ ] Handle dedup (catch unique violation -> `JobAlreadyActive`)
- [ ] Handle defaults, validation, audit

### W1.3 — Migrate callsites to factory
- [ ] `reembed` (reembed_job_state.py)
- [ ] `ai_analysis` / `ai_backfill` (ai.py)
- [ ] `strategic_digest` (ai.py)
- [ ] `reprocessing` (mailboxes.py, processing_jobs.py)
- [ ] `gmail_sync` / `outlook_sync` (sync services)
- [ ] `gmail_date_range_fetch` / `outlook_date_range_fetch` (gmail.py, outlook.py)
- [ ] Generic extraction (processing_jobs.py)

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
- [ ] Health check endpoint per worker
- [ ] "Is everything healthy?" diagnostic query
- [ ] Railway deployment config update
- [ ] Local dev mode (`python -m src.dev_runner`)
- [ ] Staged rollout: analytics -> QB sync -> reembed -> remaining

---

## Phase C0: Contact-QB Metadata Linking (Week 6)

**Status:** Migration 081 committed, backfill pending.

- [ ] Execute `batch_propagate_qb_data_to_contacts()` backfill
- [ ] Verify AI prompt enrichment reads real values (not NULLs)
- [ ] Wire propagation into QB sync pipeline (auto-run after each sync)

---

## Phase T1: Thread-QB Journey Linking (Week 6-8)

**Goal:** Emails/threads trackable through to jobs, production, and invoices.

### T1.1 — Migration: thread_qb_links table
- [ ] `scripts/migrations/086_thread_qb_links.sql`
- [ ] Schema: `client_id`, `canonical_thread_id`, `link_type`, `qb_record_id`, `qb_reference`, `confidence`, `source`, `verified`
- [ ] Indexes for thread lookup, job lookup, unverified suggestions

### T1.2 — Reference number extraction (regex)
- [ ] Create `backend/src/services/reference_extractor.py`
- [ ] Patterns: Q-\d+, J-\d+, PO-\d+, INV-\d+ (and variants)
- [ ] Validate against `qb_quotes.quote_no` / `qb_jobs.job_no` / `qb_sales_line_items.invoice_no`
- [ ] Run as worker job type: `reference_extraction`

### T1.3 — AI extraction enhancement
- [ ] Add QB reference extraction to classification prompt
- [ ] Add `extracted_references JSONB` to `ai_email_intelligence`
- [ ] Feed into `thread_qb_links` with `source='ai'`

### T1.4 — Journey API endpoints
- [ ] Create `backend/src/routers/journey.py`
- [ ] `GET /threads/{thread_id}/journey` — thread -> quotes -> jobs -> ops -> invoices -> status log
- [ ] `GET /jobs/{job_no}/journey` — job -> linked threads + full chain
- [ ] `GET /companies/{company_id}/journey-timeline` — all journeys for company

### T1.5 — Manual linking UI
- [ ] `ThreadJourneyPanel.tsx` — display journey timeline
- [ ] `ManualLinkDialog.tsx` — AM associates thread with quote/job

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
W1 (Schema + Factory)
 |
 v
W2 (Worker Process)
 |
 v
W3 (Scheduler)  <--- C0 (Contact Backfill) can start in parallel
 |
 v
W4 (Notifications)
 |
 v
W5 (Deploy + Rollout)
 |
 v
T1 (Thread-QB Journey) <--- depends on W2 for worker
 |
 v
C1 (Persona Metrics)   <--- depends on C0 + T1
 |
 v
C2 (Frontend UI)
 |
 v
C3 (Status Analytics)  <--- blocked on data (~3 months)
```

## Migrations Sequence

| # | Name | Phase | Description |
|---|------|-------|-------------|
| 083 | worker_infrastructure | W1 | processing_jobs extensions + dedup indexes |
| 084 | reconcile_stuck_jobs | W2 | Stuck-job reconciler RPC |
| 085 | pg_cron_schedules | W3 | Schedule registration + internal auth |
| 086 | events_notifications | W4 | Events + notifications tables |
| 086 | thread_qb_links | T1 | Thread-to-QB linking table |
| 087 | contact_persona_views | C1 | Persona metric views (regular + materialized) |

## Effort Summary

| Phase | Description | Effort | Cumulative |
|-------|-------------|--------|------------|
| W1 | Schema + Factory + Callsite migration | 1.5-2 weeks | 2 weeks |
| W2 | Worker process + first handler | 1-1.5 weeks | 3.5 weeks |
| W3 | Scheduler (pg_cron) | 3-4 days | 4 weeks |
| W4 | Notifications (in-app only) | 1-1.5 weeks | 5.5 weeks |
| W5 | Monitoring + deploy + staged rollout | 1 week | 6.5 weeks |
| C0 | Contact-QB metadata backfill | 2-3 days | 7 weeks |
| T1 | Thread-QB journey linking | 2-2.5 weeks | 9.5 weeks |
| C1 | Contact persona metrics | 2 weeks | 11.5 weeks |
| C2 | Frontend persona UI | 2.5 weeks | 14 weeks |
| C3 | Status transition analytics | 1-2 weeks | 15-16 weeks |

**First milestone (worker in production):** ~6.5 weeks
**Thread-QB journey queryable:** ~9.5 weeks
**Full roadmap:** ~14-16 weeks
