"""
Unified File Extractor - Auto-detects and extracts from MBOX/PST/OLM files

This is the main entry point for file-based email extraction.
Automatically detects file format and delegates to appropriate extractor.
Supports cloud storage (S3, Google Drive) and local files.
"""

import logging
import os
import sys
from pathlib import Path
from typing import Dict, Iterator, Optional, List

from .mbox_extractor import MBOXExtractor
from .pst_extractor import PSTExtractor
from .olm_extractor import OLMExtractor
from .base_extractor import BaseExtractor

# Add src to path for storage imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from src.storage import StorageManager

logger = logging.getLogger(__name__)


class FileExtractor(BaseExtractor):
    """
    Unified file extractor with auto-detection

    Supports:
    - MBOX files (universal format)
    - PST files (Windows Outlook archives)
    - OLM files (Mac Outlook archives)

    Storage backends:
    - Local filesystem
    - AWS S3 (s3://bucket/path)
    - Google Drive (gdrive://file_id or https://drive.google.com/...)
    """

    def __init__(self):
        """Initialize file extractor"""
        super().__init__(connection_config={})
        self.file_path = None
        self.file_uri = None  # Original URI (may be cloud storage)
        self.file_type = None
        self.extractor = None
        self.storage_manager = StorageManager()

    def connect(self, file_path: str, **kwargs):
        """
        Connect to email file with auto-detection
        Supports local files, S3, and Google Drive

        Args:
            file_path: Path or URI to email archive file
                      Examples:
                      - /path/to/file.mbox (local)
                      - s3://bucket/path/file.mbox (S3)
                      - gdrive://file_id (Google Drive)
                      - https://drive.google.com/file/d/FILE_ID/view (Google Drive)
            **kwargs: Additional arguments passed to specific extractor

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file type is not supported
            PermissionError: If file is locked or no read permission
            RuntimeError: If initialization fails
        """
        self.file_uri = file_path

        # Use storage manager to get local file path
        # This handles cloud storage downloads automatically
        try:
            logger.info(f"Resolving file URI: {file_path}")
            self.file_path = self.storage_manager.get_file(file_path)
            logger.info(f"Local file path: {self.file_path}")
        except FileNotFoundError as e:
            raise FileNotFoundError(
                f"File not found: {file_path}\n"
                f"Please verify:\n"
                f"  - Path/URI is correct\n"
                f"  - File location is accessible (cloud storage credentials configured)\n"
                f"  - You have read permissions\n"
                f"Error: {str(e)}"
            ) from e
        except Exception as e:
            raise RuntimeError(
                f"Failed to access file: {file_path}\n"
                f"Error: {str(e)}"
            ) from e

        # Detect file type
        try:
            self.file_type = self._detect_file_type(file_path)
            logger.info(f"Detected file type: {self.file_type}")
        except Exception as e:
            raise RuntimeError(f"Failed to detect file type for {file_path}: {e}") from e

        # Prepare connection config
        connection_config = {'file_path': file_path}
        connection_config.update(kwargs)

        # Create appropriate extractor with connection config
        try:
            if self.file_type == 'mbox':
                self.extractor = MBOXExtractor(connection_config)
            elif self.file_type == 'pst':
                self.extractor = PSTExtractor(connection_config)
            elif self.file_type == 'olm':
                self.extractor = OLMExtractor(connection_config)
            else:
                raise ValueError(f"Unsupported file type: {self.file_type}")

            # Connect using specific extractor (file_path already in connection_config)
            logger.info(f"Initializing {self.file_type.upper()} extractor...")
            self.extractor.connect(**kwargs)
            logger.info(f"{self.file_type.upper()} extractor initialized successfully")

        except PermissionError as e:
            raise PermissionError(
                f"Permission denied: {file_path}\n"
                f"Possible causes:\n"
                f"  - File is locked by another process\n"
                f"  - Insufficient read permissions\n"
                f"  - File is open in another application"
            ) from e
        except Exception as e:
            # Generic error with context
            logger.error(f"Failed to initialize {self.file_type} extractor: {e}", exc_info=True)
            raise RuntimeError(
                f"Failed to initialize {self.file_type} extractor\n"
                f"File: {file_path}\n"
                f"Error: {str(e)}"
            ) from e

    def _detect_file_type(self, file_path: str) -> str:
        """
        Auto-detect email file format

        Detection methods:
        1. File extension
        2. Magic bytes/file signatures
        3. Content analysis

        Args:
            file_path: Path to file

        Returns:
            File type: 'mbox', 'pst', or 'olm'
        """
        file_path = Path(file_path)
        extension = file_path.suffix.lower()

        # Method 1: Check extension
        if extension == '.mbox':
            return 'mbox'
        elif extension == '.pst':
            return 'pst'
        elif extension == '.olm':
            return 'olm'

        # Method 2: Check magic bytes
        try:
            with open(file_path, 'rb') as f:
                header = f.read(16)

                # PST magic: starts with 0x2142444E ("!BDN")
                if header[:4] == b'!BDN':
                    logger.info("Detected PST via magic bytes")
                    return 'pst'

                # OLM magic: ZIP signature (0x504B0304)
                if header[:4] == b'PK\x03\x04':
                    # Could be OLM (which is a ZIP) - check contents
                    import zipfile
                    if zipfile.is_zipfile(file_path):
                        with zipfile.ZipFile(file_path, 'r') as zf:
                            # OLM contains com.microsoft.outlook.olm.* directories
                            namelist = zf.namelist()
                            if any('com.microsoft.outlook.olm' in name for name in namelist):
                                logger.info("Detected OLM via ZIP contents")
                                return 'olm'

                # MBOX magic: starts with "From " (Unix mailbox format)
                if header[:5] == b'From ':
                    logger.info("Detected MBOX via magic bytes")
                    return 'mbox'

        except Exception as e:
            logger.warning(f"Failed to detect file type via magic bytes: {e}")

        # Method 3: Assume MBOX if no extension or unknown
        # MBOX is the most common universal format
        logger.warning(f"Could not definitively detect file type, assuming MBOX")
        return 'mbox'

    def extract_emails(self, max_emails: int = 0) -> Iterator[Dict]:
        """
        Extract emails from file

        Args:
            max_emails: Maximum emails to extract (0 = unlimited)

        Yields:
            Email dictionaries with folder_path (if supported)
        """
        if not self.extractor:
            raise RuntimeError("Not connected. Call connect() first.")

        logger.info(f"Extracting emails from {self.file_type} file...")

        yield from self.extractor.extract_emails(max_emails)

    def disconnect(self):
        """Disconnect from email file and cleanup cloud storage temp files"""
        if self.extractor:
            self.extractor.disconnect()
            self.extractor = None

        # Cleanup any temporary files from cloud storage
        if self.storage_manager:
            self.storage_manager.cleanup()

    def get_stats(self) -> Dict:
        """Get extraction statistics"""
        if self.extractor:
            return self.extractor.get_stats()
        return self.stats

    def get_capabilities(self) -> Dict:
        """
        Get capabilities of current file type

        Returns:
            Dict with capability flags
        """
        capabilities = {
            'mbox': {
                'folder_support': False,
                'folder_from_headers': True,  # Gmail labels
                'threading_support': True,
                'attachments_support': True,
                'fast_seeking': False
            },
            'pst': {
                'folder_support': True,  # Native folder structure
                'folder_from_headers': False,
                'threading_support': True,
                'attachments_support': True,
                'fast_seeking': True  # Binary database
            },
            'olm': {
                'folder_support': True,  # From XML mapping
                'folder_from_headers': False,
                'threading_support': True,
                'attachments_support': True,
                'fast_seeking': False
            }
        }

        return capabilities.get(self.file_type, {})

    def get_folders(self) -> List[Dict]:
        """Get list of available folders from the extractor"""
        if self.extractor and hasattr(self.extractor, 'get_folders'):
            return self.extractor.get_folders()
        return []


def detect_and_extract(file_path: str, max_emails: int = 0) -> Iterator[Dict]:
    """
    Convenience function to detect and extract emails in one call

    Args:
        file_path: Path to email file
        max_emails: Maximum emails to extract

    Yields:
        Email dictionaries

    Example:
        >>> for email in detect_and_extract('/path/to/archive.pst', max_emails=100):
        ...     print(email['subject'])
    """
    extractor = FileExtractor()

    try:
        extractor.connect(file_path)
        yield from extractor.extract_emails(max_emails)
    finally:
        extractor.disconnect()
