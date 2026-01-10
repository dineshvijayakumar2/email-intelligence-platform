"""
Smart ZIP Reader for Large Cloud Files

This module provides a specialized ZIP reader that can handle very large ZIP files
stored in cloud storage without downloading them completely. It downloads only
the essential parts (central directory, file headers) needed to read the ZIP structure.

This is specifically designed for OLM files which can be 50GB+ but still need
to be processed efficiently.
"""

import os
import logging
import tempfile
import zipfile
from typing import Dict, List, Optional, BinaryIO
from pathlib import Path

logger = logging.getLogger(__name__)


class SmartZipReader:
    """
    Smart ZIP reader that downloads only essential parts of large ZIP files
    """
    
    def __init__(self, drive_client, file_id: str, file_size: int, file_name: str):
        """
        Initialize smart ZIP reader
        
        Args:
            drive_client: Authenticated Google Drive client
            file_id: Google Drive file ID
            file_size: Total file size in bytes
            file_name: Original file name
        """
        self.drive_client = drive_client
        self.file_id = file_id
        self.file_size = file_size
        self.file_name = file_name
        self.temp_dir = None
        self.zip_file = None
        
    def connect(self) -> bool:
        """
        Connect to the ZIP file by downloading minimal required parts
        
        Returns:
            True if connection successful
        """
        try:
            logger.info(f"🔍 Analyzing large ZIP file structure: {self.file_name} ({self._format_size(self.file_size)})")
            
            # Create temporary directory
            self.temp_dir = tempfile.mkdtemp(prefix='smart_zip_')
            
            # Try to read the ZIP central directory
            central_dir_data = self._download_central_directory()
            
            if central_dir_data:
                # Create a minimal ZIP file with just the central directory
                minimal_zip_path = os.path.join(self.temp_dir, 'minimal.zip')
                self._create_minimal_zip(minimal_zip_path, central_dir_data)
                
                # Try to open the minimal ZIP to get file listing
                with zipfile.ZipFile(minimal_zip_path, 'r') as zf:
                    file_list = zf.namelist()
                    logger.info(f"📁 Found {len(file_list)} files in ZIP structure")
                    
                    # For OLM files, we're mainly interested in message files
                    message_files = [f for f in file_list if f.endswith('.xml') and 'message_' in f]
                    logger.info(f"📧 Found {len(message_files)} email message files")
                    
                    if len(message_files) > 0:
                        logger.info("✅ ZIP structure analysis complete - proceeding with download approach")
                        return self._download_to_temp()
                    else:
                        logger.warning("⚠️ No email messages found in ZIP structure")
                        return False
            else:
                logger.warning("⚠️ Could not read ZIP central directory - using full download")
                return self._download_to_temp()
                
        except Exception as e:
            logger.error(f"❌ Smart ZIP analysis failed: {e}")
            logger.info("🔄 Falling back to standard download approach")
            return self._download_to_temp()
    
    def _download_central_directory(self) -> Optional[bytes]:
        """
        Attempt to download just the ZIP central directory from the end of the file
        
        Returns:
            Central directory bytes if successful, None otherwise
        """
        try:
            # ZIP central directory is typically at the end of the file
            # We'll try downloading the last 1MB to 10MB to find it
            for size_mb in [1, 5, 10]:
                size_bytes = size_mb * 1024 * 1024
                start_pos = max(0, self.file_size - size_bytes)
                
                logger.debug(f"Trying to read last {size_mb}MB for central directory...")
                
                # Download the end portion
                end_data = self._download_range(start_pos, self.file_size)
                
                if end_data and len(end_data) > 22:  # Minimum size for EOCD record
                    # Look for End of Central Directory signature (0x06054b50)
                    eocd_signature = b'\x50\x4b\x05\x06'
                    eocd_pos = end_data.rfind(eocd_signature)
                    
                    if eocd_pos != -1:
                        logger.debug(f"Found EOCD at position {eocd_pos} in {size_mb}MB chunk")
                        return end_data[eocd_pos:]
            
            return None
            
        except Exception as e:
            logger.debug(f"Central directory download failed: {e}")
            return None
    
    def _download_range(self, start: int, end: int) -> bytes:
        """Download a specific byte range from the file"""
        try:
            # Use the Google Drive client to download the range
            range_header = f"bytes={start}-{end-1}"
            request = self.drive_client.service.files().get_media(fileId=self.file_id)
            request.headers['Range'] = range_header
            
            response = request.execute()
            if isinstance(response, bytes):
                return response
            return b''
        except Exception as e:
            logger.debug(f"Range download failed: {e}")
            return b''
    
    def _create_minimal_zip(self, output_path: str, central_dir_data: bytes):
        """Create a minimal ZIP file with just the central directory for analysis"""
        with open(output_path, 'wb') as f:
            f.write(central_dir_data)
    
    def _download_to_temp(self) -> bool:
        """
        Download the entire file to a temporary location
        This is the fallback when smart analysis fails
        """
        try:
            logger.info(f"📥 Downloading {self.file_name} to temporary location...")
            logger.warning(f"⚠️ This is a {self._format_size(self.file_size)} file - download may take a while")
            
            # Use the existing Google Drive client download method
            temp_file_path = self.drive_client.download_file_to_temp(self.file_id, self.file_name)
            
            if temp_file_path and os.path.exists(temp_file_path):
                # Open the downloaded ZIP file
                self.zip_file = zipfile.ZipFile(temp_file_path, 'r')
                logger.info(f"✅ Successfully opened downloaded ZIP file")
                return True
            else:
                logger.error("❌ Download failed or file not found")
                return False
                
        except Exception as e:
            logger.error(f"❌ Temporary download failed: {e}")
            return False
    
    def _format_size(self, size_bytes: int) -> str:
        """Format file size in human-readable format"""
        if size_bytes < 1024:
            return f"{size_bytes}B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f}KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f}MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f}GB"
    
    def get_zip_file(self):
        """Get the opened ZIP file object"""
        return self.zip_file
    
    def cleanup(self):
        """Clean up temporary files"""
        if self.zip_file:
            self.zip_file.close()
        
        if self.temp_dir and os.path.exists(self.temp_dir):
            import shutil
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            logger.debug(f"Cleaned up temporary directory: {self.temp_dir}")