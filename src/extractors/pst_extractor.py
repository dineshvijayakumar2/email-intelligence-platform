"""
PST File Extractor for Windows Outlook Archives - Streaming Implementation

Extracts emails from PST files with full folder hierarchy support.
Requires: pypff library (pip install pypff-python)

STREAMING APPROACH:
- Uses pypff library which streams PST contents internally
- Never loads entire PST database into memory
- Recursively traverses folder tree on-demand
- Uses generator pattern (yield) for memory-efficient processing
- Suitable for multi-GB PST files
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Iterator, Optional, List
from pathlib import Path

from .base_extractor import BaseExtractor

logger = logging.getLogger(__name__)


class PSTExtractor(BaseExtractor):
    """Extract emails from PST (Outlook) files"""

    def __init__(self, connection_config: Dict):
        """Initialize PST extractor

        Args:
            connection_config: Dict with 'file_path' key
        """
        super().__init__(connection_config=connection_config)
        self.source_type = "pst"
        self.pst_file = None
        self.file_path = connection_config.get('file_path')

        # Check if pypff is available
        try:
            import pypff
            self.pypff = pypff
        except ImportError:
            logger.error("pypff library not installed. Install with: pip install pypff-python")
            raise ImportError("pypff library required for PST extraction")

    def connect(self, access_token: Optional[str] = None, **kwargs) -> bool:
        """
        Open PST file

        Args:
            access_token: Google Drive OAuth2 access token (if needed for Google Drive files)

        Returns:
            True if connection successful

        Raises:
            FileNotFoundError: If PST file doesn't exist
            ConnectionError: If failed to open PST file
        """
        # Get the effective file path (local or downloaded from Google Drive)
        self.file_path = self.get_effective_file_path(access_token)

        if not Path(self.file_path).exists():
            raise FileNotFoundError(f"PST file not found: {self.file_path}")

        try:
            self.pst_file = self.pypff.file()
            self.pst_file.open(self.file_path)
            logger.info(f"Connected to PST file: {self.file_path}")

            root = self.pst_file.get_root_folder()
            logger.info(f"PST root folder: {root.name if root else 'Unknown'}")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to PST file: {e}")
            raise ConnectionError(f"PST connection failed: {e}") from e

    def extract_emails(self, max_emails: Optional[int] = None) -> Iterator[Dict]:
        """
        Extract emails from PST file with folder hierarchy

        NO date filtering - that belongs in the pipeline, not the extractor!

        Args:
            max_emails: Maximum emails to extract (None = unlimited)

        Yields:
            Standardized email dictionaries with folder_path from PST structure
        """
        if not self.pst_file:
            raise RuntimeError("PST file not opened. Call connect() first.")

        self._mark_start()

        try:
            root_folder = self.pst_file.get_root_folder()
            if not root_folder:
                logger.error("No root folder found in PST")
                self._mark_end()
                return

            extracted = 0

            # Recursively extract from all folders
            for email in self._extract_from_folder(root_folder, ""):
                yield email
                extracted += 1
                self.stats['emails_extracted'] = extracted

                if max_emails and extracted >= max_emails:
                    logger.info(f"Reached max_emails limit: {max_emails}")
                    break

            logger.info(f"PST extraction completed. Extracted {extracted} emails")

        except Exception as e:
            logger.error(f"PST extraction failed: {e}")
            self.stats['errors'].append(str(e))
            raise
        finally:
            self._mark_end()

    def _extract_from_folder(self, folder, parent_path: str) -> Iterator[Dict]:
        """
        Recursively extract emails from folder and subfolders

        Args:
            folder: pypff folder object
            parent_path: Parent folder path for hierarchy

        Yields:
            Email dictionaries
        """
        try:
            # Build current folder path
            folder_name = folder.name if folder.name else "Unknown"
            current_path = f"{parent_path}/{folder_name}".strip("/") if parent_path else folder_name

            logger.debug(f"Processing folder: {current_path}")

            # Extract messages from this folder
            num_messages = folder.get_number_of_sub_messages()
            for i in range(num_messages):
                try:
                    message = folder.get_sub_message(i)
                    email_dict = self._parse_pst_message(message, current_path)
                    if email_dict:
                        yield email_dict
                except Exception as e:
                    logger.warning(f"Failed to parse message {i} in {current_path}: {e}")

            # Recursively process subfolders
            num_subfolders = folder.get_number_of_sub_folders()
            for i in range(num_subfolders):
                try:
                    subfolder = folder.get_sub_folder(i)
                    yield from self._extract_from_folder(subfolder, current_path)
                except Exception as e:
                    logger.warning(f"Failed to process subfolder {i} in {current_path}: {e}")

        except Exception as e:
            logger.error(f"Error processing folder {parent_path}: {e}")

    def _parse_pst_message(self, message, folder_path: str) -> Optional[Dict]:
        """
        Parse PST message to standardized email dict

        Args:
            message: pypff message object
            folder_path: Folder path from PST structure

        Returns:
            Standardized email dictionary or None if parsing fails
        """
        try:
            # Extract threading information from headers
            headers = self._extract_headers(message)
            in_reply_to = headers.get('In-Reply-To', '')
            references = headers.get('References', '')

            # Parse recipients with CC/BCC separation
            recipients, cc_list, bcc_list = self._parse_recipients_with_type(message.get_recipients())

            # Extract attachments
            attachments = self._extract_attachments(message)

            # Build raw email dict with PST-specific data
            raw_email = {
                'message_id': self._get_message_id(message),
                'subject': message.subject or '',
                'sender_email': self._extract_email_from_string(message.sender_name or ''),
                'sender_name': message.sender_name or '',
                'recipients': recipients,
                'cc_list': cc_list,
                'bcc_list': bcc_list,
                'sent_date': self._convert_filetime(message.delivery_time),
                'received_date': self._convert_filetime(message.client_submit_time),
                'body_text': message.plain_text_body or '',
                'body_html': message.html_body or '',
                'folder_path': folder_path,  # Real folder from PST structure!
                'is_outbound': self._is_sent_folder(folder_path),
                'is_reply': self._is_reply(message),
                'raw_headers': headers,
                'message_size': message.size if hasattr(message, 'size') else 0,
                # Threading fields
                'in_reply_to': in_reply_to,
                'references': references,
                # Attachments
                'attachments': attachments
            }

            # Use BaseExtractor's standardization
            source_path = f"{folder_path}/{self._get_message_id(message)}"
            return self._standardize_email(raw_email, source_path)

        except Exception as e:
            logger.warning(f"Failed to parse PST message: {e}")
            self.stats['errors'].append(f"Parse error: {e}")
            return None

    def _get_message_id(self, message) -> str:
        """Extract or generate message ID"""
        # Try to get from headers
        internet_headers = message.transport_headers
        if internet_headers:
            import re
            match = re.search(r'Message-ID:\s*<(.+?)>', internet_headers, re.IGNORECASE)
            if match:
                return match.group(1)

        # Generate from entry ID
        entry_id = message.identifier
        return f"pst-{entry_id}" if entry_id else f"generated-{id(message)}"

    def _convert_filetime(self, filetime) -> Optional[datetime]:
        """Convert Windows FILETIME to datetime"""
        if not filetime:
            return None

        try:
            # FILETIME is 100-nanosecond intervals since Jan 1, 1601
            # Convert to Unix timestamp
            unix_epoch = 116444736000000000  # Difference between 1601 and 1970
            timestamp = (filetime - unix_epoch) / 10000000.0
            return datetime.fromtimestamp(timestamp)
        except Exception:
            return None

    def _parse_recipients_with_type(self, recipients):
        """
        Parse PST recipients and separate into TO/CC/BCC lists

        Args:
            recipients: pypff recipients object

        Returns:
            Tuple of (to_list, cc_list, bcc_list)
        """
        to_list = []
        cc_list = []
        bcc_list = []

        if not recipients:
            return to_list, cc_list, bcc_list

        try:
            for recipient in recipients:
                email = recipient.email_address or ''
                name = recipient.name or ''

                if not email:
                    continue

                recipient_dict = {
                    'email': email.lower(),
                    'name': name
                }

                # Check recipient type (MAPI property)
                # MAPI_TO = 1, MAPI_CC = 2, MAPI_BCC = 3
                recipient_type = getattr(recipient, 'type', 1)  # Default to TO

                if recipient_type == 2:
                    cc_list.append(recipient_dict)
                elif recipient_type == 3:
                    bcc_list.append(recipient_dict)
                else:
                    to_list.append(recipient_dict)

        except Exception as e:
            logger.warning(f"Failed to parse recipients: {e}")

        return to_list, cc_list, bcc_list

    def _extract_attachments(self, message) -> List[Dict]:
        """
        Extract attachment metadata from PST message

        Args:
            message: pypff message object

        Returns:
            List of attachment dictionaries
        """
        attachments = []

        try:
            num_attachments = message.get_number_of_attachments()

            for i in range(num_attachments):
                try:
                    attachment = message.get_attachment(i)

                    # Get attachment properties
                    filename = attachment.name or f'attachment_{i}'
                    size = attachment.size if hasattr(attachment, 'size') else 0

                    attachments.append({
                        'id': f'pst-att-{i}',
                        'filename': filename,
                        'size': size,
                        'mime_type': '',  # PST doesn't reliably store MIME type
                        'storage_pointer': f'attachment_{i}'  # Index for retrieval
                    })

                except Exception as e:
                    logger.warning(f"Failed to extract attachment {i}: {e}")

        except Exception as e:
            logger.warning(f"Failed to get attachments: {e}")

        return attachments

    def _extract_email_from_string(self, text: str) -> str:
        """Extract email address from string"""
        if not text:
            return ''

        import re
        match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)
        return match.group(0).lower() if match else ''

    def _is_reply(self, message) -> bool:
        """Check if message is a reply"""
        subject = message.subject or ''
        return subject.lower().startswith(('re:', 'aw:', 'fwd:', 'fw:'))

    def _extract_headers(self, message) -> Dict:
        """Extract headers from PST message"""
        headers = {}

        try:
            transport_headers = message.transport_headers
            if transport_headers:
                # Parse header text
                for line in transport_headers.split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        headers[key.strip()] = value.strip()
        except Exception as e:
            logger.warning(f"Failed to extract headers: {e}")

        return headers

    def disconnect(self):
        """Close PST file and cleanup temporary files"""
        if self.pst_file:
            try:
                self.pst_file.close()
                logger.info("PST file closed")
            except Exception as e:
                logger.warning(f"Error closing PST file: {e}")
            finally:
                self.pst_file = None
        
        # Cleanup any temporary Google Drive files
        self.cleanup_temp_files()

    def get_stats(self) -> Dict:
        """Get extraction statistics"""
        return self.stats

    def get_folders(self) -> list:
        """
        Get list of folders from PST file

        Returns:
            List of folder dictionaries with id, name, and path
        """
        if not self.pst_file:
            return []

        folders = []
        root = self.pst_file.get_root_folder()

        def traverse_folders(folder, parent_path=""):
            """Recursively collect all folders"""
            folder_name = folder.name if folder.name else "Unknown"
            current_path = f"{parent_path}/{folder_name}".strip("/") if parent_path else folder_name

            folders.append({
                'id': current_path,
                'name': folder_name,
                'path': current_path
            })

            # Recurse into subfolders
            num_subfolders = folder.get_number_of_sub_folders()
            for i in range(num_subfolders):
                subfolder = folder.get_sub_folder(i)
                traverse_folders(subfolder, current_path)

        traverse_folders(root)
        return folders
