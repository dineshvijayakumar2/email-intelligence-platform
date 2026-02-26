"""
Email Linker Service - Sprint 2

Purpose: Backfill foreign keys in emails table linking to customer_contacts and customer_companies
Step 8 of 13-step extraction pipeline

Features:
- Links emails.customer_contact_id to customer_contacts.id
- Links emails.customer_company_id to customer_companies.id
- Links emails.client_id from mailbox chain
- Processes both inbound (links sender) and outbound (links recipients)
- Batch processing for performance
- Handles missing contacts/companies gracefully

Critical Service: This enables all analytics and reporting that rely on
customer relationships (response times, engagement metrics, etc.)

Author: Sprint 2 Implementation
"""

from typing import List, Dict, Optional, Set, Tuple
import logging
import time
from datetime import datetime

from ..database.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)


class EmailLinker:
    """
    Link emails to customer_contacts and customer_companies

    Usage:
        linker = EmailLinker(mailbox_id="uuid-here")

        # Link all unlinked emails
        result = linker.link_emails()

        # Link specific batch
        result = linker.link_emails(email_ids=["uuid1", "uuid2", ...])
    """

    # Maximum emails to update in a single Supabase query (avoid payload size limits)
    MAX_BATCH_SIZE = 100

    def __init__(self, mailbox_id: str, client_id: Optional[str] = None):
        """
        Initialize email linker

        Args:
            mailbox_id: Mailbox UUID to process
            client_id: Optional client UUID (auto-fetched if not provided)
        """
        self.mailbox_id = mailbox_id
        self.client = SupabaseClient.get_client(use_service_key=True)

        # Fetch client_id if not provided
        if not client_id:
            self.client_id = self._fetch_client_id()
        else:
            self.client_id = client_id

        # Cache for contact and company lookups
        self._contact_cache: Dict[str, str] = {}  # email -> contact_id
        self._company_cache: Dict[str, str] = {}  # domain -> company_id

        logger.info(f"EmailLinker initialized for mailbox {mailbox_id}, client {self.client_id}")

    @staticmethod
    def _execute_with_retry(query_builder, max_retries: int = 3, base_delay: float = 2.0):
        """Execute a Supabase query with retry for transient errors (SSL, network, 5xx)."""
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                return query_builder.execute()
            except Exception as e:
                last_error = e
                error_str = str(e)
                is_transient = any(kw in error_str for kw in [
                    'SSL handshake failed', '525', '502', '503', '504',
                    'Connection reset', 'Connection refused', 'timed out',
                    'JSON could not be generated', 'ECONNRESET', 'ETIMEDOUT',
                ])
                if is_transient and attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"Transient Supabase error (attempt {attempt + 1}/{max_retries + 1}), retrying in {delay}s: {error_str[:200]}")
                    time.sleep(delay)
                    continue
                raise
        raise last_error

    def _fetch_client_id(self) -> str:
        """
        Fetch client_id from mailbox

        Returns:
            Client UUID

        Raises:
            ValueError if mailbox not found or client_id missing
        """
        try:
            response = (
                self.client.table('mailboxes')
                .select('client_id')
                .eq('id', self.mailbox_id)
                .execute()
            )

            if not response.data:
                raise ValueError(f"Mailbox {self.mailbox_id} not found")

            client_id = response.data[0].get('client_id')
            if not client_id:
                raise ValueError(f"Mailbox {self.mailbox_id} has no client_id")

            return client_id

        except Exception as e:
            logger.error(f"Failed to fetch client_id: {e}")
            raise

    def link_emails(
        self,
        email_ids: Optional[List[str]] = None,
        batch_size: int = 500,
        force_relink: bool = False
    ) -> Dict:
        """
        Link emails to customer_contacts and customer_companies (batch mode)

        Groups emails by (contact_id, company_id) and batch updates them together
        to minimize HTTP requests.

        Args:
            email_ids: Optional list of specific email IDs to link
                      If None, processes all unlinked emails
            batch_size: Not used in batch mode (kept for compatibility)
            force_relink: If True, relink even if already linked

        Returns:
            Dictionary with linking statistics
        """
        logger.info(f"Starting email linking (batch mode, force_relink={force_relink})")

        # Load caches
        self._load_contact_cache()
        self._load_company_cache()

        # Fetch emails to process
        emails = self._fetch_emails_to_link(email_ids, force_relink)
        total_emails = len(emails)

        logger.info(f"Processing {total_emails} emails for linking")

        if total_emails == 0:
            return {
                'total_emails': 0,
                'linked': 0,
                'skipped': 0,
                'errors': []
            }

        # Build link mappings for each email
        # Group emails by (contact_id, company_id) for batch updates
        link_groups: Dict[Tuple[Optional[str], Optional[str]], List[str]] = {}
        skipped_email_ids = []
        timestamp = datetime.utcnow().isoformat()

        for email in emails:
            email_id = email['id']
            is_outbound = email.get('is_outbound', False)

            # Determine which email address to link
            if is_outbound:
                # Link to primary recipient
                recipients = email.get('recipients', [])
                if not recipients:
                    skipped_email_ids.append(email_id)
                    continue

                # Get first recipient
                if isinstance(recipients, list) and len(recipients) > 0:
                    recipient = recipients[0]
                    if isinstance(recipient, dict):
                        link_email = recipient.get('email')
                    elif isinstance(recipient, str):
                        link_email = recipient
                    else:
                        link_email = None
                else:
                    link_email = None

                if not link_email:
                    skipped_email_ids.append(email_id)
                    continue
            else:
                # Link to sender
                link_email = email.get('sender_email')
                if not link_email:
                    skipped_email_ids.append(email_id)
                    continue

            # Normalize email
            link_email = link_email.lower().strip()

            # Look up contact
            contact_id = self._contact_cache.get(link_email)
            if not contact_id:
                skipped_email_ids.append(email_id)
                continue

            # Look up company from contact's domain
            domain = self._extract_domain(link_email)
            company_id = self._company_cache.get(domain.lower()) if domain else None

            # Group by (contact_id, company_id) for batch update
            group_key = (contact_id, company_id)
            if group_key not in link_groups:
                link_groups[group_key] = []
            link_groups[group_key].append(email_id)

        logger.info(f"Grouped {total_emails - len(skipped_email_ids)} emails into "
                   f"{len(link_groups)} unique contact/company pairs")
        logger.info(f"Skipped {len(skipped_email_ids)} emails (no contact match)")

        # Batch update emails by group
        linked_count = 0
        errors = []

        for group_idx, ((contact_id, company_id), email_ids_list) in enumerate(link_groups.items(), 1):
            try:
                update_data = {
                    'customer_contact_id': contact_id,
                    'client_id': self.client_id,
                    'updated_at': timestamp
                }

                if company_id:
                    update_data['customer_company_id'] = company_id

                # Split large groups into chunks to avoid payload size limits
                email_chunks = [
                    email_ids_list[i:i + self.MAX_BATCH_SIZE]
                    for i in range(0, len(email_ids_list), self.MAX_BATCH_SIZE)
                ]

                # Update each chunk
                for chunk_idx, email_chunk in enumerate(email_chunks, 1):
                    response = (
                        self.client.table('emails')
                        .update(update_data)
                        .in_('id', email_chunk)
                        .execute()
                    )
                    linked_count += len(email_chunk)

                    if len(email_chunks) > 1:
                        logger.debug(f"Group {group_idx}: Chunk {chunk_idx}/{len(email_chunks)} "
                                   f"({len(email_chunk)} emails) linked")

                if group_idx % 50 == 0:
                    logger.info(f"Processed group {group_idx}/{len(link_groups)}: "
                               f"{linked_count} emails linked")

            except Exception as e:
                logger.error(f"Failed to link email group (contact={contact_id[:8]}..., "
                           f"{len(email_ids_list)} emails): {e}")
                errors.append({
                    'contact_id': contact_id,
                    'company_id': company_id,
                    'email_count': len(email_ids_list),
                    'error': str(e)
                })

        logger.info(f"Email linking complete: {linked_count} linked, "
                   f"{len(skipped_email_ids)} skipped, {len(errors)} group errors")

        return {
            'total_emails': total_emails,
            'linked': linked_count,
            'skipped': len(skipped_email_ids),
            'errors': errors,
            'groups_processed': len(link_groups)
        }

    def _fetch_emails_to_link(
        self,
        email_ids: Optional[List[str]],
        force_relink: bool
    ) -> List[Dict]:
        """
        Fetch emails that need linking, paginating in batches of 500.

        Uses or_ filter to include emails where processing_status is NULL.
        When email_ids is provided, chunks the in_ filter to avoid URL length limits.

        Args:
            email_ids: Optional specific email IDs
            force_relink: If True, include already linked emails

        Returns:
            List of email records
        """
        COLUMNS = 'id, sender_email, recipients, is_outbound, processing_status'
        PAGE_SIZE = 500
        ID_CHUNK_SIZE = 500  # Max IDs per in_ filter to stay under URL limits

        try:
            # When specific email IDs are provided, chunk the in_ filter
            if email_ids:
                total_chunks = (len(email_ids) + ID_CHUNK_SIZE - 1) // ID_CHUNK_SIZE
                logger.info(f"Email linking: {len(email_ids)} IDs to fetch in {total_chunks} chunks of {ID_CHUNK_SIZE}")
                all_emails = []
                for i in range(0, len(email_ids), ID_CHUNK_SIZE):
                    chunk = email_ids[i:i + ID_CHUNK_SIZE]
                    chunk_num = i // ID_CHUNK_SIZE + 1
                    response = self._execute_with_retry(
                        self.client.table('emails')
                        .select(COLUMNS)
                        .eq('mailbox_id', self.mailbox_id)
                        .in_('id', chunk)
                        .order('sent_date', desc=False)
                    )
                    raw_batch = response.data or []
                    filtered = [e for e in raw_batch if e.get('processing_status') != 'failed']
                    all_emails.extend(filtered)
                    logger.info(f"Email link chunk {chunk_num}/{total_chunks}: raw={len(raw_batch)}, kept={len(filtered)}, total so far={len(all_emails)}")
                logger.info(f"Email linking: {len(all_emails)} emails fetched from {len(email_ids)} IDs")
                return all_emails

            # General fetch with pagination — get count first
            if not force_relink:
                count_resp = self._execute_with_retry(
                    self.client.table('emails')
                    .select('id', count='exact')
                    .eq('mailbox_id', self.mailbox_id)
                    .is_('customer_contact_id', 'null')
                )
            else:
                count_resp = self._execute_with_retry(
                    self.client.table('emails')
                    .select('id', count='exact')
                    .eq('mailbox_id', self.mailbox_id)
                )
            total_to_link = count_resp.count or 0
            estimated_pages = (total_to_link + PAGE_SIZE - 1) // PAGE_SIZE
            logger.info(f"Email linking: {total_to_link} emails to link, ~{estimated_pages} pages of {PAGE_SIZE}")

            all_emails = []
            offset = 0
            page = 0

            while True:
                page += 1
                query = (
                    self.client.table('emails')
                    .select(COLUMNS)
                    .eq('mailbox_id', self.mailbox_id)
                )

                if not force_relink:
                    query = query.is_('customer_contact_id', 'null')

                response = self._execute_with_retry(
                    query
                    .order('sent_date', desc=False)
                    .range(offset, offset + PAGE_SIZE - 1)
                )
                raw_batch = response.data or []
                filtered = [e for e in raw_batch if e.get('processing_status') != 'failed']
                all_emails.extend(filtered)
                logger.info(f"Email link page {page}/{estimated_pages}: raw={len(raw_batch)}, kept={len(filtered)}, total so far={len(all_emails)}")

                if len(raw_batch) < PAGE_SIZE:
                    break
                offset += PAGE_SIZE

            logger.info(f"Email linking complete: {len(all_emails)} emails fetched (from {total_to_link} to link)")
            return all_emails

        except Exception as e:
            logger.error(f"Failed to fetch emails to link: {e}")
            raise

    def _load_contact_cache(self):
        """
        Load customer_contacts into cache for fast lookups.
        Paginates in batches of 500 to handle >1000 contacts.

        Cache structure: email (lowercase) -> contact_id
        """
        PAGE_SIZE = 500
        try:
            offset = 0
            while True:
                response = (
                    self.client.table('customer_contacts')
                    .select('id, email_address')
                    .eq('client_id', self.client_id)
                    .range(offset, offset + PAGE_SIZE - 1)
                    .execute()
                )
                batch = response.data or []
                for row in batch:
                    email = row['email_address'].lower()
                    self._contact_cache[email] = row['id']

                if len(batch) < PAGE_SIZE:
                    break
                offset += PAGE_SIZE

            logger.info(f"Loaded {len(self._contact_cache)} contacts into cache")

        except Exception as e:
            logger.error(f"Failed to load contact cache: {e}")
            # Continue with empty cache

    def _load_company_cache(self):
        """
        Load customer_companies into cache for fast lookups.
        Paginates in batches of 500 to handle >1000 companies.

        Cache structure: domain (lowercase) -> company_id

        Note: Uses email_domains JSONB array to map all domains
        """
        PAGE_SIZE = 500
        company_count = 0
        try:
            offset = 0
            while True:
                response = (
                    self.client.table('customer_companies')
                    .select('id, email_domains')
                    .eq('client_id', self.client_id)
                    .range(offset, offset + PAGE_SIZE - 1)
                    .execute()
                )
                batch = response.data or []
                company_count += len(batch)

                for row in batch:
                    company_id = row['id']
                    email_domains = row.get('email_domains', [])

                    for domain in email_domains:
                        self._company_cache[domain.lower()] = company_id

                if len(batch) < PAGE_SIZE:
                    break
                offset += PAGE_SIZE

            logger.info(f"Loaded {company_count} companies with "
                       f"{len(self._company_cache)} domain mappings into cache")

        except Exception as e:
            logger.error(f"Failed to load company cache: {e}")
            # Continue with empty cache

    def _link_email(self, email: Dict) -> bool:
        """
        Link a single email to contact and company

        For inbound emails: Link sender
        For outbound emails: Link primary recipient (first in TO list)

        Args:
            email: Email record

        Returns:
            True if linked successfully, False if skipped
        """
        email_id = email['id']
        is_outbound = email.get('is_outbound', False)

        # Determine which email address to link
        if is_outbound:
            # Link to primary recipient
            recipients = email.get('recipients', [])
            if not recipients:
                logger.debug(f"Email {email_id} has no recipients, skipping")
                return False

            # Get first recipient
            if isinstance(recipients, list) and len(recipients) > 0:
                recipient = recipients[0]
                if isinstance(recipient, dict):
                    link_email = recipient.get('email')
                elif isinstance(recipient, str):
                    link_email = recipient
                else:
                    link_email = None
            else:
                link_email = None

            if not link_email:
                logger.debug(f"Email {email_id} has invalid recipient format, skipping")
                return False

        else:
            # Link to sender
            link_email = email.get('sender_email')
            if not link_email:
                logger.debug(f"Email {email_id} has no sender_email, skipping")
                return False

        # Normalize email
        link_email = link_email.lower().strip()

        # Look up contact
        contact_id = self._contact_cache.get(link_email)

        if not contact_id:
            logger.debug(f"No contact found for {link_email}, skipping email {email_id}")
            return False

        # Look up company from contact's domain
        domain = self._extract_domain(link_email)
        company_id = self._company_cache.get(domain.lower()) if domain else None

        # Update email with links
        update_data = {
            'customer_contact_id': contact_id,
            'client_id': self.client_id,
            'updated_at': datetime.utcnow().isoformat()
        }

        if company_id:
            update_data['customer_company_id'] = company_id

        response = (
            self.client.table('emails')
            .update(update_data)
            .eq('id', email_id)
            .execute()
        )

        logger.debug(f"Linked email {email_id} to contact {contact_id}, company {company_id}")
        return True

    def _extract_domain(self, email: str) -> Optional[str]:
        """
        Extract domain from email address

        Args:
            email: Email address

        Returns:
            Domain or None
        """
        if not email or '@' not in email:
            return None

        return email.split('@')[1].lower()

    def get_linking_stats(self) -> Dict:
        """
        Get current linking statistics for this mailbox

        Returns:
            Dictionary with linking statistics
        """
        try:
            # Total emails (exclude only explicitly failed)
            total_response = (
                self.client.table('emails')
                .select('id', count='exact')
                .eq('mailbox_id', self.mailbox_id)
                .neq('processing_status', 'failed')
                .execute()
            )
            total_emails = total_response.count

            # Linked emails (have customer_contact_id)
            linked_response = (
                self.client.table('emails')
                .select('id', count='exact')
                .eq('mailbox_id', self.mailbox_id)
                .neq('processing_status', 'failed')
                .not_.is_('customer_contact_id', 'null')
                .execute()
            )
            linked_emails = linked_response.count

            # With company link
            company_linked_response = (
                self.client.table('emails')
                .select('id', count='exact')
                .eq('mailbox_id', self.mailbox_id)
                .neq('processing_status', 'failed')
                .not_.is_('customer_company_id', 'null')
                .execute()
            )
            company_linked_emails = company_linked_response.count

            # Calculate rates
            link_rate = round(linked_emails / total_emails * 100, 2) if total_emails > 0 else 0
            company_rate = round(company_linked_emails / total_emails * 100, 2) if total_emails > 0 else 0

            return {
                'total_emails': total_emails,
                'linked_emails': linked_emails,
                'company_linked_emails': company_linked_emails,
                'unlinked_emails': total_emails - linked_emails,
                'contact_link_rate': link_rate,
                'company_link_rate': company_rate,
            }

        except Exception as e:
            logger.error(f"Failed to get linking stats: {e}")
            return {}

    def relink_all(self, batch_size: int = 500) -> Dict:
        """
        Relink all emails (clears existing links and relinks)

        Use this to fix incorrect links after updating contacts/companies

        Args:
            batch_size: Batch size for processing

        Returns:
            Dictionary with relinking statistics
        """
        logger.info("Relinking all emails (clearing existing links)")

        # Clear existing links
        try:
            self.client.table('emails').update({
                'customer_contact_id': None,
                'customer_company_id': None,
                'client_id': None
            }).eq('mailbox_id', self.mailbox_id).execute()

            logger.info("Cleared existing links")

        except Exception as e:
            logger.error(f"Failed to clear links: {e}")
            raise

        # Relink
        return self.link_emails(batch_size=batch_size, force_relink=True)


# Example usage
if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m backend.src.services.email_linker <mailbox_id> [--force-relink] [--stats-only]")
        sys.exit(1)

    mailbox_id = sys.argv[1]
    force_relink = '--force-relink' in sys.argv
    stats_only = '--stats-only' in sys.argv

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Initialize linker
    linker = EmailLinker(mailbox_id=mailbox_id)

    # Get current stats
    print("\n=== Current Linking Statistics ===")
    stats = linker.get_linking_stats()
    for key, value in stats.items():
        print(f"{key}: {value}")

    if stats_only:
        sys.exit(0)

    # Link emails
    print(f"\nLinking emails (force_relink={force_relink})...")
    result = linker.link_emails(force_relink=force_relink)

    print("\n=== Linking Results ===")
    for key, value in result.items():
        if key != 'errors':
            print(f"{key}: {value}")

    if result['errors']:
        print(f"\nErrors: {len(result['errors'])}")
        for error in result['errors'][:10]:
            print(f"  - {error['email_id']} ({error['sender']}): {error['error']}")

    # Get updated stats
    print("\n=== Updated Linking Statistics ===")
    updated_stats = linker.get_linking_stats()
    for key, value in updated_stats.items():
        print(f"{key}: {value}")
