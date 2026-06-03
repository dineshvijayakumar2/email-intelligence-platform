"""
Company Resolver Service - Sprint 2

Purpose: Group contacts by domain and resolve to customer_companies
Step 4 of 13-step extraction pipeline

Features:
- Groups contacts by email domain
- Classifies domains (internal, free_provider, customer)
- Matches to existing companies or creates new ones
- Handles free email providers (gmail.com, yahoo.com, etc.)
- Uses domain_parser for company name generation
- Returns company records with metadata

Classification Logic:
1. Internal domains → Skip (user's own organization)
2. Free providers → Create individual contact companies (or group)
3. Corporate domains → Create/update customer_companies

Author: Sprint 2 Implementation
"""

from typing import List, Dict, Optional, Set, Tuple
from dataclasses import dataclass, asdict
import logging
from datetime import datetime
from collections import defaultdict

from ..database.supabase_client import SupabaseClient
from ..utils.domain_parser import (
    extract_domain,
    normalize_domain,
    get_root_domain
)

logger = logging.getLogger(__name__)


@dataclass
class ResolvedCompany:
    """Company resolved from domain grouping"""
    # Company identification
    company_id: Optional[str]  # UUID if existing, None if new
    company_name: str
    domain: str
    domain_classification: str  # 'internal', 'free_provider', 'customer', 'unknown'

    # Contact statistics
    contact_count: int
    total_emails: int
    sender_count: int
    recipient_count: int

    # Metadata
    email_domains: List[str]  # All domains seen for this company
    is_new: bool  # True if company doesn't exist in DB
    first_seen: datetime
    last_seen: datetime

    # Contact IDs associated with this company
    contact_emails: List[str]


