"""
Step 2 Execute: Move contacts to their QB-anchored SB company.

For each contact whose email appears in qb_unique_emails:
  - Look up which QB customer owns that email
  - Get that QB customer's matched_company_id (SB company)
  - If contact is on a different SB, move it

Writes to:
  - customer_contacts (UPDATE customer_company_id)

Handles the unique constraint (customer_company_id, email_address) by checking
for duplicates before moving.
"""
import os, sys, json
from datetime import datetime, timezone
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
from dotenv import load_dotenv
from supabase import create_client

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
load_dotenv(env_path)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
CLIENT_ID = "241d7b99-f099-4557-96e5-212c4af10812"
NOW_ISO = datetime.now(timezone.utc).isoformat()

DRY_RUN = "--execute" not in sys.argv


def fetch_all(table, select, filters=None, not_null=None, is_null=None):
    rows = []
    offset = 0
    while True:
        q = sb.table(table).select(select).eq('client_id', CLIENT_ID)
        if filters:
            for k, v in filters.items():
                q = q.eq(k, v)
        if not_null:
            for col in not_null:
                q = q.not_.is_(col, 'null')
        if is_null:
            for col in is_null:
                q = q.is_(col, 'null')
        resp = q.range(offset, offset + 999).execute()
        rows.extend(resp.data or [])
        if len(resp.data or []) < 1000:
            break
        offset += 1000
    return rows


if DRY_RUN:
    print("=" * 100)
    print("DRY RUN -- pass --execute to write changes")
    print("=" * 100)
else:
    print("=" * 100)
    print("LIVE EXECUTION -- writing to database")
    print("=" * 100)

# ─── Load data ────────────────────────────────────────────────────────────
print("\nLoading data...")

qb_emails_raw = fetch_all('qb_unique_emails', 'qb_customer_id, email',
                           filters={'hide': False, 'email_invalid': False})
print(f"  {len(qb_emails_raw)} QB unique emails")

email_to_qb_keys = defaultdict(set)
for qe in qb_emails_raw:
    email = (qe.get('email') or '').strip().lower()
    qb_key = qe.get('qb_customer_id')
    if email and qb_key:
        email_to_qb_keys[email].add(qb_key)

qb_customers = fetch_all('qb_customers',
    'customer_key_id, customer_name, total_invoiced, matched_company_id')
qb_key_to_info = {}
for q in qb_customers:
    key = q.get('customer_key_id')
    if key:
        qb_key_to_info[key] = q
print(f"  {len(qb_customers)} QB customers")

contacts = fetch_all('customer_contacts', 'id, email_address, customer_company_id')
print(f"  {len(contacts)} contacts")

# Build existing (company_id, email) pairs to check unique constraint
existing_pairs = set()
for c in contacts:
    co_id = c.get('customer_company_id')
    email = (c.get('email_address') or '').strip().lower()
    if co_id and email:
        existing_pairs.add((co_id, email))

# ─── Compute moves ───────────────────────────────────────────────────────
print("\nComputing moves...")

moves = []
already_correct = 0
skipped_ambiguous = 0
skipped_no_sb = 0
skipped_duplicate = 0

for c in contacts:
    email = (c.get('email_address') or '').strip().lower()
    if not email:
        continue

    qb_keys = email_to_qb_keys.get(email)
    if not qb_keys:
        continue

    if len(qb_keys) > 1:
        skipped_ambiguous += 1
        continue

    qb_key = list(qb_keys)[0]
    qb_info = qb_key_to_info.get(qb_key)
    if not qb_info:
        continue

    target_sb = qb_info.get('matched_company_id')
    if not target_sb:
        skipped_no_sb += 1
        continue

    current_sb = c.get('customer_company_id')
    if current_sb == target_sb:
        already_correct += 1
        continue

    # Check unique constraint: (target_sb, email) must not already exist
    if (target_sb, email) in existing_pairs:
        skipped_duplicate += 1
        continue

    moves.append({
        'contact_id': c['id'],
        'email': email,
        'current_sb': current_sb,
        'target_sb': target_sb,
        'qb_name': qb_info.get('customer_name', '?'),
        'qb_revenue': float(qb_info.get('total_invoiced') or 0),
    })

print(f"  Already correct:    {already_correct:>6}")
print(f"  Need to move:       {len(moves):>6}")
print(f"  Skipped ambiguous:  {skipped_ambiguous:>6}")
print(f"  Skipped no SB:      {skipped_no_sb:>6}")
print(f"  Skipped duplicate:  {skipped_duplicate:>6}")

# ─── Execute moves ────────────────────────────────────────────────────────
print(f"\n{'='*100}")
print(f"Moving {len(moves)} contacts")
print(f"{'='*100}")

moved_count = 0
move_errors = []

for i, m in enumerate(moves):
    if not DRY_RUN:
        try:
            sb.table('customer_contacts').update({
                'customer_company_id': m['target_sb'],
                'updated_at': NOW_ISO,
            }).eq('id', m['contact_id']).execute()
            moved_count += 1
        except Exception as e:
            move_errors.append({
                'contact_id': m['contact_id'],
                'email': m['email'],
                'error': str(e),
            })
    else:
        moved_count += 1

    if moved_count <= 5 or moved_count % 500 == 0:
        print(f"  [{moved_count}] {m['email'][:35]:<35} -> {m['qb_name'][:30]:<30} ${m['qb_revenue']:>8,.0f}")

print(f"\n  Moved: {moved_count}, Errors: {len(move_errors)}")

if move_errors:
    print(f"\n  First 10 errors:")
    for err in move_errors[:10]:
        print(f"    {err['email']}: {err['error'][:80]}")

# ─── Summary ──────────────────────────────────────────────────────────────
print(f"\n{'='*100}")
print("STEP 2 SUMMARY")
print(f"{'='*100}")
print(f"  Moved:              {moved_count:>6} {'(dry run)' if DRY_RUN else 'executed'}")
print(f"  Already correct:    {already_correct:>6}")
print(f"  Skipped ambiguous:  {skipped_ambiguous:>6}")
print(f"  Skipped no SB:      {skipped_no_sb:>6}")
print(f"  Skipped duplicate:  {skipped_duplicate:>6}")
print(f"  Errors:             {len(move_errors):>6}")
if DRY_RUN:
    print(f"\n  Run with --execute to apply changes")
print(f"{'='*100}")
