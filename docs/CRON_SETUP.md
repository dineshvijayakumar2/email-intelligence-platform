# External Cron Setup

All scheduled work runs via HTTP POST to internal endpoints, authenticated with a `CRON_SECRET` Bearer token. Each cron job is a separate Railway service using `alpine/curl` as the Docker image.

**Status:** Live — 6 Railway cron services active (notification-dispatch disabled).

## Current Setup

- **Cron provider:** Railway native cron services
- **Auth:** `CRON_SECRET` env var (shared across all cron services + backend)
- **Backend URL:** Railway backend service private URL (referred to as `$BACKEND_URL` below)
- **Minimum interval:** Railway cron supports a minimum of **5 minutes** between runs

## Cron Schedule

| Endpoint | Interval | Railway Cron | Status |
|---|---|---|---|
| `POST /api/internal/jobs/gmail-sync` | Every 15 min | `*/15 * * * *` | Live |
| `POST /api/internal/jobs/outlook-sync` | Every 15 min | `*/15 * * * *` | Live |
| `POST /api/internal/jobs/qb-sync` | Hourly at :15 | `15 * * * *` | Live |
| `POST /api/internal/jobs/notification-dispatch` | — | No schedule | Disabled (no user-facing notifications yet) |
| `POST /api/internal/jobs/stuck-reconciler` | Every 10 min | `*/10 * * * *` | Live |
| `POST /api/internal/jobs/refresh-persona-metrics` | Daily 03:00 UTC | `0 3 * * *` | Live |
| `POST /api/internal/jobs/analytics-rollup` | Daily 02:00 UTC | `0 2 * * *` | Live |

**Note:** `notification-dispatch` is currently disabled — no user-facing notifications are implemented yet. Job lifecycle events are no longer emitted (processing jobs page serves that purpose). Re-enable when real user-facing notifications are built (e.g., new customer discovered, at-risk alerts).

## Admin-Only Endpoints (not cron-scheduled)

These require `admin` role authentication, not `CRON_SECRET`:

| Endpoint | Purpose |
|---|---|
| `POST /api/internal/jobs/mailboxes/{mailbox_id}/run-pipeline` | Manually trigger email pipeline for a mailbox |
| `POST /api/internal/jobs/jobs/{job_id}/resume-pipeline` | Resume a failed/interrupted pipeline job |

---

## How to Create a Railway Cron Service

Each cron job is a standalone Railway service that runs on a schedule and curls the backend endpoint.

### Step 1: Add a new service

In your Railway project dashboard:
1. Click **+ New** → **Docker Image**
2. Set image to: `alpine/curl:latest`

### Step 2: Configure environment variables

Add these variables to the cron service:

| Variable | Value |
|---|---|
| `CRON_SECRET` | Same value as the backend's `CRON_SECRET` |
| `BACKEND_URL` | Your backend's Railway private domain (e.g., `http://backend.railway.internal:8000`) |

### Step 3: Set the start command

In the service settings, set the **Start Command** to:

```
curl -X POST "$BACKEND_URL/api/internal/jobs/<endpoint-name>" -H "Authorization: Bearer $CRON_SECRET" -H "Content-Type: application/json" --fail --silent --show-error
```

Replace `<endpoint-name>` with the specific job name (e.g., `gmail-sync`, `stuck-reconciler`).

### Step 4: Set the cron schedule

In the service settings under **Cron Schedule**, enter the cron expression from the schedule table above.

### Step 5: Name the service

Name it descriptively (e.g., `cron-gmail-sync`, `cron-stuck-reconciler`, `cron-persona-refresh`).

### Example: complete configuration for stuck-reconciler

| Setting | Value |
|---|---|
| **Image** | `alpine/curl:latest` |
| **Start Command** | `curl -X POST "$BACKEND_URL/api/internal/jobs/stuck-reconciler" -H "Authorization: Bearer $CRON_SECRET" -H "Content-Type: application/json" --fail --silent --show-error` |
| **Cron Schedule** | `*/10 * * * *` |
| **Variables** | `CRON_SECRET=<value>`, `BACKEND_URL=http://backend.railway.internal:8000` |

---

---

## Worker Deployment

The worker process runs background jobs (AI classification, extraction pipeline, embedding, reference linking). It's a separate Railway service from the backend API.

### Architecture

- Workers poll the `processing_jobs` table every 2 seconds
- Jobs are claimed with `SELECT FOR UPDATE SKIP LOCKED` — no duplicate execution across replicas
- Each worker emits a heartbeat every 30 seconds to extend its 5-minute lease
- On startup, workers auto-resume any interrupted pipeline jobs
- Workers do **NOT** need Redis — job coordination is entirely database-driven

