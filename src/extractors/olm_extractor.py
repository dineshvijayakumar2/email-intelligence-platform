"""
OLM File Extractor for Mac Outlook Archives - XML-based Format

OLM Structure (Outlook for Mac 2011+):
- ZIP archive containing individual XML files (one per email)
- Path format: Accounts/{email}/com.microsoft.__Messages/{folder}/message_{id}.xml
- Also: Local/com.microsoft.__Messages/{folder}/message_{id}.xml
- Folder hierarchy is implicit in file paths (no Folders.xml)
- Each message is a standalone XML file with OPFMessageCopy* fields

STREAMING APPROACH:
- Opens ZIP file for reading (no extraction to disk)
- Iterates through ZIP entries one by one
- Parses each message XML in-memory
- Extracts folder from file path
- Generator pattern (yield) for memory efficiency
- Handles 65GB+ archives with 850K+ messages

References:
- Format discovered by reverse engineering (no official Microsoft docs)
- Based on OLMReader project: https://github.com/teverett/OLMReader
"""

import logging
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, Iterator, Optional, List
from pathlib import Path

from .base_extractor import BaseExtractor

logger = logging.getLogger(__name__)


class OLMExtractor(BaseExtractor):
    """Extract emails from OLM (Mac Outlook) XML-based archives"""

    def __init__(self):
        """Initialize OLM extractor"""
        super().__init__(connection_config={})
        self.file_path = None
        self.zip_file = None
        self.message_files = []  # List of message XML file paths
        self.folder_structure = {}  # Maps folder paths to message counts

    def connect(self, file_path: str, **kwargs):
        """
        Open OLM ZIP archive for streaming access

        Args:
            file_path: Path to OLM file

        Raises:
            FileNotFoundError: If file doesn't exist
            zipfile.BadZipFile: If file is not a valid ZIP
        """
        self.file_path = file_path

        if not Path(file_path).exists():
            raise FileNotFoundError(f"OLM file not found: {file_path}")

        try:
            # Open ZIP file for streaming (no extraction)
            self.zip_file = zipfile.ZipFile(file_path, 'r')
            logger.info(f"Opened OLM ZIP archive: {file_path}")

            # Build index of message files and folder structure
            self._index_messages()

            logger.info(f"Found {len(self.message_files)} messages in {len(self.folder_structure)} folders")

        except zipfile.BadZipFile as e:
            logger.error(f"Invalid OLM file (not a ZIP archive): {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to open OLM file: {e}")
            if self.zip_file:
                self.zip_file.close()
            raise

    def _index_messages(self):
        """
        Build index of all message files and folder structure from ZIP

        OLM structure:
        - Accounts/{email}/com.microsoft.__Messages/{folder_path}/message_{id}.xml
        - Local/com.microsoft.__Messages/{folder_path}/message_{id}.xml
        """
        self.message_files = []
        self.folder_structure = {}

        for entry in self.zip_file.namelist():
            # Only process message XML files
            if '/message_' in entry and entry.endswith('.xml'):
                self.message_files.append(entry)

                # Extract folder from path
                folder = self._extract_folder_from_path(entry)
                if folder:
                    self.folder_structure[folder] = self.folder_structure.get(folder, 0) + 1

        logger.info(f"Indexed {len(self.message_files)} message files")
        logger.debug(f"Folder structure: {list(self.folder_structure.keys())[:10]}")

    def _extract_folder_from_path(self, file_path: str) -> str:
        """
        Extract folder name from OLM message file path

        Examples:
        - Accounts/user@domain/com.microsoft.__Messages/Inbox/message_00001.xml → Inbox
        - Local/com.microsoft.__Messages/Sent Items/message_00002.xml → Sent Items
        - Accounts/user@domain/com.microsoft.__Messages/Projects/ClientA/message_00003.xml → Projects/ClientA

        Args:
            file_path: Full path to message XML file in ZIP

        Returns:
            Folder path (e.g., "Inbox", "Sent Items", "Projects/ClientA")
        """
        # Split path into parts
        parts = file_path.split('/')

        # Find com.microsoft.__Messages index
        try:
            messages_idx = parts.index('com.microsoft.__Messages')
        except ValueError:
            logger.warning(f"Unexpected path structure: {file_path}")
            return "Unknown"

        # Folder is between com.microsoft.__Messages and message_XXXXX.xml
        folder_parts = parts[messages_idx + 1:-1]  # Exclude last part (filename)

        if not folder_parts:
            return "Root"

        return '/'.join(folder_parts)

    def extract_emails(self, max_emails: int = 0) -> Iterator[Dict]:
        """
        Extract emails from OLM archive by streaming XML files

        Args:
            max_emails: Maximum emails to extract (0 = unlimited)

        Yields:
            Email dictionaries with standardized fields
        """
        if not self.zip_file:
            raise RuntimeError("OLM file not opened. Call connect() first.")

        extracted = 0

        for message_path in self.message_files:
            try:
                # Parse message XML directly from ZIP (no disk extraction)
                email_dict = self._parse_message_xml(message_path)

                if email_dict:
                    yield email_dict
                    extracted += 1

                    if max_emails > 0 and extracted >= max_emails:
                        logger.info(f"Reached max_emails limit: {max_emails}")
                        return

            except Exception as e:
                logger.warning(f"Failed to parse {message_path}: {e}")
                continue

        logger.info(f"OLM extraction completed. Extracted {extracted} emails")

    def _parse_message_xml(self, message_path: str) -> Optional[Dict]:
        """
        Parse a single OLM message XML file to standardized email dict

        Args:
            message_path: Path to message XML file within ZIP

        Returns:
            Email dictionary or None if parsing fails
        """
        try:
            # Read XML from ZIP (in-memory, no disk extraction)
            with self.zip_file.open(message_path) as xml_file:
                tree = ET.parse(xml_file)
                root = tree.getroot()

            # Find the email element
            email_elem = root.find('.//email')
            if email_elem is None:
                logger.warning(f"No email element found in {message_path}")
                return None

            # Extract folder from file path
            folder_path = self._extract_folder_from_path(message_path)

            # Parse all OPFMessageCopy fields
            message_id = self._get_text(email_elem, 'OPFMessageCopyMessageID', f'olm-{hash(message_path)}')
            subject = self._get_text(email_elem, 'OPFMessageCopySubject', '')

            # Parse addresses
            from_addrs = self._parse_address_list(email_elem, 'OPFMessageCopyFromAddresses')
            to_addrs = self._parse_address_list(email_elem, 'OPFMessageCopyToAddresses')
            cc_addrs = self._parse_address_list(email_elem, 'OPFMessageCopyCCAddresses')
            bcc_addrs = self._parse_address_list(email_elem, 'OPFMessageCopyBCCAddresses')

            # Get sender info
            sender_email = from_addrs[0]['email'] if from_addrs else ''
            sender_name = from_addrs[0]['name'] if from_addrs else ''

            # Parse dates
            sent_date = self._parse_datetime(email_elem, 'OPFMessageCopySentTime')
            received_date = self._parse_datetime(email_elem, 'OPFMessageCopyReceivedTime')

            # Get body content
            body_html = self._get_text(email_elem, 'OPFMessageCopyHTMLBody', '')
            body_text = self._get_text(email_elem, 'OPFMessageCopyBody', '')

            # If no plain text, get preview
            if not body_text:
                body_text = self._get_text(email_elem, 'OPFMessageCopyPreview', '')

            # Determine if outbound
            is_outbound_str = self._get_text(email_elem, 'OPFMessageIsOutgoing', '0')
            is_outbound = is_outbound_str == '1e0' or is_outbound_str == '1'

            # Also check folder name
            if not is_outbound:
                is_outbound = self._is_sent_folder(folder_path)

            # Check if reply
            is_reply = self._is_reply(subject, email_elem)

            # Build standardized email dict
            email_dict = {
                'message_id': message_id,
                'subject': subject,
                'sender_email': sender_email,
                'sender_name': sender_name,
                'recipients': to_addrs,
                'cc_list': cc_addrs,
                'bcc_list': bcc_addrs,
                'sent_date': sent_date,
                'received_date': received_date,
                'body_text': body_text,
                'body_html': body_html,
                'folder_path': folder_path,
                'is_outbound': is_outbound,
                'is_reply': is_reply,
                'raw_headers': {
                    'olm_path': message_path,
                    'thread_topic': self._get_text(email_elem, 'OPFMessageCopyThreadTopic', ''),
                    'thread_index': self._get_text(email_elem, 'OPFMessageCopyThreadIndex', ''),
                    'in_reply_to': self._get_text(email_elem, 'OPFMessageCopyInReplyTo', ''),
                    'priority': self._get_text(email_elem, 'OPFMessageGetPriority', '3'),
                }
            }

            return email_dict

        except Exception as e:
            logger.warning(f"Failed to parse OLM message {message_path}: {e}")
            return None

    def _get_text(self, parent: ET.Element, tag: str, default: str = '') -> str:
        """Get text content from XML element"""
        elem = parent.find(tag)
        if elem is not None and elem.text:
            return elem.text.strip()
        return default

    def _parse_address_list(self, parent: ET.Element, tag: str) -> List[Dict]:
        """
        Parse OLM address list XML to list of {email, name} dicts

        OLM format:
        <OPFMessageCopyToAddresses>
            <emailAddress OPFContactEmailAddressAddress="user@domain.com"
                          OPFContactEmailAddressName="John Doe"/>
        </OPFMessageCopyToAddresses>
        """
        addresses = []

        addr_list_elem = parent.find(tag)
        if addr_list_elem is None:
            return addresses

        # Find all emailAddress elements
        for email_elem in addr_list_elem.findall('.//emailAddress'):
            email = email_elem.get('OPFContactEmailAddressAddress', '')
            name = email_elem.get('OPFContactEmailAddressName', '')

            if email:
                addresses.append({
                    'email': email.lower().strip(),
                    'name': name.strip()
                })

        return addresses

    def _parse_datetime(self, parent: ET.Element, tag: str) -> Optional[datetime]:
        """
        Parse OLM datetime string to Python datetime

        OLM format: "2024-01-02T21:38:15" (ISO 8601)
        Edge cases: "2024" (year only), "2024-03-27" (date only)
        """
        date_str = self._get_text(parent, tag)
        if not date_str:
            return None

        try:
            # Handle different date formats
            if 'T' in date_str:
                # Full ISO 8601: "2024-01-02T21:38:15"
                # Remove timezone suffix if present
                base_date = date_str.split('+')[0].split('Z')[0]
                return datetime.fromisoformat(base_date)
            elif len(date_str) == 4 and date_str.isdigit():
                # Year only: "2024" - return Jan 1 of that year
                return datetime(int(date_str), 1, 1)
            elif date_str.count('-') == 2:
                # Date only: "2024-03-27"
                return datetime.strptime(date_str, '%Y-%m-%d')
            elif ' ' in date_str:
                # Full datetime with space: "2024-01-02 21:38:15"
                return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
            else:
                # Try as ISO format
                return datetime.fromisoformat(date_str)
        except Exception as e:
            logger.debug(f"Could not parse datetime '{date_str}': {e}")
            return None

    def _is_sent_folder(self, folder_path: str) -> bool:
        """Check if folder is a Sent folder"""
        sent_indicators = ['sent', 'sent items', 'sent mail', 'outbox']
        return any(indicator in folder_path.lower() for indicator in sent_indicators)

    def _is_reply(self, subject: str, email_elem: ET.Element) -> bool:
        """Check if message is a reply"""
        # Check subject
        if subject and subject.lower().startswith(('re:', 'aw:', 'fwd:', 'fw:')):
            return True

        # Check InReplyTo field
        in_reply_to = self._get_text(email_elem, 'OPFMessageCopyInReplyTo', '')
        return bool(in_reply_to)

    def disconnect(self):
        """Close ZIP file"""
        if self.zip_file:
            try:
                self.zip_file.close()
                logger.info("OLM ZIP file closed")
            except Exception as e:
                logger.warning(f"Error closing ZIP file: {e}")
            finally:
                self.zip_file = None

    def get_stats(self) -> Dict:
        """Get extraction statistics"""
        return {
            **self.stats,
            'total_messages': len(self.message_files),
            'total_folders': len(self.folder_structure)
        }

    def get_folders(self) -> List[Dict]:
        """
        Get list of folders from OLM structure

        Returns:
            List of folder dictionaries with id, name, path, and message count
        """
        folders = []

        for folder_path, message_count in self.folder_structure.items():
            folders.append({
                'id': folder_path,
                'name': folder_path.split('/')[-1],  # Last part of path
                'path': folder_path,
                'message_count': message_count
            })

        return sorted(folders, key=lambda f: f['path'])