class CompanyResolver:
    """
    Resolve contacts to customer_companies by domain

    Usage:
        resolver = CompanyResolver(client_id="uuid-here")

        # Resolve from extracted contacts
        companies = resolver.resolve_companies(contacts)

        # Upsert to database
        upserted = resolver.upsert_companies(companies)
    """

    def __init__(self, client_id: str):
        """
        Initialize company resolver

        Args:
            client_id: Client UUID for company resolution
        """
        self.client_id = client_id
        self.client = SupabaseClient.get_client(use_service_key=True)

        # Cache for lookups
        self._internal_domains: Set[str] = set()
        self._free_providers: Set[str] = set()
        self._existing_companies: Dict[str, Dict] = {}  # domain -> company record

        # QB unique email lookup: email → {qb_customer_id, customer_name}
        self._qb_email_lookup: Dict[str, Dict] = {}
        # QB customer lookup: qb_record_id → {id (UUID), customer_name, customer_code, matched_company_id}
        self._qb_customer_lookup: Dict[str, Dict] = {}

        # Load reference data
        self._load_internal_domains()
        self._load_free_providers()
        self._load_existing_companies()
        self._load_qb_unique_emails()

        logger.info(f"CompanyResolver initialized for client {client_id}")
        logger.info(f"Loaded {len(self._internal_domains)} internal domains, "
                   f"{len(self._free_providers)} free providers, "
                   f"{len(self._existing_companies)} existing companies, "
                   f"{len(self._qb_email_lookup)} QB unique emails")

    def _load_internal_domains(self):
        """Load internal domains for this client"""
        try:
            response = (
                self.client.table('internal_domains')
                .select('domain')
                .eq('client_id', self.client_id)
                .execute()
            )

            for row in response.data:
                self._internal_domains.add(row['domain'].lower())

            logger.debug(f"Loaded internal domains: {self._internal_domains}")

        except Exception as e:
            logger.error(f"Failed to load internal domains: {e}")
            # Continue with empty set

    def _load_free_providers(self):
        """Load free email providers from reference table"""
        try:
            response = (
                self.client.table('free_email_providers')
                .select('domain')
                .execute()
            )

            for row in response.data:
                self._free_providers.add(row['domain'].lower())

            logger.debug(f"Loaded {len(self._free_providers)} free email providers")

        except Exception as e:
            logger.error(f"Failed to load free providers: {e}")
            # Continue with empty set

    def _load_existing_companies(self):
        """Load ALL existing companies for this client (paginated)."""
        try:
            total_rows = 0
            offset = 0
            while True:
                response = (
                    self.client.table('customer_companies')
                    .select('id, company_name, email_domains, created_at')
                    .eq('client_id', self.client_id)
                    .range(offset, offset + 999)
                    .execute()
                )
                rows = response.data or []
                for row in rows:
                    for domain in (row.get('email_domains') or []):
                        self._existing_companies[domain.lower()] = row
                total_rows += len(rows)
                if len(rows) == 0:
                    break
                offset += len(rows)

            logger.info(f"Loaded {total_rows} existing companies "
                       f"with {len(self._existing_companies)} domain mappings")

        except Exception as e:
            logger.error(f"Failed to load existing companies: {e}")

    def _load_qb_unique_emails(self):
        """Load QB unique emails and QB customers for email-based company resolution.

        This enables the primary matching path:
        contact email → qb_unique_emails → qb_customer_id → company
        """
        try:
            # Load valid unique emails (not hidden, not invalid, has customer ID)
            offset = 0
            while True:
                resp = (
                    self.client.table('qb_unique_emails')
                    .select('email, qb_customer_id, customer_name')
                    .eq('client_id', self.client_id)
                    .eq('hide', False)
                    .eq('email_invalid', False)
                    .not_.is_('qb_customer_id', 'null')
                    .range(offset, offset + 999)
                    .execute()
                )
                rows = resp.data or []
                for r in rows:
                    email = (r.get('email') or '').strip().lower()
                    if email and r.get('qb_customer_id'):
                        self._qb_email_lookup[email] = {
                            'qb_customer_id': str(r['qb_customer_id']).strip(),
                            'customer_name': r.get('customer_name'),
                        }
                if len(rows) == 0:
                    break
                offset += len(rows)

            if not self._qb_email_lookup:
                return

            # Load QB customers so we can map qb_customer_id → matched SB company.
            # qb_unique_emails.qb_customer_id is QB's "Customer ID (key)" field —
            # which lands in qb_customers.customer_key_id, NOT qb_record_id (the
            # internal Record ID#). Keying this lookup by qb_record_id mis-joins
            # ~100% of rows (the two id spaces are unrelated), so use customer_key_id.
            offset = 0
            while True:
                resp = (
                    self.client.table('qb_customers')
                    .select('id, qb_record_id, customer_key_id, customer_name, customer_code, matched_company_id')
                    .eq('client_id', self.client_id)
                    .range(offset, offset + 999)
                    .execute()
                )
                rows = resp.data or []
                for r in rows:
                    key = str(r.get('customer_key_id', '')).strip()
                    if not key:
                        continue
                    try:
                        key = str(int(float(key)))  # match resolve_company_from_qb_email normalisation
                    except (ValueError, TypeError):
                        pass
                    self._qb_customer_lookup[key] = r
                if len(rows) == 0:
                    break
                offset += len(rows)

            logger.info(
                f"QB email lookup: {len(self._qb_email_lookup)} emails, "
                f"{len(self._qb_customer_lookup)} QB customers loaded"
            )
        except Exception as e:
            logger.warning(f"Failed to load QB unique emails (non-critical, domain fallback): {e}")

    def resolve_company_from_qb_email(self, email: str) -> Optional[Dict]:
        """Look up a contact email in QB unique emails to resolve company.

        Returns:
            Dict with {company_id, company_name, qb_customer_id, qb_customer_code, match_source}
            or None if no QB match.
        """
        email_lower = email.strip().lower()
        qb_info = self._qb_email_lookup.get(email_lower)
        if not qb_info:
            return None

        qb_customer_id = qb_info['qb_customer_id']
        # Normalise (QB IDs can be float-formatted)
        try:
            normalized_id = str(int(float(qb_customer_id)))
        except (ValueError, TypeError):
            normalized_id = qb_customer_id

        qb_cust = self._qb_customer_lookup.get(normalized_id)
        if not qb_cust:
            return None

        return {
            'company_id': qb_cust.get('matched_company_id'),  # may be None if not yet linked
            'company_name': qb_cust.get('customer_name') or qb_info.get('customer_name'),
            'qb_customer_id': qb_cust.get('qb_record_id'),
            'qb_customer_code': qb_cust.get('customer_code'),
            'qb_customer_uuid': qb_cust.get('id'),
            'match_source': 'qb_email_lookup',
        }

    def classify_domain(self, domain: str) -> str:
        """
        Classify domain as internal, free_provider, or customer

        Args:
            domain: Email domain

        Returns:
            Classification: 'internal', 'free_provider', 'customer', or 'unknown'
        """
        domain_lower = domain.lower()

        # Check internal domains first
        if domain_lower in self._internal_domains:
            return 'internal'

        # Check free providers
        if domain_lower in self._free_providers:
            return 'free_provider'

        # Check if we have an existing company for this domain
        if domain_lower in self._existing_companies:
            return 'customer'

        # New customer domain
        return 'customer'

    def _parse_datetime(self, date_value) -> datetime:
        """
        Safely parse datetime from string or datetime object

        Args:
            date_value: String or datetime object

        Returns:
            datetime object
        """
        if isinstance(date_value, datetime):
            return date_value
        elif isinstance(date_value, str):
            return datetime.fromisoformat(date_value.replace('Z', '+00:00'))
        else:
            raise ValueError(f"Invalid date value type: {type(date_value)}")

    def resolve_companies(
        self,
        contacts: List[Dict],
        exclude_internal: bool = True,
        group_free_providers: bool = False
    ) -> List[ResolvedCompany]:
        """
        Resolve contacts to companies.

        Priority:
        1. QB email lookup: contact email → qb_unique_emails → QB customer → company
        2. Domain-based: group by domain → match/create company

        Args:
            contacts: List of extracted contact dictionaries
            exclude_internal: Skip internal domains
            group_free_providers: If True, group all free provider contacts
                                 under "Individual Contacts" bucket.
                                 If False, create separate company per person.

        Returns:
            List of resolved companies
        """
        logger.info(f"Resolving {len(contacts)} contacts to companies")

        # ── Phase 1: QB email lookup (highest priority) ──────────────────
        # Contacts matched here get their company from QB, not from domain
        qb_resolved: Dict[str, Dict] = {}  # company_name → {qb_info, contacts}
        remaining_contacts: List[Dict] = []
        qb_matched_count = 0

        if self._qb_email_lookup:
            for contact in contacts:
                email = (contact.get('email') or '').strip().lower()
                qb_info = self.resolve_company_from_qb_email(email) if email else None

                if qb_info and qb_info.get('company_name'):
                    company_name = qb_info['company_name']
                    if company_name not in qb_resolved:
                        qb_resolved[company_name] = {
                            'qb_info': qb_info,
                            'contacts': [],
                            'domains': set(),
                        }
                    qb_resolved[company_name]['contacts'].append(contact)
                    domain = (contact.get('domain') or '').lower()
                    if domain:
                        qb_resolved[company_name]['domains'].add(domain)
                    qb_matched_count += 1
                else:
                    remaining_contacts.append(contact)

            logger.info(
                f"QB email lookup: {qb_matched_count} contacts → "
                f"{len(qb_resolved)} companies resolved from QB"
            )
        else:
            remaining_contacts = contacts

        # Build ResolvedCompany objects for QB-matched contacts
        companies: List[ResolvedCompany] = []
        for company_name, data in qb_resolved.items():
            qb_info = data['qb_info']
            group_contacts = data['contacts']
            domains = list(data['domains'])

            # Use existing company_id if QB customer is already linked to an SB company
            existing_id = qb_info.get('company_id')

            company = ResolvedCompany(
                company_id=existing_id,
                company_name=company_name,
                domain=domains[0] if domains else '',
                domain_classification='customer',
                contact_count=len(group_contacts),
                total_emails=sum(c.get('total_emails', 0) for c in group_contacts),
                sender_count=sum(c.get('as_sender_count', 0) for c in group_contacts),
                recipient_count=sum(c.get('as_recipient_count', 0) for c in group_contacts),
                email_domains=domains,
                is_new=existing_id is None,
                first_seen=min(
                    (self._parse_datetime(c.get('first_seen_date', datetime.utcnow()))
                     for c in group_contacts),
                    default=datetime.utcnow()
                ),
                last_seen=max(
                    (self._parse_datetime(c.get('last_seen_date', datetime.utcnow()))
                     for c in group_contacts),
                    default=datetime.utcnow()
                ),
                contact_emails=[c.get('email', '') for c in group_contacts],
            )
            # Attach QB metadata for downstream steps
            company.qb_customer_id = qb_info.get('qb_customer_id')
            company.qb_customer_code = qb_info.get('qb_customer_code')
            company.qb_customer_uuid = qb_info.get('qb_customer_uuid')
            company.qb_match_source = 'qb_email_lookup'
            companies.append(company)

        # ── Phase 2: Domain-based resolution (fallback) ──────────────────
        # QB-anchored mode: only match to EXISTING companies by domain.
        # Never create new companies from domain names or person names —
        # that produces junk SB rows. Contacts without a QB or domain match
        # stay unlinked (customer_company_id = NULL).
        logger.info(f"Domain fallback: resolving {len(remaining_contacts)} remaining contacts (existing-only)")

        domain_groups = self._group_by_domain(remaining_contacts)
        excluded_internal_count = 0
        skipped_no_existing_count = 0

        for domain, domain_contacts in domain_groups.items():
            classification = self.classify_domain(domain)

            if classification == 'internal' and exclude_internal:
                excluded_internal_count += len(domain_contacts)
                continue

            if classification == 'free_provider':
                skipped_no_existing_count += len(domain_contacts)
                continue

            existing_company = self._existing_companies.get(domain.lower())
            if existing_company:
                company = self._create_company_from_domain(domain, domain_contacts, classification)
                companies.append(company)
            else:
                skipped_no_existing_count += len(domain_contacts)

        logger.info(
            f"Resolved {len(companies)} companies total "
            f"({qb_matched_count} via QB email, "
            f"{excluded_internal_count} internal excluded, "
            f"{skipped_no_existing_count} skipped — no existing company)"
        )

        return companies

    def _group_by_domain(self, contacts: List[Dict]) -> Dict[str, List[Dict]]:
        """
        Group contacts by email domain

        Args:
            contacts: List of contact dictionaries

        Returns:
            Dictionary mapping domain -> list of contacts
        """
        domain_groups = defaultdict(list)

        for contact in contacts:
            domain = contact.get('domain')
            if domain:
                domain_groups[domain.lower()].append(contact)

        return dict(domain_groups)

    def _create_company_from_domain(
        self,
        domain: str,
        contacts: List[Dict],
        classification: str
    ) -> ResolvedCompany:
        """
        Create company record from domain and contacts

        Args:
            domain: Email domain
            contacts: List of contacts from this domain
            classification: Domain classification

        Returns:
            ResolvedCompany instance
        """
        # resolve_companies only invokes this for an EXISTING company matched by
        # domain. QB-anchored mode never mints companies from domain-derived
        # names — that historically produced junk duplicates like "Mauijim"
        # alongside the real, QB-linked "Maui Jim". Fail loud rather than
        # silently re-introduce that path.
        existing_company = self._existing_companies.get(domain.lower())
        if not existing_company:
            raise ValueError(
                f"_create_company_from_domain called for domain '{domain}' with no "
                f"existing company; domain-derived company creation is disabled"
            )
        company_id = existing_company['id']
        company_name = existing_company['company_name']
        is_new = False

        # Calculate statistics
        contact_count = len(contacts)
        total_emails = sum(int(c.get('total_emails', 0) or 0) for c in contacts)
        sender_count = sum(1 for c in contacts if int(c.get('as_sender_count', 0) or 0) > 0)
        recipient_count = sum(1 for c in contacts if int(c.get('as_recipient_count', 0) or 0) > 0)

        # Get date range
        first_seen = min(
            self._parse_datetime(c['first_seen_date'])
            for c in contacts
        )
        last_seen = max(
            self._parse_datetime(c['last_seen_date'])
            for c in contacts
        )

        # Get all domains (in case of subdomains)
        email_domains = list(set(c.get('domain') for c in contacts if c.get('domain')))

        # Get contact emails
        contact_emails = [c['email'] for c in contacts]

        return ResolvedCompany(
            company_id=company_id,
            company_name=company_name,
            domain=domain,
            domain_classification=classification,
            contact_count=contact_count,
            total_emails=total_emails,
            sender_count=sender_count,
            recipient_count=recipient_count,
            email_domains=email_domains,
            is_new=is_new,
            first_seen=first_seen,
            last_seen=last_seen,
            contact_emails=contact_emails
        )

    def upsert_companies(self, companies: List[ResolvedCompany]) -> Dict:
        """
        Upsert companies to database (batch upsert with ON CONFLICT)

        Creates new companies or updates existing ones

        Args:
            companies: List of resolved companies

        Returns:
            Dictionary with statistics
        """
        logger.info(f"Upserting {len(companies)} companies to database (batch mode)")

        if not companies:
            return {
                'total_companies': 0,
                'created': 0,
                'updated': 0,
                'errors': []
            }

        # Deduplicate companies by name (case-insensitive)
        # PostgreSQL upsert can't handle duplicate rows in same batch
        company_map: Dict[str, ResolvedCompany] = {}
        for company in companies:
            name_lower = company.company_name.lower()
            if name_lower in company_map:
                # Merge with existing
                existing = company_map[name_lower]
                existing.email_domains = list(set(existing.email_domains + company.email_domains))
                existing.contact_emails = list(set(existing.contact_emails + company.contact_emails))
                existing.contact_count = max(existing.contact_count, company.contact_count)
                existing.total_emails += company.total_emails
                existing.last_seen = max(existing.last_seen, company.last_seen)
                existing.first_seen = min(existing.first_seen, company.first_seen)
            else:
                company_map[name_lower] = company

        deduplicated_companies = list(company_map.values())

        if len(deduplicated_companies) < len(companies):
            logger.info(f"Deduplicated {len(companies)} companies to {len(deduplicated_companies)} unique companies")

        # Fetch ALL existing companies for this client (paginated)
        all_existing_rows: list = []
        offset = 0
        while True:
            existing_page = (
                self.client.table('customer_companies')
                .select('id, company_name, email_domains')
                .eq('client_id', self.client_id)
                .range(offset, offset + 999)
                .execute()
            )
            rows = existing_page.data or []
            all_existing_rows.extend(rows)
            if len(rows) == 0:
                break
            offset += len(rows)

        existing_companies = {
            row['company_name'].lower(): row
            for row in all_existing_rows
        }

        logger.info(f"Found {len(existing_companies)} existing companies in database")

        # Prepare batch upsert data
        upsert_data = []
        timestamp = datetime.utcnow().isoformat()

        for company in deduplicated_companies:
            company_name_lower = company.company_name.lower()
            existing = existing_companies.get(company_name_lower)

            # Merge email domains if updating
            if existing:
                existing_domains = set(existing.get('email_domains', []))
                new_domains = list(existing_domains.union(set(company.email_domains)))
            else:
                new_domains = company.email_domains

            company_data = {
                'client_id': self.client_id,
                'company_name': existing['company_name'] if existing else company.company_name,
                'email_domains': new_domains,
                'contact_count': company.contact_count,
                'first_contact_date': company.first_seen.isoformat(),
                'last_contact_date': company.last_seen.isoformat(),
                'updated_at': timestamp
            }

            # If resolved via QB email lookup, include QB match metadata
            if getattr(company, 'qb_match_source', None) == 'qb_email_lookup':
                company_data['qb_customer_id'] = getattr(company, 'qb_customer_id', None)
                company_data['qb_customer_code'] = getattr(company, 'qb_customer_code', None)
                company_data['qb_match_method'] = 'email_lookup'
                company_data['qb_matched_at'] = timestamp

            if not existing:
                company_data['created_at'] = timestamp

            upsert_data.append(company_data)

        # Batch upsert (100 per batch)
        # Use ON CONFLICT because customer_companies has unique constraint on (client_id, company_name)
        batch_size = 100
        created_count = 0
        updated_count = 0
        errors = []

        for i in range(0, len(upsert_data), batch_size):
            batch = upsert_data[i:i + batch_size]

            try:
                # Upsert with ON CONFLICT on unique constraint
                response = (
                    self.client.table('customer_companies')
                    .upsert(batch, on_conflict='client_id,company_name')
                    .execute()
                )

                # Count how many were new vs updated
                batch_names = {item['company_name'].lower() for item in batch}
                new_in_batch = len(batch_names - existing_companies.keys())
                updated_in_batch = len(batch_names & existing_companies.keys())

                created_count += new_in_batch
                updated_count += updated_in_batch

                logger.info(f"Upserted batch {i//batch_size + 1}: "
                          f"{new_in_batch} new, {updated_in_batch} updated")

                # Update company IDs from response
                if response.data:
                    for row in response.data:
                        company_name_lower = row['company_name'].lower()
                        # Find matching company object and update its ID
                        for company in deduplicated_companies:
                            if company.company_name.lower() == company_name_lower:
                                company.company_id = row['id']
                                break

            except Exception as e:
                logger.error(f"Failed to upsert batch: {e}")
                # Add all companies in this batch to errors
                for item in batch:
                    errors.append({
                        'company_name': item['company_name'],
                        'domain': item.get('email_domains', [None])[0],
                        'error': str(e)
                    })

        logger.info(f"Company upsert complete: {created_count} created, "
                   f"{updated_count} updated, {len(errors)} errors")

        # Link QB customers to the newly created/updated SB companies
        qb_linked = 0
        for company in deduplicated_companies:
            qb_uuid = getattr(company, 'qb_customer_uuid', None)
            if qb_uuid and company.company_id:
                try:
                    self.client.table('qb_customers').update({
                        'matched_company_id': company.company_id
                    }).eq('id', qb_uuid).execute()
                    qb_linked += 1
                except Exception as e:
                    logger.warning(f"Failed to link QB customer {qb_uuid} → {company.company_id}: {e}")

        if qb_linked:
            logger.info(f"Linked {qb_linked} QB customers to SB companies")

        return {
            'total_companies': len(deduplicated_companies),
            'original_count': len(companies),
            'created': created_count,
            'updated': updated_count,
            'qb_linked': qb_linked,
            'errors': errors
        }

    def get_resolution_summary(self, companies: List[ResolvedCompany]) -> Dict:
        """
        Get summary statistics of company resolution

        Args:
            companies: List of resolved companies

        Returns:
            Dictionary with resolution statistics
        """
        total = len(companies)
        new_companies = sum(1 for c in companies if c.is_new)
        existing_companies = sum(1 for c in companies if not c.is_new)

        by_classification = defaultdict(int)
        for company in companies:
            by_classification[company.domain_classification] += 1

        total_contacts = sum(c.contact_count for c in companies)
        total_emails = sum(c.total_emails for c in companies)

        return {
            'total_companies': total,
            'new_companies': new_companies,
            'existing_companies': existing_companies,
            'by_classification': dict(by_classification),
            'total_contacts': total_contacts,
            'total_emails': total_emails,
        }


