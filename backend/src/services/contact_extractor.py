"""
Contact Extractor Service - Sprint 2

Purpose: Extract unique contacts from emails for customer data pipeline
Step 2 of 13-step extraction pipeline

Features:
- Scans all successful emails in a mailbox
- Extracts sender + all recipients (to, cc, bcc)
- Detects mailing lists using List-* headers
- Detects shared/generic addresses (info@, sales@, etc.)
- Uses domain_parser and name_parser utilities
- Returns deduplicated contact list with metadata

Author: Sprint 2 Implementation
"""

from typing import List, Dict, Optional, Set, Tuple
from dataclasses import dataclass, asdict
import logging
import re
import time
from datetime import datetime

from ..database.supabase_client import SupabaseClient
from ..utils.domain_parser import (
    extract_domain,
    is_noreply_address,
    is_distribution_list,
    classify_email_type
)
from ..utils.name_parser import parse_display_name

logger = logging.getLogger(__name__)


@dataclass
class ExtractedContact:
    """Contact extracted from emails"""
    email: str
    display_name: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    domain: str

    # Source tracking
    first_seen_email_id: str
    first_seen_date: datetime
    last_seen_email_id: str
    last_seen_date: datetime

    # Occurrence counts
    as_sender_count: int = 0
    as_recipient_count: int = 0
    total_emails: int = 0

    # Flags
    is_mailing_list: bool = False
    is_shared_address: bool = False
    is_noreply: bool = False
    email_type: str = 'personal'  # 'personal', 'noreply', 'distribution'

    # Source email IDs for reference
    source_email_ids: List[str] = None

    def __post_init__(self):
        """Initialize mutable default"""
        if self.source_email_ids is None:
            self.source_email_ids = []


