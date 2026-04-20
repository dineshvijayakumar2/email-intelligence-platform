# External Cron Setup

All scheduled work runs via HTTP POST to internal endpoints, authenticated with a `CRON_SECRET` Bearer token.

## Prerequisites

1. **Set `CRON_SECRET` in production environment** (Railway env vars)
   - Generate: `openssl rand -hex 32`
   - Set the same value in both the backend service and the cron provider

2. **Backend URL** — replace `$BACKEND_URL` below with the Railway backend service URL (e.g., `https://your-backend.up.railway.app`)

## Cron Schedule

| Endpoint | Interval | Purpose |
|---|---|---|
| `POST /api/internal/jobs/notification-dispatch` | Every 2 min | Dispatch pending event notifications |
| `POST /api/internal/jobs/stuck-reconciler` | Every 10 min | Mark expired-lease jobs as interrupted |
| `POST /api/internal/jobs/gmail-sync` | Every 15 min | Sync Gmail mailboxes (per-mailbox interval check) |
| `POST /api/internal/jobs/outlook-sync` | Every 15 min | Sync Outlook mailboxes (per-mailbox interval check) |
| `POST /api/internal/jobs/qb-sync` | Hourly at :15 | Sync QuickBase data for auto-sync clients (respects `sync_interval_hours`) |
| `POST /api/internal/jobs/refresh-persona-metrics` | Daily 03:00 UTC | Refresh contact_email_metrics materialized view |
| `POST /api/internal/jobs/analytics-rollup` | Daily 02:00 UTC | Daily analytics rollup |

## cron-job.org Configuration

For each endpoint above:

- **URL:** `$BACKEND_URL/api/internal/jobs/<endpoint-name>`
- **Method:** POST
- **Headers:**
  ```
  Authorization: Bearer $CRON_SECRET
  Content-Type: application/json
  ```
- **Body:** (empty)
- **Timeout:** 30 seconds (60s for qb-sync)

### Example: notification-dispatch (every 2 min)

```
URL:     POST https://your-backend.up.railway.app/api/internal/jobs/notification-dispatch
Headers: Authorization: Bearer <your-cron-secret>
Cron:    */2 * * * *
```

### Example: stuck-reconciler (every 10 min)

```
URL:     POST https://your-backend.up.railway.app/api/internal/jobs/stuck-reconciler
Cron:    */10 * * * *
```

### Example: gmail-sync (every 15 min)

```
URL:     POST https://your-backend.up.railway.app/api/internal/jobs/gmail-sync
Cron:    */15 * * * *
```

### Example: outlook-sync (every 15 min)

```
URL:     POST https://your-backend.up.railway.app/api/internal/jobs/outlook-sync
Cron:    */15 * * * *
```

### Example: qb-sync (hourly at :15)

```
URL:     POST https://your-backend.up.railway.app/api/internal/jobs/qb-sync
Cron:    15 * * * *
```

### Example: analytics-rollup (daily 02:00 UTC)

```
URL:     POST https://your-backend.up.railway.app/api/internal/jobs/analytics-rollup
Cron:    0 2 * * *
```

### Example: refresh-persona-metrics (daily 03:00 UTC)

```
URL:     POST https://your-backend.up.railway.app/api/internal/jobs/refresh-persona-metrics
Cron:    0 3 * * *
```

## Railway Cron Alternative

If using Railway's native cron jobs instead of cron-job.org, create a lightweight script per schedule:

```bash
#!/bin/bash
curl -X POST "$BACKEND_URL/api/internal/jobs/$ENDPOINT" \
  -H "Authorization: Bearer $CRON_SECRET" \
  -H "Content-Type: application/json" \
  --fail --silent --show-error
```

## Disabling Legacy Sync Loops

Once Railway cron is confirmed working for Gmail/Outlook sync, disable the built-in asyncio loops:

```bash
# In Railway env vars for the backend service
DISABLE_SYNC_LOOPS=true
```

This prevents the legacy in-process `asyncio.sleep` loops from running. The cron endpoints become the sole trigger for email sync — observable, resilient to restarts, and consistent with QB sync.

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
