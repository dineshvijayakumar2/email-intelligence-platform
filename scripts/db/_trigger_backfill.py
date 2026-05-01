"""
Trigger AI classification backfill for all Carbon8 mailboxes.
Creates a processing_jobs row that the Railway worker picks up automatically.
"""
import os, sys, json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
from dotenv import load_dotenv
from supabase import create_client

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
load_dotenv(env_path)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

# 1. Get current classification health
print("[1/5] Current classification coverage...")
try:
    health = sb.rpc("get_classification_health", {"p_client_id": None}).execute()
    for row in (health.data or []):
        total = row.get("total_emails", 0)
        classified = row.get("classified", 0)
        pct = row.get("coverage_pct", 0)
        name = row.get("mailbox_name", "?")
        pending = row.get("pending", 0)
        print(f"  {name:40s}  {classified:>6}/{total:<6}  {pct:5.1f}%  ({pending} pending)")
except Exception as e:
    print(f"  [WARN] Could not get health: {e}")

# 2. Get client + mailboxes
print("\n[2/5] Finding Carbon8 client and mailboxes...")
clients = sb.table("clients").select("id, client_name").execute()
carbon8 = [c for c in (clients.data or []) if "carbon" in c.get("client_name", "").lower()]
if not carbon8:
    print("  [FAIL] No Carbon8 client found")
    sys.exit(1)

client_id = carbon8[0]["id"]
print(f"  Client: {carbon8[0]['client_name']} ({client_id})")

mailboxes = sb.table("mailboxes").select("id, name, email_address").eq("client_id", client_id).execute()
mailbox_ids = [m["id"] for m in (mailboxes.data or [])]
for m in (mailboxes.data or []):
    print(f"  Mailbox: {m.get('name', '?'):30s} {m.get('email_address', '?')}")
print(f"  Total: {len(mailbox_ids)} mailboxes")

if not mailbox_ids:
    print("  [FAIL] No mailboxes found")
    sys.exit(1)

# 3. Check for already-active backfill job
print("\n[3/5] Checking for active backfill jobs...")
active = sb.table("processing_jobs") \
    .select("id, status, created_at, current_stage") \
    .eq("job_type", "ai_backfill") \
    .in_("status", ["pending", "running"]) \
    .execute()

if active.data:
    for j in active.data:
        print(f"  [WARN] Active job found: {j['id']} status={j['status']} stage={j.get('current_stage', '?')}")
    print("  Aborting — cancel the active job first or wait for it to complete")
    sys.exit(1)
print("  No active backfill jobs — safe to create")

# 4. Create the job
print("\n[4/5] Creating ai_backfill job...")
job_data = {
    "job_type": "ai_backfill",
    "client_id": client_id,
    "status": "pending",
    "parameters": json.dumps({"mailbox_ids": mailbox_ids}),
    "triggered_by": "script",
    "total_records": 0,
    "processed_records": 0,
    "failed_records": 0,
    "attempts": 0,
    "max_attempts": 1,
}
result = sb.table("processing_jobs").insert(job_data).execute()
job_id = result.data[0]["id"]
print(f"  [ok] Job created: {job_id}")

# 5. Verify
print("\n[5/5] Verifying job is pending...")
verify = sb.table("processing_jobs").select("id, status, job_type, parameters").eq("id", job_id).execute()
if verify.data and verify.data[0]["status"] == "pending":
    print(f"  [ok] Job {job_id} is pending — worker will pick it up")
    print(f"\n=== Backfill queued for {len(mailbox_ids)} mailboxes ===")
    print("Monitor progress: check processing_jobs table or the Data Health page in the UI")
else:
    print(f"  [WARN] Unexpected state: {verify.data}")
