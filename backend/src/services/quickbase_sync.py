"""
Quickbase Sync Service — Syncs QB data to local Supabase cache tables.

Handles: Customers, Contacts, Quotes, Jobs, Sales Line Items, Operations.
After sync, matches QB records to existing customer_companies/customer_contacts:
  Pass 0a — Email join (1:1 auto-write, multi-match staged)
  Pass 0b — Contact chain (1:1 auto-write, multi-match staged)
  Pass 1-3 — Name-based: exact name, domain root, fuzzy (all staged for review)
"""

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from .quickbase_client import QuickbaseClient, DEFAULT_FIELD_MAPPINGS
from . import capability_classifier

logger = logging.getLogger(__name__)

# Supabase batch limits
UPSERT_BATCH_SIZE = 100
IN_FILTER_LIMIT = 500

# ── Matching helpers ──────────────────────────────────────────────────────────

GENERIC_DOMAINS = frozenset({
    'gmail.com', 'hotmail.com', 'yahoo.com', 'outlook.com',
    'icloud.com', 'bigpond.com', 'me.com', 'hotmail.com.au',
    'yahoo.com.au', 'live.com', 'live.com.au', 'msn.com',
    'aol.com', 'mail.com', 'protonmail.com', 'zoho.com',
})

FUZZY_SCORE_THRESHOLD = 82  # rapidfuzz token_sort_ratio cutoff


def _normalise(name: str) -> str:
    """Lowercase, strip all non-alphanumeric characters."""
    return re.sub(r'[^a-z0-9]', '', (name or '').lower())


def _extract_domain_roots(email_domains) -> list[str]:
    """Extract matchable second-level domain tokens from an email_domains value.

    email_domains may be a JSON array string, a Python list, or a plain string.
    Returns tokens of length ≥ 5 (skips generic providers).
    """
    if isinstance(email_domains, list):
        domains = email_domains
    else:
        domains = re.findall(r'[\w.-]+\.\w+', str(email_domains or ''))

    roots = []
    for d in domains:
        d_lower = d.lower()
        if d_lower in GENERIC_DOMAINS:
            continue
        parts = d_lower.split('.')
        # Use the leftmost part as the brand root — handles multi-level TLDs
        # e.g. "carbon8.com.au" → "carbon8", "thepropertyagency.com" → "thepropertyagency"
        root = parts[0] if parts else ''
        if len(root) >= 5:  # avoid short tokens ('app', 'con', 'us')
            roots.append(root)
    return roots


def _parse_recency_html(html_or_value) -> Optional[int]:
    """Parse recency from QB — handles both HTML-wrapped and plain values.

    QB exports wrap recency in HTML: '<div style="...">8 d</div>'
    QB API may return a plain integer or string like '8'.
    """
    if html_or_value is None:
        return None
    if isinstance(html_or_value, (int, float)):
        return int(html_or_value)
    m = re.search(r'(\d+)\s*d?', str(html_or_value))
    return int(m.group(1)) if m else None


def _derive_growth(ty: Optional[float], ly: Optional[float]) -> Optional[float]:
    """Derive annual growth percentage from TY and LY invoiced amounts."""
    if ty is not None and ly and ly != 0:
        return round((ty - ly) / ly * 100, 1)
    return None


def _derive_tier(total_revenue: Optional[float]) -> str:
    """Revenue band tier classification."""
    if total_revenue is None:
        return 'Unknown'
    if total_revenue >= 500_000:
        return 'Level 4 Enterprise'
    if total_revenue >= 100_000:
        return 'Level 3 Major'
    if total_revenue >= 20_000:
        return 'Level 2 Growth'
    return 'Level 1 Retail'


def _execute_with_retry(func, max_retries=3):
    """Execute a Supabase operation with retry for transient errors."""
    import time
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            err_str = str(e)
            if attempt < max_retries - 1 and any(
                code in err_str for code in ['525', '502', '503', '504', 'SSL', 'ConnectionError', 'Resource temporarily unavailable', 'ConnectionTerminated', 'Errno 11']
            ):
                time.sleep(2 ** attempt)
                continue
            raise


