# Engineering Best Practices — Email Intelligence Platform

Hard-won patterns from 2 months of production operation. Follow these to avoid repeating costly mistakes.

---

## 1. Supabase / PostgreSQL

### Never do individual row updates in a loop

**Problem:** Updating 600K rows one at a time = 600K REST API calls → connection pool exhausted → all other queries timeout → frontend hangs.

**Solution:**
- Create batch RPC functions that accept arrays
- Write in chunks of 25-100 rows per RPC call
- Add 0.1-0.5s pause between chunks

```sql
-- Example: batch update RPC
CREATE OR REPLACE FUNCTION batch_update_embeddings_emails(
    p_ids uuid[], p_embeddings vector(768)[]
) RETURNS integer LANGUAGE plpgsql AS $$
DECLARE updated integer := 0;
BEGIN
    FOR i IN 1..array_length(p_ids, 1) LOOP
        UPDATE emails SET embedding = p_embeddings[i] WHERE id = p_ids[i];
        updated := updated + 1;
    END LOOP;
    RETURN updated;
END; $$;
```

```python
# Python: write in chunks, not individual rows
DB_CHUNK = 25
for ci in range(0, len(ids), DB_CHUNK):
    supabase.rpc("batch_update_embeddings_emails", {
        "p_ids": ids[ci:ci+DB_CHUNK],
        "p_embeddings": embeddings[ci:ci+DB_CHUNK],
    }).execute()
    time.sleep(0.1)  # Let other queries breathe
```

### Query gotchas

| Pattern | Issue | Fix |
|---------|-------|-----|
| `.neq(col, val)` | Excludes NULLs silently | Filter in Python instead |
| `.in_(col, ids)` | Max ~500 IDs | Batch into groups of 500 |
| `len(batch) < PAGE_SIZE` | Wrong pagination break | Use `len(batch) == 0` |
| Boolean filters | Supabase expects lowercase strings | Use `'true'` / `'false'` |
| `ALTER COLUMN TYPE` on large tables | Full table rewrite → timeout | `DROP + ADD COLUMN` (instant) |
| `CREATE INDEX CONCURRENTLY` | Can't run in SQL editor (transaction block) | Use regular `CREATE INDEX`, run separately |
| Statement timeout | Free tier ~30s, paid ~60s | Keep queries simple, batch heavy ops |

### Migration patterns

- Split large migrations: DDL first, then indexes, then RPC functions (run each separately)
- `DROP COLUMN IF EXISTS + ADD COLUMN` is instant — `ALTER TYPE` rewrites the table
- Always test on smaller dataset before running on production
- pgvector HNSW/IVFFlat indexes: max 2000 dimensions

---

## 2. Background Processing

### Never use BackgroundTasks for heavy work

**Problem:** FastAPI's `BackgroundTasks.add_task()` runs in the event loop. Synchronous Supabase calls block all HTTP request handling.

**Solution:**

| Work type | Duration | Use |
|-----------|----------|-----|
| Quick async (< 30s) | Short | `BackgroundTasks.add_task()` |
| Heavy sync (minutes+) | Long | `threading.Thread(daemon=True).start()` |
| Heavy async (minutes+) | Long | `asyncio.create_task()` |

```python
# Wrong — blocks event loop
background_tasks.add_task(heavy_sync_function)

# Right — separate thread
import threading
thread = threading.Thread(target=heavy_sync_function, daemon=True)
thread.start()

# Right — async version
asyncio.create_task(heavy_async_function())
```

### Always wrap Supabase calls in async functions

```python
# Wrong — blocks event loop
result = supabase.table("emails").select("*").execute()

# Right — run in thread pool
result = await asyncio.to_thread(
    lambda: supabase.table("emails").select("*").execute()
)
```

### Always provide stop/cancel mechanism

For any background job that runs > 1 minute:
- Store a cancel flag in memory (`_cancel[job_id] = True`)
- Check between batches: `if cancel_check(): break`
- Return partial results, not error
- Frontend: show a Stop button that calls the cancel endpoint

---

## 3. Rate Limiting & External APIs

### Google Embedding API (Gemini)

