"""
Storage Adapter for handling files from multiple sources
Supports: Local filesystem, AWS S3, Google Drive, Azure Blob Storage
"""
import os
import tempfile
from abc import ABC, abstractmethod
from typing import Optional, BinaryIO
from urllib.parse import urlparse
import logging

logger = logging.getLogger(__name__)


class StorageAdapter(ABC):
    """Abstract base class for storage adapters"""

    @abstractmethod
    def get_file(self, path: str) -> str:
        """
        Get file and return local path (downloads if needed)
        Returns: Local file path that can be used by extractors
        """
        pass

    @abstractmethod
    def cleanup(self):
        """Cleanup any temporary files"""
        pass

    @abstractmethod
    def supports_uri(self, uri: str) -> bool:
        """Check if this adapter supports the given URI scheme"""
        pass


class LocalStorageAdapter(StorageAdapter):
    """Adapter for local filesystem access"""

    def supports_uri(self, uri: str) -> bool:
        parsed = urlparse(uri)
        return parsed.scheme in ('', 'file')

    def get_file(self, path: str) -> str:
        """Return the local file path as-is"""
        # Remove file:// prefix if present
        if path.startswith('file://'):
            path = path[7:]

        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {path}")

        return path

    def cleanup(self):
        """No cleanup needed for local files"""
        pass


class GoogleDriveAdapter(StorageAdapter):
    """Adapter for Google Drive files"""

    def __init__(self, credentials_path: Optional[str] = None):
        """
        Initialize Google Drive adapter

        Args:
            credentials_path: Path to Google Cloud service account JSON
                            or None to use environment variable GOOGLE_APPLICATION_CREDENTIALS
        """
        self.credentials_path = credentials_path or os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        self.temp_file = None
        self.service = None

    def supports_uri(self, uri: str) -> bool:
        parsed = urlparse(uri)
        return parsed.scheme in ('gdrive', 'googledrive') or 'drive.google.com' in uri

    def _init_service(self):
        """Initialize Google Drive API service (lazy loading)"""
        if self.service is not None:
            return

        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            credentials = service_account.Credentials.from_service_account_file(
                self.credentials_path,
                scopes=['https://www.googleapis.com/auth/drive.readonly']
            )
            self.service = build('drive', 'v3', credentials=credentials)
            logger.info("Google Drive service initialized successfully")
        except ImportError:
            raise ImportError(
                "Google Drive support requires: pip install google-auth google-auth-httplib2 google-api-python-client"
            )
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Google Drive service: {e}")

    def _extract_file_id(self, uri: str) -> str:
        """Extract Google Drive file ID from various URI formats"""
        # Format: gdrive://file_id
        if uri.startswith('gdrive://'):
            return uri[9:]

        # Format: https://drive.google.com/file/d/FILE_ID/...
        if 'drive.google.com' in uri:
            parts = uri.split('/d/')
            if len(parts) > 1:
                file_id = parts[1].split('/')[0].split('?')[0]
                return file_id

        # Assume it's just the file ID
        return uri

    def get_file(self, uri: str) -> str:
        """Download file from Google Drive and return local path"""
        self._init_service()

        file_id = self._extract_file_id(uri)

        try:
            # Get file metadata
            file_metadata = self.service.files().get(fileId=file_id, fields='name,mimeType').execute()
            filename = file_metadata['name']

            # Download file content
            from googleapiclient.http import MediaIoBaseDownload
            import io

            request = self.service.files().get_media(fileId=file_id)

            # Create temp file
            suffix = os.path.splitext(filename)[1]
            self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)

            downloader = MediaIoBaseDownload(self.temp_file, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status:
                    logger.info(f"Download {int(status.progress() * 100)}% complete")

            self.temp_file.flush()
            temp_path = self.temp_file.name
            self.temp_file.close()

            logger.info(f"Downloaded Google Drive file {filename} to {temp_path}")
            return temp_path

        except Exception as e:
            self.cleanup()
            raise RuntimeError(f"Failed to download from Google Drive: {e}")

    def cleanup(self):
        """Remove temporary downloaded file"""
        if self.temp_file and os.path.exists(self.temp_file.name):
            try:
                os.unlink(self.temp_file.name)
                logger.info(f"Cleaned up temp file: {self.temp_file.name}")
            except Exception as e:
                logger.warning(f"Failed to cleanup temp file: {e}")
            self.temp_file = None


class S3StorageAdapter(StorageAdapter):
    """Adapter for AWS S3 storage"""

    def __init__(self, aws_access_key: Optional[str] = None, aws_secret_key: Optional[str] = None):
        """
        Initialize S3 adapter

        Args:
            aws_access_key: AWS access key (or None to use environment/IAM)
            aws_secret_key: AWS secret key (or None to use environment/IAM)
        """
        self.aws_access_key = aws_access_key
        self.aws_secret_key = aws_secret_key
        self.temp_file = None
        self.s3_client = None

    def supports_uri(self, uri: str) -> bool:
        parsed = urlparse(uri)
        return parsed.scheme == 's3'

    def _init_client(self):
        """Initialize S3 client (lazy loading)"""
        if self.s3_client is not None:
            return

        try:
            import boto3

            if self.aws_access_key and self.aws_secret_key:
                self.s3_client = boto3.client(
                    's3',
                    aws_access_key_id=self.aws_access_key,
                    aws_secret_access_key=self.aws_secret_key
                )
            else:
                # Use default credentials (environment, IAM role, etc.)
                self.s3_client = boto3.client('s3')

            logger.info("S3 client initialized successfully")
        except ImportError:
            raise ImportError("S3 support requires: pip install boto3")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize S3 client: {e}")

    def get_file(self, uri: str) -> str:
        """Download file from S3 and return local path"""
        self._init_client()

        # Parse S3 URI: s3://bucket/path/to/file
        parsed = urlparse(uri)
        bucket = parsed.netloc
        key = parsed.path.lstrip('/')

        try:
            # Create temp file
            suffix = os.path.splitext(key)[1]
            self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)

            # Download file
            self.s3_client.download_fileobj(bucket, key, self.temp_file)
            self.temp_file.flush()
            temp_path = self.temp_file.name
            self.temp_file.close()

            logger.info(f"Downloaded S3 file s3://{bucket}/{key} to {temp_path}")
            return temp_path

        except Exception as e:
            self.cleanup()
            raise RuntimeError(f"Failed to download from S3: {e}")

    def cleanup(self):
        """Remove temporary downloaded file"""
        if self.temp_file and os.path.exists(self.temp_file.name):
            try:
                os.unlink(self.temp_file.name)
                logger.info(f"Cleaned up temp file: {self.temp_file.name}")
            except Exception as e:
                logger.warning(f"Failed to cleanup temp file: {e}")
            self.temp_file = None


