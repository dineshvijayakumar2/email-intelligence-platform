"""
Step 4 Pre-flight: Identify orphan SB companies for soft-delete.

An SB company is an orphan if:
  - No QB customer points to it (not QB-anchored)
  - No contacts are assigned to it (or all were moved away in Step 2)

These are companies created by the old domain/person-name resolution
that are now empty shells.

Read-only -- no writes.
"""
import os, sys
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


print("=" * 100)
print("STEP 4 PRE-FLIGHT: Identify orphan SB companies")
print("=" * 100)

# ─── 1. QB-anchored SB companies ─────────────────────────────────────────
print("\n1. Loading QB customer matches...")
qb_matched = fetch_all('qb_customers', 'matched_company_id', not_null=['matched_company_id'])
qb_anchored_sbs = set(q['matched_company_id'] for q in qb_matched)
print(f"   {len(qb_anchored_sbs)} SB companies are QB-anchored")

# ─── 2. Contact assignments ──────────────────────────────────────────────
print("\n2. Loading contact company assignments...")
contacts = fetch_all('customer_contacts', 'customer_company_id',
                      not_null=['customer_company_id'])
contact_sbs = defaultdict(int)
for c in contacts:
    contact_sbs[c['customer_company_id']] += 1
print(f"   {len(contact_sbs)} SB companies have contacts")

# ─── 3. All SB companies ─────────────────────────────────────────────────
print("\n3. Loading all SB companies...")
all_sb = fetch_all('customer_companies', 'id, company_name')
print(f"   {len(all_sb)} total SB companies")

# ─── 4. Classify ─────────────────────────────────────────────────────────
print("\n4. Classifying...")

orphans = []
qb_only = []       # QB-anchored but no contacts
contacts_only = [] # has contacts but no QB anchor
healthy = []       # both QB and contacts

for sb_row in all_sb:
    sb_id = sb_row['id']
    has_qb = sb_id in qb_anchored_sbs
    has_contacts = contact_sbs.get(sb_id, 0) > 0
    contact_count = contact_sbs.get(sb_id, 0)

    if has_qb and has_contacts:
        healthy.append(sb_row)
    elif has_qb and not has_contacts:
        qb_only.append(sb_row)
    elif not has_qb and has_contacts:
        contacts_only.append({'row': sb_row, 'contact_count': contact_count})
    else:
        orphans.append(sb_row)

print(f"   Healthy (QB + contacts):  {len(healthy):>6}")
print(f"   QB-only (no contacts):    {len(qb_only):>6}")
print(f"   Contacts-only (no QB):    {len(contacts_only):>6}")
print(f"   Orphan (no QB, no contacts): {len(orphans):>6}")

# ─── 5. Orphan detail ────────────────────────────────────────────────────
print(f"\n{'='*100}")
print(f"ORPHANS: {len(orphans)} SB companies with no QB match and no contacts")
print(f"{'='*100}")
print(f"  These are safe to soft-delete (or hard-delete).")
print(f"\n  Sample (first 20):")
for sb_row in orphans[:20]:
    print(f"    {sb_row.get('company_name', '?')[:60]}")

# ─── 6. Contacts-only detail ─────────────────────────────────────────────
print(f"\n{'='*100}")
print(f"CONTACTS-ONLY: {len(contacts_only)} SB companies with contacts but no QB match")
print(f"{'='*100}")
print(f"  These may contain non-QB contacts (personal emails, vendors, etc).")
print(f"  Do NOT delete -- contacts would lose their company link.")

contacts_only.sort(key=lambda x: x['contact_count'], reverse=True)
print(f"\n  Top 20 by contact count:")
for item in contacts_only[:20]:
    print(f"    {item['row'].get('company_name', '?')[:45]:<45} {item['contact_count']:>4} contacts")

# ─── 7. Check references ─────────────────────────────────────────────────
print(f"\n{'='*100}")
print("Checking for other references to orphan SB IDs...")
print(f"{'='*100}")

orphan_ids = [sb_row['id'] for sb_row in orphans]

# Check emails table
email_refs = 0
for i in range(0, len(orphan_ids), 200):
    batch = orphan_ids[i:i+200]
    resp = sb.table('emails').select('id', count='exact').in_('customer_company_id', batch).limit(1).execute()
    email_refs += (resp.count or 0)

print(f"  Emails referencing orphan SBs: {email_refs}")

# Check qb_quotes
quote_refs = 0
for i in range(0, min(len(orphan_ids), 1000), 200):
    batch = orphan_ids[i:i+200]
    try:
        resp = sb.table('qb_quotes').select('id', count='exact').in_('matched_company_id', batch).limit(1).execute()
        quote_refs += (resp.count or 0)
    except Exception:
        pass

print(f"  QB quotes referencing orphan SBs: {quote_refs}")

# ─── Decision ─────────────────────────────────────────────────────────────
print(f"\n{'='*100}")
print("DECISION GATE")
print(f"{'='*100}")
safe_to_delete = len(orphans)
if email_refs > 0:
    print(f"  WARNING: {email_refs} emails reference orphan SBs -- need CASCADE or nullify first")
if quote_refs > 0:
    print(f"  WARNING: {quote_refs} quotes reference orphan SBs -- need CASCADE or nullify first")
if email_refs == 0 and quote_refs == 0:
    print(f"  {safe_to_delete} orphan SB companies safe to delete (no FK references)")
else:
    print(f"  Need to nullify email + quote references before deleting orphans")
print(f"{'='*100}")
