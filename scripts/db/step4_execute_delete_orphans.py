"""
Step 4 Execute: Relink emails then hard-delete orphan SB companies.

An orphan SB company has:
  - No QB customer match (not QB-anchored)
  - No contacts assigned

Steps:
  4a. Relink emails: set email.customer_company_id = contact.customer_company_id
  4b. Nullify any remaining email refs that couldn't be relinked
  4c. Delete orphan SB companies

Default: dry-run. Pass --execute to write.
"""
import os, sys, argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
from dotenv import load_dotenv
from supabase import create_client

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
load_dotenv(env_path)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
CLIENT_ID = "241d7b99-f099-4557-96e5-212c4af10812"

parser = argparse.ArgumentParser()
parser.add_argument('--execute', action='store_true')
args = parser.parse_args()


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


if not args.execute:
    print("=" * 100)
    print("DRY RUN -- pass --execute to write")
    print("=" * 100)
else:
    print("=" * 100)
    print("LIVE EXECUTION -- writing to database")
    print("=" * 100)

# 1. Build orphan set
print("\nLoading data...")
qb_matched = fetch_all('qb_customers', 'matched_company_id', not_null=['matched_company_id'])
qb_anchored = set(q['matched_company_id'] for q in qb_matched)

contacts = fetch_all('customer_contacts', 'customer_company_id', not_null=['customer_company_id'])
contact_sbs = set(c['customer_company_id'] for c in contacts)

all_sb = fetch_all('customer_companies', 'id, company_name')
print(f"  {len(all_sb)} SB companies, {len(qb_anchored)} QB-anchored, {len(contact_sbs)} with contacts")

orphan_ids = []
for row in all_sb:
    sid = row['id']
    if sid not in qb_anchored and sid not in contact_sbs:
        orphan_ids.append(sid)

print(f"  {len(orphan_ids)} orphan SB companies to delete")

if not args.execute:
    print("\nWould relink emails via contact company, then delete orphan SBs.")
    sys.exit(0)

# 2. Relink emails: set customer_company_id to match their contact's company
print(f"\nStep 4a: Relinking emails from orphan SBs to contact's company...")
relinked = 0
for i in range(0, len(orphan_ids), 100):
    batch = orphan_ids[i:i+100]
    id_list = ",".join(f"'{x}'" for x in batch)
    sql = f"""
        UPDATE emails e
        SET customer_company_id = ct.customer_company_id
        FROM customer_contacts ct
        WHERE e.customer_contact_id = ct.id
          AND e.customer_company_id IN ({id_list})
          AND ct.customer_company_id IS NOT NULL
          AND ct.customer_company_id != e.customer_company_id
    """
    try:
        sb.rpc('exec_sql', {'query': sql}).execute()
        relinked += len(batch)
    except Exception as e:
        print(f"  Error relinking batch {i//100}: {str(e)[:100]}")
    if (i + 100) % 500 == 0 or i + 100 >= len(orphan_ids):
        print(f"  Processed {min(i+100, len(orphan_ids))}/{len(orphan_ids)} orphan batches")

# 3. Nullify any remaining email refs that couldn't be relinked
print(f"\nStep 4b: Nullifying any remaining email refs to orphan SBs...")
for i in range(0, len(orphan_ids), 100):
    batch = orphan_ids[i:i+100]
    id_list = ",".join(f"'{x}'" for x in batch)
    sql = f"UPDATE emails SET customer_company_id = NULL WHERE customer_company_id IN ({id_list})"
    try:
        sb.rpc('exec_sql', {'query': sql}).execute()
    except Exception as e:
        print(f"  Error nullifying batch {i//100}: {str(e)[:100]}")

print("  Done nullifying stragglers")

# 4. Delete orphan SB companies
print(f"\nStep 4c: Deleting {len(orphan_ids)} orphan SB companies...")
deleted = 0
errors = 0
for i in range(0, len(orphan_ids), 50):
    batch = orphan_ids[i:i+50]
    try:
        sb.table('customer_companies').delete().in_('id', batch).execute()
        deleted += len(batch)
    except Exception as e:
        errors += 1
        if errors <= 5:
            print(f"  Error deleting batch {i//50}: {str(e)[:100]}")
        for sid in batch:
            try:
                sb.table('customer_companies').delete().eq('id', sid).execute()
                deleted += 1
            except Exception:
                errors += 1

    if (i + 50) % 500 == 0 or i + 50 >= len(orphan_ids):
        print(f"  Deleted {deleted}/{len(orphan_ids)}, errors: {errors}")

print(f"\n{'='*100}")
print(f"STEP 4 SUMMARY")
print(f"{'='*100}")
print(f"  Emails relinked via contact:  {relinked} orphan batches processed")
print(f"  Orphan SBs deleted:           {deleted}")
print(f"  Errors:                       {errors}")
print(f"{'='*100}")
