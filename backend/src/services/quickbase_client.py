"""
Quickbase API Client — Low-level HTTP client for Quickbase JSON API.

Handles authentication, pagination, field mapping, and rate limiting.
"""

import logging
import httpx
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Default field mappings for Carbon8 schema (QB field IDs → column names)
# Verified against live qb_sync_config row — March 2026
DEFAULT_FIELD_MAPPINGS = {
    "customers": {
        "3": "qb_record_id",
        "6": "customer_code",
        "7": "customer_name",
        "9": "active",
        "16": "account_manager",
        "17": "customer_tier",
        "36": "recency_days",
        "59": "industry",
        "67": "customer_status",
        "68": "days_since_last_invoice",
        "101": "total_invoiced",
        "103": "invoiced_ty",
        "104": "invoiced_ly",
    },
    "contacts": {
        "3": "qb_record_id",
        "7": "qb_customer_id",
        "11": "first_name",
        "12": "surname",
        "13": "phone",
        "15": "email",
        "16": "active",
        "25": "quotes_accepted_count",
        "27": "most_recent_quote_date",
        "53": "contact_recency_days",
    },
    "quotes": {
        "3": "qb_record_id",
        "7": "quote_no",
        "8": "qb_customer_id",
        "9": "quote_am_name",
        "12": "sell_ex_tax",
        "13": "date_created",
        "14": "date_accepted",
        "36": "category",
        "40": "contact_name",
        "41": "contact_email",
        "51": "job_no",
        "57": "has_job",
        "65": "quantity",
        "67": "kinds",
        "68": "total_quantity",
    },
    "jobs": {
        "3": "qb_record_id",
        "7": "job_no",
        "9": "qb_customer_id",
        "10": "quote_no",
        "11": "retail_sale",
        "17": "invoiced_margin",
        "18": "margin_pct",
        "21": "factory_rush_level",
        "22": "due_date",
        "23": "accepted_date",
        "24": "job_status",
        "62": "pieces_ordered",
        "63": "kinds_ordered",
        "64": "total_qty_ordered",
    },
    "sales_line_items": {
        "3": "qb_record_id",
        "7": "invoice_id",
        "9": "job_am_name",
        "11": "invoice_no",
        "12": "job_no",
        "16": "customer_name",
        "17": "qb_customer_id",
        "19": "inv_date",
        "21": "subtotal",
        "22": "total",
        "24": "job_title",
        "56": "product_group",
        "60": "industry",
    },
    "operations": {
        "3":  "qb_record_id",
        "6":  "operation_id",
        "7":  "job_no",
        "8":  "quote_no",
        "9":  "operation_name",
        "10": "machine",
        "11": "department",
        "12": "date_accepted",
        "13": "date_due",
        "14": "qb_customer_id",
        "15": "customer_code",
        "16": "customer_name",
        "17": "am_job",
        "18": "am_customer",
        "19": "job_title",
        "20": "quantity",
        "21": "production_status",
        "22": "cost_price",
        "23": "cost_plus_price",
        "24": "profit_amount",
        "25": "profit_pct",
        "26": "finishing_type",
        "27": "first_invoice_no",
        "28": "first_invoice_date",
        # QB Formula Tags (native from QB)
        "44": "qb_process_tag",
        "45": "qb_capability_tag",
        "46": "qb_machine_tier_tag",
        "47": "qb_row_type_tag",
        "48": "qb_blank_reason_tag",
        "52": "qb_embellishment_tag",
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

    async def query_records_streamed(
        self,
        table_id: str,
        select_fields: list[int],
        where: Optional[str] = None,
        sort_by: Optional[list[dict]] = None,
    ):
        """
        Async generator yielding (page_records, total) one QB page (≤1000 records) at a time.
        Use instead of query_all_records when the table is large — the caller can upsert each
        page immediately rather than buffering all records in memory first.
        """
        skip = 0
        page_size = 1000
        total = None

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
            metadata = result.get("metadata", {})
            total = metadata.get("totalRecords", 0)

            if records:
                logger.info(f"QB stream: page skip={skip} fetched={len(records)} total={total}")
                yield records, total

            skip += len(records)
            if not records or skip >= total:
                break

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
