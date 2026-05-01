"""
Apply migration 097 via exec_sql RPC. Delete after verified.

Steps:
  1. Update 3 existing batch_update_embeddings RPCs (add audit col params)
  2. Add embedding + audit columns to qb_quotes
  3. Create batch_update_embeddings_quotes RPC
  4. Grant permissions
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


print("[1/4] Update existing RPCs with audit column params")

run("batch_update_embeddings_emails", """
CREATE OR REPLACE FUNCTION batch_update_embeddings_emails(
    p_ids uuid[], p_embeddings vector(768)[],
    p_embedding_model text DEFAULT NULL, p_embedded_at timestamptz DEFAULT NULL
) RETURNS integer LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public SET statement_timeout = '30s' AS $$
DECLARE updated integer;
BEGIN
    PERFORM set_config('statement_timeout', '30000', true);
    UPDATE emails e SET embedding = u.emb,
        embedding_model = COALESCE(p_embedding_model, e.embedding_model),
        embedded_at = COALESCE(p_embedded_at, e.embedded_at)
    FROM unnest(p_ids, p_embeddings) AS u(id, emb) WHERE e.id = u.id;
    GET DIAGNOSTICS updated = ROW_COUNT; RETURN updated;
END; $$;
""")

run("batch_update_embeddings_companies", """
CREATE OR REPLACE FUNCTION batch_update_embeddings_companies(
    p_ids uuid[], p_embeddings vector(768)[],
    p_embedding_model text DEFAULT NULL, p_embedded_at timestamptz DEFAULT NULL
) RETURNS integer LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public SET statement_timeout = '30s' AS $$
DECLARE updated integer;
BEGIN
    PERFORM set_config('statement_timeout', '30000', true);
    UPDATE customer_companies c SET embedding = u.emb,
        embedding_model = COALESCE(p_embedding_model, c.embedding_model),
        embedded_at = COALESCE(p_embedded_at, c.embedded_at)
    FROM unnest(p_ids, p_embeddings) AS u(id, emb) WHERE c.id = u.id;
    GET DIAGNOSTICS updated = ROW_COUNT; RETURN updated;
END; $$;
""")

run("batch_update_embeddings_operations", """
CREATE OR REPLACE FUNCTION batch_update_embeddings_operations(
    p_ids uuid[], p_embeddings vector(768)[],
    p_embedding_model text DEFAULT NULL, p_embedded_at timestamptz DEFAULT NULL
) RETURNS integer LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public SET statement_timeout = '30s' AS $$
DECLARE updated integer;
BEGIN
    PERFORM set_config('statement_timeout', '30000', true);
    UPDATE qb_operations o SET embedding = u.emb,
        embedding_model = COALESCE(p_embedding_model, o.embedding_model),
        embedded_at = COALESCE(p_embedded_at, o.embedded_at)
    FROM unnest(p_ids, p_embeddings) AS u(id, emb) WHERE o.id = u.id;
    GET DIAGNOSTICS updated = ROW_COUNT; RETURN updated;
END; $$;
""")

print("\n[2/4] Add embedding + audit columns to qb_quotes")
run("qb_quotes columns", "ALTER TABLE qb_quotes ADD COLUMN IF NOT EXISTS embedding vector(768), ADD COLUMN IF NOT EXISTS embedding_model TEXT, ADD COLUMN IF NOT EXISTS embedded_at TIMESTAMPTZ")
run("qb_quotes index", "CREATE INDEX IF NOT EXISTS idx_qb_quotes_embedding_model ON qb_quotes (embedding_model) WHERE embedding IS NOT NULL")

print("\n[3/4] Create batch_update_embeddings_quotes RPC")
run("batch_update_embeddings_quotes", """
CREATE OR REPLACE FUNCTION batch_update_embeddings_quotes(
    p_ids uuid[], p_embeddings vector(768)[],
    p_embedding_model text DEFAULT NULL, p_embedded_at timestamptz DEFAULT NULL
) RETURNS integer LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public SET statement_timeout = '30s' AS $$
DECLARE updated integer;
BEGIN
    PERFORM set_config('statement_timeout', '30000', true);
    UPDATE qb_quotes q SET embedding = u.emb,
        embedding_model = COALESCE(p_embedding_model, q.embedding_model),
        embedded_at = COALESCE(p_embedded_at, q.embedded_at)
    FROM unnest(p_ids, p_embeddings) AS u(id, emb) WHERE q.id = u.id;
    GET DIAGNOSTICS updated = ROW_COUNT; RETURN updated;
END; $$;
""")

print("\n[4/4] Grants")
run("emails grant", "GRANT EXECUTE ON FUNCTION batch_update_embeddings_emails(uuid[], vector(768)[], text, timestamptz) TO anon, authenticated")
run("companies grant", "GRANT EXECUTE ON FUNCTION batch_update_embeddings_companies(uuid[], vector(768)[], text, timestamptz) TO anon, authenticated")
run("operations grant", "GRANT EXECUTE ON FUNCTION batch_update_embeddings_operations(uuid[], vector(768)[], text, timestamptz) TO anon, authenticated")
run("quotes grant", "GRANT EXECUTE ON FUNCTION batch_update_embeddings_quotes(uuid[], vector(768)[], text, timestamptz) TO anon, authenticated")

# Schema reload
sb.rpc("exec_sql", {"query": "NOTIFY pgrst, 'reload schema';"}).execute()
time.sleep(3)

# Verification
print("\n=== Verification ===")
tables = ["emails", "qb_operations", "customer_companies", "qb_quotes"]
for tbl in tables:
    try:
        r = sb.table(tbl).select("embedding_model, embedded_at").limit(1).execute()
        print(f"  [ok] {tbl}: audit columns accessible")
    except Exception as e:
        print(f"  [FAIL] {tbl}: {e}")

# Test RPC signature (empty call)
rpcs = [
    "batch_update_embeddings_emails",
    "batch_update_embeddings_companies",
    "batch_update_embeddings_operations",
    "batch_update_embeddings_quotes",
]
for rpc_name in rpcs:
    try:
        sb.rpc(rpc_name, {
            "p_ids": [],
            "p_embeddings": [],
            "p_embedding_model": "test",
            "p_embedded_at": "2026-01-01T00:00:00Z",
        }).execute()
        print(f"  [ok] {rpc_name}: accepts audit params")
    except Exception as e:
        print(f"  [FAIL] {rpc_name}: {e}")

print("\n=== Migration 097 complete ===")
