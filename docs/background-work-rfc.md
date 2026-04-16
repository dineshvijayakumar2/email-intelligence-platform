# RFC: Background Work — Worker, Scheduler, Notifications

**Status:** Approved for implementation
**Author:** Dinesh
**Date:** 2026-04-15

## Decision Log

- **2026-04-15:** Expert review skipped after weighing cost/benefit. Design risk is bounded (worst case: job runs twice or doesn't run when expected — both detectable and fixable, neither catastrophic). Mitigations in place of review:
  1. Cross-check claim/lease/heartbeat patterns against graphile-worker (Node) and pg-boss documentation before implementation
  2. Explicit concurrent-failure tests (see Implementation Notes below)
  3. Staged rollout — new worker handles one job type for first week, expand after observation
  4. `exec_sql` / `exec_sql_extended` security review **still required separately** — different risk category (privilege escalation), not covered by skipping this review
- **2026-04-15:** Two worker instances at launch (multi-worker confirmed administratable, plan supports it).
- **2026-04-15:** Phased notification delivery — in-app only at launch (Phase A); push and email deferred to Phase B/C behind real demand.

## Context

The current system has three structural gaps surfaced by recent audits:

1. **Job execution is in-process and fragile.** `processing_jobs` table exists with reasonable schema, but execution happens via `asyncio.create_task` inside the API process. Jobs die on `uvicorn` reload. Seven scattered `.insert()` callsites with no factory. Dead `JobQueueManager` code from a half-finished prior attempt.
2. **No scheduled work.** Hourly QB sync, daily analytics rollups, weekly digests — all currently absent. Adding them in-process repeats the fragility problem at higher frequency.
3. **No notification system.** Time-based, job-completion, and urgent-action notifications all needed for upcoming features. No infrastructure today.

This RFC proposes a unified design for all three that minimizes operational surface area while addressing each problem properly.

## Design Principles

- **One execution model.** User-initiated jobs and scheduled jobs run through the same worker. The trigger source is metadata, not a separate code path.
- **Postgres as source of truth.** Job state, schedules, notifications, events — all in Postgres. No second-source-of-truth (Redis-backed queues, external workflow engines) except where Postgres is genuinely insufficient.
- **Channels derived from events.** Notifications read from a central event log. Adding a new notification channel doesn't require changing the producers.
- **Monitorable from one query.** A single SQL query should answer "is anything broken in background work?" That's only possible if the design has one queue, one schedule source, one event stream.

## Non-Goals

- Sub-second job latency. Polling-based queues have ~1-2s latency; that's acceptable for our use cases.
- Multi-region distribution. Single Railway region is fine.
- Workflow DAGs (job A's output feeds job B). If needed later, build on top.
- Generic event sourcing. The event log is for notification dispatch, not for replaying state.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  TRIGGER SOURCES                                             │
├─────────────────────────────────────────────────────────────┤
│  User clicks button → API endpoint → create_job() factory   │
│  pg_cron schedule  → internal endpoint → create_job() factory│
│  System event       → create_job() factory                   │
└─────────────────────────────────────────────────────────────┘
                          ↓
                  processing_jobs table
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  WORKER POOL (2 processes on Railway, scalable to N)         │
│  - SELECT FOR UPDATE SKIP LOCKED claim                       │
│  - Heartbeat + lease per active job                          │
│  - Writes events to job_events table on state changes        │
└─────────────────────────────────────────────────────────────┘
                          ↓
                  job_events table
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  NOTIFICATION DISPATCHER                                     │
│  - Reads job_events + condition triggers                     │
│  - Routes to channels: in-app (WebSocket), push, email       │
│  - Records delivery state per recipient per channel          │
└─────────────────────────────────────────────────────────────┘
```

---

## Component 1: Worker (System 1)

### Schema additions to processing_jobs

```sql
ALTER TABLE processing_jobs
  ADD COLUMN IF NOT EXISTS last_heartbeat_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS worker_id TEXT,
  ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS attempts INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS max_attempts INT NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS scheduled_for TIMESTAMPTZ DEFAULT NOW(),
  ADD COLUMN IF NOT EXISTS triggered_by TEXT;  -- 'user', 'cron', 'event'

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_processing_jobs_claimable
  ON processing_jobs(scheduled_for)
  WHERE status = 'pending'
     OR (status = 'running' AND lease_expires_at < NOW());

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_processing_jobs_active_lease
  ON processing_jobs(lease_expires_at)
  WHERE status = 'running';
```

`scheduled_for` lets you create jobs that don't run immediately ("create this job, but only start it at 3am"). Defaults to `NOW()` so user-initiated jobs run right away.

`triggered_by` is metadata for monitoring and debugging. Doesn't change execution.

### Lease + heartbeat mechanics

When a worker claims a job, it sets `lease_expires_at = NOW() + 5 minutes`. While the job runs, the worker emits a heartbeat every 30 seconds that extends the lease. If the worker crashes, the lease expires; the next worker that scans the queue reclaims the job (but with `attempts + 1`).

Two failure modes this protects against:
- Worker crashes mid-job → another worker reclaims after 5 min
- Worker hangs but doesn't crash → lease still expires because heartbeat stops

### Claim query

```sql
WITH claimed AS (
  SELECT id
  FROM processing_jobs
  WHERE scheduled_for <= NOW()
    AND (
      status = 'pending'
      OR (status = 'running' AND lease_expires_at < NOW())
    )
  ORDER BY scheduled_for, created_at
  LIMIT 1
  FOR UPDATE SKIP LOCKED
)
UPDATE processing_jobs pj
SET status = 'running',
    worker_id = $1,
    started_at = COALESCE(started_at, NOW()),
    last_heartbeat_at = NOW(),
    lease_expires_at = NOW() + INTERVAL '5 minutes',
    attempts = attempts + 1
FROM claimed
WHERE pj.id = claimed.id
RETURNING pj.*;
```

### Worker process structure

One worker process per Railway service instance. Run 2-3 instances for redundancy and to avoid scheduled-job starvation when long user jobs are running.

```python
# backend/src/workers/job_runner.py — entry point
async def main():
    worker_id = f"{socket.gethostname()}-{os.getpid()}"
    register_signal_handlers()  # SIGTERM → set shutdown flag

    while not shutdown_requested:
        job = await claim_next_job(worker_id)
        if not job:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)  # 2s
            continue

        await execute_job_with_supervision(job, worker_id)

    logger.info(f"Worker {worker_id} shutting down cleanly")
```

`execute_job_with_supervision` runs:
1. The actual job handler (looked up by `job_type`)
2. A heartbeat task that updates `lease_expires_at` every 30s
3. A cancellation watcher that checks `status` for cancellation requests

On exit, marks the job as completed/stopped/failed and emits a `job_events` row.

### Job handler registry

Each `job_type` maps to a handler function. Centralized so the worker doesn't need to know about every feature:

```python
# backend/src/workers/handlers/__init__.py

JOB_HANDLERS: dict[str, Callable] = {
    'reembed': reembed_handler,
    'qb_sync_scheduled': qb_sync_handler,
    'analytics_rollup_daily': analytics_rollup_handler,
    'digest_generation': digest_handler,
    # add new types here
}
```

Adding a new job type is: write a handler function, register it. No worker changes.

### Job creation factory (replaces 7 scattered callsites)

```python
# backend/src/services/jobs/factory.py

class JobSpec(BaseModel):
    job_type: str
    parameters: dict
    client_id: Optional[UUID] = None  # nullable for system jobs
    dedup_key: Optional[str] = None
    max_attempts: int = 1
    scheduled_for: Optional[datetime] = None  # None = now
    triggered_by: str = 'user'  # 'user' | 'cron' | 'event'

async def create_job(spec: JobSpec, db) -> UUID:
    """Single entry point for creating jobs.

    All seven existing callsites migrate to use this.
    Enforces: schema, dedup (via partial unique indexes), defaults, audit.

    Raises JobAlreadyActive if dedup_key collides with an active job.
    """
    ...
```

### Dedup via partial unique indexes

Per job-type, when single-flight is needed:

```sql
-- One active reembed per client (already exists from Phase 1 work)
CREATE UNIQUE INDEX IF NOT EXISTS uq_jobs_active_reembed_per_client
  ON processing_jobs(client_id)
  WHERE status IN ('pending', 'running') AND job_type = 'reembed';

-- One active QB sync globally (no client_id needed for scheduled jobs)
CREATE UNIQUE INDEX IF NOT EXISTS uq_jobs_active_qb_sync
  ON processing_jobs((1))  -- constant expression for global single-flight
  WHERE status IN ('pending', 'running') AND job_type = 'qb_sync_scheduled';
```

The factory catches the unique violation, looks up the existing active job, raises a typed `JobAlreadyActive` exception with the existing job_id. API endpoints translate this to HTTP 409.

### Stuck-job reconciler

A separate scheduled task (runs every 10 min, see Component 2):

```sql
-- Mark jobs whose lease expired without reclaim
UPDATE processing_jobs
SET status = 'interrupted',
    error_log = COALESCE(error_log, '[]'::jsonb) || jsonb_build_array(jsonb_build_object(
      'type', 'lease_expired',
      'detected_at', NOW(),
      'last_heartbeat_at', last_heartbeat_at,
      'last_worker_id', worker_id
    ))
WHERE status = 'running'
  AND lease_expires_at < NOW() - INTERVAL '10 minutes';
```

The 10-minute grace beyond lease expiration accommodates worker pool backups before declaring jobs dead.

### Graceful shutdown

`SIGTERM` sets a shutdown flag. The worker:
1. Stops claiming new jobs
2. Lets the current job complete (or hits its lease timeout if too long)
3. Exits

For very long jobs (reembed): the job handler should periodically check the shutdown flag and exit cleanly with status reset to `pending` so another worker picks up where it left off. This is per-handler discipline, not enforceable by the framework.

---

## Component 2: Scheduler (System 2)

### pg_cron registration

Schedules live in the database, registered once via migration:

```sql
-- Enable extension (one-time, may already be enabled)
CREATE EXTENSION IF NOT EXISTS pg_cron;
CREATE EXTENSION IF NOT EXISTS pg_net;  -- for HTTP calls from cron

-- Store the cron secret in a setting (set via Supabase dashboard or migration)
-- This avoids hardcoding it in the cron job definitions
ALTER DATABASE postgres SET app.cron_secret = '<random-secret-set-out-of-band>';

-- Schedules
SELECT cron.schedule(
  'qb-sync-hourly',
  '0 * * * *',  -- every hour at :00
  $$
    SELECT net.http_post(
      url := 'https://api.example.com/internal/jobs/qb-sync',
      headers := jsonb_build_object(
        'Authorization', 'Bearer ' || current_setting('app.cron_secret'),
        'Content-Type', 'application/json'
      ),
      body := '{}'::jsonb
    );
  $$
);

SELECT cron.schedule(
  'analytics-rollup-daily',
  '0 2 * * *',  -- 2am UTC daily
  $$ SELECT net.http_post(...) $$
);

SELECT cron.schedule(
  'digest-generation-weekly',
  '0 8 * * 1',  -- Monday 8am
  $$ SELECT net.http_post(...) $$
);

SELECT cron.schedule(
  'stuck-job-reconciler',
  '*/10 * * * *',  -- every 10 min
  $$ SELECT net.http_post(...) $$
);
```

### Internal endpoints pattern

```python
# backend/src/routers/internal_jobs.py

router = APIRouter(prefix="/internal/jobs")

@router.post("/qb-sync")
async def trigger_qb_sync(_auth: None = Depends(verify_cron_secret)):
    job_id = await create_job(JobSpec(
        job_type='qb_sync_scheduled',
        parameters={'schedule': 'hourly'},
        client_id=None,
        dedup_key='qb_sync_active',
        max_attempts=3,
        triggered_by='cron',
    ))
    return {"job_id": str(job_id)}

@router.post("/analytics-rollup")
async def trigger_analytics_rollup(_auth: None = Depends(verify_cron_secret)):
    job_id = await create_job(JobSpec(
        job_type='analytics_rollup_daily',
        parameters={'date': datetime.utcnow().date().isoformat()},
        triggered_by='cron',
    ))
    return {"job_id": str(job_id)}
```

The endpoint is intentionally thin: validate auth, create job, return. The worker (Component 1) does the actual work. Same execution path as user-initiated jobs.

### Handling missed schedules

When a scheduled job fires while a previous instance is still running, the dedup mechanism (partial unique index on `(job_type)` for active jobs) raises `JobAlreadyActive`. The internal endpoint should treat this as **success-no-op**, not as an error:

```python
@router.post("/qb-sync")
async def trigger_qb_sync(_auth: None = Depends(verify_cron_secret)):
    try:
        job_id = await create_job(JobSpec(
            job_type='qb_sync_scheduled',
            dedup_key='qb_sync_active',
            ...
        ))
        return {"job_id": str(job_id), "status": "queued"}
    except JobAlreadyActive as e:
        # Previous QB sync still running; this slot is coalesced
        return {"job_id": str(e.existing_job_id), "status": "already_active"}
```

This means missed slots coalesce — three pg_cron firings during a long QB sync produce one queued/running job, not three. Correct behavior for idempotent scheduled work.

For non-idempotent scheduled work (e.g., "send the daily digest" — running it twice would double-send), the dedup pattern is the same but the consequences of a missed slot are different. Document this per job type.

### What lives where

| Concern | Location |
|---|---|
| **What's scheduled** | `cron.job` table (one query: `SELECT * FROM cron.job`) |
| **When schedules last ran** | `cron.job_run_details` table |
| **What jobs were created from a schedule** | `processing_jobs WHERE triggered_by = 'cron'` |
| **What jobs are running right now** | `processing_jobs WHERE status = 'running'` |
| **Why a scheduled job didn't run** | Either `cron.job_run_details` (cron failed to fire) or `processing_jobs.error_log` (job ran and failed) |

This is the "monitorable from one query" principle: every question about background work has a single SQL answer.

---

## Component 3: Notification Dispatcher

### Schema: events and notifications

Two new tables. The `events` table is the source of truth for "what happened." The `notifications` table tracks "who needs to be told and through what channel."

```sql
-- Events: what happened in the system, channel-agnostic
CREATE TABLE events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_type TEXT NOT NULL,  -- 'job.completed', 'job.failed', 'urgent.action_needed', etc.
  client_id UUID,             -- nullable for system events
  source_type TEXT,           -- 'job', 'system', 'condition_check'
  source_id TEXT,             -- e.g., the job_id that produced this event
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_events_undispatched
  ON events(created_at)
  WHERE NOT EXISTS (SELECT 1 FROM notifications n WHERE n.event_id = events.id);
-- Note: this partial index uses a subquery and may need to be a regular
-- index with a flag column instead. Verify with EXPLAIN before committing.

CREATE INDEX idx_events_by_type_recent
  ON events(event_type, created_at DESC);

-- Notifications: per-recipient delivery records
CREATE TABLE notifications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  recipient_user_id UUID NOT NULL,
  channel TEXT NOT NULL,  -- 'in_app' | 'push' | 'email'
  status TEXT NOT NULL DEFAULT 'pending',  -- 'pending' | 'delivered' | 'failed' | 'skipped'
  delivered_at TIMESTAMPTZ,
  failed_at TIMESTAMPTZ,
  failure_reason TEXT,
  read_at TIMESTAMPTZ,  -- for in-app notifications, when the user saw it
  payload JSONB,         -- channel-specific rendered content
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(event_id, recipient_user_id, channel)
);

