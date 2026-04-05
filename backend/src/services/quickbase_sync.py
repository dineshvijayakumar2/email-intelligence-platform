"""
Quickbase Sync Service — Syncs QB data to local Supabase cache tables.

Handles: Customers, Contacts, Quotes, Jobs, Sales Line Items, Operations.
After sync, matches QB records to existing customer_companies/customer_contacts
using a 3-pass pipeline: exact name → domain root → fuzzy (staging).
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
        # Pass 0: Email-based matching via QB Unique Emails (highest priority)
        email_match_stats = await self.match_companies_via_unique_emails()
        counts['email_match_stats'] = email_match_stats

        # Pass 1-3: Name-based matching for remaining unmatched QB customers
        match_stats = await self.match_to_companies()
        matched_contacts = await self.match_to_contacts()
        matched_via_contacts = await self.match_customers_via_contacts()
        counts['match_stats'] = match_stats
        counts['matched_companies'] = (
            email_match_stats.get('matched', 0)
            + match_stats.get('total', 0)
            + matched_via_contacts
        )
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
    ) -> int:
        """Generic streamed sync: fetch from QB page-by-page and upsert each page immediately.

        Args:
            table_name: Supabase destination table (e.g. 'qb_customers')
            table_key: Config key for the QB table ID (e.g. 'customers_table_id')
            mapping: Field ID → column name mapping
            required_fields: Columns that must be non-NULL (rows without them are skipped)
            page_filter: Optional callable(page_records) → filtered_records, applied per page
        """
        table_id = self._config.get(table_key)
        if not table_id:
            logger.info(f"{table_key} not set — skipping {table_name} sync")
            return 0

        select_fields = QuickbaseClient.get_select_fields(mapping)
        # Resolve the logical table name from the config key (e.g. 'customers_table_id' → 'customers')
        logical_name = table_key.replace('_table_id', '')
        where = None if getattr(self, '_full_sync', False) else self._build_incremental_where(logical_name)

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
        if count:
            self._write_sync_log('operations', count)
        return count

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
        """
        total = 0
        qb_primary = 0
        classifier_used = 0
        offset = 0
        batch_size = 500

        while True:
            result = _execute_with_retry(lambda o=offset: self._supabase.table('qb_operations').select(
                'id, department, operation_name, machine, qb_capability_tag, qb_row_type_tag'
            ).eq('client_id', self._client_id).eq('capability_tags', '[]').range(
                o, o + batch_size - 1
            ).execute())

            rows = result.data or []
            if not rows:
                break

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

                update_data = {
                    'capability_tags':         tags,
                    'has_coating':             result_cls['has_coating'],
                    'has_sewing':              result_cls['has_sewing'],
                    'has_outsource_component': result_cls['has_outsource_component'],
                    'am_rush':                 result_cls['am_rush'],
                    'row_type':                qb_row or result_cls['row_type'],
                }

                try:
                    _execute_with_retry(lambda rid=row['id'], ud=update_data: (
                        self._supabase.table('qb_operations').update(ud).eq('id', rid).execute()
                    ))
                    total += 1
                except Exception as e:
                    logger.warning(f"[Enrich] classify update failed for op {row['id']}: {e}")

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

        updated = 0
        for op in ops:
            email = quote_map.get(op.get('job_no'))
            if email:
                try:
                    _execute_with_retry(lambda oid=op['id'], e=email: (
                        self._supabase.table('qb_operations').update({
                            'contact_email': e
                        }).eq('id', oid).execute()
                    ))
                    updated += 1
                except Exception as ex:
                    logger.warning(f"[Enrich] contact_email update failed for op {op['id']}: {ex}")

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

        updated = 0
        for op in ops:
            if op.get('job_no') in rush_job_nos:
                try:
                    _execute_with_retry(lambda oid=op['id']: (
                        self._supabase.table('qb_operations').update({
                            'factory_rush': True
                        }).eq('id', oid).execute()
                    ))
                    updated += 1
                except Exception as ex:
                    logger.warning(f"[Enrich] factory_rush update failed for op {op['id']}: {ex}")

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
                # Numeric overflow guard: DECIMAL(8,2) columns max at ±999,999.99.
                # Null out values that would cause a "numeric field overflow" error.
                if isinstance(mapped[k], (int, float)) and not isinstance(mapped[k], bool):
                    if abs(mapped[k]) >= 1_000_000:
                        logger.debug(f"Nullifying {k}={mapped[k]} — numeric overflow guard")
                        mapped[k] = None
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

        Chain: customer_contacts.email_address → qb_unique_emails.email
               → qb_unique_emails.qb_customer_id → link to company via contact's customer_company_id

        This is the highest-confidence match method because it's email-based.
        Auto-writes matches (100% confidence).
        """
        stats = {
            'matched': 0,
            'skipped_no_company': 0,
            'skipped_no_qb_customer': 0,
            'multi_customer_conflicts': 0,
            'total_emails_checked': 0,
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

        # Build email → qb_customer_id lookup (lowercased)
        email_to_qb_customer: dict[str, str] = {}
        for ue in all_qb_emails:
            email = (ue.get('email') or '').strip().lower()
            qb_cid = ue.get('qb_customer_id')
            if email and qb_cid:
                email_to_qb_customer[email] = str(qb_cid).strip()

        logger.info(f"Built email→QB customer lookup: {len(email_to_qb_customer)} valid entries")

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

        logger.info(f"Fetched {len(all_contacts)} SB contacts with companies for email matching")

        # Step 3: For each contact email, look up in QB unique emails
        # Build: company_id → {qb_customer_id: contact_count} (to detect conflicts)
        company_to_qb_customers: dict[str, dict[str, int]] = {}

        for contact in all_contacts:
            email = (contact.get('email_address') or '').strip().lower()
            company_id = contact.get('customer_company_id')
            if not email or not company_id:
                continue

            stats['total_emails_checked'] += 1
            qb_customer_id = email_to_qb_customer.get(email)

            if not qb_customer_id:
                continue

            if company_id not in company_to_qb_customers:
                company_to_qb_customers[company_id] = {}
            counts_map = company_to_qb_customers[company_id]
            counts_map[qb_customer_id] = counts_map.get(qb_customer_id, 0) + 1

        # Step 4: Resolve conflicts — majority vote (most contacts wins)
        company_to_best_qb: dict[str, str] = {}
        for company_id, qb_map in company_to_qb_customers.items():
            if len(qb_map) == 1:
                company_to_best_qb[company_id] = next(iter(qb_map))
            else:
                stats['multi_customer_conflicts'] += 1
                best_qb = max(qb_map, key=qb_map.get)
                company_to_best_qb[company_id] = best_qb
                logger.debug(
                    f"Company {company_id} has {len(qb_map)} QB customer matches, "
                    f"picking {best_qb} ({qb_map[best_qb]} contacts)"
                )

        logger.info(
            f"Email lookup resolved {len(company_to_best_qb)} company→QB customer links "
            f"({stats['multi_customer_conflicts']} had conflicts)"
        )

        if not company_to_best_qb:
            return stats

        # Step 5: Build qb_record_id → qb_customers row lookup (need UUID + code)
        qb_customer_map: dict[str, dict] = {}
        offset = 0
        while True:
            page = _execute_with_retry(lambda o=offset: self._supabase.table('qb_customers').select(
                'id, qb_record_id, customer_code'
            ).eq('client_id', self._client_id).range(o, o + 999).execute())
            rows = page.data or []
            for r in rows:
                rid = r.get('qb_record_id')
                if rid:
                    qb_customer_map[str(rid)] = r
            if len(rows) == 0:
                break
            offset += len(rows)

        # Step 6: Build batch payloads and write via RPC
        now_iso = datetime.now(timezone.utc).isoformat()

        matches_payload: list[dict] = []
        for company_id, qb_customer_id in company_to_best_qb.items():
            try:
                normalized_id = str(int(float(qb_customer_id)))
            except (ValueError, TypeError):
                normalized_id = str(qb_customer_id)

            qb_cust = qb_customer_map.get(normalized_id)
            if not qb_cust:
                stats['skipped_no_qb_customer'] += 1
                continue

            matches_payload.append({
                'company_id': company_id,
                'qb_customer_uuid': qb_cust['id'],
                'qb_record_id': qb_cust.get('qb_record_id'),
                'qb_customer_code': qb_cust.get('customer_code'),
                'match_method': 'email_lookup',
            })

        stats['matched'] = await self._rpc_batch_write_matches(matches_payload, now_iso)

        logger.info(
            f"Email-lookup matching complete: {stats['matched']} matched, "
            f"{stats['skipped_no_qb_customer']} skipped (QB customer not in cache), "
            f"{stats['multi_customer_conflicts']} conflicts resolved by majority vote"
        )
        return stats

    async def match_to_companies(self) -> dict:
        """Match qb_customers → customer_companies using a 3-pass pipeline.

        Pass 1 — Exact normalised name (high confidence, auto-write)
        Pass 2 — Email domain root (medium confidence, auto-write with flag)
        Pass 3 — Fuzzy name via rapidfuzz (low confidence, staging only)

        Returns dict with per-pass counts: {pass1, pass2, pass3_staged, unmatched, total}.
        """
        stats = {'pass1': 0, 'pass2': 0, 'pass3_staged': 0, 'unmatched': 0, 'total': 0}

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

        logger.info(f"Fetched {len(unmatched)} unmatched QB customers for matching")
        if not unmatched:
            return stats

        # ── Fetch all SB companies (paginated) ───────────────────────────────
        all_companies = self._fetch_all_companies()

        # ── Build lookup structures ───────────────────────────────────────────
        # Normalised SB name → company dict
        sb_by_norm: dict[str, dict] = {}
        # Domain root → company dict (first wins)
        sb_by_domain_root: dict[str, dict] = {}

        for c in all_companies:
            if not c.get('company_name'):
                continue
            norm = _normalise(c['company_name'])
            if norm and norm not in sb_by_norm:
                sb_by_norm[norm] = c
            # Index by domain roots
            for root in _extract_domain_roots(c.get('email_domains')):
                if root not in sb_by_domain_root:
                    sb_by_domain_root[root] = c

        # Normalised QB name → QB row (for fuzzy pass)
        qb_by_norm: dict[str, dict] = {}
        for qb in unmatched:
            norm = _normalise(qb.get('customer_name'))
            if norm:
                qb_by_norm[norm] = qb

        now_iso = datetime.now(timezone.utc).isoformat()
        pass2_remaining = []  # QB customers not matched in pass 1
        pass3_remaining = []  # QB customers not matched in pass 1 or 2

        # Collect matches in memory first, then batch-write at the end
        confirmed_matches: list[tuple[dict, dict, str]] = []  # (qb_cust, sb_company, method)

        # ── Pass 1: Exact normalised name ─────────────────────────────────────
        for qb_cust in unmatched:
            qb_norm = _normalise(qb_cust.get('customer_name'))
            if not qb_norm:
                pass2_remaining.append(qb_cust)
                continue

            sb_match = sb_by_norm.get(qb_norm)
            if sb_match:
                confirmed_matches.append((qb_cust, sb_match, 'exact_name'))
                stats['pass1'] += 1
            else:
                pass2_remaining.append(qb_cust)

        # ── Pass 2: Email domain root ─────────────────────────────────────────
        for qb_cust in pass2_remaining:
            qb_norm = _normalise(qb_cust.get('customer_name'))
            if not qb_norm:
                pass3_remaining.append(qb_cust)
                continue

            matched = False
            for root, sb_company in sb_by_domain_root.items():
                if root in qb_norm:
                    confirmed_matches.append((qb_cust, sb_company, 'domain_root'))
                    stats['pass2'] += 1
                    matched = True
                    break

            if not matched:
                pass3_remaining.append(qb_cust)

        # ── Batch-write Pass 1+2 matches ─────────────────────────────────────
        if confirmed_matches:
            logger.info(f"Writing {len(confirmed_matches)} confirmed matches (Pass 1+2) in batches")
            await self._batch_write_matches(confirmed_matches, now_iso)

        # ── Pass 3: Fuzzy name match (staging only) ───────────────────────────
        # Clear stale unreviewed candidates before inserting fresh ones
        try:
            _execute_with_retry(lambda: self._supabase.table('qb_match_candidates').delete().eq(
                'client_id', self._client_id
            ).eq('reviewed', False).execute())
        except Exception as e:
            logger.warning(f"Failed to clear stale candidates: {e}")

        try:
            from rapidfuzz import fuzz, process as rf_process

            sb_norm_names = list(sb_by_norm.keys())
            staged_batch: list[dict] = []
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
                        'match_score': score,
                        'match_method': 'fuzzy',
                    })
                    stats['pass3_staged'] += 1
                else:
                    stats['unmatched'] += 1

            # Batch insert all fuzzy candidates at once (instead of 1-by-1)
            if staged_batch:
                for i in range(0, len(staged_batch), UPSERT_BATCH_SIZE):
                    batch = staged_batch[i:i + UPSERT_BATCH_SIZE]
                    try:
                        _execute_with_retry(lambda b=batch: self._supabase.table(
                            'qb_match_candidates'
                        ).insert(b).execute())
                    except Exception as e:
                        logger.warning(f"Failed to stage fuzzy batch {i // UPSERT_BATCH_SIZE + 1}: {e}")

        except ImportError:
            logger.warning("rapidfuzz not installed — skipping Pass 3 fuzzy matching")
            stats['unmatched'] += len(pass3_remaining)

        stats['total'] = stats['pass1'] + stats['pass2']
        logger.info(
            f"Company matching complete: "
            f"Pass 1 (exact)={stats['pass1']}, Pass 2 (domain)={stats['pass2']}, "
            f"Pass 3 (staged)={stats['pass3_staged']}, Unmatched={stats['unmatched']}"
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

            # Debug: log sample data to diagnose format mismatches
            sample_contact_ids = [c.get('qb_customer_id') for c in all_matched_contacts[:5] if c.get('qb_customer_id')]
            sample_key_ids = list(qb_cust_by_key.keys())[:5]
            logger.info(
                f"Chain match debug: {len(all_matched_contacts)} matched contacts, "
                f"{len(all_unmatched_custs)} unmatched customers, "
                f"{len(contact_company_map)} contacts with companies. "
                f"Sample qb_customer_id on contacts: {sample_contact_ids}, "
                f"Sample customer_key_id on customers: {sample_key_ids}"
            )

            # Now match: QB contact → customer_contact → company
            matched = 0
            no_company = 0
            no_cust_match = 0
            total_chain = len(all_matched_contacts)
            for chain_idx, qb_contact in enumerate(all_matched_contacts):
                contact_id = qb_contact.get('matched_contact_id')
                customer_id = qb_contact.get('qb_customer_id')
                if not contact_id or not customer_id:
                    continue

                company_id = contact_company_map.get(contact_id)
                if not company_id:
                    no_company += 1
                    continue

                # Look up by customer_key_id (field 92), not record_id (field 3)
                try:
                    normalized_key = str(int(float(customer_id)))
                except (ValueError, TypeError):
                    normalized_key = str(customer_id)
                qb_cust_id = qb_cust_by_key.get(normalized_key)
                if not qb_cust_id:
                    no_cust_match += 1
                    continue

                if company_id and qb_cust_id:
                    try:
                        _execute_with_retry(lambda cid=company_id, qid=qb_cust_id: (
                            self._supabase.table('qb_customers').update({
                                'matched_company_id': cid
                            }).eq('id', qid).execute()
                        ))
                        matched += 1
                    except Exception:
                        pass

                if (chain_idx + 1) % 2000 == 0:
                    logger.info(f"Chain match progress: {chain_idx + 1}/{total_chain} "
                                f"({matched} matched so far)")

            logger.info(
                f"Chain match result: {matched} matched, "
                f"{no_company} contacts without company, "
                f"{no_cust_match} contacts whose QB customer already matched or ID mismatch"
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
                'qb_record_id, customer_code, matched_company_id, customer_status, '
                'customer_tier, account_manager, total_invoiced, invoiced_ty, invoiced_ly, '
                'growth_90d, days_since_last_invoice, recency_days'
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
        # customers can map to the same company — last one wins)
        by_company: dict[str, dict] = {}
        for qb in all_matched:
            company_id = qb['matched_company_id']
            ty = qb.get('invoiced_ty')
            ly = qb.get('invoiced_ly')
            total = qb.get('total_invoiced')
            growth = qb.get('growth_90d') or _derive_growth(ty, ly)
            tier = qb.get('customer_tier') or _derive_tier(total)
            recency_raw = qb.get('days_since_last_invoice') or qb.get('recency_days')
            recency = _parse_recency_html(recency_raw)

            by_company[company_id] = {
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
            for idx, (cid, data) in enumerate(items):
                data = {k: v for k, v in data.items() if v is not None}
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
