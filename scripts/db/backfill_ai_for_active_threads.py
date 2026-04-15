"""
Targeted AI classification backfill for thread intelligence coverage.

Scope (Option D from our earlier analysis):
  Classify only the LAST email of each currently-active thread where that
  email hasn't been AI-classified yet. These are the emails whose intent
  actually drives thread_status override rules — without them, the rules
  can't fire even though the refactored engine is now correct.

Today this is ~98 emails → ~$0.10 cost → ~5 minutes runtime. Dramatically
cheaper than the full 252K-email backfill, and captures the signal that
matters for thread intelligence at launch.

Safeguards:
  - External AI calls only (hits Anthropic's Claude Haiku API, not Supabase CPU)
  - Throttled (small batches, pauses between them)
  - Dry-run support (count targets without classifying)
  - Per-mailbox scoping (analyze_batch requires a mailbox_id)
  - Uses existing ai_email_analyzer — honors circuit breakers, rate limits,
    cost logging to ai_usage_log, and the `ai_enabled` master kill switch

Usage:
    python scripts/db/backfill_ai_for_active_threads.py --dry-run
    python scripts/db/backfill_ai_for_active_threads.py
    python scripts/db/backfill_ai_for_active_threads.py --limit 20  # test with a small set

Prereqs:
  - DATABASE_URL set (direct Postgres — targeting queries that JOIN multiple tables)
  - SUPABASE_URL + SUPABASE_SERVICE_KEY set (for the analyzer itself)
  - AI enabled via the admin toggle
  - Valid Anthropic or Gemini API key configured per client
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import List, Dict

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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("ai_backfill")

ACTIVE_STATUSES = ("awaiting_response", "awaiting_our_response", "ongoing", "outbound_pending", "stale", "overdue")


def get_target_emails(conn, limit: int | None) -> list[dict]:
    """Find the last email of each currently-active thread where that email
    is unclassified. Uses thread_status.last_email_id directly (already
    populated by thread_tracker) instead of DISTINCT ON across all emails —
    that latter form times out on 266K emails without a proper index."""
    sql = """
        SELECT
            e.id, e.mailbox_id, e.subject, e.body_text, e.sender_email,
            e.sender_name, e.sent_date, e.direction, e.folder_path, e.thread_id,
            e.is_reply, e.client_id, e.customer_contact_id, e.customer_company_id,
            e.cc_list, e.bcc_list
        FROM thread_status ts
        JOIN emails e ON e.id = ts.last_email_id
        LEFT JOIN ai_email_intelligence ai ON ai.email_id = e.id
        WHERE ts.status = ANY(%s::text[])
          AND ts.last_email_id IS NOT NULL
          AND ai.id IS NULL
        ORDER BY e.mailbox_id, e.sent_date DESC
    """
    params = [list(ACTIVE_STATUSES)]
    if limit:
        sql += " LIMIT %s"
        params.append(limit)

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def group_by_mailbox(emails: list[dict]) -> Dict[str, List[dict]]:
    grouped: Dict[str, List[dict]] = {}
    for e in emails:
        mb = str(e["mailbox_id"]) if e.get("mailbox_id") else None
        if not mb:
            continue
        grouped.setdefault(mb, []).append(e)
    return grouped


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="Count + list targets; no AI calls")
    ap.add_argument("--limit", type=int, default=None, help="Process at most N emails")
    ap.add_argument("--batch", type=int, default=10, help="Emails per AI batch call (default 10)")
    ap.add_argument("--sleep", type=float, default=1.0, help="Seconds between batches (default 1.0)")
    args = ap.parse_args()

    url = os.getenv("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL not set"); sys.exit(2)

    conn = psycopg2.connect(url, application_name="ai_backfill_active_threads")

    logger.info("Identifying target emails...")
    targets = get_target_emails(conn, args.limit)
    logger.info(f"Found {len(targets)} unclassified last-emails of currently-active threads")

    # Convert UUIDs + datetimes to serializable for the analyzer
    def _stringify(e: dict) -> dict:
        r = dict(e)
        for k, v in r.items():
            if hasattr(v, "hex"):  # UUID
                r[k] = str(v)
            elif hasattr(v, "isoformat"):  # datetime/date
                r[k] = v.isoformat()
        return r
    targets = [_stringify(e) for e in targets]

    grouped = group_by_mailbox(targets)
    logger.info(f"Distributed across {len(grouped)} mailbox(es)")
    for mb, rows in grouped.items():
        logger.info(f"  {mb}: {len(rows)} emails")

    if args.dry_run:
        logger.info("Dry-run — exiting without AI calls.")
        conn.close()
        return

    if not targets:
        logger.info("Nothing to do.")
        conn.close()
        return

    # Import + initialize the analyzer. In normal operation FastAPI startup
    # calls init_email_analyzer(supabase_client) — this script is standalone
    # so we do the init manually with a fresh Supabase service-role client.
    logger.info("Loading ai_email_analyzer...")
    from src.database.supabase_client import SupabaseClient  # type: ignore
    from src.services.ai_email_analyzer import init_email_analyzer, get_email_analyzer  # type: ignore
    from src.services.ai_usage_tracker import init_usage_tracker  # type: ignore

    sb = SupabaseClient.get_client(use_service_key=True)
    from src.services.ai_client import load_ai_settings_from_db, get_ai_settings  # type: ignore
    from src.services.langchain_core import resolve_task_model_name  # type: ignore
    init_usage_tracker(sb)   # analyzer logs usage via this tracker
    init_email_analyzer(sb)
    analyzer = get_email_analyzer()
    if not analyzer:
        logger.error("Analyzer still not initialized after manual init — check env vars")
        sys.exit(1)

    t0 = time.time()
    total_analyzed = 0
    total_failed = 0

    for mailbox_id, mailbox_emails in grouped.items():
        client_id = str(mailbox_emails[0].get("client_id")) if mailbox_emails[0].get("client_id") else None
        logger.info(f"\n=== Mailbox {mailbox_id} ({len(mailbox_emails)} emails, client {client_id}) ===")

        # Load THIS client's daily_budget_usd / ai_enabled. Without this, the
        # process would use the $2.00 default from ai_client.py.
        # Per-task model routing reads DB directly inside analyze_batch.
        if client_id:
            load_ai_settings_from_db(client_id=client_id)
            cs = get_ai_settings()
            task_model = resolve_task_model_name("email_analysis", client_id)
            logger.info(
                f"  client settings: daily_budget=${cs.daily_budget_usd:.2f}, "
                f"email_analysis_model={task_model}"
            )

        for i in range(0, len(mailbox_emails), args.batch):
            batch = mailbox_emails[i:i + args.batch]
            try:
                result = analyzer.analyze_batch(
                    mailbox_id=mailbox_id,
                    client_id=client_id,
                    emails=batch,
                )
                analyzed = result.get("analyzed", 0)
                failed = result.get("failed", 0)
                total_analyzed += analyzed
                total_failed += failed
                logger.info(f"  batch {i}-{i+len(batch)}: +{analyzed} analyzed, +{failed} failed")
            except Exception as e:
                logger.error(f"  batch {i}-{i+len(batch)} raised: {e}")
                total_failed += len(batch)

            # Throttle between batches (external API rate-limit friendliness)
            if i + args.batch < len(mailbox_emails):
                time.sleep(args.sleep)

    elapsed = time.time() - t0
    logger.info(f"\n=== Complete ===")
    logger.info(f"Total: {total_analyzed} analyzed, {total_failed} failed in {elapsed:.1f}s")
    logger.info("Check ai_usage_log table for per-call cost tracking.")

    conn.close()


if __name__ == "__main__":
    main()