| Setting | Free tier | Paid tier |
|---------|-----------|-----------|
| Batch size | 5-20 texts/call | 50-100 texts/call |
| Delay between batches | 4-6s | 1-2s |
| On 429 | Exponential backoff: 4s→8s→16s→32s→64s | Same but rarer |
| After 429 recovery | 30s cooldown | 30s cooldown |
| After 5 failed retries | Skip batch + continue (don't abort job) | Same |

### Embedding data format

PostgreSQL `vector` type requires string format: `"[0.1, 0.2, 0.3]"`

```python
# Convert Python list to PostgreSQL vector string
def vecs_to_pg(embeddings):
    return [f"[{','.join(str(v) for v in emb)}]" for emb in embeddings]
```

### Use `output_dimensionality` to control vector size

`gemini-embedding-001` natively outputs 3072 dims, but pgvector indexes only support up to 2000. Force 768 dims:

```python
GoogleGenerativeAIEmbeddings(
    model="models/gemini-embedding-001",
    output_dimensionality=768,  # Truncate to 768 for pgvector HNSW compatibility
)
```

---

## 4. Frontend Patterns

### API base URL — don't double-prefix

`apiClient.ts` already prepends `/api`. Service modules should use `/v1/...` not `/api/v1/...`:

```typescript
// Wrong — results in /api/api/v1/...
const BASE = '/api/v1/intelligence-config';

// Right
const BASE = '/v1/intelligence-config';
```

### Always add ClientSelector to admin pages

Any page managing per-client data **must** include `<ClientSelector>` in the header for explicit selection. Never rely on implicit localStorage resolution alone — the user may not have visited an analytics page yet.

```typescript
import { ClientSelector } from '../../components/analytics/ClientSelector';

const [clientId, setClientId] = useState<string>(
    localStorage.getItem('analytics_client_id') || ''  // key is 'analytics_client_id', NOT 'selectedClientId'
);

// In JSX header:
<ClientSelector value={clientId} onChange={setClientId} />

// Guard content when no client selected:
{!clientId && <Card>Select a client above</Card>}
{clientId && <>...page content...</>}

// Pass to all API calls:
api.get(`/endpoint?client_id=${clientId}`);
```

### Don't wipe data on transient errors

```typescript
// Wrong — flashes "no data" on network blip
catch { setData(null); }

// Right — keep previous data, show error only if first load fails
catch { if (!data) setStatsError(true); }
```

### Route redirects with params

`<Navigate to="/new-path/:id" />` passes literal `:id` — use a helper:

```tsx
const RedirectWithParams = ({ to }) => {
    const { mailboxId } = useParams();
    return <Navigate to={`${to}/${mailboxId}`} replace />;
};
```

---

## 5. CSV Import / Data Loading

### Always strip UTF-8 BOM

Windows/Excel CSV exports include `\ufeff` BOM — strip before parsing:

```python
csv_clean = body.csv_text.strip().lstrip('\ufeff')
reader = csv.DictReader(io.StringIO(csv_clean))
```

### Handle field name variations

Different sources use different field names. Handle both:

```python
dept = r.get("dept") or r.get("department")
tag = r.get("tag") or r.get("mvp_tag")
if tag == "(none)": tag = None
```

---

## 6. Extraction Pipeline

### Lightweight mode for auto-sync

Gmail/Outlook sync triggers extraction after every cycle. Full 13-step pipeline is too heavy for incremental sync.

```python
# Auto-sync: lightweight (steps 1-9 only)
orchestrator.run_extraction(lightweight=True)

# Manual trigger: full pipeline
orchestrator.run_extraction(lightweight=False)
```

Steps skipped in lightweight mode: engagement scoring, response time calculation, company stats, report generation.

### LIVE vs Archive mailboxes

- LIVE (Gmail/Outlook): sync service handles everything. Don't show "Start Processing" button.
- Archive (MBOX/PST/OLM): old processing pipeline needed for file import only.

---

## 7. Disambiguation

### PostgREST FK ambiguity

When a table has multiple FKs to the same target, PostgREST requires explicit FK hint:

```python
# Wrong — ambiguous
.select("thread_status, customer_companies(company_name)")

# Right — specify FK
.select("thread_status, customer_companies!thread_status_primary_company_id_fkey(company_name)")
```

### Ant Design Menu key uniqueness

Parent menu item and first child cannot share the same `key`:

```tsx
// Wrong — duplicate key '/customers'
{ key: '/customers', label: 'Customers', children: [
    { key: '/customers', label: 'Companies' },

// Right
{ key: 'customers-menu', label: 'Customers', children: [
    { key: '/customers', label: 'Companies' },
```
