"""
Customer Company Models - Stage 2 Business Hierarchy

Pydantic models for customer company CRUD operations.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, HttpUrl


class CustomerCompanyBase(BaseModel):
    """Base customer company fields"""
    company_name: str = Field(..., min_length=1, max_length=255)
    email_domains: List[str] = Field(default_factory=list)
    industry: Optional[str] = Field(None, max_length=100)
    website: Optional[str] = None
    notes: Optional[str] = None


class CustomerCompanyCreate(CustomerCompanyBase):
    """Create customer company request"""
    client_id: str


class CustomerCompanyUpdate(BaseModel):
    """Update customer company request"""
    company_name: Optional[str] = Field(None, min_length=1, max_length=255)
    email_domains: Optional[List[str]] = None
    industry: Optional[str] = Field(None, max_length=100)
    website: Optional[str] = None
    notes: Optional[str] = None


class CustomerCompanyResponse(CustomerCompanyBase):
    """Customer company response model"""
    id: str
    client_id: str
    first_contact_date: Optional[datetime] = None
    last_contact_date: Optional[datetime] = None
    total_emails: int = 0
    total_inbound: int = 0
    total_outbound: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CustomerCompanyWithContacts(CustomerCompanyResponse):
    """Customer company with contact list"""
    contacts: List["ContactSummary"] = []
    contact_count: int = 0


class CustomerCompanySummary(BaseModel):
    """Customer company summary for list views"""
    id: str
    company_name: str
    client_id: str
    client_name: Optional[str] = None
    email_domains: List[str] = []
    industry: Optional[str] = None
    first_contact_date: Optional[datetime] = None
    last_contact_date: Optional[datetime] = None
    total_emails: int = 0
    contact_count: int = 0
    engagement_status: Optional[str] = None  # active, quiet, at_risk


class CustomerCompanyListResponse(BaseModel):
    """List of customer companies response"""
    customer_companies: List[CustomerCompanySummary]
    total: int


class ContactSummary(BaseModel):
    """Contact summary for embedding in customer company"""
    id: str
    email_address: str
    full_name: Optional[str] = None
    job_title: Optional[str] = None
    total_emails_sent: int = 0
    total_emails_received: int = 0
    last_contacted_at: Optional[datetime] = None


# Update forward reference
CustomerCompanyWithContacts.model_rebuild()
