"""
BulkIndexManager — Drop non-essential indexes before bulk writes, recreate after.

Proven pattern: embedding 20K emails went from 2h → 15min by dropping HNSW
indexes during bulk UPDATE. This class generalises it for all bulk operations.

Usage (sync):
    manager = BulkIndexManager(supabase_client)
    with manager.bulk_operation('emails', row_count=50000):
        # ... bulk inserts/updates ...

Usage (async):
    async with manager.async_bulk_operation(['emails', 'qb_operations'], row_count=80000):
        # ... async bulk writes ...

Key constraints:
  - UNIQUE indexes used for ON CONFLICT are NEVER dropped
  - btree indexes recreated with 30s timeout
  - HNSW/GIN indexes recreated with 5min timeout via exec_sql_extended
  - If row_count < MIN_ROWS (500), skip index management entirely
  - Always recreate in finally block — even on error/cancel
"""

import logging
import asyncio
from dataclasses import dataclass
from contextlib import contextmanager, asynccontextmanager
from typing import Union

logger = logging.getLogger(__name__)


@dataclass
class IndexDef:
    """Definition of a database index for the registry."""
    name: str           # e.g. 'idx_emails_embedding'
    table: str          # e.g. 'emails'
    create_sql: str     # Full CREATE INDEX IF NOT EXISTS statement
    index_type: str = 'btree'  # 'btree', 'hnsw', 'gin'
    timeout_s: int = 30 # Recreation timeout: 30 for btree, 300 for HNSW/GIN


