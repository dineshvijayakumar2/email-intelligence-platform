# Bucket List: Apr 16–22, 2026 (Completed)

**Purpose:** Historical record of the multi-worker + contact intelligence + journey tracking sprint.
**Status:** Closed — all delivered items below. Incomplete items moved to `BUCKET_LIST_APR23_MAY14.md`.
**Status convention:** [x] done + verified

---

## Delivered

### Worker Infrastructure (W1–W2)

- [x] Migration 083: `processing_jobs` extensions — `last_heartbeat_at`, `worker_id`, `lease_expires_at`, `attempts`, `max_attempts`, `scheduled_for`, `triggered_by`
- [x] Claimable + active-lease partial indexes
- [x] Job Factory: `JobSpec` model + `create_job()` with dedup (`JobAlreadyActive`)
- [x] All callsites migrated to factory (reembed, ai_analysis, ai_backfill, strategic_digest, reprocessing, sync services, date-range fetch, generic extraction)
- [x] Worker process: `job_runner.py` — claim loop, `SELECT FOR UPDATE SKIP LOCKED`, 5-min lease, 30s heartbeat, graceful SIGTERM
- [x] Handler registry: `JOB_HANDLERS` dict mapping job_type → handler
- [x] Stuck-job reconciler RPC (migration 084) — marks expired-lease jobs as `interrupted`; extended for NULL-lease BackgroundTasks jobs stuck >2h
- [x] First handler migrated: `reembed` (handlers/reembed.py)

### Scheduler (W3)

- [x] pg_cron/pg_net not available on Supabase tier — decision: external HTTP cron
- [x] Internal endpoints: `internal_jobs.py` — qb-sync (hourly), analytics-rollup (daily), stuck-reconciler (10min), notification-dispatch (2min)
- [x] Auth via `verify_cron_secret` dependency
- [x] Cron setup documentation: `docs/CRON_SETUP.md`

### Notifications (W4)

- [x] Migration 085: events + notifications tables
- [x] Event emission: `emit_event()` + `emit_job_event()` on job state changes
- [x] Notification dispatcher handler
- [x] WebSocket: user-scoped `notifications` room + `push_notification()`
- [x] Notifications router: GET /notifications, GET /unread-count, POST /read, POST /read-all
- [x] `NotificationBell.tsx` — bell icon, unread badge, popover with mark-read

### Monitoring + Deploy (W5 — partial)

- [x] Health diagnostic endpoint (`GET /internal/jobs/health`)
- [x] Railway deployment config: `job-worker` service with 2 replicas
- [x] Local dev mode (`python -m src.dev_runner`)

### Thread-QB Journey Linking (T1)

- [x] Migration 086: `thread_qb_links` table + `extracted_references` on `ai_email_intelligence`
- [x] Reference extractor: regex patterns (Q\d+, J\d+, Quote #, Job #, QT, JB variants)
- [x] AI extraction: `qb_references` field in classification prompt v1.3, post-classification linker writes `thread_qb_links` with `source='ai'`, `confidence=0.9`
- [x] Journey API: 5 endpoints (thread journey, job journey, company timeline, manual link, delete link)
- [x] Manual linking UI: `ThreadJourneyPanel.tsx`, `ManualLinkDialog.tsx`, `journeyService.ts`

### Contact-QB Metadata Linking (C0)

- [x] `batch_propagate_qb_data_to_contacts()` backfill (7,119/21,076 contacts linked)
- [x] AI prompt enrichment verified reading real values
- [x] Propagation wired into QB sync pipeline (auto-run after each sync)

### Email Pipeline Handler (W6)

- [x] `email_pipeline.py` — 8-step sequential pipeline: extract_and_link → assign_threads → evaluate_threads → refresh_counts → embed_emails → ai_classify → bucket_engine → evaluate_threads_final
- [x] Migration 087: partial unique index `uq_email_pipeline_per_mailbox` for single-flight dedup
- [x] Resumable: `completed_steps` persisted after every stage; startup sweep auto-resumes on boot
- [x] Observability hardened: `_persist_progress` retries 3x, raises `ProgressPersistError` on exhaustion
- [x] All 4 sync trigger points replaced (Gmail + Outlook)
- [x] Date-range fetch and manual "Run" button rewired to pipeline

### Critical Fixes (commit `b7f1486`, Apr 17)

- [x] Pipeline auto-trigger: cron sync paths were missing `_trigger_post_sync_extraction()`
- [x] 8 hybrid callsites protected with `initial_status="running"`
- [x] Embed thread safety: `asyncio.run()` replaces `get_event_loop().run_until_complete()` (Python 3.13)
- [x] 13 silent `except: pass` locations hardened to log or raise

### Production-verified handlers

| Job Type | Handler | Status |
|----------|---------|--------|
| `ai_backfill` | `handlers/ai_backfill.py` | ✅ Verified: heartbeat, completion, worker_id |
| `ai_analysis` | `handlers/ai_analysis.py` | ✅ Deployed |
| `reembed` | `handlers/reembed.py` | ✅ Handler exists |
| `notification_dispatch` | `handlers/notification_dispatch.py` | ✅ Verified (sub-second) |
| `reference_extraction` | `handlers/reference_extraction.py` | ✅ Handler exists |
| `email_pipeline` | `handlers/email_pipeline.py` | ✅ Deployed + production verified |

### Migrations shipped

| # | Name | Description |
|---|------|-------------|
| 083 | worker_infrastructure | processing_jobs extensions + dedup indexes |
| 084 | reconcile_stuck_jobs | Stuck-job reconciler RPC (updated for NULL-lease jobs) |
| 085 | events_notifications | Events + notifications tables |
| 086 | thread_qb_links | Thread-to-QB linking + extracted_references |
| 087 | email_pipeline_dedup | Single-flight per mailbox |

### Key lessons

1. `asyncio.to_thread()` mandatory for sync blocking calls — heartbeat starves without it
2. `max_attempts=1` for long pipelines — startup sweep with `completed_steps` is the recovery path
3. BackgroundTasks jobs must use `initial_status="running"` — otherwise worker claims and fails
4. `asyncio.run()` not `get_event_loop().run_until_complete()` — latter fails in ThreadPoolExecutor on Python 3.13
5. No `except Exception: pass` — every handler must log or raise
6. `_persist_progress` is the keystone — if checkpoint writes fail silently, resume breaks

---

## Items moved to current sprint (BUCKET_LIST_APR23_MAY14.md)

- External cron registration (Railway/cron-job.org) + `CRON_SECRET` env var
- Staged rollout: analytics → QB sync → reembed → remaining
- Operations Center UI consolidation (W7)
- Contact Persona Metrics (C1)
- Contact Persona Frontend (C2)
- Status Transition Analytics (C3) — blocked on data until ~July 2026
