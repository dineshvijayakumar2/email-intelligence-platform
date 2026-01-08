"""
Google Drive Streaming File Wrapper

This module provides a file-like object that streams data from Google Drive
without downloading the entire file first. This is essential for processing
large files (e.g., 65GB+ OLM archives) that would be impractical to download
completely before processing.

The GoogleDriveStreamWrapper class implements Python's file-like interface
with seek, read, and tell methods, allowing it to be used with zipfile.ZipFile
and other libraries that expect file-like objects.
"""

import io
import logging
from typing import Optional, Dict, Any
import time

logger = logging.getLogger(__name__)


class GoogleDriveStreamWrapper:
    """
    A file-like object that streams content from Google Drive on-demand.
    
    This wrapper implements buffered reading with intelligent caching to minimize
    API calls while supporting random access patterns required by ZIP files.
    """
    
    def __init__(self, drive_service, file_id: str, file_metadata: Optional[Dict[str, Any]] = None):
        """
        Initialize the streaming wrapper
        
        Args:
            drive_service: Authenticated Google Drive service instance
            file_id: Google Drive file ID
            file_metadata: Optional pre-fetched file metadata
        """
        self.drive_service = drive_service
        self.file_id = file_id
        
        # Get file metadata if not provided
        if file_metadata:
            self.file_size = int(file_metadata.get('size', 0))
            self.file_name = file_metadata.get('name', 'unknown')
        else:
            metadata = drive_service.files().get(
                fileId=file_id, 
                fields="name,size"
            ).execute()
            self.file_size = int(metadata.get('size', 0))
            self.file_name = metadata.get('name', 'unknown')
        
        self.position = 0
        
        # Buffer configuration - adaptive based on file size
        if self.file_size < 100 * 1024 * 1024:  # < 100MB
            self.buffer_size = 1 * 1024 * 1024  # 1MB buffer
        elif self.file_size < 1024 * 1024 * 1024:  # < 1GB
            self.buffer_size = 5 * 1024 * 1024  # 5MB buffer
        else:  # >= 1GB
            self.buffer_size = 10 * 1024 * 1024  # 10MB buffer
        
        self.buffer = bytearray()
        self.buffer_start = 0
        self.buffer_end = 0
        
        # Statistics
        self.total_bytes_read = 0
        self.api_calls = 0
        self.start_time = time.time()
        
        # Cache for frequently accessed regions (like ZIP central directory)
        self.cache_regions = {}
        self.max_cache_regions = 5
        
        logger.info(f"🌊 Initialized streaming wrapper for '{self.file_name}' "
                   f"(ID: {file_id}, Size: {self._format_size(self.file_size)}, "
                   f"Buffer: {self._format_size(self.buffer_size)})")
    
    def seek(self, offset: int, whence: int = 0) -> int:
        """
        Seek to a specific position in the file
        
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
        
        # Clamp position to valid range
        self.position = max(0, min(self.position, self.file_size))
        return self.position
    
    def tell(self) -> int:
        """Return current position in the file"""
        return self.position
    
    def read(self, size: int = -1) -> bytes:
        """
        Read bytes from the current position
        
        Args:
            size: Number of bytes to read (-1 for all remaining)
        
        Returns:
            Bytes read from the file
        """
        if size == 0:
            return b''
        
        if size == -1 or size > self.file_size - self.position:
            size = self.file_size - self.position
        
        if size <= 0:
            return b''
        
        # Check cache first
        cached_data = self._check_cache(self.position, size)
        if cached_data is not None:
            self.position += len(cached_data)
            return cached_data
        
        # Check if requested data is in buffer
        if self._is_in_buffer(self.position, size):
            return self._read_from_buffer(size)
        
        # Need to fetch from Google Drive
        return self._fetch_and_read(size)
    
    def _is_in_buffer(self, position: int, size: int) -> bool:
        """Check if the requested range is fully within the current buffer"""
        return (position >= self.buffer_start and 
                position + size <= self.buffer_end and
                len(self.buffer) > 0)
    
    def _read_from_buffer(self, size: int) -> bytes:
        """Read data from the existing buffer"""
        buffer_offset = self.position - self.buffer_start
        data = bytes(self.buffer[buffer_offset:buffer_offset + size])
        self.position += len(data)
        return data
    
    def _check_cache(self, position: int, size: int) -> Optional[bytes]:
        """Check if requested data is in cache"""
        for (start, end), data in self.cache_regions.items():
            if position >= start and position + size <= end:
                offset = position - start
                return data[offset:offset + size]
        return None
    
    def _fetch_and_read(self, size: int) -> bytes:
        """Fetch data from Google Drive and update buffer"""
        # Calculate range to fetch
        fetch_start = self.position
        
        # For small reads near the end of large files (like ZIP central directory),
        # fetch a smaller chunk
        if self.position > self.file_size * 0.9:  # Last 10% of file
            fetch_size = min(size * 2, 1024 * 1024)  # Max 1MB for end reads
        else:
            fetch_size = max(size, self.buffer_size)
        
        fetch_end = min(fetch_start + fetch_size, self.file_size)
        actual_fetch_size = fetch_end - fetch_start
        
        if actual_fetch_size <= 0:
            return b''
        
        # Prepare range header for partial download
        range_header = f"bytes={fetch_start}-{fetch_end - 1}"
        
        try:
            # Log fetch operation
            self._log_progress()
            
            # Fetch data with retry logic
            data = self._fetch_with_retry(range_header, actual_fetch_size)
            
            # Update main buffer
            self.buffer = bytearray(data)
            self.buffer_start = fetch_start
            self.buffer_end = fetch_end
            
            # Cache frequently accessed regions (like ZIP central directory)
            if fetch_end > self.file_size * 0.9:  # Cache end regions
                self._add_to_cache(fetch_start, fetch_end, data)
            
            # Update statistics
            self.api_calls += 1
            self.total_bytes_read += len(data)
            
            # Read requested data from new buffer
            return self._read_from_buffer(min(size, len(data)))
            
        except Exception as e:
            logger.error(f"❌ Failed to fetch data from Google Drive: {e}")
            raise IOError(f"Failed to read from Google Drive stream: {e}")
    
    def _fetch_with_retry(self, range_header: str, expected_size: int, max_retries: int = 3) -> bytes:
        """Fetch data with retry logic for resilience"""
        for attempt in range(max_retries):
            try:
                # Create request with range header
                request = self.drive_service.files().get_media(fileId=self.file_id)
                request.headers['Range'] = range_header
                
                # Execute request and get response
                response = request.execute()
                
                # Handle response based on type
                if isinstance(response, bytes):
                    return response
                elif hasattr(response, 'read'):
                    return response.read()
                else:
                    # Shouldn't reach here, but handle gracefully
                    logger.warning(f"Unexpected response type: {type(response)}")
                    return b''
                    
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(f"⚠️ Fetch attempt {attempt + 1} failed, retrying in {wait_time}s: {e}")
                    time.sleep(wait_time)
                else:
                    raise
    
    def _add_to_cache(self, start: int, end: int, data: bytes):
        """Add a region to cache, evicting old entries if needed"""
        # Evict oldest cache entry if at limit
        if len(self.cache_regions) >= self.max_cache_regions:
            # Remove first (oldest) entry
            oldest_key = next(iter(self.cache_regions))
            del self.cache_regions[oldest_key]
        
        self.cache_regions[(start, end)] = data
    
    def _log_progress(self):
        """Log streaming progress at reasonable intervals"""
        # Log every 100 API calls or every 30 seconds
        should_log = (self.api_calls % 100 == 0 or 
                     time.time() - self.start_time > 30 * (self.api_calls // 100 + 1))
        
        if should_log and self.file_size > 0:
            progress_pct = (self.total_bytes_read / self.file_size * 100)
            elapsed = time.time() - self.start_time
            rate = self.total_bytes_read / elapsed if elapsed > 0 else 0
            
            logger.info(f"📊 Streaming '{self.file_name}': {progress_pct:.1f}% "
                       f"({self._format_size(self.total_bytes_read)} / {self._format_size(self.file_size)}) "
                       f"Rate: {self._format_size(rate)}/s, "
                       f"API calls: {self.api_calls}")
    
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
    
    def close(self):
        """Clean up resources"""
        self.buffer = bytearray()
        self.cache_regions.clear()
        
        elapsed = time.time() - self.start_time
        rate = self.total_bytes_read / elapsed if elapsed > 0 else 0
        
        logger.info(f"🏁 Closed stream for '{self.file_name}' - "
                   f"Total: {self._format_size(self.total_bytes_read)}, "
                   f"API calls: {self.api_calls}, "
                   f"Time: {elapsed:.1f}s, "
                   f"Avg rate: {self._format_size(rate)}/s")
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()
    
    # Additional methods for compatibility with file-like objects
    def readable(self) -> bool:
        """Check if stream is readable"""
        return True
    
    def writable(self) -> bool:
        """Check if stream is writable (always False for Google Drive)"""
        return False
    
    def seekable(self) -> bool:
        """Check if stream supports seeking"""
        return True
    
    def flush(self):
        """Flush buffer (no-op for read-only stream)"""
        pass