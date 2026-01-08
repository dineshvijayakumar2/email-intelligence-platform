"""
Universal Cloud Storage Streaming Wrapper

This module provides a unified file-like interface for streaming data from various
cloud storage providers (Google Drive, OneDrive, Dropbox, etc.) without downloading
the entire file first. This is essential for processing large files (e.g., 65GB+ archives).

The CloudStreamWrapper class implements Python's file-like interface with seek, read,
and tell methods, making it compatible with zipfile.ZipFile and other libraries.
"""

import io
import logging
import time
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, BinaryIO
import requests

logger = logging.getLogger(__name__)


class CloudStorageAdapter(ABC):
    """Abstract base class for cloud storage adapters"""
    
    @abstractmethod
    def get_file_metadata(self, file_id: str) -> Dict[str, Any]:
        """Get file metadata (size, name, etc.)"""
        pass
    
    @abstractmethod
    def read_range(self, file_id: str, start: int, end: int) -> bytes:
        """Read a specific byte range from the file"""
        pass


class GoogleDriveAdapter(CloudStorageAdapter):
    """Adapter for Google Drive using the Google API"""
    
    def __init__(self, drive_service):
        self.drive_service = drive_service
    
    def get_file_metadata(self, file_id: str) -> Dict[str, Any]:
        """Get file metadata from Google Drive"""
        metadata = self.drive_service.files().get(
            fileId=file_id,
            fields="name,size,mimeType"
        ).execute()
        
        return {
            'name': metadata.get('name', 'unknown'),
            'size': int(metadata.get('size', 0)),
            'mime_type': metadata.get('mimeType', '')
        }
    
    def read_range(self, file_id: str, start: int, end: int) -> bytes:
        """Read a byte range from Google Drive"""
        import io
        
        try:
            # Log the request
            logger.debug(f"Reading range {start}-{end} from Google Drive file {file_id}")
            
            # Use the Google API client's partial download feature
            request = self.drive_service.files().get_media(fileId=file_id)
            
            # Create a BytesIO buffer for the response
            fh = io.BytesIO()
            
            # Set the range header for partial content
            request.headers['Range'] = f'bytes={start}-{end-1}'
            
            # Execute the request and get the response directly
            # Note: We're NOT using MediaIoBaseDownload here as it doesn't handle ranges well
            import httplib2
            http = self.drive_service._http
            
            # Execute the HTTP request directly with the range header
            resp, content = http.request(request.uri, 
                                        method=request.method,
                                        headers=request.headers)
            
            if resp.status in [200, 206]:  # OK or Partial Content (status is int, not string)
                logger.debug(f"Successfully read {len(content)} bytes (status: {resp.status})")
                return content
            else:
                error_msg = f"Failed to read range: HTTP {resp.status}"
                logger.error(error_msg)
                raise Exception(error_msg)
                
        except Exception as e:
            logger.error(f"Failed to read range {start}-{end} from Google Drive: {e}")
            # Try a simpler fallback approach
            try:
                request = self.drive_service.files().get_media(fileId=file_id)
                request.headers = {'Range': f'bytes={start}-{end-1}'}
                response = request.execute()
                if isinstance(response, bytes):
                    return response
                else:
                    return b''
            except Exception as e2:
                logger.error(f"Fallback also failed: {e2}")
                raise


class OneDriveAdapter(CloudStorageAdapter):
    """Adapter for OneDrive using Microsoft Graph API"""
    
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = "https://graph.microsoft.com/v1.0"
    
    def get_file_metadata(self, file_id: str) -> Dict[str, Any]:
        """Get file metadata from OneDrive"""
        headers = {'Authorization': f'Bearer {self.access_token}'}
        response = requests.get(
            f"{self.base_url}/me/drive/items/{file_id}",
            headers=headers
        )
        response.raise_for_status()
        
        data = response.json()
        return {
            'name': data.get('name', 'unknown'),
            'size': data.get('size', 0),
            'mime_type': data.get('file', {}).get('mimeType', '')
        }
    
    def read_range(self, file_id: str, start: int, end: int) -> bytes:
        """Read a byte range from OneDrive"""
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Range': f'bytes={start}-{end-1}'
        }
        
        response = requests.get(
            f"{self.base_url}/me/drive/items/{file_id}/content",
            headers=headers
        )
        response.raise_for_status()
        return response.content


