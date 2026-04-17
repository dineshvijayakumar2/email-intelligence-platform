# Email Pipeline Handler — Design Document

**Created:** 2026-04-17
**Status:** Approved for Phase 2 implementation 2026-04-17 with the decisions below.

---

## Resolved Decisions (Phase 2)

**Q1 (lightweight vs full mode):** `lightweight=True` for sync-triggered pipelines. Full mode is a separate admin action ("Run Full Extraction") not part of the auto-pipeline.

**Q2 (client_id resolution):** Pipeline handler resolves `client_id` from the mailbox row on first use. Sync trigger code passes `client_id=None` and lets the handler look it up.

**Q3 (max_attempts):** `max_attempts=1`. Worker crash → reconciler marks job `interrupted` → admin sees it in operations center → explicit "Resume" creates a new job with `completed_steps` pre-populated. Automatic retry would re-run the entire pipeline from step 1, wasting potentially hours of work. The resume mechanism is the recovery path.

**Q4 (zero-email syncs):** Sync service checks `success_count > 0` BEFORE creating the pipeline job. Pipeline handler does NOT contain this check — it runs whatever pending work exists. Manual triggers also have no `success_count` check — admin is explicitly saying "run this now."

---

## 1.1 Pipeline Steps: Actual Implementations

### Overview

The current post-sync chain lives in `ExtractionOrchestrator.run_extraction()` at
`backend/src/services/extraction_orchestrator.py:289-464`. After the 13-step extraction
completes, it calls 4 additional methods (embed, classify, bucket, thread re-eval).

The 8 pipeline steps map to the code as follows:

| # | Pipeline Step | Implementation | File:Line | Signature | Caller | Idempotent? | Callable? |
|---|---|---|---|---|---|---|---|
| 1 | **extract_and_link** | `ExtractionOrchestrator.run_extraction(lightweight=True)` | extraction_orchestrator.py:289 | `(self, exclude_mailing_lists, exclude_noreply, exclude_shared, exclude_internal, force_relink, skip_role_classification, lightweight) -> Dict` | sync services, analytics router | Yes — upserts contacts/companies, idempotent email linking | **Clean callable** — instantiate orchestrator, call method |
| 2 | **assign_threads** | `ExtractionOrchestrator._assign_canonical_threads()` | extraction_orchestrator.py:1249 | `(self) -> None` | Called by run_extraction after step 9 | Yes — only processes `canonical_thread_id IS NULL` emails | **Tangled** — private method on orchestrator, needs `self.mailbox_id`, `self.client_id`, `self.client`, `self._execute_with_retry` |
| 3 | **evaluate_threads** | `ExtractionOrchestrator._update_affected_threads()` | extraction_orchestrator.py:1332 | `(self) -> None` | Called twice: after assign_threads AND after AI classify | Yes — `save_thread_statuses` does upsert (INSERT ON CONFLICT UPDATE) | **Tangled** — same as step 2 |
| 4 | **refresh_counts** | `ExtractionOrchestrator._refresh_email_counts()` | extraction_orchestrator.py:1148 | `(self) -> None` | Called by run_extraction after step 9 | Yes — RPCs recompute from scratch each time | **Tangled** — uses `self.client` and `self.client_id`, but logic is trivial (2 RPC calls) |
| 5 | **embed_emails** | `VectorService.embed_emails_batch()` | vector_service.py:277 | `async (self, client_id, batch_size=500, limit=None, on_progress=None) -> dict` | `_embed_new_emails()` wrapper | Yes — queries `embedding IS NULL`, skips already-embedded | **Clean callable** — async, create VectorService(sb), call directly |
| 6 | **ai_classify** | `AIEmailAnalyzer.analyze_all_unanalyzed()` | ai_email_analyzer.py:1499 | `(self, mailbox_id, client_id=None, max_emails=5000, date_from=None, date_to=None, job_id=None) -> dict` | `_auto_trigger_ai_analysis()` wrapper | Yes — queries `processing_status != 'completed'`, skips classified | **Clean callable** — sync, create AIEmailAnalyzer(sb), call directly |
| 7 | **bucket_engine** | `ActionBucketEngine.process_email_buckets()` | ai_action_bucket_engine.py:430 | `(self, mailbox_id, force=False) -> dict` | `_auto_trigger_ai_analysis()` after classify | Yes — recalculates from `ai_email_intelligence` rows | **Clean callable** — sync, create ActionBucketEngine(sb), call directly |
| 8 | **evaluate_threads_final** | `ExtractionOrchestrator._update_affected_threads()` | extraction_orchestrator.py:1332 | Same as step 3 | Called after AI classify to apply override rules | Yes — same upsert logic | **Tangled** — same method as step 3, second invocation |

