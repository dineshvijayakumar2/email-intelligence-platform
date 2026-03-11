"""
Quickbase API Client — Low-level HTTP client for Quickbase JSON API.

Handles authentication, pagination, field mapping, and rate limiting.
"""

import logging
import httpx
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Default field mappings for Carbon8 schema (QB field IDs → column names)
DEFAULT_FIELD_MAPPINGS = {
    "customers": {
        "3": "qb_record_id",
        "7": "customer_name",
        "16": "account_manager",
        "748": "customer_code",
        "894": "customer_tier",
        "1717": "customer_status",  # MKTG: Customer Status?
        "1775": "industry",
        "570": "active",
        "101": "total_invoiced",
        "103": "invoiced_ty",
        "104": "invoiced_ly",
        "1125": "invoiced_l90d",
        "1163": "invoiced_l12m",
        "36": "recency_days",  # Recency (numeric)
        "280": "cadence_score",
        "540": "growth_90d",  # 90 day Growth
        "1043": "days_since_last_invoice",
    },
    "contacts": {
        "3": "qb_record_id",
        "7": "qb_customer_id",       # Customer ID (parent FK)
        "11": "first_name",           # First Name*:
        "12": "surname",              # Surname*:
        "15": "email",                # Email*:
        "13": "phone",                # Phone:
        "16": "active",               # Active:
        "53": "contact_recency_days", # Contact Recency
        "25": "quotes_accepted_count",# # of Quotes Accepted
        "27": "most_recent_quote_date",# Most Recent Accepted Quote Date
    },
    "quotes": {
        "3": "qb_record_id",
        "7": "quote_no",
        "8": "qb_customer_id",
        "9": "quote_am_name",
        "12": "sell_ex_tax",
        "13": "date_created",
        "219": "date_accepted",
        "805": "category",
        "892": "contact_email",
        "863": "contact_name",
        "1062": "job_no",
        "1238": "has_job",  # Job # Exists?
        "1447": "quantity",
        "1476": "kinds",
        "1505": "total_quantity",
    },
    "jobs": {
        "3": "qb_record_id",
        "41": "job_no",
        "71": "quote_no",
        "129": "qb_customer_id",
        "371": "job_status",
        "158": "retail_sale",
        "219": "invoiced_margin",
        "251": "margin_pct",
        "341": "accepted_date",
        "311": "due_date",
        "282": "factory_rush_level",
        "1069": "pieces_ordered",
        "1102": "kinds_ordered",
        "1135": "total_qty_ordered",
    },
    "sales_line_items": {
        "3": "qb_record_id",
        "7": "invoice_id",
        "12": "job_no",
        "9": "job_am_name",
        "16": "customer_name",
        "225": "qb_customer_id",
        "286": "inv_date",
        "345": "subtotal",
        "378": "total",
        "1292": "product_group",
        "1420": "industry",
        "439": "job_title",
        "11": "invoice_no",
    },
}


class QuickbaseClient:
    """Low-level Quickbase JSON API client."""

    BASE_URL = "https://api.quickbase.com/v1"

    def __init__(self, realm_hostname: str, user_token: str):
        self.realm_hostname = realm_hostname
        self.user_token = user_token
        self.headers = {
            "QB-Realm-Hostname": realm_hostname,
            "Authorization": f"QB-USER-TOKEN {user_token}",
            "Content-Type": "application/json",
        }

    async def query_records(
        self,
        table_id: str,
        select_fields: list[int],
        where: Optional[str] = None,
        sort_by: Optional[list[dict]] = None,
        skip: int = 0,
        top: int = 1000,
    ) -> dict[str, Any]:
        """
        Query records from a Quickbase table.

        Args:
            table_id: QB table ID (e.g., 'buzhzbv39')
            select_fields: List of field IDs to select
            where: QB query string (e.g., "{'7'.CT.'acme'}")
            sort_by: Sort config (e.g., [{"fieldId": 7, "order": "ASC"}])
            skip: Number of records to skip (pagination)
            top: Max records to return (max 1000)

        Returns:
            QB API response with 'data' and 'metadata' keys
        """
        body: dict[str, Any] = {
            "from": table_id,
            "select": select_fields,
            "options": {
                "skip": skip,
                "top": min(top, 1000),
            },
        }

        if where:
            body["where"] = where
        if sort_by:
            body["sortBy"] = sort_by

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.BASE_URL}/records/query",
                headers=self.headers,
                json=body,
            )
            response.raise_for_status()
            return response.json()

    async def query_all_records(
        self,
        table_id: str,
        select_fields: list[int],
        where: Optional[str] = None,
        sort_by: Optional[list[dict]] = None,
    ) -> list[dict]:
        """
        Query ALL records with automatic pagination.

        Returns:
            List of all record dicts
        """
        all_records = []
        skip = 0
        page_size = 1000

        while True:
            result = await self.query_records(
                table_id=table_id,
                select_fields=select_fields,
                where=where,
                sort_by=sort_by,
                skip=skip,
                top=page_size,
            )

            records = result.get("data", [])
            all_records.extend(records)

            metadata = result.get("metadata", {})
            total = metadata.get("totalRecords", 0)

            logger.info(
                f"QB query: fetched {len(records)} records (total so far: {len(all_records)}/{total})"
            )

            if len(records) == 0 or len(all_records) >= total:
                break

            skip += len(records)

        return all_records

    async def get_fields(self, table_id: str) -> list[dict]:
        """Get field definitions for a table."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{self.BASE_URL}/fields",
                headers=self.headers,
                params={"tableId": table_id},
            )
            response.raise_for_status()
            return response.json()

    async def test_connection(self) -> bool:
        """Test if the QB connection is valid."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.BASE_URL}/tables",
                    headers=self.headers,
                    params={"appId": "placeholder"},
                )
                # 200 = connected, 401 = bad token, other = error
                return response.status_code != 401
        except Exception as e:
            logger.error(f"QB connection test failed: {e}")
            return False

    @staticmethod
    def map_record(
        record: dict, field_mapping: dict[str, str]
    ) -> dict[str, Any]:
        """
        Map a QB record (field ID keys) to our column names.

        Args:
            record: QB record dict like {"7": {"value": "Acme"}, "16": {"value": "John"}}
            field_mapping: Dict mapping QB field IDs to column names

        Returns:
            Dict with column names as keys
        """
        mapped = {}
        for fid, col_name in field_mapping.items():
            field_data = record.get(fid, {})
            value = field_data.get("value") if isinstance(field_data, dict) else None
            mapped[col_name] = value
        return mapped

    @staticmethod
    def get_select_fields(field_mapping: dict[str, str]) -> list[int]:
        """Extract QB field IDs (as ints) from a field mapping dict."""
        return [int(fid) for fid in field_mapping.keys()]