# Example usage
if __name__ == '__main__':
    import sys
    import json

    if len(sys.argv) < 3:
        print("Usage: python -m backend.src.services.company_resolver <client_id> <contacts_json_file>")
        print("\ncontacts_json_file should contain output from contact_extractor")
        sys.exit(1)

    client_id = sys.argv[1]
    contacts_file = sys.argv[2]

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Load contacts
    with open(contacts_file, 'r') as f:
        contacts = json.load(f)

    logger.info(f"Loaded {len(contacts)} contacts from {contacts_file}")

    # Resolve companies
    resolver = CompanyResolver(client_id=client_id)
    companies = resolver.resolve_companies(
        contacts=contacts,
        exclude_internal=True,
        group_free_providers=False
    )

    # Print summary
    summary = resolver.get_resolution_summary(companies)
    print("\n=== Company Resolution Summary ===")
    for key, value in summary.items():
        print(f"{key}: {value}")

    # Upsert to database
    print("\nUpserting companies to database...")
    upsert_result = resolver.upsert_companies(companies)

    print("\n=== Upsert Results ===")
    for key, value in upsert_result.items():
        if key != 'errors':
            print(f"{key}: {value}")

    if upsert_result['errors']:
        print(f"\nErrors: {len(upsert_result['errors'])}")
        for error in upsert_result['errors'][:5]:
            print(f"  - {error['company_name']}: {error['error']}")

    # Print top 10 companies
    companies.sort(key=lambda c: c.total_emails, reverse=True)
    print("\n=== Top 10 Companies by Email Volume ===")
    for i, company in enumerate(companies[:10], 1):
        status = "NEW" if company.is_new else "EXISTING"
        print(f"{i}. [{status}] {company.company_name} ({company.domain}) - "
              f"{company.contact_count} contacts, {company.total_emails} emails")
