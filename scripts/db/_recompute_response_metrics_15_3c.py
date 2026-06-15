"""
ONE-OFF (15.3c) — recompute email_response_metrics for Carbon8 with the FIXED pairing logic
(canonical-thread grouping + same-conversation validation + automated-inbound exclusion).

Exercises the real code path: imports the patched ResponseTimeTracker and runs it per mailbox.
Strategy: compute ALL mailboxes in memory first (fail-fast), then delete-all-Carbon8 metric
rows (scoped via emails join), then insert fresh per mailbox, then refresh contact averages.
The metric is keyed by email_id (one row per responding email); the fix changes WHICH pairs
exist, so a plain upsert would leave stale rows — hence delete-then-insert.

Read-after-write verification is done separately by _resp_latency_plausibility.py.
"""
import os, sys, io, time, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, "..", "..", "backend"))
sys.path.insert(0, BACKEND)
from dotenv import load_dotenv
load_dotenv(os.path.join(BACKEND, ".env.production"))
from supabase import create_client
from src.services.response_time_tracker import ResponseTimeTracker

CARBON8 = "241d7b99-f099-4557-96e5-212c4af10812"
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


def exec_sql(q):
    return sb.rpc("exec_sql", {"query": q}).execute()


def counts_by_mailbox():
    q = f"""SELECT coalesce(e.mailbox_id::text,'<none>') mb, count(*) c
            FROM email_response_metrics m JOIN emails e ON e.id=m.email_id
            WHERE e.client_id='{CARBON8}' GROUP BY 1"""
    rows = exec_sql(q).data or []
    return {r["mb"]: r["c"] for r in rows}


# ── mailboxes ──────────────────────────────────────────────────────────────
mboxes = sb.table("mailboxes").select("id, name, user_id").eq("client_id", CARBON8).execute().data or []
profiles = sb.table("user_profiles").select("id, name").execute().data or []
uname = {p["id"]: (p.get("name") or "") for p in profiles}
disp = {m["id"]: (uname.get(m.get("user_id")) or m.get("name") or "<no-user>") for m in mboxes}
print(f"Carbon8 mailboxes: {len(mboxes)}")

before = counts_by_mailbox()

# ── 1. compute all mailboxes in memory (fail-fast before any write) ─────────
print("\n[1] computing response pairs with FIXED tracker (per mailbox) ...", flush=True)
computed = {}   # mailbox_id -> list[ResponseMetric]
for m in mboxes:
    mid = m["id"]
    tracker = ResponseTimeTracker(mailbox_id=mid, client_id=CARBON8)
    metrics = tracker.calculate_response_times()
    computed[mid] = metrics
    print(f"    {disp[mid]:<32} pairs={len(metrics):,}", flush=True)
total_new = sum(len(v) for v in computed.values())
print(f"  total new pairs: {total_new:,}")

# ── 2. delete all existing Carbon8 metric rows (server-side, one statement) ─
print("\n[2] deleting existing Carbon8 email_response_metrics rows ...", flush=True)
del_sql = (f"DELETE FROM email_response_metrics m USING emails e "
           f"WHERE e.id = m.email_id AND e.client_id = '{CARBON8}'")
exec_sql(del_sql)
exec_sql("NOTIFY pgrst, 'reload schema'")
remaining = sum(counts_by_mailbox().values())
print(f"  remaining Carbon8 rows after delete: {remaining}")

# ── 3. insert fresh metrics per mailbox ─────────────────────────────────────
print("\n[3] inserting fresh metrics ...", flush=True)
for m in mboxes:
    mid = m["id"]
    tracker = ResponseTimeTracker(mailbox_id=mid, client_id=CARBON8)
    res = tracker.save_metrics(computed[mid])
    print(f"    {disp[mid]:<32} saved={res.get('created_count',0):,}  errors={len(res.get('errors',[]))}", flush=True)

# ── 4. refresh contact averages (derived from the metrics) ──────────────────
print("\n[4] refreshing contact response-time averages (RPC) ...", flush=True)
upd = sb.rpc("update_all_contact_response_times", {"p_client_id": CARBON8}).execute()
print(f"    contacts updated: {upd.data}")

# ── report ─────────────────────────────────────────────────────────────────
after = counts_by_mailbox()
print("\n" + "=" * 78)
print(f"  {'mailbox':<32}{'before':>10}{'after':>10}{'delta':>10}")
print("  " + "-" * 62)
for m in mboxes:
    mid = m["id"]
    b, a = before.get(mid, 0), after.get(mid, 0)
    print(f"  {disp[mid]:<32}{b:>10,}{a:>10,}{a-b:>+10,}")
print("  " + "-" * 62)
tb, ta = sum(before.values()), sum(after.values())
print(f"  {'TOTAL (Carbon8)':<32}{tb:>10,}{ta:>10,}{ta-tb:>+10,}")
print("=" * 78)
print("recompute complete — verify medians with _resp_latency_plausibility.py")
