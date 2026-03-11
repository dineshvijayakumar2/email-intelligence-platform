"""
Quickbase Sync Service — Syncs QB data to local Supabase cache tables.

Handles: Customers, Contacts, Quotes, Jobs, Sales Line Items.
After sync, matches QB records to existing customer_companies/customer_contacts.
"""

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

    async def sync_all(self) -> dict[str, int]:
        """Sync all QB tables. Returns record counts per table."""
        logger.info(f"Starting full QB sync for client {self._client_id}")
        counts = {}

        for table_key, sync_fn in [
            ('customers', self.sync_customers),
            ('contacts', self.sync_contacts),
            ('quotes', self.sync_quotes),
            ('jobs', self.sync_jobs),
            ('sales_line_items', self.sync_sales_line_items),
        ]:
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

        return self._upsert_records('qb_customers', records, mapping)

    async def sync_contacts(self) -> int:
        """Sync QB Contacts table → qb_contacts."""
        mapping = self._field_mappings['contacts']
        table_id = self._config['contacts_table_id']
        select_fields = QuickbaseClient.get_select_fields(mapping)

        records = await self._qb_client.query_all_records(table_id, select_fields)
        logger.info(f"Fetched {len(records)} contacts from QB")

        return self._upsert_records('qb_contacts', records, mapping)

    async def sync_quotes(self) -> int:
        """Sync QB Quotes table → qb_quotes."""
        mapping = self._field_mappings['quotes']
        table_id = self._config['quotes_table_id']
        select_fields = QuickbaseClient.get_select_fields(mapping)

        records = await self._qb_client.query_all_records(table_id, select_fields)
        logger.info(f"Fetched {len(records)} quotes from QB")

        return self._upsert_records('qb_quotes', records, mapping)

    async def sync_jobs(self) -> int:
        """Sync QB Jobs table → qb_jobs."""
        mapping = self._field_mappings['jobs']
        table_id = self._config['jobs_table_id']
        select_fields = QuickbaseClient.get_select_fields(mapping)

        records = await self._qb_client.query_all_records(table_id, select_fields)
        logger.info(f"Fetched {len(records)} jobs from QB")

        return self._upsert_records('qb_jobs', records, mapping)

    async def sync_sales_line_items(self) -> int:
        """Sync QB Sales Line Items table → qb_sales_line_items."""
        mapping = self._field_mappings['sales_line_items']
        table_id = self._config['sales_line_items_table_id']
        select_fields = QuickbaseClient.get_select_fields(mapping)

        records = await self._qb_client.query_all_records(table_id, select_fields)
        logger.info(f"Fetched {len(records)} sales line items from QB")

        return self._upsert_records('qb_sales_line_items', records, mapping)

    def _upsert_records(
        self, table_name: str, records: list[dict], mapping: dict[str, str]
    ) -> int:
        """Map and upsert QB records into a Supabase cache table."""
        now = datetime.now(timezone.utc).isoformat()
        rows = []

        for record in records:
            mapped = QuickbaseClient.map_record(record, mapping)
            # QB returns integers as floats (e.g. 9999.0) — coerce whole floats to int
            # QB returns empty strings for unset date/numeric fields — coerce to None
            for k, v in list(mapped.items()):
                if isinstance(v, float) and v == int(v):
                    mapped[k] = int(v)
                elif v == '':
                    mapped[k] = None
            mapped['client_id'] = self._client_id
            mapped['synced_at'] = now
            rows.append(mapped)

        # Batch upsert
        total = 0
        for i in range(0, len(rows), UPSERT_BATCH_SIZE):
            batch = rows[i:i + UPSERT_BATCH_SIZE]
            _execute_with_retry(lambda b=batch: self._supabase.table(table_name).upsert(
                b, on_conflict='client_id,qb_record_id'
            ).execute())
            total += len(batch)

        logger.info(f"Upserted {total} records into {table_name}")
        return total

    async def match_to_companies(self) -> int:
        """Match qb_customers to customer_companies by normalized name."""
        # Get all QB customers for this client
        qb_result = _execute_with_retry(lambda: self._supabase.table('qb_customers').select(
            'id, customer_name'
        ).eq('client_id', self._client_id).is_('matched_company_id', 'null').execute())

        unmatched = qb_result.data or []
        if not unmatched:
            return 0

        # Get all companies for this client
        company_result = _execute_with_retry(lambda: self._supabase.table('customer_companies').select(
            'id, company_name'
        ).eq('client_id', self._client_id).execute())

        companies = {
            c['company_name'].strip().lower(): c['id']
            for c in (company_result.data or [])
            if c.get('company_name')
        }

        matched = 0
        for qb_cust in unmatched:
            name = (qb_cust.get('customer_name') or '').strip().lower()
            if not name:
                continue

            # Exact match first
            company_id = companies.get(name)

            # Try without common suffixes
            if not company_id:
                for suffix in [' pty ltd', ' pty. ltd.', ' ltd', ' inc', ' llc', ' corp']:
                    clean = name.rstrip('.').removesuffix(suffix).strip()
                    company_id = companies.get(clean)
                    if company_id:
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
        contact_result = _execute_with_retry(lambda: self._supabase.table('customer_contacts').select(
            'id, email'
        ).eq('client_id', self._client_id).execute())

        contacts_by_email = {
            c['email'].strip().lower(): c['id']
            for c in (contact_result.data or [])
            if c.get('email')
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
