"""
Customer Recognition Rule Models - Stage 2 Business Hierarchy

Pydantic models for recognition rule CRUD operations.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from enum import Enum


class RuleType(str, Enum):
    """Types of recognition rules"""
    DOMAIN = "domain"  # Match sender domain (e.g., "acme.com")
    EMAIL_EXACT = "email_exact"  # Exact email match
    EMAIL_PATTERN = "email_pattern"  # Email pattern with wildcards (e.g., "*@sales.acme.com")
    SUBJECT_CONTAINS = "subject_contains"  # Subject line contains text
    BODY_KEYWORD = "body_keyword"  # Body contains keyword


class RuleBase(BaseModel):
    """Base rule fields"""
    rule_name: str = Field(..., min_length=1, max_length=255)
    rule_type: RuleType
    pattern: str = Field(..., min_length=1, max_length=500)
    priority: int = Field(default=0, ge=0, le=1000)
    is_active: bool = True


class RuleCreate(RuleBase):
    """Create rule request"""
    client_id: Optional[str] = None  # NULL = applies to all clients
    customer_company_id: str  # Which company to assign matched emails to


class RuleUpdate(BaseModel):
    """Update rule request"""
    rule_name: Optional[str] = Field(None, min_length=1, max_length=255)
    rule_type: Optional[RuleType] = None
    pattern: Optional[str] = Field(None, min_length=1, max_length=500)
    priority: Optional[int] = Field(None, ge=0, le=1000)
    is_active: Optional[bool] = None
    customer_company_id: Optional[str] = None


class RuleResponse(RuleBase):
    """Rule response model"""
    id: str
    client_id: Optional[str] = None
    customer_company_id: str
    match_count: int = 0
    last_matched_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RuleWithContext(RuleResponse):
    """Rule with related entity names"""
    client_name: Optional[str] = None
    customer_company_name: Optional[str] = None


class RuleSummary(BaseModel):
    """Rule summary for list views"""
    id: str
    rule_name: str
    rule_type: RuleType
    pattern: str
    priority: int
    is_active: bool
    client_id: Optional[str] = None
    client_name: Optional[str] = None
    customer_company_id: str
    customer_company_name: Optional[str] = None
    match_count: int = 0
    last_matched_at: Optional[datetime] = None


class RuleListResponse(BaseModel):
    """List of rules response"""
    rules: List[RuleSummary]
    total: int


class RuleTestRequest(BaseModel):
    """Request to test a rule against sample data"""
    rule_type: RuleType
    pattern: str
    sample_email: Optional[str] = None
    sample_subject: Optional[str] = None
    sample_body: Optional[str] = None


class RuleTestResponse(BaseModel):
    """Response from rule test"""
    matched: bool
    match_details: Optional[str] = None
    sample_matches: List[str] = []  # Sample emails that would match


class RuleApplyRequest(BaseModel):
    """Request to apply a rule to historical emails"""
    rule_id: str
    limit: int = Field(default=1000, ge=1, le=10000)
    dry_run: bool = True  # If true, just return count without updating


class RuleApplyResponse(BaseModel):
    """Response from applying a rule"""
    rule_id: str
    emails_matched: int
    emails_updated: int
    dry_run: bool
    sample_matches: List[dict] = []  # Sample of matched emails