CREATE INDEX idx_notifications_pending
  ON notifications(created_at)
  WHERE status = 'pending';

CREATE INDEX idx_notifications_user_unread
  ON notifications(recipient_user_id, created_at DESC)
  WHERE channel = 'in_app' AND read_at IS NULL;
```

### Event production

Events are written by:
1. **Worker** (after every job state change): `job.started`, `job.completed`, `job.failed`, `job.stopped`
2. **Scheduled checks** (a `condition_check` job type that runs hourly): `urgent.action_needed`, `threshold.crossed`
3. **Application code** (when domain events occur that need notification): `digest.generated`, `email.high_priority_received`

Producing an event is a single INSERT — no notification logic in the producer. The producer doesn't know or care who gets notified or how.

```python
# backend/src/services/events.py

async def emit_event(
    event_type: str,
    payload: dict,
    client_id: Optional[UUID] = None,
    source_type: Optional[str] = None,
    source_id: Optional[str] = None,
):
    """Single entry point for emitting events. Producers call this.
    Notification routing happens later, in the dispatcher."""
    await db.events.insert(...)
```

### Notification dispatcher

The dispatcher is a job type (`notification_dispatch`) scheduled every minute via pg_cron. It:

1. Reads undispatched events
2. For each event, looks up routing rules (which users should be notified, on which channels)
3. Inserts `notifications` rows for each (event, user, channel) tuple
4. Triggers the channel-specific delivery for each notification

```python
# backend/src/workers/handlers/notification_dispatch.py

