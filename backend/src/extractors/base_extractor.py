"""
Base Extractor - Stable Contract for All Email Format Adapters

This is the core abstraction that all format-specific extractors (MBOX, PST, OLM, etc.)
must implement. It defines the minimal, stable interface that the rest of the system
depends on.

Design principles:
1. Format adapters (extractors) are thin - they parse and yield standardized emails
2. Cross-cutting concerns (date filtering, dedup, indexing) live in the pipeline
3. All extractors speak the same language (standardized email dict)
4. Shared logic lives here to avoid duplication
"""

from abc import ABC, abstractmethod
from typing import Iterator, Dict, Optional, List, Any
from datetime import datetime, timezone
import logging
import hashlib
import os
import tempfile

logger = logging.getLogger(__name__)


class BaseExtractor(ABC):
    """
    Abstract base class for email extractors

    Contract:
    - __init__(connection_config) stores configuration
    - connect(**kwargs) establishes connection to source
    - extract_emails(max_emails) yields standardized email dicts
    - get_folders() returns folder metadata for UI
    - disconnect() cleans up resources
    """

    def __init__(self, connection_config: Dict[str, Any]):
        """
        Initialize extractor with connection configuration

        Args:
            connection_config: Dict with connection details
                - file_path: Path to email file (for file-based formats)
                - google_drive_file_id: Google Drive file ID (for Google Drive files)
                - file_source: 'local' or 'google_drive'
                - url: Cloud URL (for cloud sources)
                - credentials: Auth details (for remote sources)
                - format-specific options
        """
        self.config = connection_config
        self.temp_file_path = None  # For downloaded Google Drive files
        self.stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'errors': [],  # Stage 2: List of error messages for tracking
            'emails_extracted': 0,  # Track extracted count
            'start_time': None,
            'end_time': None
        }
        self.source_type = None  # Set by subclass: "mbox", "pst", "olm", etc.
        self.temp_file_path = None  # For downloaded Google Drive files

    def get_effective_file_path(self, access_token: Optional[str] = None) -> str:
        """
        Get the file path to process, checking for mounted drives first, then streaming
        
        Args:
            access_token: OAuth2 access token for Google Drive (if needed)
        
        Returns:
            str: Path to the file that can be processed locally
        """
        file_source = self.config.get('file_source', 'local')
        
        if file_source == 'google_drive':
            # First, check if Google Drive is mounted locally (best performance)
            google_file_name = self.config.get('google_drive_file_name', '')
            
            # Common Google Drive mount points
            possible_mounts = [
                f"/mnt/gdrive/{google_file_name}",  # Linux rclone
                f"/home/{os.getenv('USER', 'user')}/gdrive/{google_file_name}",  # Linux user mount
                f"/Users/{os.getenv('USER', 'user')}/Google Drive/{google_file_name}",  # macOS Google Drive app
                f"/Users/{os.getenv('USER', 'user')}/GoogleDrive/{google_file_name}",  # macOS alternative
                f"~/gdrive/{google_file_name}",  # Generic home mount
                f"/google-drive/{google_file_name}",  # Docker mount
            ]
            
            # Check each possible mount point
            for mount_path in possible_mounts:
                expanded_path = os.path.expanduser(mount_path)
                if os.path.exists(expanded_path) and os.path.isfile(expanded_path):
                    logger.info(f"📁 Found Google Drive file at local mount: {expanded_path}")
                    return expanded_path
            
            # No local mount found, use streaming
            logger.info(f"📡 No local mount found for {google_file_name}, using streaming approach")
            return 'GOOGLE_DRIVE_STREAM'
        else:
            # Use local file path
            file_path = self.config.get('file_path')
            if not file_path:
                raise ValueError("No file_path provided in connection config")
            return file_path
    
    def _download_google_drive_file(self, access_token: Optional[str] = None) -> str:
        """
        Download Google Drive file to temporary location using user's stored tokens
        
        Args:
            access_token: Legacy parameter (not used with new user token system)
        
        Returns:
            str: Path to downloaded temporary file
        """
        google_file_id = self.config.get('google_drive_file_id')
        google_file_name = self.config.get('google_drive_file_name', 'downloaded_file')
        user_id = self.config.get('user_id')  # User ID should be in config for token lookup
        
        if not google_file_id:
            raise ValueError("Google Drive file ID not provided in connection config")
        
        logger.info(f"📥 Downloading Google Drive file: {google_file_name} (ID: {google_file_id})")
        
        try:
            # Import here to avoid circular imports
            from ..storage.google_drive_client import create_google_drive_client
            
            # Create client and try authentication methods
            client = create_google_drive_client()
            authenticated = False
            
            # Try user token authentication first (industry standard)
            if user_id:
                logger.info("Trying Google Drive authentication with user's stored tokens...")
                try:
                    # Get user tokens from database
                    from ..database.supabase_client import SupabaseClient
                    supabase = SupabaseClient.get_client(use_service_key=True)
                    
                    result = supabase.table('user_integrations').select('access_token,refresh_token').eq('user_id', user_id).eq('provider', 'google_drive').execute()
                    
                    if result.data:
                        tokens = result.data[0]
                        authenticated = client.authenticate_with_user_tokens(
                            access_token=tokens['access_token'],
                            refresh_token=tokens['refresh_token']
                        )
                        
                        # If token was refreshed, update database
                        updated_tokens = client.get_current_tokens()
                        if updated_tokens and updated_tokens['access_token'] != tokens['access_token']:
                            supabase.table('user_integrations').update({
                                'access_token': updated_tokens['access_token']
                            }).eq('user_id', user_id).eq('provider', 'google_drive').execute()
                            logger.info("Updated refreshed access token in database")
                    
                except Exception as e:
                    logger.warning(f"Failed to use user tokens: {e}")
            
            # Fallback to service account authentication
            if not authenticated:
                logger.info("Falling back to service account authentication...")
                authenticated = client.authenticate_with_service_account()
            
            if not authenticated:
                raise RuntimeError(
                    "Failed to authenticate with Google Drive. Please ensure either:\n"
                    "1. User has connected their Google Drive account, OR\n"
                    "2. Service account credentials are configured (GOOGLE_SERVICE_ACCOUNT_JSON environment variable)"
                )
            
            # Download the file
            temp_file_path = client.download_file_to_temp(google_file_id, google_file_name)
            if not temp_file_path:
                raise RuntimeError(f"Failed to download Google Drive file: {google_file_name}")
            
            logger.info(f"✅ Google Drive file downloaded successfully: {temp_file_path}")
            return temp_file_path
            
        except Exception as e:
            logger.error(f"Failed to download Google Drive file {google_file_id}: {e}")
            raise
    
    def cleanup_temp_files(self):
        """Clean up any temporary files created for Google Drive downloads"""
        if self.temp_file_path and os.path.exists(self.temp_file_path):
            try:
                # Remove the file
                os.remove(self.temp_file_path)
                
                # Remove parent directory if empty
                parent_dir = os.path.dirname(self.temp_file_path)
                if os.path.exists(parent_dir) and not os.listdir(parent_dir):
                    os.rmdir(parent_dir)
                
                logger.info(f"🗑️ Cleaned up temporary Google Drive file: {self.temp_file_path}")
                self.temp_file_path = None
                
            except Exception as e:
                logger.warning(f"Failed to cleanup temp file {self.temp_file_path}: {e}")

    @abstractmethod
    def connect(self, **kwargs) -> bool:
        """
        Establish connection to email source

        Returns:
            True if connection successful

        Raises:
            ConnectionError: If connection fails
        """
        pass

    @abstractmethod
    def extract_emails(self, max_emails: Optional[int] = None) -> Iterator[Dict]:
        """
        Extract emails and yield as standardized dictionaries

        This should ONLY parse and normalize - no date filtering, no deduplication.
        Those concerns belong in the pipeline layer.

        Args:
            max_emails: Maximum number of emails to extract (None = all)

        Yields:
            Dict: Standardized email dictionary (see _standardize_email for schema)
        """
        pass

    @abstractmethod
    def get_folders(self) -> List[Dict]:
        """
        Get list of available folders from source

        Returns:
            List of folder dicts with:
                - id: Unique folder identifier
                - name: Display name
                - path: Full folder path
                - message_count: Number of messages (optional)
                - type: Folder type hint (inbox, sent, drafts, etc.)
        """
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Clean up connection and resources"""
        pass

    def get_email_count(self) -> Optional[int]:
        """
        Get total number of emails in source (fast estimation)

        This method should be implemented by subclasses to provide a quick count
        of total emails without processing them. Used for progress estimation.

        Returns:
            Total email count or None if not available/not implemented
        """
        # Default implementation returns None (not implemented)
        # Subclasses should override with format-specific counting
        return None

    # =========================================================================
    # Stats and Lifecycle Methods
    # =========================================================================

    def get_stats(self) -> Dict:
        """Return extraction statistics"""
        return self.stats

    def _mark_start(self):
        """Mark extraction start time"""
        self.stats['start_time'] = datetime.now(timezone.utc)
        logger.info(f"Starting {self.source_type} extraction at {self.stats['start_time']}")

    def _mark_end(self):
        """Mark extraction end time"""
        self.stats['end_time'] = datetime.now(timezone.utc)
        duration = (self.stats['end_time'] - self.stats['start_time']).total_seconds()
        logger.info(f"Completed {self.source_type} extraction in {duration:.2f}s - "
                   f"Total: {self.stats['total']}, Success: {self.stats['success']}, "
                   f"Failed: {self.stats['failed']}")

    def _update_stats(self, success: bool, error: str = None):
        """Update extraction statistics"""
        self.stats['total'] += 1
        if success:
            self.stats['success'] += 1
        else:
            self.stats['failed'] += 1
            if error:
                logger.error(f"Extraction error: {error}")

    # =========================================================================
    # Standardization - The Core Contract
    # =========================================================================

    def _standardize_email(self, raw_email: Dict, source_path: str = None) -> Dict:
        """
        Convert raw format-specific email to standardized schema

        Standard Email Schema:
        ----------------------
        REQUIRED FIELDS:
        - message_id: Unique message identifier
        - subject: Email subject
        - sender_email: Sender email address (normalized)
        - sender_name: Sender display name
        - recipients: List[{email, name}]
        - cc_list: List[{email, name}]
        - bcc_list: List[{email, name}]
        - sent_date: datetime when sent
        - received_date: datetime when received
        - body_text: Plain text body
        - body_html: HTML body
        - folder_path: Folder location
        - is_outbound: True if sent by user
        - is_reply: True if reply/forward
        - raw_headers: Dict of original headers
        - message_size: Size in bytes

        RECOMMENDED FIELDS (for future):
        - attachments: List[{id, filename, size, mime_type, storage_pointer}]
        - source: Format type ("mbox", "pst", "olm")
        - source_path: Location within source (offset, ZIP entry, folder+id)
        - thread_key: Threading identifier (Message-Id/In-Reply-To based)

        Args:
            raw_email: Format-specific email dict
            source_path: Optional path within source for debugging

        Returns:
            Standardized email dict
        """
        # Generate thread key for future threading support
        thread_key = self._generate_thread_key(
            raw_email.get('message_id'),
            raw_email.get('in_reply_to'),
            raw_email.get('references')
        )

        return {
            # Required fields
            'message_id': raw_email.get('message_id', ''),
            'subject': raw_email.get('subject', ''),
            'sender_email': self._clean_email(raw_email.get('sender_email', '')),
            'sender_name': raw_email.get('sender_name', ''),
            'recipients': self._normalize_recipients(raw_email.get('recipients', [])),
            'cc_list': self._normalize_recipients(raw_email.get('cc_list', [])),
            'bcc_list': self._normalize_recipients(raw_email.get('bcc_list', [])),
            'sent_date': self._normalize_datetime(raw_email.get('sent_date')),
            'received_date': self._normalize_datetime(raw_email.get('received_date')),
            'body_text': raw_email.get('body_text', ''),
            'body_html': raw_email.get('body_html', ''),
            'folder_path': raw_email.get('folder_path', 'INBOX'),
            'is_outbound': raw_email.get('is_outbound', False),
            'is_reply': raw_email.get('is_reply', False),
            'raw_headers': raw_email.get('raw_headers', {}),
            'message_size': len(raw_email.get('body_text', '')),

            # Recommended fields
            'attachments': raw_email.get('attachments', []),
            'source': self.source_type,
            'source_path': source_path or raw_email.get('source_path', ''),
            'thread_key': thread_key,

            # Threading fields (first-class for robust thread grouping)
            'in_reply_to': raw_email.get('in_reply_to', ''),
            'references': raw_email.get('references', ''),
            'provider_thread_id': (
                raw_email.get('gmail_thread_id')
                or raw_email.get('outlook_conversation_id')
                or raw_email.get('provider_thread_id')
                or ''
            ),
        }

    # =========================================================================
    # Shared Helper Methods
    # =========================================================================

    def _clean_email(self, email: str) -> str:
        """Clean and normalize email address"""
        if not email:
            return ''
        return email.lower().strip()

    def _normalize_recipients(self, recipients: Any) -> List[Dict]:
        """
        Normalize recipients to standard format: List[{email, name}]

        Handles:
        - String: "user@domain.com"
        - List of strings: ["user1@domain.com", "user2@domain.com"]
        - List of dicts: [{"email": "user@domain.com", "name": "User"}]
        """
        if not recipients:
            return []

        if isinstance(recipients, str):
            return [{'email': self._clean_email(recipients), 'name': ''}]

        normalized = []
        for recipient in recipients:
            if isinstance(recipient, str):
                normalized.append({
                    'email': self._clean_email(recipient),
                    'name': ''
                })
            elif isinstance(recipient, dict):
                normalized.append({
                    'email': self._clean_email(recipient.get('email', '')),
                    'name': recipient.get('name', '')
                })

        return normalized

    def _normalize_datetime(self, dt: Any, default_tz=timezone.utc) -> Optional[datetime]:
        """
        Normalize datetime to consistent format with timezone

        Args:
            dt: datetime object, string, or None
            default_tz: Default timezone if none specified

        Returns:
            datetime object with timezone or None
        """
        if dt is None:
            return None

        if isinstance(dt, datetime):
            # Ensure timezone awareness
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=default_tz)
            return dt

        # If string, try to parse (subclasses can override for format-specific parsing)
        if isinstance(dt, str):
            try:
                parsed = datetime.fromisoformat(dt)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=default_tz)
                return parsed
            except Exception as e:
                logger.debug(f"Could not parse datetime '{dt}': {e}")
                return None

        return None

    def _is_sent_folder(self, folder_path: str) -> bool:
        """
        Check if folder is a Sent folder

        Common indicators across all email systems
        """
        if not folder_path:
            return False

        sent_indicators = [
            'sent', 'sent items', 'sent mail', 'sent messages',
            'outbox', 'envoyé', 'enviados', 'gesendete'  # International
        ]
        folder_lower = folder_path.lower()
        return any(indicator in folder_lower for indicator in sent_indicators)

    def _is_reply_subject(self, subject: str) -> bool:
        """
        Check if subject indicates reply or forward

        Handles international reply/forward prefixes
        """
        if not subject:
            return False

        subject_lower = subject.lower().strip()
        reply_prefixes = [
            're:', 'aw:',  # Reply (English, German)
            'fwd:', 'fw:', 'wg:',  # Forward (English, German)
            'sv:',  # Reply (Swedish)
            'vs:',  # Reply (Finnish)
        ]
        return any(subject_lower.startswith(prefix) for prefix in reply_prefixes)

    def _generate_thread_key(self, message_id: str, in_reply_to: str = None,
                            references: str = None) -> str:
        """
        Generate thread key for email threading

        Uses Message-ID and In-Reply-To to group related emails

        Args:
            message_id: Message-ID header
            in_reply_to: In-Reply-To header
            references: References header

        Returns:
            Thread key (hash of conversation root)
        """
        # Use In-Reply-To as thread root if available
        if in_reply_to:
            root = in_reply_to.strip()
        # Otherwise use first reference
        elif references:
            refs = references.split()
            root = refs[0] if refs else message_id
        # Otherwise this starts a new thread
        else:
            root = message_id

        if not root:
            return ''

        # Hash to fixed-length key
        return hashlib.sha256(root.encode()).hexdigest()[:16]

    def _extract_message_id(self, headers: Dict) -> str:
        """
        Extract Message-ID from headers

        Tries multiple common header formats
        """
        for key in ['Message-ID', 'Message-Id', 'message-id']:
            if key in headers:
                msg_id = headers[key]
                # Strip angle brackets if present
                return msg_id.strip('<>')
        return ''

    def _calculate_message_size(self, body_text: str = '', body_html: str = '',
                                attachments: List = None) -> int:
        """
        Calculate approximate message size

        Args:
            body_text: Plain text body
            body_html: HTML body
            attachments: List of attachment dicts with 'size' field

        Returns:
            Size in bytes
        """
        size = len(body_text) + len(body_html)

        if attachments:
            for att in attachments:
                size += att.get('size', 0)

        return size
