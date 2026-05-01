"""
Add expression indexes to support the contact_quote_metrics view join.
The lower(email) join is slow without index support on 21K × 148K tables.
"""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
from dotenv import load_dotenv
from supabase import create_client

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
load_dotenv(env_path)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

indexes = [
    (
        "idx_qb_quotes_contact_email_lower",
        "CREATE INDEX IF NOT EXISTS idx_qb_quotes_contact_email_lower ON qb_quotes (lower(contact_email), client_id);"
    ),
    (
        "idx_customer_contacts_email_lower",
        "CREATE INDEX IF NOT EXISTS idx_customer_contacts_email_lower ON customer_contacts (lower(email_address), client_id);"
    ),
    (
        "idx_qb_jobs_quote_no_client",
        "CREATE INDEX IF NOT EXISTS idx_qb_jobs_quote_no_client ON qb_jobs (quote_no, client_id);"
    ),
]

for name, sql in indexes:
    print(f"Creating {name}...")
    try:
        sb.rpc("exec_sql_extended", {"p_query": sql, "p_timeout_s": 120}).execute()
        print(f"  [ok]")
    except Exception as e:
        print(f"  [FAIL] {e}")

# Verify the view works now
print("\nVerifying contact_quote_metrics...")
try:
    result = sb.table("contact_quote_metrics").select("*").limit(3).execute()
    print(f"  [ok] {len(result.data)} rows returned")
    for row in (result.data or [])[:3]:
        print(f"  contact_id={row.get('contact_id', '?')[:8]}... "
              f"quotes={row.get('quote_count', 0)} "
              f"strike={row.get('strike_rate', 'N/A')}")
except Exception as e:
    print(f"  [FAIL] {e}")

print("\nVerifying contact_persona (with quote data)...")
try:
    result = sb.table("contact_persona").select(
        "contact_id, name, persona_classification, engagement_score, "
        "quote_count, strike_rate, total_quote_value, email_total"
    ).gt("quote_count", 0).order("engagement_score", desc=True).limit(5).execute()
    if result.data:
        for row in result.data:
            sr = row.get('strike_rate')
            sr_str = f"{sr:.3f}" if sr is not None else "N/A"
            print(f"  {str(row.get('name', '?'))[:30]:30s} | "
                  f"{str(row.get('persona_classification', '?')):20s} | "
                  f"score={row.get('engagement_score', 0):3d} | "
                  f"quotes={row.get('quote_count', 0):4d} | "
                  f"strike={sr_str:>5s} | "
                  f"qval=${row.get('total_quote_value', 0):>10.2f} | "
                  f"emails={row.get('email_total', 0):5d}")
    else:
        print("  (no contacts with quotes)")
except Exception as e:
    print(f"  [FAIL] {e}")

print("\n[done]")
