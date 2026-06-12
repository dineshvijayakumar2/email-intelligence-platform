"""Read-only: inspect email_response_metrics coverage per Carbon8 mailbox.

Looks up mailbox ids, counts existing metric rows joined to each mailbox's emails,
and estimates reply pairs available, to confirm under-computation before re-running
the response-time tracker.
"""
import os
from dotenv import load_dotenv
from supabase import create_client

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
load_dotenv(env_path)
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
CLIENT_ID = "241d7b99-f099-4557-96e5-212c4af10812"


def count_emails(mailbox_id, **filters):
    q = sb.table("emails").select("id", count="exact").eq("mailbox_id", mailbox_id)
    for k, v in filters.items():
        q = q.eq(k, v)
    return q.execute().count


def count_metrics_for_mailbox(mailbox_id):
    """Count email_response_metrics whose email_id belongs to this mailbox.

    Paginate email ids for the mailbox, then count metric rows in chunks via in_().
    """
    # Gather email ids for the mailbox (paginated)
    email_ids = []
    offset = 0
    PAGE = 1000
    while True:
        rows = (sb.table("emails").select("id")
                .eq("mailbox_id", mailbox_id)
                .range(offset, offset + PAGE - 1).execute().data or [])
        email_ids.extend(r["id"] for r in rows)
        if len(rows) < PAGE:
            break
        offset += PAGE
    # Count metrics in chunks
    total = 0
    CH = 200
    for i in range(0, len(email_ids), CH):
        chunk = email_ids[i:i + CH]
        c = (sb.table("email_response_metrics").select("email_id", count="exact")
             .in_("email_id", chunk).execute().count)
        total += c or 0
    return total, len(email_ids)


mbs = (sb.table("mailboxes")
       .select("*")
       .eq("client_id", CLIENT_ID).execute().data or [])

print(f"Carbon8 mailboxes ({len(mbs)}):\n")
if mbs:
    print("  columns:", ", ".join(sorted(mbs[0].keys())))
    print()
for mb in sorted(mbs, key=lambda m: (m.get("name") or "").lower()):
    print(f"  {mb['id']}  {mb.get('name')!r}  <{mb.get('email_address')}>")

print("\n--- Coverage per mailbox (metrics rows / total emails) ---\n")
for mb in sorted(mbs, key=lambda m: (m.get("name") or "").lower()):
    metrics, n_emails = count_metrics_for_mailbox(mb["id"])
    inbound = count_emails(mb["id"], is_outbound=False)
    outbound = count_emails(mb["id"], is_outbound=True)
    print(f"  {mb.get('name')!r:40s} emails={n_emails:6d}  inbound={inbound:6d}  "
          f"outbound={outbound:6d}  metric_rows={metrics:6d}")
