"""
Test script for reembed job state migration (migrations 073/074).

Matches the project's existing testing style: integration script that runs
against a real database, NOT pytest unit tests with mocks. Reason: the
single-flight guarantee and the atomic-increment guarantee are worthless
without a real DB to exercise them. Mocks would silently pass tests that
don't actually verify the constraint.

Prerequisites:
    - Migrations 073 and 074 applied to the target database
    - DATABASE_URL set in backend/.env.production (or as env var)
    - A test client_id available in clients(id) — the script will look up the
      first available client; override with TEST_CLIENT_ID env var
    - Backend server running at http://localhost:3000 for HTTP tests (#11)

Run:
    cd backend
    python test_reembed_jobs.py

Cleanup:
    The script attempts to delete its test jobs in a finally block. If a run
    is interrupted, manually clean up:
        DELETE FROM processing_jobs WHERE parameters->>'_test_marker' = 'reembed_jobs_test';
"""
import asyncio
import os
import sys
import time
import uuid
from pathlib import Path

# Make the helper importable
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

# Load env from .env.production
try:
    from dotenv import load_dotenv
    for p in [Path(__file__).parent / ".env.production", Path(__file__).parent / ".env"]:
        if p.exists():
            load_dotenv(p, override=False)
            break
except ImportError:
    pass

from supabase import create_client
from services.reembed_job_state import ReembedJobState, ActiveJobExists, JOB_TYPE  # type: ignore


# ── Test infra ───────────────────────────────────────────────────────────────

class C:
    G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; B = "\033[94m"; END = "\033[0m"


passed = 0
failed = 0
created_job_ids: list[str] = []


def t_pass(name: str):
    global passed
    passed += 1
    print(f"{C.G}PASS{C.END}  {name}")


def t_fail(name: str, msg: str):
    global failed
    failed += 1
    print(f"{C.R}FAIL{C.END}  {name}: {msg}")