class DropboxAdapter(CloudStorageAdapter):
    """Adapter for Dropbox using Dropbox API"""
    
    def __init__(self, access_token: str):
        self.access_token = access_token
    
    def get_file_metadata(self, file_id: str) -> Dict[str, Any]:
        """Get file metadata from Dropbox"""
        import dropbox
        dbx = dropbox.Dropbox(self.access_token)
        
        metadata = dbx.files_get_metadata(file_id)
        return {
            'name': metadata.name,
            'size': metadata.size if hasattr(metadata, 'size') else 0,
            'mime_type': ''  # Dropbox doesn't provide MIME type in metadata
        }
    
    def read_range(self, file_id: str, start: int, end: int) -> bytes:
        """Read a byte range from Dropbox"""
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Dropbox-API-Arg': f'{{"path": "{file_id}"}}',
            'Range': f'bytes={start}-{end-1}'
        }
        
        response = requests.post(
            'https://content.dropboxapi.com/2/files/download',
            headers=headers
        )
        response.raise_for_status()
        return response.content


class S3Adapter(CloudStorageAdapter):
    """Adapter for AWS S3 or S3-compatible storage"""
    
    def __init__(self, s3_client, bucket_name: str):
        self.s3_client = s3_client
        self.bucket_name = bucket_name
    
    def get_file_metadata(self, file_id: str) -> Dict[str, Any]:
        """Get file metadata from S3"""
        response = self.s3_client.head_object(Bucket=self.bucket_name, Key=file_id)
        
        return {
            'name': file_id.split('/')[-1],  # Extract filename from key
            'size': response['ContentLength'],
            'mime_type': response.get('ContentType', '')
        }
    
    def read_range(self, file_id: str, start: int, end: int) -> bytes:
        """Read a byte range from S3"""
        response = self.s3_client.get_object(
            Bucket=self.bucket_name,
            Key=file_id,
            Range=f'bytes={start}-{end-1}'
        )
        return response['Body'].read()


