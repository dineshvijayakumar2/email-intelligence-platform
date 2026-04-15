"""
One-off backfill: apply the new thread-status override engine to existing threads.

After the Thread Intelligence refactor (migrations 077, 078, 079 + the new
ThreadStatusEngine), existing thread_status rows still hold their OLD
timing-only status because the evaluator hasn't re-run since the refactor.

Rather than doing a full recompute (44,076 threads; known to cause CPU
spikes on the current Supabase tier and trigger the high-CPU alert), this
script targets ONLY threads that contain at least one AI-classified email —
those are the only threads whose effective status could differ from their
current timing value under the new engine.

Count in production today: ~3,829 threads (vs 44,076 total).

Safeguards:
  - Per-client scoping (don't cross clients)
  - Batched (small N per iteration)
  - Throttled (sleep between batches to avoid CPU spikes)
  - Resumable (read-only pass first to identify; save per batch)
  - Limit via --limit for dry-runs

Usage:
    python scripts/db/backfill_thread_statuses.py                    # all clients
    python scripts/db/backfill_thread_statuses.py --client <uuid>    # single client
    python scripts/db/backfill_thread_statuses.py --dry-run          # identify only
    python scripts/db/backfill_thread_statuses.py --batch 50 --sleep 2.0  # more conservative

Prereqs: migrations 077, 078, 079 applied; thread_status_engine module present.
Safe to re-run; idempotent.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import List

_BACKEND = Path(__file__).resolve().parent.parent.parent / "backend"
sys.path.insert(0, str(_BACKEND / "src"))
sys.path.insert(0, str(_BACKEND))

try:
    from dotenv import load_dotenv
    for p in [_BACKEND / ".env.production", _BACKEND / ".env"]:
        if p.exists():
            load_dotenv(p, override=False)
            break
except ImportError:
    pass

import psycopg2
import psycopg2.extras

from src.services.thread_tracker import ThreadTracker  # type: ignore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("backfill")


def get_clients(conn) -> list[str]:
    """All client ids, or a single one if TEST_CLIENT_ID is set."""
    single = os.getenv("TEST_CLIENT_ID")
    if single:
        return [single]
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM clients ORDER BY id")
        return [r[0] for r in cur.fetchall()]


def get_affected_thread_ids(conn, client_id: str) -> List[str]:
    """Thread_ids for this client that contain at least one AI-classified email.

    Uses mailbox_ids as the join path (same pattern as ThreadTracker._fetch_threads
    in client-wide mode) to avoid the expensive client_id-on-emails filter which
    isn't indexed the way we need.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM mailboxes WHERE client_id = %s::uuid",
            (client_id,),
        )
        mb_ids = [r[0] for r in cur.fetchall()]
        if not mb_ids:
            return []

        # Paginate to avoid huge single query. Each mailbox has bounded threads.
        thread_ids: set[str] = set()
        for mb_id in mb_ids:
            cur.execute(
                """
                SELECT DISTINCT e.canonical_thread_id
                FROM emails e
                JOIN ai_email_intelligence ai ON ai.email_id = e.id
                WHERE e.mailbox_id = %s
                  AND e.canonical_thread_id IS NOT NULL
                  AND ai.intent IS NOT NULL
                """,
                (mb_id,),
            )
            for (tid,) in cur.fetchall():
                thread_ids.add(tid)
        return sorted(thread_ids)


def fetch_thread_emails(conn, thread_ids: List[str]) -> dict[str, list[dict]]:
    """Load all emails for the given thread_ids (ordered by date ascending).

    Same column set as _update_affected_threads in extraction_orchestrator.
    """
    if not thread_ids:
        return {}
    threads: dict[str, list[dict]] = {t: [] for t in thread_ids}
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        # Chunk the IN clause to stay within PostgREST/psycopg limits
        for i in range(0, len(thread_ids), 100):
            batch = thread_ids[i:i + 100]
            cur.execute(
                """
                SELECT id, canonical_thread_id, subject, sent_date, is_outbound,
                       customer_contact_id, customer_company_id
                FROM emails
                WHERE canonical_thread_id = ANY(%s::uuid[])
                ORDER BY sent_date ASC
                """,
                (batch,),
            )
            for row in cur.fetchall():
                tid = row["canonical_thread_id"]
                if tid in threads:
                    threads[tid].append(dict(row))
    return threads