class ContactExtractor:
    """
    Extract contacts from emails with mailing list detection

    Usage:
        extractor = ContactExtractor(mailbox_id="uuid-here")
        contacts = extractor.extract_contacts()

        # With filtering
        contacts = extractor.extract_contacts(
            exclude_mailing_lists=True,
            exclude_noreply=True,
            exclude_shared=True
        )
    """

    # Shared address patterns (info@, sales@, support@, etc.)
    SHARED_ADDRESS_PATTERNS = [
        r'^info@',
        r'^contact@',
        r'^hello@',
        r'^sales@',
        r'^support@',
        r'^help@',
        r'^admin@',
        r'^office@',
        r'^team@',
        r'^service@',
        r'^inquiries@',
        r'^feedback@',
        r'^billing@',
        r'^careers@',
        r'^jobs@',
        r'^hr@',
        r'^press@',
        r'^media@',
        r'^marketing@',
        r'^webmaster@',
        r'^postmaster@',
    ]

    # Mailing list headers to check
    MAILING_LIST_HEADERS = [
        'List-Id',
        'List-Unsubscribe',
        'List-Subscribe',
        'List-Post',
        'List-Help',
        'List-Owner',
        'List-Archive',
        'Mailing-List',
        'X-Mailing-List',
        'X-Loop',
    ]

    def __init__(self, mailbox_id: str, client_id: Optional[str] = None):
        """
        Initialize contact extractor

        Args:
            mailbox_id: Mailbox UUID to extract contacts from
            client_id: Optional client UUID for filtering
        """
        self.mailbox_id = mailbox_id
        self.client_id = client_id
        self.client = SupabaseClient.get_client(use_service_key=True)

        # Contact deduplication cache: email -> ExtractedContact
        self._contact_cache: Dict[str, ExtractedContact] = {}

        logger.info(f"ContactExtractor initialized for mailbox {mailbox_id}")

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

    def extract_contacts(
        self,
        exclude_mailing_lists: bool = False,  # Changed default to False
        exclude_noreply: bool = False,  # Changed default to False
        exclude_shared: bool = False,  # Changed default to False
        limit: Optional[int] = None
    ) -> List[Dict]:
        """
        Extract all unique contacts from mailbox emails (WITH TAGGING)

        Now includes ALL contacts and tags them by type instead of filtering.
        Use contact_type field to filter in queries if needed.

        Args:
            exclude_mailing_lists: DEPRECATED - kept for compatibility (always False)
            exclude_noreply: DEPRECATED - kept for compatibility (always False)
            exclude_shared: DEPRECATED - kept for compatibility (always False)
            limit: Optional limit for testing (processes first N emails)

        Returns:
            List of contact dictionaries with metadata including contact_type:
            - 'person': Real person (default)
            - 'automated': noreply, no-reply, bounce, automated
            - 'shared': info@, support@, sales@, etc.
            - 'mailing_list': Detected via List-* headers
            - 'unknown': Could not classify
        """
        logger.info(f"Starting contact extraction for mailbox {self.mailbox_id}")
        logger.info(f"Extracting ALL contacts with classification tags (not filtering)")

        # Reset cache for new extraction
        self._contact_cache = {}

        # Query all successful emails
        emails = self._fetch_emails(limit=limit)
        total_emails = len(emails)

        logger.info(f"Processing {total_emails} emails for contact extraction")

        # Process each email
        processed_count = 0
        mailing_list_count = 0

        for email in emails:
            # Check if email is from mailing list (tag but don't skip)
            is_mailing_list = self._is_mailing_list_email(email)
            if is_mailing_list:
                mailing_list_count += 1

            # Extract contacts from this email (now includes all contacts)
            self._extract_from_email(email, is_mailing_list)
            processed_count += 1

            if processed_count % 500 == 0:
                logger.info(f"Processed {processed_count}/{total_emails} emails, "
                           f"extracted {len(self._contact_cache)} unique contacts")

        logger.info(f"Contact extraction complete: {processed_count} emails processed, "
                   f"{mailing_list_count} mailing list emails detected (included)")

        # Convert cache to list and classify (no filtering!)
        contacts = self._classify_contacts()

        # Log classification breakdown
        type_counts = {}
        for contact in contacts:
            ctype = contact.get('contact_type', 'unknown')
            type_counts[ctype] = type_counts.get(ctype, 0) + 1

        logger.info(f"Contact classification: {type_counts}")
        logger.info(f"Total contacts extracted: {len(contacts)}")

        return contacts

    def _fetch_emails(self, limit: Optional[int] = None) -> List[Dict]:
        """
        Fetch all non-failed emails from mailbox, paginating in batches of 500.

        Uses or_ filter to include emails where processing_status is NULL
        (PostgreSQL's != 'failed' excludes NULLs).

        Args:
            limit: Optional limit for testing

        Returns:
            List of email records
        """
        try:
            PAGE_SIZE = 500
            COLUMNS = ('id, sender_email, sender_name, recipients, cc_list, bcc_list, '
                       'sent_date, raw_headers, is_outbound, processing_status')

            # Small limit: single query
            if limit and limit <= PAGE_SIZE:
                response = self._execute_with_retry(
                    self.client.table('emails')
                    .select(COLUMNS)
                    .eq('mailbox_id', self.mailbox_id)
                    .order('sent_date', desc=False)
                    .limit(limit)
                )
                result = [e for e in (response.data or []) if e.get('processing_status') != 'failed']
                logger.info(f"Fetched {len(result)} emails (limit={limit})")
                return result

            # Get total count for visibility
            count_resp = self._execute_with_retry(
                self.client.table('emails')
                .select('id', count='exact')
                .eq('mailbox_id', self.mailbox_id)
            )
            total_in_db = count_resp.count or 0
            estimated_pages = (total_in_db + PAGE_SIZE - 1) // PAGE_SIZE
            logger.info(f"Contact extraction: {total_in_db} total emails in mailbox, ~{estimated_pages} pages of {PAGE_SIZE}")

            # Paginated fetch
            all_emails = []
            offset = 0
            page = 0

            while True:
                page += 1
                response = self._execute_with_retry(
                    self.client.table('emails')
                    .select(COLUMNS)
                    .eq('mailbox_id', self.mailbox_id)
                    .order('sent_date', desc=False)
                    .range(offset, offset + PAGE_SIZE - 1)
                )
                raw_batch = response.data or []
                filtered = [e for e in raw_batch if e.get('processing_status') != 'failed']
                all_emails.extend(filtered)
                logger.info(f"Contact extraction page {page}/{estimated_pages}: raw={len(raw_batch)}, kept={len(filtered)}, total so far={len(all_emails)}", extra={'mailbox_id': self.mailbox_id})

                if len(raw_batch) == 0:
                    break
                offset += len(raw_batch)

                if limit and len(all_emails) >= limit:
                    return all_emails[:limit]

            logger.info(f"Contact extraction complete: {len(all_emails)} emails fetched (from {total_in_db} total)")
            return all_emails

        except Exception as e:
            logger.error(f"Failed to fetch emails: {e}")
            raise

    def _is_mailing_list_email(self, email: Dict) -> bool:
        """
        Detect if email is from a mailing list

        Checks for List-* headers in raw_headers

        Args:
            email: Email record

        Returns:
            True if mailing list email
        """
        raw_headers = email.get('raw_headers', {})

        if not raw_headers:
            return False

        # Check for any mailing list headers
        for header in self.MAILING_LIST_HEADERS:
            if header in raw_headers:
                logger.debug(f"Email {email['id']} is mailing list (has {header} header)")
                return True

        return False

    def _is_shared_address(self, email: str) -> bool:
        """
        Detect if email is a shared/generic address

        Args:
            email: Email address

        Returns:
            True if shared address (info@, sales@, etc.)
        """
        email_lower = email.lower()

        for pattern in self.SHARED_ADDRESS_PATTERNS:
            if re.match(pattern, email_lower):
                return True

        return False

    def _extract_from_email(self, email: Dict, is_mailing_list: bool = False):
        """
        Extract all contacts from a single email

        Extracts:
        - Sender (unless outbound)
        - Recipients (to, cc, bcc) (unless inbound)

        Args:
            email: Email record
            is_mailing_list: Whether email is from mailing list
        """
        email_id = email['id']
        sent_date = datetime.fromisoformat(email['sent_date'].replace('Z', '+00:00'))
        is_outbound = email.get('is_outbound', False)

        # Extract sender (if inbound)
        if not is_outbound:
            sender_email = email.get('sender_email')
            sender_name = email.get('sender_name')

            if sender_email:
                self._add_contact(
                    email=sender_email,
                    display_name=sender_name,
                    email_id=email_id,
                    sent_date=sent_date,
                    as_sender=True,
                    is_mailing_list=is_mailing_list
                )

        # Extract recipients (if outbound or for context)
        # We extract recipients from both inbound and outbound for complete picture
        self._extract_recipients(
            email_id=email_id,
            recipients=email.get('recipients', []),
            sent_date=sent_date,
            is_mailing_list=is_mailing_list
        )

        self._extract_recipients(
            email_id=email_id,
            recipients=email.get('cc_list', []),
            sent_date=sent_date,
            is_mailing_list=is_mailing_list
        )

        # BCC only available on outbound emails we sent
        if is_outbound:
            self._extract_recipients(
                email_id=email_id,
                recipients=email.get('bcc_list', []),
                sent_date=sent_date,
                is_mailing_list=is_mailing_list
            )

    def _extract_recipients(
        self,
        email_id: str,
        recipients: List,
        sent_date: datetime,
        is_mailing_list: bool = False
    ):
        """
        Extract contacts from recipient list

        Args:
            email_id: Source email ID
            recipients: List of recipients (JSONB array)
            sent_date: Email sent date
            is_mailing_list: Whether email is from mailing list
        """
        if not recipients:
            return

        for recipient in recipients:
            # Handle different recipient formats
            if isinstance(recipient, dict):
                recipient_email = recipient.get('email')
                recipient_name = recipient.get('name')
            elif isinstance(recipient, str):
                recipient_email = recipient
                recipient_name = None
            else:
                continue

            if recipient_email:
                self._add_contact(
                    email=recipient_email,
                    display_name=recipient_name,
                    email_id=email_id,
                    sent_date=sent_date,
                    as_sender=False,
                    is_mailing_list=is_mailing_list
                )

    def _add_contact(
        self,
        email: str,
        display_name: Optional[str],
        email_id: str,
        sent_date: datetime,
        as_sender: bool,
        is_mailing_list: bool = False
    ):
        """
        Add or update contact in cache

        Args:
            email: Email address
            display_name: Display name (optional)
            email_id: Source email ID
            sent_date: Email sent date
            as_sender: True if this contact was sender
            is_mailing_list: Whether from mailing list
        """
        # Normalize email
        email = email.lower().strip()

        # Extract domain
        domain = extract_domain(email)
        if not domain:
            logger.warning(f"Failed to extract domain from email: {email}")
            return

        # Parse name
        parsed_name = parse_display_name(display_name, email)

        # Classify email type
        email_type = classify_email_type(email)
        is_noreply = is_noreply_address(email)
        is_shared = self._is_shared_address(email)
        is_distribution = is_distribution_list(email)

        # Check if contact already exists in cache
        if email in self._contact_cache:
            # Update existing contact
            contact = self._contact_cache[email]

            # Update counts
            if as_sender:
                contact.as_sender_count += 1
            else:
                contact.as_recipient_count += 1

            contact.total_emails += 1

            # Update last seen
            if sent_date > contact.last_seen_date:
                contact.last_seen_date = sent_date
                contact.last_seen_email_id = email_id

            # Update first seen if earlier
            if sent_date < contact.first_seen_date:
                contact.first_seen_date = sent_date
                contact.first_seen_email_id = email_id

            # Update display name if we have a better one
            if display_name and not contact.display_name:
                contact.display_name = display_name
                contact.first_name = parsed_name.first_name
                contact.last_name = parsed_name.last_name

            # Add source email ID
            if email_id not in contact.source_email_ids:
                contact.source_email_ids.append(email_id)

        else:
            # Create new contact
            contact = ExtractedContact(
                email=email,
                display_name=display_name,
                first_name=parsed_name.first_name,
                last_name=parsed_name.last_name,
                domain=domain,
                first_seen_email_id=email_id,
                first_seen_date=sent_date,
                last_seen_email_id=email_id,
                last_seen_date=sent_date,
                as_sender_count=1 if as_sender else 0,
                as_recipient_count=0 if as_sender else 1,
                total_emails=1,
                is_mailing_list=is_mailing_list,
                is_shared_address=is_shared,
                is_noreply=is_noreply,
                email_type=email_type,
                source_email_ids=[email_id]
            )

            self._contact_cache[email] = contact

    def _classify_contacts(self) -> List[Dict]:
        """
        Convert cache to list and classify all contacts by type

        No filtering - all contacts are returned with contact_type field.
        This allows the caller to decide whether to filter based on contact_type.

        Returns:
            List of contact dictionaries with contact_type field:
            - 'person': Real person (default)
            - 'automated': noreply, no-reply, bounce, automated
            - 'shared': info@, support@, sales@, etc.
            - 'mailing_list': Detected via List-* headers
            - 'unknown': Could not classify
        """
        contacts = []

        for contact in self._contact_cache.values():
            # Convert to dict
            contact_dict = asdict(contact)

            # Determine contact_type based on flags (priority order matters)
            if contact.is_mailing_list:
                contact_type = 'mailing_list'
            elif contact.is_noreply:
                contact_type = 'automated'
            elif contact.email_type == 'distribution':
                contact_type = 'automated'
            elif contact.is_shared_address:
                contact_type = 'shared'
            elif contact.email_type == 'personal':
                contact_type = 'person'
            else:
                contact_type = 'unknown'

            # Add contact_type to dictionary
            contact_dict['contact_type'] = contact_type

            contacts.append(contact_dict)

        logger.info(f"Classified {len(contacts)} contacts (no filtering applied)")

        # Sort by total_emails descending (most active first)
        contacts.sort(key=lambda c: c['total_emails'], reverse=True)

        return contacts

    def get_contact_summary(self) -> Dict:
        """
        Get summary statistics of extracted contacts

        Returns:
            Dictionary with contact statistics
        """
        if not self._contact_cache:
            return {
                'total_contacts': 0,
                'sender_contacts': 0,
                'recipient_contacts': 0,
                'mailing_list_contacts': 0,
                'noreply_contacts': 0,
                'shared_contacts': 0,
                'distribution_contacts': 0,
                'personal_contacts': 0,
            }

        total = len(self._contact_cache)
        senders = sum(1 for c in self._contact_cache.values() if c.as_sender_count > 0)
        recipients = sum(1 for c in self._contact_cache.values() if c.as_recipient_count > 0)
        mailing_lists = sum(1 for c in self._contact_cache.values() if c.is_mailing_list)
        noreply = sum(1 for c in self._contact_cache.values() if c.is_noreply)
        shared = sum(1 for c in self._contact_cache.values() if c.is_shared_address)
        distribution = sum(1 for c in self._contact_cache.values() if c.email_type == 'distribution')
        personal = sum(1 for c in self._contact_cache.values() if c.email_type == 'personal')

        return {
            'total_contacts': total,
            'sender_contacts': senders,
            'recipient_contacts': recipients,
            'mailing_list_contacts': mailing_lists,
            'noreply_contacts': noreply,
            'shared_contacts': shared,
            'distribution_contacts': distribution,
            'personal_contacts': personal,
        }


# Example usage
if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m backend.src.services.contact_extractor <mailbox_id>")
        sys.exit(1)

    mailbox_id = sys.argv[1]

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Extract contacts
    extractor = ContactExtractor(mailbox_id=mailbox_id)
    contacts = extractor.extract_contacts(
        exclude_mailing_lists=True,
        exclude_noreply=True,
        exclude_shared=True
    )

    # Print summary
    summary = extractor.get_contact_summary()
    print("\n=== Contact Extraction Summary ===")
    for key, value in summary.items():
        print(f"{key}: {value}")

    print(f"\nTotal contacts after filtering: {len(contacts)}")

    # Print top 10 contacts
    print("\n=== Top 10 Most Active Contacts ===")
    for i, contact in enumerate(contacts[:10], 1):
        print(f"{i}. {contact['email']} ({contact['display_name']}) - "
              f"{contact['total_emails']} emails, "
              f"domain: {contact['domain']}")