class StorageManager:
    """
    Manager for selecting appropriate storage adapter based on URI scheme
    """

    def __init__(self):
        self.adapters = [
            GoogleDriveAdapter(),
            S3StorageAdapter(),
            LocalStorageAdapter(),  # Fallback
        ]
        self.current_adapter: Optional[StorageAdapter] = None

    def get_adapter(self, uri: str) -> StorageAdapter:
        """Get appropriate adapter for the given URI"""
        for adapter in self.adapters:
            if adapter.supports_uri(uri):
                return adapter

        # Fallback to local
        return LocalStorageAdapter()

    def get_file(self, uri: str) -> str:
        """
        Get file from any supported storage location

        Args:
            uri: File URI (local path, s3://, gdrive://, etc.)

        Returns:
            Local file path that can be used by extractors

        Example URIs:
            - /path/to/local/file.mbox
            - file:///path/to/file.mbox
            - s3://bucket-name/path/to/file.mbox
            - gdrive://file_id_here
            - https://drive.google.com/file/d/FILE_ID/view
        """
        self.current_adapter = self.get_adapter(uri)
        logger.info(f"Using {self.current_adapter.__class__.__name__} for {uri}")
        return self.current_adapter.get_file(uri)

    def cleanup(self):
        """Cleanup any temporary files"""
        if self.current_adapter:
            self.current_adapter.cleanup()
            self.current_adapter = None


# Example usage:
if __name__ == '__main__':
    manager = StorageManager()

    # Local file
    # local_path = manager.get_file('/path/to/local/file.mbox')

    # S3 file
    # s3_path = manager.get_file('s3://my-bucket/emails/archive.mbox')

    # Google Drive file
    # gdrive_path = manager.get_file('gdrive://1234567890abcdef')

    # Always cleanup when done
    # manager.cleanup()

    pass
