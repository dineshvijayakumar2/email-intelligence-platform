"""Check step details of recently completed pipeline jobs."""
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
from dotenv import load_dotenv
from supabase import create_client

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
load_dotenv(env_path)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

from datetime import datetime, timezone, timedelta
cutoff = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()

resp = (
    sb.table("processing_jobs")
    .select("id, job_type, status, created_at, completed_at, parameters, error_summary, current_stage, mailbox_id")
    .eq("job_type", "email_pipeline")
    .eq("status", "completed")
    .gte("created_at", cutoff)
    .order("created_at", desc=True)
    .limit(10)
    .execute()
)

for j in (resp.data or []):
    params = j.get("parameters") or {}
    summary = j.get("error_summary") or {}
    step_results = summary.get("step_results") or {}
    completed_steps = params.get("completed_steps") or []
    trigger = params.get("trigger_source", "?")

    print(f"\n{'='*70}")
    print(f"Job: {j['id'][:12]}  mailbox: {(j.get('mailbox_id') or '?')[:12]}")
    print(f"Created: {j['created_at'][:19]}  Completed: {(j.get('completed_at') or '?')[:19]}")
    print(f"Trigger: {trigger}  Completed steps: {len(completed_steps)}/{8}")

    if completed_steps:
        print(f"Steps: {', '.join(completed_steps)}")

    if step_results:
        print(f"\nStep details:")
        for stage, detail in step_results.items():
            if isinstance(detail, dict):
                status = detail.get("status", "?")
                dur = detail.get("duration_s", "?")
                data = detail.get("data")
                err = detail.get("error", "")
                line = f"  {stage:30} {status:12} {dur}s"
                if err:
                    line += f"  ERR: {err[:60]}"
                if data and isinstance(data, dict):
                    # Show key metrics from step data
                    interesting = {k: v for k, v in data.items()
                                   if k in ('success', 'total_embedded', 'total_skipped',
                                           'emails_analyzed', 'emails_bucketed', 'threads_updated',
                                           'contacts_extracted', 'companies_resolved',
                                           'emails_processed', 'total_contacts', 'total_companies')}
                    if interesting:
                        line += f"  {interesting}"
                print(line)
    else:
        print("  (no step_results in error_summary)")