### Critical finding: Steps 1-2 of the spec are ONE atomic call

The task spec lists "Extract contacts" and "Link emails" as separate steps. In practice, they are inseparable:

- Steps 1-9 of the extraction orchestrator share in-memory state via `self.step_results`
- Step 3 (dedup) reads `self.step_results[2]['contacts']`
- Step 4 (resolve) reads `self.step_results[2]['contacts']`
- Step 5 (upsert contacts) reads `self.step_results[2]` and `self.step_results[4]`
- Step 9 (link emails) is the final step of this chain

**They cannot be individually resumed.** The extraction orchestrator must run steps 1-9 as one unit.

The pipeline handler treats extraction as **one step**: `extract_and_link`.

### Critical finding: Two thread evaluation passes, not one

The current code runs `_update_affected_threads()` **twice**:

1. **First pass** (line 404): After thread assignment, BEFORE AI classification. Evaluates thread status from email metadata only (sent_date, is_outbound, response patterns).
2. **Second pass** (line 462): AFTER AI classification. Picks up newly-classified intents and applies override rules (complaint → urgent, thank_you → closing, etc.).

Both passes call the same method. The pipeline preserves this as steps 3 and 8.

### Critical finding: Tangled methods need orchestrator instance

Steps 2, 3, 4, 8 are private methods on `ExtractionOrchestrator`. They access:
- `self.mailbox_id`, `self.client_id` (set in constructor)
- `self.client` (Supabase service-role client, created in constructor)
- `self.lookback_days` (set in constructor, default 7)
- `self._execute_with_retry()` (retry wrapper)

**Resolution: The pipeline handler creates an ExtractionOrchestrator instance** (without calling `run_extraction`) purely to access these methods. No refactoring needed — the constructor only sets instance variables and fetches `client_id` if not provided.

```python
# Pipeline handler creates orchestrator for its utility methods:
orch = ExtractionOrchestrator(mailbox_id=mailbox_id, client_id=client_id,
                              extraction_mode='incremental', lookback_days=7)
orch.client = sb  # Use the worker's Supabase client
```

### Critical finding: Worker process lacks module-level singletons

The current `_auto_trigger_ai_analysis()` calls `get_email_analyzer()` — a module-level singleton initialized during API startup (`ai.py:62`). This singleton does NOT exist in the worker process.

**Resolution:** The pipeline handler creates its own instances:
- `AIEmailAnalyzer(sb)` — same pattern as `ai_analysis_handler.py`
- `ActionBucketEngine(sb)` — same pattern
- `VectorService(sb)` — same pattern

### Step 1 child job note

`ExtractionOrchestrator.run_extraction()` creates its own row in `extraction_jobs` table (line 327). This means step 1 produces a child row in `extraction_jobs` alongside the parent `processing_jobs` row for the pipeline. This is acceptable — `extraction_jobs` is a different table used for extraction-specific progress tracking. The pipeline's `processing_jobs` row is the admin-facing observability.

---

## 1.2 Mailbox Scope and Concurrency

### Scope: Per-mailbox

Each pipeline run processes **one mailbox**. This matches the existing trigger:

```python
# gmail_sync_service.py:295
await self._trigger_post_sync_extraction(mailbox_id, success_count)
```

Each sync completion fires for one mailbox. The pipeline job carries `mailbox_id` in its parameters.

### Concurrent pipelines for different mailboxes: Allowed

