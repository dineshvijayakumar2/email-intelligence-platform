import os
import json
import base64
from datetime import datetime, timezone
from typing import Iterator, Dict, Optional, List
import logging
from msal import ConfidentialClientApplication
import requests

from .base_extractor import BaseExtractor

logger = logging.getLogger(__name__)

class OutlookLiveExtractor(BaseExtractor):
    """Extract emails from Outlook Live using Microsoft Graph API"""
    
    def __init__(self, connection_config: Dict = None):
        """
        Initialize with Azure app registration details
        
        Args:
            connection_config: Dict containing:
                - client_id: Azure app client ID
                - client_secret: Azure app client secret  
                - tenant_id: Azure tenant ID
                - redirect_uri: OAuth redirect URI
        """
        config = connection_config or {}
        
        # Load from environment if not provided
        self.client_id = config.get('client_id') or os.getenv('AZURE_CLIENT_ID')
        self.client_secret = config.get('client_secret') or os.getenv('AZURE_CLIENT_SECRET') 
        self.tenant_id = config.get('tenant_id') or os.getenv('AZURE_TENANT_ID')
        self.redirect_uri = config.get('redirect_uri') or os.getenv('AZURE_REDIRECT_URI')
        
        if not all([self.client_id, self.client_secret, self.tenant_id]):
            raise ValueError("Azure credentials not fully configured")
        
        super().__init__(config)
        
        # Microsoft Graph endpoints
        self.authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        self.graph_endpoint = "https://graph.microsoft.com/v1.0"
        self.scopes = ["https://graph.microsoft.com/Mail.Read"]
        
        # MSAL client
        self.app = ConfidentialClientApplication(
            client_id=self.client_id,
            client_credential=self.client_secret,
            authority=self.authority
        )
        
        self.access_token = None
        self.user_principal_name = None
        
    def connect(self) -> bool:
        """Connect to Outlook Live via Microsoft Graph"""
        try:
            # For POC, using device flow authentication
            # In production, you'd implement proper OAuth flow
            flow = self.app.initiate_device_flow(scopes=self.scopes)
            
            if "user_code" not in flow:
                raise ValueError("Failed to create device flow")
            
            print(f"\nTo authenticate with Outlook Live:")
            print(f"1. Go to: {flow['verification_uri']}")
            print(f"2. Enter code: {flow['user_code']}")
            print("3. Sign in with your Outlook Live account")
            print("4. Press Enter here when done...")
            input()
            
            # Get token
            result = self.app.acquire_token_by_device_flow(flow)
            
            if "access_token" in result:
                self.access_token = result["access_token"]
                logger.info("Successfully authenticated with Outlook Live")
                
                # Get user info
                self._get_user_info()
                return True
            else:
                error = result.get("error_description", "Unknown error")
                logger.error(f"Authentication failed: {error}")
                return False
                
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False
    
    def _get_user_info(self):
        """Get authenticated user information"""
        if not self.access_token:
            return
        
        try:
            headers = {'Authorization': f'Bearer {self.access_token}'}
            response = requests.get(f"{self.graph_endpoint}/me", headers=headers)
            response.raise_for_status()
            
            user_data = response.json()
            self.user_principal_name = user_data.get('userPrincipalName')
            logger.info(f"Connected as: {self.user_principal_name}")
            
        except Exception as e:
            logger.warning(f"Could not get user info: {e}")
    
    def get_folders(self) -> List[Dict]:
        """Get list of mail folders"""
        if not self.access_token:
            return []
        
        try:
            headers = {'Authorization': f'Bearer {self.access_token}'}
            url = f"{self.graph_endpoint}/me/mailFolders"
            
            folders = []
            while url:
                response = requests.get(url, headers=headers)
                response.raise_for_status()
                
                data = response.json()
                
                for folder in data.get('value', []):
                    folders.append({
                        'id': folder['id'],
                        'name': folder['displayName'],
                        'path': folder['displayName'],  # Simplified for POC
                        'total_item_count': folder.get('totalItemCount', 0),
                        'unread_item_count': folder.get('unreadItemCount', 0)
                    })
                
                url = data.get('@odata.nextLink')
            
            logger.info(f"Found {len(folders)} folders")
            return folders
            
        except Exception as e:
            logger.error(f"Failed to get folders: {e}")
            return []
    
    def extract_emails(
        self,
        folder_name: Optional[str] = "Inbox",
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        max_emails: Optional[int] = None
    ) -> Iterator[Dict]:
        """
        Extract emails from Outlook Live
        
        Args:
            folder_name: Folder to extract from ('Inbox', 'Sent Items', etc.)
            date_from: Start date for extraction
            date_to: End date for extraction  
            max_emails: Maximum emails to extract
        """
        if not self.access_token:
            raise RuntimeError("Not connected. Call connect() first.")
        
        self.stats['start_time'] = datetime.now()
        
        try:
            # Get folder ID
            folder_id = self._get_folder_id(folder_name)
            if not folder_id:
                logger.error(f"Folder '{folder_name}' not found")
                return
            
            # Build Graph API URL with filters
            url = f"{self.graph_endpoint}/me/mailFolders/{folder_id}/messages"
            params = {
                '$select': 'id,subject,sender,toRecipients,ccRecipients,bccRecipients,receivedDateTime,sentDateTime,body,isRead,hasAttachments,internetMessageHeaders',
                '$orderby': 'receivedDateTime desc'
            }
            
            # Add date filters
            filters = []
            if date_from:
                filters.append(f"receivedDateTime ge {date_from.isoformat()}")
            if date_to:
                filters.append(f"receivedDateTime le {date_to.isoformat()}")
            
            if filters:
                params['$filter'] = ' and '.join(filters)
            
            if max_emails:
                params['$top'] = min(max_emails, 1000)  # Graph API limit
            
            headers = {'Authorization': f'Bearer {self.access_token}'}
            
            # Extract emails with pagination
            extracted = 0
            while url and (not max_emails or extracted < max_emails):
                try:
                    response = requests.get(url, headers=headers, params=params)
                    response.raise_for_status()
                    
                    data = response.json()
                    emails = data.get('value', [])
                    
                    for email_data in emails:
                        if max_emails and extracted >= max_emails:
                            break
                        
                        try:
                            standardized = self._parse_graph_email(email_data, folder_name)
                            self._update_stats(True)
                            extracted += 1
                            yield standardized
                            
                        except Exception as e:
                            self._update_stats(False, str(e))
                            logger.warning(f"Failed to parse email {email_data.get('id', 'unknown')}: {e}")
                            continue
                    
                    # Get next page
                    url = data.get('@odata.nextLink')
                    params = {}  # Params already included in nextLink
                    
                except Exception as e:
                    logger.error(f"Failed to fetch emails page: {e}")
                    break
            
            logger.info(f"Extraction completed. Processed: {self.stats['success']} emails")
            
        except Exception as e:
            logger.error(f"Email extraction failed: {e}")
            raise
        finally:
            self.stats['end_time'] = datetime.now()
    
    def _get_folder_id(self, folder_name: str) -> Optional[str]:
        """Get folder ID by name"""
        folders = self.get_folders()
        for folder in folders:
            if folder['name'].lower() == folder_name.lower():
                return folder['id']
        return None
    
    def _parse_graph_email(self, email_data: Dict, folder_name: str) -> Dict:
        """Parse Microsoft Graph email response into standard format"""
        
        # Extract sender
        sender = email_data.get('sender', {})
        sender_info = sender.get('emailAddress', {})
        
        # Extract recipients
        to_recipients = self._parse_graph_recipients(email_data.get('toRecipients', []))
        cc_recipients = self._parse_graph_recipients(email_data.get('ccRecipients', []))
        bcc_recipients = self._parse_graph_recipients(email_data.get('bccRecipients', []))
        
        # Extract dates
        sent_date = self._parse_graph_date(email_data.get('sentDateTime'))
        received_date = self._parse_graph_date(email_data.get('receivedDateTime'))
        
        # Extract body
        body = email_data.get('body', {})
        body_content = body.get('content', '')
        body_type = body.get('contentType', 'text')
        
        # Get internet headers for message ID
        headers = {}
        for header in email_data.get('internetMessageHeaders', []):
            headers[header.get('name', '')] = header.get('value', '')
        
        message_id = headers.get('Message-ID', email_data.get('id', ''))
        
        # Determine if outbound (from Sent Items or user's domain)
        is_outbound = (
            folder_name.lower() in ['sent items', 'sent', 'outbox'] or
            (self.user_principal_name and sender_info.get('address', '').lower() == self.user_principal_name.lower())
        )
        
        # Check if reply
        is_reply = self._is_reply_email(email_data.get('subject', ''), headers)
        
        standardized = {
            'message_id': self._clean_message_id(message_id),
            'subject': email_data.get('subject', ''),
            'sender_email': sender_info.get('address', ''),
            'sender_name': sender_info.get('name', ''),
            'recipients': to_recipients,
            'cc_list': cc_recipients,
            'bcc_list': bcc_recipients,
            'sent_date': sent_date,
            'received_date': received_date,
            'body_text': body_content if body_type == 'text' else self._html_to_text(body_content),
            'body_html': body_content if body_type == 'html' else '',
            'folder_path': folder_name,
            'is_outbound': is_outbound,
            'is_reply': is_reply,
            'raw_headers': headers,
            'message_size': len(body_content)
        }
        
        return self._standardize_email(standardized)
    
    def _parse_graph_recipients(self, recipients_data: List[Dict]) -> List[Dict]:
        """Parse Graph API recipients format"""
        recipients = []
        for recipient in recipients_data:
            email_addr = recipient.get('emailAddress', {})
            recipients.append({
                'email': email_addr.get('address', ''),
                'name': email_addr.get('name', '')
            })
        return recipients
    
    def _parse_graph_date(self, date_string: Optional[str]) -> Optional[datetime]:
        """Parse Graph API date string to datetime"""
        if not date_string:
            return None
        
        try:
            # Graph API returns ISO 8601 format
            return datetime.fromisoformat(date_string.replace('Z', '+00:00'))
        except Exception as e:
            logger.warning(f"Failed to parse date '{date_string}': {e}")
            return None
    
    def _clean_message_id(self, message_id: str) -> str:
        """Clean message ID"""
        return message_id.strip('<>').strip() if message_id else ''
    
    def _is_reply_email(self, subject: str, headers: Dict) -> bool:
        """Check if email is a reply"""
        if not subject:
            return False
        
        # Check subject line
        subject_lower = subject.lower()
        if any(prefix in subject_lower for prefix in ['re:', 're ', 'aw:', 'aw ']):
            return True
        
        # Check headers
        if headers.get('In-Reply-To') or headers.get('References'):
            return True
        
        return False
    
    def _html_to_text(self, html_content: str) -> str:
        """Convert HTML to plain text (basic implementation)"""
        if not html_content:
            return ''
        
        # Basic HTML stripping (for production, use BeautifulSoup)
        import re
        text = re.sub(r'<[^>]+>', '', html_content)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    def disconnect(self):
        """Clean up connection"""
        self.access_token = None
        self.user_principal_name = None
        logger.info("Disconnected from Outlook Live")