"""
Bulk merge case-variant duplicate companies.
Groups companies by LOWER(name), merges into the one with the most emails,
re-points QB links, moves contacts/emails, copies QB enrichment.

Usage:
  python bulk_merge_case_dupes.py          # dry run
  python bulk_merge_case_dupes.py --live   # execute
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
DRY_RUN = '--live' not in sys.argv

print("=" * 90)
print("DRY RUN" if DRY_RUN else "LIVE EXECUTION -- writing to database")
print("=" * 90)

# Fetch all companies
all_co = []
offset = 0
while True:
    r = sb.table('customer_companies').select(
        'id, company_name, total_emails, qb_customer_id, qb_match_method, '
        'qb_total_revenue, qb_customer_code, qb_invoiced_ty, qb_invoiced_ly, '
        'qb_growth_90d, qb_tier, qb_customer_type, qb_account_manager, qb_days_since_last_invoice'
    ).eq('client_id', CLIENT_ID).range(offset, offset + 999).execute()
    all_co.extend(r.data or [])
    if len(r.data or []) < 1000:
        break
    offset += 1000

print(f"Total companies: {len(all_co)}")

# Group by LOWER(name)
by_lower = defaultdict(list)
for c in all_co:
    name = (c.get('company_name') or '').strip().lower()
    if name:
        by_lower[name].append(c)

dupes = {k: v for k, v in by_lower.items() if len(v) > 1}
print(f"Case-variant duplicate groups: {len(dupes)}")

QB_ENRICH_FIELDS = [
    'qb_customer_id', 'qb_customer_code', 'qb_match_method', 'qb_total_revenue',
    'qb_invoiced_ty', 'qb_invoiced_ly', 'qb_growth_90d', 'qb_tier',
    'qb_customer_type', 'qb_account_manager', 'qb_days_since_last_invoice',
]

total_merged = 0
total_contacts_moved = 0
total_emails_moved = 0
total_qb_relinked = 0
errors = 0

for name, entries in sorted(dupes.items(), key=lambda x: -max(e.get('qb_total_revenue') or 0 for e in x[1])):
    # Pick keeper: most emails wins
    entries.sort(key=lambda c: c.get('total_emails') or 0, reverse=True)
    keeper = entries[0]
    losers = entries[1:]

    keeper_emails = keeper.get('total_emails') or 0
    loser_summary = ", ".join(
        f'"{e["company_name"]}" ({e.get("total_emails") or 0} emails)'
        for e in losers
    )

    print(f'\n  [{name}] Keep: "{keeper["company_name"]}" ({keeper_emails} emails)')
    print(f'    Merge: {loser_summary}')

    for loser in losers:
        loser_id = loser['id']
        keeper_id = keeper['id']

        # Find QB customers pointing to loser
        qb_rows = sb.table('qb_customers').select('id, qb_record_id, customer_name').eq(
            'client_id', CLIENT_ID
        ).eq('matched_company_id', loser_id).execute()
        qb_count = len(qb_rows.data or [])

        # Count contacts and emails on loser
        ct = sb.table('customer_contacts').select('id', count='exact').eq(
            'customer_company_id', loser_id
        ).limit(0).execute()
        em = sb.table('emails').select('id', count='exact').eq(
            'customer_company_id', loser_id
        ).limit(0).execute()
        contact_count = ct.count or 0
        email_count = em.count or 0

        if qb_count:
            print(f'    -> Re-link {qb_count} QB customers')
        if contact_count:
            print(f'    -> Move {contact_count} contacts')
        if email_count:
            print(f'    -> Move {email_count} emails')

        # Collect QB enrichment from loser (use if keeper has None)
        enrich_updates = {}
        for field in QB_ENRICH_FIELDS:
            if loser.get(field) is not None and keeper.get(field) is None:
                enrich_updates[field] = loser[field]
        # Special: prefer loser's revenue if keeper has no QB method
        if loser.get('qb_total_revenue') is not None and keeper.get('qb_match_method') is None and loser.get('qb_match_method'):
            for field in QB_ENRICH_FIELDS:
                if loser.get(field) is not None:
                    enrich_updates[field] = loser[field]

        if enrich_updates:
            print(f'    -> Copy QB enrichment: {list(enrich_updates.keys())}')

        if DRY_RUN:
            total_merged += 1
            total_qb_relinked += qb_count
            total_contacts_moved += contact_count
            total_emails_moved += email_count
            continue

        try:
            # Re-point QB customers
            if qb_count:
                for q in (qb_rows.data or []):
                    sb.table('qb_customers').update({
                        'matched_company_id': keeper_id
                    }).eq('id', q['id']).execute()

            # Move contacts
            if contact_count:
                sb.table('customer_contacts').update({
                    'customer_company_id': keeper_id
                }).eq('customer_company_id', loser_id).execute()

            # Move emails
            if email_count:
                sb.table('emails').update({
                    'customer_company_id': keeper_id
                }).eq('customer_company_id', loser_id).execute()

            # Copy QB enrichment
            if enrich_updates:
                sb.table('customer_companies').update(enrich_updates).eq('id', keeper_id).execute()

            # Delete loser
            sb.table('customer_companies').delete().eq('id', loser_id).execute()
            print(f'    [OK] Deleted "{loser["company_name"]}"')

            total_merged += 1
            total_qb_relinked += qb_count
            total_contacts_moved += contact_count
            total_emails_moved += email_count

        except Exception as e:
            print(f'    [ERROR] {e}')
            errors += 1

print(f'\n{"=" * 90}')
print(f'SUMMARY')
print(f'{"=" * 90}')
print(f'  Groups merged:     {total_merged}')
print(f'  QB customers relinked: {total_qb_relinked}')
print(f'  Contacts moved:    {total_contacts_moved}')
print(f'  Emails moved:      {total_emails_moved}')
print(f'  Errors:            {errors}')
if DRY_RUN:
    print(f'\n  --- DRY RUN: No changes made. Run with --live to execute. ---')
