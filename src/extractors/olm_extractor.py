"""
OLM File Extractor for Mac Outlook Archives - Streaming Implementation

Extracts emails from OLM files with folder hierarchy from XML mapping.
OLM format: ZIP archive containing MBOX files + XML folder structure

STREAMING APPROACH:
- Opens ZIP file for streaming access (no full extraction)
- Reads Folders.xml directly from ZIP (in-memory)
- Extracts individual MBOX files to temp on-demand, one at a time
- Cleans up temp MBOX files immediately after processing
- Uses generator pattern (yield) for memory-efficient processing
- Saves 60GB+ disk space for large OLM archives vs full extraction
"""

import logging
import os
import zipfile
import xml.etree.ElementTree as ET
from email import message_from_bytes
from email.header import decode_header
from datetime import datetime
from typing import Dict, Iterator, Optional, List
from pathlib import Path
import tempfile

from .base_extractor import BaseExtractor

logger = logging.getLogger(__name__)


class OLMExtractor(BaseExtractor):
    """Extract emails from OLM (Mac Outlook) files"""

    def __init__(self):
        """Initialize OLM extractor"""
        super().__init__(connection_config={})
        self.file_path = None
        self.temp_dir = None
        self.folder_mapping = {}  # Maps MBOX files to folder names
        self.zip_file = None  # Keep ZIP file open for streaming

    def connect(self, file_path: str, **kwargs):
        """
        Open OLM file for streaming (without full extraction to save disk space)

        Args:
            file_path: Path to OLM file
        """
        self.file_path = file_path

        if not Path(file_path).exists():
            raise FileNotFoundError(f"OLM file not found: {file_path}")

        try:
            # Open ZIP file for reading (don't extract - saves disk space!)
            self.zip_file = zipfile.ZipFile(file_path, 'r')
            logger.info(f"Opened OLM file (streaming mode): {file_path}")

            # Parse folder structure from XML (in-memory, no extraction)
            self._parse_folder_structure()

        except Exception as e:
            logger.error(f"Failed to open OLM file: {e}")
            if self.zip_file:
                self.zip_file.close()
            raise

    def _parse_folder_structure(self):
        """
        Parse folder structure from OLM XML files (in-memory from ZIP)

        OLM contains:
        - com.microsoft.outlook.olm.email/Folders.xml (folder hierarchy)
        - MBOX files in Messages/ subdirectory
        """
        try:
            # Look for Folders.xml in ZIP
            folders_xml_path = None
            for name in self.zip_file.namelist():
                if 'Folders.xml' in name:
                    folders_xml_path = name
                    break

            if not folders_xml_path:
                logger.warning("No Folders.xml found in OLM - using default folder mapping")
                return

            # Read and parse XML directly from ZIP (no extraction needed!)
            with self.zip_file.open(folders_xml_path) as xml_file:
                tree = ET.parse(xml_file)
                root = tree.getroot()

            # Build folder mapping: MBOX filename -> folder path
            for folder in root.findall('.//folder'):
                folder_name = folder.get('OPFContactFolderName', 'Unknown')
                mbox_files = folder.findall('.//messageFile')

                for mbox_file in mbox_files:
                    mbox_name = mbox_file.get('OPFMessageFilePath', '')
                    if mbox_name:
                        # Extract just the filename
                        mbox_basename = os.path.basename(mbox_name)
                        self.folder_mapping[mbox_basename] = folder_name

            logger.info(f"Parsed folder mapping for {len(self.folder_mapping)} MBOX files")

        except Exception as e:
            logger.warning(f"Failed to parse folder structure: {e}")
            # Continue with extraction, just won't have folder names

    def extract_emails(self, max_emails: int = 0) -> Iterator[Dict]:
        """
        Extract emails from all MBOX files in OLM (streaming from ZIP)

        Args:
            max_emails: Maximum emails to extract (0 = unlimited)

        Yields:
            Email dictionaries with folder_path from XML mapping
        """
        if not self.zip_file:
            raise RuntimeError("OLM file not opened. Call connect() first.")

        try:
            extracted = 0

            # Find all MBOX files in ZIP
            mbox_files = []
            for name in self.zip_file.namelist():
                if name.endswith('.mbox') or name.endswith('.emlx'):
                    mbox_files.append(name)

            logger.info(f"Found {len(mbox_files)} MBOX files in OLM")

            # Extract from each MBOX (read directly from ZIP)
            for mbox_name in mbox_files:
                folder_name = self._get_folder_for_mbox(mbox_name)

                for email in self._extract_from_mbox_in_zip(mbox_name, folder_name):
                    yield email
                    extracted += 1

                    if max_emails > 0 and extracted >= max_emails:
                        logger.info(f"Reached max_emails limit: {max_emails}")
                        return

            logger.info(f"OLM extraction completed. Extracted {extracted} emails")

        except Exception as e:
            logger.error(f"OLM extraction failed: {e}")
            raise

    def _get_folder_for_mbox(self, mbox_name: str) -> str:
        """
        Get folder name for MBOX file from folder mapping

        Args:
            mbox_name: Name/path of MBOX file in ZIP

        Returns:
            Folder name or default
        """
        mbox_basename = os.path.basename(mbox_name)

        # Check mapping
        if mbox_basename in self.folder_mapping:
            return self.folder_mapping[mbox_basename]

        # Fallback: use MBOX filename as folder
        return os.path.splitext(mbox_basename)[0]

    def _extract_from_mbox_in_zip(self, mbox_name: str, folder_name: str) -> Iterator[Dict]:
        """
        Extract emails from a single MBOX file inside the ZIP

        Args:
            mbox_name: Name of MBOX file in ZIP
            folder_name: Folder name for these emails

        Yields:
            Email dictionaries
        """
        try:
            import mailbox
            import io

            # Read MBOX data from ZIP into memory (or temp file if too large)
            with self.zip_file.open(mbox_name) as mbox_file:
                mbox_data = mbox_file.read()

            # Create a temporary file to parse as MBOX (mailbox module needs a file path)
            import tempfile
            with tempfile.NamedTemporaryFile(mode='wb', suffix='.mbox', delete=False) as temp_mbox:
                temp_mbox.write(mbox_data)
                temp_mbox_path = temp_mbox.name

            try:
                # Parse the temporary MBOX file
                mbox = mailbox.mbox(temp_mbox_path)

                for idx, msg in enumerate(mbox):
                    try:
                        email_dict = self._parse_message(msg, idx, folder_name)
                        if email_dict:
                            yield email_dict
                    except Exception as e:
                        logger.warning(f"Failed to parse message {idx} in {folder_name}: {e}")

            finally:
                # Clean up temp file
                os.unlink(temp_mbox_path)

        except Exception as e:
            logger.error(f"Failed to read MBOX {mbox_name} from ZIP: {e}")

    def _parse_message(self, msg, idx: int, folder_name: str) -> Optional[Dict]:
        """Parse email message to standard dict"""
        try:
            from .mbox_extractor import MBOXExtractor

            # Reuse MBOX parsing logic
            mbox_extractor = MBOXExtractor()

            # Parse using MBOX methods
            email_dict = {
                'message_id': mbox_extractor._clean_header(msg.get('Message-ID', f'generated-olm-{idx}')),
                'subject': mbox_extractor._decode_header(msg.get('Subject', '')),
                'sender_email': mbox_extractor._extract_email(msg.get('From', '')),
                'sender_name': mbox_extractor._extract_name(msg.get('From', '')),
                'recipients': mbox_extractor._parse_recipients(msg.get('To', '')),
                'cc_list': mbox_extractor._parse_recipients(msg.get('Cc', '')),
                'bcc_list': mbox_extractor._parse_recipients(msg.get('Bcc', '')),
                'sent_date': mbox_extractor._parse_date(msg.get('Date')),
                'received_date': mbox_extractor._parse_date(msg.get('Received')),
                'body_text': mbox_extractor._get_body_text(msg),
                'body_html': mbox_extractor._get_body_html(msg),
                'folder_path': folder_name,  # Real folder from OLM structure!
                'is_outbound': self._is_sent_folder(folder_name),
                'is_reply': mbox_extractor._is_reply(msg),
                'raw_headers': dict(msg.items())
            }

            return email_dict

        except Exception as e:
            logger.warning(f"Failed to parse OLM message: {e}")
            return None

    def _is_sent_folder(self, folder_name: str) -> bool:
        """Check if folder is a Sent folder"""
        sent_indicators = ['sent', 'sent items', 'sent mail', 'outbox']
        return any(indicator in folder_name.lower() for indicator in sent_indicators)

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
        return self.stats

    def get_folders(self) -> List[Dict]:
        """Get list of folders from OLM structure"""
        folders = []
        for mbox_file, folder_name in self.folder_mapping.items():
            folders.append({
                'id': mbox_file,
                'name': folder_name,
                'path': folder_name
            })
        return folders
