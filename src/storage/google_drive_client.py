"""
Google Drive Client for Backend File Access

This service handles downloading files from Google Drive using OAuth2 credentials
that are passed from the frontend. It supports streaming downloads for large files
without storing them completely in memory.

Usage:
- Frontend provides access_token from user's OAuth2 flow
- Backend uses this token to download files directly from Google Drive
- Files are streamed to temporary locations for processing
"""

import os
import tempfile
import logging
from typing import Optional, Dict, Any
from pathlib import Path
import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io
import json

logger = logging.getLogger(__name__)


class GoogleDriveClient:
    """Handle Google Drive file operations for the backend"""
    
    def __init__(self):
        self.service = None
        self.credentials = None
    
    def authenticate_with_token(self, access_token: str) -> bool:
        """
        Authenticate using access token from frontend
        
        Args:
            access_token: OAuth2 access token from frontend
            
        Returns:
            bool: True if authentication successful
        """
        try:
            # Create credentials object from access token
            self.credentials = Credentials(token=access_token)
            
            # Build the Drive service
            self.service = build('drive', 'v3', credentials=self.credentials)
            
            # Test the connection
            about = self.service.about().get(fields="user").execute()
            logger.info(f"✅ Google Drive authenticated for user: {about.get('user', {}).get('emailAddress', 'Unknown')}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to authenticate with Google Drive: {e}")
            return False
    
    def authenticate_with_service_account(self, service_account_file: Optional[str] = None, 
                                        service_account_info: Optional[Dict] = None) -> bool:
        """
        Authenticate using service account for backend access
        
        Args:
            service_account_file: Path to service account JSON file
            service_account_info: Service account info dict (alternative to file)
            
        Returns:
            bool: True if authentication successful
        """
        try:
            # Try service account file first
            if service_account_file and os.path.exists(service_account_file):
                self.credentials = ServiceAccountCredentials.from_service_account_file(
                    service_account_file,
                    scopes=['https://www.googleapis.com/auth/drive.readonly']
                )
                logger.info(f"✅ Service account loaded from file: {service_account_file}")
            
            # Try service account info from environment
            elif service_account_info:
                self.credentials = ServiceAccountCredentials.from_service_account_info(
                    service_account_info,
                    scopes=['https://www.googleapis.com/auth/drive.readonly']
                )
                logger.info("✅ Service account loaded from environment info")
            
            # Try environment variable
            else:
                service_account_env = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')
                if service_account_env:
                    service_account_data = json.loads(service_account_env)
                    self.credentials = ServiceAccountCredentials.from_service_account_info(
                        service_account_data,
                        scopes=['https://www.googleapis.com/auth/drive.readonly']
                    )
                    logger.info("✅ Service account loaded from GOOGLE_SERVICE_ACCOUNT_JSON environment variable")
                else:
                    logger.error("❌ No service account credentials found. Set GOOGLE_SERVICE_ACCOUNT_JSON environment variable or provide file path")
                    return False
            
            # Build the Drive service
            self.service = build('drive', 'v3', credentials=self.credentials)
            
            # Test the connection (service accounts don't have user info)
            about = self.service.about().get(fields="storageQuota").execute()
            logger.info("✅ Google Drive service account authenticated successfully")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to authenticate with service account: {e}")
            return False
    
    def authenticate_with_user_tokens(self, access_token: str, refresh_token: str) -> bool:
        """
        Authenticate using user's stored OAuth2 tokens
        
        Args:
            access_token: User's current access token
            refresh_token: User's refresh token for auto-renewal
            
        Returns:
            bool: True if authentication successful
        """
        try:
            # Create credentials with user tokens
            self.credentials = Credentials(
                token=access_token,
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=os.getenv("GOOGLE_CLIENT_ID"),
                client_secret=os.getenv("GOOGLE_CLIENT_SECRET")
            )
            
            # Auto-refresh if token is expired
            if self.credentials.expired:
                logger.info("Access token expired, refreshing...")
                self.credentials.refresh(Request())
                logger.info("✅ Access token refreshed successfully")
            
            # Build the Drive service
            self.service = build('drive', 'v3', credentials=self.credentials)
            
            # Test the connection
            about = self.service.about().get(fields="user").execute()
            user_email = about.get('user', {}).get('emailAddress', 'Unknown')
            logger.info(f"✅ Google Drive authenticated for user: {user_email}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to authenticate with user tokens: {e}")
            return False
    
    def get_current_tokens(self) -> Optional[Dict[str, str]]:
        """
        Get current access token (useful after auto-refresh)
        
        Returns:
            Dict with current tokens or None if not authenticated
        """
        if self.credentials:
            return {
                'access_token': self.credentials.token,
                'refresh_token': self.credentials.refresh_token,
                'expires_at': self.credentials.expiry.isoformat() if self.credentials.expiry else None
            }
        return None
    
    def download_file_to_temp(self, file_id: str, file_name: str) -> Optional[str]:
        """
        Download a Google Drive file to a temporary location
        
        Args:
            file_id: Google Drive file ID
            file_name: Original file name (for extension detection)
            
        Returns:
            str: Path to downloaded temporary file, or None if failed
        """
        if not self.service:
            logger.error("Google Drive service not initialized")
            return None
            
        try:
            logger.info(f"📥 Starting download of Google Drive file: {file_name} (ID: {file_id})")
            
            # Get file metadata
            file_metadata = self.service.files().get(fileId=file_id, fields="name,size,mimeType").execute()
            actual_name = file_metadata.get('name', file_name)
            file_size = int(file_metadata.get('size', 0))
            
            logger.info(f"📄 File details: {actual_name}, Size: {self._format_size(file_size)}")
            
            # Create temporary file with proper extension
            file_extension = Path(actual_name).suffix
            temp_dir = tempfile.mkdtemp(prefix='gdrive_download_')
            temp_file_path = os.path.join(temp_dir, f"downloaded_{file_id}{file_extension}")
            
            # Request file content
            request = self.service.files().get_media(fileId=file_id)
            
            # Stream download to file
            with open(temp_file_path, 'wb') as temp_file:
                downloader = MediaIoBaseDownload(temp_file, request)
                done = False
                
                while not done:
                    status, done = downloader.next_chunk()
                    if status:
                        progress = int(status.progress() * 100)
                        logger.info(f"📥 Download progress: {progress}%")
            
            # Verify download
            downloaded_size = os.path.getsize(temp_file_path)
            if downloaded_size > 0:
                logger.info(f"✅ Download complete: {temp_file_path} ({self._format_size(downloaded_size)})")
                return temp_file_path
            else:
                logger.error("❌ Downloaded file is empty")
                self._cleanup_temp_file(temp_file_path)
                return None
                
        except Exception as e:
            logger.error(f"❌ Failed to download Google Drive file {file_id}: {e}")
            return None
    
    def get_file_info(self, file_id: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata about a Google Drive file
        
        Args:
            file_id: Google Drive file ID
            
        Returns:
            Dict with file metadata, or None if failed
        """
        if not self.service:
            logger.error("Google Drive service not initialized")
            return None
            
        try:
            file_metadata = self.service.files().get(
                fileId=file_id, 
                fields="name,size,mimeType,modifiedTime,parents"
            ).execute()
            
            return {
                'name': file_metadata.get('name'),
                'size': int(file_metadata.get('size', 0)),
                'mimeType': file_metadata.get('mimeType'),
                'modifiedTime': file_metadata.get('modifiedTime'),
                'parents': file_metadata.get('parents', [])
            }
            
        except Exception as e:
            logger.error(f"Failed to get file info for {file_id}: {e}")
            return None
    
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
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
    
    @staticmethod
    def _cleanup_temp_file(file_path: str):
        """Clean up temporary files and directories"""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                
            # Also remove parent directory if empty
            parent_dir = os.path.dirname(file_path)
            if os.path.exists(parent_dir) and not os.listdir(parent_dir):
                os.rmdir(parent_dir)
                
            logger.info(f"🗑️ Cleaned up temporary file: {file_path}")
            
        except Exception as e:
            logger.warning(f"Failed to cleanup temp file {file_path}: {e}")


def create_google_drive_client() -> GoogleDriveClient:
    """Factory function to create a Google Drive client"""
    return GoogleDriveClient()