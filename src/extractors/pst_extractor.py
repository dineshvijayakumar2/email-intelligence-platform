"""
PST File Extractor for Windows Outlook Archives

Extracts emails from PST files with full folder hierarchy support.
Requires: pypff library (pip install pypff-python)
"""

import logging
from datetime import datetime
from typing import Dict, Iterator, Optional
from pathlib import Path

from .base_extractor import BaseExtractor

logger = logging.getLogger(__name__)


class PSTExtractor(BaseExtractor):
    """Extract emails from PST (Outlook) files"""

    def __init__(self):
        """Initialize PST extractor"""
        super().__init__(connection_config={})
        self.pst_file = None
        self.file_path = None

        # Check if pypff is available
        try:
            import pypff
            self.pypff = pypff
        except ImportError:
            logger.error("pypff library not installed. Install with: pip install pypff-python")
            raise ImportError("pypff library required for PST extraction")

    def connect(self, file_path: str, **kwargs):
        """
        Open PST file

        Args:
            file_path: Path to PST file
        """
        self.file_path = file_path

        if not Path(file_path).exists():
            raise FileNotFoundError(f"PST file not found: {file_path}")

        try:
            self.pst_file = self.pypff.file()
            self.pst_file.open(file_path)
            logger.info(f"Opened PST file: {file_path}")

            root = self.pst_file.get_root_folder()
            logger.info(f"PST root folder: {root.name if root else 'Unknown'}")

        except Exception as e:
            logger.error(f"Failed to open PST file: {e}")
            raise

    def extract_emails(self, max_emails: int = 0) -> Iterator[Dict]:
        """
        Extract emails from PST file with folder hierarchy

        Args:
            max_emails: Maximum emails to extract (0 = unlimited)

        Yields:
            Email dictionaries with folder_path from PST structure
        """
        if not self.pst_file:
            raise RuntimeError("PST file not opened. Call connect() first.")

        try:
            root_folder = self.pst_file.get_root_folder()
            if not root_folder:
                logger.error("No root folder found in PST")
                return

            extracted = 0

            # Recursively extract from all folders
            for email in self._extract_from_folder(root_folder, ""):
                yield email
                extracted += 1

                if max_emails > 0 and extracted >= max_emails:
                    logger.info(f"Reached max_emails limit: {max_emails}")
                    break

            logger.info(f"PST extraction completed. Extracted {extracted} emails")

        except Exception as e:
            logger.error(f"PST extraction failed: {e}")
            raise

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
            Email dictionary or None if parsing fails
        """
        try:
            # Extract basic fields
            email_dict = {
                'message_id': self._get_message_id(message),
                'subject': message.subject or '',
                'sender_email': self._extract_email_from_string(message.sender_name or ''),
                'sender_name': message.sender_name or '',
                'recipients': self._parse_recipients(message.get_recipients()),
                'cc_list': [],  # TODO: Extract CC from recipients
                'bcc_list': [],  # TODO: Extract BCC from recipients
                'sent_date': self._convert_filetime(message.delivery_time),
                'received_date': self._convert_filetime(message.client_submit_time),
                'body_text': message.plain_text_body or '',
                'body_html': message.html_body or '',
                'folder_path': folder_path,  # Real folder from PST structure!
                'is_outbound': self._is_sent_folder(folder_path),
                'is_reply': self._is_reply(message),
                'raw_headers': self._extract_headers(message)
            }

            return email_dict

        except Exception as e:
            logger.warning(f"Failed to parse PST message: {e}")
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

    def _parse_recipients(self, recipients) -> list:
        """Parse PST recipients to list of dicts"""
        recipient_list = []

        if not recipients:
            return recipient_list

        try:
            for recipient in recipients:
                email = recipient.email_address or ''
                name = recipient.name or ''

                if email:
                    recipient_list.append({
                        'email': email.lower(),
                        'name': name
                    })
        except Exception as e:
            logger.warning(f"Failed to parse recipients: {e}")

        return recipient_list

    def _extract_email_from_string(self, text: str) -> str:
        """Extract email address from string"""
        if not text:
            return ''

        import re
        match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)
        return match.group(0).lower() if match else ''

    def _is_sent_folder(self, folder_path: str) -> bool:
        """Check if folder is a Sent folder"""
        sent_indicators = ['sent', 'sent items', 'sent mail', 'outbox']
        return any(indicator in folder_path.lower() for indicator in sent_indicators)

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
        """Close PST file"""
        if self.pst_file:
            try:
                self.pst_file.close()
                logger.info("PST file closed")
            except Exception as e:
                logger.warning(f"Error closing PST file: {e}")
            finally:
                self.pst_file = None

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
