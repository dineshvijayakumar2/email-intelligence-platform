"""
MBOX Extractor - Universal Email Archive Format

MBOX is a plain-text format where all emails in a folder are stored sequentially
in a single file. Each message starts with "From " line.

Streaming Strategy:
- Read file line-by-line (no full load into memory)
- Parse messages on-the-fly using Python's email library
- Generator pattern for memory efficiency
- Can handle multi-GB MBOX files

Format quirks:
- No native folder structure (single file)
- Folder hierarchy can be inferred from Gmail labels (X-Gmail-Labels header)
- Encoding can vary (UTF-8, Latin-1, etc.) - robust decoding needed
"""

from email import message_from_string
from email.header import decode_header
from email.utils import parsedate_tz, mktime_tz
from typing import Iterator, Dict, Optional, List
from datetime import datetime, timezone
import logging
import re

from .base_extractor import BaseExtractor

logger = logging.getLogger(__name__)


class MBOXExtractor(BaseExtractor):
    """
    Extract emails from MBOX format files

    Reference implementation following the clean BaseExtractor contract.
    """

    def __init__(self, connection_config: Dict):
        """
        Initialize MBOX extractor

        Args:
            connection_config: Dict containing 'file_path' key
        """
        super().__init__(connection_config)
        self.source_type = "mbox"  # Set format type
        self.file_path = connection_config.get('file_path')

        # Support Google Drive files
        self.google_drive_file_id = connection_config.get('google_drive_file_id')
        self.google_drive_file_name = connection_config.get('google_drive_file_name')

        # Check if we have either local file path or Google Drive info
        if not self.file_path and not self.google_drive_file_id:
            raise ValueError("Either 'file_path' or 'google_drive_file_id' required in connection_config")

        # Determine if this is a Google Drive file
        self.is_google_drive = bool(self.google_drive_file_id)
        if self.is_google_drive:
            logger.info(f"🌟 MBOX extractor configured for Google Drive file: {self.google_drive_file_name}")
        else:
            logger.info(f"📁 MBOX extractor configured for local file: {self.file_path}")

        self.mbox = None
        self.message_count = 0  # Track count during extraction

        # Google Drive streaming components
        self.drive_stream = None  # Will hold GoogleDriveTextStream for remote files
        self.drive_client = None  # Google Drive client for authentication

    def connect(self, access_token: Optional[str] = None, **kwargs) -> bool:
        """
        Open MBOX file or initialize streaming from Google Drive

        Args:
            access_token: Google Drive OAuth2 access token (if needed for Google Drive files)

        Returns:
            True if connection successful
        """
        try:
            # For Google Drive files, set up streaming (like OLM does)
            if self.is_google_drive:
                logger.info(f"🌟 Processing Google Drive MBOX file: {self.google_drive_file_name}")

                # Check for local mount first
                effective_path = self.get_effective_file_path(access_token)

                if effective_path == 'GOOGLE_DRIVE_STREAM':
                    # No local mount found - use streaming approach
                    logger.info(f"🌊 No local mount found, streaming MBOX file from Google Drive...")

                    # Get Google Drive file details
                    google_file_id = self.config.get('google_drive_file_id')
                    google_file_name = self.config.get('google_drive_file_name', 'Unknown MBOX')
                    user_id = self.config.get('user_id')

                    if not google_file_id:
                        raise ValueError("Google Drive file ID not provided")

                    # Import here to avoid circular imports
                    from ..storage.google_drive_client import create_google_drive_client
                    from ..storage.google_drive_text_stream import GoogleDriveTextStream

                    # Create client and authenticate
                    self.drive_client = create_google_drive_client()
                    authenticated = False

                    # Try user token authentication first
                    if user_id:
                        logger.info("Authenticating with user's stored Google Drive tokens...")
                        try:
                            from ..database.supabase_client import SupabaseClient
                            supabase = SupabaseClient.get_client(use_service_key=True)

                            result = supabase.table('user_integrations').select('access_token,refresh_token').eq('user_id', user_id).eq('provider', 'google_drive').execute()

                            if result.data:
                                user_tokens = result.data[0]
                                if self.drive_client.authenticate_with_user_tokens(
                                    user_tokens['access_token'],
                                    user_tokens['refresh_token']
                                ):
                                    authenticated = True
                                    logger.info("✅ Authenticated with user's Google Drive tokens")

                                    # Update tokens if refreshed
                                    current_tokens = self.drive_client.get_current_tokens()
                                    if current_tokens and current_tokens['access_token'] != user_tokens['access_token']:
                                        supabase.table('user_integrations').update({
                                            'access_token': current_tokens['access_token']
                                        }).eq('user_id', user_id).eq('provider', 'google_drive').execute()
                                        logger.info("Updated refreshed access token in database")
                        except Exception as e:
                            logger.warning(f"Failed to authenticate with user tokens: {e}")

                    # Fallback to service account if user auth failed
                    if not authenticated:
                        logger.info("Trying service account authentication...")
                        if self.drive_client.authenticate_with_service_account():
                            authenticated = True
                            logger.info("✅ Authenticated with service account")
                        else:
                            raise ConnectionError("Failed to authenticate with Google Drive")

                    # Get file metadata
                    file_info = self.drive_client.get_file_info(google_file_id)
                    if not file_info:
                        raise ConnectionError(f"Could not get info for Google Drive file {google_file_id}")

                    logger.info(f"📦 Opening MBOX via streaming: {file_info['name']} "
                               f"(Size: {file_info['size']:,} bytes)")

                    # Create streaming text reader
                    self.drive_stream = GoogleDriveTextStream(
                        self.drive_client.service,
                        google_file_id,
                        file_info
                    )

                    # Mark as connected via streaming
                    self.mbox = 'GOOGLE_DRIVE_STREAM'
                    logger.info(f"✅ Connected to MBOX via streaming: {file_info['name']}")
                    return True

                else:
                    # Found local mount
                    self.file_path = effective_path
                    logger.info(f"📁 Using local mount: {self.file_path}")

            # Local file path processing
            if not self.file_path:
                raise ValueError("No file path available for MBOX processing")

            # Verify file exists and is readable
            with open(self.file_path, 'r', encoding='utf-8', errors='replace') as f:
                # Just peek at first line to verify it's an MBOX
                first_line = f.readline()
                if not first_line.startswith('From '):
                    logger.warning(f"File may not be valid MBOX format: {self.file_path}")

            self.mbox = self.file_path  # Store path for later use
            logger.info(f"Connected to MBOX file: {self.file_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to MBOX file: {e}")
            if self.drive_stream:
                self.drive_stream.close()
            raise ConnectionError(f"MBOX connection failed: {e}")

    def get_email_count(self) -> Optional[int]:
        """
        Quickly count total emails in MBOX file by counting "From " lines

        This is much faster than parsing all emails, used for progress estimation.

        Returns:
            Total email count or None if count fails
        """
        if not self.file_path:
            return None

        try:
            count = 0
            logger.info(f"Counting emails in {self.file_path}...")

            with open(self.file_path, 'r', encoding='utf-8', errors='replace') as f:
                for line in f:
                    # MBOX format: each message starts with "From " (note the space)
                    if line.startswith('From '):
                        count += 1

            logger.info(f"Found {count} emails in MBOX file")
            return count

        except Exception as e:
            logger.error(f"Failed to count emails in MBOX file: {e}")
            return None

    def extract_emails(self, max_emails: Optional[int] = None) -> Iterator[Dict]:
        """
        Extract emails from MBOX file (local or streaming from Google Drive)

        Streams file line-by-line, yields standardized email dicts.
        NO date filtering - that belongs in the pipeline.

        Args:
            max_emails: Maximum number of emails to extract (None = all)

        Yields:
            Standardized email dictionaries
        """
        if not self.mbox:
            raise RuntimeError("Not connected. Call connect() first.")

        self._mark_start()
        logger.info(f"Extracting emails from MBOX (max={max_emails or 'unlimited'})...")

        try:
            extracted = 0
            self.message_count = 0

            # Determine if we're streaming from Google Drive or reading local file
            if self.mbox == 'GOOGLE_DRIVE_STREAM' and self.drive_stream:
                # Stream from Google Drive
                logger.info("🌊 Streaming MBOX content from Google Drive...")
                line_iterator = iter(self.drive_stream)
            else:
                # Read from local file
                logger.info(f"📁 Reading MBOX from local file: {self.mbox}")
                file_handle = open(self.mbox, 'r', encoding='utf-8', errors='replace')
                line_iterator = iter(file_handle)

            try:
                current_message_lines = []
                current_message_size = 0  # Track message size to limit memory
                MAX_MESSAGE_SIZE = 10 * 1024 * 1024  # 10MB limit per email (skip larger ones with attachments)
                skipped_large = 0

                for line in line_iterator:
                    # MBOX format: messages start with "From " at beginning of line
                    if line.startswith('From ') and current_message_lines:
                        # Process the previous message only if it's under size limit
                        if current_message_size <= MAX_MESSAGE_SIZE:
                            message_text = ''.join(current_message_lines)
                            email_dict = self._process_message(message_text, self.message_count)
                        else:
                            # Skip oversized email (likely has large attachments)
                            skipped_large += 1
                            if skipped_large % 100 == 1:
                                logger.info(f"Skipped {skipped_large} emails over 10MB (likely large attachments)")
                            email_dict = None

                        if email_dict:
                            self._update_stats(True)
                            extracted += 1

                            # Log progress
                            if extracted <= 10:
                                logger.info(f"📧 Email {extracted}: {email_dict.get('subject', 'No subject')[:60]}")

                            yield email_dict

                            # Check limit
                            if max_emails and extracted >= max_emails:
                                logger.info(f"Reached max_emails limit: {max_emails}")
                                break

                        # Start new message
                        current_message_lines = [line]
                        current_message_size = len(line)
                        self.message_count += 1

                        # Progress logging
                        if self.message_count % 1000 == 0:
                            logger.info(f"Scanned {self.message_count:,} messages, extracted {extracted:,} emails")

                    else:
                        # Only accumulate if under size limit
                        if current_message_size <= MAX_MESSAGE_SIZE:
                            current_message_lines.append(line)
                            current_message_size += len(line)

                    # Early exit if limit reached
                    if max_emails and extracted >= max_emails:
                        break

                # Process final message
                if current_message_lines and (not max_emails or extracted < max_emails):
                    if current_message_size <= MAX_MESSAGE_SIZE:
                        message_text = ''.join(current_message_lines)
                        email_dict = self._process_message(message_text, self.message_count)
                    else:
                        skipped_large += 1
                        logger.info(f"Skipped final email over 10MB")
                        email_dict = None

                    if email_dict:
                        self._update_stats(True)
                        extracted += 1

                        if extracted <= 10:
                            logger.info(f"📧 Email {extracted}: {email_dict.get('subject', 'No subject')[:60]}")

                        yield email_dict

            finally:
                # Close local file handle if we opened one
                if self.mbox != 'GOOGLE_DRIVE_STREAM':
                    file_handle.close()

                # Log summary of skipped large emails
                if skipped_large > 0:
                    logger.warning(f"⚠️ Skipped {skipped_large} emails over 10MB to reduce memory usage (likely large attachments)")

        except Exception as e:
            logger.error(f"MBOX extraction failed: {e}")
            raise
        finally:
            self._mark_end()

    def _process_message(self, message_text: str, idx: int) -> Optional[Dict]:
        """
        Parse and standardize a single message

        Args:
            message_text: Raw MBOX message text
            idx: Message index for source_path

        Returns:
            Standardized email dict or None if parse fails
        """
        try:
            msg = message_from_string(message_text)
            raw_email = self._parse_message(msg, idx)

            # Standardize with source path
            source_path = f"message_{idx}"
            return self._standardize_email(raw_email, source_path=source_path)

        except Exception as e:
            self._update_stats(False, str(e))
            logger.warning(f"Failed to parse message {idx}: {e}")
            return None

    def _parse_message(self, msg, idx: int) -> Dict:
        """
        Parse email.message.Message into raw email dict

        Args:
            msg: email.message.Message object
            idx: Message index

        Returns:
            Raw email dict (before standardization)
        """
        # Extract threading headers for thread_key generation
        in_reply_to = self._clean_header(msg.get('In-Reply-To', ''))
        references = self._clean_header(msg.get('References', ''))

        # Check if this is a sent message (Gmail labels)
        gmail_labels = msg.get('X-Gmail-Labels', '')
        is_sent_gmail = 'Sent' in gmail_labels or 'Outbox' in gmail_labels

        return {
            'message_id': self._clean_header(msg.get('Message-ID', f'generated-mbox-{idx}')),
            'subject': self._decode_header(msg.get('Subject', '')),
            'sender_email': self._extract_email(msg.get('From', '')),
            'sender_name': self._extract_name(msg.get('From', '')),
            'recipients': self._parse_recipients(msg.get('To', '')),
            'cc_list': self._parse_recipients(msg.get('Cc', '')),
            'bcc_list': self._parse_recipients(msg.get('Bcc', '')),
            'sent_date': self._parse_date(msg.get('Date')),
            'received_date': self._parse_date(msg.get('Received')),
            'body_text': self._get_body_text(msg),
            'body_html': self._get_body_html(msg),
            'folder_path': self._extract_folder(msg),  # From Gmail labels if available
            'is_outbound': is_sent_gmail,  # Will be further refined by normalizer
            'is_reply': self._is_reply_subject(self._decode_header(msg.get('Subject', ''))) or bool(in_reply_to),
            'raw_headers': dict(msg.items()),
            # Threading fields
            'in_reply_to': in_reply_to,
            'references': references,
            # Attachments placeholder
            'attachments': []  # TODO: Parse attachments in future
        }

    def _extract_folder(self, msg) -> str:
        """
        Extract folder path from Gmail labels or default to INBOX

        Gmail MBOX exports include X-Gmail-Labels header
        """
        gmail_labels = msg.get('X-Gmail-Labels', '')
        if gmail_labels:
            # Use first label as folder
            labels = [l.strip() for l in gmail_labels.split(',') if l.strip()]
            if labels:
                return labels[0]

        return 'INBOX'

    def get_folders(self) -> List[Dict]:
        """
        Get list of folders

        MBOX is a single file, but we report it as one folder.
        Message count is not available until extraction runs.
        """
        if not self.mbox:
            return []

        return [{
            'id': 'mbox',
            'name': 'MBOX Archive',
            'path': self.file_path,
            'message_count': self.message_count if self.message_count > 0 else None,
            'type': 'archive'
        }]

    def disconnect(self) -> None:
        """Clean up resources and temporary files"""
        # Close Google Drive stream if active
        if self.drive_stream:
            try:
                self.drive_stream.close()
                logger.info("Google Drive stream closed")
            except Exception as e:
                logger.warning(f"Error closing Google Drive stream: {e}")
            finally:
                self.drive_stream = None
                self.drive_client = None

        self.mbox = None
        # Cleanup any temporary Google Drive files (if any were downloaded as fallback)
        self.cleanup_temp_files()
        logger.info("MBOX extractor disconnected")

    # =========================================================================
    # MBOX-Specific Parsing Helpers
    # =========================================================================

    def _decode_header(self, header: str) -> str:
        """Decode email header to UTF-8 string"""
        if not header:
            return ''

        decoded_parts = decode_header(header)
        decoded_str = ''

        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                try:
                    decoded_str += part.decode(encoding or 'utf-8', errors='replace')
                except:
                    decoded_str += part.decode('utf-8', errors='replace')
            else:
                decoded_str += str(part)

        return decoded_str.strip()

    def _extract_email(self, from_field: str) -> str:
        """Extract email address from 'Name <email>' format"""
        if not from_field:
            return ''

        # Decode first in case of encoded headers
        from_field = self._decode_header(from_field)

        match = re.search(r'<(.+?)>', from_field)
        if match:
            return match.group(1).lower().strip()

        # If no angle brackets, might be just the email
        if '@' in from_field:
            return from_field.lower().strip()

        return ''

    def _extract_name(self, from_field: str) -> str:
        """Extract name from 'Name <email>' format"""
        if not from_field:
            return ''

        from_field = self._decode_header(from_field)

        match = re.match(r'(.+?)\s*<', from_field)
        if match:
            return match.group(1).strip().strip('"\'')
        return ''

    def _parse_recipients(self, recipients_field: str) -> List[Dict]:
        """Parse comma-separated recipients"""
        if not recipients_field:
            return []

        recipients = []

        # Split by comma, but be careful about commas in quoted names
        parts = []
        current_part = ""
        in_quotes = False

        for char in recipients_field:
            if char == '"':
                in_quotes = not in_quotes
            elif char == ',' and not in_quotes:
                parts.append(current_part.strip())
                current_part = ""
                continue
            current_part += char

        if current_part.strip():
            parts.append(current_part.strip())

        for part in parts:
            part = part.strip()
            if part:
                recipients.append({
                    'email': self._extract_email(part),
                    'name': self._extract_name(part)
                })

        return recipients

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse email date string to datetime"""
        if not date_str:
            return None

        try:
            # Handle Received header which might have multiple dates
            if 'received:' in date_str.lower():
                # Extract just the date part
                match = re.search(r';([^;]+)$', date_str)
                if match:
                    date_str = match.group(1).strip()

            # Parse the date
            time_tuple = parsedate_tz(date_str)
            if time_tuple:
                timestamp = mktime_tz(time_tuple)
                return datetime.fromtimestamp(timestamp, tz=timezone.utc)

        except Exception as e:
            logger.debug(f"Failed to parse date '{date_str}': {e}")

        return None

    def _get_body_text(self, msg) -> str:
        """Extract plain text body with UTF-8 preservation"""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == 'text/plain':
                    return self._decode_payload(part)
        else:
            if msg.get_content_type() == 'text/plain':
                return self._decode_payload(msg)

        return ''

    def _get_body_html(self, msg) -> str:
        """Extract HTML body with UTF-8 preservation"""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == 'text/html':
                    return self._decode_payload(part)
        else:
            if msg.get_content_type() == 'text/html':
                return self._decode_payload(msg)

        return ''

    def _decode_payload(self, part) -> str:
        """Decode email part payload to UTF-8 string"""
        try:
            payload = part.get_payload(decode=True)
            if not payload:
                return ''

            # Try to get charset from content type
            charset = part.get_content_charset() or 'utf-8'

            try:
                return payload.decode(charset, errors='replace')
            except (UnicodeDecodeError, LookupError):
                # Fallback to common encodings
                for encoding in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
                    try:
                        return payload.decode(encoding, errors='replace')
                    except (UnicodeDecodeError, LookupError):
                        continue

                # Last resort - decode as latin-1 which never fails
                return payload.decode('latin-1', errors='replace')

        except Exception as e:
            logger.debug(f"Failed to decode payload: {e}")
            return ''

    def _clean_header(self, header: str) -> str:
        """Clean message ID and similar headers"""
        if not header:
            return ''
        return header.strip('<>').strip()