Two mailboxes can run their pipelines concurrently. No shared state between them. The worker's `SELECT FOR UPDATE SKIP LOCKED` naturally distributes them across workers.

### Concurrent pipelines for the same mailbox: Must not happen

If sync fires twice for the same mailbox before the first pipeline completes, the second should be silently skipped.

**Dedup mechanism:** Partial unique index on `processing_jobs`:

```sql
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS
  uq_email_pipeline_per_mailbox
ON processing_jobs(mailbox_id)
WHERE job_type = 'email_pipeline' AND status IN ('pending', 'running');
```

The factory's existing `JobAlreadyActive` catch (SQLSTATE 23505) handles the collision. The sync trigger wraps `create_job` in try/except and logs "pipeline already active, skipping."

---

## 1.3 Data Boundary Per Step

| # | Step | Scope | How it finds work |
|---|---|---|---|
| 1 | extract_and_link | **Incremental: last 7 days** | `extraction_mode='incremental', lookback_days=7` — queries emails by `sent_date` range. Upserts are idempotent. |
| 2 | assign_threads | **All pending** | Queries `canonical_thread_id IS NULL` for the mailbox. Processes all unresolved. |
| 3 | evaluate_threads | **Recent threads** | Queries threads with emails in last `max(lookback_days, 7)` days. Only updates affected threads. |
| 4 | refresh_counts | **All (full recompute)** | RPCs `update_contact_email_counts_from_junction` and `update_company_email_counts_from_junction` recompute from scratch for the client. |
| 5 | embed_emails | **All pending** | Queries `embedding IS NULL` for the client. Processes all unembedded. |
| 6 | ai_classify | **All pending** | Queries emails without completed `ai_email_intelligence` row. `date_from="all"`. |
| 7 | bucket_engine | **All classified** | Queries all `processing_status='completed'` rows for the mailbox, re-derives buckets. |
| 8 | evaluate_threads_final | **Same as step 3** | Same query, but now AI intent data is available for override rules. |

**Every step is "all pending work" mode.** No step requires knowledge of "which specific emails triggered this run." This is ideal for resume — a resumed pipeline doesn't need to know what the original sync contained.

---

## 1.4 Single-Flight vs Child Jobs

**Decision: Call underlying functions directly.** The pipeline job IS the observability layer.

Consequences and mitigations:

| Scenario | Risk | Mitigation |
|---|---|---|
| Admin triggers manual `ai_analysis` while pipeline is at classify step | Two concurrent classification processes | **Accept this.** `analyze_all_unanalyzed` is idempotent — each email gets a row with `INSERT ... ON CONFLICT DO NOTHING` on the first classification, and subsequent calls skip it. Two concurrent runs waste API credits but don't corrupt data. |
| Admin triggers manual `reembed` while pipeline is at embed step | Two concurrent embedding processes | **Accept this.** `embed_emails_batch` queries `embedding IS NULL` — the first process to embed a row wins, the second skips it. No data corruption. |
| Pipeline creates extraction child job while manual extraction is running | Extraction dedup index prevents collision | **Already handled.** The `extraction_jobs` table doesn't have the same dedup mechanism, but `_step_upsert_contacts/companies` use upserts, so concurrent runs produce identical results. |

If the "wasted API credits" scenario needs stricter control in the future, the pipeline can check `processing_jobs` for active `ai_analysis` or `reembed` jobs and skip the step. But this adds complexity that isn't needed now.

---

## 1.5 Failure Model

### Per-step return contracts

| # | Step | Return type | Failure mode | Partial success? |
|---|---|---|---|---|
| 1 | extract_and_link | `dict` with `success: bool` | Exception on infra failure; `success: False` on validation failure | Yes — some contacts/companies may fail to upsert while others succeed. The dict includes counts. |
| 2 | assign_threads | `None` | Exception (caught internally, logged as warning) | No — either resolves all unresolved or fails entirely |
| 3 | evaluate_threads | `None` | Exception (caught internally, logged as warning) | Yes — individual thread evaluations can fail while others succeed |
| 4 | refresh_counts | `None` | Exception (caught internally per RPC) | Yes — contact count RPC can succeed while company count RPC fails |
| 5 | embed_emails | `dict` with `embedded: int` | Exception on service failure | Yes — some emails may embed while others fail. Returns counts. |
| 6 | ai_classify | `dict` with `total_analyzed, total_failed` | Exception on service failure; circuit breaker after 3 consecutive zero-success batches | Yes — common for some emails to fail (malformed body, API timeout). Returns counts. |
| 7 | bucket_engine | `dict` with counts | Exception on infra failure | Yes — individual bucket derivations can fail |
| 8 | evaluate_threads_final | `None` (same as step 3) | Exception (caught internally) | Yes |

