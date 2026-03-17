"""
Client Models - Stage 2 Business Hierarchy

Pydantic models for client CRUD operations.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from enum import Enum


class ClientStatus(str, Enum):
    """Client status options"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    PROSPECT = "prospect"


class ClientBase(BaseModel):
    """Base client fields"""
    client_name: str = Field(..., min_length=1, max_length=255)
    client_label: Optional[str] = Field(None, max_length=50)
    industry: Optional[str] = Field(None, max_length=100)
    status: ClientStatus = ClientStatus.ACTIVE
    notes: Optional[str] = None


class ClientCreate(ClientBase):
    """Create client request"""
    uses_quickbase: bool = False
    quickbase_realm: Optional[str] = None
    quickbase_api_token: Optional[str] = None
    uses_printiq: bool = False
    printiq_api_url: Optional[str] = None
    printiq_api_key: Optional[str] = None


class ClientUpdate(BaseModel):
    """Update client request"""
    client_name: Optional[str] = Field(None, min_length=1, max_length=255)
    client_label: Optional[str] = Field(None, max_length=50)
    industry: Optional[str] = Field(None, max_length=100)
    status: Optional[ClientStatus] = None
    notes: Optional[str] = None
    uses_quickbase: Optional[bool] = None
    quickbase_realm: Optional[str] = None
    quickbase_api_token: Optional[str] = None
    uses_printiq: Optional[bool] = None
    printiq_api_url: Optional[str] = None
    printiq_api_key: Optional[str] = None
    timezone: Optional[str] = None
    currency_code: Optional[str] = Field(None, max_length=3, description="ISO 4217 currency code, e.g. AUD")


class ClientResponse(ClientBase):
    """Client response model"""
    id: str
    uses_quickbase: bool = False
    uses_printiq: bool = False
    timezone: str = "Australia/Sydney"
    currency_code: str = "AUD"
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AccountManagerSummary(BaseModel):
    """Account manager summary for derived fields"""
    id: str
    name: str
    email: str


class ClientWithStats(ClientResponse):
    """Client with statistics"""
    account_managers: List[AccountManagerSummary] = []  # Derived from mailbox assignments
    total_customer_companies: int = 0
    total_customer_contacts: int = 0
    total_mailboxes: int = 0
    total_emails: int = 0
    total_rules: int = 0


class ClientSummary(BaseModel):
    """Client summary for list views"""
    id: str
    client_name: str
    client_label: Optional[str] = None
    status: ClientStatus
    account_managers: List[AccountManagerSummary] = []  # Derived from mailbox assignments
    customer_company_count: int = 0
    contact_count: int = 0
    mailbox_count: int = 0
    total_emails: int = 0


class ClientListResponse(BaseModel):
    """List of clients response"""
    clients: List[ClientSummary]
    total: int
