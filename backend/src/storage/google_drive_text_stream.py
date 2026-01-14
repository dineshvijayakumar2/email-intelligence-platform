"""
Google Drive Text File Streaming for MBOX Files

This module provides line-by-line streaming of text files (like MBOX) from Google Drive
without downloading the entire file first. This is essential for processing large MBOX files
(e.g., 10GB+) that would be impractical to download completely before processing.

The GoogleDriveTextStream class implements an iterator interface that yields lines
from the remote file, using HTTP range requests to fetch chunks on-demand.
"""

import logging
from typing import Optional, Dict, Any, Iterator
import time

logger = logging.getLogger(__name__)


class GoogleDriveTextStream:
    """
    A text stream that reads lines from Google Drive on-demand.

    This wrapper implements buffered line-by-line reading with intelligent chunking
    to minimize API calls while supporting sequential line access required by MBOX parsing.
    """

    def __init__(self, drive_service, file_id: str, file_metadata: Optional[Dict[str, Any]] = None,
                 chunk_size: int = 5 * 1024 * 1024):  # 5MB default chunks
        """
        Initialize the text streaming wrapper

        Args:
            drive_service: Authenticated Google Drive service instance
            file_id: Google Drive file ID
            file_metadata: Optional pre-fetched file metadata
            chunk_size: Size of chunks to fetch per API call (default 5MB)
        """
        self.drive_service = drive_service
        self.file_id = file_id
        self.chunk_size = chunk_size

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
        self.buffer = ""
        self.buffer_start_pos = 0

        # Statistics
        self.total_bytes_read = 0
        self.api_calls = 0
        self.lines_read = 0
        self.start_time = time.time()

        logger.info(f"🌊 Initialized text streaming for '{self.file_name}' "
                   f"(ID: {file_id}, Size: {self._format_size(self.file_size)}, "
                   f"Chunk: {self._format_size(self.chunk_size)})")

    def __iter__(self) -> Iterator[str]:
        """
        Iterate over lines in the file

        Yields:
            Lines from the file (including newline characters)
        """
        while self.position < self.file_size or self.buffer:
            # If buffer is empty or has no complete lines, fetch more data
            if '\n' not in self.buffer and self.position < self.file_size:
                self._fetch_next_chunk()

            # If we still don't have a newline and reached EOF, yield remaining buffer
            if '\n' not in self.buffer:
                if self.buffer:
                    self.lines_read += 1
                    self._log_progress()
                    yield self.buffer
                    self.buffer = ""
                break

            # Extract one line from buffer
            newline_idx = self.buffer.index('\n')
            line = self.buffer[:newline_idx + 1]  # Include newline
            self.buffer = self.buffer[newline_idx + 1:]  # Remove line from buffer

            self.lines_read += 1
            self._log_progress()
            yield line

    def readline(self) -> str:
        """
        Read a single line from the file

        Returns:
            A line from the file (including newline) or empty string if EOF
        """
        # If buffer is empty or has no complete lines, fetch more data
        if '\n' not in self.buffer and self.position < self.file_size:
            self._fetch_next_chunk()

        # If we still don't have a newline and reached EOF, return remaining buffer
        if '\n' not in self.buffer:
            line = self.buffer
            self.buffer = ""
            if line:
                self.lines_read += 1
                self._log_progress()
            return line

        # Extract one line from buffer
        newline_idx = self.buffer.index('\n')
        line = self.buffer[:newline_idx + 1]  # Include newline
        self.buffer = self.buffer[newline_idx + 1:]  # Remove line from buffer

        self.lines_read += 1
        self._log_progress()
        return line

    def _fetch_next_chunk(self):
        """Fetch the next chunk of data from Google Drive"""
        if self.position >= self.file_size:
            return

        # Calculate range to fetch
        fetch_start = self.position
        fetch_end = min(fetch_start + self.chunk_size, self.file_size)
        actual_fetch_size = fetch_end - fetch_start

        if actual_fetch_size <= 0:
            return

        # Prepare range header for partial download
        range_header = f"bytes={fetch_start}-{fetch_end - 1}"

        try:
            # Fetch data with retry logic
            data = self._fetch_with_retry(range_header, actual_fetch_size)

            # Decode to text (UTF-8 with error handling)
            text = data.decode('utf-8', errors='replace')

            # Append to buffer
            self.buffer += text
            self.position = fetch_end

            # Update statistics
            self.api_calls += 1
            self.total_bytes_read += len(data)

        except Exception as e:
            logger.error(f"❌ Failed to fetch chunk from Google Drive: {e}")
            raise IOError(f"Failed to read from Google Drive text stream: {e}")

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
                    logger.warning(f"Unexpected response type: {type(response)}")
                    return b''

            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(f"⚠️ Fetch attempt {attempt + 1} failed, retrying in {wait_time}s: {e}")
                    time.sleep(wait_time)
                else:
                    raise

    def _log_progress(self):
        """Log streaming progress at reasonable intervals"""
        # Log every 10,000 lines or every 30 seconds
        should_log = (self.lines_read % 10000 == 0 or
                     (self.lines_read > 0 and time.time() - self.start_time > 30 * (self.lines_read // 10000 + 1)))

        if should_log and self.file_size > 0:
            progress_pct = (self.total_bytes_read / self.file_size * 100)
            elapsed = time.time() - self.start_time
            rate = self.total_bytes_read / elapsed if elapsed > 0 else 0

            logger.info(f"📊 Streaming '{self.file_name}': {progress_pct:.1f}% "
                       f"({self._format_size(self.total_bytes_read)} / {self._format_size(self.file_size)}) "
                       f"Lines: {self.lines_read:,}, "
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
        self.buffer = ""

        elapsed = time.time() - self.start_time
        rate = self.total_bytes_read / elapsed if elapsed > 0 else 0

        logger.info(f"🏁 Closed text stream for '{self.file_name}' - "
                   f"Total: {self._format_size(self.total_bytes_read)}, "
                   f"Lines: {self.lines_read:,}, "
                   f"API calls: {self.api_calls}, "
                   f"Time: {elapsed:.1f}s, "
                   f"Avg rate: {self._format_size(rate)}/s")

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()
