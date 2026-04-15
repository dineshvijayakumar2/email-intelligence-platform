"""
One-off backfill: propagate QB signals to customer_contacts for every client.

Migration 081 added `batch_propagate_qb_data_to_contacts(p_client_id)` which
does two UPDATE passes:
  Pass 1: qb_unique_emails → customer_contacts (case-insensitive email join)
  Pass 2: qb_contacts      → customer_contacts (FK via matched_contact_id)

Going forward, QB sync wires this RPC into every sync/rematch path. But the
existing ~20K rows in customer_contacts have never been populated. This script
runs the RPC once per client so downstream AI enrichment (thread intelligence,
action buckets, digests) reads real values instead of NULL.

Usage:
    python scripts/db/backfill_qb_contacts.py                 # all clients
    python scripts/db/backfill_qb_contacts.py --client <uuid> # one client
    python scripts/db/backfill_qb_contacts.py --dry-run       # report matchable
                                                              # counts, no write

Prereqs:
  - Migration 081 applied
  - SUPABASE_URL + SUPABASE_SERVICE_KEY set (read from backend/.env*)

Idempotent and safe to re-run — the RPC uses COALESCE so it won't overwrite
values that already exist. Uses the Supabase client (not psycopg2) because
the whole operation is a single RPC call per client.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

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

from src.database.supabase_client import SupabaseClient  # type: ignore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("backfill_qb_contacts")


def list_clients(sb, explicit: str | None) -> list[str]:
    if explicit:
        return [explicit]
    rows = sb.table("clients").select("id").order("id").execute().data or []
    return [r["id"] for r in rows]


def report_matchable_counts(sb, client_id: str) -> dict:
    """Dry-run: conservative upper bounds on what the RPC could affect.

    Pass 1 bound: count of valid QB unique-email rows (each is a potential
    match target, though not every one has a corresponding customer_contact).
    Pass 2 bound: count of qb_contacts with a matched_contact_id FK set.
    """
    pass1 = sb.table("qb_unique_emails").select(
        "id", count="exact"
    ).eq("client_id", client_id).eq("hide", False).eq(
        "email_invalid", False
    ).neq("email", "").not_.is_("email", "null").limit(0).execute().count or 0

    pass2 = sb.table("qb_contacts").select(
        "id", count="exact"
    ).eq("client_id", client_id).not_.is_(
        "matched_contact_id", "null"
    ).limit(0).execute().count or 0

    return {"pass1": pass1, "pass2": pass2}


def run_for_client(sb, client_id: str, dry_run: bool) -> int:
    if dry_run:
        try:
            counts = report_matchable_counts(sb, client_id)
            logger.info(
                f"[dry-run] client {client_id}: "
                f"pass1 upper-bound (valid qb_unique_emails) = {counts['pass1']}, "
                f"pass2 upper-bound (matched qb_contacts) = {counts['pass2']}"
            )
        except Exception as e:
            logger.warning(f"[dry-run] client {client_id}: count failed ({e})")
        return 0

    try:
        result = sb.rpc(
            "batch_propagate_qb_data_to_contacts",
            {"p_client_id": client_id},
        ).execute()
        updated = result.data if isinstance(result.data, int) else 0
        logger.info(f"client {client_id}: propagated {updated} contact rows")
        return updated
    except Exception as e:
        logger.error(f"client {client_id}: RPC failed: {e}")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", help="Single client UUID (default: all)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report matchable counts without writing",
    )
    args = parser.parse_args()

    sb = SupabaseClient.get_client(use_service_key=True)
    clients = list_clients(sb, args.client)
    logger.info(f"Processing {len(clients)} client(s)")

    total = 0
    for cid in clients:
        total += run_for_client(sb, cid, args.dry_run)

    mode = "would propagate" if args.dry_run else "propagated"
    logger.info(f"Done. {mode} {total} contact rows across {len(clients)} client(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
