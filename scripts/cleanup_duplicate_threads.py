"""
Cleanup duplicate thread_status rows.

Merges rows that have the same normalized subject + contact/company,
keeping the one with highest message_count. Deletes the rest.

Run: cd backend && python ../scripts/cleanup_duplicate_threads.py
"""

import os, re, sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'backend', '.env.development'))

from supabase import create_client

url = os.environ['SUPABASE_URL']
key = os.environ['SUPABASE_SERVICE_KEY']
sb = create_client(url, key)

SUBJECT_STRIP = re.compile(r'^(re|fwd?|fw):\s*', re.IGNORECASE)

def norm_subject(s: str | None) -> str:
    if not s:
        return ''
    cleaned = s.strip().lower()
    while SUBJECT_STRIP.match(cleaned):
        cleaned = SUBJECT_STRIP.sub('', cleaned).strip()
    return cleaned

# Fetch all thread_status rows (paginated)
print("Fetching all thread_status rows...")
all_rows = []
offset = 0
while True:
    page = sb.table('thread_status').select(
        'id, thread_id, canonical_thread_id, subject, customer_contact_id, customer_company_id, '
        'message_count, last_message_at, status, mailbox_id'
    ).range(offset, offset + 999).execute()
    rows = page.data or []
    all_rows.extend(rows)
    if len(rows) == 0:
        break
    offset += len(rows)
    if offset % 5000 == 0:
        print(f"  ...fetched {offset} rows")

print(f"Total thread_status rows: {len(all_rows)}")

# Group by normalized subject + contact/company
groups: dict[str, list[dict]] = defaultdict(list)
for r in all_rows:
    subj = norm_subject(r.get('subject'))
    contact = r.get('customer_contact_id') or ''
    company = r.get('customer_company_id') or ''
    key = f"{subj}|{contact or company}"
    groups[key].append(r)

# Find groups with duplicates
dupe_groups = {k: v for k, v in groups.items() if len(v) > 1}
print(f"Groups with duplicates: {len(dupe_groups)}")

# Determine which rows to delete
ids_to_delete = []
total_merged = 0
for key, rows in dupe_groups.items():
    # Sort: highest message_count first, then most recent last_message_at
    rows.sort(key=lambda r: (r.get('message_count') or 0, r.get('last_message_at') or ''), reverse=True)
    keeper = rows[0]
    dupes = rows[1:]

    # Sum up message counts from dupes into keeper? No — message_count is per-thread, not additive.
    # Just keep the best one and delete the rest.
    for d in dupes:
        ids_to_delete.append(d['id'])

    total_merged += len(dupes)

print(f"Rows to delete (duplicates): {len(ids_to_delete)}")
print(f"Rows to keep: {len(all_rows) - len(ids_to_delete)}")

if not ids_to_delete:
    print("No duplicates found. Done.")
    sys.exit(0)

# Confirm before deleting
print(f"\nSample duplicates being removed:")
sample_keys = list(dupe_groups.keys())[:5]
for k in sample_keys:
    rows = dupe_groups[k]
    subj = rows[0].get('subject', '?')
    print(f"  '{subj}' -- {len(rows)} rows -> keeping 1 (message_count={rows[0].get('message_count')})")

resp = input(f"\nDelete {len(ids_to_delete)} duplicate rows? [y/N] ")
if resp.strip().lower() != 'y':
    print("Aborted.")
    sys.exit(0)

# Delete in batches of 200
deleted = 0
batch_size = 200
for i in range(0, len(ids_to_delete), batch_size):
    batch = ids_to_delete[i:i + batch_size]
    try:
        sb.table('thread_status').delete().in_('id', batch).execute()
        deleted += len(batch)
        if deleted % 1000 == 0:
            print(f"  ...deleted {deleted}/{len(ids_to_delete)}")
    except Exception as e:
        print(f"  Error at batch {i}: {e}")

print(f"\nDone! Deleted {deleted} duplicate thread_status rows.")
print(f"Remaining rows: ~{len(all_rows) - deleted}")
