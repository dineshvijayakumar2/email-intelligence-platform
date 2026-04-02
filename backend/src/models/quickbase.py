"""Pydantic models for Quickbase integration."""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class QBSyncConfigCreate(BaseModel):
    realm_hostname: str
    app_id: str
    user_token: Optional[str] = None  # blank = keep existing token
    customers_table_id: str
    contacts_table_id: str
    quotes_table_id: str
    jobs_table_id: str
    sales_line_items_table_id: str
    operations_table_id: Optional[str] = 'bvqsudnif'
    unique_emails_table_id: Optional[str] = 'bvmtc5re6'
    field_mappings: Optional[dict] = None
    sync_interval_hours: Optional[int] = None  # None = manual mode (no auto-sync)


class QBSyncConfigResponse(BaseModel):
    client_id: str
    realm_hostname: str
    app_id: str
    user_token: str  # returned as-is (admin-only endpoint)
    customers_table_id: str
    contacts_table_id: str
    quotes_table_id: str
    jobs_table_id: str
    sales_line_items_table_id: str
    operations_table_id: Optional[str] = 'bvqsudnif'
    unique_emails_table_id: Optional[str] = 'bvmtc5re6'
    field_mappings: Optional[dict] = None
    sync_interval_hours: Optional[int] = None  # None = manual mode
    last_sync_at: Optional[datetime] = None
    is_active: bool = True


class QBTableSyncLog(BaseModel):
    table_name: str
    table_id: Optional[str] = None   # QB table ID — cross-ref to qb_field_definitions
    record_count: int
    synced_at: Optional[datetime] = None
    status: str = 'success'
    error_message: Optional[str] = None


class QBSyncStatus(BaseModel):
    client_id: str
    last_sync_at: Optional[datetime] = None
    is_active: bool = True
    record_counts: dict = {}
    table_logs: list[QBTableSyncLog] = []


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
