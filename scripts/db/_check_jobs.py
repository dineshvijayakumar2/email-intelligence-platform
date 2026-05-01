"""Quick check of processing_jobs state."""
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
from dotenv import load_dotenv
from supabase import create_client

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
load_dotenv(env_path)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

print("=== Active jobs (pending/running) ===")
resp = (
    sb.table("processing_jobs")
    .select("id, job_type, status, mailbox_id, created_at, current_stage, worker_id")
    .in_("status", ["pending", "running"])
    .order("created_at", desc=True)
    .limit(10)
    .execute()
)
for j in (resp.data or []):
    print(f"  {j['id'][:8]}  {j['status']:10}  {j['job_type']:20}  stage={j.get('current_stage','—')}  created={j['created_at'][:19]}")
if not resp.data:
    print("  (none)")

print("\n=== Recent interrupted (last 48h) ===")
from datetime import datetime, timezone, timedelta
cutoff = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
resp = (
    sb.table("processing_jobs")
    .select("id, job_type, status, mailbox_id, created_at, parameters, current_stage")
    .eq("status", "interrupted")
    .gte("created_at", cutoff)
    .order("created_at", desc=True)
    .limit(20)
    .execute()
)
for j in (resp.data or []):
    params = j.get("parameters") or {}
    steps = params.get("completed_steps") or []
    resumed_from = params.get("resumed_from", "—")
    stage = j.get('current_stage') or '—'
    print(f"  {j['id'][:8]}  {j['created_at'][:19]}  stage={stage:25}  steps={len(steps)}  resumed_from={str(resumed_from)[:8]}")
if not resp.data:
    print("  (none)")

print("\n=== Recent completed (last 48h) ===")
resp = (
    sb.table("processing_jobs")
    .select("id, job_type, status, created_at, current_stage")
    .eq("job_type", "email_pipeline")
    .eq("status", "completed")
    .gte("created_at", cutoff)
    .order("created_at", desc=True)
    .limit(10)
    .execute()
)
for j in (resp.data or []):
    print(f"  {j['id'][:8]}  {j['created_at'][:19]}  stage={j.get('current_stage','—')}")
if not resp.data:
    print("  (none)")

print("\n=== Recent failed (last 48h) ===")
resp = (
    sb.table("processing_jobs")
    .select("id, job_type, status, created_at, current_stage, error_log")
    .eq("job_type", "email_pipeline")
    .eq("status", "failed")
    .gte("created_at", cutoff)
    .order("created_at", desc=True)
    .limit(10)
    .execute()
)
for j in (resp.data or []):
    err = ""
    if j.get("error_log"):
        err = str(j["error_log"][0].get("message", ""))[:80] if j["error_log"] else ""
    print(f"  {j['id'][:8]}  {j['created_at'][:19]}  stage={j.get('current_stage','—'):25}  err={err}")
if not resp.data:
    print("  (none)")
