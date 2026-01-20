"""
Customer Contact Models - Stage 2 Business Hierarchy

Pydantic models for customer contact CRUD operations.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, EmailStr, Field


class ContactBase(BaseModel):
    """Base contact fields"""
    email_address: EmailStr
    full_name: Optional[str] = Field(None, max_length=255)
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    job_title: Optional[str] = Field(None, max_length=255)
    company_name: Optional[str] = Field(None, max_length=255)  # From signature
    phone_number: Optional[str] = Field(None, max_length=50)
    mobile_number: Optional[str] = Field(None, max_length=50)
    linkedin_url: Optional[str] = None
    notes: Optional[str] = None


class ContactCreate(ContactBase):
    """Create contact request"""
    customer_company_id: str
    client_id: str


class ContactUpdate(BaseModel):
    """Update contact request"""
    full_name: Optional[str] = Field(None, max_length=255)
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    job_title: Optional[str] = Field(None, max_length=255)
    company_name: Optional[str] = Field(None, max_length=255)
    phone_number: Optional[str] = Field(None, max_length=50)
    mobile_number: Optional[str] = Field(None, max_length=50)
    linkedin_url: Optional[str] = None
    notes: Optional[str] = None
    customer_company_id: Optional[str] = None  # For moving contact to different company


class ContactResponse(ContactBase):
    """Contact response model"""
    id: str
    customer_company_id: Optional[str] = None
    client_id: Optional[str] = None
    first_contacted_at: Optional[datetime] = None
    last_contacted_at: Optional[datetime] = None
    total_emails_sent: int = 0
    total_emails_received: int = 0
    signature_data: Optional[Dict[str, Any]] = None
    signature_last_updated: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ContactWithCompany(ContactResponse):
    """Contact with company information"""
    company_info: Optional["CompanyInfo"] = None


class CompanyInfo(BaseModel):
    """Company information for contact context"""
    id: str
    company_name: str
    client_id: str
    client_name: Optional[str] = None


class ContactSummary(BaseModel):
    """Contact summary for list views"""
    id: str
    email_address: str
    full_name: Optional[str] = None
    job_title: Optional[str] = None
    company_name: Optional[str] = None
    customer_company_id: Optional[str] = None
    customer_company_name: Optional[str] = None
    client_id: Optional[str] = None
    last_contacted_at: Optional[datetime] = None
    total_emails: int = 0


class ContactListResponse(BaseModel):
    """List of contacts response"""
    contacts: List[ContactSummary]
    total: int


class SignatureData(BaseModel):
    """Parsed signature data structure"""
    raw_text: Optional[str] = None
    full_name: Optional[str] = None
    job_title: Optional[str] = None
    company_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None
    fax: Optional[str] = None
    address: Optional[str] = None
    website: Optional[str] = None
    linkedin_url: Optional[str] = None
    twitter_handle: Optional[str] = None
    parsed_at: Optional[datetime] = None
    confidence_score: Optional[float] = None


# Update forward reference
ContactWithCompany.model_rebuild()
