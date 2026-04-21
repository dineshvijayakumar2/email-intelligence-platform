"""
Throwaway script: Full thread re-resolve for all client emails.

Clears canonical_thread_id on all emails, runs the resolver fresh
(processes oldest-first so Tier 1/2 correctly chains replies), then
rebuilds thread_status.

Expected runtime: ~30-40 min for 255K emails.
DELETE AFTER VERIFIED.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
load_dotenv(env_path)

from supabase import create_client

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

CLIENT_ID = "241d7b99-f095-4890-b498-d84685e2a2da"

# ── Step 1: Get all mailbox IDs ──────────────────────────────────────────
print("[1/4] Finding mailboxes...")
mb_resp = sb.table("mailboxes").select("id, email_address").eq("client_id", CLIENT_ID).execute()
mailbox_ids = [m["id"] for m in (mb_resp.data or [])]
print(f"  Found {len(mailbox_ids)} mailboxes")

if not mailbox_ids:
    print("  No mailboxes found. Exiting.")
    sys.exit(1)

# ── Step 2: Clear canonical_thread_id via exec_sql (avoids REST timeout) ──
print("\n[2/4] Clearing canonical_thread_id (exec_sql, batch=500)...")
CLEAR_BATCH = 500
total_cleared = 0
t0 = time.time()

for mb_id in mailbox_ids:
    mb_cleared = 0
    while True:
        try:
            sb.rpc('exec_sql', {'query': f"""
                UPDATE emails SET
                    canonical_thread_id = NULL,
                    thread_match_method = NULL,
                    thread_match_confidence = NULL
                WHERE id IN (
                    SELECT id FROM emails
                    WHERE mailbox_id = '{mb_id}'
                      AND canonical_thread_id IS NOT NULL
                    LIMIT {CLEAR_BATCH}
                )
            """}).execute()
        except Exception as e:
            print(f"    Retry: {e}")
            time.sleep(2)
            continue

        check = sb.table("emails").select("id", count="exact").eq(
            "mailbox_id", mb_id
        ).not_.is_("canonical_thread_id", "null").limit(0).execute()
        remaining = check.count or 0
        mb_cleared = (31430 - remaining)  # approximate
        total_cleared += CLEAR_BATCH

        if total_cleared % 5000 == 0:
            elapsed = time.time() - t0
            print(f"    Progress: ~{total_cleared:,} cleared, {remaining:,} remaining ({elapsed:.0f}s)")

        if remaining == 0:
            break

    print(f"  Mailbox {mb_id[:8]}...: done")

elapsed = time.time() - t0
print(f"  Total cleared in {elapsed:.0f}s")

# ── Step 3: Run the canonical thread resolver ────────────────────────────
print("\n[3/4] Running canonical thread resolver...")
t1 = time.time()

from src.services.canonical_thread_resolver import CanonicalThreadResolver

resolver = CanonicalThreadResolver(client_id=CLIENT_ID)
stats = resolver.resolve_all()

elapsed = time.time() - t1
print(f"  Resolver complete in {elapsed:.0f}s")
print(f"  Stats: {stats}")

# ── Step 4: Rebuild thread_status ────────────────────────────────────────
print("\n[4/4] Rebuilding thread_status...")
t2 = time.time()

# Delete all thread_status for this client's mailboxes
for mb_id in mailbox_ids:
    try:
        sb.table("thread_status").delete().eq("mailbox_id", mb_id).execute()
    except Exception as e:
        print(f"  Delete thread_status for {mb_id[:8]}...: {e}")

# Use the extraction orchestrator's evaluate_threads to rebuild
from src.services.extraction_orchestrator import ExtractionOrchestrator

orch = ExtractionOrchestrator(
    mailbox_id=mailbox_ids[0],
    client_id=CLIENT_ID,
    extraction_mode="full",
    use_redis=False,
)
orch.client = sb

# evaluate_threads processes ALL canonical threads for the client's mailboxes
for mb_id in mailbox_ids:
    print(f"  Evaluating threads for mailbox {mb_id[:8]}...")
    orch.mailbox_id = mb_id
    try:
        orch._update_affected_threads()
    except Exception as e:
        print(f"    Error: {e}")

elapsed = time.time() - t2
print(f"  Thread evaluation complete in {elapsed:.0f}s")

total_elapsed = time.time() - t0
print(f"\nDone. Total time: {total_elapsed:.0f}s ({total_elapsed/60:.1f} min)")
print("Verify in the UI, then delete this script.")
