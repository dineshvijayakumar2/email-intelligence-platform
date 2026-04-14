"""
Index Registry Reconciliation — compare BulkIndexManager registry vs production.

Detects drift between the index definitions registered in
backend/src/database/bulk_index_manager.py and the actual indexes that exist
on the production database.

Outputs four categories per table:
  - HEALTHY: index in registry AND in prod, valid
  - MISSING: index in registry but NOT in prod (e.g., never created, or dropped ad-hoc)
  - ORPHAN: index in prod but NOT in registry (e.g., created via SQL console)
  - INVALID: index in prod but pg_index.indisvalid = false (failed build, partial state)

Usage:
    cd backend
    python -m scripts.db.index_registry_reconcile

    # Or from project root:
    python scripts/db/index_registry_reconcile.py

Requires env vars:
    DATABASE_URL  — full postgres connection string (e.g. postgresql://user:pass@host/db)
                    Falls back to building from SUPABASE_DB_URL or SUPABASE_URL + SUPABASE_DB_PASSWORD

Read-only — performs no writes. Safe to run in production.
"""
import os
import sys
import logging
from pathlib import Path
from collections import defaultdict
from typing import Optional

import psycopg2
import psycopg2.extras

# Make the BulkIndexManager registry importable regardless of cwd
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "backend"))

from src.database.bulk_index_manager import INDEX_REGISTRY  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("reconcile")


