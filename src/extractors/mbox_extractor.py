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

        if not self.file_path:
            raise ValueError("file_path required in connection_config")

        self.mbox = None
        self.message_count = 0  # Track count during extraction

    def connect(self, **kwargs) -> bool:
        """
        Open MBOX file

        We don't actually open the file here - we'll stream it directly
        in extract_emails() for better memory efficiency.
        """
        try:
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
            raise ConnectionError(f"MBOX connection failed: {e}")

    def extract_emails(self, max_emails: Optional[int] = None) -> Iterator[Dict]:
        """
        Extract emails from MBOX file

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

            # Stream file line-by-line
            with open(self.mbox, 'r', encoding='utf-8', errors='replace') as f:
                current_message_lines = []

                for line_num, line in enumerate(f, 1):
                    # MBOX format: messages start with "From " at beginning of line
                    if line.startswith('From ') and current_message_lines:
                        # Process the previous message
                        message_text = ''.join(current_message_lines)
                        email_dict = self._process_message(message_text, self.message_count)

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
                        self.message_count += 1

                        # Progress logging
                        if self.message_count % 1000 == 0:
                            logger.info(f"Scanned {self.message_count:,} messages, extracted {extracted:,} emails")

                    else:
                        current_message_lines.append(line)

                    # Early exit if limit reached
                    if max_emails and extracted >= max_emails:
                        break

                # Process final message
                if current_message_lines and (not max_emails or extracted < max_emails):
                    message_text = ''.join(current_message_lines)
                    email_dict = self._process_message(message_text, self.message_count)

                    if email_dict:
                        self._update_stats(True)
                        extracted += 1

                        if extracted <= 10:
                            logger.info(f"📧 Email {extracted}: {email_dict.get('subject', 'No subject')[:60]}")

                        yield email_dict

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
        """Clean up resources"""
        self.mbox = None
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
