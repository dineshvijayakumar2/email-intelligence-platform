"""
Throwaway script: Delete mailboxes and all related records for
dinesh@newbound.com.au and dinesh.vijayakumar@live.com users.

Steps:
  1. Find user_ids for the two email addresses
  2. Find mailboxes owned by those users OR with matching email_address
  3. Delete related records in dependency order
  4. Delete the mailboxes themselves
  5. Optionally delete the user_profiles + auth entries

DELETE AFTER VERIFIED.
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

USER_EMAILS = ['dinesh@newbound.com.au', 'dinesh.vijayakumar@live.com']

# ── Step 1: Find user_ids ────────────────────────────────────────────
print("[1/6] Finding user profiles...")
user_resp = sb.table("user_profiles").select("id, email, name").in_("email", USER_EMAILS).execute()
user_ids = [u["id"] for u in (user_resp.data or [])]
for u in (user_resp.data or []):
    print(f"  Found user: {u.get('name', '?')} ({u['email']}) -> {u['id']}")

if not user_ids:
    print("  No users found, checking mailboxes by email_address directly...")

# ── Step 2: Find mailboxes ───────────────────────────────────────────
print("\n[2/6] Finding mailboxes...")
mailbox_ids = []

# By user_id
if user_ids:
    mb_by_user = sb.table("mailboxes").select("id, name, email_address, user_id").in_("user_id", user_ids).execute()
    for m in (mb_by_user.data or []):
        print(f"  By user_id: {m['name']} ({m['email_address']}) -> {m['id']}")
        mailbox_ids.append(m["id"])

# By email_address
mb_by_email = sb.table("mailboxes").select("id, name, email_address, user_id").in_("email_address", USER_EMAILS).execute()
for m in (mb_by_email.data or []):
    if m["id"] not in mailbox_ids:
        print(f"  By email_address: {m['name']} ({m['email_address']}) -> {m['id']}")
        mailbox_ids.append(m["id"])

# Also check for Newbound client mailboxes (client 2131bdd7...)
nb_client = sb.table("user_client_assignments").select("client_id").in_("user_id", user_ids).execute()
nb_client_ids = list({r["client_id"] for r in (nb_client.data or [])})
for cid in nb_client_ids:
    mb_by_client = sb.table("mailboxes").select("id, name, email_address").eq("client_id", cid).execute()
    for m in (mb_by_client.data or []):
        if m["id"] not in mailbox_ids:
            print(f"  By client_id ({cid}): {m['name']} ({m['email_address']}) -> {m['id']}")
            mailbox_ids.append(m["id"])

if not mailbox_ids:
    print("  No mailboxes found. Nothing to delete.")
    sys.exit(0)

print(f"\n  Total mailboxes to delete: {len(mailbox_ids)}")
print(f"  IDs: {mailbox_ids}")

# ── Step 3: Count related records ────────────────────────────────────
print("\n[3/6] Counting related records...")
for mb_id in mailbox_ids:
    email_count = sb.table("emails").select("id", count="exact").eq("mailbox_id", mb_id).limit(0).execute()
    jobs_count = sb.table("processing_jobs").select("id", count="exact").eq("mailbox_id", mb_id).limit(0).execute()
    print(f"  Mailbox {mb_id}: {email_count.count or 0} emails, {jobs_count.count or 0} jobs")

# ── Confirm ──────────────────────────────────────────────────────────
confirm = input("\nWARNING:  Proceed with deletion? Type 'DELETE' to confirm: ")
if confirm != "DELETE":
    print("Aborted.")
    sys.exit(0)

# ── Step 4: Delete related records (dependency order) ────────────────
print("\n[4/6] Deleting related records...")

for mb_id in mailbox_ids:
    print(f"\n  Processing mailbox {mb_id}...")

    # Get all email IDs for this mailbox (paginated)
    all_email_ids = []
    offset = 0
    while True:
        page = sb.table("emails").select("id").eq("mailbox_id", mb_id).range(offset, offset + 999).execute()
        rows = page.data or []
        all_email_ids.extend([r["id"] for r in rows])
        if not rows:
            break
        offset += len(rows)

    print(f"    Found {len(all_email_ids)} emails")

    if all_email_ids:
        # Delete in chunks of 200 to avoid query size limits
        CHUNK = 200
        for i in range(0, len(all_email_ids), CHUNK):
            chunk = all_email_ids[i:i + CHUNK]

            # email_contact_links (CASCADE from emails, but be explicit)
            try:
                sb.table("email_contact_links").delete().in_("email_id", chunk).execute()
            except Exception as e:
                print(f"    email_contact_links chunk {i//CHUNK}: {e}")

            # ai_email_intelligence
            try:
                sb.table("ai_email_intelligence").delete().in_("email_id", chunk).execute()
            except Exception as e:
                print(f"    ai_email_intelligence chunk {i//CHUNK}: {e}")

            # email_response_metrics
            try:
                sb.table("email_response_metrics").delete().in_("email_id", chunk).execute()
            except Exception as e:
                print(f"    email_response_metrics chunk {i//CHUNK}: {e}")

            # email_embeddings
            try:
                sb.table("email_embeddings").delete().in_("email_id", chunk).execute()
            except Exception as e:
                print(f"    email_embeddings chunk {i//CHUNK}: {e}")

            if (i + CHUNK) % 2000 == 0:
                print(f"    Processed {i + CHUNK}/{len(all_email_ids)} email relations...")

        # Delete the emails themselves
        print(f"    Deleting {len(all_email_ids)} emails...")
        for i in range(0, len(all_email_ids), CHUNK):
            chunk = all_email_ids[i:i + CHUNK]
            try:
                sb.table("emails").delete().in_("id", chunk).execute()
            except Exception as e:
                print(f"    emails chunk {i//CHUNK}: {e}")

    # Delete processing_jobs
    try:
        sb.table("processing_jobs").delete().eq("mailbox_id", mb_id).execute()
        print(f"    Deleted processing_jobs")
    except Exception as e:
        print(f"    processing_jobs: {e}")

    # Delete extraction_jobs
    try:
        sb.table("extraction_jobs").delete().eq("mailbox_id", mb_id).execute()
        print(f"    Deleted extraction_jobs")
    except Exception as e:
        print(f"    extraction_jobs: {e}")

# ── Step 5: Delete mailboxes ─────────────────────────────────────────
print("\n[5/6] Deleting mailboxes...")
for mb_id in mailbox_ids:
    try:
        sb.table("mailboxes").delete().eq("id", mb_id).execute()
        print(f"  Deleted mailbox {mb_id}")
    except Exception as e:
        print(f"  Failed to delete mailbox {mb_id}: {e}")

# ── Step 6: Clean up user assignments (NOT deleting auth users) ──────
print("\n[6/6] Cleaning up user assignments...")
for uid in user_ids:
    try:
        sb.table("user_client_assignments").delete().eq("user_id", uid).execute()
        print(f"  Deleted client assignments for user {uid}")
    except Exception as e:
        print(f"  user_client_assignments: {e}")

    try:
        sb.table("user_mailbox_assignments").delete().eq("user_id", uid).execute()
        print(f"  Deleted mailbox assignments for user {uid}")
    except Exception as e:
        print(f"  user_mailbox_assignments: {e}")

print("\nOK: Done. Verify in Supabase dashboard and delete this script.")