class CloudStreamWrapper:
    """
    Universal cloud storage streaming wrapper.
    
    This wrapper provides a file-like interface for reading from any cloud storage
    provider without downloading the entire file first.
    """
    
    def __init__(self, adapter: CloudStorageAdapter, file_id: str, 
                 file_metadata: Optional[Dict[str, Any]] = None):
        """
        Initialize the streaming wrapper
        
        Args:
            adapter: Cloud storage adapter instance
            file_id: File identifier (path or ID depending on provider)
            file_metadata: Optional pre-fetched file metadata
        """
        self.adapter = adapter
        self.file_id = file_id
        
        # Get file metadata
        if file_metadata:
            self.file_size = file_metadata.get('size', 0)
            self.file_name = file_metadata.get('name', 'unknown')
        else:
            metadata = adapter.get_file_metadata(file_id)
            self.file_size = metadata.get('size', 0)
            self.file_name = metadata.get('name', 'unknown')
        
        self.position = 0
        
        # Adaptive buffer size based on file size
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
        
        # Cache for frequently accessed regions
        self.cache_regions = {}
        self.max_cache_regions = 5
        
        logger.info(f"🌊 Initialized cloud streaming for '{self.file_name}' "
                   f"(Size: {self._format_size(self.file_size)}, "
                   f"Buffer: {self._format_size(self.buffer_size)}, "
                   f"Provider: {type(adapter).__name__})")
    
    def seek(self, offset: int, whence: int = 0) -> int:
        """Seek to a specific position in the file"""
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
        """Read bytes from the current position"""
        if size == 0:
            return b''
        
        if size == -1 or size > self.file_size - self.position:
            size = self.file_size - self.position
        
        if size <= 0:
            return b''
        
        # Debug logging for ZIP central directory reads
        if self.position > self.file_size - 1024 * 1024:  # Last 1MB
            logger.debug(f"Reading near end of file: position={self.position}, size={size}, file_size={self.file_size}")
        
        # Check cache first
        cached_data = self._check_cache(self.position, size)
        if cached_data is not None:
            self.position += len(cached_data)
            logger.debug(f"Returned {len(cached_data)} bytes from cache")
            return cached_data
        
        # Check if requested data is in buffer
        if self._is_in_buffer(self.position, size):
            return self._read_from_buffer(size)
        
        # Need to fetch from cloud storage
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
        """Fetch data from cloud storage and update buffer"""
        fetch_start = self.position
        
        # Adaptive fetch size
        if self.position > self.file_size * 0.9:  # Last 10% of file
            fetch_size = min(size * 2, 1024 * 1024)  # Max 1MB for end reads
        else:
            fetch_size = max(size, self.buffer_size)
        
        fetch_end = min(fetch_start + fetch_size, self.file_size)
        
        if fetch_end <= fetch_start:
            return b''
        
        try:
            # Log progress
            self._log_progress()
            
            # Fetch data with retry logic
            data = self._fetch_with_retry(fetch_start, fetch_end)
            
            # Update buffer
            self.buffer = bytearray(data)
            self.buffer_start = fetch_start
            self.buffer_end = fetch_end
            
            # Cache end regions for better ZIP performance
            if fetch_end > self.file_size * 0.9:
                self._add_to_cache(fetch_start, fetch_end, data)
            
            # Update statistics
            self.api_calls += 1
            self.total_bytes_read += len(data)
            
            # Read requested data
            return self._read_from_buffer(min(size, len(data)))
            
        except Exception as e:
            logger.error(f"❌ Failed to fetch data from cloud storage: {e}")
            raise IOError(f"Failed to read from cloud stream: {e}")
    
    def _fetch_with_retry(self, start: int, end: int, max_retries: int = 3) -> bytes:
        """Fetch data with retry logic"""
        for attempt in range(max_retries):
            try:
                return self.adapter.read_range(self.file_id, start, end)
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(f"⚠️ Fetch attempt {attempt + 1} failed, retrying in {wait_time}s: {e}")
                    time.sleep(wait_time)
                else:
                    raise
    
    def _add_to_cache(self, start: int, end: int, data: bytes):
        """Add a region to cache"""
        if len(self.cache_regions) >= self.max_cache_regions:
            # Remove oldest entry
            oldest_key = next(iter(self.cache_regions))
            del self.cache_regions[oldest_key]
        
        self.cache_regions[(start, end)] = data
    
    def _log_progress(self):
        """Log streaming progress"""
        if self.api_calls % 100 == 0 and self.file_size > 0:
            progress_pct = (self.total_bytes_read / self.file_size * 100)
            elapsed = time.time() - self.start_time
            rate = self.total_bytes_read / elapsed if elapsed > 0 else 0
            
            logger.info(f"📊 Streaming '{self.file_name}': {progress_pct:.1f}% "
                       f"({self._format_size(self.total_bytes_read)} / {self._format_size(self.file_size)}) "
                       f"Rate: {self._format_size(rate)}/s, API calls: {self.api_calls}")
    
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
    
    # File-like interface methods
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    def readable(self) -> bool:
        return True
    
    def writable(self) -> bool:
        return False
    
    def seekable(self) -> bool:
        return True
    
    def flush(self):
        pass


def create_cloud_stream(provider: str, file_id: str, **kwargs) -> CloudStreamWrapper:
    """
    Factory function to create a cloud stream wrapper
    
    Args:
        provider: Cloud storage provider ('google_drive', 'onedrive', 'dropbox', 's3')
        file_id: File identifier
        **kwargs: Provider-specific arguments
    
    Returns:
        CloudStreamWrapper instance
    """
    if provider == 'google_drive':
        drive_service = kwargs.get('drive_service')
        if not drive_service:
            raise ValueError("drive_service required for Google Drive")
        adapter = GoogleDriveAdapter(drive_service)
    
    elif provider == 'onedrive':
        access_token = kwargs.get('access_token')
        if not access_token:
            raise ValueError("access_token required for OneDrive")
        adapter = OneDriveAdapter(access_token)
    
    elif provider == 'dropbox':
        access_token = kwargs.get('access_token')
        if not access_token:
            raise ValueError("access_token required for Dropbox")
        adapter = DropboxAdapter(access_token)
    
    elif provider == 's3':
        s3_client = kwargs.get('s3_client')
        bucket_name = kwargs.get('bucket_name')
        if not s3_client or not bucket_name:
            raise ValueError("s3_client and bucket_name required for S3")
        adapter = S3Adapter(s3_client, bucket_name)
    
    else:
        raise ValueError(f"Unsupported cloud provider: {provider}")
    
    return CloudStreamWrapper(adapter, file_id, kwargs.get('file_metadata'))