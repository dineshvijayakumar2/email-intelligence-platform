import mailbox
import email
from email import message_from_binary_file
from email.header import decode_header
from email.utils import parsedate_tz, mktime_tz
from typing import Iterator, Dict, Optional, List
from datetime import datetime, timezone
import logging
import re

from .base_extractor import BaseExtractor

logger = logging.getLogger(__name__)

class MBOXExtractor(BaseExtractor):
    """Extract emails from MBOX format files"""
    
    def __init__(self, connection_config: Dict):
        """
        Initialize with MBOX file path
        
        Args:
            connection_config: Dict containing 'file_path' key
        """
        super().__init__(connection_config)
        self.file_path = connection_config.get('file_path')
        if not self.file_path:
            raise ValueError("file_path required in connection_config")
        
        self.mbox = None
        
    def connect(self) -> bool:
        """Open MBOX file - using direct file access for speed"""
        try:
            # Don't use mailbox.mbox() - it's too slow for large files
            # We'll read the file directly in extract_emails()
            self.mbox = self.file_path  # Just store the path
            logger.info(f"Opened MBOX file: {self.file_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to open MBOX file: {e}")
            return False
    
    def get_folders(self) -> List[Dict]:
        """MBOX files don't have folders, return single folder info"""
        if not self.mbox:
            return []
        
        return [{
            'id': 'mbox',
            'name': 'MBOX Archive',
            'path': self.file_path,
            'total_item_count': len(self.mbox),
            'unread_item_count': 0
        }]
    
    def extract_emails(
        self,
        folder_name: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        max_emails: Optional[int] = None
    ) -> Iterator[Dict]:
        """
        Extract emails from MBOX file
        
        Args:
            folder_name: Ignored for MBOX (single file)
            date_from: Start date filter
            date_to: End date filter
            max_emails: Maximum emails to extract
        """
        # Direct file reading - much faster than mailbox.mbox()
        self.stats['start_time'] = datetime.now()
        logger.info(f"Starting email extraction (max_emails={max_emails})...")

        try:
            extracted = 0

            # Read file directly, splitting on "From " lines
            with open(self.mbox, 'r', encoding='utf-8', errors='replace') as f:
                current_message_lines = []
                message_count = 0

                for line in f:
                    # MBOX format: messages start with "From " at beginning of line
                    if line.startswith('From ') and current_message_lines:
                        # Process the previous message
                        message_text = ''.join(current_message_lines)
                        try:
                            message = email.message_from_string(message_text)
                            email_data = self._parse_message(message, message_count)

                            # Apply date filters
                            should_include = True
                            if date_from or date_to:
                                sent_date = email_data.get('sent_date')
                                if sent_date:
                                    if date_from and sent_date < date_from:
                                        should_include = False
                                    if date_to and sent_date > date_to:
                                        should_include = False

                            if should_include:
                                standardized = self._standardize_email(email_data)
                                self._update_stats(True)
                                extracted += 1

                                # Log first few emails
                                if extracted <= 10:
                                    subject = email_data.get('subject', 'No subject')[:50]
                                    logger.info(f"✉️  Extracted email {extracted}: {subject}")

                                yield standardized

                                if max_emails and extracted >= max_emails:
                                    logger.info(f"✓ Reached limit of {max_emails} emails")
                                    break

                        except Exception as e:
                            self._update_stats(False, str(e))
                            logger.warning(f"⚠️  Failed to parse message {message_count}: {e}")

                        # Start new message
                        current_message_lines = [line]
                        message_count += 1

                        # Log progress
                        if message_count > 0 and message_count % 1000 == 0:
                            logger.info(f"🔍 Scanned {message_count:,} messages, extracted {extracted:,} emails...")
                    else:
                        current_message_lines.append(line)

                    # Early exit if we've extracted enough
                    if max_emails and extracted >= max_emails:
                        break

                # Process final message
                if current_message_lines and (not max_emails or extracted < max_emails):
                    message_text = ''.join(current_message_lines)
                    try:
                        message = email.message_from_string(message_text)
                        email_data = self._parse_message(message, message_count)

                        standardized = self._standardize_email(email_data)
                        self._update_stats(True)
                        extracted += 1

                        # Log final email if needed
                        if extracted <= 10:
                            subject = email_data.get('subject', 'No subject')[:50]
                            logger.info(f"✉️  Extracted email {extracted}: {subject}")

                        yield standardized

                    except Exception as e:
                        self._update_stats(False, str(e))
                        logger.warning(f"⚠️  Failed to parse final message: {e}")

            logger.info(f"MBOX extraction completed. Processed: {self.stats['success']} emails")
            
        except Exception as e:
            logger.error(f"MBOX extraction failed: {e}")
            raise
        finally:
            self.stats['end_time'] = datetime.now()
    
    def _parse_message(self, msg, idx: int) -> Dict:
        """Parse email.message.Message into dict"""
        return {
            'message_id': self._clean_header(msg.get('Message-ID', f'generated-{idx}')),
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
            'folder_path': None,  # Generic MBOX - folder will be inferred by normalizer
            'is_outbound': False,  # Will be determined by normalizer
            'is_reply': self._is_reply(msg),
            'raw_headers': dict(msg.items())
        }
    
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
        
        match = re.match(r'(.+?)\s*<', from_field)
        if match:
            return self._decode_header(match.group(1).strip().strip('"\''))
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
    
    def _is_reply(self, msg) -> bool:
        """Check if message is a reply"""
        subject = msg.get('Subject', '')
        in_reply_to = msg.get('In-Reply-To')
        references = msg.get('References')
        
        # Check subject
        if subject.lower().startswith(('re:', 're ', 'aw:', 'aw ')):
            return True
        
        # Check headers
        if in_reply_to or references:
            return True
        
        return False
    
    def disconnect(self):
        """Close MBOX file"""
        # Since we read the file directly in extract_emails(), nothing to close here
        self.mbox = None
        logger.info("MBOX extractor disconnected")