def main():
    """Test OLM extraction"""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m src.extractors.olm_extractor <path-to-olm-file> [max_emails]")
        sys.exit(1)

    olm_path = sys.argv[1]
    max_emails = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    logging.basicConfig(level=logging.INFO)

    print(f"\n{'='*60}")
    print(f"OLM Extractor Test")
    print(f"{'='*60}\n")
    print(f"File: {olm_path}")
    print(f"Max emails: {max_emails}\n")

    extractor = OLMExtractor()

    try:
        extractor.connect(olm_path)

        # Show folders
        print("\nFolders found:")
        folders = extractor.get_folders()
        for folder in folders[:20]:
            print(f"  {folder['path']}: {folder['message_count']} messages")
        if len(folders) > 20:
            print(f"  ... and {len(folders) - 20} more folders")

        # Extract sample emails
        print(f"\nExtracting {max_emails} sample emails:\n")

        for i, email in enumerate(extractor.extract_emails(max_emails=max_emails), 1):
            print(f"{i}. [{email['folder_path']}] {email['subject']}")
            print(f"   From: {email['sender_name']} <{email['sender_email']}>")
            print(f"   Date: {email['sent_date']}")
            print(f"   Outbound: {email['is_outbound']}, Reply: {email['is_reply']}")
            print()

        # Show stats
        stats = extractor.get_stats()
        print(f"\nStats: {stats}")

    finally:
        extractor.disconnect()


if __name__ == '__main__':
    main()
