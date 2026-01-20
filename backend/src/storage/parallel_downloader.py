"""
Parallel File Downloader for Google Drive

Downloads large files from Google Drive using multiple threads for faster transfer.
Ideal for files > 1GB where streaming may be slower than parallel download.

Key Features:
- Multi-threaded download using byte-range requests
- Progress tracking per chunk and overall
- Automatic retry logic for failed chunks
- Cleanup on failure or cancellation
- Graceful shutdown support for server restarts
"""

import os
import logging
import tempfile
import requests
import threading
import time
import atexit
import signal
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Callable, Dict, Any, Set
from pathlib import Path
from weakref import WeakSet

logger = logging.getLogger(__name__)

# Global registry of active downloaders for shutdown cleanup
_active_downloaders: Set['ParallelDownloader'] = set()
_registry_lock = threading.Lock()


def cancel_all_downloads():
    """Cancel all active downloads - called during server shutdown"""
    with _registry_lock:
        active_count = len(_active_downloaders)
        if active_count > 0:
            logger.info(f"Cancelling {active_count} active parallel downloads...")
            for downloader in list(_active_downloaders):
                try:
                    downloader.cancel()
                except Exception as e:
                    logger.warning(f"Error cancelling download: {e}")
            logger.info("All parallel downloads cancelled")


def _register_downloader(downloader: 'ParallelDownloader'):
    """Register a downloader for shutdown cleanup"""
    with _registry_lock:
        _active_downloaders.add(downloader)


def _unregister_downloader(downloader: 'ParallelDownloader'):
    """Unregister a downloader after completion"""
    with _registry_lock:
        _active_downloaders.discard(downloader)


class DaemonThreadPoolExecutor(ThreadPoolExecutor):
    """
    A ThreadPoolExecutor that uses daemon threads.
    Daemon threads don't block process exit, allowing graceful shutdown.
    """

    def _adjust_thread_count(self):
        """Override to make threads daemon"""
        super()._adjust_thread_count()
        # Make all threads in this pool daemon threads
        for thread in self._threads:
            if not thread.daemon:
                thread.daemon = True