# ---------------------------------------------------------------------------
# Index Registry — all droppable indexes per table
# UNIQUE/ON CONFLICT indexes are intentionally excluded (never dropped)
# ---------------------------------------------------------------------------
INDEX_REGISTRY: dict[str, list[IndexDef]] = {

    # ── emails ─────────────────────────────────────────────────────────
    'emails': [
        IndexDef('idx_emails_mailbox_id', 'emails',
                 'CREATE INDEX IF NOT EXISTS idx_emails_mailbox_id ON emails(mailbox_id)'),
        IndexDef('idx_emails_sent_date', 'emails',
                 'CREATE INDEX IF NOT EXISTS idx_emails_sent_date ON emails(sent_date)'),
        IndexDef('idx_emails_mailbox_date', 'emails',
                 'CREATE INDEX IF NOT EXISTS idx_emails_mailbox_date ON emails(mailbox_id, sent_date)'),
        IndexDef('idx_emails_coverage_main', 'emails',
                 'CREATE INDEX IF NOT EXISTS idx_emails_coverage_main ON emails(mailbox_id, sent_date DESC)'),
        IndexDef('idx_emails_processing_status_mailbox', 'emails',
                 'CREATE INDEX IF NOT EXISTS idx_emails_processing_status_mailbox ON emails(mailbox_id, processing_status)'),
        IndexDef('idx_emails_folder_mailbox', 'emails',
                 'CREATE INDEX IF NOT EXISTS idx_emails_folder_mailbox ON emails(mailbox_id, folder_path)'),
        IndexDef('idx_emails_canonical_thread', 'emails',
                 "CREATE INDEX IF NOT EXISTS idx_emails_canonical_thread ON emails(canonical_thread_id) WHERE canonical_thread_id IS NOT NULL"),
        IndexDef('idx_emails_unresolved_threads', 'emails',
                 'CREATE INDEX IF NOT EXISTS idx_emails_unresolved_threads ON emails(mailbox_id, sent_date) WHERE canonical_thread_id IS NULL'),
        IndexDef('idx_emails_resolved_msgid', 'emails',
                 'CREATE INDEX IF NOT EXISTS idx_emails_resolved_msgid ON emails(mailbox_id) WHERE canonical_thread_id IS NOT NULL AND internet_message_id IS NOT NULL'),
        IndexDef('idx_emails_customer_company', 'emails',
                 'CREATE INDEX IF NOT EXISTS idx_emails_customer_company ON emails(customer_company_id)'),
        IndexDef('idx_emails_customer_contact', 'emails',
                 'CREATE INDEX IF NOT EXISTS idx_emails_customer_contact ON emails(customer_contact_id)'),
        IndexDef('idx_emails_client', 'emails',
                 'CREATE INDEX IF NOT EXISTS idx_emails_client ON emails(client_id)'),
        # HNSW — only dropped for embedding operations (slow rebuild, 5 min timeout)
        IndexDef('idx_emails_embedding', 'emails',
                 'CREATE INDEX IF NOT EXISTS idx_emails_embedding ON emails USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)',
                 index_type='hnsw', timeout_s=300),
        # GIN — only dropped for search reindex operations
        IndexDef('idx_emails_search_text', 'emails',
                 "CREATE INDEX IF NOT EXISTS idx_emails_search_text ON emails USING gin(search_text) WHERE search_text IS NOT NULL",
                 index_type='gin', timeout_s=300),
    ],

    # ── qb_operations ──────────────────────────────────────────────────
    'qb_operations': [
        IndexDef('idx_qb_operations_client_operation', 'qb_operations',
                 'CREATE INDEX IF NOT EXISTS idx_qb_operations_client_operation ON qb_operations(client_id, operation_name)'),
        IndexDef('idx_qb_operations_client_department', 'qb_operations',
                 'CREATE INDEX IF NOT EXISTS idx_qb_operations_client_department ON qb_operations(client_id, department)'),
        IndexDef('idx_qb_operations_company', 'qb_operations',
                 'CREATE INDEX IF NOT EXISTS idx_qb_operations_company ON qb_operations(matched_company_id, date_accepted DESC)'),
        IndexDef('idx_qb_operations_job', 'qb_operations',
                 'CREATE INDEX IF NOT EXISTS idx_qb_operations_job ON qb_operations(job_no)'),
        IndexDef('idx_qb_operations_customer', 'qb_operations',
                 'CREATE INDEX IF NOT EXISTS idx_qb_operations_customer ON qb_operations(qb_customer_id)'),
        IndexDef('idx_qb_operations_client_customer', 'qb_operations',
                 'CREATE INDEX IF NOT EXISTS idx_qb_operations_client_customer ON qb_operations(client_id, qb_customer_id)'),
        IndexDef('idx_qb_operations_company_date', 'qb_operations',
                 'CREATE INDEX IF NOT EXISTS idx_qb_operations_company_date ON qb_operations(matched_company_id, date_accepted) WHERE date_accepted IS NOT NULL'),
        # HNSW — only dropped for embedding operations
        IndexDef('idx_qb_operations_embedding', 'qb_operations',
                 'CREATE INDEX IF NOT EXISTS idx_qb_operations_embedding ON qb_operations USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)',
                 index_type='hnsw', timeout_s=300),
    ],

    # ── customer_companies ─────────────────────────────────────────────
    'customer_companies': [
        IndexDef('idx_customer_companies_client', 'customer_companies',
                 'CREATE INDEX IF NOT EXISTS idx_customer_companies_client ON customer_companies(client_id)'),
        IndexDef('idx_customer_companies_name', 'customer_companies',
                 'CREATE INDEX IF NOT EXISTS idx_customer_companies_name ON customer_companies(company_name)'),
        IndexDef('idx_customer_companies_last_contact', 'customer_companies',
                 'CREATE INDEX IF NOT EXISTS idx_customer_companies_last_contact ON customer_companies(last_contact_date DESC)'),
        IndexDef('idx_companies_engagement', 'customer_companies',
                 'CREATE INDEX IF NOT EXISTS idx_companies_engagement ON customer_companies(engagement_score DESC)'),
        IndexDef('idx_companies_relationship', 'customer_companies',
                 'CREATE INDEX IF NOT EXISTS idx_companies_relationship ON customer_companies(relationship_status)'),
        IndexDef('idx_companies_health', 'customer_companies',
                 'CREATE INDEX IF NOT EXISTS idx_companies_health ON customer_companies(communication_health)'),
        IndexDef('idx_companies_primary_contact', 'customer_companies',
                 'CREATE INDEX IF NOT EXISTS idx_companies_primary_contact ON customer_companies(primary_contact_id)'),
        IndexDef('idx_companies_qb_tier', 'customer_companies',
                 'CREATE INDEX IF NOT EXISTS idx_companies_qb_tier ON customer_companies(qb_tier)'),
        IndexDef('idx_companies_qb_total_revenue', 'customer_companies',
                 'CREATE INDEX IF NOT EXISTS idx_companies_qb_total_revenue ON customer_companies(qb_total_revenue DESC NULLS LAST)'),
        # HNSW — only dropped for embedding operations
        IndexDef('idx_companies_embedding', 'customer_companies',
                 'CREATE INDEX IF NOT EXISTS idx_companies_embedding ON customer_companies USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)',
                 index_type='hnsw', timeout_s=300),
        # GIN — only dropped for domain reindex operations
        IndexDef('idx_customer_companies_domains_gin', 'customer_companies',
                 'CREATE INDEX IF NOT EXISTS idx_customer_companies_domains_gin ON customer_companies USING gin(email_domains)',
                 index_type='gin', timeout_s=300),
    ],

    # ── qb_quotes ──────────────────────────────────────────────────────
    'qb_quotes': [
        IndexDef('idx_qb_quotes_company', 'qb_quotes',
                 'CREATE INDEX IF NOT EXISTS idx_qb_quotes_company ON qb_quotes(matched_company_id, date_created DESC)'),
        IndexDef('idx_qb_quotes_status', 'qb_quotes',
                 'CREATE INDEX IF NOT EXISTS idx_qb_quotes_status ON qb_quotes(client_id, date_accepted)'),
        IndexDef('idx_qb_quotes_client_customer', 'qb_quotes',
                 'CREATE INDEX IF NOT EXISTS idx_qb_quotes_client_customer ON qb_quotes(client_id, qb_customer_id)'),
    ],

    # ── qb_jobs ────────────────────────────────────────────────────────
    'qb_jobs': [
        IndexDef('idx_qb_jobs_company', 'qb_jobs',
                 'CREATE INDEX IF NOT EXISTS idx_qb_jobs_company ON qb_jobs(matched_company_id, accepted_date DESC)'),
        IndexDef('idx_qb_jobs_client_customer', 'qb_jobs',
                 'CREATE INDEX IF NOT EXISTS idx_qb_jobs_client_customer ON qb_jobs(client_id, qb_customer_id)'),
    ],

    # ── qb_sales_line_items ────────────────────────────────────────────
    'qb_sales_line_items': [
        IndexDef('idx_qb_sales_company', 'qb_sales_line_items',
                 'CREATE INDEX IF NOT EXISTS idx_qb_sales_company ON qb_sales_line_items(matched_company_id, inv_date DESC)'),
        IndexDef('idx_qb_sales_am', 'qb_sales_line_items',
                 'CREATE INDEX IF NOT EXISTS idx_qb_sales_am ON qb_sales_line_items(job_am_name, inv_date DESC)'),
    ],

    # ── qb_customers ───────────────────────────────────────────────────
    'qb_customers': [
        IndexDef('idx_qb_customers_matched', 'qb_customers',
                 'CREATE INDEX IF NOT EXISTS idx_qb_customers_matched ON qb_customers(matched_company_id)'),
        IndexDef('idx_qb_customers_client', 'qb_customers',
                 'CREATE INDEX IF NOT EXISTS idx_qb_customers_client ON qb_customers(client_id)'),
    ],

    # ── qb_unique_emails ───────────────────────────────────────────────
    'qb_unique_emails': [
        IndexDef('idx_qb_ue_email', 'qb_unique_emails',
                 'CREATE INDEX IF NOT EXISTS idx_qb_ue_email ON qb_unique_emails(client_id, lower(email))'),
        IndexDef('idx_qb_ue_customer', 'qb_unique_emails',
                 'CREATE INDEX IF NOT EXISTS idx_qb_ue_customer ON qb_unique_emails(client_id, qb_customer_id) WHERE qb_customer_id IS NOT NULL'),
    ],

    # ── email_contact_links ────────────────────────────────────────────
    'email_contact_links': [
        IndexDef('idx_ecl_email', 'email_contact_links',
                 'CREATE INDEX IF NOT EXISTS idx_ecl_email ON email_contact_links(email_id)'),
        IndexDef('idx_ecl_contact', 'email_contact_links',
                 'CREATE INDEX IF NOT EXISTS idx_ecl_contact ON email_contact_links(contact_id) WHERE contact_id IS NOT NULL'),
        IndexDef('idx_ecl_company', 'email_contact_links',
                 'CREATE INDEX IF NOT EXISTS idx_ecl_company ON email_contact_links(company_id) WHERE company_id IS NOT NULL'),
        IndexDef('idx_ecl_client', 'email_contact_links',
                 'CREATE INDEX IF NOT EXISTS idx_ecl_client ON email_contact_links(client_id)'),
    ],

    # ── thread_status ──────────────────────────────────────────────────
    'thread_status': [
        IndexDef('idx_thread_status_canonical', 'thread_status',
                 'CREATE INDEX IF NOT EXISTS idx_thread_status_canonical ON thread_status(canonical_thread_id) WHERE canonical_thread_id IS NOT NULL'),
        IndexDef('idx_thread_status_intent', 'thread_status',
                 'CREATE INDEX IF NOT EXISTS idx_thread_status_intent ON thread_status(intent_status) WHERE intent_status IS NOT NULL'),
        IndexDef('idx_thread_status_last_intent', 'thread_status',
                 'CREATE INDEX IF NOT EXISTS idx_thread_status_last_intent ON thread_status(last_email_intent) WHERE last_email_intent IS NOT NULL'),
    ],

    # ── customer_contacts ──────────────────────────────────────────────
    'customer_contacts': [
        IndexDef('idx_customer_contacts_company', 'customer_contacts',
                 'CREATE INDEX IF NOT EXISTS idx_customer_contacts_company ON customer_contacts(customer_company_id)'),
        IndexDef('idx_customer_contacts_client', 'customer_contacts',
                 'CREATE INDEX IF NOT EXISTS idx_customer_contacts_client ON customer_contacts(client_id)'),
        IndexDef('idx_customer_contacts_email', 'customer_contacts',
                 'CREATE INDEX IF NOT EXISTS idx_customer_contacts_email ON customer_contacts(email_address)'),
        IndexDef('idx_customer_contacts_last_contact', 'customer_contacts',
                 'CREATE INDEX IF NOT EXISTS idx_customer_contacts_last_contact ON customer_contacts(last_contacted_at DESC)'),
    ],

    # ── ai_email_intelligence ──────────────────────────────────────────
    'ai_email_intelligence': [
        IndexDef('idx_ai_intel_mailbox', 'ai_email_intelligence',
                 'CREATE INDEX IF NOT EXISTS idx_ai_intel_mailbox ON ai_email_intelligence(mailbox_id)'),
        IndexDef('idx_ai_intel_mailbox_status', 'ai_email_intelligence',
                 'CREATE INDEX IF NOT EXISTS idx_ai_intel_mailbox_status ON ai_email_intelligence(mailbox_id, processing_status)'),
    ],
}


