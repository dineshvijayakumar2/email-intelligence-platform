"""
One-off: Merge duplicate HH Global companies.
"Hhglobal" (2157 emails, 23 contacts) keeps the data.
"HH Global" (0 emails, 0 contacts) has the correct QB revenue link.
Action: re-point the QB link to the company with actual data, delete the empty one.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
from dotenv import load_dotenv
from supabase import create_client

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
load_dotenv(env_path)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
CLIENT_ID = "241d7b99-f099-4557-96e5-212c4af10812"

DRY_RUN = '--live' not in sys.argv

print("=" * 80)
print("DRY RUN" if DRY_RUN else "LIVE EXECUTION")
print("=" * 80)

# Find both companies
resp = sb.table('customer_companies').select(
    'id, company_name, total_emails, qb_customer_id, qb_match_method, qb_total_revenue, qb_customer_code'
).eq('client_id', CLIENT_ID).ilike('company_name', '%hh%global%').execute()

companies = resp.data or []
print(f"\nFound {len(companies)} companies matching 'hh*global':")
for c in companies:
    print(f"  {c['company_name']:30s} id={c['id']}  emails={c.get('total_emails', 0)}  "
          f"qb_revenue={c.get('qb_total_revenue')}  qb_method={c.get('qb_match_method')}")

if len(companies) != 2:
    print(f"\nExpected 2 companies, found {len(companies)}. Aborting.")
    sys.exit(1)

# Identify keeper (has emails) and empty (no emails)
keeper = max(companies, key=lambda c: c.get('total_emails') or 0)
empty = min(companies, key=lambda c: c.get('total_emails') or 0)

print(f"\nKeeper: {keeper['company_name']} (id={keeper['id']}, emails={keeper.get('total_emails', 0)})")
print(f"Empty:  {empty['company_name']} (id={empty['id']}, emails={empty.get('total_emails', 0)})")

# Find QB customers pointing to either company
qb_to_keeper = sb.table('qb_customers').select('id, qb_record_id, customer_name, total_invoiced').eq(
    'client_id', CLIENT_ID
).eq('matched_company_id', keeper['id']).execute()
qb_to_empty = sb.table('qb_customers').select('id, qb_record_id, customer_name, total_invoiced').eq(
    'client_id', CLIENT_ID
).eq('matched_company_id', empty['id']).execute()

print(f"\nQB customers pointing to keeper ({keeper['company_name']}):")
for q in (qb_to_keeper.data or []):
    print(f"  {q['customer_name']:40s} revenue={q.get('total_invoiced')}")

print(f"\nQB customers pointing to empty ({empty['company_name']}):")
for q in (qb_to_empty.data or []):
    print(f"  {q['customer_name']:40s} revenue={q.get('total_invoiced')}")

# Check contacts and emails on the empty company
contacts_on_empty = sb.table('customer_contacts').select('id', count='exact').eq(
    'customer_company_id', empty['id']
).limit(0).execute()
emails_on_empty = sb.table('emails').select('id', count='exact').eq(
    'customer_company_id', empty['id']
).limit(0).execute()

print(f"\nEmpty company has {contacts_on_empty.count} contacts and {emails_on_empty.count} emails in DB")

if DRY_RUN:
    print("\n--- DRY RUN: No changes made. Run with --live to execute. ---")
    sys.exit(0)

print("\n" + "=" * 80)
print("EXECUTING MERGE")
print("=" * 80)

# Step 1: Re-point QB customers from empty -> keeper
for q in (qb_to_empty.data or []):
    print(f"  Re-linking QB '{q['customer_name']}' -> keeper {keeper['company_name']}")
    sb.table('qb_customers').update({
        'matched_company_id': keeper['id']
    }).eq('id', q['id']).execute()

# Step 2: Move any contacts/emails from empty -> keeper (should be 0 but be safe)
if contacts_on_empty.count > 0:
    print(f"  Moving {contacts_on_empty.count} contacts to keeper")
    sb.table('customer_contacts').update({
        'customer_company_id': keeper['id']
    }).eq('customer_company_id', empty['id']).execute()

if emails_on_empty.count > 0:
    print(f"  Moving {emails_on_empty.count} emails to keeper")
    sb.table('emails').update({
        'customer_company_id': keeper['id']
    }).eq('customer_company_id', empty['id']).execute()

# Step 3: Copy QB enrichment from empty to keeper
enrich = {}
for field in ['qb_customer_id', 'qb_customer_code', 'qb_match_method', 'qb_total_revenue',
              'qb_invoiced_ty', 'qb_invoiced_ly', 'qb_growth_90d', 'qb_tier',
              'qb_customer_type', 'qb_account_manager', 'qb_days_since_last_invoice']:
    val = empty.get(field)
    if val is not None:
        enrich[field] = val
if enrich:
    print(f"  Copying QB enrichment to keeper: {list(enrich.keys())}")
    sb.table('customer_companies').update(enrich).eq('id', keeper['id']).execute()

# Step 4: Rename keeper to the QB customer name (proper casing)
proper_name = None
for q in (qb_to_empty.data or []) + (qb_to_keeper.data or []):
    if q.get('customer_name'):
        proper_name = q['customer_name']
        break
if proper_name and proper_name != keeper['company_name']:
    print(f"  Renaming keeper: '{keeper['company_name']}' -> '{proper_name}'")
    sb.table('customer_companies').update({
        'company_name': proper_name
    }).eq('id', keeper['id']).execute()

# Step 5: Delete the empty company
print(f"  Deleting empty company: {empty['company_name']} (id={empty['id']})")
sb.table('customer_companies').delete().eq('id', empty['id']).execute()

print("\nMerge complete!")
