"""ONE-OFF (15.3c cleanup) — the shared hello box had non-CARBON8 client_id on most of its
emails, so the main recompute's client-scoped DELETE left stale provider-thread rows. Re-do
hello with a MAILBOX-scoped delete + reinsert so it's consistent too. Writes."""
import os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
sys.path.insert(0, BACKEND)
from dotenv import load_dotenv
load_dotenv(os.path.join(BACKEND, ".env.production"))
from supabase import create_client
from src.services.response_time_tracker import ResponseTimeTracker
CARBON8 = "241d7b99-f099-4557-96e5-212c4af10812"
HELLO = "c1157f56-79a0-4f0b-9dcf-2db257f0d5c4"
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

print("[1] computing hello pairs (fixed tracker) ...", flush=True)
t = ResponseTimeTracker(mailbox_id=HELLO, client_id=CARBON8)
metrics = t.calculate_response_times()
print(f"    computed {len(metrics):,} pairs", flush=True)

print("[2] mailbox-scoped delete of hello metric rows ...", flush=True)
sb.rpc("exec_sql", {"query":
    f"DELETE FROM email_response_metrics m USING emails e "
    f"WHERE e.id=m.email_id AND e.mailbox_id='{HELLO}'"}).execute()
sb.rpc("exec_sql", {"query": "NOTIFY pgrst, 'reload schema'"}).execute()

print("[3] reinserting ...", flush=True)
res = t.save_metrics(metrics)
print(f"    saved {res.get('created_count',0):,}  errors={len(res.get('errors',[]))}", flush=True)

# refresh contact averages once more (hello pairs feed them)
upd = sb.rpc("update_all_contact_response_times", {"p_client_id": CARBON8}).execute()
print(f"[4] contact averages refreshed: {upd.data}")
print("done — hello cleaned")
