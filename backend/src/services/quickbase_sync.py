"""
Quickbase Sync Service — Syncs QB data to local Supabase cache tables.

Handles: Customers, Contacts, Quotes, Jobs, Sales Line Items.
After sync, matches QB records to existing customer_companies/customer_contacts.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from .quickbase_client import QuickbaseClient, DEFAULT_FIELD_MAPPINGS

logger = logging.getLogger(__name__)

# Supabase batch limits
UPSERT_BATCH_SIZE = 100
IN_FILTER_LIMIT = 500


def _execute_with_retry(func, max_retries=3):
    """Execute a Supabase operation with retry for transient errors."""
    import time
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            err_str = str(e)
            if attempt < max_retries - 1 and any(
                code in err_str for code in ['525', '502', '503', '504', 'SSL', 'ConnectionError']
            ):
                time.sleep(2 ** attempt)
                continue
            raise


class QuickbaseSync:
    """Orchestrates syncing Quickbase data to local Supabase cache."""

    def __init__(self, supabase_client, qb_config: dict):
        """
        Args:
            supabase_client: Initialized Supabase client
            qb_config: Row from qb_sync_config table
        """
        self._supabase = supabase_client
        self._config = qb_config
        self._client_id = qb_config['client_id']

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

    # Maps logical table name → qb_sync_config field holding the QB table ID
    _TABLE_ID_CONFIG_FIELD = {
        'customers':       'customers_table_id',
        'contacts':        'contacts_table_id',
        'quotes':          'quotes_table_id',
        'jobs':            'jobs_table_id',
        'sales_line_items': 'sales_line_items_table_id',
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

    async def sync_all(self, tables: list[str] | None = None) -> dict[str, int]:
        """Sync QB tables. Pass `tables` to sync a subset; omit for full sync."""
        all_fns = [
            ('customers', self.sync_customers),
            ('contacts', self.sync_contacts),
            ('quotes', self.sync_quotes),
            ('jobs', self.sync_jobs),
            ('sales_line_items', self.sync_sales_line_items),
        ]
        to_sync = [(k, fn) for k, fn in all_fns if tables is None or k in tables]
        label = ', '.join(k for k, _ in to_sync)
        logger.info(f"Starting QB sync for client {self._client_id}: [{label}]")
        counts = {}

        for table_key, sync_fn in to_sync:
            try:
                counts[table_key] = await sync_fn()
                self._write_sync_log(table_key, counts[table_key])
            except Exception as e:
                logger.error(f"QB sync failed for table {table_key}: {e}")
                self._write_sync_log(table_key, 0, status='error', error_message=str(e))
                counts[table_key] = 0

        # After sync, match to existing companies/contacts
        matched_companies = await self.match_to_companies()
        matched_contacts = await self.match_to_contacts()
        matched_via_contacts = await self.match_customers_via_contacts()
        matched_companies += matched_via_contacts
        counts['matched_companies'] = matched_companies
        counts['matched_contacts'] = matched_contacts

        # Update last_sync_at
        _execute_with_retry(lambda: self._supabase.table('qb_sync_config').update({
            'last_sync_at': datetime.now(timezone.utc).isoformat(),
            'updated_at': datetime.now(timezone.utc).isoformat(),
        }).eq('client_id', self._client_id).execute())

        logger.info(f"QB sync complete for client {self._client_id}: {counts}")
        return counts

    async def sync_customers(self) -> int:
        """Sync QB Customers table → qb_customers."""
        mapping = self._field_mappings['customers']
        table_id = self._config['customers_table_id']
        select_fields = QuickbaseClient.get_select_fields(mapping)

        records = await self._qb_client.query_all_records(table_id, select_fields)
        logger.info(f"Fetched {len(records)} customers from QB")

        return await self._upsert_records('qb_customers', records, mapping, required_fields=['customer_name'])

    async def sync_contacts(self) -> int:
        """Sync QB Contacts table → qb_contacts."""
        mapping = self._field_mappings['contacts']
        table_id = self._config['contacts_table_id']
        select_fields = QuickbaseClient.get_select_fields(mapping)

        records = await self._qb_client.query_all_records(table_id, select_fields)
        logger.info(f"Fetched {len(records)} contacts from QB")

        return await self._upsert_records('qb_contacts', records, mapping)

    async def sync_quotes(self) -> int:
        """Sync QB Quotes table → qb_quotes."""
        mapping = self._field_mappings['quotes']
        table_id = self._config['quotes_table_id']
        select_fields = QuickbaseClient.get_select_fields(mapping)

        records = await self._qb_client.query_all_records(table_id, select_fields)
        logger.info(f"Fetched {len(records)} quotes from QB")

        return await self._upsert_records('qb_quotes', records, mapping)

    async def sync_jobs(self) -> int:
        """Sync QB Jobs table → qb_jobs."""
        mapping = self._field_mappings['jobs']
        table_id = self._config['jobs_table_id']
        select_fields = QuickbaseClient.get_select_fields(mapping)

        records = await self._qb_client.query_all_records(table_id, select_fields)
        logger.info(f"Fetched {len(records)} jobs from QB")

        return await self._upsert_records('qb_jobs', records, mapping)

    async def sync_sales_line_items(self) -> int:
        """Sync QB Sales Line Items table → qb_sales_line_items."""
        mapping = self._field_mappings['sales_line_items']
        table_id = self._config['sales_line_items_table_id']
        select_fields = QuickbaseClient.get_select_fields(mapping)

        records = await self._qb_client.query_all_records(table_id, select_fields)
        logger.info(f"Fetched {len(records)} sales line items from QB")

        return await self._upsert_records('qb_sales_line_items', records, mapping)

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
            num_batches = (len(rows) + UPSERT_BATCH_SIZE - 1) // UPSERT_BATCH_SIZE
            for i in range(0, len(rows), UPSERT_BATCH_SIZE):
                batch = rows[i:i + UPSERT_BATCH_SIZE]
                batch_num = i // UPSERT_BATCH_SIZE + 1
                try:
                    _execute_with_retry(lambda b=batch: self._supabase.table(table_name).upsert(
                        b, on_conflict='client_id,qb_record_id'
                    ).execute())
                    total += len(batch)
                except Exception as e:
                    logger.warning(f"Batch {batch_num}/{num_batches} failed for {table_name}: {e}")
                    # Retry once after longer pause
                    _time.sleep(2)
                    try:
                        _execute_with_retry(lambda b=batch: self._supabase.table(table_name).upsert(
                            b, on_conflict='client_id,qb_record_id'
                        ).execute())
                        total += len(batch)
                    except Exception as e2:
                        logger.error(f"Batch {batch_num} permanently failed: {e2}")
                # Throttle: small pause every 10 batches to avoid connection exhaustion
                if batch_num % 10 == 0:
                    _time.sleep(0.5)
                    if batch_num % 100 == 0:
                        logger.info(f"  {table_name}: {total}/{len(rows)} upserted...")
            return total

        total = await asyncio.to_thread(_do_upsert)
        logger.info(f"Upserted {total} records into {table_name}")
        return total

    async def match_to_companies(self) -> int:
        """Match qb_customers to customer_companies by normalized name + domain."""
        # Get all QB customers for this client
        qb_result = _execute_with_retry(lambda: self._supabase.table('qb_customers').select(
            'id, customer_name'
        ).eq('client_id', self._client_id).is_('matched_company_id', 'null').execute())

        unmatched = qb_result.data or []
        if not unmatched:
            return 0

        # Get all companies for this client (include email_domains for domain matching)
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

        # Build lookup maps: name → id and domain-keyword → id
        companies_by_name = {}
        companies_by_keyword = {}
        for c in all_companies:
            if not c.get('company_name'):
                continue
            cname = c['company_name'].strip().lower()
            companies_by_name[cname] = c['id']
            # Also index by stripped name (no suffixes)
            for suffix in [' pty ltd', ' pty. ltd.', ' pty', ' ltd', ' inc', ' llc', ' corp',
                           ' corporation', ' company', ' group', ' holdings', ' services',
                           ' australia', ' international']:
                clean = cname.removesuffix(suffix).strip()
                if clean != cname and clean:
                    companies_by_name[clean] = c['id']
            # Index by domain keywords (e.g., "carbon8.com.au" → "carbon8")
            for domain in (c.get('email_domains') or []):
                keyword = domain.split('.')[0].lower()
                if keyword and len(keyword) > 2:
                    companies_by_keyword[keyword] = c['id']

        matched = 0
        for qb_cust in unmatched:
            name = (qb_cust.get('customer_name') or '').strip().lower()
            if not name:
                continue

            # 1. Exact match
            company_id = companies_by_name.get(name)

            # 2. Try stripped QB name (remove suffixes from QB side too)
            if not company_id:
                for suffix in [' pty ltd', ' pty. ltd.', ' pty', ' ltd', ' inc', ' llc', ' corp',
                               ' corporation', ' company', ' group', ' holdings', ' services',
                               ' australia', ' international']:
                    clean = name.rstrip('.').removesuffix(suffix).strip()
                    if clean != name:
                        company_id = companies_by_name.get(clean)
                        if company_id:
                            break

            # 3. Contains match: QB name contains a company name or vice versa
            if not company_id:
                for cname, cid in companies_by_name.items():
                    if len(cname) >= 3 and (cname in name or name in cname):
                        company_id = cid
                        break

            # 4. Domain keyword match: QB "Carbon8 Pty Ltd" → keyword "carbon8" → domain match
            if not company_id:
                qb_words = name.replace('.', ' ').split()
                for word in qb_words:
                    if word in companies_by_keyword:
                        company_id = companies_by_keyword[word]
                        break

            if company_id:
                _execute_with_retry(lambda cid=company_id, qid=qb_cust['id']: (
                    self._supabase.table('qb_customers').update({
                        'matched_company_id': cid
                    }).eq('id', qid).execute()
                ))
                matched += 1

        logger.info(f"Matched {matched}/{len(unmatched)} QB customers to companies")
        return matched

    async def match_to_contacts(self) -> int:
        """Match qb_contacts to customer_contacts by email address."""
        # Get unmatched QB contacts with emails
        qb_result = _execute_with_retry(lambda: self._supabase.table('qb_contacts').select(
            'id, email'
        ).eq('client_id', self._client_id).is_('matched_contact_id', 'null').execute())

        unmatched = [r for r in (qb_result.data or []) if r.get('email')]
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
        for qb_contact in unmatched:
            email = (qb_contact.get('email') or '').strip().lower()
            contact_id = contacts_by_email.get(email)

            if contact_id:
                _execute_with_retry(lambda cid=contact_id, qid=qb_contact['id']: (
                    self._supabase.table('qb_contacts').update({
                        'matched_contact_id': cid
                    }).eq('id', qid).execute()
                ))
                matched += 1

        logger.info(f"Matched {matched}/{len(unmatched)} QB contacts by email")
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
            # Get all matched QB contacts with their QB customer link
            qb_contacts = _execute_with_retry(lambda: self._supabase.table('qb_contacts').select(
                'id, matched_contact_id, qb_customer_id'
            ).eq('client_id', self._client_id).not_.is_(
                'matched_contact_id', 'null'
            ).execute())

            if not qb_contacts.data:
                return 0

            # Get unmatched QB customers
            unmatched_custs = _execute_with_retry(lambda: self._supabase.table('qb_customers').select(
                'id, qb_record_id'
            ).eq('client_id', self._client_id).is_(
                'matched_company_id', 'null'
            ).execute())

            if not unmatched_custs.data:
                return 0

            # Build QB record_id → QB customer id lookup
            qb_cust_by_record = {c['qb_record_id']: c['id'] for c in unmatched_custs.data if c.get('qb_record_id')}

            # Build contact_id → company_id lookup from customer_contacts
            contact_ids = [c['matched_contact_id'] for c in qb_contacts.data if c.get('matched_contact_id')]
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

            # Now match: QB contact → customer_contact → company
            matched = 0
            for qb_contact in qb_contacts.data:
                contact_id = qb_contact.get('matched_contact_id')
                customer_id = qb_contact.get('qb_customer_id')  # QB customer record ID
                if not contact_id or not customer_id:
                    continue

                company_id = contact_company_map.get(contact_id)
                qb_cust_id = qb_cust_by_record.get(str(customer_id))

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

            logger.info(f"Matched {matched} QB customers via contact email→company chain")
            return matched

        except Exception as e:
            logger.warning(f"match_customers_via_contacts failed: {e}")
            return 0

    async def propagate_qb_data_to_companies(self) -> int:
        """
        After matching, copy QB data to customer_companies enrichment columns.
        This makes QB context available to all downstream pipeline steps.
        """
        # Get matched QB customers
        result = _execute_with_retry(lambda: self._supabase.table('qb_customers').select(
            'matched_company_id, customer_status, customer_tier, account_manager, '
            'total_invoiced, invoiced_ty, invoiced_ly, growth_90d, days_since_last_invoice'
        ).eq('client_id', self._client_id).not_.is_('matched_company_id', 'null').execute())

        updated = 0
        for qb in (result.data or []):
            company_id = qb['matched_company_id']
            update_data = {
                'qb_customer_type': qb.get('customer_status'),
                'qb_tier': qb.get('customer_tier'),
                'qb_total_revenue': qb.get('total_invoiced'),
                'qb_invoiced_ty': qb.get('invoiced_ty'),
                'qb_invoiced_ly': qb.get('invoiced_ly'),
                'qb_growth_90d': qb.get('growth_90d'),
                'qb_days_since_last_invoice': qb.get('days_since_last_invoice'),
                'qb_account_manager': qb.get('account_manager'),
            }
            # Remove None values
            update_data = {k: v for k, v in update_data.items() if v is not None}

            if update_data:
                _execute_with_retry(lambda d=update_data, cid=company_id: (
                    self._supabase.table('customer_companies').update(d).eq('id', cid).execute()
                ))
                updated += 1

        logger.info(f"Propagated QB data to {updated} customer_companies")
        return updated
