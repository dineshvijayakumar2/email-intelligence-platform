"""
Apply migration 096 via exec_sql RPC. Delete after verified.

Runs steps separately to avoid statement_timeout on bulk UPDATEs:
  1. ADD COLUMN (instant, IF NOT EXISTS)
  2. DROP HNSW indexes (fast)
  3. NULL out stale embeddings per table (bulk, but fast without HNSW)
  4. CREATE partial indexes on embedding_model
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


def run(label, sql, timeout_s=60):
    t0 = time.time()
    print(f"  {label}...", end="", flush=True)
    try:
        try:
            sb.rpc("exec_sql_extended", {"p_query": sql, "p_timeout_s": timeout_s}).execute()
        except Exception:
            sb.rpc("exec_sql", {"query": sql}).execute()
        print(f" OK ({time.time() - t0:.1f}s)")
    except Exception as e:
        print(f" FAILED: {e}")
        sys.exit(1)


print("[1/4] Add audit columns")
run("emails",             "ALTER TABLE emails ADD COLUMN IF NOT EXISTS embedding_model TEXT, ADD COLUMN IF NOT EXISTS embedded_at TIMESTAMPTZ")
run("qb_operations",      "ALTER TABLE qb_operations ADD COLUMN IF NOT EXISTS embedding_model TEXT, ADD COLUMN IF NOT EXISTS embedded_at TIMESTAMPTZ")
run("customer_companies", "ALTER TABLE customer_companies ADD COLUMN IF NOT EXISTS embedding_model TEXT, ADD COLUMN IF NOT EXISTS embedded_at TIMESTAMPTZ")

print("\n[2/4] Drop HNSW indexes")
run("idx_emails_embedding",        "DROP INDEX IF EXISTS idx_emails_embedding")
run("idx_qb_operations_embedding", "DROP INDEX IF EXISTS idx_qb_operations_embedding")
run("idx_companies_embedding",     "DROP INDEX IF EXISTS idx_companies_embedding")

print("\n[3/4] Null out stale embeddings (no audit trail)")
run("emails (257K rows)",     "UPDATE emails SET embedding = NULL WHERE embedding IS NOT NULL AND embedding_model IS NULL", timeout_s=120)
run("qb_operations (6.8K)",   "UPDATE qb_operations SET embedding = NULL WHERE embedding IS NOT NULL AND embedding_model IS NULL")
run("customer_companies (1K)", "UPDATE customer_companies SET embedding = NULL WHERE embedding IS NOT NULL AND embedding_model IS NULL")

print("\n[4/4] Create partial indexes on embedding_model")
run("idx_emails_embedding_model",             "CREATE INDEX IF NOT EXISTS idx_emails_embedding_model ON emails (embedding_model) WHERE embedding IS NOT NULL")
run("idx_qb_operations_embedding_model",      "CREATE INDEX IF NOT EXISTS idx_qb_operations_embedding_model ON qb_operations (embedding_model) WHERE embedding IS NOT NULL")
run("idx_customer_companies_embedding_model", "CREATE INDEX IF NOT EXISTS idx_customer_companies_embedding_model ON customer_companies (embedding_model) WHERE embedding IS NOT NULL")

# Schema reload
sb.rpc("exec_sql", {"query": "NOTIFY pgrst, 'reload schema';"}).execute()
time.sleep(3)

# Verification
print("\n=== Verification ===")
tables = ["emails", "qb_operations", "customer_companies"]
for tbl in tables:
    try:
        r = sb.table(tbl).select("embedding_model, embedded_at").limit(1).execute()
        print(f"  [ok] {tbl}: columns accessible")
    except Exception as e:
        print(f"  [FAIL] {tbl}: {e}")

print("\n[info] Post-migration baseline:")
for tbl in tables:
    total = sb.table(tbl).select("id", count="exact").limit(1).execute()
    has_emb = sb.table(tbl).select("id", count="exact").not_.is_("embedding", "null").limit(1).execute()
    stale = sb.table(tbl).select("id", count="exact").not_.is_("embedding", "null").is_("embedding_model", "null").limit(1).execute()
    print(f"  {tbl:25s} total={total.count:>7}  with_embedding={has_emb.count:>7}  stale(no model)={stale.count:>7}")

print("\n=== Migration 096 complete ===")
