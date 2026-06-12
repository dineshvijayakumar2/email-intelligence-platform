"""Backfill email_response_metrics by re-running ResponseTimeTracker per Carbon8 mailbox.

Diagnosed 2026-06-12: several Carbon8 mailboxes have under-computed
email_response_metrics (Nic worst: ~1,001 rows vs ~8.4K expected pairs). The
tracker is idempotent (save_metrics upserts on email_id), so a straight re-run
backfills missing pairs without duplicating existing ones.

Runs the tracker for each mailbox (critical/partial first, largest last), then
calls update_contact_averages once at the end (it recomputes client-wide, so a
single pass after all saves is sufficient).

Usage:
    python -u scripts/db/_backfill_response_metrics.py
"""
import os
import sys
import logging

# Make backend importable
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'backend'))

from dotenv import load_dotenv

env_path = os.path.join(ROOT, 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(ROOT, 'backend', '.env')
load_dotenv(env_path)

from src.services.response_time_tracker import ResponseTimeTracker  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
)
log = logging.getLogger("backfill")

CLIENT_ID = "241d7b99-f099-4557-96e5-212c4af10812"

# (name, mailbox_id) — ordered: critical/partial first, largest last.
MAILBOXES = [
    ("Nic Outlook Mac",            "5f3afeb3-a5f7-44b8-b657-ec972c92911d"),
    ("Linda carbon8 outlook Mac",  "e1abc287-805b-4cee-8f95-0b47e1cd8f99"),
    ("Production PC Outlook",      "3e09b3d0-5fb2-4499-819f-cc5f0c35b94e"),
    ("Jeff Love | Carbon8",        "71ebdbc8-c3ca-4802-942e-948975c736ea"),
    ("Kenneth Carbon8 outlook",    "1332eba5-9121-4b55-91db-a37dd81d5d85"),
    ("Ehab Carbon8 Outlook 2",     "92eba92f-b6be-4fbf-8c49-9f3b7c72ea74"),
    ("Hello Carbon8 OutlookMac",   "c1157f56-79a0-4f0b-9dcf-2db257f0d5c4"),
]


def main():
    summary = []
    for name, mb_id in MAILBOXES:
        log.info("=" * 70)
        log.info(f"MAILBOX: {name}  ({mb_id})")
        log.info("=" * 70)
        tracker = ResponseTimeTracker(mailbox_id=mb_id, client_id=CLIENT_ID)
        metrics = tracker.calculate_response_times()
        save = tracker.save_metrics(metrics)
        log.info(f"[{name}] pairs={len(metrics)} saved={save.get('created_count')} "
                 f"errors={len(save.get('errors', []))}")
        summary.append((name, len(metrics), save.get('created_count'), len(save.get('errors', []))))

    log.info("=" * 70)
    log.info("Updating contact averages (client-wide, single pass)")
    log.info("=" * 70)
    last_tracker = ResponseTimeTracker(mailbox_id=MAILBOXES[0][1], client_id=CLIENT_ID)
    upd = last_tracker.update_contact_averages()
    log.info(f"Contact averages updated: {upd}")

    log.info("\n===== BACKFILL SUMMARY =====")
    for name, pairs, saved, errs in summary:
        log.info(f"  {name:32s} pairs={pairs:6d} saved={saved:6d} errors={errs}")


if __name__ == '__main__':
    main()
