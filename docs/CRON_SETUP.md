# External Cron Setup

All scheduled work runs via HTTP POST to internal endpoints, authenticated with a `CRON_SECRET` Bearer token. Each cron job is a separate Railway service using `alpine/curl` as the Docker image.

**Status:** Live — 7 Railway cron services configured and running.

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
| `POST /api/internal/jobs/notification-dispatch` | Every 5 min | `*/5 * * * *` | Live |
| `POST /api/internal/jobs/stuck-reconciler` | Every 10 min | `*/10 * * * *` | Live |
| `POST /api/internal/jobs/refresh-persona-metrics` | Daily 03:00 UTC | `0 3 * * *` | Live |
| `POST /api/internal/jobs/analytics-rollup` | Daily 02:00 UTC | `0 2 * * *` | Live |

**Note:** `notification-dispatch` was designed for 2-minute intervals but Railway's minimum is 5 minutes. This is acceptable — notifications may be delayed up to 5 minutes from event creation.

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
2. Verify `events.dispatched_at` is being populated (notification dispatch working)
3. Check `/api/internal/jobs/health` returns healthy status
4. Monitor `qb_sync_config.last_synced_at` timestamps for QB sync
5. Check `contact_email_metrics` view freshness — should reflect emails from the last 24 hours
