"""
Pydantic models for the core API endpoints (mailboxes, processing jobs, emails).

Extracted from main.py to be shared across routers.
"""

from pydantic import BaseModel
from typing import Optional, Dict, Any, List


class MailboxConfig(BaseModel):
    name: str
    email_address: Optional[str] = None
    mailbox_type: str
    is_active: bool = True
    connection_config: Optional[Dict[str, Any]] = {}
    client_id: Optional[str] = None
    user_id: Optional[str] = None


class ProcessingJobConfig(BaseModel):
    """
    Configuration for email processing jobs.

    Processing Limits:
    - max_emails: Maximum number of emails to process (None = all emails in file)
    - batch_size: Database batch insert size (default 250, auto-splits on timeout for reliability)

    Date Filters (for processing only emails within a date range):
    - start_date: Process emails sent on or after this date (ISO format: YYYY-MM-DD)
    - end_date: Process emails sent on or before this date (ISO format: YYYY-MM-DD)

    Download Options (for Google Drive files):
    - download_first: Download file completely before processing (faster for large files)
    - download_threads: Number of parallel threads for download (default: 8)
    """
    job_type: str
    # Processing limits
    max_emails: Optional[int] = None
    batch_size: Optional[int] = 250
    # Date-based filtering
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    # Feature flags
    enable_categorization: Optional[bool] = True
    enable_enrichment: Optional[bool] = False
    # Download options for Google Drive files
    download_first: Optional[bool] = True
    download_threads: Optional[int] = 8
    keep_downloaded_file: Optional[bool] = True
    use_cached_file: Optional[bool] = True
    # Deprecated field (use max_emails instead)
    total_records: Optional[int] = None
    # These will be populated from mailbox data
    mailbox_id: Optional[str] = None
    mailbox_type: Optional[str] = None
    connection_config: Optional[Dict[str, Any]] = {}


class ConnectionTest(BaseModel):
    mailbox_type: str
    connection_config: Dict[str, Any]


class OAuth2ExchangeRequest(BaseModel):
    code: str
    user_id: str


class GoogleDriveConnection(BaseModel):
    user_id: str
    status: str


class EmailFilters(BaseModel):
    search: Optional[str] = None
    category: Optional[str] = None
    mailbox: Optional[str] = None
    folder: Optional[str] = None
    dateRange: Optional[List[str]] = None
    isOutbound: Optional[str] = None
    tags: Optional[List[str]] = None
    isSpam: Optional[bool] = None
    isMarketing: Optional[bool] = None
    minPriority: Optional[int] = None
    maxPriority: Optional[int] = None


class EmailRequest(BaseModel):
    filters: EmailFilters = EmailFilters()
    page: int = 1
    pageSize: int = 20


class EmailResponse(BaseModel):
    id: str
    subject: str
    sender_email: str
    sender_name: Optional[str]
    recipients: Optional[List[Dict[str, str]]] = None
    cc_list: Optional[List[Dict[str, str]]] = None
    bcc_list: Optional[List[Dict[str, str]]] = None
    sent_date: str
    received_date: Optional[str] = None
    category: Optional[str]
    is_outbound: bool
    is_reply: bool
    folder_path: str
    message_size: int
    mailbox_name: str
    mailbox_id: str
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    tags: Optional[List[str]] = None
    is_spam: Optional[bool] = None
    is_marketing: Optional[bool] = None
    priority_score: Optional[int] = None
    sender_type: Optional[str] = None
    attachments: Optional[List[Dict[str, Any]]] = None
    provider_web_link: Optional[str] = None
    mailbox_type: Optional[str] = None


class EmailListResponse(BaseModel):
    emails: List[EmailResponse]
    totalCount: int
