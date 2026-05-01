"""
Full QB reference linking for all classified emails in a mailbox.

Reads ALL ai_email_intelligence rows with extracted_references (no date cutoff),
validates refs against qb_quotes/qb_jobs in bulk, and upserts thread_qb_links.

Usage:
    python scripts/db/_link_ai_refs_full.py                    # all mailboxes
    python scripts/db/_link_ai_refs_full.py <mailbox_id>       # specific mailbox
    python scripts/db/_link_ai_refs_full.py --lookback 30      # last 30 days only
"""
import os, sys, re, time, argparse
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
from dotenv import load_dotenv
from supabase import create_client

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
load_dotenv(env_path)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

PAGE = 500


def link_refs_for_mailbox(mailbox_id: str, client_id: str, mailbox_name: str, lookback_days: int | None = None):
    print(f"\n{'='*60}")
    print(f"Mailbox: {mailbox_name} ({mailbox_id[:8]}...)")
    print(f"{'='*60}")

    # --- Fetch ai_email_intelligence rows with extracted_references ---
    all_rows = []
    offset = 0
    while True:
        query = sb.table("ai_email_intelligence").select(
            "email_id, extracted_references"
        ).eq("mailbox_id", mailbox_id).eq(
            "processing_status", "completed"
        ).not_.is_("extracted_references", "null")

        if lookback_days is not None:
            cutoff = (datetime.utcnow() - timedelta(days=lookback_days)).isoformat()
            query = query.gte("processed_at", cutoff)

        resp = query.range(offset, offset + PAGE - 1).execute()
        batch = resp.data or []
        all_rows.extend(batch)
        if len(batch) < PAGE:
            break
        offset += PAGE

    if not all_rows:
        print("  No classified emails with extracted references found.")
        return 0

    print(f"  Found {len(all_rows)} classified emails with extracted references")

    # --- Build thread map ---
    email_ids = [r["email_id"] for r in all_rows]
    thread_map: dict[str, str] = {}
    for i in range(0, len(email_ids), PAGE):
        chunk = email_ids[i:i + PAGE]
        thread_resp = sb.table("emails").select(
            "id, canonical_thread_id"
        ).in_("id", chunk).execute()
        for r in (thread_resp.data or []):
            tid = r.get("canonical_thread_id")
            if tid:
                thread_map[r["id"]] = tid

    print(f"  Mapped {len(thread_map)} emails to threads")

    # --- Parse refs from all rows ---
    all_quote_refs: set[str] = set()
    all_job_refs: set[str] = set()
    row_refs: list[tuple[str, dict[str, set[str]]]] = []

    for row in all_rows:
        refs_raw = row.get("extracted_references") or []
        if not refs_raw:
            continue
        thread_id = thread_map.get(row["email_id"])
        if not thread_id:
            continue

        refs: dict[str, set[str]] = {}
        for ref in refs_raw:
            ref_type = ref.get("type")
            ref_number = ref.get("number")
            if ref_type and ref_number:
                digits = re.sub(r'[^0-9]', '', str(ref_number))
                if not digits:
                    continue
                prefix = "Q" if ref_type == "quote" else "J"
                canonical = f"{prefix}{digits}"
                refs.setdefault(ref_type, set()).add(canonical)
                if ref_type == "quote":
                    all_quote_refs.add(canonical)
                else:
                    all_job_refs.add(canonical)

        if refs:
            row_refs.append((thread_id, refs))

    if not row_refs:
        print("  No valid refs to link.")
        return 0

    print(f"  Unique refs: {len(all_quote_refs)} quotes, {len(all_job_refs)} jobs across {len(row_refs)} thread-ref pairs")

    # --- Bulk-validate against QB tables ---
    valid_quotes: dict[str, str] = {}
    valid_jobs: dict[str, str] = {}

    quote_list = list(all_quote_refs)
    for i in range(0, len(quote_list), PAGE):
        chunk = quote_list[i:i + PAGE]
        resp = sb.table("qb_quotes").select("quote_no, qb_record_id").eq(
            "client_id", client_id
        ).in_("quote_no", chunk).execute()
        for r in (resp.data or []):
            valid_quotes[r["quote_no"]] = str(r["qb_record_id"])

    job_list = list(all_job_refs)
    for i in range(0, len(job_list), PAGE):
        chunk = job_list[i:i + PAGE]
        resp = sb.table("qb_jobs").select("job_no, qb_record_id").eq(
            "client_id", client_id
        ).in_("job_no", chunk).execute()
        for r in (resp.data or []):
            valid_jobs[r["job_no"]] = str(r["qb_record_id"])

    print(f"  Validated: {len(valid_quotes)} quotes, {len(valid_jobs)} jobs match QB records")

    if not valid_quotes and not valid_jobs:
        print("  No QB matches found — nothing to link.")
        return 0

    # --- Upsert links ---
    total_linked = 0
    threads_linked = 0
    errors = 0

    for thread_id, refs in row_refs:
        validated: dict[str, dict[str, str]] = {}
        for ref_str in refs.get("quote", set()):
            if ref_str in valid_quotes:
                validated.setdefault("quote", {})[ref_str] = valid_quotes[ref_str]
        for ref_str in refs.get("job", set()):
            if ref_str in valid_jobs:
                validated.setdefault("job", {})[ref_str] = valid_jobs[ref_str]

        if not validated:
            continue

        rows = []
        for link_type, ref_map in validated.items():
            for ref_str, record_id in ref_map.items():
                rows.append({
                    "client_id": client_id,
                    "canonical_thread_id": thread_id,
                    "link_type": link_type,
                    "qb_record_id": record_id,
                    "qb_reference": ref_str,
                    "confidence": 0.9,
                    "source": "ai",
                    "verified": False,
                })

        try:
            sb.table("thread_qb_links").upsert(
                rows,
                on_conflict="client_id,canonical_thread_id,link_type,qb_record_id",
            ).execute()
            total_linked += len(rows)
            threads_linked += 1
        except Exception as e:
            errors += 1
            if errors <= 3:
                print(f"  Error upserting for thread {thread_id[:16]}: {e}")

    # --- Batch sync qb_link_count ---
    if threads_linked > 0:
        unique_threads = list({tid for tid, _ in row_refs})
        synced = 0
        for tid in unique_threads:
            try:
                cnt_r = sb.table("thread_qb_links").select(
                    "id", count="exact"
                ).eq("client_id", client_id).eq(
                    "canonical_thread_id", tid
                ).execute()
                count = cnt_r.count if cnt_r.count is not None else len(cnt_r.data or [])
                sb.table("thread_status").update(
                    {"qb_link_count": count}
                ).eq("canonical_thread_id", tid).execute()
                synced += 1
            except Exception:
                pass

        print(f"  Synced qb_link_count on {synced} threads")

    print(f"  Result: {total_linked} links upserted across {threads_linked} threads ({errors} errors)")
    return total_linked


