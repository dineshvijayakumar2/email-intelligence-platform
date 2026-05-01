"""Check for client_id mismatches between emails and ai_email_intelligence."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
from dotenv import load_dotenv
from supabase import create_client

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
load_dotenv(env_path)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

# Get the client_id used by Carbon8
clients = sb.table("clients").select("id, client_name").execute()
for c in (clients.data or []):
    print(f"Client: {c['client_name']} - {c['id']}")

print()

# Run health with and without client_id
health_no_filter = sb.rpc("get_classification_health", {}).execute()
print("=" * 80)
print("Comparing health RPC: no filter vs with client_id")
print("=" * 80)

for c in (clients.data or []):
    client_id = c["id"]
    health_with_filter = sb.rpc("get_classification_health", {"p_client_id": client_id}).execute()

    no_filter_map = {r["mailbox_id"]: r for r in (health_no_filter.data or [])}
    with_filter_map = {r["mailbox_id"]: r for r in (health_with_filter.data or [])}

    for mb_id in set(list(no_filter_map.keys()) + list(with_filter_map.keys())):
        nf = no_filter_map.get(mb_id, {})
        wf = with_filter_map.get(mb_id, {})
        name = nf.get("email_address") or wf.get("email_address") or mb_id[:8]

        nf_pending = nf.get("pending", 0)
        wf_pending = wf.get("pending", 0)
        nf_total = nf.get("total_emails", 0)
        wf_total = wf.get("total_emails", 0)
        nf_skipped = nf.get("skipped", 0)
        wf_skipped = wf.get("skipped", 0)
        nf_classified = nf.get("classified", 0)
        wf_classified = wf.get("classified", 0)

        if nf_pending != wf_pending or nf_total != wf_total:
            print(f"\n  {name}:")
            print(f"    No filter:   total={nf_total}  classified={nf_classified}  skipped={nf_skipped}  pending={nf_pending}")
            print(f"    With filter:  total={wf_total}  classified={wf_classified}  skipped={wf_skipped}  pending={wf_pending}")
            print(f"    Dtotal={nf_total-wf_total}  Dclassified={nf_classified-wf_classified}  Dskipped={nf_skipped-wf_skipped}  Dpending={nf_pending-wf_pending}")

# Check NULL client_id in ai_email_intelligence
print("\n" + "=" * 80)
print("ai_email_intelligence records with NULL client_id")
print("=" * 80)
null_ai = sb.rpc("exec_sql", {"query": """
    SELECT ai.mailbox_id, m.email_address, m.name as mb_name,
           COUNT(*) as cnt,
           COUNT(*) FILTER (WHERE ai.processing_status = 'completed') as completed,
           COUNT(*) FILTER (WHERE ai.processing_status = 'skipped') as skipped
    FROM ai_email_intelligence ai
    JOIN mailboxes m ON m.id = ai.mailbox_id
    WHERE ai.client_id IS NULL
    GROUP BY ai.mailbox_id, m.email_address, m.name
    ORDER BY cnt DESC
"""}).execute()
for row in (null_ai.data or []):
    name = row.get("email_address") or row.get("mb_name")
    print(f"  {name}: {row['cnt']} NULL client_id (completed={row['completed']}, skipped={row['skipped']})")

# Check NULL client_id in emails
print("\n" + "=" * 80)
print("emails records with NULL client_id")
print("=" * 80)
null_emails = sb.rpc("exec_sql", {"query": """
    SELECT e.mailbox_id, m.email_address, m.name as mb_name, COUNT(*) as cnt
    FROM emails e
    JOIN mailboxes m ON m.id = e.mailbox_id
    WHERE e.client_id IS NULL
    GROUP BY e.mailbox_id, m.email_address, m.name
    ORDER BY cnt DESC
"""}).execute()
for row in (null_emails.data or []):
    name = row.get("email_address") or row.get("mb_name")
    print(f"  {name}: {row['cnt']} NULL client_id")
