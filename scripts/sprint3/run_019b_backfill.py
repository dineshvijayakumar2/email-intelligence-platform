"""
Run migration 019b backfill via Supabase REST API — no DB password needed.

Usage:
    cd backend
    python ../scripts/sprint3/run_019b_backfill.py

Uses SUPABASE_URL + SUPABASE_SERVICE_KEY from .env.development.
Runs all backfills in small batches with progress logging.
"""

import os
import sys
import time

# Load env — use --prod flag for production
env_name = ".env.production" if "--prod" in sys.argv else ".env.development"
env_path = os.path.join(os.path.dirname(__file__), "..", "..", "backend", env_name)
if os.path.exists(env_path):
    print(f"Loading: {env_name}")
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip().strip("'\""))
else:
    print(f"WARNING: {env_path} not found")

from supabase import create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env.development")
    sys.exit(1)

sb = create_client(SUPABASE_URL, SUPABASE_KEY)

BATCH_SIZE = 500  # Supabase .in_() limit
PAUSE = 0.3


def get_stats():
    """Get current backfill stats using individual queries."""
    # Total
    r = sb.table("emails").select("id", count="exact").limit(0).execute()
    total = r.count or 0

    # Has real message ID (not null, not __none__)
    r = sb.table("emails").select("id", count="exact").not_.is_("internet_message_id", "null").neq("internet_message_id", "__none__").limit(0).execute()
    has_real = r.count or 0

    # Marked __none__
    r = sb.table("emails").select("id", count="exact").eq("internet_message_id", "__none__").limit(0).execute()
    marked_none = r.count or 0

    # Pending (NULL internet_message_id)
    pending = total - has_real - marked_none

    # Has subject_normalized
    r = sb.table("emails").select("id", count="exact").not_.is_("subject_normalized", "null").limit(0).execute()
    has_subj = r.count or 0

    return {
        "total": total,
        "has_real_msg_id": has_real,
        "marked_none": marked_none,
        "pending_msg_id": pending,
        "has_subject_norm": has_subj,
        "pending_subject_norm": total - has_subj,
    }


def backfill_extract_headers():
    """Backfill 1: Extract Message-ID/In-Reply-To/References from raw_headers."""
    print("=" * 60)
    print("BACKFILL 1: Extract headers from raw_headers JSONB")
    print("=" * 60)

    total = 0
    batch_num = 0

    while True:
        batch_num += 1

        # Find emails with raw_headers but no internet_message_id
        result = sb.table("emails").select(
            "id, raw_headers"
        ).is_("internet_message_id", "null").not_.is_(
            "raw_headers", "null"
        ).limit(BATCH_SIZE).execute()

        rows = result.data or []
        # Filter out empty raw_headers in Python
        rows = [r for r in rows if r.get("raw_headers") and r["raw_headers"] != {}]

        if not rows:
            print(f"  Batch {batch_num}: 0 rows — done!")
            break

        updated = 0
        for row in rows:
            headers = row["raw_headers"]
            msg_id = (
                headers.get("Message-ID") or
                headers.get("Message-Id") or
                headers.get("message-id") or
                ""
            )
            in_reply = (
                headers.get("In-Reply-To") or
                headers.get("in-reply-to") or
                None
            )
            refs = (
                headers.get("References") or
                headers.get("references") or
                None
            )

            update_data = {
                "internet_message_id": msg_id if msg_id else "__none__",
            }
            if in_reply:
                update_data["in_reply_to"] = in_reply
            if refs:
                update_data["references_header"] = refs

            sb.table("emails").update(update_data).eq("id", row["id"]).execute()
            updated += 1

        total += updated
        print(f"  Batch {batch_num}: {updated} rows (total: {total:,})")
        time.sleep(PAUSE)

    return total


def backfill_extract_headers_fast():
    """Backfill 1 (fast): Batch update using .in_() for IDs."""
    print("=" * 60)
    print("BACKFILL 1: Extract headers from raw_headers JSONB")
    print("=" * 60)

    total = 0
    batch_num = 0

    while True:
        batch_num += 1

        # Fetch batch of rows with raw_headers but no internet_message_id
        result = sb.table("emails").select(
            "id, raw_headers"
        ).is_("internet_message_id", "null").not_.is_(
            "raw_headers", "null"
        ).limit(BATCH_SIZE).execute()

        rows = [r for r in (result.data or []) if r.get("raw_headers") and r["raw_headers"] != {}]

        if not rows:
            # Also check if there are rows with empty/null raw_headers to mark
            print(f"  Batch {batch_num}: 0 extractable rows — done!")
            break

        # Process each row, group by outcome for batch updates
        has_msgid_ids = {}  # id -> {internet_message_id, in_reply_to, references_header}
        no_msgid_ids = []

        for row in rows:
            headers = row["raw_headers"]
            msg_id = (
                headers.get("Message-ID") or
                headers.get("Message-Id") or
                headers.get("message-id") or
                ""
            ).strip()

            if msg_id:
                in_reply = (headers.get("In-Reply-To") or headers.get("in-reply-to") or "").strip() or None
                refs = (headers.get("References") or headers.get("references") or "").strip() or None
                has_msgid_ids[row["id"]] = {
                    "internet_message_id": msg_id,
                    "in_reply_to": in_reply,
                    "references_header": refs,
                }
            else:
                no_msgid_ids.append(row["id"])

        # Update rows with real Message-IDs (one by one since each has different values)
        for eid, data in has_msgid_ids.items():
            update = {"internet_message_id": data["internet_message_id"]}
            if data["in_reply_to"]:
                update["in_reply_to"] = data["in_reply_to"]
            if data["references_header"]:
                update["references_header"] = data["references_header"]
            try:
                sb.table("emails").update(update).eq("id", eid).execute()
            except Exception as e:
                print(f"    WARN: Failed to update {eid}: {e}")

        # Batch mark rows with no Message-ID
        if no_msgid_ids:
            try:
                sb.table("emails").update(
                    {"internet_message_id": "__none__"}
                ).in_("id", no_msgid_ids).execute()
            except Exception:
                # Fallback: update one by one
                for eid in no_msgid_ids:
                    sb.table("emails").update(
                        {"internet_message_id": "__none__"}
                    ).eq("id", eid).execute()

        updated = len(rows)
        total += updated
        print(f"  Batch {batch_num}: {updated} rows ({len(has_msgid_ids)} extracted, {len(no_msgid_ids)} marked none) — total: {total:,}")
        time.sleep(PAUSE)

    return total


