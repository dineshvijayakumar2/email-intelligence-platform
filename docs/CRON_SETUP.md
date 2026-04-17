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
| `POST /internal/jobs/notification-dispatch` | Every 2 min | Dispatch pending event notifications |
| `POST /internal/jobs/stuck-reconciler` | Every 10 min | Mark expired-lease jobs as interrupted |
| `POST /internal/jobs/qb-sync` | Hourly at :15 | Sync QuickBase data for all active clients |
| `POST /internal/jobs/refresh-persona-metrics` | Daily 03:00 UTC | Refresh contact_email_metrics materialized view |
| `POST /internal/jobs/analytics-rollup` | Daily 02:00 UTC | Daily analytics rollup |

## cron-job.org Configuration

For each endpoint above:

- **URL:** `$BACKEND_URL/internal/jobs/<endpoint-name>`
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
URL:     POST https://your-backend.up.railway.app/internal/jobs/notification-dispatch
Headers: Authorization: Bearer <your-cron-secret>
Cron:    */2 * * * *
```

### Example: stuck-reconciler (every 10 min)

```
URL:     POST https://your-backend.up.railway.app/internal/jobs/stuck-reconciler
Cron:    */10 * * * *
```

### Example: qb-sync (hourly at :15)

```
URL:     POST https://your-backend.up.railway.app/internal/jobs/qb-sync
Cron:    15 * * * *
```

### Example: analytics-rollup (daily 02:00 UTC)

```
URL:     POST https://your-backend.up.railway.app/internal/jobs/analytics-rollup
Cron:    0 2 * * *
```

### Example: refresh-persona-metrics (daily 03:00 UTC)

```
URL:     POST https://your-backend.up.railway.app/internal/jobs/refresh-persona-metrics
Cron:    0 3 * * *
```

## Railway Cron Alternative

If using Railway's native cron jobs instead of cron-job.org, create a lightweight script per schedule:

```bash
#!/bin/bash
curl -X POST "$BACKEND_URL/internal/jobs/$ENDPOINT" \
  -H "Authorization: Bearer $CRON_SECRET" \
  -H "Content-Type: application/json" \
  --fail --silent --show-error
```

## Health Check

Verify cron is running correctly:

```bash
curl -X GET "$BACKEND_URL/internal/jobs/health" \
  -H "Authorization: Bearer $CRON_SECRET"
```

Returns `{"status": "healthy", "issues": []}` when everything is fine. Non-empty `issues` array means something needs attention (stuck jobs, pending backlog, undispatched events).

## Monitoring

After configuring cron:
1. Check `processing_jobs` table for `triggered_by='cron'` entries
2. Verify `events.dispatched_at` is being populated (notification dispatch working)
3. Check `/internal/jobs/health` returns healthy status
4. Monitor `qb_sync_config.last_synced_at` timestamps for QB sync
