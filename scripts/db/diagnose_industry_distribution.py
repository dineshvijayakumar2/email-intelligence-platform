"""
Read-only investigation: industry value distribution in customer_companies.
Delete this file after review.
"""
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
from dotenv import load_dotenv
from supabase import create_client

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
load_dotenv(env_path)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

# --- Query 1: All industry values (including NULL / empty) ---
FUNC1 = "tmp_diag_industry_all"
create_sql_1 = f"""
CREATE OR REPLACE FUNCTION {FUNC1}()
RETURNS json
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT json_agg(row_to_json(t))
  FROM (
    SELECT industry, COUNT(*) as cnt
    FROM customer_companies
    GROUP BY industry
    ORDER BY cnt DESC
    LIMIT 30
  ) t;
$$
"""

# --- Query 2: Only meaningful industry values ---
FUNC2 = "tmp_diag_industry_meaningful"
create_sql_2 = f"""
CREATE OR REPLACE FUNCTION {FUNC2}()
RETURNS json
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT json_agg(row_to_json(t))
  FROM (
    SELECT industry, COUNT(*) as cnt
    FROM customer_companies
    WHERE industry IS NOT NULL
      AND industry != ''
      AND industry != 'Not Selected'
    GROUP BY industry
    ORDER BY cnt DESC
  ) t;
$$
"""

drop_sql_1 = f"DROP FUNCTION IF EXISTS {FUNC1}()"
drop_sql_2 = f"DROP FUNCTION IF EXISTS {FUNC2}()"

try:
    # Create both temp functions
    print("Creating temp function 1 (all industries)...")
    sb.rpc('exec_sql', {'query': create_sql_1}).execute()
    print("  [OK]")

    print("Creating temp function 2 (meaningful industries)...")
    sb.rpc('exec_sql', {'query': create_sql_2}).execute()
    print("  [OK]")

    # Reload schema so PostgREST sees the new functions
    print("Reloading schema cache...")
    sb.rpc('exec_sql', {'query': "NOTIFY pgrst, 'reload schema'"}).execute()
    print("  [OK]")

    # Small pause to let PostgREST pick up the new functions
    import time
    time.sleep(2)

    # Call function 1
    print("\n" + "=" * 70)
    print("QUERY 1: All industry values (top 30 by count)")
    print("=" * 70)
    result1 = sb.rpc(FUNC1).execute()
    rows1 = result1.data or []
    if rows1:
        print(f"{'Industry':<50} {'Count':>8}")
        print("-" * 60)
        for row in rows1:
            industry = row.get('industry')
            display = repr(industry) if industry is None or industry == '' else industry
            print(f"{display:<50} {row['cnt']:>8}")
        print("-" * 60)
        total = sum(r['cnt'] for r in rows1)
        print(f"{'TOTAL (shown)':<50} {total:>8}")
    else:
        print("  No results returned.")

    # Call function 2
    print("\n" + "=" * 70)
    print("QUERY 2: Meaningful industry values only (excl NULL, empty, 'Not Selected')")
    print("=" * 70)
    result2 = sb.rpc(FUNC2).execute()
    rows2 = result2.data or []
    if rows2:
        print(f"{'Industry':<50} {'Count':>8}")
        print("-" * 60)
        for row in rows2:
            print(f"{row['industry']:<50} {row['cnt']:>8}")
        print("-" * 60)
        total = sum(r['cnt'] for r in rows2)
        print(f"{'TOTAL (meaningful)':<50} {total:>8}")
    else:
        print("  No meaningful industry values found.")

finally:
    # Always clean up: drop temp functions
    print("\nCleaning up temp functions...")
    try:
        sb.rpc('exec_sql', {'query': drop_sql_1}).execute()
        print(f"  [OK] Dropped {FUNC1}")
    except Exception as e:
        print(f"  [WARN] Failed to drop {FUNC1}: {e}")
    try:
        sb.rpc('exec_sql', {'query': drop_sql_2}).execute()
        print(f"  [OK] Dropped {FUNC2}")
    except Exception as e:
        print(f"  [WARN] Failed to drop {FUNC2}: {e}")
    # Reload schema again after cleanup
    try:
        sb.rpc('exec_sql', {'query': "NOTIFY pgrst, 'reload schema'"}).execute()
        print("  [OK] Schema cache reloaded")
    except Exception as e:
        print(f"  [WARN] Failed to reload schema: {e}")

print("\nDone.")