def _load_dotenv_files():
    """Auto-load .env files from common locations. Existing env vars take precedence."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    candidates = [
        _PROJECT_ROOT / "backend" / ".env.production",
        _PROJECT_ROOT / "backend" / ".env",
        _PROJECT_ROOT / ".env.production",
        _PROJECT_ROOT / ".env",
    ]
    for path in candidates:
        if path.exists():
            load_dotenv(path, override=False)
            log.info(f"Loaded env from {path.relative_to(_PROJECT_ROOT)}")


def get_database_url() -> Optional[str]:
    """Resolve the postgres connection string from env vars.

    Looks for DATABASE_URL or SUPABASE_DB_URL. Get the value from
    Supabase Dashboard → Project Settings → Database → Connection string (URI tab).
    Use the Direct connection string (port 5432), NOT the transaction pooler.
    """
    return os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL")


def fetch_prod_indexes(conn, tables: list[str]) -> dict[str, dict]:
    """Return {table_name: {index_name: {valid: bool, definition: str, size_bytes: int}}}.

    Queries pg_indexes (definitions) joined with pg_index (validity) and
    pg_class (sizes). Read-only.
    """
    sql = """
        SELECT
            t.relname     AS table_name,
            i.relname     AS index_name,
            ix.indisvalid AS is_valid,
            pg_indexes.indexdef AS definition,
            pg_relation_size(i.oid) AS size_bytes
        FROM pg_class t
        JOIN pg_index ix      ON ix.indrelid = t.oid
        JOIN pg_class i       ON i.oid = ix.indexrelid
        JOIN pg_indexes       ON pg_indexes.indexname = i.relname
                              AND pg_indexes.tablename = t.relname
        WHERE t.relkind = 'r'
          AND t.relname = ANY(%s)
        ORDER BY t.relname, i.relname;
    """
    out: dict[str, dict] = defaultdict(dict)
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (tables,))
        for row in cur.fetchall():
            out[row["table_name"]][row["index_name"]] = {
                "valid": row["is_valid"],
                "definition": row["definition"],
                "size_bytes": row["size_bytes"],
            }
    return dict(out)


def pretty_size(n_bytes: int) -> str:
    for unit in ["B", "kB", "MB", "GB"]:
        if n_bytes < 1024:
            return f"{n_bytes:.1f} {unit}"
        n_bytes /= 1024.0
    return f"{n_bytes:.1f} TB"


def reconcile(conn) -> dict:
    """Compare INDEX_REGISTRY against live database. Returns structured report."""
    tables = list(INDEX_REGISTRY.keys())
    prod = fetch_prod_indexes(conn, tables)

    report = {"healthy": [], "missing": [], "orphan": [], "invalid": []}

    for table, registry_entries in INDEX_REGISTRY.items():
        registry_names = {e.name for e in registry_entries}
        prod_names = set(prod.get(table, {}).keys())

        for entry in registry_entries:
            prod_info = prod.get(table, {}).get(entry.name)
            if prod_info is None:
                report["missing"].append({
                    "table": table,
                    "index": entry.name,
                    "type": entry.index_type,
                    "create_sql": entry.create_sql,
                })
            else:
                if not prod_info["valid"]:
                    report["invalid"].append({
                        "table": table,
                        "index": entry.name,
                        "definition": prod_info["definition"],
                        "size": pretty_size(prod_info["size_bytes"]),
                    })
                else:
                    report["healthy"].append({
                        "table": table,
                        "index": entry.name,
                        "size": pretty_size(prod_info["size_bytes"]),
                    })

        for prod_name in prod_names - registry_names:
            prod_info = prod[table][prod_name]
            is_pk_or_unique = (
                prod_name.endswith("_pkey")
                or "unique" in prod_name.lower()
                or "UNIQUE" in prod_info["definition"]
            )
            if is_pk_or_unique:
                continue
            report["orphan"].append({
                "table": table,
                "index": prod_name,
                "definition": prod_info["definition"],
                "size": pretty_size(prod_info["size_bytes"]),
                "valid": prod_info["valid"],
            })

    return report


def render_markdown(report: dict) -> str:
    out = ["# Index Registry Reconciliation Report\n"]
    out.append(
        f"**Summary:** "
        f"{len(report['healthy'])} healthy, "
        f"{len(report['missing'])} missing, "
        f"{len(report['orphan'])} orphan, "
        f"{len(report['invalid'])} invalid\n"
    )

    if report["invalid"]:
        out.append("## ACTION_REQUIRED — Invalid Indexes\n")
        out.append("These exist in production but `pg_index.indisvalid = false` — likely "
                   "the result of a failed/interrupted CREATE INDEX. Drop and rebuild.\n")
        out.append("| Table | Index | Size | Definition |")
        out.append("|-------|-------|------|------------|")
        for r in report["invalid"]:
            out.append(f"| {r['table']} | `{r['index']}` | {r['size']} | `{r['definition']}` |")
        out.append("")

    if report["missing"]:
        out.append("## WARN — Missing in Production\n")
        out.append("Registered in `BulkIndexManager` but not present in the database. "
                   "If `BulkIndexManager` runs, it will attempt to drop these (no-op) and recreate them.\n")
        out.append("| Table | Index | Type | CREATE SQL |")
        out.append("|-------|-------|------|------------|")
        for r in report["missing"]:
            out.append(f"| {r['table']} | `{r['index']}` | {r['type']} | `{r['create_sql']}` |")
        out.append("")

    if report["orphan"]:
        out.append("## INFO — Orphan Indexes (in production, not in registry)\n")
        out.append("These exist in the database but are not tracked by `BulkIndexManager`. "
                   "Likely created via SQL console, ad-hoc migration, or migration not yet "
                   "reflected in the registry. PK/UNIQUE indexes are excluded automatically.\n")
        out.append("| Table | Index | Size | Valid | Definition |")
        out.append("|-------|-------|------|-------|------------|")
        for r in report["orphan"]:
            valid_mark = "yes" if r["valid"] else "**NO**"
            out.append(
                f"| {r['table']} | `{r['index']}` | {r['size']} | {valid_mark} | "
                f"`{r['definition']}` |"
            )
        out.append("")

    if report["healthy"]:
        out.append("## OK — Healthy Indexes\n")
        out.append(f"{len(report['healthy'])} indexes match registry and are valid in production.\n")
        out.append("<details><summary>Show list</summary>\n")
        out.append("| Table | Index | Size |")
        out.append("|-------|-------|------|")
        for r in report["healthy"]:
            out.append(f"| {r['table']} | `{r['index']}` | {r['size']} |")
        out.append("\n</details>\n")

    return "\n".join(out)


def main():
    _load_dotenv_files()
    db_url = get_database_url()
    if not db_url:
        log.error(
            "ERROR: No database connection string found. Either:\n"
            "  1. Add DATABASE_URL=postgresql://... to backend/.env.production, OR\n"
            "  2. Set DATABASE_URL environment variable directly.\n"
            "\n"
            "Get the connection string from:\n"
            "  Supabase Dashboard -> Project Settings -> Database -> Connection string\n"
            "  Use 'URI' tab, 'Direct connection' mode (port 5432, NOT pooler)."
        )
        sys.exit(2)

    log.info("Connecting to database...")
    try:
        conn = psycopg2.connect(db_url, application_name="index_registry_reconcile")
    except Exception as e:
        log.error(f"Connection failed: {e}")
        sys.exit(1)

    try:
        log.info(f"Reconciling {len(INDEX_REGISTRY)} tables from BulkIndexManager registry...")
        report = reconcile(conn)
        markdown = render_markdown(report)
        print(markdown)

        any_action = bool(report["invalid"] or report["missing"] or report["orphan"])
        sys.exit(1 if any_action else 0)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