def get_supabase():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        print(f"{C.R}ERROR{C.END}: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
        sys.exit(2)
    return create_client(url, key)


def get_test_client_id(sb) -> str:
    cid = os.getenv("TEST_CLIENT_ID")
    if cid:
        return cid
    resp = sb.table("clients").select("id").limit(1).execute()
    if not resp.data:
        print(f"{C.R}ERROR{C.END}: No clients in database; set TEST_CLIENT_ID to a real UUID")
        sys.exit(2)
    return resp.data[0]["id"]


def mark_test_job(sb, job_id: str):
    """Tag the job so cleanup can find it even if the script crashes.

    MERGES the marker into the existing parameters JSONB instead of replacing
    it — replacing would wipe out legitimate test inputs like {limit, tables}.
    """
    resp = sb.table("processing_jobs").select("parameters").eq("id", job_id).single().execute()
    existing = (resp.data or {}).get("parameters") or {}
    existing["_test_marker"] = "reembed_jobs_test"
    sb.table("processing_jobs").update({"parameters": existing}).eq("id", job_id).execute()
    created_job_ids.append(job_id)


def cleanup(sb):
    if created_job_ids:
        try:
            sb.table("processing_jobs").delete().in_("id", created_job_ids).execute()
            print(f"{C.B}cleanup{C.END}: removed {len(created_job_ids)} test job(s)")
        except Exception as e:
            print(f"{C.Y}cleanup warning{C.END}: {e}")


# ── Tests ────────────────────────────────────────────────────────────────────

def test_create_and_lifecycle(state: ReembedJobState, client_id: str):
    """Tests #1, #2, #5, #6: create, mark_running, mark_failed, mark_stopped."""
    job_id = state.create_job(
        client_id=client_id,
        tables=["emails"],
        limit=10,
        triggered_by_user_id="test-user",
    )
    mark_test_job(state._sb, job_id)
    job = state.get_job(job_id)
    if job and job["job_type"] == JOB_TYPE and job["status"] == "pending" \
            and job["client_id"] == client_id and job["parameters"].get("limit") == 10:
        t_pass("test_create_job inserts with correct fields")
    else:
        t_fail("test_create_job", f"wrong shape: {job}")

    state.mark_running(job_id)
    job = state.get_job(job_id)
    if job["status"] == "running" and job["started_at"]:
        t_pass("test_mark_running transitions to running with timestamp")
    else:
        t_fail("test_mark_running", f"got {job}")

    # Test mark_stopped (terminal) — also serves test #6
    state.mark_stopped(job_id)
    job = state.get_job(job_id)
    if job["status"] == "stopped" and job["completed_at"]:
        t_pass("test_mark_stopped uses 'stopped' and stamps completed_at")
    else:
        t_fail("test_mark_stopped", f"got {job}")

    # Separate job for mark_failed test
    job_id_2 = state.create_job(client_id, ["emails"], None, "test-user")
    mark_test_job(state._sb, job_id_2)
    state.mark_running(job_id_2)
    state.mark_failed(job_id_2, {"type": "RuntimeError", "error": "test failure"})
    job = state.get_job(job_id_2)
    if job["status"] == "failed" and job["completed_at"] \
            and job["error_summary"]["total_errors"] >= 1:
        t_pass("test_mark_failed stamps completed_at and preserves error")
    else:
        t_fail("test_mark_failed", f"got {job}")


def test_atomic_increment(state: ReembedJobState, client_id: str):
    """Test #3: increment_job_progress is truly atomic via the SQL function.

    Two sequential calls with deltas 5 and 3 should leave processed_records at 8.
    A read-modify-write bug would clobber and leave it at 3. This test does NOT
    yet exercise concurrent calls — that's harder to set up reliably from one
    process; the SQL function's atomicity is guaranteed by Postgres at the row
    level (the UPDATE is a single statement). The sequential test verifies the
    increment math is correct.
    """
    job_id = state.create_job(client_id, ["emails"], None, "test-user")
    mark_test_job(state._sb, job_id)
    state.update_progress(job_id, delta_processed=5, current_stage="stage_a")
    state.update_progress(job_id, delta_processed=3, current_stage="stage_b")
    job = state.get_job(job_id)
    if job["processed_records"] == 8 and job["current_stage"] == "stage_b":
        t_pass("test_atomic_increment: 5 + 3 = 8 (not clobbered)")
    else:
        t_fail("test_atomic_increment", f"expected 8, got {job['processed_records']}")
    state.mark_stopped(job_id)


def test_append_error(state: ReembedJobState, client_id: str):
    """Test #4: append_error preserves previous entries."""
    job_id = state.create_job(client_id, ["emails"], None, "test-user")
    mark_test_job(state._sb, job_id)
    state.append_error(job_id, {"type": "A", "error": "first"})
    state.append_error(job_id, {"type": "B", "error": "second"})
    job = state.get_job(job_id)
    log = job.get("error_log") or []
    if len(log) == 2 and log[0]["type"] == "A" and log[1]["type"] == "B":
        t_pass("test_append_error preserves order and prior entries")
    else:
        t_fail("test_append_error", f"got log={log}")
    state.mark_stopped(job_id)


def test_request_cancel_check_cancelled(state: ReembedJobState, client_id: str):
    """Test #7: request_cancel + check_cancelled round-trip."""
    job_id = state.create_job(client_id, ["emails"], None, "test-user")
    mark_test_job(state._sb, job_id)
    state.mark_running(job_id)
    if state.check_cancelled(job_id):
        t_fail("test_request_cancel pre-state", "check_cancelled true before request")
        return
    state.request_cancel(job_id)
    if state.check_cancelled(job_id):
        t_pass("test_request_cancel + check_cancelled round-trip")
    else:
        t_fail("test_request_cancel", "check_cancelled false after request")


def test_get_active_job(state: ReembedJobState, client_id: str):
    """Test #8: get_active_job_for_client returns None / the right job."""
    # Create + finish — should NOT show as active
    job_id_done = state.create_job(client_id, ["emails"], None, "test-user")
    mark_test_job(state._sb, job_id_done)
    state.mark_stopped(job_id_done)

    active = state.get_active_job_for_client(client_id)
    if active is None:
        t_pass("test_get_active_job returns None when no active job")
    else:
        t_fail("test_get_active_job (no active)", f"got {active['id']}")

    # Create a new active job
    job_id_active = state.create_job(client_id, ["emails"], None, "test-user")
    mark_test_job(state._sb, job_id_active)
    state.mark_running(job_id_active)
    active = state.get_active_job_for_client(client_id)
    if active and active["id"] == job_id_active:
        t_pass("test_get_active_job returns the active job")
    else:
        t_fail("test_get_active_job (with active)", f"got {active}")
    state.mark_stopped(job_id_active)


async def test_single_flight_race(sb, client_id: str):
    """Test #9: TRUE concurrent INSERTs — exactly one wins, the other gets ActiveJobExists.

    This is the test the user emphasized — without real concurrency, a
    single-flight guarantee is almost worthless. We use asyncio.gather over
    asyncio.to_thread to dispatch the two synchronous INSERTs concurrently.
    """
    # Pre-clean to ensure no active jobs exist for this client at start
    sb.table("processing_jobs").update({
        "status": "stopped", "completed_at": "2026-04-13T00:00:00Z"
    }).eq("client_id", client_id).eq("job_type", JOB_TYPE).in_(
        "status", ["pending", "running"]
    ).execute()

    state = ReembedJobState(sb)

    def attempt():
        try:
            jid = state.create_job(client_id, ["emails"], None, "race-test")
            return ("ok", jid)
        except ActiveJobExists as e:
            return ("conflict", e.existing_job["id"])
        except Exception as e:
            return ("error", str(e))

    results = await asyncio.gather(
        asyncio.to_thread(attempt),
        asyncio.to_thread(attempt),
    )
    oks = [r for r in results if r[0] == "ok"]
    conflicts = [r for r in results if r[0] == "conflict"]
    errors = [r for r in results if r[0] == "error"]

    # Track for cleanup
    for kind, val in results:
        if kind == "ok":
            created_job_ids.append(val)
        elif kind == "conflict":
            created_job_ids.append(val)

    if errors:
        # KNOWN-LIMITATION FLAG: depending on Supavisor pooling and timing, both
        # requests may race so closely that one returns a non-23505 error. In
        # that case investigate before considering the test reliable.
        t_fail("test_single_flight_race", f"unexpected errors: {errors}")
    elif len(oks) == 1 and len(conflicts) == 1 and oks[0][1] == conflicts[0][1]:
        t_pass("test_single_flight_race: 1 wins, 1 conflict on same job_id")
    else:
        t_fail("test_single_flight_race", f"got oks={oks}, conflicts={conflicts}")

    # Cleanup the active row created by this test
    if oks:
        state.mark_stopped(oks[0][1])


def test_create_job_rejects_null_client(state: ReembedJobState):
    """Defense-in-depth: create_job must reject null client_id at app layer."""
    try:
        state.create_job(None, ["emails"], None, "test-user")  # type: ignore
        t_fail("test_create_job_rejects_null_client", "no exception raised")
    except ValueError:
        t_pass("test_create_job rejects null client_id")
    except Exception as e:
        t_fail("test_create_job_rejects_null_client", f"wrong exception: {e!r}")


def test_qb_batch_rpcs(sb, client_id: str):
    """Integration test for migration 072's batch RPCs against real Supabase.

    Verifies:
      1. batch_update_qb_capabilities correctly updates jsonb capability_tags,
         boolean flags, and row_type — catching any text[] ↔ jsonb cast bug.
      2. batch_update_qb_contact_emails correctly updates contact_email.
      3. Partial updates: rows not in p_updates are untouched.

    Tagged test rows by operation_name prefix '_TEST_QB_BATCH_' so cleanup is
    reliable even if the script is interrupted.
    """
    TEST_MARKER = '_TEST_QB_BATCH_RPC'
    test_row_ids: list[str] = []

    try:
        # Insert 3 test rows with known-starting-values
        rows = [
            {
                'client_id': client_id,
                'qb_record_id': f'99990{i}',
                'operation_name': f'{TEST_MARKER}_op_{i}',
                'department': 'TEST_DEPT',
                'capability_tags': [],
                'has_coating': False,
                'has_sewing': False,
                'has_outsource_component': False,
                'am_rush': False,
                'factory_rush': False,
                'row_type': None,
                'contact_email': None,
            }
            for i in range(3)
        ]
        ins = sb.table('qb_operations').insert(rows).execute()
        if not ins.data or len(ins.data) != 3:
            t_fail('test_qb_batch_rpcs: insert fixtures', f'expected 3 rows, got {len(ins.data or [])}')
            return
        test_row_ids = [r['id'] for r in ins.data]

        # Case 1: batch_update_qb_capabilities
        updates = [
            {
                'id': test_row_ids[0],
                'capability_tags': 'coating,welding',   # comma-separated → SQL splits
                'has_coating': 'true',
                'has_sewing': 'false',
                'has_outsource_component': 'false',
                'am_rush': 'true',
                'row_type': 'operation',
            },
            {
                'id': test_row_ids[1],
                'capability_tags': 'sewing',
                'has_coating': 'false',
                'has_sewing': 'true',
                'has_outsource_component': 'false',
                'am_rush': 'false',
                'row_type': 'operation',
            },
            # Deliberately leave test_row_ids[2] out of updates to verify
            # untouched rows stay untouched.
        ]
        try:
            resp = sb.rpc('batch_update_qb_capabilities', {'p_updates': updates}).execute()
            updated_count = int(resp.data) if resp.data is not None else None
        except Exception as e:
            t_fail('test_qb_batch_rpcs: capabilities RPC call', f'raised: {e}')
            return

        if updated_count != 2:
            t_fail('test_qb_batch_rpcs: capabilities count', f'expected 2 rows updated, got {updated_count}')
        else:
            t_pass('test_qb_batch_rpcs: capabilities RPC returns correct count')

        # Verify row 0: comma-separated split correctly into jsonb/array column
        r0 = sb.table('qb_operations').select('*').eq('id', test_row_ids[0]).single().execute().data
        # capability_tags is jsonb — stored as a JSON array of strings
        tags_ok = isinstance(r0['capability_tags'], list) and set(r0['capability_tags']) == {'coating', 'welding'}
        if tags_ok and r0['has_coating'] is True and r0['has_sewing'] is False and r0['am_rush'] is True and r0['row_type'] == 'operation':
            t_pass('test_qb_batch_rpcs: row 0 fields all set correctly (jsonb cast OK)')
        else:
            t_fail(
                'test_qb_batch_rpcs: row 0 values',
                f'tags={r0["capability_tags"]}, has_coating={r0["has_coating"]}, '
                f'has_sewing={r0["has_sewing"]}, am_rush={r0["am_rush"]}, row_type={r0["row_type"]}'
            )

        # Verify row 2: unchanged (was NOT in the update payload)
        r2 = sb.table('qb_operations').select('*').eq('id', test_row_ids[2]).single().execute().data
        if r2['capability_tags'] == [] and r2['has_coating'] is False and r2['row_type'] is None:
            t_pass('test_qb_batch_rpcs: partial update leaves other rows untouched')
        else:
            t_fail('test_qb_batch_rpcs: untouched row', f'row 2 was modified: {r2}')

        # Case 2: batch_update_qb_contact_emails
        email_updates = [
            {'id': test_row_ids[0], 'contact_email': 'a@example.com'},
            {'id': test_row_ids[1], 'contact_email': 'b@example.com'},
        ]
        try:
            resp = sb.rpc('batch_update_qb_contact_emails', {'p_updates': email_updates}).execute()
            updated_count = int(resp.data) if resp.data is not None else None
        except Exception as e:
            t_fail('test_qb_batch_rpcs: contact_emails RPC call', f'raised: {e}')
            return

        if updated_count != 2:
            t_fail('test_qb_batch_rpcs: contact_emails count', f'expected 2, got {updated_count}')
        else:
            t_pass('test_qb_batch_rpcs: contact_emails RPC returns correct count')

        r0 = sb.table('qb_operations').select('contact_email').eq('id', test_row_ids[0]).single().execute().data
        if r0['contact_email'] == 'a@example.com':
            t_pass('test_qb_batch_rpcs: contact_email persisted correctly')
        else:
            t_fail('test_qb_batch_rpcs: contact_email value', f'got {r0["contact_email"]}')

    finally:
        if test_row_ids:
            try:
                sb.table('qb_operations').delete().in_('id', test_row_ids).execute()
                print(f'  [cleanup] removed {len(test_row_ids)} QB test rows')
            except Exception as e:
                print(f'  [cleanup warn] could not delete QB test rows: {e}')


def test_bulk_index_manager_fallback_logic():
    """BulkIndexManager._exec_sql_extended: fall back to exec_sql ONLY when the
    RPC itself is missing (SQLSTATE 42883). On any other error — transient
    socket, statement_timeout, permissions — raise.

    This is the exact bug that caused the 2026-04-13 HNSW loss: the original
    implementation caught `Exception` broadly and silently fell back to the
    8s-timeout exec_sql path for a transient error, which then timed out
    during an HNSW rebuild and left the production index missing. Regression
    test so that failure mode cannot reappear.

    Pure-Python test using a minimal mock of the supabase client's rpc()
    chain — we are testing the error-branching logic, not Supabase behavior.
    """
    from src.database.bulk_index_manager import BulkIndexManager

    class _MockRpc:
        def __init__(self, exc):
            self._exc = exc
        def execute(self):
            raise self._exc

    class _MockSb:
        def __init__(self, exc_for_extended, exc_for_basic=None):
            self.exc_for_extended = exc_for_extended
            self.exc_for_basic = exc_for_basic
            self.basic_called = False
        def rpc(self, name, params):
            if name == "exec_sql_extended":
                return _MockRpc(self.exc_for_extended) if self.exc_for_extended else _NoOpRpc()
            elif name == "exec_sql":
                self.basic_called = True
                if self.exc_for_basic:
                    return _MockRpc(self.exc_for_basic)
                return _NoOpRpc()
            raise AssertionError(f"unexpected rpc call: {name}")

    class _NoOpRpc:
        def execute(self):
            return None

    # Case 1: exec_sql_extended RPC does NOT exist (42883) → fall back to exec_sql
    sb = _MockSb(exc_for_extended=Exception(
        "function exec_sql_extended(text, integer) does not exist (SQLSTATE 42883)"
    ))
    mgr = BulkIndexManager(sb)
    try:
        mgr._exec_sql_extended("CREATE INDEX foo ON bar(baz)", timeout_s=300)
        if sb.basic_called:
            t_pass("test_bulk_index_manager_fallback: 42883 triggers fallback to exec_sql")
        else:
            t_fail("test_bulk_index_manager_fallback_42883", "exec_sql was NOT called after 42883")
    except Exception as e:
        t_fail("test_bulk_index_manager_fallback_42883", f"raised instead of falling back: {e!r}")

    # Case 2: exec_sql_extended fails with statement_timeout → MUST raise, NOT fall back
    #         (this is what would have prevented today's HNSW loss)
    sb = _MockSb(exc_for_extended=Exception(
        "canceling statement due to statement timeout (SQLSTATE 57014)"
    ))
    mgr = BulkIndexManager(sb)
    try:
        mgr._exec_sql_extended("CREATE INDEX idx_emails_embedding ON emails USING hnsw ...", timeout_s=300)
        t_fail(
            "test_bulk_index_manager_fallback_timeout",
            "did not raise on statement_timeout (silent fallback is the bug)"
        )
    except Exception:
        if not sb.basic_called:
            t_pass("test_bulk_index_manager_fallback: statement_timeout raises (no silent fallback)")
        else:
            t_fail(
                "test_bulk_index_manager_fallback_timeout",
                "fell back to exec_sql on statement_timeout — this was the bug"
            )

    # Case 3: exec_sql_extended fails with WinError 10035 (transient) → MUST raise
    sb = _MockSb(exc_for_extended=Exception("[WinError 10035] socket would block"))
    mgr = BulkIndexManager(sb)
    try:
        mgr._exec_sql_extended("CREATE INDEX ...", timeout_s=300)
        t_fail(
            "test_bulk_index_manager_fallback_winerror",
            "did not raise on WinError 10035 (silent fallback is the bug)"
        )
    except Exception:
        if not sb.basic_called:
            t_pass("test_bulk_index_manager_fallback: WinError 10035 raises (no silent fallback)")
        else:
            t_fail(
                "test_bulk_index_manager_fallback_winerror",
                "fell back to exec_sql on WinError 10035"
            )


async def test_retry_async_recovers_from_transient_errors():
    """retry_async: transient errors (e.g. WinError 10035) are retried, permanent
    errors are raised immediately.

    This is a pure Python test of the retry mechanism itself — no DB, no mocks
    of Supabase. It verifies the exact behavior we rely on in embed_emails_batch.
    """
    from src.database.supabase_client import retry_async

    # Case 1: transient error on first two attempts, succeed on third
    attempts = {"count": 0}

    async def flaky_then_succeeds():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise OSError("[WinError 10035] A non-blocking socket operation could not be completed immediately")
        return "ok"

    try:
        result = await retry_async(flaky_then_succeeds, base_delay=0.01, label="test_flaky")
        if result == "ok" and attempts["count"] == 3:
            t_pass("test_retry_async: transient errors recovered (attempts=3)")
        else:
            t_fail("test_retry_async_transient", f"expected 'ok' after 3 attempts, got {result} after {attempts['count']}")
    except Exception as e:
        t_fail("test_retry_async_transient", f"unexpectedly raised: {e!r}")

    # Case 2: permanent error (not in retryable list) — raised immediately
    perm_attempts = {"count": 0}

    async def permanent_error():
        perm_attempts["count"] += 1
        raise ValueError("some permanent non-retryable error")

    try:
        await retry_async(permanent_error, base_delay=0.01, label="test_permanent")
        t_fail("test_retry_async_permanent", "did not raise on permanent error")
    except ValueError:
        if perm_attempts["count"] == 1:
            t_pass("test_retry_async: permanent errors raise immediately (no retry)")
        else:
            t_fail("test_retry_async_permanent", f"retried {perm_attempts['count']} times on permanent error — should be 1")

    # Case 3: transient error exhausts max_retries
    exhausted_attempts = {"count": 0}

    async def always_fails():
        exhausted_attempts["count"] += 1
        raise OSError("[WinError 10035] again")

    try:
        await retry_async(always_fails, max_retries=2, base_delay=0.01, label="test_exhaust")
        t_fail("test_retry_async_exhausted", "did not raise after exhausting retries")
    except OSError:
        # max_retries=2 means 1 initial + 2 retries = 3 attempts
        if exhausted_attempts["count"] == 3:
            t_pass("test_retry_async: raises after max_retries attempts (3 = 1 + 2 retries)")
        else:
            t_fail("test_retry_async_exhausted", f"expected 3 attempts, got {exhausted_attempts['count']}")


# ── HTTP integration test ────────────────────────────────────────────────────

def test_http_endpoint_smoke(client_id: str):
    """Test #11: lightweight smoke test of the HTTP endpoints.

    Skipped if backend not reachable. Does not exercise SSE — that needs an
    auth token and admin role; covered by manual curl in the runbook.
    """
    import urllib.request
    base = os.getenv("API_BASE_URL", "http://localhost:3000")
    try:
        urllib.request.urlopen(f"{base}/health", timeout=2).read()
    except Exception:
        print(f"{C.Y}SKIP{C.END}  test_http_endpoint_smoke: backend at {base} not reachable")
        return
    # Full HTTP test would require auth wiring; left as manual curl in runbook.
    print(f"{C.B}NOTE{C.END}  HTTP smoke: backend reachable; full POST/GET/STREAM "
          "test requires auth token — see manual curl in monkey-d-luffy.md")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    sb = get_supabase()
    state = ReembedJobState(sb)
    client_id = get_test_client_id(sb)
    print(f"{C.B}Running reembed job state tests against client_id={client_id}{C.END}\n")

    try:
        test_create_and_lifecycle(state, client_id)
        test_atomic_increment(state, client_id)
        test_append_error(state, client_id)
        test_request_cancel_check_cancelled(state, client_id)
        test_get_active_job(state, client_id)
        test_create_job_rejects_null_client(state)
        test_bulk_index_manager_fallback_logic()
        test_qb_batch_rpcs(sb, client_id)
        asyncio.run(test_retry_async_recovers_from_transient_errors())
        asyncio.run(test_single_flight_race(sb, client_id))
        test_http_endpoint_smoke(client_id)
    finally:
        cleanup(sb)

    print(f"\n{C.B}Results: {C.G}{passed} passed{C.END}, {C.R}{failed} failed{C.END}")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