### Pipeline failure policy

**Proposed:** Each step is wrapped in try/except. The pipeline distinguishes:

1. **Hard failure (exception raised):** Step failed entirely. Log error, persist `completed_steps`, mark job `failed`. Admin can resume.
2. **Partial success (step returns but with failures):** Step completed with some items failing. Log the failure counts in `error_log`, **continue to next step**. The failed items will be retried on the next pipeline run (they remain in "pending" state in the DB).
3. **Empty result (no work to do):** Treated as success. Step logs "0 items to process" and continues.

Steps 2, 3, 4, 8 currently catch their own exceptions and log warnings. The pipeline should NOT double-catch — it should let the existing try/except handle partial failures and only catch unexpected exceptions that propagate up.

For steps 5, 6, 7: the underlying functions return structured dicts with counts. The pipeline logs these and continues regardless. A step where 15/20 emails classified is still progress — the 5 failures will be retried next time.

### Structured step result

The pipeline persists per-step results in `error_summary` JSONB:

```json
{
  "progress_pct": 75,
  "progress_message": "Running ai_classify...",
  "step_results": {
    "extract_and_link": {"duration_s": 12.3, "contacts": 45, "companies": 12},
    "assign_threads": {"duration_s": 2.1, "resolved": 30},
    "embed_emails": {"duration_s": 8.5, "embedded": 150, "failed": 2},
    "ai_classify": {"duration_s": 45.2, "analyzed": 140, "failed": 5}
  }
}
```

---

## 1.6 Trigger Paths

### Current trigger point (to be replaced)

**Gmail sync** — `gmail_sync_service.py:295` (in `_sync_mailbox`):
```python
await self._trigger_post_sync_extraction(mailbox_id, success_count)
```

**Gmail sync (legacy user path)** — `gmail_sync_service.py:538` (in `_sync_user`):
```python
await self._trigger_post_sync_extraction(mailbox['id'], success_count)
```

**Outlook sync** — `outlook_sync_service.py:293` (in `_sync_mailbox`):
```python
await self._trigger_post_sync_extraction(mailbox_id, success_count)
```

**Outlook sync (legacy user path)** — `outlook_sync_service.py:535` (in `_sync_user`):
```python
await self._trigger_post_sync_extraction(mailbox['id'], success_count)
```

All four paths call `_trigger_post_sync_extraction()` which:
1. Checks `emails_synced > 0`
2. Creates `asyncio.create_task(_run_extraction_background(mailbox_id))`
3. `_run_extraction_background` creates a `ThreadPoolExecutor`, runs `ExtractionOrchestrator.run_extraction(lightweight=True)` in it

**Replacement:** Instead of calling `_trigger_post_sync_extraction`, create an `email_pipeline` job:

```python
# Replace _trigger_post_sync_extraction call with:
if success_count > 0:
    try:
        from ..services.jobs import create_job, JobSpec, JobAlreadyActive
        create_job(sb, JobSpec(
            job_type='email_pipeline',
            mailbox_id=mailbox_id,
            client_id=client_id,  # Need to fetch if not available
            parameters={'trigger_source': 'sync'},
            triggered_by='sync',
        ))
    except JobAlreadyActive:
        logger.info(f"Pipeline already active for mailbox {mailbox_id}")
    except Exception as e:
        logger.error(f"Failed to create pipeline job: {e}")
```

**Issue:** The sync services don't have `client_id` readily available at the trigger point. `_sync_mailbox` has the mailbox dict which may contain `client_id`. `_sync_user` fetches the mailbox but doesn't extract client_id. The factory allows `client_id=None` — we can let the pipeline handler resolve it from the mailbox row.

