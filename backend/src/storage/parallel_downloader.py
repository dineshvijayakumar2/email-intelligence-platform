"""
Parallel File Downloader for Google Drive

Downloads large files from Google Drive using multiple threads for faster transfer.
Ideal for files > 1GB where streaming may be slower than parallel download.

Key Features:
- Multi-threaded download using byte-range requests
- Progress tracking per chunk and overall
- Two-tier retry logic: per-chunk retries + batch retry for failed chunks
- Network resilience: waits for network stability before retrying failed batches
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
from typing import Optional, Callable, Dict, Any, Set, TYPE_CHECKING
from pathlib import Path
from weakref import WeakSet

if TYPE_CHECKING:
    from ..services.job_error_logger import JobErrorLogger

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


class ParallelDownloader:
    """Download Google Drive files using parallel byte-range requests"""

    def __init__(
        self,
        access_token: str,
        num_threads: int = 8,
        chunk_size_mb: int = 50,
        max_retries: int = 3,
        max_batch_retries: int = 5,
        batch_retry_delay: int = 10,
        progress_callback: Optional[Callable[[int, int, float], None]] = None,
        job_id: Optional[str] = None,
        mailbox_id: Optional[str] = None,
        error_logger: Optional['JobErrorLogger'] = None
    ):
        """
        Initialize the parallel downloader.

        Args:
            access_token: Google OAuth2 access token
            num_threads: Number of parallel download threads (default: 8)
            chunk_size_mb: Size of each chunk in MB (default: 50MB)
            max_retries: Max retries per chunk on immediate failure (default: 3)
            max_batch_retries: Max batch retry rounds for failed chunks after network stabilizes (default: 5)
            batch_retry_delay: Seconds to wait before retrying failed chunk batch (default: 10)
            progress_callback: Optional callback(downloaded_bytes, total_bytes, speed_mbps)
            job_id: Optional job ID for error logging
            mailbox_id: Optional mailbox ID for error logging
            error_logger: Optional JobErrorLogger instance for persistent error tracking
        """
        self.access_token = access_token
        self.num_threads = num_threads
        self.chunk_size = chunk_size_mb * 1024 * 1024  # Convert to bytes
        self.max_retries = max_retries
        self.max_batch_retries = max_batch_retries
        self.batch_retry_delay = batch_retry_delay
        self.progress_callback = progress_callback

        # Error logging
        self.job_id = job_id
        self.mailbox_id = mailbox_id
        self.error_logger = error_logger
        self.file_id: Optional[str] = None  # Set during download
        self.file_name: Optional[str] = None  # Set during download

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

    def _check_network_connectivity(self) -> bool:
        """
        Check if network is available by making a lightweight API call.
        Returns True if network is working, False otherwise.
        """
        try:
            # Use Google's API endpoint for a lightweight connectivity check
            response = requests.head(
                "https://www.googleapis.com/drive/v3/about",
                headers={"Authorization": f"Bearer {self.access_token}"},
                timeout=10
            )
            return response.status_code in [200, 401, 403]  # 401/403 means network works, just auth issue
        except (requests.ConnectionError, requests.Timeout):
            return False
        except Exception:
            return False

    def _wait_for_network(self, max_wait_seconds: int = 120) -> bool:
        """
        Wait for network to become available.

        Args:
            max_wait_seconds: Maximum time to wait for network (default: 120s)

        Returns:
            True if network became available, False if timeout or cancelled
        """
        wait_start = time.time()
        check_interval = 5  # Check every 5 seconds

        logger.info(f"Waiting for network connectivity (max {max_wait_seconds}s)...")

        while time.time() - wait_start < max_wait_seconds:
            if self.cancelled:
                logger.info("Network wait cancelled")
                return False

            if self._check_network_connectivity():
                wait_time = time.time() - wait_start
                logger.info(f"Network connectivity restored after {wait_time:.1f}s")
                return True

            time.sleep(check_interval)

        logger.warning(f"Network wait timeout after {max_wait_seconds}s")
        return False

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

                # Log error on final attempt failure
                if attempt == self.max_retries - 1 and self.error_logger and self.job_id:
                    try:
                        self.error_logger.log_download_error(
                            job_id=self.job_id,
                            error_message=f"Chunk {chunk_index} download failed after {self.max_retries} attempts: {str(e)}",
                            mailbox_id=self.mailbox_id,
                            file_id=file_id,
                            file_name=self.file_name,
                            chunk_index=chunk_index,
                            chunk_start=start,
                            chunk_end=end,
                            error_type=self._classify_download_error(e),
                            is_retryable=True,
                            exception=e
                        )
                    except Exception as log_error:
                        logger.debug(f"Failed to log chunk error: {log_error}")

                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff

        return (chunk_index, None, False)

    def _classify_download_error(self, exception: Exception) -> str:
        """Classify a download exception into an error type."""
        error_str = str(exception).lower()
        exception_name = type(exception).__name__.lower()

        if 'timeout' in error_str or 'timeout' in exception_name:
            return 'timeout_error'
        if 'connection' in error_str or 'connection' in exception_name:
            return 'connection_error'
        if 'network' in error_str or 'unreachable' in error_str:
            return 'network_error'
        if 'auth' in error_str or '401' in error_str or '403' in error_str:
            return 'auth_error'
        if 'range' in error_str or '416' in error_str:
            return 'chunk_error'
        if 'ssl' in error_str or 'certificate' in error_str:
            return 'network_error'

        return 'network_error'  # Default to network error for download issues

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
            # Store file info for error logging
            self.file_id = file_id

            # Get file info
            file_info = self.get_file_info(file_id)
            self.total_bytes = int(file_info.get('size', 0))
            actual_name = file_name or file_info.get('name', f'download_{file_id}')
            self.file_name = actual_name

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

            # Download chunks in parallel with batch retry for network failures
            chunk_data_map = {}
            chunks_to_download = chunks.copy()  # List of (idx, start, end) tuples
            batch_attempt = 0

            while chunks_to_download and batch_attempt < self.max_batch_retries:
                if self.cancelled:
                    logger.info("Download cancelled, stopping...")
                    self._cleanup()
                    return None

                batch_attempt += 1
                failed_chunks = []

                if batch_attempt > 1:
                    logger.info(
                        f"Batch retry {batch_attempt}/{self.max_batch_retries}: "
                        f"Retrying {len(chunks_to_download)} failed chunks..."
                    )
                    # Wait for network to stabilize before retrying
                    time.sleep(self.batch_retry_delay)

                    # Check network connectivity before retrying
                    if not self._check_network_connectivity():
                        logger.warning("Network still unavailable, waiting for connectivity...")
                        if not self._wait_for_network(max_wait_seconds=120):
                            logger.error("Network did not recover, aborting download")
                            self._cleanup()
                            return None

                # Create a managed thread pool for this batch
                self._pool = ThreadPoolExecutor(max_workers=self.num_threads)
                try:
                    futures = {
                        self._pool.submit(
                            self._download_chunk,
                            file_id,
                            start,
                            end,
                            idx
                        ): (idx, start, end)
                        for idx, start, end in chunks_to_download
                    }

                    for future in as_completed(futures):
                        if self.cancelled:
                            logger.info("Download cancelled, stopping...")
                            self._pool.shutdown(wait=False, cancel_futures=True)
                            self._cleanup()
                            return None

                        chunk_info = futures[future]
                        idx, start, end = chunk_info
                        chunk_index, chunk_data, success = future.result()

                        if success and chunk_data:
                            chunk_data_map[chunk_index] = chunk_data
                        else:
                            failed_chunks.append((idx, start, end))
                finally:
                    # Ensure pool is shut down
                    if self._pool:
                        self._pool.shutdown(wait=False)
                        self._pool = None

                # Update chunks_to_download with only the failed ones
                chunks_to_download = failed_chunks

                if failed_chunks:
                    failed_indices = [c[0] for c in failed_chunks]
                    if batch_attempt < self.max_batch_retries:
                        logger.warning(
                            f"Batch {batch_attempt}: {len(failed_chunks)} chunks failed "
                            f"(indices: {failed_indices[:10]}{'...' if len(failed_indices) > 10 else ''}). "
                            f"Will retry after {self.batch_retry_delay}s delay."
                        )
                    else:
                        logger.error(
                            f"Final batch attempt failed. {len(failed_chunks)} chunks could not be downloaded: "
                            f"{failed_indices}"
                        )

            # Check if all chunks were successfully downloaded
            if chunks_to_download:
                failed_indices = [c[0] for c in chunks_to_download]
                error_msg = (
                    f"Failed to download {len(chunks_to_download)} chunks after "
                    f"{self.max_batch_retries} batch retries: {failed_indices}"
                )
                logger.error(error_msg)

                # Log critical error for complete download failure
                if self.error_logger and self.job_id:
                    try:
                        self.error_logger.log_critical_error(
                            job_id=self.job_id,
                            phase="download",
                            error_message=error_msg,
                            mailbox_id=self.mailbox_id,
                            context_details={
                                "file_id": file_id,
                                "file_name": self.file_name,
                                "total_chunks": len(chunks),
                                "failed_chunks": len(chunks_to_download),
                                "failed_indices": failed_indices[:20],  # Limit to first 20
                                "batch_retries": self.max_batch_retries
                            }
                        )
                    except Exception as log_error:
                        logger.debug(f"Failed to log critical error: {log_error}")

                self._cleanup()
                return None

            logger.info(f"All {len(chunks)} chunks downloaded successfully")

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

            # Log critical error
            if self.error_logger and self.job_id:
                try:
                    self.error_logger.log_critical_error(
                        job_id=self.job_id,
                        phase="download",
                        error_message=f"Download failed: {str(e)}",
                        mailbox_id=self.mailbox_id,
                        exception=e,
                        context_details={
                            "file_id": file_id,
                            "file_name": self.file_name,
                            "total_bytes": self.total_bytes,
                            "downloaded_bytes": self.downloaded_bytes
                        }
                    )
                except Exception as log_error:
                    logger.debug(f"Failed to log critical error: {log_error}")

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
    max_batch_retries: int = 5,
    batch_retry_delay: int = 10,
    progress_callback: Optional[Callable[[Dict], None]] = None,
    job_id: Optional[str] = None,
    mailbox_id: Optional[str] = None,
    error_logger: Optional['JobErrorLogger'] = None
) -> Optional[str]:
    """
    Convenience function to download a Google Drive file with progress tracking.

    Args:
        access_token: Google OAuth2 access token
        file_id: Google Drive file ID
        file_name: Output filename
        num_threads: Number of parallel download threads
        max_batch_retries: Max batch retry rounds for failed chunks (default: 5)
        batch_retry_delay: Seconds to wait before retrying failed batches (default: 10)
        progress_callback: Optional callback receiving progress dict:
            {
                'downloaded_bytes': int,
                'total_bytes': int,
                'speed_mbps': float,
                'percent': float,
                'eta_seconds': float
            }
        job_id: Optional job ID for error logging
        mailbox_id: Optional mailbox ID for error logging
        error_logger: Optional JobErrorLogger instance

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
        max_batch_retries=max_batch_retries,
        batch_retry_delay=batch_retry_delay,
        progress_callback=internal_callback,
        job_id=job_id,
        mailbox_id=mailbox_id,
        error_logger=error_logger
    )

    return downloader.download(file_id, file_name)
