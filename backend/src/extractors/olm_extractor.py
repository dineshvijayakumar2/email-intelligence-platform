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
from datetime import datetime, timezone
from typing import Dict, Iterator, Optional, List
from pathlib import Path

from .base_extractor import BaseExtractor

logger = logging.getLogger(__name__)


class OLMExtractor(BaseExtractor):
    """Extract emails from OLM (Mac Outlook) XML-based archives"""

    def __init__(self, connection_config: Dict):
        """Initialize OLM extractor

        Args:
            connection_config: Dict with 'file_path' or Google Drive config
        """
        super().__init__(connection_config=connection_config)
        self.source_type = "olm"
        self.file_path = None  # Will be set in connect()
        self.zip_file = None
        self.message_files = []  # List of message XML file paths
        self.folder_structure = {}  # Maps folder paths to message counts

    def connect(self, access_token: Optional[str] = None, **kwargs) -> bool:
        """
        Open OLM ZIP archive for streaming access

        Args:
            access_token: Google Drive OAuth2 access token (if needed for Google Drive files)

        Returns:
            True if connection successful

        Raises:
            ValueError: If file_path not in connection_config
            FileNotFoundError: If file doesn't exist
            zipfile.BadZipFile: If file is not a valid ZIP
            ConnectionError: If failed to open OLM file
        """
        # Get the effective file path (local or streamed from Google Drive)
        self.file_path = self.get_effective_file_path(access_token)

        # Check if we're streaming from Google Drive
        if self.file_path == 'GOOGLE_DRIVE_STREAM':
            # For large ZIP files, download to temp file instead of streaming
            # This is more reliable for zipfile module compatibility
            try:
                logger.info("💾 Using temporary download approach for Google Drive OLM file (large ZIP compatibility)")
                
                # Get Google Drive file details
                google_file_id = self.config.get('google_drive_file_id')
                google_file_name = self.config.get('google_drive_file_name', 'Unknown OLM')
                user_id = self.config.get('user_id')
                
                if not google_file_id:
                    raise ValueError("Google Drive file ID not provided")
                
                # Import here to avoid circular imports
                from ..storage.google_drive_client import create_google_drive_client
                from ..storage.remote_zip_google_drive import create_remote_zip
                
                # Create client and authenticate
                client = create_google_drive_client()
                authenticated = False
                
                # Try user token authentication first
                if user_id:
                    logger.info("Authenticating with user's stored Google Drive tokens...")
                    try:
                        from ..database.supabase_client import SupabaseClient
                        supabase = SupabaseClient.get_client(use_service_key=True)
                        
                        result = supabase.table('user_integrations').select('access_token,refresh_token').eq('user_id', user_id).eq('provider', 'google_drive').execute()
                        
                        if result.data:
                            user_tokens = result.data[0]
                            if client.authenticate_with_user_tokens(
                                user_tokens['access_token'],
                                user_tokens['refresh_token']
                            ):
                                authenticated = True
                                logger.info("✅ Authenticated with user's Google Drive tokens")
                                
                                # Update tokens if refreshed
                                current_tokens = client.get_current_tokens()
                                if current_tokens and current_tokens['access_token'] != user_tokens['access_token']:
                                    supabase.table('user_integrations').update({
                                        'access_token': current_tokens['access_token']
                                    }).eq('user_id', user_id).eq('provider', 'google_drive').execute()
                                    logger.info("Updated refreshed access token in database")
                    except Exception as e:
                        logger.warning(f"Failed to authenticate with user tokens: {e}")
                
                # Fallback to service account if user auth failed
                if not authenticated:
                    logger.info("Trying service account authentication...")
                    if client.authenticate_with_service_account():
                        authenticated = True
                        logger.info("✅ Authenticated with service account")
                    else:
                        raise ConnectionError("Failed to authenticate with Google Drive")
                
                # Get file metadata
                file_info = client.get_file_info(google_file_id)
                if not file_info:
                    raise ConnectionError(f"Could not get info for Google Drive file {google_file_id}")
                
                logger.info(f"📦 Opening OLM via RemoteZip: {file_info['name']} "
                           f"(Size: {file_info['size']:,} bytes)")
                
                # Use industry-standard RemoteZip approach
                self.zip_file = create_remote_zip(client, google_file_id, file_info)
                logger.info(f"✅ Connected to OLM via RemoteZip: {file_info['name']}")
                
                # Build index of message files and folder structure
                self._index_messages()
                
                logger.info(f"Found {len(self.message_files)} messages in {len(self.folder_structure)} folders")
                return True
                
            except Exception as e:
                logger.error(f"Failed to connect to Google Drive OLM: {e}")
                if self.zip_file:
                    self.zip_file.close()
                raise ConnectionError(f"Google Drive OLM connection failed: {e}") from e
        
        else:
            # Local file path - use existing logic
            if not Path(self.file_path).exists():
                raise FileNotFoundError(f"OLM file not found: {self.file_path}")

            try:
                # Open ZIP file for streaming (no extraction)
                self.zip_file = zipfile.ZipFile(self.file_path, 'r')
                logger.info(f"Connected to OLM ZIP archive: {self.file_path}")

                # Build index of message files and folder structure
                self._index_messages()

                logger.info(f"Found {len(self.message_files)} messages in {len(self.folder_structure)} folders")
                return True

            except zipfile.BadZipFile as e:
                logger.error(f"Invalid OLM file (not a ZIP archive): {e}")
                raise ConnectionError(f"OLM connection failed: not a valid ZIP file") from e
            except Exception as e:
                logger.error(f"Failed to connect to OLM file: {e}")
                if self.zip_file:
                    self.zip_file.close()
                raise ConnectionError(f"OLM connection failed: {e}") from e

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

    def extract_emails(self, max_emails: Optional[int] = None) -> Iterator[Dict]:
        """
        Extract emails from OLM archive by streaming XML files

        NO date filtering - that belongs in the pipeline, not the extractor!

        Args:
            max_emails: Maximum emails to extract (None = unlimited)

        Yields:
            Standardized email dictionaries with folder_path from OLM structure
        """
        if not self.zip_file:
            raise RuntimeError("OLM file not opened. Call connect() first.")

        self._mark_start()

        try:
            extracted = 0

            for message_path in self.message_files:
                try:
                    # Parse message XML directly from ZIP (no disk extraction)
                    email_dict = self._parse_message_xml(message_path)

                    if email_dict:
                        yield email_dict
                        extracted += 1
                        self.stats['emails_extracted'] = extracted

                        if max_emails and extracted >= max_emails:
                            logger.info(f"Reached max_emails limit: {max_emails}")
                            break

                except Exception as e:
                    logger.warning(f"Failed to parse {message_path}: {e}")
                    self.stats['errors'].append(f"Parse error in {message_path}: {e}")
                    continue

            logger.info(f"OLM extraction completed. Extracted {extracted} emails")

        finally:
            self._mark_end()

    def _parse_message_xml(self, message_path: str) -> Optional[Dict]:
        """
        Parse a single OLM message XML file to standardized email dict

        Args:
            message_path: Path to message XML file within ZIP

        Returns:
            Standardized email dictionary or None if parsing fails
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

            # Threading information
            in_reply_to = self._get_text(email_elem, 'OPFMessageCopyInReplyTo', '')
            references = self._get_text(email_elem, 'OPFMessageCopyReferences', '')  # If available

            # Determine if outbound
            is_outbound_str = self._get_text(email_elem, 'OPFMessageIsOutgoing', '0')
            is_outbound = is_outbound_str == '1e0' or is_outbound_str == '1'

            # Also check folder name
            if not is_outbound:
                is_outbound = self._is_sent_folder(folder_path)

            # Check if reply
            is_reply = bool(in_reply_to) or (subject and subject.lower().startswith(('re:', 'aw:', 'fwd:', 'fw:')))

            # Extract attachments
            attachments = self._extract_attachments(email_elem)

            # Get message size (rough estimate from body lengths)
            message_size = len(body_text) + len(body_html)

            # Build raw email dict with OLM-specific data
            raw_email = {
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
                'message_size': message_size,
                'raw_headers': {
                    'olm_path': message_path,
                    'thread_topic': self._get_text(email_elem, 'OPFMessageCopyThreadTopic', ''),
                    'thread_index': self._get_text(email_elem, 'OPFMessageCopyThreadIndex', ''),
                    'In-Reply-To': in_reply_to,
                    'References': references,
                    'priority': self._get_text(email_elem, 'OPFMessageGetPriority', '3'),
                },
                # Threading fields
                'in_reply_to': in_reply_to,
                'references': references,
                # Attachments
                'attachments': attachments
            }

            # Use BaseExtractor's standardization
            source_path = message_path  # Full ZIP path as source
            return self._standardize_email(raw_email, source_path)

        except Exception as e:
            logger.warning(f"Failed to parse OLM message {message_path}: {e}")
            self.stats['errors'].append(f"Parse error: {e}")
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

    def _extract_attachments(self, email_elem: ET.Element) -> List[Dict]:
        """
        Extract attachment metadata from OLM XML

        OLM attachments are typically referenced in OPFMessageCopyAttachmentList

        Args:
            email_elem: XML email element

        Returns:
            List of attachment dictionaries
        """
        attachments = []

        try:
            # Look for attachment list element
            attach_list = email_elem.find('OPFMessageCopyAttachmentList')
            if attach_list is None:
                return attachments

            # Find all attachment entries
            for i, attach_elem in enumerate(attach_list.findall('.//messageAttachment')):
                try:
                    filename = attach_elem.get('OPFAttachmentName', f'attachment_{i}')
                    # Size might not always be available in OLM XML
                    size_str = attach_elem.get('OPFAttachmentContentLength', '0')
                    size = int(size_str) if size_str.isdigit() else 0

                    attachments.append({
                        'id': f'olm-att-{i}',
                        'filename': filename,
                        'size': size,
                        'mime_type': attach_elem.get('OPFAttachmentContentType', ''),
                        'storage_pointer': f'attachment_{i}'
                    })

                except Exception as e:
                    logger.warning(f"Failed to extract attachment {i}: {e}")

        except Exception as e:
            logger.debug(f"No attachments found or error extracting: {e}")

        return attachments

    def disconnect(self):
        """Close ZIP file and cleanup temporary files"""
        if self.zip_file:
            try:
                self.zip_file.close()
                logger.info("OLM ZIP file closed")
            except Exception as e:
                logger.warning(f"Error closing ZIP file: {e}")
            finally:
                self.zip_file = None
        
        # Cleanup any temporary Google Drive files
        self.cleanup_temp_files()

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

    extractor = OLMExtractor({'file_path': olm_path})

    try:
        extractor.connect()

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