### Manual trigger (new endpoint)

`POST /internal/jobs/run-pipeline/{mailbox_id}` — admin triggers pipeline for a specific mailbox. Uses existing `verify_cron_secret` or admin role auth.

### Resume from failure

`POST /internal/jobs/resume-pipeline/{job_id}` — creates a new pipeline job with `completed_steps` pre-populated from the failed job's parameters.

---

## Refactoring Prerequisites

### Required before Phase 2: None

The pipeline handler can work without refactoring by:
1. Creating an `ExtractionOrchestrator` instance for utility methods (steps 2, 3, 4, 8)
2. Creating standalone service instances for clean callables (steps 5, 6, 7)
3. Calling `run_extraction(lightweight=True)` for step 1

### Recommended (not blocking): Extract utility methods

Steps 2, 3, 4, 8 use private methods on `ExtractionOrchestrator`. While the handler CAN access them (Python doesn't enforce `_` privacy), it would be cleaner to extract them into standalone functions in a shared module. This is optional and should be a separate task.

---

## Open Questions for Human Decision

### Q1: Should step 1 run in `lightweight=True` or full mode?

Current auto-sync uses `lightweight=True` (skips engagement scoring, company stats, report generation — steps 10-12). The pipeline replaces the auto-sync chain.

**Recommendation:** `lightweight=True` for sync-triggered pipelines. Full mode is a separate admin action ("Run Full Extraction").

### Q2: What `client_id` resolution strategy for the sync trigger?

The sync services don't always have `client_id` at the trigger point. Options:
- **A:** Query the mailbox row to get `client_id` before creating the job (one extra DB call)
- **B:** Let the pipeline handler resolve it from `mailbox_id` on execution (simpler trigger code)
- **C:** Pass `client_id=None` and let each step resolve it internally (current pattern)

**Recommendation:** Option B — the pipeline handler resolves `client_id` from the mailbox row on first use.

### Q3: Should `max_attempts` be 1 or 3?

The task spec suggests `max_attempts=1` because "pipeline handles its own retry via resume." But the worker's claim mechanism uses `attempts < max_attempts`. With `max_attempts=1`:
- If the worker crashes mid-pipeline, the job is permanently stranded (can't be reclaimed)
- Admin must manually resume

With `max_attempts=3`:
- Worker crash → reconciler marks as `interrupted` → another worker reclaims
- But the reclaimed job starts from the beginning (no `completed_steps` awareness in the claim logic)

**Recommendation:** `max_attempts=2`. First attempt runs normally. If worker crashes, one automatic retry starts from the beginning (all steps are idempotent, so this is safe). If it fails again, admin intervention needed. The `completed_steps` resume mechanism is for deliberate retries of genuinely failed steps, not crash recovery.

### Q4: Should the pipeline skip embed/classify for zero-email syncs?

When `success_count == 0` (no new emails), the current code skips extraction entirely. But embed and classify steps process ALL pending work (not just from this sync). Should the pipeline:
- **A:** Skip entirely when triggered by sync with 0 new emails (current behavior)
- **B:** Still run — there may be pending classify/embed work from previous failed runs

**Recommendation:** Option A for sync-triggered, Option B for manual-triggered. The sync handler already checks `success_count > 0` before creating the job.

---

## Summary

The pipeline is feasible with the existing code. No refactoring prerequisites block Phase 2. The 8 steps map cleanly to existing implementations:

- **3 steps are clean callables** (embed, classify, bucket) — create service instance, call method
- **1 step is a clean high-level call** (extract_and_link) — create orchestrator, call `run_extraction`
- **4 steps are tangled but accessible** (assign_threads, evaluate_threads x2, refresh_counts) — create orchestrator instance, call private methods

The main implementation work is:
1. Write the handler (~150 lines)
2. Register it in `__init__.py` (1 line)
3. Create the dedup index (migration)
4. Replace 4 trigger points in sync services (~20 lines each)
5. Add 2 API endpoints (trigger + resume)