### Creating the Worker Service in Railway

#### Step 1: Add a new service

In your Railway project dashboard:
1. Click **+ New** → **GitHub Repo**
2. Select the same repository as the backend API

#### Step 2: Configure the service

| Setting | Value |
|---|---|
| **Root Directory** | `/backend` |
| **Start Command** | `python3 -m src.workers.job_runner` |
| **Replicas** | 2 (recommended for availability) |

#### Step 3: Set environment variables

**Required** — worker will not start without these:

| Variable | Description |
|---|---|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Supabase service role key |

**Required for job handlers** — without these, specific job types will fail when claimed:

| Variable | Description | Used by |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude API key | `ai_analysis`, `ai_backfill` |
| `OPENAI_API_KEY` | OpenAI API key | `ai_analysis` (if configured as provider) |
| `GOOGLE_GENAI_API_KEY` | Google Gemini API key | `ai_analysis` (if configured as provider) |
| `EMBEDDING_PROVIDER` | `openai` or `google` | `embed_emails`, `reembed` |

**Optional tuning:**

| Variable | Default | Description |
|---|---|---|
| `WORKER_POLL_INTERVAL` | `2` | Seconds between job polls |
| `WORKER_ID` | `{hostname}-{pid}` | Override auto-generated worker ID |

**NOT needed by worker** (API-only variables — safe to omit):

- `REDIS_URL` — worker explicitly disables Redis
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` — OAuth, API-only
- `MICROSOFT_CLIENT_ID` / `MICROSOFT_CLIENT_SECRET` — OAuth, API-only
- `GOOGLE_REDIRECT_URI` / `MICROSOFT_REDIRECT_URI` — OAuth callbacks
- `SECRET_KEY` / `SUPABASE_JWT_SECRET` — API auth
- `CRON_SECRET` — cron endpoint auth
- All `VITE_*` variables — frontend only

**Practical recommendation:** Copy all backend env vars to the worker service. The worker ignores variables it doesn't need, and this avoids missing a variable when a new handler is added. The list above is for minimal deployments or debugging.

#### Step 4: Verify deployment

After deployment, check the Railway logs for:
```
Worker <worker-id> started, polling every 2s
```

Then create a test job (e.g., trigger pipeline from the UI) and confirm the worker picks it up.

### Job Types

| Job Type | Handler | What it does |
|---|---|---|
| `email_pipeline` | 10-step pipeline | Full sync → extract → classify → embed flow |
| `ai_analysis` | AI classification | Claude-based email classification + bucket engine |
| `ai_backfill` | Backfill classifier | Batch classification of unanalyzed emails |
| `reembed` | Vector embeddings | Re-embed emails/companies/operations |
| `reference_extraction` | QB ref linking | Regex-based QB reference extraction from email bodies |
| `notification_dispatch` | Event notifications | Dispatch pending event notifications (currently idle — cron disabled, no events emitted) |

### Scaling

Workers scale horizontally — add replicas in Railway to increase throughput. Each replica gets a unique `worker_id` from its hostname. The database lease mechanism prevents duplicate execution. Start with 2 replicas; increase if `processing_jobs` shows a backlog of `pending` jobs.

---

## Sync Architecture

Gmail and Outlook sync services are initialized at startup but remain idle. They only activate when the external cron calls the sync endpoint. There are no background asyncio loops — sync is 100% cron-triggered.

The `email_pipeline` is not cron-scheduled. It runs as a worker job, triggered automatically after sync completes (when new emails are fetched) or manually via the admin endpoint.

## Health Check

Verify cron is running correctly:

```bash
curl -X GET "$BACKEND_URL/api/internal/jobs/health" \
  -H "Authorization: Bearer $CRON_SECRET"
```

Returns `{"status": "healthy", "issues": []}` when everything is fine. Non-empty `issues` array means something needs attention (stuck jobs, pending backlog, undispatched events).

## Monitoring

After configuring cron:
1. Check `processing_jobs` table for `triggered_by='cron'` entries
2. ~~Verify `events.dispatched_at` is being populated~~ (notification dispatch currently disabled)
3. Check `/api/internal/jobs/health` returns healthy status
4. Monitor `qb_sync_config.last_synced_at` timestamps for QB sync
5. Check `contact_email_metrics` view freshness — should reflect emails from the last 24 hours
