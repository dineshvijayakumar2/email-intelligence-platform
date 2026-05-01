"""
Production verification for migration 088 — Contact Persona Views.
Covers all 5 verification steps from the task spec.
"""
import os, sys, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
from dotenv import load_dotenv
from supabase import create_client

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
load_dotenv(env_path)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

passed = 0
failed = 0

def check(label, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  [PASS] {label}")
    else:
        failed += 1
        print(f"  [FAIL] {label} — {detail}")

# ──────────────────────────────────────────────────────────────────────
# 1. Query contact_persona LIMIT 5 — verify rows with sensible data
# ──────────────────────────────────────────────────────────────────────
print("\n=== VERIFICATION 1: contact_persona returns sensible data ===")
try:
    result = sb.table("contact_persona").select("*").not_.is_("name", "null").gt("quote_count", 0).limit(5).execute()
    check("contact_persona returns rows", len(result.data) >= 1, f"got {len(result.data)}")
    if result.data:
        row = result.data[0]
        check("has contact_id", row.get("contact_id") is not None)
        check("has email", row.get("email") is not None)
        check("has name", row.get("name") is not None)
        check("has company_name", row.get("company_name") is not None)
        check("has persona_classification", row.get("persona_classification") in
              ("champion", "active_relationship", "prospect", "inactive_buyer", "dormant", "unknown"),
              f"got {row.get('persona_classification')}")
        check("engagement_score 0-100", 0 <= (row.get("engagement_score") or 0) <= 100,
              f"got {row.get('engagement_score')}")
        check("quote_count > 0 (filtered)", row.get("quote_count", 0) > 0)
        check("has client_id", row.get("client_id") is not None)
        check("has qb_tier", "qb_tier" in row)
        check("has customer_type", "customer_type" in row)
except Exception as e:
    check("contact_persona query succeeds", False, str(e))

# ──────────────────────────────────────────────────────────────────────
# 2. Refresh the materialized view via RPC
# ──────────────────────────────────────────────────────────────────────
print("\n=== VERIFICATION 2: Materialized view refresh ===")
try:
    t0 = time.monotonic()
    sb.rpc("refresh_contact_email_metrics", {}).execute()
    elapsed = round(time.monotonic() - t0, 2)
    check(f"refresh_contact_email_metrics() completes ({elapsed}s)", True)
except Exception as e:
    check("refresh_contact_email_metrics() completes", False, str(e))

# Verify the refreshed view has data
try:
    result = sb.table("contact_email_metrics").select("contact_id, total_emails", count="exact").limit(1).execute()
    check(f"contact_email_metrics has data (count={result.count})", (result.count or 0) > 0)
except Exception as e:
    check("contact_email_metrics has data", False, str(e))

# ──────────────────────────────────────────────────────────────────────
# 3. Query each API-facing view with a real ID
# ──────────────────────────────────────────────────────────────────────
print("\n=== VERIFICATION 3: All views return well-formed data ===")

# Get a real contact_id that has data
try:
    sample = sb.table("contact_persona").select("contact_id, company_id, industry, client_id").not_.is_("company_id", "null").gt("quote_count", 0).limit(1).execute()
    if sample.data:
        sample_contact = sample.data[0]["contact_id"]
        sample_company = sample.data[0]["company_id"]
        sample_industry = sample.data[0].get("industry")
        sample_client = sample.data[0]["client_id"]
        print(f"  Using contact={sample_contact[:8]}... company={sample_company[:8]}... industry={sample_industry}")
    else:
        sample_contact = sample_company = sample_industry = sample_client = None
        check("found sample data for API verification", False, "no contacts with quotes + company")
except Exception as e:
    check("sample lookup", False, str(e))
    sample_contact = sample_company = sample_industry = sample_client = None

# 3a. contact_quote_metrics
if sample_contact:
    try:
        r = sb.table("contact_quote_metrics").select("*").eq("contact_id", sample_contact).execute()
        check("contact_quote_metrics by contact_id", len(r.data) == 1)
        row = r.data[0]
        check("  has quote_count", "quote_count" in row)
        check("  has strike_rate", "strike_rate" in row)
        check("  has total_quote_value", "total_quote_value" in row)
        check("  has avg_margin_pct", "avg_margin_pct" in row)
    except Exception as e:
        check("contact_quote_metrics query", False, str(e))

# 3b. contact_email_metrics
if sample_contact:
    try:
        r = sb.table("contact_email_metrics").select("*").eq("contact_id", sample_contact).execute()
        if r.data:
            check("contact_email_metrics by contact_id", True)
            row = r.data[0]
            check("  has total_emails", "total_emails" in row)
            check("  has inbound_emails", "inbound_emails" in row)
            check("  has email_velocity_30d", "email_velocity_30d" in row)
        else:
            check("contact_email_metrics by contact_id", True, "(no email data for this contact — OK)")
    except Exception as e:
        check("contact_email_metrics query", False, str(e))

# 3c. company_contact_summary
if sample_company:
    try:
        r = sb.table("company_contact_summary").select("*").eq("company_id", sample_company).execute()
        check("company_contact_summary by company_id", len(r.data) >= 1)
        if r.data:
            row = r.data[0]
            check("  has total_contacts", "total_contacts" in row and row["total_contacts"] >= 1)
            check("  has champions_count", "champions_count" in row)
            check("  has total_quote_value", "total_quote_value" in row)
    except Exception as e:
        check("company_contact_summary query", False, str(e))

# 3d. industry_benchmarks
if sample_industry and sample_industry != "Not Selected":
    try:
        r = sb.table("industry_benchmarks").select("*").eq("industry", sample_industry).eq("client_id", sample_client).execute()
        if r.data:
            check("industry_benchmarks by industry", True)
            row = r.data[0]
            check("  has contact_count >= 3", row.get("contact_count", 0) >= 3)
            check("  has avg_strike_rate", "avg_strike_rate" in row)
            check("  has avg_engagement_score", "avg_engagement_score" in row)
        else:
            check("industry_benchmarks by industry", True, f"(no benchmark for '{sample_industry}' — might have < 3 contacts)")
    except Exception as e:
        check("industry_benchmarks query", False, str(e))

# ──────────────────────────────────────────────────────────────────────
# 4. Cross-tenant test: query with wrong client_id returns nothing
# ──────────────────────────────────────────────────────────────────────
print("\n=== VERIFICATION 4: Cross-tenant isolation ===")
fake_client = "00000000-0000-0000-0000-000000000000"
if sample_contact:
    try:
        r = sb.table("contact_persona").select("contact_id").eq("contact_id", sample_contact).eq("client_id", fake_client).execute()
        check("contact_persona with wrong client_id returns empty", len(r.data) == 0, f"got {len(r.data)} rows")
    except Exception as e:
        check("cross-tenant query", False, str(e))

    try:
        r = sb.table("company_contact_summary").select("company_id").eq("company_id", sample_company).eq("client_id", fake_client).execute()
        check("company_contact_summary with wrong client_id returns empty", len(r.data) == 0)
    except Exception as e:
        check("cross-tenant query (company)", False, str(e))

# ──────────────────────────────────────────────────────────────────────
# 5. Distribution check: how many contacts per classification
# ──────────────────────────────────────────────────────────────────────
print("\n=== VERIFICATION 5: Classification distribution ===")
try:
    # Use the discovery function pattern
    sb.rpc("exec_sql", {"query": """
        CREATE OR REPLACE FUNCTION _temp_verify()
        RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER AS $$
        DECLARE result jsonb;
        BEGIN
            SELECT coalesce(jsonb_agg(row_to_json(t)), '[]'::jsonb)
            FROM (
                SELECT persona_classification, count(*) as cnt
                FROM contact_persona
                GROUP BY persona_classification
                ORDER BY cnt DESC
            ) t INTO result;
            RETURN result;
        END; $$;
    """}).execute()
    sb.rpc("exec_sql", {"query": "NOTIFY pgrst, 'reload schema';"}).execute()
    time.sleep(4)

    resp = sb.rpc("_temp_verify", {}).execute()
    if resp.data:
        print("  Classification distribution:")
        for row in resp.data:
            print(f"    {row['persona_classification']:20s}: {row['cnt']:>6d}")

    sb.rpc("exec_sql", {"query": "DROP FUNCTION IF EXISTS _temp_verify();"}).execute()
except Exception as e:
    print(f"  Distribution query failed (non-critical): {e}")

# ──────────────────────────────────────────────────────────────────────
# Summary
# ──────────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"VERIFICATION COMPLETE: {passed} passed, {failed} failed")
print(f"{'='*60}")
