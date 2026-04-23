"""
Role Classifier Service - Sprint 2

Purpose: Extract and classify job titles/roles from email signatures
Step 6 of 13-step extraction pipeline

Features:
- Extracts job titles from email signatures
- Classifies into seniority_level (c_level, vp, director, manager, etc.)
- Classifies into functional_role (sales, marketing, engineering, etc.)
- Determines is_decision_maker flag
- Calculates confidence scores based on source
- Handles multiple title variations per contact

Title Sources (in priority order):
1. Manual input (confidence: 1.0)
2. CSV import (confidence: 0.9)
3. AI enrichment (confidence: 0.85)
4. Email signature (confidence: 0.7)
5. Inferred from context (confidence: 0.3)

Author: Sprint 2 Implementation
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
import logging
import re
import time
from datetime import datetime

from ..database.supabase_client import SupabaseClient
from ..utils.title_parser import parse_title, TitleInfo

logger = logging.getLogger(__name__)


@dataclass
class ClassifiedRole:
    """Role classification result for a contact"""
    email: str
    title_raw: Optional[str]  # Original title string

    # Classification
    seniority_level: str
    functional_role: str
    is_decision_maker: bool

    # Source and confidence
    role_source: str  # 'email_signature', 'manual', 'csv_import', 'ai_enriched', 'inferred', 'unknown'
    role_confidence: float  # 0.0-1.0

    # Metadata
    department: Optional[str] = None
    source_email_id: Optional[str] = None  # Email ID where title was extracted


class RoleClassifier:
    """
    Extract and classify job titles/roles from emails

    Usage:
        classifier = RoleClassifier(mailbox_id="uuid-here")

        # Classify roles for contacts
        roles = classifier.classify_roles(contacts)

        # Extract titles from email signatures
        titles = classifier.extract_titles_from_signatures(limit=1000)

        # Update customer_contacts with role info
        classifier.update_contact_roles(roles)
    """

    # Email signature patterns
    SIGNATURE_PATTERNS = [
        # Common signature separators
        r'(?:^|\n)(?:--|__|\*\*|==)(?:\s*\n)',
        r'(?:\n\s*){2,}',  # Double line breaks

        # "Sent from" patterns (mobile signatures)
        r'\n\s*Sent from (?:my )?(?:iPhone|iPad|Android|Mobile)',
        r'\n\s*Get Outlook for (?:iOS|Android)',

        # Common signature markers
        r'\n\s*(?:Best regards?|Regards?|Thanks?|Cheers|Sincerely),?\s*\n',
        r'\n\s*(?:Thank you|Thx|BR),?\s*\n',
    ]

    # Title extraction patterns (after name line)
    # Format: "Name\nTitle | Company" or "Name\nTitle\nCompany"
    TITLE_LINE_PATTERNS = [
        # Title with company on same line
        r'^([^|\n]+)\s*\|\s*([^|\n]+)$',  # "Senior Manager | Acme Corp"

        # Title with separators
        r'^([^•·\n]+)\s*[•·]\s*([^•·\n]+)$',  # "Senior Manager • Acme Corp"

        # Standalone title line
        r'^([A-Z][^|\n]{5,60})$',  # "Senior Marketing Manager"

        # Title at company
        r'^([^@\n]+)\s+at\s+([^@\n]+)$',  # "Senior Manager at Acme Corp"

        # Title, department
        r'^([^,\n]+),\s*([^,\n]+)$',  # "Senior Manager, Sales"
    ]

    def __init__(self, mailbox_id: str, client_id: Optional[str] = None):
        """
        Initialize role classifier

        Args:
            mailbox_id: Mailbox UUID to process
            client_id: Optional client UUID
        """
        self.mailbox_id = mailbox_id
        self.client_id = client_id
        self.client = SupabaseClient.get_client(use_service_key=True)

        logger.info(f"RoleClassifier initialized for mailbox {mailbox_id}")

    def classify_roles(
        self,
        contacts: List[Dict],
        extract_from_signatures: bool = True
    ) -> List[ClassifiedRole]:
        """
        Classify roles for a list of contacts

        Args:
            contacts: List of contact dictionaries from contact_extractor
            extract_from_signatures: If True, fetch and parse email signatures

        Returns:
            List of classified roles
        """
        logger.info(f"Classifying roles for {len(contacts)} contacts")

        classified_roles = []

        # If extracting from signatures, get email bodies
        if extract_from_signatures:
            # Get source email IDs for all contacts
            email_ids = []
            for contact in contacts:
                email_ids.extend(contact.get('source_email_ids', []))

            # Fetch email bodies in batch
            signatures = self._fetch_email_signatures(list(set(email_ids)))
        else:
            signatures = {}

        # Classify each contact
        for contact in contacts:
            role = self._classify_contact(contact, signatures)
            if role:
                classified_roles.append(role)

        logger.info(f"Classified {len(classified_roles)} contact roles")

        return classified_roles

    def _classify_contact(
        self,
        contact: Dict,
        signatures: Dict[str, str]
    ) -> Optional[ClassifiedRole]:
        """
        Classify role for a single contact

        Args:
            contact: Contact dictionary
            signatures: Dictionary mapping email_id -> body_text

        Returns:
            ClassifiedRole or None if no title found
        """
        email = contact['email']

        # Try to extract title from email signatures
        title_raw = None
        source_email_id = None
        role_source = 'unknown'

        for email_id in contact.get('source_email_ids', [])[:5]:  # Check first 5 emails
            signature = signatures.get(email_id)
            if signature:
                extracted_title = self._extract_title_from_signature(signature, contact)
                if extracted_title:
                    title_raw = extracted_title
                    source_email_id = email_id
                    role_source = 'email_signature'
                    break

        # If no title found, return with unknown classification
        if not title_raw:
            title_info = parse_title(None, source='unknown')
        else:
            title_info = parse_title(title_raw, source=role_source)

        return ClassifiedRole(
            email=email,
            title_raw=title_raw,
            seniority_level=title_info.seniority_level,
            functional_role=title_info.functional_role,
            is_decision_maker=title_info.is_decision_maker,
            role_source=role_source,
            role_confidence=title_info.confidence,
            source_email_id=source_email_id
        )

    def _fetch_email_signatures(self, email_ids: List[str]) -> Dict[str, str]:
        """
        Fetch email body_text for signature extraction

        Args:
            email_ids: List of email UUIDs

        Returns:
            Dictionary mapping email_id -> body_text
        """
        if not email_ids:
            return {}

        try:
            # Fetch in small batches — body_text can be large; HTTP/2 stream
            # cancellations (ConnectionTerminated error_code:9) happen with big payloads
            batch_size = 20
            all_signatures = {}
            total_ids = len(email_ids)
            logger.info(f"Fetching signatures for {total_ids} emails (~{total_ids // batch_size} batches)")

            for i in range(0, total_ids, batch_size):
                batch = email_ids[i:i + batch_size]

                fetched = False
                for attempt in range(3):
                    try:
                        response = (
                            self.client.table('emails')
                            .select('id, body_text')
                            .in_('id', batch)
                            .execute()
                        )
                        for row in response.data:
                            body_text = row.get('body_text', '')
                            # Only keep last 1000 characters — signatures are at end
                            if body_text:
                                all_signatures[row['id']] = body_text[-1000:] if len(body_text) > 1000 else body_text
                            else:
                                all_signatures[row['id']] = ''
                        fetched = True
                        break
                    except Exception as batch_error:
                        if attempt < 2:
                            time.sleep(2 ** attempt)  # 1s, 2s
                        else:
                            logger.warning(f"Failed to fetch batch of {len(batch)} email signatures: {batch_error}")
                            for email_id in batch:
                                all_signatures[email_id] = ''

                if (i + batch_size) % 500 == 0:
                    logger.info(f"Signature fetch progress: {i + batch_size}/{total_ids}")

            logger.info(f"Fetched signatures for {len(all_signatures)} emails")
            return all_signatures

        except Exception as e:
            logger.error(f"Failed to fetch email signatures: {e}")
            return {}

    def _extract_title_from_signature(
        self,
        body_text: str,
        contact: Dict
    ) -> Optional[str]:
        """
        Extract job title from email signature

        Strategy:
        1. Find signature block (usually at end after "--" or double newline)
        2. Look for lines after contact name
        3. Extract line that looks like a job title

        Args:
            body_text: Email body text
            contact: Contact dictionary

        Returns:
            Extracted title string or None
        """
        if not body_text:
            return None

        # Get contact name for matching
        contact_name = contact.get('display_name', '')
        first_name = contact.get('first_name', '')
        last_name = contact.get('last_name', '')

        # Find signature block (last 500 characters usually sufficient)
        signature_block = body_text[-500:]

        # Split into lines
        lines = [line.strip() for line in signature_block.split('\n') if line.strip()]

        # Try to find name line
        name_index = -1

        for i, line in enumerate(lines):
            # Check if line contains contact name
            if contact_name and contact_name.lower() in line.lower():
                name_index = i
                break
            elif first_name and last_name:
                if first_name.lower() in line.lower() and last_name.lower() in line.lower():
                    name_index = i
                    break

        # If name not found, try first few lines (signatures often start with name)
        if name_index == -1:
            name_index = 0

        # Look at lines after name
        for i in range(name_index + 1, min(name_index + 4, len(lines))):
            line = lines[i]

            # Skip email addresses, phone numbers, URLs
            if '@' in line or 'http' in line.lower() or re.match(r'^\+?\d', line):
                continue

            # Skip very short lines (< 5 chars)
            if len(line) < 5:
                continue

            # Skip lines with only company name (usually on separate line)
            # Check if line matches title pattern
            if self._looks_like_title(line):
                # Extract title part (before | or other separators)
                title = self._extract_title_part(line)
                if title:
                    return title

        return None

    def _looks_like_title(self, line: str) -> bool:
        """
        Check if line looks like a job title

        Args:
            line: Text line

        Returns:
            True if line looks like a job title
        """
        # Skip if too long (> 80 chars)
        if len(line) > 80:
            return False

        # Skip if too short (< 5 chars)
        if len(line) < 5:
            return False

        # Skip if all caps (likely company name or label)
        if line.isupper() and len(line) > 10:
            return False

        # Skip common non-title patterns
        skip_patterns = [
            r'^\d+',  # Starts with number
            r'©.*copyright',  # Copyright notice
            r'confidential',  # Confidentiality notice
            r'unsubscribe',  # Unsubscribe link
            r'privacy policy',  # Privacy links
            r'(?:^|\s)(?:kind\s+)?regards?,?\s*$',
            r'(?:^|\s)(?:best\s+)?regards?,?\s*$',
            r'(?:^|\s)(?:warm\s+)?regards?,?\s*$',
            r'(?:^|\s)thanks?,?\s*$',
            r'(?:^|\s)thank\s+you,?\s*$',
            r'(?:^|\s)cheers,?\s*$',
            r'(?:^|\s)sincerely,?\s*$',
            r'(?:^|\s)(?:yours\s+)?(?:faithfully|truly),?\s*$',
            r'(?:^|\s)(?:thx|br|ty),?\s*$',
            r'^sent\s+from\s+(?:my\s+)?',
            r'^get\s+outlook\s+for\s+',
        ]

        for pattern in skip_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                return False

        # Look for title keywords
        title_keywords = [
            'manager', 'director', 'president', 'officer', 'executive',
            'engineer', 'developer', 'analyst', 'specialist', 'coordinator',
            'consultant', 'advisor', 'lead', 'head', 'chief', 'vp',
            'associate', 'assistant', 'representative', 'agent'
        ]

        line_lower = line.lower()
        for keyword in title_keywords:
            if keyword in line_lower:
                return True

        # If line has proper case and 2-5 words, might be title
        words = line.split()
        if 2 <= len(words) <= 5 and line[0].isupper():
            return True

        return False

    def _extract_title_part(self, line: str) -> Optional[str]:
        """
        Extract title part from line (remove company name, separators)

        Args:
            line: Line containing title

        Returns:
            Cleaned title string
        """
        # Try patterns
        for pattern in self.TITLE_LINE_PATTERNS:
            match = re.match(pattern, line)
            if match:
                # Return first capture group (title part)
                title = match.group(1).strip()
                return title

        # If no pattern matched, return line as-is (cleaned)
        return line.strip()

    def update_contact_roles(
        self,
        roles: List[ClassifiedRole],
        batch_size: int = 500
    ) -> Dict:
        """
        Update customer_contacts table with role classifications using batch operations

        Args:
            roles: List of classified roles
            batch_size: Batch size for RPC calls (default 500)

        Returns:
            Dictionary with update statistics
        """
        logger.info(f"Processing {len(roles)} contact roles using batch update function")

        if len(roles) == 0:
            return {
                'total_roles': 0,
                'updated': 0,
                'errors': [],
                'with_titles': 0,
                'decision_makers': 0
            }

        # Calculate summary metrics
        with_title = sum(1 for r in roles if r.title_raw)
        decision_makers = sum(1 for r in roles if r.is_decision_maker)

        logger.info(f"Role classification summary: {with_title} with titles, "
                   f"{decision_makers} decision makers")

        # Batch UPDATE using PostgreSQL function
        updated_count = 0
        errors = []

        # Process in batches to avoid overwhelming the RPC function
        for i in range(0, len(roles), batch_size):
            batch = roles[i:i + batch_size]

            try:
                # Prepare JSONB array for batch update
                update_payload = [
                    {
                        'email_address': role.email,
                        'client_id': str(self.client_id),
                        'job_title': role.title_raw,
                        'seniority_level': role.seniority_level,
                        'functional_role': role.functional_role,
                        'is_decision_maker': role.is_decision_maker,
                        'role_source': role.role_source,
                        'role_confidence': float(role.role_confidence),
                        'department': role.department
                    }
                    for role in batch
                ]

                # Call PostgreSQL batch update function
                response = self.client.rpc('batch_update_contact_roles', {
                    'updates': update_payload
                }).execute()

                if response.data and len(response.data) > 0:
                    batch_updated = response.data[0].get('updated_count', 0)
                    batch_errors = response.data[0].get('error_count', 0)

                    updated_count += batch_updated

                    if batch_errors > 0:
                        errors.append({
                            'batch': i // batch_size + 1,
                            'error_count': batch_errors
                        })

                    logger.info(f"Batch {i//batch_size + 1}: Updated {batch_updated} roles, "
                               f"{batch_errors} errors")
                else:
                    logger.warning(f"Batch {i//batch_size + 1} returned no data")

            except Exception as e:
                logger.error(f"Failed to update batch {i//batch_size + 1}: {e}")
                errors.append({
                    'batch': i // batch_size + 1,
                    'error': str(e)
                })

            if (i + batch_size) % 1000 == 0:
                logger.info(f"Progress: Updated {updated_count}/{len(roles)} contact roles")

        logger.info(f"Role update complete: {updated_count} updated, {len(errors)} batch errors")

        return {
            'total_roles': len(roles),
            'updated': updated_count,
            'errors': errors,
            'with_titles': with_title,
            'decision_makers': decision_makers
        }

    def get_role_summary(self, roles: List[ClassifiedRole]) -> Dict:
        """
        Get summary statistics of role classifications

        Args:
            roles: List of classified roles

        Returns:
            Dictionary with role statistics
        """
        from collections import Counter

        total = len(roles)
        with_title = sum(1 for r in roles if r.title_raw)

        seniority_counts = Counter(r.seniority_level for r in roles)
        role_counts = Counter(r.functional_role for r in roles)
        decision_makers = sum(1 for r in roles if r.is_decision_maker)

        avg_confidence = sum(r.role_confidence for r in roles) / total if total > 0 else 0

        return {
            'total_contacts': total,
            'with_extracted_title': with_title,
            'title_extraction_rate': round(with_title / total * 100, 2) if total > 0 else 0,
            'decision_makers': decision_makers,
            'decision_maker_rate': round(decision_makers / total * 100, 2) if total > 0 else 0,
            'avg_confidence': round(avg_confidence, 2),
            'by_seniority': dict(seniority_counts),
            'by_role': dict(role_counts),
        }


# Example usage
if __name__ == '__main__':
    import sys
    import json

    if len(sys.argv) < 3:
        print("Usage: python -m backend.src.services.role_classifier <mailbox_id> <contacts_json_file>")
        print("\ncontacts_json_file should contain output from contact_extractor")
        sys.exit(1)

    mailbox_id = sys.argv[1]
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

    # Classify roles
    classifier = RoleClassifier(mailbox_id=mailbox_id)
    roles = classifier.classify_roles(contacts, extract_from_signatures=True)

    # Print summary
    summary = classifier.get_role_summary(roles)
    print("\n=== Role Classification Summary ===")
    for key, value in summary.items():
        print(f"{key}: {value}")

    # Print decision makers
    decision_makers = [r for r in roles if r.is_decision_maker]
    print(f"\n=== Decision Makers ({len(decision_makers)}) ===")
    for role in decision_makers[:20]:
        print(f"- {role.email}: {role.title_raw or 'No title'} "
              f"({role.seniority_level}, {role.functional_role})")

    # Update database
    print("\nUpdating customer_contacts table...")
    update_result = classifier.update_contact_roles(roles)

    print("\n=== Update Results ===")
    for key, value in update_result.items():
        if key != 'errors':
            print(f"{key}: {value}")

    if update_result['errors']:
        print(f"\nErrors: {len(update_result['errors'])}")
        for error in update_result['errors'][:5]:
            print(f"  - {error['email']}: {error['error']}")
