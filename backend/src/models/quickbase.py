"""Pydantic models for Quickbase integration."""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class QBSyncConfigCreate(BaseModel):
    realm_hostname: str
    app_id: str
    user_token: str
    customers_table_id: str
    contacts_table_id: str
    quotes_table_id: str
    jobs_table_id: str
    sales_line_items_table_id: str
    field_mappings: Optional[dict] = None
    sync_interval_hours: int = 6


class QBSyncConfigResponse(BaseModel):
    client_id: str
    realm_hostname: str
    app_id: str
    user_token_masked: str
    customers_table_id: str
    contacts_table_id: str
    quotes_table_id: str
    jobs_table_id: str
    sales_line_items_table_id: str
    field_mappings: Optional[dict] = None
    sync_interval_hours: int = 6
    last_sync_at: Optional[datetime] = None
    is_active: bool = True


class QBSyncStatus(BaseModel):
    client_id: str
    last_sync_at: Optional[datetime] = None
    is_active: bool = True
    record_counts: dict = {}


class QBSyncResult(BaseModel):
    status: str
    message: str
    counts: Optional[dict] = None


class QBCustomerResponse(BaseModel):
    id: str
    qb_record_id: str
    customer_name: str
    customer_code: Optional[str] = None
    customer_tier: Optional[str] = None
    customer_status: Optional[str] = None
    account_manager: Optional[str] = None
    industry: Optional[str] = None
    active: Optional[bool] = True
    total_invoiced: Optional[float] = None
    invoiced_ty: Optional[float] = None
    invoiced_ly: Optional[float] = None
    days_since_last_invoice: Optional[int] = None
    matched_company_id: Optional[str] = None
    matched_company_name: Optional[str] = None
    synced_at: Optional[datetime] = None
