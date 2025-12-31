"""
OLM File Extractor for Mac Outlook Archives

Extracts emails from OLM files with folder hierarchy from XML mapping.
OLM format: ZIP archive containing MBOX files + XML folder structure
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
import shutil

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

    def connect(self, file_path: str, **kwargs):
        """
        Extract OLM file to temp directory

        Args:
            file_path: Path to OLM file
        """
        self.file_path = file_path

        if not Path(file_path).exists():
            raise FileNotFoundError(f"OLM file not found: {file_path}")

        try:
            # Create temp directory for extraction
            self.temp_dir = tempfile.mkdtemp(prefix='olm_extract_')
            logger.info(f"Extracting OLM to: {self.temp_dir}")

            # Extract OLM (it's a ZIP file)
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(self.temp_dir)

            logger.info(f"OLM file extracted successfully")

            # Parse folder structure from XML
            self._parse_folder_structure()

        except Exception as e:
            logger.error(f"Failed to open OLM file: {e}")
            if self.temp_dir:
                shutil.rmtree(self.temp_dir, ignore_errors=True)
            raise

    def _parse_folder_structure(self):
        """
        Parse folder structure from OLM XML files

        OLM contains:
        - com.microsoft.outlook.olm.email/Folders.xml (folder hierarchy)
        - MBOX files in Messages/ subdirectory
        """
        try:
            # Look for Folders.xml
            folders_xml_path = None

            for root, dirs, files in os.walk(self.temp_dir):
                if 'Folders.xml' in files:
                    folders_xml_path = os.path.join(root, 'Folders.xml')
                    break

            if not folders_xml_path:
                logger.warning("No Folders.xml found in OLM - using default folder mapping")
                return

            # Parse XML
            tree = ET.parse(folders_xml_path)
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
        Extract emails from all MBOX files in OLM

        Args:
            max_emails: Maximum emails to extract (0 = unlimited)

        Yields:
            Email dictionaries with folder_path from XML mapping
        """
        if not self.temp_dir:
            raise RuntimeError("OLM file not extracted. Call connect() first.")

        try:
            extracted = 0

            # Find all MBOX files
            mbox_files = []
            for root, dirs, files in os.walk(self.temp_dir):
                for file in files:
                    if file.endswith('.mbox') or file.endswith('.emlx'):
                        mbox_files.append(os.path.join(root, file))

            logger.info(f"Found {len(mbox_files)} MBOX files in OLM")

            # Extract from each MBOX
            for mbox_path in mbox_files:
                folder_name = self._get_folder_for_mbox(mbox_path)

                for email in self._extract_from_mbox(mbox_path, folder_name):
                    yield email
                    extracted += 1

                    if max_emails > 0 and extracted >= max_emails:
                        logger.info(f"Reached max_emails limit: {max_emails}")
                        return

            logger.info(f"OLM extraction completed. Extracted {extracted} emails")

        except Exception as e:
            logger.error(f"OLM extraction failed: {e}")
            raise

    def _get_folder_for_mbox(self, mbox_path: str) -> str:
        """
        Get folder name for MBOX file from folder mapping

        Args:
            mbox_path: Path to MBOX file

        Returns:
            Folder name or default
        """
        mbox_basename = os.path.basename(mbox_path)

        # Check mapping
        if mbox_basename in self.folder_mapping:
            return self.folder_mapping[mbox_basename]

        # Fallback: use MBOX filename as folder
        return os.path.splitext(mbox_basename)[0]

    def _extract_from_mbox(self, mbox_path: str, folder_name: str) -> Iterator[Dict]:
        """
        Extract emails from a single MBOX file

        Args:
            mbox_path: Path to MBOX file
            folder_name: Folder name for these emails

        Yields:
            Email dictionaries
        """
        try:
            import mailbox

            mbox = mailbox.mbox(mbox_path)

            for idx, msg in enumerate(mbox):
                try:
                    email_dict = self._parse_message(msg, idx, folder_name)
                    if email_dict:
                        yield email_dict
                except Exception as e:
                    logger.warning(f"Failed to parse message {idx} in {folder_name}: {e}")

        except Exception as e:
            logger.error(f"Failed to read MBOX {mbox_path}: {e}")

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
        """Clean up temp directory"""
        if self.temp_dir:
            try:
                shutil.rmtree(self.temp_dir, ignore_errors=True)
                logger.info("OLM temp directory cleaned up")
            except Exception as e:
                logger.warning(f"Error cleaning up temp directory: {e}")
            finally:
                self.temp_dir = None

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