class QuickbaseSync:
    """Orchestrates syncing Quickbase data to local Supabase cache."""

    def __init__(self, supabase_client, qb_config: dict, cancel_event=None):
        """
        Args:
            supabase_client: Initialized Supabase client
            qb_config: Row from qb_sync_config table
            cancel_event: Optional threading.Event — set to signal cancellation
        """
        self._supabase = supabase_client
        self._config = qb_config
        self._client_id = qb_config['client_id']
        self._cancel = cancel_event

        # Merge default field mappings with any client-specific overrides
        stored_mappings = qb_config.get('field_mappings') or {}
        self._field_mappings = {}
        for table_name in DEFAULT_FIELD_MAPPINGS:
            self._field_mappings[table_name] = {
                **DEFAULT_FIELD_MAPPINGS[table_name],
                **(stored_mappings.get(table_name) or {}),
            }

        self._qb_client = QuickbaseClient(
            realm_hostname=qb_config['realm_hostname'],
            user_token=qb_config['user_token_encrypted'],  # TODO: decrypt in production
        )

    @property
    def cancelled(self) -> bool:
        """Check if cancellation has been requested."""
        return self._cancel is not None and self._cancel.is_set()

    # Maps logical table name → qb_sync_config field holding the QB table ID
    _TABLE_ID_CONFIG_FIELD = {
        'customers':        'customers_table_id',
        'contacts':         'contacts_table_id',
        'quotes':           'quotes_table_id',
        'jobs':             'jobs_table_id',
        'sales_line_items': 'sales_line_items_table_id',
        'operations':       'operations_table_id',
        'unique_emails':    'unique_emails_table_id',
        'job_status_log':   'audit_logs_table_id',
    }

    def _write_sync_log(self, table_name: str, record_count: int, status: str = 'success', error_message: str = None):
        """Write a sync log entry including the QB table ID for cross-referencing qb_field_definitions."""
        config_field = self._TABLE_ID_CONFIG_FIELD.get(table_name, '')
        table_id = self._config.get(config_field)  # e.g. 'buzhzbv39'
        try:
            _execute_with_retry(lambda: self._supabase.table('qb_sync_log').insert({
                'client_id': self._client_id,
                'table_name': table_name,
                'table_id': table_id,
                'record_count': record_count,
                'synced_at': datetime.now(timezone.utc).isoformat(),
                'status': status,
                'error_message': error_message,
            }).execute())
        except Exception as e:
            logger.warning(f"Failed to write sync log for {table_name}: {e}")

    def _build_incremental_where(self, table_key: str | None = None) -> Optional[str]:
        """Build a QB query clause to filter records modified since last sync.

        Uses QB field ID 2 (Date Modified) with the AF (after) operator.
        Returns None for full sync (no last sync recorded).

        When table_key is provided, looks up the per-table last sync time from
        qb_sync_log first, falling back to the global last_sync_at. This ensures
        syncing a single table doesn't advance the timestamp for other tables.
        """
        last_sync = None

        # Per-table timestamp from qb_sync_log (most recent successful sync)
        if table_key:
            try:
                log_result = _execute_with_retry(lambda tk=table_key: self._supabase.table('qb_sync_log').select(
                    'synced_at'
                ).eq('client_id', self._client_id).eq(
                    'table_name', tk
                ).eq('status', 'success').order(
                    'synced_at', desc=True
                ).limit(1).execute())
                if log_result.data:
                    last_sync = log_result.data[0]['synced_at']
            except Exception:
                pass

        # Fall back to global last_sync_at
        if not last_sync:
            last_sync = self._config.get('last_sync_at')

        if not last_sync:
            return None

        # QB expects ISO 8601 format for date comparisons
        if isinstance(last_sync, str):
            ts = last_sync
        else:
            ts = last_sync.isoformat() if hasattr(last_sync, 'isoformat') else str(last_sync)

        # QB query syntax: {'2'.AF.'2026-03-20T00:00:00Z'}
        return f"{{'2'.AF.'{ts}'}}"

    async def sync_all(
        self,
        tables: list[str] | None = None,
        full: bool = False,
    ) -> dict[str, int]:
        """Sync QB tables. Incremental by default (only records modified since last sync).

        Args:
            tables: Sync a subset of tables; omit for all tables.
            full: Force full sync (ignore last_sync_at). Default False.
        """
        self._full_sync = full
        mode = 'full' if full else 'incremental'

        all_fns = [
            ('customers', self.sync_customers),
            ('contacts', self.sync_contacts),
            ('quotes', self.sync_quotes),
            ('jobs', self.sync_jobs),
            ('sales_line_items', self.sync_sales_line_items),
            ('operations', self.sync_operations),
            ('unique_emails', self.sync_unique_emails),
            ('job_status_log', self.sync_job_status_log),
        ]
        to_sync = [(k, fn) for k, fn in all_fns if tables is None or k in tables]
        label = ', '.join(k for k, _ in to_sync)
        logger.info(f"Starting QB sync ({mode}) for client {self._client_id}: [{label}]")
        counts = {'sync_mode': mode}

        for table_key, sync_fn in to_sync:
            if self.cancelled:
                logger.info(f"QB sync cancelled before {table_key}")
                break
            try:
                counts[table_key] = await sync_fn()
                # operations writes its own log before enrichment (so restart won't re-fetch 600K+)
                if table_key != 'operations':
                    self._write_sync_log(table_key, counts[table_key])
            except Exception as e:
                logger.error(f"QB sync failed for table {table_key}: {e}")
                if table_key != 'operations':
                    self._write_sync_log(table_key, 0, status='error', error_message=str(e))
                counts[table_key] = 0

        # Post-sync operations enrichment — always run if operations was synced
        # (even with 0 new records, unmatched operations from previous syncs need matching)
        if 'operations' in counts:
            try:
                await self._post_sync_operations()
            except Exception as e:
                logger.error(f"Operations post-sync enrichment failed: {e}")

        # After sync, match to existing companies/contacts
        self._email_matched_qb_ids: set[str] = set()
        self._email_staged_qb_record_ids: set[str] = set()

        # Pass 0: Email-based matching via QB Unique Emails (highest priority)
        email_match_stats = await self.match_companies_via_unique_emails()
        counts['email_match_stats'] = email_match_stats

        # Pass 1-3: Name-based matching → staged for review (no auto-write)
        match_stats = await self.match_to_companies()
        matched_contacts = await self.match_to_contacts()
        matched_via_contacts = await self.match_customers_via_contacts()
        counts['match_stats'] = match_stats
        counts['matched_companies'] = (
            email_match_stats.get('matched', 0)
            + matched_via_contacts
        )
        counts['staged_candidates'] = match_stats.get('total', 0)
        counts['matched_contacts'] = matched_contacts

        # Update last_sync_at
        _execute_with_retry(lambda: self._supabase.table('qb_sync_config').update({
            'last_sync_at': datetime.now(timezone.utc).isoformat(),
            'updated_at': datetime.now(timezone.utc).isoformat(),
        }).eq('client_id', self._client_id).execute())

        # Auto-embed new/updated records so they're immediately searchable
        await self._post_sync_embeddings(counts)

        logger.info(f"QB sync complete for client {self._client_id}: {counts}")
        return counts

    async def _sync_table_streamed(
        self,
        table_name: str,
        table_key: str,
        mapping: dict[str, str],
        required_fields: list[str] | None = None,
        page_filter=None,
        base_where: str | None = None,
    ) -> int:
        """Generic streamed sync: fetch from QB page-by-page and upsert each page immediately.

        Args:
            table_name: Supabase destination table (e.g. 'qb_customers')
            table_key: Config key for the QB table ID (e.g. 'customers_table_id')
            mapping: Field ID → column name mapping
            required_fields: Columns that must be non-NULL (rows without them are skipped)
            page_filter: Optional callable(page_records) → filtered_records, applied per page
            base_where: Optional QB query clause ANDed with the incremental clause on every
                sync (e.g. "{'7'.EX.'Job Status'}" to pull only Job Status audit rows).
                Applied on both full and incremental syncs so filtered tables stay filtered.
        """
        table_id = self._config.get(table_key)
        if not table_id:
            logger.info(f"{table_key} not set — skipping {table_name} sync")
            return 0

        select_fields = QuickbaseClient.get_select_fields(mapping)
        # Resolve the logical table name from the config key via the reverse of
        # _TABLE_ID_CONFIG_FIELD (so e.g. 'audit_logs_table_id' → 'job_status_log',
        # not the naïve 'audit_logs' which wouldn't match qb_sync_log.table_name).
        _reverse = {v: k for k, v in self._TABLE_ID_CONFIG_FIELD.items()}
        logical_name = _reverse.get(table_key, table_key.replace('_table_id', ''))
        incremental = None if getattr(self, '_full_sync', False) else self._build_incremental_where(logical_name)
        # Combine base + incremental with AND. QB accepts ANDed clauses as a single string.
        if base_where and incremental:
            where = f"{base_where}AND{incremental}"
        else:
            where = base_where or incremental

        total_count = 0
        page_num = 0

        async for page_records, qb_total in self._qb_client.query_records_streamed(
            table_id, select_fields, where=where
        ):
            if self.cancelled:
                logger.info(f"{table_name} sync cancelled after {page_num} pages ({total_count} upserted)")
                break

            page_num += 1

            if page_filter:
                page_records = page_filter(page_records)

            logger.info(
                f"{table_name} page {page_num}: upserting {len(page_records)} records "
                f"(QB total: {qb_total})"
            )
            page_count = await self._upsert_records(
                table_name, page_records, mapping, required_fields=required_fields,
            )
            total_count += page_count

        logger.info(f"{table_name} sync complete: {total_count} upserted across {page_num} pages")
        return total_count

    async def sync_customers(self) -> int:
        """Sync QB Customers table → qb_customers."""
        return await self._sync_table_streamed(
            'qb_customers', 'customers_table_id',
            self._field_mappings['customers'],
            required_fields=['customer_name'],
        )

    async def sync_contacts(self) -> int:
        """Sync QB Contacts table → qb_contacts."""
        return await self._sync_table_streamed(
            'qb_contacts', 'contacts_table_id',
            self._field_mappings['contacts'],
        )

    async def sync_quotes(self) -> int:
        """Sync QB Quotes table → qb_quotes."""
        return await self._sync_table_streamed(
            'qb_quotes', 'quotes_table_id',
            self._field_mappings['quotes'],
        )

    async def sync_jobs(self) -> int:
        """Sync QB Jobs table → qb_jobs."""
        return await self._sync_table_streamed(
            'qb_jobs', 'jobs_table_id',
            self._field_mappings['jobs'],
        )

    async def sync_sales_line_items(self) -> int:
        """Sync QB Sales Line Items table → qb_sales_line_items."""
        return await self._sync_table_streamed(
            'qb_sales_line_items', 'sales_line_items_table_id',
            self._field_mappings['sales_line_items'],
        )

    async def sync_operations(self) -> int:
        """Sync QB Operations table → qb_operations."""
        def _filter_t_cancelled(page_records):
            return [
                r for r in page_records
                if (r.get('21') or {}).get('value') != 'T-Cancelled'
            ]

        count = await self._sync_table_streamed(
            'qb_operations', 'operations_table_id',
            self._field_mappings.get('operations', DEFAULT_FIELD_MAPPINGS['operations']),
            page_filter=_filter_t_cancelled,
        )
        # Write sync log immediately after upsert — before enrichment.
        # This ensures the timestamp is saved even if enrichment is interrupted,
        # so the next incremental sync won't re-fetch all 600K+ records.
        self._write_sync_log('operations', count)
        return count

    async def sync_job_status_log(self) -> int:
        """Sync QB Audit Logs (bu9yjc3ne) filtered to Field Name = 'Job Status'.

        QB user fields return the display name string for user-typed values, so
        changed_by (fid 10) lands as TEXT without extra extraction. Date Created
        (fid 1) is the moment of the status change, stored as changed_at.
        """
        return await self._sync_table_streamed(
            'qb_job_status_log', 'audit_logs_table_id',
            self._field_mappings.get('job_status_log', DEFAULT_FIELD_MAPPINGS['job_status_log']),
            base_where="{'7'.EX.'Job Status'}",
            required_fields=['job_no'],  # audit rows without a linked job aren't useful
        )

    async def _post_sync_operations(self):
        """Post-sync enrichment for operations — called by sync_all after the sync log is written."""
        if self.cancelled:
            return
        await self.match_operations_to_companies()
        await self.enrich_operations()

    async def _post_sync_embeddings(self, counts: dict):
        """Auto-embed new/updated records after sync so they're searchable immediately.

        Runs on un-embedded records only (WHERE embedding IS NULL).
        Non-critical — failures are logged but don't affect sync result.
        """
        try:
            from .vector_service import VectorService
            vs = VectorService(self._supabase)

            if counts.get('customers', 0) > 0 or counts.get('contacts', 0) > 0:
                try:
                    result = await vs.embed_companies(self._client_id, limit=500)
                    embedded = result.get('embedded', 0)
                    if embedded > 0:
                        logger.info(f"Auto-embedded {embedded} companies after QB sync")
                except Exception as e:
                    logger.warning(f"Company embedding after sync failed: {e}")

            if counts.get('operations', 0) > 0:
                try:
                    result = await vs.embed_operations(self._client_id, batch_size=100, limit=1000)
                    embedded = result.get('embedded', 0)
                    if embedded > 0:
                        logger.info(f"Auto-embedded {embedded} operations after QB sync")
                except Exception as e:
                    logger.warning(f"Operations embedding after sync failed: {e}")

        except Exception as e:
            logger.warning(f"Post-sync embedding failed (non-critical): {e}")

    async def sync_unique_emails(self) -> int:
        """Sync QB Unique Emails table → qb_unique_emails."""
        mapping = self._field_mappings.get('unique_emails', DEFAULT_FIELD_MAPPINGS.get('unique_emails', {}))
        if not mapping:
            logger.warning("No field mappings for unique_emails — skipping")
            return 0

        # QB formula checkboxes may return 1/0 or "true"/"false" — coerce per page
        bool_fields = {'hide', 'email_invalid', 'free'}
        bool_fid_map = {v: k for k, v in mapping.items() if v in bool_fields}

        def _coerce_booleans(page_records):
            for record in page_records:
                for col_name, fid in bool_fid_map.items():
                    field_data = record.get(fid)
                    if isinstance(field_data, dict):
                        v = field_data.get('value')
                        if v is not None and not isinstance(v, bool):
                            if isinstance(v, (int, float)):
                                field_data['value'] = bool(v)
                            elif isinstance(v, str):
                                field_data['value'] = v.lower() in ('true', '1', 'yes')
            return page_records

        return await self._sync_table_streamed(
            'qb_unique_emails', 'unique_emails_table_id',
            mapping,
            required_fields=['email'],
            page_filter=_coerce_booleans,
        )

    async def enrich_operations(self) -> dict:
        """
        Post-sync enrichment for qb_operations — no QB API calls, pure DB joins + classification.

        Steps:
          1. Classify: capability_tags + has_coating/sewing/outsource + row_type via classifier
          2. am_rush: pattern match on operation_name
          3. contact_email: join qb_operations.job_no → qb_quotes.contact_email
          4. factory_rush: join qb_operations.job_no → qb_jobs.factory_rush_level IS NOT NULL

        Called automatically after sync_operations(). Also triggered by POST /intelligence-config/reclassify.
        """
        logger.info(f"[Enrich] Starting operations enrichment for client {self._client_id}")
        counts = {}

        # ── 1 + 2: Classify + am_rush ────────────────────────────────────────
        counts['classified'] = await asyncio.to_thread(
            self._classify_operations
        )

        # ── 3: contact_email join ────────────────────────────────────────────
        counts['contact_email'] = await asyncio.to_thread(
            self._join_contact_email
        )

        # ── 4: factory_rush join ─────────────────────────────────────────────
        counts['factory_rush'] = await asyncio.to_thread(
            self._join_factory_rush
        )

        logger.info(f"[Enrich] Complete for client {self._client_id}: {counts}")
        return counts

    def _classify_operations(self) -> int:
        """Classify unclassified operations. QB tags are primary; our classifier fills gaps.

        - If qb_capability_tag is populated: use it as capability_tags (wrapped in list)
        - If qb_capability_tag is blank: full classifier fallback
        - Boolean flags (has_coating, has_sewing, etc.) and am_rush always come from classifier
        - row_type: prefer qb_row_type_tag, fall back to classifier

        Writes batched via batch_update_qb_capabilities RPC (migration 072) —
        replaces per-row UPDATE calls with one RPC per 100-row chunk.
        """
        total = 0
        qb_primary = 0
        classifier_used = 0
        offset = 0
        batch_size = 500
        WRITE_CHUNK = 100  # batch RPC chunk size

        def _flush(updates: list[dict]) -> int:
            if not updates:
                return 0
            try:
                resp = _execute_with_retry(lambda u=updates: (
                    self._supabase.rpc('batch_update_qb_capabilities', {'p_updates': u}).execute()
                ))
                # RPC returns INTEGER count of rows updated
                return int(resp.data) if resp and resp.data is not None else len(updates)
            except Exception as ex:
                logger.warning(f"[Enrich] classify batch update failed ({len(updates)} rows): {ex}")
                return 0

        while True:
            result = _execute_with_retry(lambda o=offset: self._supabase.table('qb_operations').select(
                'id, department, operation_name, machine, qb_capability_tag, qb_row_type_tag'
            ).eq('client_id', self._client_id).eq('capability_tags', '[]').range(
                o, o + batch_size - 1
            ).execute())

            rows = result.data or []
            if not rows:
                break

            pending: list[dict] = []
            for row in rows:
                # Always run classifier for boolean flags + am_rush (QB doesn't have these)
                result_cls = capability_classifier.classify(
                    self._supabase,
                    self._client_id,
                    dept=row.get('department'),
                    op=row.get('operation_name'),
                    machine=row.get('machine'),
                    operation_name=row.get('operation_name'),
                )

                qb_cap = (row.get('qb_capability_tag') or '').strip()
                qb_row = (row.get('qb_row_type_tag') or '').strip()

                if qb_cap:
                    # QB is source of truth for capability tag
                    tags = [qb_cap]
                    qb_primary += 1
                else:
                    # No QB tag — full classifier fallback
                    tags = result_cls['capability_tags']
                    if tags:
                        classifier_used += 1

                # Shape for the batch RPC: all text fields; SQL function casts.
                # capability_tags is comma-separated (the RPC splits via string_to_array).
                pending.append({
                    'id':                      row['id'],
                    'capability_tags':         ','.join(tags) if tags else '',
                    'has_coating':             str(bool(result_cls['has_coating'])).lower(),
                    'has_sewing':              str(bool(result_cls['has_sewing'])).lower(),
                    'has_outsource_component': str(bool(result_cls['has_outsource_component'])).lower(),
                    'am_rush':                 str(bool(result_cls['am_rush'])).lower(),
                    'row_type':                qb_row or result_cls['row_type'] or '',
                })

                if len(pending) >= WRITE_CHUNK:
                    total += _flush(pending)
                    pending = []

            # Flush trailing rows from this page
            total += _flush(pending)

            offset += len(rows)
            if len(rows) < batch_size:
                break
            if offset % 5000 == 0:
                logger.info(f"[Enrich] Classified {total} operations so far "
                            f"(QB primary: {qb_primary}, classifier: {classifier_used})...")

        logger.info(f"[Enrich] Classified {total} operations for client {self._client_id} "
                    f"(QB primary: {qb_primary}, classifier fallback: {classifier_used})")
        return total

    def _join_contact_email(self) -> int:
        """
        Populate contact_email on qb_operations via:
          qb_operations.job_no → qb_quotes.job_no → qb_quotes.contact_email
        Only updates rows where contact_email is NULL.
        """
        # Fetch ALL ops missing contact_email (paginated — can be 100K+)
        ops: list[dict] = []
        offset = 0
        while True:
            page = _execute_with_retry(lambda o=offset: self._supabase.table('qb_operations').select(
                'id, job_no'
            ).eq('client_id', self._client_id).is_('contact_email', 'null').not_.is_(
                'job_no', 'null'
            ).range(o, o + 999).execute())
            rows = page.data or []
            ops.extend(rows)
            if len(rows) == 0:
                break
            offset += len(rows)

        if not ops:
            return 0

        # Build job_no → contact_email map from qb_quotes
        job_nos = list({r['job_no'] for r in ops if r.get('job_no')})
        quote_map: dict[str, str] = {}
        for i in range(0, len(job_nos), 500):
            batch_jobs = job_nos[i:i + 500]
            q_result = _execute_with_retry(lambda b=batch_jobs: self._supabase.table('qb_quotes').select(
                'job_no, contact_email'
            ).eq('client_id', self._client_id).in_('job_no', b).execute())
            for q in (q_result.data or []):
                if q.get('job_no') and q.get('contact_email') and q['job_no'] not in quote_map:
                    quote_map[q['job_no']] = q['contact_email']

        # Batch writes via batch_update_qb_contact_emails RPC (migration 072)
        # rather than 1 UPDATE per op. Chunk at 100 to keep RPC payloads small.
        WRITE_CHUNK = 100
        pending: list[dict] = []
        for op in ops:
            email = quote_map.get(op.get('job_no'))
            if email:
                pending.append({'id': op['id'], 'contact_email': email})

        updated = 0
        for i in range(0, len(pending), WRITE_CHUNK):
            chunk = pending[i:i + WRITE_CHUNK]
            try:
                resp = _execute_with_retry(lambda c=chunk: (
                    self._supabase.rpc('batch_update_qb_contact_emails', {'p_updates': c}).execute()
                ))
                # RPC returns INTEGER count
                updated += int(resp.data) if resp and resp.data is not None else len(chunk)
            except Exception as ex:
                logger.warning(f"[Enrich] contact_email batch update failed ({len(chunk)} rows): {ex}")

        logger.info(f"[Enrich] contact_email populated for {updated}/{len(ops)} operations")
        return updated

    def _join_factory_rush(self) -> int:
        """
        Set factory_rush=TRUE on qb_operations where linked qb_jobs.factory_rush_level IS NOT NULL.
        qb_operations.job_no → qb_jobs.job_no → qb_jobs.factory_rush_level
        Only processes rows where factory_rush is currently FALSE and job_no is set.
        """
        # Fetch ALL ops needing rush check (paginated)
        all_ops: list[dict] = []
        offset = 0
        while True:
            page = _execute_with_retry(lambda o=offset: self._supabase.table('qb_operations').select(
                'id, job_no'
            ).eq('client_id', self._client_id).eq('factory_rush', False).not_.is_(
                'job_no', 'null'
            ).range(o, o + 999).execute())
            rows = page.data or []
            all_ops.extend(rows)
            if len(rows) == 0:
                break
            offset += len(rows)

        ops = all_ops
        if not ops:
            return 0

        # Build job_no → factory_rush from qb_jobs
        job_nos = list({r['job_no'] for r in ops if r.get('job_no')})
        rush_job_nos: set[str] = set()
        for i in range(0, len(job_nos), 500):
            batch_jobs = job_nos[i:i + 500]
            j_result = _execute_with_retry(lambda b=batch_jobs: self._supabase.table('qb_jobs').select(
                'job_no, factory_rush_level'
            ).eq('client_id', self._client_id).in_('job_no', b).execute())
            for j in (j_result.data or []):
                if j.get('job_no') and j.get('factory_rush_level'):
                    rush_job_nos.add(j['job_no'])

        # Batch the update — since factory_rush is a constant TRUE for every
        # matching op, a single PostgREST .update().in_(ids) call per chunk is
        # equivalent to one SQL UPDATE. Does NOT need a dedicated RPC.
        to_update_ids = [op['id'] for op in ops if op.get('job_no') in rush_job_nos]
        CHUNK = 500  # Supabase .in_() supports large arrays but keep chunks reasonable
        updated = 0
        for i in range(0, len(to_update_ids), CHUNK):
            ids_chunk = to_update_ids[i:i + CHUNK]
            try:
                _execute_with_retry(lambda ids=ids_chunk: (
                    self._supabase.table('qb_operations').update({
                        'factory_rush': True
                    }).in_('id', ids).execute()
                ))
                updated += len(ids_chunk)
            except Exception as ex:
                logger.warning(f"[Enrich] factory_rush batch update failed ({len(ids_chunk)} rows): {ex}")

        logger.info(f"[Enrich] factory_rush set for {updated} operations")
        return updated

    async def match_operations_to_companies(self) -> int:
        """
        Resolve qb_operations.matched_company_id via:
        qb_operations.qb_customer_id → qb_customers.customer_key_id → qb_customers.matched_company_id

        Note: qb_operations.qb_customer_id stores the Customer ID (key) value (field 92),
        NOT the Record ID# (field 3). Must join on customer_key_id.
        """
        # Fetch ALL unmatched operations (paginated — can be 100K+)
        unmatched: list[dict] = []
        offset = 0
        while True:
            ops_page = _execute_with_retry(lambda o=offset: self._supabase.table('qb_operations').select(
                'id, qb_customer_id'
            ).eq('client_id', self._client_id).is_(
                'matched_company_id', 'null'
            ).range(o, o + 999).execute())
            rows = [r for r in (ops_page.data or []) if r.get('qb_customer_id')]
            unmatched.extend(rows)
            if len(ops_page.data or []) == 0:
                break
            offset += len(ops_page.data or [])

        if not unmatched:
            return 0

        # Fetch ALL matched qb_customers (paginated)
        # Use customer_key_id (field 92) for joining — this is what child tables reference
        customer_map: dict = {}  # customer_key_id → matched_company_id
        offset = 0
        while True:
            cust_page = _execute_with_retry(lambda o=offset: self._supabase.table('qb_customers').select(
                'customer_key_id, matched_company_id'
            ).eq('client_id', self._client_id).not_.is_(
                'matched_company_id', 'null'
            ).range(o, o + 999).execute())
            rows = cust_page.data or []
            for r in rows:
                key_id = r.get('customer_key_id') or ''
                if key_id and r.get('matched_company_id'):
                    customer_map[str(key_id)] = r['matched_company_id']
            if len(rows) == 0:
                break
            offset += len(rows)

        matched = 0
        for op in unmatched:
            company_id = customer_map.get(str(op['qb_customer_id']))
            if company_id:
                _execute_with_retry(lambda cid=company_id, oid=op['id']: (
                    self._supabase.table('qb_operations').update({
                        'matched_company_id': cid
                    }).eq('id', oid).execute()
                ))
                matched += 1

        logger.info(f"Matched {matched}/{len(unmatched)} QB operations to companies")
        return matched

    async def _upsert_records(
        self, table_name: str, records: list[dict], mapping: dict[str, str],
        required_fields: list[str] | None = None,
    ) -> int:
        """Map QB records and upsert into Supabase.

        The mapping/coercion step runs synchronously (CPU-bound), then the
        batch-upsert loop is offloaded to a thread so the event loop stays
        free for other requests during the potentially long write phase.
        """
        now = datetime.now(timezone.utc).isoformat()
        rows = []
        skipped = 0

        for record in records:
            mapped = QuickbaseClient.map_record(record, mapping)
            # QB returns integers as floats (e.g. 9999.0) — coerce whole floats to int
            # QB returns empty strings for unset date/numeric fields — coerce to None
            for k, v in list(mapped.items()):
                if isinstance(v, float) and v == int(v):
                    mapped[k] = int(v)
                elif v == '':
                    mapped[k] = None
                elif isinstance(v, str):
                    # Strip null bytes — Postgres text columns reject \u0000
                    mapped[k] = v.replace('\x00', '')
            # Skip rows missing any required (NOT NULL) field
            if required_fields and any(mapped.get(f) is None for f in required_fields):
                skipped += 1
                continue
            mapped['client_id'] = self._client_id
            mapped['synced_at'] = now
            rows.append(mapped)

        if skipped:
            logger.warning(f"Skipped {skipped} {table_name} records with missing required fields")

        # Offload blocking Supabase batch-upsert loop to thread pool so the
        # async event loop is not blocked during large syncs (e.g. 80K SLIs)
        def _do_upsert():
            import time as _time
            total = 0
            consecutive_failures = 0
            MAX_CONSECUTIVE_FAILURES = 3
            num_batches = (len(rows) + UPSERT_BATCH_SIZE - 1) // UPSERT_BATCH_SIZE
            for i in range(0, len(rows), UPSERT_BATCH_SIZE):
                batch = rows[i:i + UPSERT_BATCH_SIZE]
                batch_num = i // UPSERT_BATCH_SIZE + 1
                try:
                    _execute_with_retry(lambda b=batch: self._supabase.table(table_name).upsert(
                        b, on_conflict='client_id,qb_record_id'
                    ).execute())
                    total += len(batch)
                    consecutive_failures = 0
                except Exception as e:
                    logger.warning(f"Batch {batch_num}/{num_batches} failed for {table_name}: {e}")
                    # Retry once after longer pause
                    _time.sleep(2)
                    try:
                        _execute_with_retry(lambda b=batch: self._supabase.table(table_name).upsert(
                            b, on_conflict='client_id,qb_record_id'
                        ).execute())
                        total += len(batch)
                        consecutive_failures = 0
                    except Exception as e2:
                        logger.error(f"Batch {batch_num} permanently failed: {e2}")
                        consecutive_failures += 1
                        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                            raise RuntimeError(
                                f"Aborting {table_name} upsert after {consecutive_failures} "
                                f"consecutive batch failures. Last error: {e2}"
                            ) from e2
                # Throttle: small pause every 10 batches to avoid connection exhaustion
                if batch_num % 10 == 0:
                    _time.sleep(0.5)
                    if batch_num % 100 == 0:
                        logger.info(f"  {table_name}: {total}/{len(rows)} upserted...")
            return total

        total = await asyncio.to_thread(_do_upsert)
        logger.info(f"Upserted {total} records into {table_name}")
        return total

    async def match_companies_via_unique_emails(self) -> dict:
        """Pass 0: Match QB customers to SB companies via QB Unique Emails.

        Chain: customer_contacts.email_address = qb_unique_emails.email
               links SB company (via customer_company_id) to QB customer (via qb_customer_id).

        1:1 pairs (one SB company <-> one QB customer) are auto-written as
        perfect matches. Multi-match cases are staged for human review.
        """
        from collections import defaultdict

        stats = {
            'matched': 0,
            'staged': 0,
            'skipped_no_qb_customer': 0,
            'total_sb_linked': 0,
            'total_qb_linked': 0,
            'total_emails_joined': 0,
        }

        # Step 1: Fetch ALL valid QB unique emails (paginated)
        all_qb_emails: list[dict] = []
        offset = 0
        while True:
            page = _execute_with_retry(lambda o=offset: self._supabase.table('qb_unique_emails').select(
                'email, qb_customer_id'
            ).eq('client_id', self._client_id).eq(
                'hide', False
            ).eq(
                'email_invalid', False
            ).not_.is_(
                'qb_customer_id', 'null'
            ).range(o, o + 999).execute())
            rows = page.data or []
            all_qb_emails.extend(rows)
            if len(rows) == 0:
                break
            offset += len(rows)

        if not all_qb_emails:
            logger.info("No valid QB unique emails found for email-based matching")
            return stats

        # Step 2: Fetch ALL SB contacts with their company links (paginated)
        all_contacts: list[dict] = []
        offset = 0
        while True:
            page = _execute_with_retry(lambda o=offset: self._supabase.table('customer_contacts').select(
                'email_address, customer_company_id'
            ).eq('client_id', self._client_id).not_.is_(
                'customer_company_id', 'null'
            ).range(o, o + 999).execute())
            rows = page.data or []
            all_contacts.extend(rows)
            if len(rows) == 0:
                break
            offset += len(rows)

        # Step 3: Build bidirectional maps via email join
        email_to_qb: dict[str, set] = defaultdict(set)
        for ue in all_qb_emails:
            email = (ue.get('email') or '').strip().lower()
            qb_cid = ue.get('qb_customer_id')
            if email and qb_cid:
                email_to_qb[email].add(str(qb_cid).strip())

        email_to_sb: dict[str, set] = defaultdict(set)
        for contact in all_contacts:
            email = (contact.get('email_address') or '').strip().lower()
            company_id = contact.get('customer_company_id')
            if email and company_id:
                email_to_sb[email].add(company_id)

        # Load internal domains to exclude from matching (e.g. carbon8.com.au)
        internal_domains: set[str] = set()
        try:
            id_resp = _execute_with_retry(lambda: self._supabase.table('internal_domains').select(
                'domain'
            ).eq('client_id', self._client_id).execute())
            internal_domains = {(r['domain'] or '').strip().lower() for r in (id_resp.data or [])}
            if internal_domains:
                logger.info(f"Email match: excluding {len(internal_domains)} internal domains: {internal_domains}")
        except Exception as e:
            logger.warning(f"Could not load internal_domains: {e}")

        sb_to_qb: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
        qb_to_sb: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
        raw_shared = set(email_to_qb.keys()) & set(email_to_sb.keys())
        shared_emails = {e for e in raw_shared if e.split('@')[-1] not in internal_domains}
        if len(raw_shared) != len(shared_emails):
            logger.info(f"Email match: filtered {len(raw_shared) - len(shared_emails)} internal-domain emails from {len(raw_shared)} shared")
        stats['total_emails_joined'] = len(shared_emails)

        for email in shared_emails:
            for sb_cid in email_to_sb[email]:
                for qb_cid in email_to_qb[email]:
                    sb_to_qb[sb_cid][qb_cid].append(email)
                    qb_to_sb[qb_cid][sb_cid].append(email)

        stats['total_sb_linked'] = len(sb_to_qb)
        stats['total_qb_linked'] = len(qb_to_sb)

        logger.info(
            f"Email join: {len(shared_emails)} shared emails, "
            f"{len(sb_to_qb)} SB companies linked, {len(qb_to_sb)} QB customers linked"
        )

        if not sb_to_qb:
            return stats

        # Step 4: Classify 1:1 pairs vs multi-match
        perfect_pairs: list[tuple[str, str, list[str]]] = []
        multi_match_pairs: list[tuple[str, str, list[str]]] = []

        for sb_cid, qb_map in sb_to_qb.items():
            if len(qb_map) == 1:
                qb_cid = next(iter(qb_map))
                if len(qb_to_sb.get(qb_cid, {})) == 1:
                    perfect_pairs.append((sb_cid, qb_cid, qb_map[qb_cid]))
                    continue
            for qb_cid, emails in qb_map.items():
                multi_match_pairs.append((sb_cid, qb_cid, emails))

        logger.info(f"Classified: {len(perfect_pairs)} perfect 1:1 pairs, {len(multi_match_pairs)} multi-match pairs")

        # Step 5: Resolve QB customer IDs to UUIDs (index by both record_id and customer_key_id)
        qb_by_record_id: dict[str, dict] = {}
        qb_by_key_id: dict[str, dict] = {}
        offset = 0
        while True:
            page = _execute_with_retry(lambda o=offset: self._supabase.table('qb_customers').select(
                'id, qb_record_id, customer_key_id, customer_code, customer_name'
            ).eq('client_id', self._client_id).range(o, o + 999).execute())
            rows = page.data or []
            for r in rows:
                rid = r.get('qb_record_id')
                kid = r.get('customer_key_id')
                if rid:
                    qb_by_record_id[str(rid)] = r
                if kid:
                    qb_by_key_id[str(kid)] = r
            if len(rows) == 0:
                break
            offset += len(rows)

        def _resolve_qb_customer(qb_customer_id: str) -> dict | None:
            try:
                norm_id = str(int(float(qb_customer_id)))
            except (ValueError, TypeError):
                norm_id = str(qb_customer_id)
            return qb_by_record_id.get(norm_id) or qb_by_key_id.get(norm_id)

        # Step 6: Build payloads for perfect matches (auto-write)
        now_iso = datetime.now(timezone.utc).isoformat()
        matches_payload: list[dict] = []

        for sb_cid, qb_cid, emails in perfect_pairs:
            qb_cust = _resolve_qb_customer(qb_cid)
            if not qb_cust:
                stats['skipped_no_qb_customer'] += 1
                continue
            matches_payload.append({
                'company_id': sb_cid,
                'qb_customer_uuid': qb_cust['id'],
                'qb_record_id': qb_cust.get('qb_record_id'),
                'qb_customer_code': qb_cust.get('customer_code'),
                'match_method': 'email_lookup',
                'qb_customer_name': qb_cust.get('customer_name'),
            })

        stats['matched'] = await self._rpc_batch_write_matches(matches_payload, now_iso)

        # Track matched QB customer UUIDs for downstream passes
        self._email_matched_qb_ids = {m['qb_customer_uuid'] for m in matches_payload}

        # Step 7: Stage multi-match cases for human review
        staged_batch: list[dict] = []
        for sb_cid, qb_cid, emails in multi_match_pairs:
            qb_cust = _resolve_qb_customer(qb_cid)
            if not qb_cust:
                continue
            staged_batch.append({
                'client_id': self._client_id,
                'sb_company_id': sb_cid,
                'sb_company_name': None,
                'qb_record_id': qb_cust.get('qb_record_id'),
                'qb_customer_id': qb_cust.get('qb_record_id'),
                'qb_name': qb_cust.get('customer_name'),
                'match_score': 85,
                'match_method': 'email_multi_match',
            })

        if staged_batch:
            # Dedup by (qb_record_id, sb_company_id) — email fan-out can produce duplicates
            seen_keys: set[tuple] = set()
            deduped: list[dict] = []
            for row in staged_batch:
                key = (row['qb_record_id'], row['sb_company_id'])
                if key not in seen_keys:
                    seen_keys.add(key)
                    deduped.append(row)
            if len(staged_batch) != len(deduped):
                logger.info(f"Email multi-match: deduped {len(staged_batch)} -> {len(deduped)} candidates")
            staged_batch = deduped

            try:
                _execute_with_retry(lambda: self._supabase.table('qb_match_candidates').delete().eq(
                    'client_id', self._client_id
                ).eq('reviewed', False).execute())
            except Exception as e:
                logger.warning(f"Failed to clear stale unreviewed candidates: {e}")
            for i in range(0, len(staged_batch), UPSERT_BATCH_SIZE):
                batch = staged_batch[i:i + UPSERT_BATCH_SIZE]
                try:
                    _execute_with_retry(lambda b=batch: self._supabase.table(
                        'qb_match_candidates'
                    ).insert(b).execute())
                except Exception as e:
                    logger.warning(f"Failed to stage email multi-match batch: {e}")
            stats['staged'] = len(staged_batch)

        # Track staged record IDs so name-matching passes skip them
        self._email_staged_qb_record_ids = {s['qb_record_id'] for s in staged_batch if s.get('qb_record_id')}

        logger.info(
            f"Email matching complete: {stats['matched']} auto-matched (1:1), "
            f"{stats['staged']} staged (multi-match), "
            f"{stats['skipped_no_qb_customer']} skipped (QB customer not found)"
        )
        return stats

    async def match_to_companies(self) -> dict:
        """Match qb_customers → customer_companies by name.

        Pass 1 — Exact normalised name → AUTO-PROMOTED (high confidence)
        Pass 2 — Email domain root → staged for review
        Pass 3 — Fuzzy name via rapidfuzz → staged for review

        Returns dict with per-pass counts.
        """
        stats = {'pass1_matched': 0, 'pass2_staged': 0, 'pass3_staged': 0, 'unmatched': 0, 'total': 0}

        # ── Fetch ALL unmatched QB customers (paginated) ─────────────────────
        unmatched: list[dict] = []
        offset = 0
        while True:
            qb_result = _execute_with_retry(lambda o=offset: self._supabase.table('qb_customers').select(
                'id, qb_record_id, customer_name, customer_code'
            ).eq('client_id', self._client_id).is_(
                'matched_company_id', 'null'
            ).range(o, o + 999).execute())
            rows = qb_result.data or []
            unmatched.extend(rows)
            if len(rows) == 0:
                break
            offset += len(rows)

        # Filter out QB customers already handled by email/contact chain passes
        if hasattr(self, '_email_staged_qb_record_ids') and self._email_staged_qb_record_ids:
            unmatched = [qc for qc in unmatched
                         if qc.get('qb_record_id') not in self._email_staged_qb_record_ids]

        logger.info(f"Fetched {len(unmatched)} unmatched QB customers for name matching")
        if not unmatched:
            return stats

        # ── Fetch all SB companies (paginated) ───────────────────────────────
        all_companies = self._fetch_all_companies()

        # ── Build lookup structures ───────────────────────────────────────────
        sb_by_norm: dict[str, dict] = {}
        sb_by_domain_root: dict[str, dict] = {}

        for c in all_companies:
            if not c.get('company_name'):
                continue
            norm = _normalise(c['company_name'])
            if norm and norm not in sb_by_norm:
                sb_by_norm[norm] = c
            for root in _extract_domain_roots(c.get('email_domains')):
                if root not in sb_by_domain_root:
                    sb_by_domain_root[root] = c

        now_iso = datetime.now(timezone.utc).isoformat()
        pass2_remaining = []
        pass3_remaining = []

        # Clear stale name-based candidates only (preserve email/contact chain staged ones)
        try:
            _execute_with_retry(lambda: self._supabase.table('qb_match_candidates').delete().eq(
                'client_id', self._client_id
            ).eq('reviewed', False).in_(
                'match_method', ['exact_name', 'domain_root', 'fuzzy']
            ).execute())
        except Exception as e:
            logger.warning(f"Failed to clear stale candidates: {e}")

        staged_batch: list[dict] = []
        pass1_matches: list[dict] = []

        # ── Pass 1: Exact normalised name → AUTO-PROMOTE ─────────────────────
        for qb_cust in unmatched:
            qb_norm = _normalise(qb_cust.get('customer_name'))
            if not qb_norm:
                pass2_remaining.append(qb_cust)
                continue

            sb_match = sb_by_norm.get(qb_norm)
            if sb_match:
                pass1_matches.append({
                    'company_id': sb_match['id'],
                    'qb_customer_uuid': qb_cust['id'],
                    'qb_record_id': qb_cust.get('qb_record_id'),
                    'qb_customer_code': qb_cust.get('customer_code'),
                    'match_method': 'exact_name',
                    'qb_customer_name': qb_cust.get('customer_name'),
                })
                stats['pass1_matched'] += 1
            else:
                pass2_remaining.append(qb_cust)

        if pass1_matches:
            written = await self._rpc_batch_write_matches(pass1_matches, now_iso)
            logger.info(f"Pass 1 (exact name): auto-promoted {written}/{len(pass1_matches)} matches")

        # ── Pass 2: Email domain root → stage ────────────────────────────────
        for qb_cust in pass2_remaining:
            qb_norm = _normalise(qb_cust.get('customer_name'))
            if not qb_norm:
                pass3_remaining.append(qb_cust)
                continue

            matched = False
            for root, sb_company in sb_by_domain_root.items():
                if root in qb_norm:
                    staged_batch.append({
                        'client_id': self._client_id,
                        'sb_company_id': sb_company['id'],
                        'sb_company_name': sb_company.get('company_name'),
                        'qb_record_id': qb_cust.get('qb_record_id'),
                        'qb_customer_id': qb_cust.get('qb_record_id'),
                        'qb_name': qb_cust.get('customer_name'),
                        'match_score': 65,
                        'match_method': 'domain_root',
                    })
                    stats['pass2_staged'] += 1
                    matched = True
                    break

            if not matched:
                pass3_remaining.append(qb_cust)

        # ── Pass 3: Fuzzy name match → stage ─────────────────────────────────
        try:
            from rapidfuzz import fuzz, process as rf_process

            sb_norm_names = list(sb_by_norm.keys())
            total_pass3 = len(pass3_remaining)
            logger.info(f"Pass 3 (fuzzy): processing {total_pass3} remaining customers against {len(sb_norm_names)} SB names")

            for idx, qb_cust in enumerate(pass3_remaining):
                qb_norm = _normalise(qb_cust.get('customer_name'))
                if not qb_norm or len(qb_norm) < 4:
                    stats['unmatched'] += 1
                    continue

                result = rf_process.extractOne(
                    qb_norm,
                    sb_norm_names,
                    scorer=fuzz.token_sort_ratio,
                    score_cutoff=FUZZY_SCORE_THRESHOLD,
                )

                if (idx + 1) % 1000 == 0:
                    logger.info(f"Pass 3 progress: {idx + 1}/{total_pass3} "
                                f"({stats['pass3_staged']} staged so far)")

                if result:
                    matched_norm, score, _idx = result
                    sb_company = sb_by_norm[matched_norm]
                    staged_batch.append({
                        'client_id': self._client_id,
                        'sb_company_id': sb_company['id'],
                        'sb_company_name': sb_company.get('company_name'),
                        'qb_record_id': qb_cust.get('qb_record_id'),
                        'qb_customer_id': qb_cust.get('qb_record_id'),
                        'qb_name': qb_cust.get('customer_name'),
                        'match_score': round(score * 0.75),
                        'match_method': 'fuzzy',
                    })
                    stats['pass3_staged'] += 1
                else:
                    stats['unmatched'] += 1

        except ImportError:
            logger.warning("rapidfuzz not installed — skipping Pass 3 fuzzy matching")
            stats['unmatched'] += len(pass3_remaining)

        # Batch insert all candidates (Pass 1+2+3) at once
        if staged_batch:
            logger.info(f"Staging {len(staged_batch)} match candidates (Pass 1+2+3) for review")
            for i in range(0, len(staged_batch), UPSERT_BATCH_SIZE):
                batch = staged_batch[i:i + UPSERT_BATCH_SIZE]
                try:
                    _execute_with_retry(lambda b=batch: self._supabase.table(
                        'qb_match_candidates'
                    ).insert(b).execute())
                except Exception as e:
                    logger.warning(f"Failed to stage batch {i // UPSERT_BATCH_SIZE + 1}: {e}")

        stats['total'] = stats['pass1_matched'] + stats['pass2_staged'] + stats['pass3_staged']
        logger.info(
            f"Company matching complete: "
            f"Pass 1 (exact)={stats['pass1_matched']} auto-promoted, "
            f"Pass 2 (domain)={stats['pass2_staged']} staged, "
            f"Pass 3 (fuzzy)={stats['pass3_staged']} staged, "
            f"Unmatched={stats['unmatched']}"
        )
        return stats

    async def _batch_write_matches(
        self,
        matches: list[tuple[dict, dict, str]],
        now_iso: str,
    ):
        """Batch-write confirmed matches via RPC.

        Each match is (qb_cust, sb_company, method). Converts to RPC payload format.
        """
        payload = []
        for qb_cust, sb_company, method in matches:
            payload.append({
                'company_id': sb_company.get('id'),
                'qb_customer_uuid': qb_cust.get('id'),
                'qb_record_id': qb_cust.get('qb_record_id'),
                'qb_customer_code': qb_cust.get('customer_code'),
                'match_method': method,
            })

        written = await self._rpc_batch_write_matches(payload, now_iso)
        logger.info(f"Match write complete: {written}/{len(matches)} matches written")

    async def _rpc_batch_write_matches(
        self,
        matches: list[dict],
        now_iso: str,
        batch_size: int = 500,
    ) -> int:
        """Write matches via the batch_write_qb_matches RPC function.

        Each match dict: {company_id, qb_customer_uuid, qb_record_id, qb_customer_code, match_method}
        Falls back to individual updates if RPC is not available (migration not run).
        """
        total = len(matches)
        if not total:
            return 0

        written = 0

        # Try RPC batch write first (single DB round-trip per batch)
        try:
            for i in range(0, total, batch_size):
                if self.cancelled:
                    logger.info(f"Batch match write cancelled at {i}/{total}")
                    break

                batch = matches[i:i + batch_size]
                result = _execute_with_retry(lambda b=batch, n=now_iso: (
                    self._supabase.rpc('batch_write_qb_matches', {
                        'p_client_id': self._client_id,
                        'p_matches': b,
                        'p_now': n,
                    }).execute()
                ))
                batch_written = result.data if isinstance(result.data, int) else len(batch)
                written += batch_written
                logger.info(f"RPC batch match write: {i + len(batch)}/{total} ({written} written)")

            return written

        except Exception as rpc_err:
            logger.warning(f"RPC batch_write_qb_matches failed, falling back to individual writes: {rpc_err}")

        # Fallback: individual updates (slower but works without migration 050)
        import time as _time

        def _do_individual():
            nonlocal written
            for i, m in enumerate(matches):
                if self._cancel and self._cancel.is_set():
                    break
                try:
                    _execute_with_retry(lambda m=m: (
                        self._supabase.table('qb_customers').update({
                            'matched_company_id': m['company_id']
                        }).eq('id', m['qb_customer_uuid']).execute()
                    ))
                    # Only write match metadata if not already email_lookup (higher confidence)
                    if m['match_method'] == 'email_lookup':
                        _execute_with_retry(lambda m=m: (
                            self._supabase.table('customer_companies').update({
                                'qb_customer_id': m['qb_record_id'],
                                'qb_customer_code': m['qb_customer_code'],
                                'qb_match_method': m['match_method'],
                                'qb_matched_at': now_iso,
                            }).eq('id', m['company_id']).execute()
                        ))
                    else:
                        # Name-based: only set if not already linked
                        _execute_with_retry(lambda m=m: (
                            self._supabase.table('customer_companies').update({
                                'qb_customer_id': m['qb_record_id'],
                                'qb_customer_code': m['qb_customer_code'],
                                'qb_match_method': m['match_method'],
                                'qb_matched_at': now_iso,
                            }).eq('id', m['company_id']).is_('qb_match_method', 'null').execute()
                        ))
                    written += 1
                except Exception as e:
                    logger.warning(f"Individual match write failed: {e}")

                if (i + 1) % 500 == 0:
                    logger.info(f"Fallback match write: {i + 1}/{total} ({written} written)")
                    _time.sleep(0.3)

        await asyncio.to_thread(_do_individual)
        return written

    def _fetch_all_companies(self) -> list[dict]:
        """Fetch all customer_companies for this client (paginated)."""
        all_companies = []
        offset = 0
        while True:
            company_batch = _execute_with_retry(lambda o=offset: self._supabase.table('customer_companies').select(
                'id, company_name, email_domains'
            ).eq('client_id', self._client_id).range(o, o + 999).execute())
            rows = company_batch.data or []
            all_companies.extend(rows)
            if len(rows) == 0:
                break
            offset += len(rows)
        return all_companies

    async def match_to_contacts(self) -> int:
        """Match qb_contacts to customer_contacts by email address."""
        # Get ALL unmatched QB contacts with emails (paginated)
        all_unmatched: list[dict] = []
        offset = 0
        while True:
            qb_result = _execute_with_retry(lambda o=offset: self._supabase.table('qb_contacts').select(
                'id, email'
            ).eq('client_id', self._client_id).is_(
                'matched_contact_id', 'null'
            ).range(o, o + 999).execute())
            rows = qb_result.data or []
            all_unmatched.extend(rows)
            if len(rows) == 0:
                break
            offset += len(rows)

        unmatched = [r for r in all_unmatched if r.get('email')]
        logger.info(f"Fetched {len(unmatched)} unmatched QB contacts for matching")
        if not unmatched:
            return 0

        # Get all contacts for this client
        all_contacts = []
        offset = 0
        while True:
            contact_batch = _execute_with_retry(lambda o=offset: self._supabase.table('customer_contacts').select(
                'id, email_address'
            ).eq('client_id', self._client_id).range(o, o + 999).execute())
            rows = contact_batch.data or []
            all_contacts.extend(rows)
            if len(rows) == 0:
                break
            offset += len(rows)

        contacts_by_email = {
            c['email_address'].strip().lower(): c['id']
            for c in all_contacts
            if c.get('email_address')
        }

        matched = 0
        total_to_match = len(unmatched)
        for idx, qb_contact in enumerate(unmatched):
            email = (qb_contact.get('email') or '').strip().lower()
            contact_id = contacts_by_email.get(email)

            if contact_id:
                _execute_with_retry(lambda cid=contact_id, qid=qb_contact['id']: (
                    self._supabase.table('qb_contacts').update({
                        'matched_contact_id': cid
                    }).eq('id', qid).execute()
                ))
                matched += 1

            if (idx + 1) % 2000 == 0:
                logger.info(f"Contact matching progress: {idx + 1}/{total_to_match} "
                            f"({matched} matched so far)")

        logger.info(f"Matched {matched}/{total_to_match} QB contacts by email")
        return matched

    async def match_customers_via_contacts(self) -> int:
        """
        Match QB customers to companies via email-matched contacts.

        Flow: qb_contacts (matched by email) → customer_contacts → customer_company_id
        → set qb_customers.matched_company_id for the parent QB customer.

        This catches cases where company name matching fails but we have
        email-level links through contacts.
        """
        # Get QB contacts that are matched but whose parent QB customer is NOT matched
        # QB contacts have a customer_id field linking to QB customers
        try:
            # Get all matched QB contacts with their QB customer link (paginated)
            all_matched_contacts: list[dict] = []
            offset = 0
            while True:
                qb_contacts_page = _execute_with_retry(lambda o=offset: self._supabase.table('qb_contacts').select(
                    'id, matched_contact_id, qb_customer_id'
                ).eq('client_id', self._client_id).not_.is_(
                    'matched_contact_id', 'null'
                ).range(o, o + 999).execute())
                rows = qb_contacts_page.data or []
                all_matched_contacts.extend(rows)
                if len(rows) == 0:
                    break
                offset += len(rows)

            if not all_matched_contacts:
                return 0

            # Get all unmatched QB customers (paginated)
            all_unmatched_custs: list[dict] = []
            offset = 0
            while True:
                unmatched_page = _execute_with_retry(lambda o=offset: self._supabase.table('qb_customers').select(
                    'id, qb_record_id, customer_key_id'
                ).eq('client_id', self._client_id).is_(
                    'matched_company_id', 'null'
                ).range(o, o + 999).execute())
                rows = unmatched_page.data or []
                all_unmatched_custs.extend(rows)
                if len(rows) == 0:
                    break
                offset += len(rows)

            if not all_unmatched_custs:
                return 0

            # Build customer_key_id → QB customer UUID lookup
            # qb_contacts.qb_customer_id stores the Customer ID (key) = field 92, NOT Record ID#
            qb_cust_by_key = {str(c['customer_key_id']): c['id'] for c in all_unmatched_custs if c.get('customer_key_id')}

            # Build contact_id → company_id lookup from customer_contacts
            contact_ids = [c['matched_contact_id'] for c in all_matched_contacts if c.get('matched_contact_id')]
            if not contact_ids:
                return 0

            contact_company_map = {}
            for i in range(0, len(contact_ids), 500):
                batch = contact_ids[i:i+500]
                resp = _execute_with_retry(lambda b=batch: self._supabase.table('customer_contacts').select(
                    'id, customer_company_id'
                ).in_('id', b).execute())
                for c in (resp.data or []):
                    if c.get('customer_company_id'):
                        contact_company_map[c['id']] = c['customer_company_id']

            logger.info(
                f"Chain match: {len(all_matched_contacts)} matched contacts, "
                f"{len(all_unmatched_custs)} unmatched customers, "
                f"{len(contact_company_map)} contacts with companies"
            )

            # Build bidirectional maps: QB customer key -> {company_id} and reverse
            from collections import defaultdict
            chain_qb_to_company: dict[str, set] = defaultdict(set)
            chain_company_to_qb: dict[str, set] = defaultdict(set)

            for qb_contact in all_matched_contacts:
                contact_id = qb_contact.get('matched_contact_id')
                customer_id = qb_contact.get('qb_customer_id')
                if not contact_id or not customer_id:
                    continue

                company_id = contact_company_map.get(contact_id)
                if not company_id:
                    continue

                try:
                    normalized_key = str(int(float(customer_id)))
                except (ValueError, TypeError):
                    normalized_key = str(customer_id)

                qb_cust_uuid = qb_cust_by_key.get(normalized_key)
                if not qb_cust_uuid:
                    continue

                # Skip QB customers already matched by email
                if qb_cust_uuid in self._email_matched_qb_ids:
                    continue

                chain_qb_to_company[normalized_key].add(company_id)
                chain_company_to_qb[company_id].add(normalized_key)

            # Classify 1:1 pairs vs multi-match
            perfect_matches: list[dict] = []
            staged_batch: list[dict] = []
            matched = 0

            for qb_key, companies in chain_qb_to_company.items():
                qb_cust_uuid = qb_cust_by_key.get(qb_key)
                if not qb_cust_uuid:
                    continue
                # Find the qb_customers row for record_id/code
                qb_row = next((c for c in all_unmatched_custs if c['id'] == qb_cust_uuid), None)
                if not qb_row:
                    continue

                if len(companies) == 1:
                    company_id = next(iter(companies))
                    if len(chain_company_to_qb.get(company_id, set())) == 1:
                        perfect_matches.append({
                            'company_id': company_id,
                            'qb_customer_uuid': qb_cust_uuid,
                            'qb_record_id': qb_row.get('qb_record_id'),
                            'qb_customer_code': None,
                            'match_method': 'contact_chain',
                            'qb_customer_name': qb_row.get('customer_name'),
                        })
                        continue

                # Multi-match: stage for review
                for company_id in companies:
                    staged_batch.append({
                        'client_id': self._client_id,
                        'sb_company_id': company_id,
                        'sb_company_name': None,
                        'qb_record_id': qb_row.get('qb_record_id'),
                        'qb_customer_id': qb_row.get('qb_record_id'),
                        'qb_name': None,
                        'match_score': 75,
                        'match_method': 'contact_chain',
                    })

            # Write perfect matches via RPC
            if perfect_matches:
                now_iso = datetime.now(timezone.utc).isoformat()
                matched = await self._rpc_batch_write_matches(perfect_matches, now_iso)
                self._email_matched_qb_ids.update(m['qb_customer_uuid'] for m in perfect_matches)

            # Stage multi-match cases
            staged = 0
            if staged_batch:
                try:
                    _execute_with_retry(lambda: self._supabase.table('qb_match_candidates').delete().eq(
                        'client_id', self._client_id
                    ).eq('reviewed', False).eq('match_method', 'contact_chain').execute())
                except Exception as e:
                    logger.warning(f"Failed to clear stale contact chain candidates: {e}")
                for i in range(0, len(staged_batch), UPSERT_BATCH_SIZE):
                    batch = staged_batch[i:i + UPSERT_BATCH_SIZE]
                    try:
                        _execute_with_retry(lambda b=batch: self._supabase.table(
                            'qb_match_candidates'
                        ).insert(b).execute())
                    except Exception as e:
                        logger.warning(f"Failed to stage contact chain batch: {e}")
                staged = len(staged_batch)
                self._email_staged_qb_record_ids.update(
                    s['qb_record_id'] for s in staged_batch if s.get('qb_record_id')
                )

            logger.info(
                f"Chain match result: {matched} auto-matched (1:1), {staged} staged (multi-match)"
            )
            return matched

        except Exception as e:
            logger.warning(f"match_customers_via_contacts failed: {e}")
            return 0

    async def propagate_qb_data_to_companies(self) -> int:
        """
        After matching, copy QB data to customer_companies enrichment columns.
        Runs on ALL matched QB customers — overwrites financial fields every sync
        so customer_companies always reflects the latest QB state.

        Derives qb_growth_90d from TY/LY and qb_tier from total_revenue if not
        already set in QB. Handles HTML-wrapped recency values.
        """
        # Fetch ALL matched QB customers (paginated)
        all_matched: list[dict] = []
        offset = 0
        while True:
            page = _execute_with_retry(lambda o=offset: self._supabase.table('qb_customers').select(
                'qb_record_id, customer_key_id, customer_code, customer_name, matched_company_id, customer_status, '
                'customer_tier, account_manager, total_invoiced, invoiced_ty, invoiced_ly, '
                'growth_90d, days_since_last_invoice, recency_days, industry'
            ).eq('client_id', self._client_id).not_.is_(
                'matched_company_id', 'null'
            ).range(o, o + 999).execute())
            rows = page.data or []
            all_matched.extend(rows)
            if len(rows) == 0:
                break
            offset += len(rows)

        total_propagate = len(all_matched)
        logger.info(f"Propagating QB data for {total_propagate} matched customers")

        # Group matched QB customers by company_id for dedup (multiple QB
        # customers can map to the same company — pick best: highest revenue)
        by_company: dict[str, dict] = {}
        for qb in all_matched:
            company_id = qb['matched_company_id']
            total = qb.get('total_invoiced')
            tier = qb.get('customer_tier') or _derive_tier(total)
            ty = qb.get('invoiced_ty')
            ly = qb.get('invoiced_ly')
            growth = qb.get('growth_90d') or _derive_growth(ty, ly)
            recency_raw = qb.get('days_since_last_invoice') or qb.get('recency_days')
            recency = _parse_recency_html(recency_raw)
            if recency and recency >= 9999:
                recency = None

            existing = by_company.get(company_id)
            if existing and (existing.get('qb_total_revenue') or 0) > (total or 0):
                continue

            by_company[company_id] = {
                'qb_customer_name': qb.get('customer_name'),
                'qb_customer_type': qb.get('customer_status'),
                'qb_tier': tier,
                'qb_total_revenue': total,
                'qb_invoiced_ty': ty,
                'qb_invoiced_ly': ly,
                'qb_growth_90d': growth,
                'qb_days_since_last_invoice': recency,
                'qb_account_manager': qb.get('account_manager'),
                'qb_customer_id': qb.get('qb_record_id'),
                'qb_customer_code': qb.get('customer_code'),
                'industry': qb.get('industry'),
            }

        items = list(by_company.items())
        total_unique = len(items)
        logger.info(f"Propagating to {total_unique} unique companies (deduped from {total_propagate})")

        # Build batch payload — stringify numeric values for the RPC's TEXT parameters
        batch_payload: list[dict] = []
        for cid, data in items:
            row = {'company_id': cid}
            for k, v in data.items():
                if v is not None:
                    row[k] = str(v) if isinstance(v, (int, float)) else v
            batch_payload.append(row)

        # Try RPC batch propagation (single DB call per 500 companies)
        updated = 0
        batch_size = 500
        try:
            for i in range(0, len(batch_payload), batch_size):
                if self.cancelled:
                    logger.info(f"Propagation cancelled at {i}/{len(batch_payload)}")
                    break
                batch = batch_payload[i:i + batch_size]
                result = _execute_with_retry(lambda b=batch: (
                    self._supabase.rpc('batch_propagate_qb_data', {
                        'p_client_id': self._client_id,
                        'p_data': b,
                    }).execute()
                ))
                batch_updated = result.data if isinstance(result.data, int) else len(batch)
                updated += batch_updated
                logger.info(f"Propagation progress: {i + len(batch)}/{len(batch_payload)} ({updated} updated)")

        except Exception as rpc_err:
            logger.warning(f"RPC batch_propagate_qb_data failed, falling back to individual: {rpc_err}")
            # Fallback: individual updates
            rpc_only_keys = {'qb_customer_name'}
            for idx, (cid, data) in enumerate(items):
                data = {k: v for k, v in data.items() if v is not None and k not in rpc_only_keys}
                if data:
                    try:
                        _execute_with_retry(lambda d=data, c=cid: (
                            self._supabase.table('customer_companies').update(d).eq('id', c).execute()
                        ))
                        updated += 1
                    except Exception as e:
                        logger.warning(f"Propagation failed for {cid}: {e}")
                if (idx + 1) % 500 == 0:
                    logger.info(f"Fallback propagation: {idx + 1}/{total_unique} ({updated} updated)")

        logger.info(f"Propagation complete: {updated}/{total_propagate} companies updated")
        # Invalidate stale analytics cache so next request recomputes with fresh QB data
        if updated > 0:
            try:
                _execute_with_retry(lambda: self._supabase.table('customer_intelligence_cache').delete().eq(
                    'client_id', self._client_id
                ).in_('cache_type', [
                    'strike_rate', 'contact_capability_profile',
                    'seasonality_profile', 'capability_rhythm',
                ]).execute())
                logger.info(f"Invalidated analytics cache for client {self._client_id}")
            except Exception as e:
                logger.warning(f"Cache invalidation failed (non-fatal): {e}")

        logger.info(f"Propagated QB data to {updated} customer_companies")
        return updated

    async def propagate_qb_data_to_contacts(self) -> int:
        """Push QB signals from qb_unique_emails + qb_contacts to customer_contacts.

        Single RPC call — two UPDATE passes on the DB side:
          Pass 1: qb_unique_emails (email match) → qb_customer_type, capabilities, processes
          Pass 2: qb_contacts (matched_contact_id FK) → quotes_count, last_quote_date, recency_days

        Replaces the per-row enrichment loop in extraction_orchestrator.py Step 6.
        """
        try:
            result = _execute_with_retry(lambda: self._supabase.rpc(
                'batch_propagate_qb_data_to_contacts',
                {'p_client_id': self._client_id},
            ).execute())
            count = result.data if isinstance(result.data, int) else 0
            logger.info(f"Propagated QB data to {count} customer_contacts rows")
            return count
        except Exception as e:
            logger.error(f"propagate_qb_data_to_contacts failed: {e}", exc_info=True)
            return 0
