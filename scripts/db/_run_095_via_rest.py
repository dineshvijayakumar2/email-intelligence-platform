"""
Throwaway migration runner for 095_cleanup_internal_contact_qb_tier.sql
Tags internal/shared contacts and NULLs incorrectly propagated QB data.
"""
import os, sys, time, re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
from dotenv import load_dotenv
from supabase import create_client

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
load_dotenv(env_path)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

with open(os.path.join(os.path.dirname(__file__), '..', 'migrations', '095_cleanup_internal_contact_qb_tier.sql'), 'r', encoding='utf-8') as f:
    raw_sql = f.read()

stripped = re.sub(r'^\s*BEGIN\s*;\s*$', '', raw_sql, flags=re.MULTILINE | re.IGNORECASE)
stripped = re.sub(r'^\s*COMMIT\s*;\s*$', '', stripped, flags=re.MULTILINE | re.IGNORECASE)

# Pre-flight: count contacts that will be affected
print("[1/5] Pre-flight counts...")
try:
    internal_count = sb.rpc("exec_sql", {"query": """
        SELECT COUNT(*) as cnt FROM customer_contacts cc
        JOIN internal_domains id ON SPLIT_PART(cc.email_address, '@', 2) = id.domain
            AND cc.client_id = id.client_id
        WHERE COALESCE(cc.contact_type, 'person') = 'person';
    """}).execute()
    print(f"  Contacts at internal domains to be tagged 'internal': {(internal_count.data or [{}])[0].get('cnt', '?')}")

    shared_count = sb.rpc("exec_sql", {"query": """
        SELECT COUNT(*) as cnt FROM customer_contacts
        WHERE COALESCE(contact_type, 'person') = 'person'
        AND (
            email_address ~* '^(info|contact|hello|sales|support|help|admin|office|team|service)@'
            OR email_address ~* '^(inquiries|feedback|billing|careers|jobs|hr|press|media|marketing)@'
            OR email_address ~* '^(webmaster|postmaster|accounts|noreply|no-reply|no\\.reply)@'
            OR email_address ~* '^(donotreply|do-not-reply|form-submission|notifications?)@'
            OR email_address ~* '^(alerts?|mailer-daemon|bounce|receipts?|orders?|invoices?)@'
            OR email_address ~* '^(enquiry|enquiries)@'
        );
    """}).execute()
    print(f"  Contacts matching shared patterns to be tagged 'shared': {(shared_count.data or [{}])[0].get('cnt', '?')}")

    bad_tier = sb.rpc("exec_sql", {"query": """
        SELECT COUNT(*) as cnt FROM customer_contacts cc
        JOIN internal_domains id ON SPLIT_PART(cc.email_address, '@', 2) = id.domain
            AND cc.client_id = id.client_id
        WHERE cc.qb_tier IS NOT NULL;
    """}).execute()
    print(f"  Internal contacts with QB tier to be cleared: {(bad_tier.data or [{}])[0].get('cnt', '?')}")
except Exception as e:
    print(f"  [WARN] Pre-flight failed: {e}")

print("\n[2/5] Applying migration 095...")
try:
    try:
        sb.rpc("exec_sql_extended", {"p_query": stripped, "p_timeout_s": 120}).execute()
    except Exception:
        sb.rpc("exec_sql", {"query": stripped}).execute()
    print("  [ok] Migration applied")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print("[3/5] Post-flight verification...")
try:
    # Zero internal contacts with QB tier
    check1 = sb.rpc("exec_sql", {"query": """
        SELECT COUNT(*) as cnt FROM customer_contacts cc
        JOIN internal_domains id ON SPLIT_PART(cc.email_address, '@', 2) = id.domain
            AND cc.client_id = id.client_id
        WHERE cc.qb_tier IS NOT NULL;
    """}).execute()
    cnt1 = (check1.data or [{}])[0].get("cnt", -1)
    if cnt1 == 0:
        print(f"  [ok] Zero internal contacts with QB tier")
    else:
        print(f"  [WARN] {cnt1} internal contacts still have QB tier")

    # Zero shared contacts with QB tier
    check2 = sb.rpc("exec_sql", {"query": """
        SELECT COUNT(*) as cnt FROM customer_contacts
        WHERE contact_type IN ('shared', 'automated', 'mailing_list')
        AND qb_tier IS NOT NULL;
    """}).execute()
    cnt2 = (check2.data or [{}])[0].get("cnt", -1)
    if cnt2 == 0:
        print(f"  [ok] Zero shared/automated contacts with QB tier")
    else:
        print(f"  [WARN] {cnt2} shared/automated contacts still have QB tier")
except Exception as e:
    print(f"  [WARN] Post-flight failed: {e}")

print("[4/5] Contact type distribution...")
try:
    dist = sb.rpc("exec_sql", {"query": """
        SELECT contact_type, COUNT(*) as cnt
        FROM customer_contacts
        GROUP BY contact_type
        ORDER BY cnt DESC;
    """}).execute()
    for row in (dist.data or []):
        print(f"  {row.get('contact_type', 'NULL'):20s} {row.get('cnt', 0):>6}")
except Exception as e:
    print(f"  [WARN] {e}")

print("[5/5] Spot-check Carbon8 internal contacts...")
try:
    spots = sb.rpc("exec_sql", {"query": """
        SELECT cc.email_address, cc.contact_type, cc.qb_tier, cc.qb_customer_type
        FROM customer_contacts cc
        JOIN internal_domains id ON SPLIT_PART(cc.email_address, '@', 2) = id.domain
            AND cc.client_id = id.client_id
        LIMIT 10;
    """}).execute()
    for row in (spots.data or []):
        print(f"  {row.get('email_address', '?'):40s} type={row.get('contact_type', '?'):10s} "
              f"tier={row.get('qb_tier', 'NULL')}")
except Exception as e:
    print(f"  [WARN] {e}")

print("\n=== Migration 095 complete ===")
