"""
Diagnostic: why does Artis (51e72d07-e322-4fd6-8f51-5a6548a7d004) show 0 quotes/jobs
despite having $2.1M revenue on qb_customers?

Checks the join key mismatch hypothesis: customer_key_id vs qb_record_id in qb_quotes.
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

ARTIS_ID = "51e72d07-e322-4fd6-8f51-5a6548a7d004"
RAREID_ID = "68e9344b-1a43-4ef4-802f-7760877df4a9"

def check_company(name: str, company_id: str):
    print(f"\n{'='*60}")
    print(f"  {name} ({company_id})")
    print(f"{'='*60}")

    # 1. qb_customers record
    cust = sb.table('qb_customers').select(
        'qb_record_id, customer_key_id, customer_code, customer_name, total_invoiced, matched_company_id'
    ).eq('matched_company_id', company_id).execute()

    if not cust.data:
        print("  [!] No qb_customers matched to this company")
        return

    for c in cust.data:
        print(f"  qb_customers row:")
        print(f"    qb_record_id    = {c.get('qb_record_id')}")
        print(f"    customer_key_id = {c.get('customer_key_id')}")
        print(f"    customer_code   = {c.get('customer_code')}")
        print(f"    customer_name   = {c.get('customer_name')}")
        print(f"    total_invoiced  = {c.get('total_invoiced')}")

    key_ids = [c['customer_key_id'] for c in cust.data if c.get('customer_key_id')]
    record_ids = [c['qb_record_id'] for c in cust.data if c.get('qb_record_id')]

    print(f"\n  Join keys: customer_key_id={key_ids}, qb_record_id={record_ids}")
    print(f"  Match? {set(key_ids) == set(record_ids)}")

    # 2. Quotes by customer_key_id (current join path)
    if key_ids:
        q_by_key = sb.table('qb_quotes').select('qb_record_id', count='exact').in_(
            'qb_customer_id', key_ids
        ).execute()
        print(f"\n  qb_quotes WHERE qb_customer_id IN customer_key_ids: {q_by_key.count}")

    # 3. Quotes by qb_record_id (alternative join path)
    if record_ids:
        q_by_rec = sb.table('qb_quotes').select('qb_record_id', count='exact').in_(
            'qb_customer_id', record_ids
        ).execute()
        print(f"  qb_quotes WHERE qb_customer_id IN qb_record_ids:    {q_by_rec.count}")

    # 4. Sample qb_customer_id values from quotes to see format
    if key_ids:
        sample = sb.table('qb_quotes').select(
            'qb_customer_id, quote_no'
        ).limit(3).execute()
        if sample.data:
            print(f"\n  Sample qb_quotes.qb_customer_id values (first 3 rows):")
            for s in sample.data:
                print(f"    qb_customer_id={s.get('qb_customer_id')!r}  quote_no={s.get('quote_no')}")

    # 5. Operations matched to company
    ops = sb.table('qb_operations').select('id', count='exact').eq(
        'matched_company_id', company_id
    ).execute()
    print(f"\n  qb_operations matched to company: {ops.count}")

    # 6. Operations by qb_customer_id (via key_id)
    if key_ids:
        ops_by_key = sb.table('qb_operations').select('id', count='exact').in_(
            'qb_customer_id', key_ids
        ).execute()
        print(f"  qb_operations WHERE qb_customer_id IN customer_key_ids: {ops_by_key.count}")

    if record_ids and set(key_ids) != set(record_ids):
        ops_by_rec = sb.table('qb_operations').select('id', count='exact').in_(
            'qb_customer_id', record_ids
        ).execute()
        print(f"  qb_operations WHERE qb_customer_id IN qb_record_ids:    {ops_by_rec.count}")


check_company("Rareid (works)", RAREID_ID)
check_company("Artis (broken)", ARTIS_ID)

print("\n\nDone!")