def backfill_mark_none():
    """Backfill 2: Mark remaining NULL internet_message_id as __none__."""
    print("=" * 60)
    print("BACKFILL 2: Mark remaining emails as __none__")
    print("=" * 60)

    total = 0
    batch_num = 0

    while True:
        batch_num += 1

        result = sb.table("emails").select("id").is_(
            "internet_message_id", "null"
        ).limit(BATCH_SIZE).execute()

        ids = [r["id"] for r in (result.data or [])]
        if not ids:
            print(f"  Batch {batch_num}: 0 rows — done!")
            break

        try:
            sb.table("emails").update(
                {"internet_message_id": "__none__"}
            ).in_("id", ids).execute()
        except Exception:
            # Fallback: smaller batches
            for i in range(0, len(ids), 100):
                chunk = ids[i:i+100]
                sb.table("emails").update(
                    {"internet_message_id": "__none__"}
                ).in_("id", chunk).execute()

        total += len(ids)
        print(f"  Batch {batch_num}: {len(ids)} rows (total: {total:,})")
        time.sleep(PAUSE)

    return total


def backfill_subjects():
    """Backfill 3: Normalize subjects."""
    print("=" * 60)
    print("BACKFILL 3: Normalize subjects")
    print("=" * 60)

    import re
    RE_PREFIX = re.compile(r'^(\s*(RE|FW|FWD|AW|WG|SV|VS|TR)\s*:\s*)+', re.IGNORECASE)

    total = 0
    batch_num = 0

    while True:
        batch_num += 1

        result = sb.table("emails").select("id, subject").is_(
            "subject_normalized", "null"
        ).not_.is_("subject", "null").limit(BATCH_SIZE).execute()

        rows = result.data or []
        if not rows:
            print(f"  Batch {batch_num}: 0 rows — done!")
            break

        for row in rows:
            subject = row.get("subject") or ""
            normalized = RE_PREFIX.sub("", subject).strip().lower()
            try:
                sb.table("emails").update(
                    {"subject_normalized": normalized}
                ).eq("id", row["id"]).execute()
            except Exception as e:
                print(f"    WARN: Failed {row['id']}: {e}")

        total += len(rows)
        print(f"  Batch {batch_num}: {len(rows)} rows (total: {total:,})")
        time.sleep(PAUSE)

    return total


def main():
    print("Connecting to Supabase...\n")

    stats = get_stats()
    print(f"Current state:")
    print(f"  Total emails:          {stats['total']:,}")
    print(f"  Has real Message-ID:   {stats['has_real_msg_id']:,}")
    print(f"  Marked __none__:       {stats['marked_none']:,}")
    print(f"  Pending Message-ID:    {stats['pending_msg_id']:,}")
    print(f"  Has subject_norm:      {stats['has_subject_norm']:,}")
    print(f"  Pending subject_norm:  {stats['pending_subject_norm']:,}")
    print()

    if stats["pending_msg_id"] > 0:
        backfill_extract_headers_fast()
        print()

    # Re-check
    r = sb.table("emails").select("id", count="exact").is_("internet_message_id", "null").limit(0).execute()
    remaining = r.count or 0

    if remaining > 0:
        backfill_mark_none()
        print()

    if stats["pending_subject_norm"] > 0:
        backfill_subjects()
        print()

    # Final stats
    print()
    final = get_stats()
    print("=" * 60)
    print("FINAL STATE:")
    print(f"  Real Message-ID:       {final['has_real_msg_id']:,}")
    print(f"  No Message-ID (__none__): {final['marked_none']:,}")
    print(f"  Still pending:         {final['pending_msg_id']:,}")
    print(f"  Has subject_norm:      {final['has_subject_norm']:,}")
    print(f"  Pending subject_norm:  {final['pending_subject_norm']:,}")
    print("=" * 60)

    if final["pending_msg_id"] == 0 and final["pending_subject_norm"] == 0:
        print("\nAll backfills complete!")
    else:
        print("\nSome rows still pending. Run again.")


if __name__ == "__main__":
    main()