def backfill_client(conn, client_id: str, batch: int, sleep_s: float, dry_run: bool, limit: int | None) -> dict:
    """Process one client. Returns a summary dict."""
    logger.info(f"[{client_id}] scanning for threads with AI classification...")
    all_thread_ids = get_affected_thread_ids(conn, client_id)
    total = len(all_thread_ids)
    logger.info(f"[{client_id}] {total} threads to re-evaluate")

    if limit:
        all_thread_ids = all_thread_ids[:limit]
        logger.info(f"[{client_id}] limited to {len(all_thread_ids)} threads (--limit)")

    if dry_run or not all_thread_ids:
        return {"client_id": client_id, "total": total, "processed": 0, "dry_run": dry_run}

    tracker = ThreadTracker(client_id=client_id)
    tracker._junction_cache = {}

    processed = 0
    saved = 0
    errors = 0

    for i in range(0, len(all_thread_ids), batch):
        batch_ids = all_thread_ids[i:i + batch]
        try:
            threads = fetch_thread_emails(conn, batch_ids)

            # Targeted intent preload for only these threads' emails
            all_email_ids = [e["id"] for emails in threads.values() for e in emails]
            tracker._preload_intent_for_emails(all_email_ids)

            statuses = []
            for tid, emails in threads.items():
                if len(emails) == 0 or len(emails) > 200:
                    continue
                try:
                    status = tracker._evaluate_thread_status(tid, emails)
                    statuses.append(status)
                except Exception as e:
                    logger.warning(f"[{client_id}] eval failed for {tid}: {e}")
                    errors += 1

            if statuses:
                result = tracker.save_thread_statuses(statuses)
                saved += result.get("created_count", 0)

            processed += len(batch_ids)
            pct = round(100 * processed / len(all_thread_ids), 1)
            logger.info(f"[{client_id}] {processed}/{len(all_thread_ids)} ({pct}%) — saved {saved}, errors {errors}")

        except Exception as e:
            logger.error(f"[{client_id}] batch {i}-{i+batch} failed: {e}")
            errors += len(batch_ids)

        # Throttle: pause between batches to keep CPU pressure low.
        if i + batch < len(all_thread_ids):
            time.sleep(sleep_s)

    return {
        "client_id": client_id,
        "total": total,
        "processed": processed,
        "saved": saved,
        "errors": errors,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--client", help="Process a single client (UUID); default: all clients")
    ap.add_argument("--dry-run", action="store_true", help="Count target threads per client; no writes")
    ap.add_argument("--batch", type=int, default=50, help="Threads per batch (default 50)")
    ap.add_argument("--sleep", type=float, default=1.5, help="Seconds to sleep between batches (default 1.5)")
    ap.add_argument("--limit", type=int, default=None, help="Max threads per client (for test runs)")
    args = ap.parse_args()

    url = os.getenv("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL not set in env")
        sys.exit(2)

    conn = psycopg2.connect(url, application_name="backfill_thread_statuses")
    conn.autocommit = True

    client_ids = [args.client] if args.client else get_clients(conn)
    logger.info(f"Clients to process: {len(client_ids)}")

    t0 = time.time()
    summary = []
    for cid in client_ids:
        try:
            summary.append(backfill_client(conn, cid, args.batch, args.sleep, args.dry_run, args.limit))
        except Exception as e:
            logger.exception(f"[{cid}] fatal error: {e}")
            summary.append({"client_id": cid, "error": str(e)})

    elapsed = time.time() - t0
    logger.info(f"\n=== Done in {elapsed:.1f}s ===")
    for s in summary:
        logger.info(f"  {s}")

    conn.close()


if __name__ == "__main__":
    main()