class ParallelDownloader:
    """Download Google Drive files using parallel byte-range requests"""

    def __init__(
        self,
        access_token: str,
        num_threads: int = 8,
        chunk_size_mb: int = 50,
        max_retries: int = 3,
        progress_callback: Optional[Callable[[int, int, float], None]] = None
    ):
        """
        Initialize the parallel downloader.

        Args:
            access_token: Google OAuth2 access token
            num_threads: Number of parallel download threads (default: 8)
            chunk_size_mb: Size of each chunk in MB (default: 50MB)
            max_retries: Max retries per chunk on failure (default: 3)
            progress_callback: Optional callback(downloaded_bytes, total_bytes, speed_mbps)
        """
        self.access_token = access_token
        self.num_threads = num_threads
        self.chunk_size = chunk_size_mb * 1024 * 1024  # Convert to bytes
        self.max_retries = max_retries
        self.progress_callback = progress_callback

        # Progress tracking
        self.downloaded_bytes = 0
        self.total_bytes = 0
        self.start_time = None
        self.cancelled = False
        self._lock = threading.Lock()
        self._last_logged_percent = 0  # Track last logged percentage
        self._last_log_time = 0  # Track last log time for time-based logging

        # Temp file tracking
        self.temp_dir = None
        self.output_path = None

        # Thread pool for this downloader (will be created in download())
        self._pool: Optional[ThreadPoolExecutor] = None

    def get_file_info(self, file_id: str) -> Dict[str, Any]:
        """Get file metadata from Google Drive"""
        url = f"https://www.googleapis.com/drive/v3/files/{file_id}"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        params = {"fields": "name,size,mimeType"}

        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()

        return response.json()

    def _download_chunk(
        self,
        file_id: str,
        start: int,
        end: int,
        chunk_index: int
    ) -> tuple:
        """
        Download a single chunk of the file.

        Returns:
            (chunk_index, chunk_data, success)
        """
        if self.cancelled:
            return (chunk_index, None, False)

        url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Range": f"bytes={start}-{end}"
        }

        for attempt in range(self.max_retries):
            if self.cancelled:
                return (chunk_index, None, False)

            try:
                response = requests.get(
                    url,
                    headers=headers,
                    timeout=300,  # 5 min timeout per chunk
                    stream=True
                )
                response.raise_for_status()

                chunk_data = response.content
                chunk_size = len(chunk_data)

                # Update progress
                with self._lock:
                    self.downloaded_bytes += chunk_size
                    percent = int(self.downloaded_bytes / self.total_bytes * 100) if self.total_bytes > 0 else 0
                    elapsed = time.time() - self.start_time
                    speed_mbps = (self.downloaded_bytes / (1024 * 1024)) / elapsed if elapsed > 0 else 0

                    # Call progress callback
                    if self.progress_callback and self.total_bytes > 0:
                        self.progress_callback(
                            self.downloaded_bytes,
                            self.total_bytes,
                            speed_mbps
                        )

                    # Log progress every 5% or every 30 seconds
                    current_time = time.time()
                    should_log = (
                        (percent >= self._last_logged_percent + 5) or  # Every 5%
                        (current_time - self._last_log_time >= 30 and percent > self._last_logged_percent)  # Every 30s
                    )

                    if should_log and percent > 0:
                        self._last_logged_percent = percent
                        self._last_log_time = current_time
                        logger.info(
                            f"[DOWNLOAD] {percent}% complete - "
                            f"{self._format_size(self.downloaded_bytes)}/{self._format_size(self.total_bytes)} "
                            f"@ {speed_mbps:.1f} MB/s"
                        )

                return (chunk_index, chunk_data, True)

            except Exception as e:
                logger.warning(
                    f"Chunk {chunk_index} attempt {attempt + 1}/{self.max_retries} failed: {e}"
                )
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff

        return (chunk_index, None, False)

    def download(
        self,
        file_id: str,
        file_name: Optional[str] = None,
        output_dir: Optional[str] = None
    ) -> Optional[str]:
        """
        Download file from Google Drive using parallel threads.

        Args:
            file_id: Google Drive file ID
            file_name: Optional output filename (uses Drive name if not provided)
            output_dir: Optional output directory (uses temp dir if not provided)

        Returns:
            Path to downloaded file, or None if failed
        """
        # Register for shutdown cleanup
        _register_downloader(self)

        try:
            # Get file info
            file_info = self.get_file_info(file_id)
            self.total_bytes = int(file_info.get('size', 0))
            actual_name = file_name or file_info.get('name', f'download_{file_id}')

            logger.info(
                f"Starting parallel download: {actual_name} "
                f"({self._format_size(self.total_bytes)}) "
                f"using {self.num_threads} threads"
            )

            if self.total_bytes == 0:
                logger.error("Cannot download file with size 0")
                return None

            # Setup output path
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
                self.temp_dir = output_dir
            else:
                self.temp_dir = tempfile.mkdtemp(prefix='parallel_download_')

            self.output_path = os.path.join(self.temp_dir, actual_name)

            # Calculate chunks
            chunks = []
            for i in range(0, self.total_bytes, self.chunk_size):
                start = i
                end = min(i + self.chunk_size - 1, self.total_bytes - 1)
                chunks.append((i // self.chunk_size, start, end))

            logger.info(f"Split into {len(chunks)} chunks of ~{self.chunk_size // (1024*1024)}MB each")

            # Reset progress tracking
            self.downloaded_bytes = 0
            self.cancelled = False
            self.start_time = time.time()
            self._last_logged_percent = 0
            self._last_log_time = time.time()

            logger.info(f"[DOWNLOAD] Starting download of {len(chunks)} chunks...")

            # Download chunks in parallel
            chunk_data_map = {}
            failed_chunks = []

            # Create a managed thread pool for this download
            self._pool = DaemonThreadPoolExecutor(max_workers=self.num_threads)
            try:
                futures = {
                    self._pool.submit(
                        self._download_chunk,
                        file_id,
                        start,
                        end,
                        idx
                    ): idx
                    for idx, start, end in chunks
                }

                for future in as_completed(futures):
                    if self.cancelled:
                        logger.info("Download cancelled, stopping...")
                        self._pool.shutdown(wait=False, cancel_futures=True)
                        self._cleanup()
                        return None

                    chunk_index, chunk_data, success = future.result()

                    if success and chunk_data:
                        chunk_data_map[chunk_index] = chunk_data
                    else:
                        failed_chunks.append(chunk_index)
            finally:
                # Ensure pool is shut down
                if self._pool:
                    self._pool.shutdown(wait=False)
                    self._pool = None

            if failed_chunks:
                logger.error(f"Failed to download chunks: {failed_chunks}")
                self._cleanup()
                return None

            # Write chunks to file in order
            logger.info(f"Writing {len(chunk_data_map)} chunks to {self.output_path}...")
            with open(self.output_path, 'wb') as f:
                for i in range(len(chunks)):
                    f.write(chunk_data_map[i])

            # Verify file size
            actual_size = os.path.getsize(self.output_path)
            if actual_size != self.total_bytes:
                logger.error(
                    f"Size mismatch! Expected {self.total_bytes}, got {actual_size}"
                )
                self._cleanup()
                return None

            # Calculate final stats
            elapsed = time.time() - self.start_time
            speed_mbps = (self.total_bytes / (1024 * 1024)) / elapsed if elapsed > 0 else 0

            logger.info(
                f"✅ Download complete: {self._format_size(actual_size)} "
                f"in {elapsed:.1f}s ({speed_mbps:.1f} MB/s)"
            )

            return self.output_path

        except Exception as e:
            logger.error(f"Download failed: {e}")
            self._cleanup()
            return None
        finally:
            # Always unregister from shutdown cleanup
            _unregister_downloader(self)

    def cancel(self):
        """Cancel the ongoing download"""
        self.cancelled = True
        logger.info("Download cancellation requested")

        # Also shut down the thread pool if active
        if self._pool:
            try:
                self._pool.shutdown(wait=False, cancel_futures=True)
            except Exception as e:
                logger.warning(f"Error shutting down thread pool: {e}")
            self._pool = None

    def _cleanup(self):
        """Clean up temporary files on failure"""
        try:
            if self.output_path and os.path.exists(self.output_path):
                os.remove(self.output_path)
                logger.info(f"Cleaned up partial file: {self.output_path}")

            if self.temp_dir and os.path.exists(self.temp_dir):
                if not os.listdir(self.temp_dir):
                    os.rmdir(self.temp_dir)
        except Exception as e:
            logger.warning(f"Cleanup failed: {e}")

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Format file size in human-readable format"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def download_with_progress(
    access_token: str,
    file_id: str,
    file_name: str,
    num_threads: int = 8,
    progress_callback: Optional[Callable[[Dict], None]] = None
) -> Optional[str]:
    """
    Convenience function to download a Google Drive file with progress tracking.

    Args:
        access_token: Google OAuth2 access token
        file_id: Google Drive file ID
        file_name: Output filename
        num_threads: Number of parallel download threads
        progress_callback: Optional callback receiving progress dict:
            {
                'downloaded_bytes': int,
                'total_bytes': int,
                'speed_mbps': float,
                'percent': float,
                'eta_seconds': float
            }

    Returns:
        Path to downloaded file, or None if failed
    """

    def internal_callback(downloaded: int, total: int, speed: float):
        if progress_callback:
            percent = (downloaded / total * 100) if total > 0 else 0
            remaining = total - downloaded
            eta = remaining / (speed * 1024 * 1024) if speed > 0 else 0

            progress_callback({
                'downloaded_bytes': downloaded,
                'total_bytes': total,
                'speed_mbps': speed,
                'percent': percent,
                'eta_seconds': eta
            })

    downloader = ParallelDownloader(
        access_token=access_token,
        num_threads=num_threads,
        progress_callback=internal_callback
    )

    return downloader.download(file_id, file_name)
