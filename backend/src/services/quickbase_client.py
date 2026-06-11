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
        "92": "customer_key_id",
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
        "85": "has_hot_foil",
        "86": "has_spot_uv",
        "87": "has_special_substrate",
        "88": "has_digital_foil",
        "89": "has_de_emboss",
        "90": "has_raised_ink",
        "91": "has_laser_cut",
        "92": "has_white_ink",
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
    "unique_emails": {
        "3":  "qb_record_id",
        "6":  "email",
        "23": "qb_customer_id",
        "24": "customer_name",
        "44": "first_name",
        "45": "last_name",
        "46": "hide",
        "49": "quality",
        "50": "result",
        "51": "free",
        "53": "email_invalid",
        "70": "customer_type",
        "72": "customer_id_text",
        "128": "embellishments_used",
        "130": "processes_used",
        "131": "capabilities_used",
    },
    "job_status_log": {
        "3":  "qb_record_id",
        "16": "job_no",         # Related Job (FK → qb_jobs.job_no via masterTableKeyFid=7)
        "8":  "old_status",
        "9":  "new_status",
        "1":  "changed_at",     # QB Date Created on the audit row = when the change happened
        "10": "changed_by",     # User field; QB returns display name for `value`
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
        # Reusable client with generous timeout and connection pooling
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=30.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )

    async def close(self):
        """Close the underlying HTTP client."""
        await self._http.aclose()

    async def query_records(
        self,
        table_id: str,
        select_fields: list[int],
        where: Optional[str] = None,
        sort_by: Optional[list[dict]] = None,
        skip: int = 0,
        top: int = 1000,
        max_retries: int = 6,
    ) -> dict[str, Any]:
        """
        Query records from a Quickbase table with retry on transient errors.
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

        import time as _time
        last_err = None
        for attempt in range(max_retries + 1):
            try:
                response = await self._http.post(
                    f"{self.BASE_URL}/records/query",
                    headers=self.headers,
                    json=body,
                )
                response.raise_for_status()
                return response.json()
            except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as e:
                last_err = e
                if attempt < max_retries:
                    # Capped exponential backoff: 1,2,4,8,16,30s (~61s total tolerance).
                    # A full-table sync makes hundreds of sequential page calls over ~70 min,
                    # so it must survive a transient QB outage longer than a few seconds.
                    delay = min(2 ** attempt, 30)
                    logger.warning(f"QB query retry {attempt+1}/{max_retries} (skip={skip}): {e}. Waiting {delay}s...")
                    _time.sleep(delay)
                    continue
                raise
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (502, 503, 504, 525) and attempt < max_retries:
                    last_err = e
                    delay = min(2 ** attempt, 30)
                    logger.warning(f"QB query retry {attempt+1}/{max_retries} (skip={skip}): HTTP {e.response.status_code}. Waiting {delay}s...")
                    _time.sleep(delay)
                    continue
                raise
        raise last_err

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

        Pagination uses skip/top across many sequential calls, so a STABLE sort is required:
        without one, QB's default order can shift between page fetches (e.g. as rows are
        modified mid-sync), causing records to be skipped or fetched twice. When the caller
        doesn't specify a sort, default to Record ID# (field 3) ascending — a built-in,
        unique, immutable key present on every QB table — so each record is visited exactly once.
        """
        if not sort_by:
            sort_by = [{"fieldId": 3, "order": "ASC"}]

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
        response = await self._http.get(
            f"{self.BASE_URL}/fields",
            headers=self.headers,
            params={"tableId": table_id},
        )
        response.raise_for_status()
        return response.json()

    async def test_connection(self) -> bool:
        """Test if the QB connection is valid."""
        try:
            response = await self._http.get(
                f"{self.BASE_URL}/tables",
                headers=self.headers,
                params={"appId": "placeholder"},
            )
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
