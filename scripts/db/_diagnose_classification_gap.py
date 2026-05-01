"""Diagnose mismatch between health RPC pending count and analyzer behavior."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
from dotenv import load_dotenv
from supabase import create_client

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
load_dotenv(env_path)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

health = sb.rpc("get_classification_health", {}).execute()

print("=" * 80)
print("HEALTH RPC RESULTS")
print("=" * 80)
for row in sorted(health.data or [], key=lambda r: -r.get("pending", 0)):
    name = row.get("email_address", "?")
    mb_id = row["mailbox_id"]
    total = row.get("total_emails", 0)
    classified = row.get("classified", 0)
    failed = row.get("failed", 0)
    skipped = row.get("skipped", 0)
    pending = row.get("pending", 0)
    print(f"\n  {name} ({mb_id[:8]})")
    print(f"    total={total}  classified={classified}  failed={failed}  skipped={skipped}  pending={pending}")

    if pending <= 5:
        continue

    # Direct counts from ai_email_intelligence
    for status in ["completed", "skipped", "failed", "processing"]:
        r = (sb.table("ai_email_intelligence")
             .select("id", count="exact")
             .eq("mailbox_id", mb_id)
             .eq("processing_status", status)
             .limit(1)
             .execute())
        cnt = r.count or 0
        if cnt > 0:
            print(f"    ai_intel {status}: {cnt}")

    # Check what analyzer's query returns vs health total
    analyzer_total = sb.table("emails").select("id", count="exact").eq("mailbox_id", mb_id).execute()
    analyzer_count = analyzer_total.count or 0
    if analyzer_count != total:
        print(f"    ** MISMATCH: emails table count={analyzer_count} vs health total={total} **")

    # Check for emails with NULL sent_date
    null_sent = sb.rpc("exec_sql", {"query": f"""
        SELECT COUNT(*) as cnt FROM emails
        WHERE mailbox_id = '{mb_id}' AND sent_date IS NULL
    """}).execute()
    null_count = (null_sent.data or [{}])[0].get("cnt", 0)
    if null_count > 0:
        print(f"    NULL sent_date emails: {null_count}")

    # Check for emails with NULL client_id
    null_client = sb.rpc("exec_sql", {"query": f"""
        SELECT COUNT(*) as cnt FROM emails
        WHERE mailbox_id = '{mb_id}' AND client_id IS NULL
    """}).execute()
    null_client_count = (null_client.data or [{}])[0].get("cnt", 0)
    if null_client_count > 0:
        print(f"    NULL client_id emails: {null_client_count}")

    # Check emails that exist in emails but NOT in ai_email_intelligence
    orphan_count = sb.rpc("exec_sql", {"query": f"""
        SELECT COUNT(*) as cnt FROM emails e
        LEFT JOIN ai_email_intelligence ai ON ai.email_id = e.id
        WHERE e.mailbox_id = '{mb_id}' AND ai.email_id IS NULL
    """}).execute()
    orphans = (orphan_count.data or [{}])[0].get("cnt", 0)
    if orphans > 0:
        print(f"    Emails with NO ai_intel record: {orphans}")

    # Sample orphan emails
    if orphans > 0:
        sample = sb.rpc("exec_sql", {"query": f"""
            SELECT e.id, e.subject, e.sent_date, e.folder_path, e.direction,
                   LENGTH(COALESCE(e.body_text,'')) as body_len, e.client_id
            FROM emails e
            LEFT JOIN ai_email_intelligence ai ON ai.email_id = e.id
            WHERE e.mailbox_id = '{mb_id}' AND ai.email_id IS NULL
            ORDER BY e.sent_date DESC NULLS LAST
            LIMIT 5
        """}).execute()
        print(f"    Sample orphans:")
        for s in (sample.data or []):
            subj = (s.get("subject") or "")[:50]
            print(f"      sent={s.get('sent_date')}  body={s.get('body_len')}  "
                  f"dir={s.get('direction')}  folder={s.get('folder_path')}  "
                  f"client={str(s.get('client_id'))[:8]}  {subj}")