def main():
    parser = argparse.ArgumentParser(description="Full QB reference linking")
    parser.add_argument("mailbox_id", nargs="?", help="Specific mailbox ID (default: all)")
    parser.add_argument("--lookback", type=int, default=None,
                        help="Only process emails classified in last N days (default: all)")
    args = parser.parse_args()

    if args.mailbox_id:
        resp = sb.table("mailboxes").select("id, name, email_address, client_id").eq("id", args.mailbox_id).execute()
    else:
        resp = sb.table("mailboxes").select("id, name, email_address, client_id").execute()

    mailboxes = resp.data or []
    if not mailboxes:
        print("No mailboxes found.")
        return

    print(f"Processing {len(mailboxes)} mailbox(es)")
    if args.lookback:
        print(f"Lookback: last {args.lookback} days")
    else:
        print("Lookback: ALL classified emails (no date filter)")

    grand_total = 0
    for mb in mailboxes:
        client_id = mb.get("client_id")
        if not client_id:
            print(f"\nSkipping {mb.get('email_address', mb['id'][:8])} — no client_id")
            continue

        name = mb.get("name") or mb.get("email_address") or mb["id"][:8]
        total = link_refs_for_mailbox(mb["id"], client_id, name, args.lookback)
        grand_total += total

    print(f"\n{'='*60}")
    print(f"Grand total: {grand_total} links upserted across {len(mailboxes)} mailbox(es)")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
