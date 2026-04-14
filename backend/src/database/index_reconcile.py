"""
Startup-time index drift check.

On FastAPI boot, compares BulkIndexManager.INDEX_REGISTRY against the actual
indexes in production. Logs WARN for missing/invalid/orphan drift, INFO if
clean. Intended as an early-warning signal — doesn't block startup, doesn't
auto-fix anything.

Why this exists: on 2026-04-13 a BulkIndexManager silent-fallback bug dropped
the HNSW index on emails and the platform ran for hours with degraded vector
search before the 16h-of-slow-queries dashboard made it visible. A 2-second
startup check would have surfaced the INVALID index immediately.

The standalone CLI at scripts/db/index_registry_reconcile.py has richer output
(full report + sizes). This module is the lightweight always-on version.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Optional

logger = logging.getLogger(__name__)


def _fetch_prod_indexes_sync(conn, tables: list[str]) -> dict[str, dict]:
    """Query pg_indexes + pg_index for each table. Returns {table: {index: info}}.
    Runs synchronously — caller is expected to to_thread this.
    """
    out: dict[str, dict] = defaultdict(dict)
    sql = """
        SELECT
            t.relname AS table_name,
            i.relname AS index_name,
            ix.indisvalid AS is_valid,
            pg_indexes.indexdef AS definition
        FROM pg_class t
        JOIN pg_index ix      ON ix.indrelid = t.oid
        JOIN pg_class i       ON i.oid = ix.indexrelid
        JOIN pg_indexes       ON pg_indexes.indexname = i.relname
                              AND pg_indexes.tablename = t.relname
        WHERE t.relkind = 'r'
          AND t.relname = ANY(%s);
    """
    with conn.cursor() as cur:
        cur.execute(sql, (tables,))
        for row in cur.fetchall():
            out[row[0]][row[1]] = {"valid": row[2], "definition": row[3]}
    return dict(out)


def _reconcile_sync(conn) -> dict:
    """Compare INDEX_REGISTRY vs actual. Returns summary dict.
    Sync function — caller is expected to to_thread this.
    """
    from .bulk_index_manager import INDEX_REGISTRY

    tables = list(INDEX_REGISTRY.keys())
    prod = _fetch_prod_indexes_sync(conn, tables)

    summary = {"healthy": 0, "missing": [], "orphan": [], "invalid": []}

    for table, registry_entries in INDEX_REGISTRY.items():
        registry_names = {e.name for e in registry_entries}
        prod_names = set(prod.get(table, {}).keys())

        for entry in registry_entries:
            prod_info = prod.get(table, {}).get(entry.name)
            if prod_info is None:
                summary["missing"].append(f"{table}.{entry.name}")
            elif not prod_info["valid"]:
                summary["invalid"].append(f"{table}.{entry.name}")
            else:
                summary["healthy"] += 1

        for prod_name in prod_names - registry_names:
            prod_info = prod[table][prod_name]
            is_pk_or_unique = (
                prod_name.endswith("_pkey")
                or "unique" in prod_name.lower()
                or "UNIQUE" in (prod_info["definition"] or "")
            )
            if not is_pk_or_unique:
                summary["orphan"].append(f"{table}.{prod_name}")

    return summary


async def run_startup_check(database_url: Optional[str] = None) -> None:
    """Log index drift at startup. Advisory only; never blocks or raises.

    Call from FastAPI startup_event as fire-and-forget:
        asyncio.create_task(run_startup_check())

    Uses the DATABASE_URL env var if not provided. If no URL, logs INFO and
    returns (no-op — safe in environments where only SUPABASE_URL is set).
    """
    import os
    import psycopg2  # lazy — avoids import overhead if check is disabled

    url = database_url or os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL")
    if not url:
        logger.info("[IndexReconcile] DATABASE_URL not set — skipping startup drift check")
        return

    try:
        def _run():
            conn = psycopg2.connect(url, application_name="startup_index_reconcile", connect_timeout=5)
            try:
                return _reconcile_sync(conn)
            finally:
                conn.close()

        summary = await asyncio.to_thread(_run)
    except Exception as e:
        logger.warning(f"[IndexReconcile] Startup check failed (non-critical): {e}")
        return

    n_invalid = len(summary["invalid"])
    n_missing = len(summary["missing"])
    n_orphan = len(summary["orphan"])
    n_healthy = summary["healthy"]

    # Invalid is the critical drift — an index physically present but broken.
    # This caused the 2026-04-13 outage; loud WARN is deliberate.
    if n_invalid:
        logger.warning(
            f"[IndexReconcile] {n_invalid} INVALID index(es) in production — "
            f"queries relying on them will fall back to sequential scans. "
            f"Run DROP INDEX CONCURRENTLY + recreate:"
        )
        for name in summary["invalid"]:
            logger.warning(f"[IndexReconcile]   INVALID: {name}")

    if n_missing:
        # Missing = registered in code but absent in DB. Happens if a migration
        # wasn't applied on this environment, or an index was dropped manually.
        logger.warning(
            f"[IndexReconcile] {n_missing} index(es) in registry but MISSING from DB:"
        )
        for name in summary["missing"]:
            logger.warning(f"[IndexReconcile]   MISSING: {name}")

    if not n_invalid and not n_missing:
        if n_orphan:
            logger.info(
                f"[IndexReconcile] OK: {n_healthy} healthy, {n_orphan} orphan "
                "(present in DB but not tracked by BulkIndexManager — non-critical)"
            )
        else:
            logger.info(f"[IndexReconcile] OK: all {n_healthy} registered indexes healthy")
