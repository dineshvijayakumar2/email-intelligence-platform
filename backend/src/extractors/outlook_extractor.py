"""
Outlook Extractor - LIVE Email Sync via Microsoft Graph API

This extractor fetches emails directly from Outlook/O365 using the Microsoft Graph API.
Supports both O365 (work/school) and personal Microsoft accounts.

Key Features:
- OAuth2 authentication with MSAL
- Incremental sync using Microsoft Graph delta queries
- Folder mapping for consistency
- Rate limiting: 10,000 requests per 10 minutes
- Full and incremental sync modes

Microsoft Graph API Reference:
https://docs.microsoft.com/en-us/graph/api/resources/mail-api-overview
"""

from typing import Iterator, Dict, Optional, List, Any
from datetime import datetime, timezone
import logging
import os
import re
import time

import requests

from .base_extractor import BaseExtractor

logger = logging.getLogger(__name__)


class OutlookExtractor(BaseExtractor):
    """
    Extract emails from Outlook via Microsoft Graph API

    Implements BaseExtractor contract for LIVE email sync.
    Supports both O365 (work/school) and personal Microsoft accounts.
    """

    # Microsoft Graph API configuration
    GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
    MESSAGES_PER_REQUEST = 100  # Graph API default page size
    MAX_RETRIES = 3
    RETRY_DELAY = 2  # seconds

    # Well-known Outlook folder names
    WELL_KNOWN_FOLDERS = {
        'inbox': 'Inbox',
        'sentitems': 'Sent',
        'drafts': 'Drafts',
        'deleteditems': 'Trash',
        'junkemail': 'Spam',
        'archive': 'Archive',
        'outbox': 'Outbox',
    }

    # Folder type mapping
    FOLDER_TYPE_MAP = {
        'inbox': 'inbox',
        'sentitems': 'sent',
        'drafts': 'drafts',
        'deleteditems': 'trash',
        'junkemail': 'spam',
        'archive': 'archive',
        'outbox': 'outbox',
    }

    def __init__(self, connection_config: Dict[str, Any] = None):
        """
        Initialize Outlook extractor

        Args:
            connection_config: Dict containing:
                - user_id: User ID for token lookup
                - access_token: Current access token
                - refresh_token: Refresh token for renewal
                - delta_link: Last delta link for incremental sync (optional)
                - folders: List of folders to sync (default: ['inbox', 'sentitems'])
                - mailbox_id: Associated mailbox ID for the email records
        """
        config = connection_config or {}
        super().__init__(config)

        self.source_type = "outlook"
        self.user_id = config.get('user_id')
        self.access_token = config.get('access_token')
        self.refresh_token = config.get('refresh_token')
        self.delta_link = config.get('delta_link')
        self.folders_to_sync = config.get('folders', ['inbox', 'sentitems'])
        self.mailbox_id = config.get('mailbox_id')

        # Microsoft Graph state
        self.user_email = None
        self.folder_map = {}  # Maps folder IDs to folder info

        # Token management
        self.tokens_refreshed = False
        self._new_access_token = None
        self.auth_expired = False
        self.auth_error = None

        logger.info(f"OutlookExtractor initialized for user: {self.user_id}, folders: {self.folders_to_sync}")

    def connect(self, **kwargs) -> bool:
        """
        Connect to Microsoft Graph API using OAuth2 tokens

        Returns:
            True if connection successful
        """
        try:
            if not self.access_token:
                raise ValueError("No access token provided")

            # Try to get user profile to verify connection
            headers = self._get_auth_headers()
            response = requests.get(
                f"{self.GRAPH_BASE_URL}/me",
                headers=headers
            )

            if response.status_code == 401:
                # Token might be expired, try to refresh
                if self.refresh_token:
                    logger.info("Access token expired, refreshing...")
                    if self._refresh_access_token():
                        headers = self._get_auth_headers()
                        response = requests.get(
                            f"{self.GRAPH_BASE_URL}/me",
                            headers=headers
                        )
                    else:
                        raise RuntimeError("Failed to refresh access token")
                else:
                    raise RuntimeError("Access token expired and no refresh token available")

            response.raise_for_status()
            user_data = response.json()

            self.user_email = user_data.get('mail') or user_data.get('userPrincipalName', '')
            logger.info(f"Connected to Outlook as: {self.user_email}")

            # Load folder mappings
            self._load_folders()

            return True

        except Exception as e:
            error_msg = str(e)
            # Detect auth expiry - refresh token revoked or expired (cannot auto-recover)
            auth_patterns = [
                'invalid_grant', 'failed to refresh access token',
                'aadsts70008', 'aadsts700082', 'aadsts70043',
                'refresh token is expired', 'access token expired and no refresh token'
            ]
            if any(pat in error_msg.lower() for pat in auth_patterns):
                self.auth_expired = True
                self.auth_error = error_msg
                logger.error(f"Outlook authentication expired (refresh token revoked): {e}")
            else:
                logger.error(f"Failed to connect to Outlook: {e}")
            return False

    def _get_auth_headers(self) -> Dict[str, str]:
        """Get authorization headers for API requests"""
        return {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json',
            'Prefer': 'outlook.body-content-type="html"'  # Request HTML body for rich text formatting
        }

    def _refresh_access_token(self) -> bool:
        """
        Refresh the access token using MSAL

        Returns:
            True if refresh successful
        """
        try:
            client_id = os.getenv("MICROSOFT_CLIENT_ID")
            client_secret = os.getenv("MICROSOFT_CLIENT_SECRET")
            tenant_id = os.getenv("MICROSOFT_TENANT_ID", "common")

            if not client_id or not client_secret:
                logger.error("Microsoft OAuth credentials not configured")
                return False

            token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

            data = {
                'client_id': client_id,
                'client_secret': client_secret,
                'refresh_token': self.refresh_token,
                'grant_type': 'refresh_token',
                'scope': 'openid profile email offline_access Mail.Read User.Read MailboxSettings.Read'
            }

            response = requests.post(token_url, data=data)
            response.raise_for_status()

            token_data = response.json()
            self.access_token = token_data.get('access_token')
            self._new_access_token = self.access_token
            self.tokens_refreshed = True

            # Update refresh token if a new one was issued
            if 'refresh_token' in token_data:
                self.refresh_token = token_data['refresh_token']

            logger.info("Token refreshed successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to refresh token: {e}")
            return False

    def _load_folders(self):
        """Load and cache Outlook folder mappings"""
        try:
            headers = self._get_auth_headers()
            response = requests.get(
                f"{self.GRAPH_BASE_URL}/me/mailFolders",
                headers=headers,
                params={'$top': 100, '$select': 'id,displayName,totalItemCount,unreadItemCount'}
            )
            response.raise_for_status()

            folders = response.json().get('value', [])

            for folder in folders:
                folder_id = folder['id']
                display_name = folder['displayName']

                self.folder_map[folder_id] = {
                    'id': folder_id,
                    'name': display_name,
                    'display_name_lower': display_name.lower(),
                    'messagesTotal': folder.get('totalItemCount', 0),
                    'messagesUnread': folder.get('unreadItemCount', 0),
                }

            logger.info(f"Loaded {len(self.folder_map)} Outlook folders")

        except Exception as e:
            logger.warning(f"Failed to load folders: {e}")

    def get_folders(self) -> List[Dict]:
        """
        Get Outlook folders

        Returns:
            List of folder dicts compatible with BaseExtractor contract
        """
        folders = []

        for folder_id, folder_info in self.folder_map.items():
            folder_type = self._get_folder_type(folder_info['display_name_lower'])

            folders.append({
                'id': folder_id,
                'name': folder_info['name'],
                'path': folder_info['name'],
                'message_count': folder_info.get('messagesTotal', 0),
                'type': folder_type
            })

        return folders

    def _get_folder_type(self, folder_name_lower: str) -> str:
        """Map Outlook folder name to folder type"""
        for key, folder_type in self.FOLDER_TYPE_MAP.items():
            if key in folder_name_lower or folder_name_lower in key:
                return folder_type
        return 'user'

    def _get_folder_id_by_name(self, folder_name: str) -> Optional[str]:
        """Get folder ID by well-known name or display name"""
        folder_name_lower = folder_name.lower()

        # First try well-known folder names
        for folder_id, info in self.folder_map.items():
            if info['display_name_lower'] == folder_name_lower:
                return folder_id

        # Try partial match for well-known folders
        well_known_mappings = {
            'inbox': ['inbox'],
            'sentitems': ['sent', 'sent items', 'sent mail'],
            'drafts': ['drafts', 'draft'],
            'deleteditems': ['deleted', 'trash', 'deleted items'],
            'junkemail': ['junk', 'spam', 'junk email'],
            'archive': ['archive'],
        }

        for folder_key, aliases in well_known_mappings.items():
            if folder_name_lower in aliases or any(alias in folder_name_lower for alias in aliases):
                for folder_id, info in self.folder_map.items():
                    if any(alias in info['display_name_lower'] for alias in aliases):
                        return folder_id

        return None

    def get_email_count(self) -> Optional[int]:
        """
        Get total number of emails in the configured folders

        Returns:
            Total email count or None if not available
        """
        try:
            total = 0
            for folder_name in self.folders_to_sync:
                folder_id = self._get_folder_id_by_name(folder_name)
                if folder_id and folder_id in self.folder_map:
                    total += self.folder_map[folder_id].get('messagesTotal', 0)
            return total
        except Exception:
            return None

    def extract_emails(self, max_emails: Optional[int] = None) -> Iterator[Dict]:
        """
        Extract emails from Outlook

        Uses incremental sync if delta_link is available, otherwise full sync.

        Args:
            max_emails: Maximum number of emails to extract (None = all)

        Yields:
            Standardized email dictionaries
        """
        self._mark_start()

        try:
            if self.delta_link:
                # Incremental sync - only get changes since last sync
                logger.info(f"Starting incremental sync from delta link")
                yield from self._extract_incremental(max_emails)
            else:
                # Full sync - get all emails from configured folders
                logger.info(f"Starting full sync for folders: {self.folders_to_sync}")
                yield from self._extract_full(max_emails)

        except Exception as e:
            logger.error(f"Outlook extraction failed: {e}")
            self.stats['errors'].append(str(e))
            raise
        finally:
            self._mark_end()

    def _extract_full(self, max_emails: Optional[int] = None) -> Iterator[Dict]:
        """
        Full extraction - fetch all messages from configured folders

        Args:
            max_emails: Maximum emails to extract

        Yields:
            Standardized email dictionaries
        """
        extracted = 0
        seen_message_ids = set()  # Avoid duplicates across folders

        for folder_name in self.folders_to_sync:
            folder_id = self._get_folder_id_by_name(folder_name)
            if not folder_id:
                logger.warning(f"Folder not found: {folder_name}")
                continue

            logger.info(f"Extracting from folder: {folder_name} (ID: {folder_id})")

            # Use delta endpoint to enable incremental sync later
            url = f"{self.GRAPH_BASE_URL}/me/mailFolders/{folder_id}/messages/delta"
            params = {
                '$top': self.MESSAGES_PER_REQUEST,
                '$select': 'id,subject,from,toRecipients,ccRecipients,bccRecipients,'
                          'sentDateTime,receivedDateTime,body,bodyPreview,hasAttachments,'
                          'internetMessageId,conversationId,parentFolderId,isRead,isDraft,'
                          'internetMessageHeaders'
            }

            while url:
                if max_emails and extracted >= max_emails:
                    logger.info(f"Reached max_emails limit: {max_emails}")
                    return

                try:
                    headers = self._get_auth_headers()
                    response = self._request_with_retry(url, headers, params)

                    if response is None:
                        break

                    data = response.json()
                    messages = data.get('value', [])

                    for msg in messages:
                        if max_emails and extracted >= max_emails:
                            return

                        msg_id = msg.get('id')
                        if msg_id in seen_message_ids:
                            continue
                        seen_message_ids.add(msg_id)

                        try:
                            email_dict = self._parse_outlook_message(msg, folder_name)
                            if email_dict:
                                self._update_stats(True)
                                extracted += 1
                                yield email_dict

                        except Exception as e:
                            self._update_stats(False, f"Failed to parse message {msg_id}: {e}")
                            logger.warning(f"Failed to parse message {msg_id}: {e}")

                    # Log progress
                    logger.info(f"Outlook extraction progress: {extracted} emails fetched")

                    # Store delta link for next incremental sync
                    if '@odata.deltaLink' in data:
                        self.delta_link = data['@odata.deltaLink']

                    # Get next page URL
                    url = data.get('@odata.nextLink')
                    params = None  # nextLink includes all params

                except Exception as e:
                    logger.error(f"Error fetching messages: {e}")
                    self.stats['errors'].append(str(e))
                    break

        logger.info(f"Outlook full sync completed: {extracted} emails extracted")

    def _extract_incremental(self, max_emails: Optional[int] = None) -> Iterator[Dict]:
        """
        Incremental sync using Microsoft Graph delta queries

        Args:
            max_emails: Maximum emails to extract

        Yields:
            Standardized email dictionaries
        """
        extracted = 0
        seen_message_ids = set()

        try:
            url = self.delta_link
            params = None  # Delta link includes all parameters

            while url:
                if max_emails and extracted >= max_emails:
                    logger.info(f"Reached max_emails limit: {max_emails}")
                    return

                headers = self._get_auth_headers()
                response = self._request_with_retry(url, headers, params)

                if response is None:
                    break

                data = response.json()
                messages = data.get('value', [])

                for msg in messages:
                    if max_emails and extracted >= max_emails:
                        return

                    # Skip deleted messages (marked with @removed)
                    if '@removed' in msg:
                        continue

                    msg_id = msg.get('id')
                    if msg_id in seen_message_ids:
                        continue
                    seen_message_ids.add(msg_id)

                    try:
                        # Get folder name for the message
                        folder_id = msg.get('parentFolderId')
                        folder_name = self._get_folder_name_by_id(folder_id)

                        email_dict = self._parse_outlook_message(msg, folder_name)
                        if email_dict:
                            self._update_stats(True)
                            extracted += 1
                            yield email_dict

                    except Exception as e:
                        self._update_stats(False, str(e))
                        logger.warning(f"Failed to parse message {msg_id}: {e}")

                # Update delta link
                if '@odata.deltaLink' in data:
                    self.delta_link = data['@odata.deltaLink']

                # Get next page
                url = data.get('@odata.nextLink')

            logger.info(f"Outlook incremental sync completed: {extracted} new emails")

        except requests.exceptions.HTTPError as e:
            # If delta link expired, fall back to full sync
            if e.response and e.response.status_code in [400, 404, 410]:
                logger.warning(f"Delta link expired or invalid, falling back to full sync: {e}")
                self.delta_link = None
                yield from self._extract_full(max_emails)
            else:
                raise

    def _request_with_retry(
        self,
        url: str,
        headers: Dict,
        params: Optional[Dict] = None
    ) -> Optional[requests.Response]:
        """
        Make HTTP request with retry logic

        Args:
            url: Request URL
            headers: Request headers
            params: Query parameters

        Returns:
            Response object or None if all retries failed
        """
        for attempt in range(self.MAX_RETRIES):
            try:
                response = requests.get(url, headers=headers, params=params)

                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 60))
                    logger.warning(f"Rate limited, waiting {retry_after}s...")
                    time.sleep(retry_after)
                    continue

                # Handle token expiration
                if response.status_code == 401:
                    if self._refresh_access_token():
                        headers = self._get_auth_headers()
                        continue
                    else:
                        raise RuntimeError("Token refresh failed")

                response.raise_for_status()
                return response

            except Exception as e:
                if attempt < self.MAX_RETRIES - 1:
                    wait_time = self.RETRY_DELAY * (2 ** attempt)
                    logger.warning(f"Retry {attempt + 1}/{self.MAX_RETRIES}, waiting {wait_time}s: {e}")
                    time.sleep(wait_time)
                else:
                    raise

        return None

    def _get_folder_name_by_id(self, folder_id: str) -> str:
        """Get folder display name by ID"""
        if folder_id in self.folder_map:
            return self.folder_map[folder_id]['name']
        return 'Unknown'

    def _parse_outlook_message(self, msg: Dict, folder_name: str) -> Optional[Dict]:
        """
        Parse Outlook message to standardized format

        Args:
            msg: Microsoft Graph message dict
            folder_name: Folder display name

        Returns:
            Standardized email dict or None if parsing fails
        """
        try:
            # Extract sender info
            from_data = msg.get('from', {}).get('emailAddress', {})
            sender_email = from_data.get('address', '')
            sender_name = from_data.get('name', '')

            # Parse recipients
            recipients = self._parse_recipients(msg.get('toRecipients', []))
            cc_list = self._parse_recipients(msg.get('ccRecipients', []))
            bcc_list = self._parse_recipients(msg.get('bccRecipients', []))

            # Extract body
            body_data = msg.get('body', {})
            body_content = body_data.get('content', '')
            body_type = body_data.get('contentType', 'text').lower()

            if body_type == 'html':
                body_html = body_content
                # Extract plain text from HTML for search indexing
                body_text = self._html_to_text(body_content)
            else:
                body_text = body_content
                body_html = ''

            # Parse dates
            sent_date = self._parse_outlook_date(msg.get('sentDateTime'))
            received_date = self._parse_outlook_date(msg.get('receivedDateTime'))

            # Determine if outbound
            is_outbound = self._is_outbound_message(folder_name, sender_email)

            # Extract internet headers if available
            raw_headers = {}
            internet_headers = msg.get('internetMessageHeaders', [])
            for header in internet_headers:
                raw_headers[header.get('name', '')] = header.get('value', '')

            # Build raw email dict
            raw_email = {
                'message_id': msg.get('internetMessageId', msg.get('id', '')),
                'subject': msg.get('subject', ''),
                'sender_email': sender_email,
                'sender_name': sender_name,
                'recipients': recipients,
                'cc_list': cc_list,
                'bcc_list': bcc_list,
                'sent_date': sent_date,
                'received_date': received_date,
                'body_text': body_text,
                'body_html': body_html,
                'folder_path': folder_name,
                'is_outbound': is_outbound,
                'is_reply': self._is_reply_subject(msg.get('subject', '')),
                'raw_headers': raw_headers,
                'in_reply_to': raw_headers.get('In-Reply-To', ''),
                'references': raw_headers.get('References', ''),
                'attachments': self._extract_attachment_metadata(msg),
                'outlook_id': msg.get('id'),  # Keep Outlook's ID for reference
                'outlook_conversation_id': msg.get('conversationId'),
            }

            return self._standardize_email(raw_email)

        except Exception as e:
            logger.warning(f"Failed to parse Outlook message: {e}")
            return None

    def _parse_recipients(self, recipients: List[Dict]) -> List[Dict]:
        """Parse Outlook recipient list to standard format"""
        result = []
        for recipient in recipients:
            email_address = recipient.get('emailAddress', {})
            result.append({
                'email': (email_address.get('address', '') or '').lower(),
                'name': email_address.get('name', '')
            })
        return result

    def _parse_outlook_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse Outlook ISO 8601 date string"""
        if not date_str:
            return None

        try:
            # Microsoft Graph returns ISO 8601 format with 'Z' suffix
            if date_str.endswith('Z'):
                date_str = date_str[:-1] + '+00:00'
            return datetime.fromisoformat(date_str)
        except Exception:
            try:
                from dateutil import parser
                return parser.parse(date_str)
            except Exception:
                return None

    def _is_outbound_message(self, folder_name: str, sender_email: str) -> bool:
        """Determine if message is outbound (sent by user)"""
        # Check if in Sent folder
        folder_lower = folder_name.lower()
        if 'sent' in folder_lower or 'outbox' in folder_lower:
            return True

        # Check if sender matches user email
        if self.user_email and sender_email:
            if sender_email.lower() == self.user_email.lower():
                return True

        return False

    def _extract_attachment_metadata(self, msg: Dict) -> List[Dict]:
        """Extract attachment metadata from message"""
        if not msg.get('hasAttachments'):
            return []

        # Note: Full attachment data requires separate API call
        # For now, just indicate attachments exist
        # Could be enhanced to fetch attachment details if needed
        return [{'filename': 'attachment', 'size': 0, 'mime_type': 'application/octet-stream'}] \
            if msg.get('hasAttachments') else []

    def get_current_delta_link(self) -> Optional[str]:
        """
        Get current delta link for incremental sync

        Returns:
            Current delta link or None
        """
        return self.delta_link

    def get_refreshed_tokens(self) -> Optional[Dict]:
        """
        Get refreshed tokens if they were refreshed during connection

        Returns:
            Dict with tokens if refreshed, None otherwise
        """
        if self.tokens_refreshed:
            result = {'access_token': self.access_token}
            if hasattr(self, '_new_refresh_token') and self._new_refresh_token:
                result['refresh_token'] = self._new_refresh_token
            return result
        return None

    def extract_emails_by_date_range(
        self,
        start_date: str,
        end_date: str,
        max_emails: Optional[int] = None
    ) -> Iterator[Dict]:
        """
        Extract emails from Outlook within a specific date range.

        Uses Microsoft Graph $filter query syntax.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            max_emails: Maximum emails to extract (None = all in range)

        Yields:
            Standardized email dictionaries
        """
        self._mark_start()

        # Format filter for date range
        # receivedDateTime ge 2024-01-01T00:00:00Z and receivedDateTime lt 2024-02-01T00:00:00Z
        filter_query = (
            f"receivedDateTime ge {start_date}T00:00:00Z and "
            f"receivedDateTime lt {end_date}T23:59:59Z"
        )

        logger.info(f"Starting date range extraction with filter: {filter_query}")

        extracted = 0
        seen_message_ids = set()

        try:
            # Search across all folders
            url = f"{self.GRAPH_BASE_URL}/me/messages"
            params = {
                '$top': self.MESSAGES_PER_REQUEST,
                '$filter': filter_query,
                '$orderby': 'receivedDateTime desc',
                '$select': 'id,subject,from,toRecipients,ccRecipients,bccRecipients,'
                          'sentDateTime,receivedDateTime,body,bodyPreview,hasAttachments,'
                          'internetMessageId,conversationId,parentFolderId,isRead,isDraft,'
                          'internetMessageHeaders'
            }

            while url:
                if max_emails and extracted >= max_emails:
                    logger.info(f"Reached max_emails limit: {max_emails}")
                    return

                headers = self._get_auth_headers()
                response = self._request_with_retry(url, headers, params)

                if response is None:
                    break

                data = response.json()
                messages = data.get('value', [])

                if not messages:
                    break

                for msg in messages:
                    if max_emails and extracted >= max_emails:
                        return

                    msg_id = msg.get('id')
                    if msg_id in seen_message_ids:
                        continue
                    seen_message_ids.add(msg_id)

                    try:
                        folder_id = msg.get('parentFolderId')
                        folder_name = self._get_folder_name_by_id(folder_id)

                        email_dict = self._parse_outlook_message(msg, folder_name)
                        if email_dict:
                            self._update_stats(True)
                            extracted += 1
                            yield email_dict

                    except Exception as e:
                        self._update_stats(False, f"Failed to parse message {msg_id}: {e}")
                        logger.warning(f"Failed to parse message {msg_id}: {e}")

                # Log progress
                logger.info(f"Date range extraction progress: {extracted} emails fetched")

                # Get next page URL
                url = data.get('@odata.nextLink')
                params = None  # nextLink includes all params

        except Exception as e:
            logger.error(f"Date range extraction failed: {e}")
            self.stats['errors'].append(str(e))
            raise
        finally:
            self._mark_end()

        logger.info(f"Date range extraction completed: {extracted} emails from {start_date} to {end_date}")

    def disconnect(self) -> None:
        """Clean up Outlook connection"""
        self.access_token = None
        self.refresh_token = None
        self.folder_map = {}
        logger.info("Outlook extractor disconnected")

    def _html_to_text(self, html_content: str) -> str:
        """Convert HTML to plain text for search indexing and fallback display"""
        if not html_content:
            return ''

        # Strip HTML tags
        text = re.sub(r'<style[^>]*>.*?</style>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        # Decode HTML entities
        text = re.sub(r'&nbsp;', ' ', text)
        text = re.sub(r'&amp;', '&', text)
        text = re.sub(r'&lt;', '<', text)
        text = re.sub(r'&gt;', '>', text)
        text = re.sub(r'&quot;', '"', text)
        text = re.sub(r'&#39;', "'", text)
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