async def dispatch_notifications(job: Job):
    events = await fetch_undispatched_events(limit=1000)
    for event in events:
        rules = await lookup_routing_rules(event)
        for rule in rules:
            for user_id in rule.recipient_user_ids:
                for channel in rule.channels:
                    if not await user_wants_notification(user_id, event, channel):
                        await create_notification(event, user_id, channel, status='skipped')
                        continue
                    notification = await create_notification(event, user_id, channel)
                    await deliver_notification(notification)
```

### Routing rules

For launch, keep routing rules simple — a static mapping from event type to recipient logic. Don't build a rules engine yet:

```python
ROUTING_RULES = {
    'job.completed': RoutingRule(
        recipients=lambda event: [event.payload['triggered_by_user_id']],
        channels=['in_app'],
    ),
    'job.failed': RoutingRule(
        recipients=lambda event: [event.payload['triggered_by_user_id']],
        channels=['in_app', 'email'],  # failure is more important
    ),
    'urgent.action_needed': RoutingRule(
        recipients=lambda event: get_account_managers_for_client(event.client_id),
        channels=['in_app', 'push'],
    ),
    'digest.generated': RoutingRule(
        recipients=lambda event: get_subscribed_users(event.payload['digest_type']),
        channels=['email'],
    ),
}
```

When you need user-configurable rules later (e.g., "let me turn off email notifications for job completions"), this becomes a `notification_preferences` table the lookup consults. Don't build that yet — wait for actual user demand.

### Channel implementations

#### In-app (WebSocket)

Reuses the existing `/ws` infrastructure. The dispatcher inserts the `notifications` row, then publishes to the user's WebSocket room (`user:{user_id}`). The frontend has a notification component that subscribes to its user's room and shows a toast or badge.

If the user is offline, the notification still exists in the DB. When they reconnect, the frontend fetches unread notifications via `GET /notifications?unread=true` and displays them.

This is the cheapest channel — no third-party service, uses existing WebSocket infra, handles offline naturally.

#### Push (deferred — see "Phased delivery")

#### Email (deferred — see "Phased delivery")

### Phased delivery for notifications

In-app first. Push and email later. Reasons:

- **In-app has zero new infrastructure** — uses existing WebSocket, costs nothing, immediate value
- **Push and email both need third-party services** with their own setup, deliverability concerns, compliance requirements, and cost
- **Each channel adds operational surface area** that requires monitoring (delivery rates, bounce handling, unsubscribe tracking)

Recommended phasing:

**Phase A (launch):** Events + notifications schema, dispatcher, in-app channel only. All event types route only to in-app at launch. Three weeks of work.

**Phase B (post-launch, when needed):** Add push channel. Requires choosing a service (Web Push native, Firebase Cloud Messaging, OneSignal). One-week add when you have a real user need.

**Phase C (when needed):** Add email channel. Requires choosing a transactional email provider (Postmark, Resend, AWS SES). One-week add. **This is where compliance and deliverability concerns become real — expert review recommended before sending the first email to a real user.**

### Why this design instead of "just use a notifications service"

Services like Knock, Courier, or OneSignal handle multi-channel notifications natively. They're tempting because they look like "less to build."

Why I'm not recommending them for launch:

- **Vendor lock-in.** Routing rules, templates, user preferences all live in the vendor's system. Migrating later is painful.
- **Cost scales with notification volume**, which can grow fast.
- **Most of the value is in channels you don't have yet** (push, email). For in-app only, the service overhead exceeds the benefit.
- **The schema above is small** (~150 lines including migrations). The dispatcher is one job handler. Operational cost is essentially zero on top of what you already have.

**Revisit this at Phase B or C.** If by then you have meaningful push + email volume, mature templates, and want user-facing notification preferences, a service may be worth the lock-in. At that point you'd have real data on volume, channels, and routing complexity to make the decision well.

---

## Deployment Topology

### Railway services

Three services, all from the same Docker image, different commands:

| Service | Command | Replicas | Purpose |
|---------|---------|----------|---------|
| `api` | `uvicorn src.main:app` | 1 | HTTP API + WebSocket |
| `worker` | `python -m src.workers.job_runner` | 2 | Job execution |
| (future) `worker-priority` | same | 0-1 | Reserved for priority queue if needed |

Each worker instance gets a unique `WORKER_ID` env var (`worker-1`, `worker-2`). All workers connect to the same Postgres and read from the same `processing_jobs` table.

**Worker count: 2 at launch.** Reasons:
- Eliminates starvation when long user jobs run during scheduled job slots
- Provides redundancy against single worker crash
- Resource cost is negligible on Pro Plan (24 GB / 24 vCPU available; each worker ~256-512 MB / 0.25-0.5 vCPU)

Scaling beyond 2 is a Railway config change (no code change). Adding worker 3 if observed starvation occurs is "spin up another instance."

### Railway service configuration requirements

Verify before going live:
- **Auto-restart on crash** for the worker service (and API)
- **Health check endpoint** for each worker that confirms heartbeat is recent
- **Resource limits** set to reasonable defaults (don't let a runaway worker consume the whole plan's RAM)
- **Logs aggregated** to whichever logging system you use (Railway's built-in, or external)
- **Env vars** for `WORKER_ID`, `CRON_SECRET`, DB connection — sourced from Railway's secret store, not committed

### Local development

Single process can run worker + API together via `python -m src.dev_runner` which spawns the worker as a subprocess. WORKER_ID is `local-dev`. pg_cron isn't typically installed locally; scheduled job triggering can be done manually via curl to internal endpoints during dev.

This is the only place "single worker" matters — in dev. Production is always 2.

---

## Monitoring & Alerting

This is non-negotiable for the design to actually be operationally sound. The architecture above is robust *if* you know when something breaks.

### The "is everything healthy?" query

```sql
-- Single query that should return zero rows if all is well
WITH worker_health AS (
  -- Workers should heartbeat at least once per minute
  SELECT 'no_recent_heartbeat' AS issue, worker_id, MAX(last_heartbeat_at) AS last_seen
  FROM processing_jobs
  WHERE status = 'running'
  GROUP BY worker_id
  HAVING MAX(last_heartbeat_at) < NOW() - INTERVAL '2 minutes'
),
stuck_jobs AS (
  SELECT 'stuck_job' AS issue, id::text AS detail, started_at AS last_seen
  FROM processing_jobs
  WHERE status = 'running'
    AND lease_expires_at < NOW() - INTERVAL '15 minutes'
),
backlog AS (
  SELECT 'queue_backlog' AS issue, COUNT(*)::text AS detail, NULL::timestamptz
  FROM processing_jobs
  WHERE status = 'pending' AND scheduled_for < NOW() - INTERVAL '5 minutes'
  HAVING COUNT(*) > 10
),
failed_schedules AS (
  -- pg_cron jobs that failed in the last hour
  SELECT 'cron_failed' AS issue, jobname AS detail, end_time AS last_seen
  FROM cron.job_run_details
  WHERE status = 'failed' AND end_time > NOW() - INTERVAL '1 hour'
),
undispatched_events AS (
  SELECT 'events_not_dispatched' AS issue, COUNT(*)::text AS detail, MIN(created_at) AS oldest
  FROM events e
  WHERE NOT EXISTS (SELECT 1 FROM notifications n WHERE n.event_id = e.id)
    AND created_at < NOW() - INTERVAL '5 minutes'
  HAVING COUNT(*) > 0
)
SELECT * FROM worker_health
UNION ALL SELECT * FROM stuck_jobs
UNION ALL SELECT * FROM backlog
UNION ALL SELECT issue, detail, NULL FROM failed_schedules
UNION ALL SELECT issue, detail, oldest FROM undispatched_events;
```

This query is the contract. If it returns rows, something needs attention.

### External monitoring

**Required for launch:**
- Health check endpoint on each worker (`GET /workers/{worker_id}/health`) that returns 200 if heartbeat in last 2 min, 503 otherwise
- External pinger (UptimeRobot free tier or similar) checks both worker health URLs every minute
- Alert channel (email, Slack, whatever you actually watch) for the alerts

**Strongly recommended:**
- A daily summary email/post showing the previous day's: jobs run, jobs failed, average job duration per type, scheduled job timing accuracy. Helps you notice slow degradation, not just hard failures.

### What to alert on (and what NOT to alert on)

Alert on:
- Worker missing heartbeat for 5+ minutes
- Stuck job (lease expired without reclaim) for 15+ minutes
- Queue backlog of 10+ pending jobs older than 5 minutes
- pg_cron job execution failure
- Notification delivery failure rate > 5% in the last hour

Do NOT alert on:
- Individual job failures (they happen; aggregate alerts only)
- Jobs taking longer than expected unless they hit lease timeout
- Pending jobs in their normal scheduled window
- In-app notifications not being read (that's the user's choice)

The discipline is: alert on system health, not on user actions or expected variability.

---

## Risks & Open Questions

### Known risks

1. **pg_cron + pg_net availability on Supabase.** Both are supported but check current limitations on your tier. If pg_net is restricted, fall back to having pg_cron call SQL functions that do the work directly (won't work for HTTP-out, but works for SQL-only scheduled tasks). **Verify before committing.**

2. **Single API instance becomes a bottleneck for `/internal/jobs/*` endpoints if many schedules fire simultaneously.** At launch this is unlikely (a few schedules, not thousands), but worth monitoring. Mitigation: add rate limiting on the internal router, or have pg_cron call SQL stored procedures instead of HTTP for high-frequency schedules.

3. **`SELECT FOR UPDATE SKIP LOCKED` correctness under concurrent worker startup.** Two workers starting simultaneously and both attempting to claim the same job is exactly the race the pattern handles, but the SQL above should be reviewed by someone who has operated this in production to confirm the index choice and ordering are right.

4. **Lease reclamation can cause double-execution if the original worker is alive but slow.** If worker A holds a lease, fails to heartbeat for 5 min (e.g., GC pause, network blip), worker B reclaims the job and runs it. Worker A then "wakes up" and continues running. Two workers executing the same job simultaneously. This is rare in practice but possible. Mitigation: handlers must be idempotent OR the heartbeat interval must be much shorter than the lease (e.g., heartbeat every 30s, lease 5min — gives 10x safety margin).

5. **Notification dispatcher running every minute creates latency floor.** A job that completes at 14:00:05 produces an event, but the dispatcher doesn't run until 14:01:00, so the user sees the in-app notification ~55s later. For "your job is done" notifications, this is acceptable. For "urgent action needed," it might not be. Consider per-event-type dispatch latency requirements.

### Known unknowns to verify during implementation

These are the specific items that would have gone to expert review. Each has a verification path that doesn't require an outside expert.

1. **Claim query and indexes.** Cross-check the claim query against graphile-worker's implementation (their `get_job` function in the source). If the patterns match, you have evidence the design is sound. If they diverge, understand why before committing. Run `EXPLAIN ANALYZE` on the claim query against a populated `processing_jobs` table to verify index usage.

2. **Lease + heartbeat reclamation.** Read the "How it works" section of graphile-worker docs and pg-boss docs. Both implement this pattern. Compare lease durations, heartbeat intervals, and reclamation logic. If your design matches the consensus, you're following well-trodden ground. The specific concurrent-failure tests in Implementation Notes below exercise the failure modes.

3. **Partial unique index for dedup.** The `WHERE status IN ('pending', 'running')` predicate must perfectly match the application's understanding of "active job." Test the race: two API requests creating the same job type for the same client simultaneously, via `asyncio.gather`. Assert exactly one succeeds with a new job, the other gets `JobAlreadyActive`. If this passes reliably under repeated runs, the dedup works.

4. **pg_cron + pg_net on Supabase.** Verify by trying it. Create a test schedule that fires every minute and POSTs to a test endpoint. Watch for an hour. If it works, it works. Check `cron.job_run_details` for any errors. **Do this verification before committing to the rest of the design** — if pg_net is restricted, the design changes materially.

5. **The `idx_events_undispatched` partial index.** Resolved: do NOT use a partial index with a subquery (Postgres won't allow it). Use a `dispatched_at TIMESTAMPTZ NULL` column on `events` and a partial index `WHERE dispatched_at IS NULL`. Update the schema in Component 3 accordingly during implementation.

6. **WebSocket integration for in-app notifications.** Verify by inspection of the existing `/ws` code. The `user:{user_id}` room pattern (or equivalent) needs to exist or be addable cleanly. If the existing room model is `mailbox:{id}` only and not user-keyed, this is a small addition to the WebSocket infrastructure — not a design blocker, just a scope item to add.

### Open questions for product/business

1. **Notification preferences UI.** Phase A doesn't include user-configurable preferences. Is "all users get all notifications routed to all enabled channels" acceptable for launch? If yes, ship. If no, add preferences to Phase A scope.

2. **Email channel timing.** When does email become a real priority? This determines whether we provision Postmark/Resend at launch (in case it's needed within a month) or defer until there's a confirmed feature requiring it.

3. **Push notifications target platforms.** Web push (browser) only, or also mobile native apps? Native apps require significantly more infrastructure (FCM, APNs, app store coordination). For now, assume web push only.

4. **Urgent action notification thresholds.** What conditions trigger an `urgent.action_needed` event? This needs business-side definition before the condition_check scheduled job can be implemented.

## Implementation Notes

### Required concurrent-failure tests (substitute for expert review on concurrency correctness)

These tests must exist and pass before the worker design is considered production-ready. They exercise the specific failure modes the lease/heartbeat/SKIP LOCKED pattern is designed to handle.

1. **Concurrent claim race.** Spawn 5 workers attempting to claim from a queue with 5 pending jobs simultaneously. Assert each worker claims exactly one distinct job, no job is claimed twice, no job is missed.

2. **Worker death mid-job.** Start a job, kill the worker process (SIGKILL, not SIGTERM) before the lease expires. Wait for lease expiration + grace period. Assert another worker reclaims the job and `attempts` is incremented.

3. **Lease expiration during slow heartbeat.** Mock heartbeat to fail. Verify the lease expires on schedule and the job becomes reclaimable. Verify the original worker, when it next attempts to update progress, detects it has lost the lease and aborts cleanly.

4. **Dedup race.** Two `asyncio.gather` calls to `create_job()` for the same job_type and client_id. Assert exactly one returns a new job_id, the other raises `JobAlreadyActive`. Repeat 100 times to surface flakiness.

5. **Scheduled job during running job.** Manually create a long-running job of type X. Trigger the scheduled job for type X via the internal endpoint. Assert it returns `status: already_active` with the existing job_id, no new row created.

6. **Graceful shutdown with in-flight job.** Send SIGTERM to a worker running a job. For long jobs (>30s), the handler should check `shutdown_requested` and exit cleanly with status reset to `pending`. Verify the job is reclaimed by another worker without `attempts` incrementing for the graceful-handoff case.

7. **Stuck job reconciler.** Manually set `lease_expires_at` to a past timestamp on a running job, with `last_heartbeat_at` also old. Run the reconciler. Verify the job transitions to `interrupted` with the correct error_log entry.

If any of these tests are flaky or fail, the design has a bug that expert review would have caught. Fix before launch.

### Cross-reference reading list (substitute for expert review on patterns)

Read these before implementation. Each takes 30-60 minutes:

- **graphile-worker README and "How it works" docs** — the closest production-grade reference for Postgres-as-queue. Compare claim query, lease handling, error handling.
- **pg-boss documentation, especially "Concurrency" and "Failure Handling"** — Node.js library, but the SQL patterns translate directly.
- **river docs (Rust/Go)** — different ecosystem, same problem. Useful for cross-checking the design from a different angle.
- **Supabase docs on pg_cron and pg_net** — verify the exact features available on your tier, current rate limits, known issues.

### Staged rollout plan

Do not cut over all background work to the new worker at once. The phasing:

**Week 1 of rollout:** Deploy the worker infrastructure. Migrate ONE job type (suggest: `analytics_rollup_daily` — low frequency, idempotent, low blast radius if buggy). Leave reembed and other jobs on the old in-process path. Watch metrics for a week.

**Week 2:** If week 1 is clean, migrate the next job type. Suggest QB sync (scheduled, idempotent).

**Week 3:** Migrate reembed. This is the highest-stakes migration because it's user-initiated, long-running, and exercises the lease/heartbeat path heavily.

**Week 4+:** Migrate remaining job types one at a time, watching each for a few days before the next.

This sequencing means a bug discovered during the rollout affects one job type, not all background work. The rollback is "revert that job type's code to the old in-process path" — small, fast, contained.

### Security review still required separately

The `exec_sql` and `exec_sql_extended` RPCs are a **separate** concern that this RFC does not address. They are arbitrary-DDL functions callable from application code, which is a privilege escalation risk distinct from anything in this RFC.

That review is **not skippable** the way this design review was skippable. Job execution failing means jobs run weirdly. `exec_sql` failing means the database can be taken over. Different category.

The recommendation from earlier conversations stands: replace `exec_sql` with purpose-built typed-parameter functions (one per legitimate use case), revoke API role's grants on `exec_sql`, drop `exec_sql` once no callers remain. Track this as a separate work item.

---



- **Workflow DAGs.** No support for "job A then job B then job C." If needed, build on top by having handlers create child jobs.
- **Job priorities.** Single FIFO queue per scheduled_for time. Adding priority is a column addition + claim query change when needed.
- **External job submission.** No HTTP API for third-party systems to submit jobs. All jobs come from internal code paths.
- **Event sourcing / replay.** The events table is for notification dispatch only. It is not a CQRS event store.
- **Distributed tracing / OpenTelemetry.** Worth adding eventually but not part of launch scope.
- **Per-user notification preferences.** Phase A assumes static routing rules. Add when there's user demand.
- **A second queue for high-priority work.** The reserved third Railway service in the deployment topology section is a future option, not a launch concern.

---

## Effort Estimate

| Component | Effort |
|---|---|
| WebSocket retrofit for Data Health (independent immediate win) | 1-2 days |
| Schema additions (worker leases, events, notifications) | 1-2 days |
| Job factory + migration of 7 callsites | 3-4 days |
| Worker process (claim, lease, heartbeat, handlers) | 1 week |
| Stuck-job reconciler + monitoring queries | 2-3 days |
| pg_cron schedules + internal endpoints | 2-3 days |
| Notification dispatcher (Phase A: in-app only) | 3-4 days |
| Health checks + external monitoring setup | 2-3 days |
| Local dev mode + Railway deploy config | 2-3 days |
| Testing + cutover (often underestimated) | 1 week |

**Total: 4-5 weeks** for the worker + scheduler + in-app notifications.
**Push and email channels:** +1 week each, deferred to post-launch.

---

## Action Items Before Implementation

1. [ ] **Verify pg_cron + pg_net availability on your Supabase tier** by creating a one-minute test schedule and watching it fire for an hour. Single point of failure for the design — verify before committing to the rest.
2. [ ] **Read the cross-reference list** (graphile-worker, pg-boss docs) — substitute for expert review on concurrency patterns. ~2 hours total.
3. [ ] **Confirm the WebSocket `user:{user_id}` room pattern** (or equivalent) exists in `/ws` infrastructure or scope the addition.
4. [ ] **Decide on Phase A scope vs. notification preferences.** Default: ship without user-configurable preferences, add when there's user demand.
5. [ ] **Update the events schema** to use a `dispatched_at` flag column instead of the subquery-based partial index (resolved during this RFC).
6. [ ] **Set up Railway secrets** for `CRON_SECRET` and per-worker `WORKER_ID`.
7. [ ] **File the `exec_sql` security review as a separate ticket.** Do not bundle with this work. Different risk category, different review needed.

Once items 1-7 are resolved, implementation proceeds in the staged rollout order described in Implementation Notes: WebSocket retrofit (immediate, independent) → schema → factory → worker → scheduler → notification dispatcher → monitoring → staged migration of job types one at a time.


`verify_cron_secret` is a separate auth dependency from user auth. The secret is shared between pg_cron's job definition and an env var on the API