# Minimum rows to engage index management — below this, the overhead isn't worth it
MIN_ROWS = 500


class BulkIndexManager:
    """Drop heavy indexes before bulk writes, recreate after.

    By default, only HNSW indexes are dropped — they cause ~50-100ms overhead
    per row on large tables. Btree indexes (~0.1ms/row) are left in place so
    all queries keep working at full speed during the operation.

    Use index_types=['hnsw', 'gin'] to also drop GIN indexes, or
    index_types=['hnsw', 'gin', 'btree'] to drop everything (risky).
    """

    def __init__(self, supabase_client):
        self._sb = supabase_client
        self._exec_sql_available = True

    # ── Public API ─────────────────────────────────────────────────────

    @contextmanager
    def bulk_operation(self, tables: Union[str, list[str]], row_count: int = 0,
                       index_types: list[str] = None):
        """Sync context manager. Only drops HNSW indexes by default."""
        tables = [tables] if isinstance(tables, str) else tables
        types = index_types or ['hnsw']
        if row_count < MIN_ROWS:
            yield
            return

        dropped = self.drop_indexes(tables, types)
        try:
            yield
        finally:
            self.recreate_indexes(tables, types)

    @asynccontextmanager
    async def async_bulk_operation(self, tables: Union[str, list[str]], row_count: int = 0,
                                    index_types: list[str] = None):
        """Async context manager. Only drops HNSW indexes by default."""
        tables = [tables] if isinstance(tables, str) else tables
        types = index_types or ['hnsw']
        if row_count < MIN_ROWS:
            yield
            return

        await asyncio.to_thread(self.drop_indexes, tables, types)
        try:
            yield
        finally:
            await asyncio.to_thread(self.recreate_indexes, tables, types)

    # ── Drop / Recreate ────────────────────────────────────────────────

    def drop_indexes(self, tables: list[str], index_types: list[str] = None) -> int:
        """Drop indexes of the specified types. Returns count dropped."""
        if not self._exec_sql_available:
            return 0
        types = set(index_types or ['hnsw'])

        dropped = 0
        for table in tables:
            indexes = INDEX_REGISTRY.get(table, [])
            for idx in indexes:
                if idx.index_type not in types:
                    continue
                try:
                    self._exec_sql(f'DROP INDEX IF EXISTS {idx.name}')
                    dropped += 1
                except Exception as e:
                    if 'does not exist' in str(e).lower():
                        logger.warning("[BulkIndex] exec_sql RPC not available — skipping")
                        self._exec_sql_available = False
                        return 0
                    logger.warning(f"[BulkIndex] Failed to drop {idx.name}: {e}")

        if dropped:
            logger.info(f"[BulkIndex] Dropped {dropped} {'/'.join(types)} indexes on [{', '.join(tables)}]")
        return dropped

    def recreate_indexes(self, tables: list[str], index_types: list[str] = None) -> int:
        """Recreate indexes of the specified types. Returns count recreated."""
        if not self._exec_sql_available:
            return 0
        types = set(index_types or ['hnsw'])

        recreated = 0
        for table in tables:
            indexes = INDEX_REGISTRY.get(table, [])
            for idx in indexes:
                if idx.index_type not in types:
                    continue
                try:
                    if idx.timeout_s > 30:
                        self._exec_sql_extended(idx.create_sql, idx.timeout_s)
                    else:
                        self._exec_sql(idx.create_sql)
                    recreated += 1
                except Exception as e:
                    logger.error(f"[BulkIndex] Failed to recreate {idx.name}: {e}")
                    logger.error(f"[BulkIndex] Run manually: {idx.create_sql}")

        if recreated:
            logger.info(f"[BulkIndex] Recreated {recreated} {'/'.join(types)} indexes on [{', '.join(tables)}]")
        return recreated

    # ── SQL execution helpers ──────────────────────────────────────────

    def _exec_sql(self, query: str):
        """Execute DDL via exec_sql RPC (8s default timeout)."""
        self._sb.rpc('exec_sql', {'query': query}).execute()

    def _exec_sql_extended(self, query: str, timeout_s: int = 300):
        """Execute DDL with extended timeout for slow indexes (HNSW, GIN).

        Critical: if this RPC call fails for any reason EXCEPT the RPC literally
        not existing in the DB, DO NOT fall back to the short-timeout exec_sql.
        HNSW rebuilds on 200K+ vectors take minutes; the 8s exec_sql timeout
        will hard-fail and leave the index dropped in production (observed
        2026-04-13). Propagate the error so the caller sees a loud failure
        instead of silently degrading.

        Only fall back if the RPC itself is missing (SQLSTATE 42883 /
        'function does not exist'). That's the ONE case where the fallback is
        the right behavior (older DB without migration 072 applied).
        """
        try:
            self._sb.rpc('exec_sql_extended', {
                'p_query': query,
                'p_timeout_s': timeout_s,
            }).execute()
        except Exception as e:
            err_str = str(e).lower()
            rpc_missing = (
                '42883' in err_str
                or 'function exec_sql_extended' in err_str and 'does not exist' in err_str
            )
            if rpc_missing:
                logger.warning(
                    f"[BulkIndex] exec_sql_extended RPC not deployed — falling back to "
                    f"exec_sql (8s timeout). Apply migration 072. Query: {query[:80]}..."
                )
                self._exec_sql(query)
                return
            # Any other error — transient socket, statement_timeout, deadlock,
            # bad DDL, permissions — surface it. Do NOT mask with a shorter-timeout
            # fallback that is guaranteed to fail for the same reason the original
            # call was using the extended timeout.
            logger.error(
                f"[BulkIndex] exec_sql_extended failed (NOT falling back): {e}. "
                f"Query: {query[:200]}"
            )
            raise
