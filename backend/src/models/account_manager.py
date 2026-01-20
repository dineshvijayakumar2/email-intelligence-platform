"""
Account Manager Models - Stage 2 Business Hierarchy

Pydantic models for account manager CRUD operations.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field
from enum import Enum


class AccountManagerRole(str, Enum):
    """Account manager roles"""
    ADMIN = "admin"
    ACCOUNT_MANAGER = "account_manager"
    VIEWER = "viewer"


class AccountManagerBase(BaseModel):
    """Base account manager fields"""
    name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    role: AccountManagerRole = AccountManagerRole.ACCOUNT_MANAGER


class AccountManagerCreate(AccountManagerBase):
    """Create account manager request"""
    password: Optional[str] = Field(None, min_length=8)


class AccountManagerUpdate(BaseModel):
    """Update account manager request"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    role: Optional[AccountManagerRole] = None
    is_active: Optional[bool] = None


class AccountManagerResponse(AccountManagerBase):
    """Account manager response model"""
    id: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AccountManagerWithStats(AccountManagerResponse):
    """Account manager with client statistics"""
    total_clients: int = 0
    total_mailboxes: int = 0
    active_clients: int = 0


class AccountManagerListResponse(BaseModel):
    """List of account managers response"""
    account_managers: List[AccountManagerResponse]
    total: int
