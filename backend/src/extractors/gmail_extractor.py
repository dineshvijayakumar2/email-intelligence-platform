"""
Gmail Extractor - LIVE Email Sync via Gmail API

This extractor fetches emails directly from Gmail using the Google Gmail API.
Unlike file-based extractors (MBOX, PST, OLM), this works with live mailboxes.

Key Features:
- OAuth2 authentication with user tokens
- Incremental sync using Gmail's historyId
- Label-to-folder mapping for consistency
- Rate limiting: 100 messages per request, 10,000 queries/day/user
- Full and incremental sync modes

Gmail API Reference:
https://developers.google.com/gmail/api/reference/rest
"""

from typing import Iterator, Dict, Optional, List, Any
from datetime import datetime, timezone
import logging
import base64
import os
import re
import time

from .base_extractor import BaseExtractor

logger = logging.getLogger(__name__)


class GmailExtractor(BaseExtractor):
    """
    Extract emails from Gmail via Google Gmail API

    Implements BaseExtractor contract for LIVE email sync.
    """

    # Gmail API configuration
    MESSAGES_PER_REQUEST = 100  # Max 500, but 100 is safer for rate limits
    MAX_RETRIES = 3
    RETRY_DELAY = 2  # seconds

    # Gmail system labels
    SYSTEM_LABELS = {
        'INBOX': 'Inbox',
        'SENT': 'Sent',
        'DRAFT': 'Drafts',
        'SPAM': 'Spam',
        'TRASH': 'Trash',
        'STARRED': 'Starred',
        'IMPORTANT': 'Important',
        'CATEGORY_PERSONAL': 'Personal',
        'CATEGORY_SOCIAL': 'Social',
        'CATEGORY_PROMOTIONS': 'Promotions',
        'CATEGORY_UPDATES': 'Updates',
        'CATEGORY_FORUMS': 'Forums',
    }

    def __init__(self, connection_config: Dict[str, Any] = None):
        """
        Initialize Gmail extractor

        Args:
            connection_config: Dict containing:
                - user_id: User ID for token lookup
                - access_token: Current access token
                - refresh_token: Refresh token for renewal
                - history_id: Last history ID for incremental sync (optional)
                - labels: List of labels to sync (default: ['INBOX', 'SENT'])
                - mailbox_id: Associated mailbox ID for the email records
        """
        config = connection_config or {}
        super().__init__(config)

        self.source_type = "gmail"
        self.user_id = config.get('user_id')
        self.access_token = config.get('access_token')
        self.refresh_token = config.get('refresh_token')
        self.last_history_id = config.get('history_id')
        self.labels_to_sync = config.get('labels', ['INBOX', 'SENT'])
        self.mailbox_id = config.get('mailbox_id')

        # Gmail API service
        self.service = None
        self.user_email = None
        self.label_map = {}  # Maps label IDs to label info

        # Token management
        self.credentials = None
        self.tokens_refreshed = False

        logger.info(f"GmailExtractor initialized for user: {self.user_id}, labels: {self.labels_to_sync}")

    def connect(self, **kwargs) -> bool:
        """
        Connect to Gmail API using OAuth2 tokens

        Returns:
            True if connection successful
        """
        try:
            # Import Google API libraries
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            from google.auth.transport.requests import Request

            if not self.access_token:
                raise ValueError("No access token provided")

            # Build credentials from tokens
            self.credentials = Credentials(
                token=self.access_token,
                refresh_token=self.refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=os.getenv("GOOGLE_CLIENT_ID"),
                client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
                scopes=[
                    'https://www.googleapis.com/auth/gmail.readonly',
                    'https://www.googleapis.com/auth/gmail.settings.basic'
                ]
            )

            # Refresh if expired
            if self.credentials.expired and self.credentials.refresh_token:
                logger.info("Access token expired, refreshing...")
                self.credentials.refresh(Request())
                self.access_token = self.credentials.token
                self.tokens_refreshed = True
                logger.info("Token refreshed successfully")

            # Build Gmail service
            self.service = build('gmail', 'v1', credentials=self.credentials)

            # Get user profile to verify connection
            profile = self.service.users().getProfile(userId='me').execute()
            self.user_email = profile.get('emailAddress')

            logger.info(f"Connected to Gmail as: {self.user_email}")

            # Load label mappings
            self._load_labels()

            return True

        except Exception as e:
            logger.error(f"Failed to connect to Gmail: {e}")
            return False

    def _load_labels(self):
        """Load and cache Gmail label mappings"""
        try:
            results = self.service.users().labels().list(userId='me').execute()
            labels = results.get('labels', [])

            for label in labels:
                self.label_map[label['id']] = {
                    'id': label['id'],
                    'name': label['name'],
                    'type': label.get('type', 'user'),  # system or user
                    'messagesTotal': label.get('messagesTotal', 0),
                    'messagesUnread': label.get('messagesUnread', 0),
                }

            logger.info(f"Loaded {len(self.label_map)} Gmail labels")

        except Exception as e:
            logger.warning(f"Failed to load labels: {e}")

    def get_folders(self) -> List[Dict]:
        """
        Get Gmail labels as folders

        Returns:
            List of folder dicts compatible with BaseExtractor contract
        """
        if not self.service:
            return []

        folders = []
        for label_id, label_info in self.label_map.items():
            # Map Gmail labels to folder types
            folder_type = self._get_folder_type(label_id, label_info['name'])

            folders.append({
                'id': label_id,
                'name': label_info['name'],
                'path': self._get_folder_path(label_info['name']),
                'message_count': label_info.get('messagesTotal', 0),
                'type': folder_type
            })

        return folders

    def _get_folder_type(self, label_id: str, label_name: str) -> str:
        """Map Gmail label to folder type"""
        type_mapping = {
            'INBOX': 'inbox',
            'SENT': 'sent',
            'DRAFT': 'drafts',
            'SPAM': 'spam',
            'TRASH': 'trash',
            'STARRED': 'flagged',
            'IMPORTANT': 'important',
        }
        return type_mapping.get(label_id, 'user')

    def _get_folder_path(self, label_name: str) -> str:
        """Convert Gmail label name to folder path"""
        # Gmail uses "/" for nested labels
        # Convert to consistent format
        if label_name in self.SYSTEM_LABELS:
            return self.SYSTEM_LABELS[label_name]
        return label_name

    def get_email_count(self) -> Optional[int]:
        """
        Get total number of emails in the configured labels

        Returns:
            Total email count or None if not available
        """
        if not self.service:
            return None

        try:
            total = 0
            for label_id in self.labels_to_sync:
                if label_id in self.label_map:
                    total += self.label_map[label_id].get('messagesTotal', 0)
            return total
        except Exception:
            return None

    def extract_emails(self, max_emails: Optional[int] = None) -> Iterator[Dict]:
        """
        Extract emails from Gmail

        Uses incremental sync if history_id is available, otherwise full sync.

        Args:
            max_emails: Maximum number of emails to extract (None = all)

        Yields:
            Standardized email dictionaries
        """
        if not self.service:
            raise RuntimeError("Not connected. Call connect() first.")

        self._mark_start()

        try:
            if self.last_history_id:
                # Incremental sync - only get changes since last sync
                logger.info(f"Starting incremental sync from history ID: {self.last_history_id}")
                yield from self._extract_incremental(max_emails)
            else:
                # Full sync - get all emails from configured labels
                logger.info(f"Starting full sync for labels: {self.labels_to_sync}")
                yield from self._extract_full(max_emails)

        except Exception as e:
            logger.error(f"Gmail extraction failed: {e}")
            self.stats['errors'].append(str(e))
            raise
        finally:
            self._mark_end()

    def _extract_full(self, max_emails: Optional[int] = None) -> Iterator[Dict]:
        """
        Full extraction - fetch all messages from configured labels

        Args:
            max_emails: Maximum emails to extract

        Yields:
            Standardized email dictionaries
        """
        extracted = 0
        page_token = None

        while True:
            try:
                # List messages from configured labels
                results = self.service.users().messages().list(
                    userId='me',
                    labelIds=self.labels_to_sync,
                    maxResults=min(self.MESSAGES_PER_REQUEST, max_emails - extracted if max_emails else self.MESSAGES_PER_REQUEST),
                    pageToken=page_token
                ).execute()

                messages = results.get('messages', [])

                if not messages:
                    break

                for msg_ref in messages:
                    if max_emails and extracted >= max_emails:
                        logger.info(f"Reached max_emails limit: {max_emails}")
                        return

                    try:
                        # Fetch full message with retry
                        msg = self._get_message_with_retry(msg_ref['id'])

                        if msg:
                            email_dict = self._parse_gmail_message(msg)
                            if email_dict:
                                self._update_stats(True)
                                extracted += 1
                                yield email_dict

                    except Exception as e:
                        self._update_stats(False, f"Failed to fetch message {msg_ref['id']}: {e}")
                        logger.warning(f"Failed to parse message {msg_ref['id']}: {e}")

                # Log progress every batch
                logger.info(f"Gmail extraction progress: {extracted} emails fetched")

                page_token = results.get('nextPageToken')
                if not page_token:
                    break

            except Exception as e:
                logger.error(f"Error listing messages: {e}")
                self.stats['errors'].append(str(e))
                # Try to continue with next page if possible
                if 'rateLimitExceeded' in str(e):
                    logger.warning("Rate limit hit, waiting 60s...")
                    time.sleep(60)
                else:
                    raise

        logger.info(f"Gmail full sync completed: {extracted} emails extracted")

    def _extract_incremental(self, max_emails: Optional[int] = None) -> Iterator[Dict]:
        """
        Incremental sync using Gmail history API

        Syncs all configured labels (INBOX, SENT, etc.)

        Args:
            max_emails: Maximum emails to extract

        Yields:
            Standardized email dictionaries
        """
        extracted = 0
        seen_message_ids = set()  # Track seen messages to avoid duplicates

        try:
            # Get history for each configured label
            for label_id in self.labels_to_sync:
                logger.info(f"Checking incremental sync for label: {label_id}")
                page_token = None

                while True:
                    results = self.service.users().history().list(
                        userId='me',
                        startHistoryId=self.last_history_id,
                        historyTypes=['messageAdded'],
                        labelId=label_id,  # Sync each configured label
                        pageToken=page_token
                    ).execute()

                    history = results.get('history', [])

                    for record in history:
                        messages_added = record.get('messagesAdded', [])

                        for msg_added in messages_added:
                            if max_emails and extracted >= max_emails:
                                return

                            msg_ref = msg_added.get('message', {})
                            msg_id = msg_ref.get('id')

                            # Skip if we've already processed this message (avoids duplicates across labels)
                            if msg_id in seen_message_ids:
                                continue
                            seen_message_ids.add(msg_id)

                            try:
                                msg = self._get_message_with_retry(msg_id)

                                if msg:
                                    email_dict = self._parse_gmail_message(msg)
                                    if email_dict:
                                        self._update_stats(True)
                                        extracted += 1
                                        yield email_dict

                            except Exception as e:
                                self._update_stats(False, str(e))
                                logger.warning(f"Failed to fetch message {msg_id}: {e}")

                    page_token = results.get('nextPageToken')
                    if not page_token:
                        break

            logger.info(f"Gmail incremental sync completed: {extracted} new emails from labels {self.labels_to_sync}")

        except Exception as e:
            error_str = str(e).lower()

            # If history is too old or invalid, fall back to full sync
            if 'historyid' in error_str or 'invalid' in error_str or 'notfound' in error_str:
                logger.warning(f"History ID expired or invalid, falling back to full sync: {e}")
                self.last_history_id = None
                yield from self._extract_full(max_emails)
            else:
                raise

    def _get_message_with_retry(self, message_id: str) -> Optional[Dict]:
        """
        Fetch a message with retry logic

        Args:
            message_id: Gmail message ID

        Returns:
            Message dict or None if all retries failed
        """
        for attempt in range(self.MAX_RETRIES):
            try:
                msg = self.service.users().messages().get(
                    userId='me',
                    id=message_id,
                    format='full'
                ).execute()
                return msg

            except Exception as e:
                if attempt < self.MAX_RETRIES - 1:
                    wait_time = self.RETRY_DELAY * (2 ** attempt)
                    logger.warning(f"Retry {attempt + 1}/{self.MAX_RETRIES} for message {message_id}, waiting {wait_time}s")
                    time.sleep(wait_time)
                else:
                    raise

        return None

    def _parse_gmail_message(self, msg: Dict) -> Optional[Dict]:
        """
        Parse Gmail message to standardized format

        Args:
            msg: Gmail message dict from API

        Returns:
            Standardized email dict or None if parsing fails
        """
        try:
            payload = msg.get('payload', {})
            headers = self._parse_headers(payload.get('headers', []))

            # Extract body
            body_text, body_html = self._extract_body(payload)

            # Get labels and determine folder
            label_ids = msg.get('labelIds', [])
            folder_path = self._get_folder_from_labels(label_ids)

            # Determine if outbound
            is_outbound = self._is_outbound_message(label_ids, headers)

            # Parse dates
            sent_date = self._parse_email_date(headers.get('Date'))
            received_date = self._parse_internal_date(msg.get('internalDate'))

            # Build raw email dict
            raw_email = {
                'message_id': headers.get('Message-ID', headers.get('Message-Id', msg.get('id', ''))),
                'subject': headers.get('Subject', ''),
                'sender_email': self._extract_email_from_field(headers.get('From', '')),
                'sender_name': self._extract_name_from_field(headers.get('From', '')),
                'recipients': self._parse_address_list(headers.get('To', '')),
                'cc_list': self._parse_address_list(headers.get('Cc', '')),
                'bcc_list': self._parse_address_list(headers.get('Bcc', '')),
                'sent_date': sent_date,
                'received_date': received_date,
                'body_text': body_text,
                'body_html': body_html,
                'folder_path': folder_path,
                'is_outbound': is_outbound,
                'is_reply': self._is_reply_subject(headers.get('Subject', '')),
                'raw_headers': headers,
                'in_reply_to': headers.get('In-Reply-To', ''),
                'references': headers.get('References', ''),
                'attachments': self._extract_attachments(payload),
                'gmail_id': msg.get('id'),  # Keep Gmail's ID for reference
                'gmail_thread_id': msg.get('threadId'),
            }

            return self._standardize_email(raw_email)

        except Exception as e:
            logger.warning(f"Failed to parse Gmail message: {e}")
            return None

    def _parse_headers(self, headers_list: List[Dict]) -> Dict[str, str]:
        """Convert Gmail's header list to dict"""
        return {h['name']: h['value'] for h in headers_list}

    def _extract_body(self, payload: Dict) -> tuple:
        """
        Extract text and HTML body from Gmail payload

        Args:
            payload: Gmail message payload

        Returns:
            Tuple of (text_body, html_body)
        """
        text_body = ''
        html_body = ''

        def process_part(part):
            nonlocal text_body, html_body

            mime_type = part.get('mimeType', '')
            body = part.get('body', {})
            data = body.get('data', '')

            if data:
                try:
                    decoded = base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')

                    if mime_type == 'text/plain' and not text_body:
                        text_body = decoded
                    elif mime_type == 'text/html' and not html_body:
                        html_body = decoded
                except Exception as e:
                    logger.debug(f"Failed to decode body part: {e}")

            # Process nested parts (multipart messages)
            for sub_part in part.get('parts', []):
                process_part(sub_part)

        process_part(payload)
        return text_body, html_body

    def _get_folder_from_labels(self, label_ids: List[str]) -> str:
        """
        Convert Gmail labels to folder path

        Priority: User labels > System labels (INBOX)
        """
        user_labels = []
        system_label = 'INBOX'

        for label_id in label_ids:
            if label_id in self.label_map:
                label_info = self.label_map[label_id]
                if label_info.get('type') == 'user':
                    user_labels.append(label_info['name'])
                elif label_id in ['INBOX', 'SENT', 'DRAFT', 'SPAM', 'TRASH']:
                    system_label = self.SYSTEM_LABELS.get(label_id, label_id)

        # Prefer user labels if available
        if user_labels:
            return user_labels[0]
        return system_label

    def _is_outbound_message(self, label_ids: List[str], headers: Dict) -> bool:
        """Determine if message is outbound (sent by user)"""
        # Check SENT label
        if 'SENT' in label_ids:
            return True

        # Check From header matches user email
        if self.user_email:
            from_field = headers.get('From', '').lower()
            if self.user_email.lower() in from_field:
                return True

        return False

    def _parse_email_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse email Date header to datetime"""
        if not date_str:
            return None

        try:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(date_str)
        except Exception:
            try:
                # Fallback: try parsing common formats
                from dateutil import parser
                return parser.parse(date_str)
            except Exception:
                return None

    def _parse_internal_date(self, ms_timestamp: str) -> Optional[datetime]:
        """Parse Gmail's internalDate (milliseconds since epoch)"""
        if not ms_timestamp:
            return None
        try:
            return datetime.fromtimestamp(int(ms_timestamp) / 1000, tz=timezone.utc)
        except Exception:
            return None

    def _extract_email_from_field(self, field: str) -> str:
        """Extract email address from 'Name <email>' format"""
        if not field:
            return ''

        # Try to extract email from angle brackets
        match = re.search(r'<([^>]+)>', field)
        if match:
            return match.group(1).lower().strip()

        # No brackets, might be just email
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', field)
        if email_match:
            return email_match.group(0).lower().strip()

        return field.lower().strip()

    def _extract_name_from_field(self, field: str) -> str:
        """Extract display name from 'Name <email>' format"""
        if not field:
            return ''

        # Remove email in brackets
        if '<' in field:
            name = field.split('<')[0].strip()
            # Remove quotes
            return name.strip('"\'')

        return ''

    def _parse_address_list(self, field: str) -> List[Dict]:
        """Parse comma-separated address list"""
        if not field:
            return []

        recipients = []
        # Split by comma, but respect quoted strings
        parts = re.split(r',\s*(?=(?:[^"]*"[^"]*")*[^"]*$)', field)

        for part in parts:
            part = part.strip()
            if part:
                recipients.append({
                    'email': self._extract_email_from_field(part),
                    'name': self._extract_name_from_field(part)
                })

        return recipients

    def _extract_attachments(self, payload: Dict) -> List[Dict]:
        """Extract attachment metadata from payload"""
        attachments = []

        def process_part(part):
            filename = part.get('filename', '')
            if filename:
                body = part.get('body', {})
                attachments.append({
                    'id': body.get('attachmentId', ''),
                    'filename': filename,
                    'size': body.get('size', 0),
                    'mime_type': part.get('mimeType', 'application/octet-stream')
                })

            for sub_part in part.get('parts', []):
                process_part(sub_part)

        process_part(payload)
        return attachments

    def get_current_history_id(self) -> Optional[str]:
        """
        Get current history ID for incremental sync

        Returns:
            Current history ID or None
        """
        if not self.service:
            return None

        try:
            profile = self.service.users().getProfile(userId='me').execute()
            return profile.get('historyId')
        except Exception as e:
            logger.warning(f"Failed to get history ID: {e}")
            return None

    def get_refreshed_tokens(self) -> Optional[Dict]:
        """
        Get refreshed tokens if they were refreshed during connection

        Returns:
            Dict with access_token if refreshed, None otherwise
        """
        if self.tokens_refreshed and self.credentials:
            return {
                'access_token': self.credentials.token,
            }
        return None

    def extract_emails_by_date_range(
        self,
        start_date: str,
        end_date: str,
        max_emails: Optional[int] = None
    ) -> Iterator[Dict]:
        """
        Extract emails from Gmail within a specific date range.

        Uses Gmail's search query syntax to filter by date.

        Args:
            start_date: Start date in YYYY-MM-DD or YYYY/MM/DD format
            end_date: End date in YYYY-MM-DD or YYYY/MM/DD format
            max_emails: Maximum emails to extract (None = all in range)

        Yields:
            Standardized email dictionaries
        """
        if not self.service:
            raise RuntimeError("Not connected. Call connect() first.")

        self._mark_start()

        # Format dates for Gmail query (YYYY/MM/DD format)
        start_formatted = start_date.replace('-', '/')
        end_formatted = end_date.replace('-', '/')

        # Gmail search query for date range
        # after: is inclusive, before: is exclusive
        query = f"after:{start_formatted} before:{end_formatted}"

        logger.info(f"Starting date range extraction with query: {query}")

        extracted = 0
        page_token = None

        try:
            while True:
                # List messages matching the date range query
                # Note: Don't filter by labelIds here - we want ALL emails in the date range
                # regardless of which folder/label they're in
                results = self.service.users().messages().list(
                    userId='me',
                    q=query,
                    maxResults=min(
                        self.MESSAGES_PER_REQUEST,
                        max_emails - extracted if max_emails else self.MESSAGES_PER_REQUEST
                    ),
                    pageToken=page_token
                ).execute()

                messages = results.get('messages', [])

                if not messages:
                    break

                for msg_ref in messages:
                    if max_emails and extracted >= max_emails:
                        logger.info(f"Reached max_emails limit: {max_emails}")
                        return

                    try:
                        # Fetch full message with retry
                        msg = self._get_message_with_retry(msg_ref['id'])

                        if msg:
                            email_dict = self._parse_gmail_message(msg)
                            if email_dict:
                                self._update_stats(True)
                                extracted += 1
                                yield email_dict

                    except Exception as e:
                        self._update_stats(False, f"Failed to fetch message {msg_ref['id']}: {e}")
                        logger.warning(f"Failed to parse message {msg_ref['id']}: {e}")

                # Log progress
                logger.info(f"Date range extraction progress: {extracted} emails fetched")

                page_token = results.get('nextPageToken')
                if not page_token:
                    break

        except Exception as e:
            logger.error(f"Date range extraction failed: {e}")
            self.stats['errors'].append(str(e))
            raise
        finally:
            self._mark_end()

        logger.info(f"Date range extraction completed: {extracted} emails from {start_date} to {end_date}")

    def disconnect(self) -> None:
        """Clean up Gmail connection"""
        self.service = None
        self.credentials = None
        self.label_map = {}
        logger.info("Gmail extractor disconnected")
