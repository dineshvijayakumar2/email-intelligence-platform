"""
RemoteZip for Google Drive

Industry-standard approach for processing large ZIP archives from cloud storage
without downloading them completely. Based on the RemoteZip pattern used by
major cloud providers and data processing platforms.

This implementation uses HTTP range requests to:
1. Locate the ZIP Central Directory at file end
2. Download only the metadata needed for file listing
3. Extract individual files on-demand with targeted range requests

Optimized for 65GB+ OLM files with minimal memory usage.
"""

import io
import logging
import struct
import zipfile
from typing import Optional, Dict, Any, BinaryIO
import time

logger = logging.getLogger(__name__)


class GoogleDriveRemoteZipFile(zipfile.ZipFile):
    """
    RemoteZip implementation for Google Drive files
    
    Subclasses zipfile.ZipFile to provide transparent streaming access to large
    ZIP files stored in Google Drive using HTTP range requests.
    """
    
    def __init__(self, drive_service, file_id: str, file_size: int, file_name: str):
        """
        Initialize remote ZIP file
        
        Args:
            drive_service: Authenticated Google Drive service
            file_id: Google Drive file ID
            file_size: Total file size in bytes
            file_name: File name for logging
        """
        self.drive_service = drive_service
        self.file_id = file_id
        self.file_size = file_size
        self.file_name = file_name
        
        # Create a virtual file-like object
        self._file_like = GoogleDriveVirtualFile(drive_service, file_id, file_size, file_name)
        
        # Initialize the parent zipfile.ZipFile with our virtual file
        super().__init__(self._file_like, 'r')
        
        logger.info(f"📦 Initialized RemoteZip for {file_name} ({self._format_size(file_size)})")
    
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


class GoogleDriveVirtualFile:
    """
    Virtual file-like object that provides random access to Google Drive files
    using HTTP range requests. Optimized for ZIP file access patterns.
    """
    
    def __init__(self, drive_service, file_id: str, file_size: int, file_name: str):
        """Initialize virtual file"""
        self.drive_service = drive_service
        self.file_id = file_id
        self.file_size = file_size
        self.file_name = file_name
        self.position = 0
        
        # Cache for small, repeated reads (like ZIP metadata)
        self.cache = {}
        self.cache_max_size = 10 * 1024 * 1024  # 10MB cache limit
        self.cache_current_size = 0
        
        # Statistics for optimization
        self.range_requests = 0
        self.bytes_downloaded = 0
        self.start_time = time.time()
        
        logger.debug(f"🔗 Created virtual file for {file_name}")
    
    def read(self, size: int = -1) -> bytes:
        """
        Read data from current position
        
        Args:
            size: Number of bytes to read (-1 for all remaining)
            
        Returns:
            Bytes read from file
        """
        if size == -1:
            size = self.file_size - self.position
        
        if size <= 0:
            return b''
        
        # Check cache first
        cache_key = (self.position, size)
        if cache_key in self.cache:
            data = self.cache[cache_key]
            self.position += len(data)
            return data
        
        # Download the requested range
        data = self._download_range(self.position, self.position + size)
        
        # Cache small reads (likely metadata)
        if size <= 64 * 1024:  # Cache reads <= 64KB
            self._add_to_cache(cache_key, data)
        
        self.position += len(data)
        return data
    
    def seek(self, offset: int, whence: int = 0) -> int:
        """
        Seek to a specific position
        
        Args:
            offset: Byte offset
            whence: Reference point (0=start, 1=current, 2=end)
            
        Returns:
            New absolute position
        """
        if whence == 0:  # Absolute position
            self.position = offset
        elif whence == 1:  # Relative to current
            self.position += offset
        elif whence == 2:  # Relative to end
            self.position = self.file_size + offset
        
        # Clamp to valid range
        self.position = max(0, min(self.position, self.file_size))
        return self.position
    
    def tell(self) -> int:
        """Return current position"""
        return self.position
    
    def readable(self) -> bool:
        """Check if file is readable"""
        return True
    
    def seekable(self) -> bool:
        """Check if file supports seeking"""
        return True
    
    def close(self):
        """Close the virtual file and clean up"""
        self.cache.clear()
        
        elapsed = time.time() - self.start_time
        rate = self.bytes_downloaded / elapsed if elapsed > 0 else 0
        
        logger.info(f"📊 RemoteZip stats for {self.file_name}: "
                   f"{self.range_requests} requests, "
                   f"{self._format_size(self.bytes_downloaded)} downloaded, "
                   f"{rate:.1f} KB/s avg")
    
    def _download_range(self, start: int, end: int) -> bytes:
        """
        Download a specific byte range from Google Drive
        
        Args:
            start: Start byte position
            end: End byte position (exclusive)
            
        Returns:
            Downloaded bytes
        """
        if start >= end or start >= self.file_size:
            return b''
        
        # Adjust end to not exceed file size
        end = min(end, self.file_size)
        size = end - start
        
        try:
            # Create range request
            range_header = f"bytes={start}-{end-1}"
            
            # Use direct HTTP request for better control
            import httplib2
            http = self.drive_service._http
            
            # Build request URL
            url = f"https://www.googleapis.com/drive/v3/files/{self.file_id}?alt=media"
            
            # Execute request with range header
            resp, content = http.request(url, method='GET', headers={'Range': range_header})
            
            # Check response
            if resp.status in [200, 206]:  # OK or Partial Content
                self.range_requests += 1
                self.bytes_downloaded += len(content)
                
                # Log large downloads
                if size > 1024 * 1024:  # Log downloads > 1MB
                    logger.debug(f"📥 Downloaded {self._format_size(len(content))} "
                               f"(range {start}-{end-1}) from {self.file_name}")
                
                return content
            else:
                error_msg = f"Range request failed: HTTP {resp.status}"
                logger.error(error_msg)
                raise Exception(error_msg)
                
        except Exception as e:
            logger.error(f"Failed to download range {start}-{end} from {self.file_name}: {e}")
            raise
    
    def _add_to_cache(self, key: tuple, data: bytes):
        """Add data to cache with size management"""
        data_size = len(data)
        
        # Don't cache if it would exceed our limit
        if self.cache_current_size + data_size > self.cache_max_size:
            # Clear cache to make room
            self.cache.clear()
            self.cache_current_size = 0
        
        self.cache[key] = data
        self.cache_current_size += data_size
    
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


def create_remote_zip(drive_client, file_id: str, file_metadata: Dict[str, Any]) -> GoogleDriveRemoteZipFile:
    """
    Factory function to create a RemoteZip file
    
    Args:
        drive_client: Authenticated Google Drive client
        file_id: Google Drive file ID
        file_metadata: File metadata including size and name
        
    Returns:
        GoogleDriveRemoteZipFile instance
    """
    file_size = file_metadata.get('size', 0)
    file_name = file_metadata.get('name', 'unknown')
    
    return GoogleDriveRemoteZipFile(
        drive_client.service,
        file_id, 
        file_size,
        file_name
    )