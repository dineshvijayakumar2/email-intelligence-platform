"""
Admin Data View API Router

Generic table browser for admin users.
Provides read-only access to whitelisted Supabase tables
with search, sort, and pagination.
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Dict, Any
import time
import logging

from ..dependencies.auth import require_role

logger = logging.getLogger(__name__)


def _execute_with_retry(query_builder, max_retries: int = 2, base_delay: float = 1.0):
    """Execute a Supabase query with retry for transient errors (SSL 525, network)."""
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            return query_builder.execute()
        except Exception as e:
            last_error = e
            error_str = str(e)
            is_transient = any(kw in error_str for kw in [
                'SSL handshake failed', '525', '502', '503', '504',
                'Connection reset', 'Connection refused', 'timed out',
                'JSON could not be generated', 'ECONNRESET', 'ETIMEDOUT',
            ])
            if is_transient and attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    f"Transient Supabase error in admin query (attempt {attempt + 1}/{max_retries + 1}), "
                    f"retrying in {delay}s: {error_str[:200]}"
                )
                time.sleep(delay)
                continue
            raise
    raise last_error

router = APIRouter(prefix="/admin", tags=["admin"])

_supabase = None


def init_admin_router(supabase_client):
    """Initialize the router with Supabase client"""
    global _supabase
    _supabase = supabase_client


# ============================================================================
# TABLE CONFIGURATION
# Whitelist of allowed tables with column exclusions and search config.
# Tables NOT listed here cannot be queried (prevents SQL injection).
# ============================================================================

TABLE_CONFIG: Dict[str, Dict[str, Any]] = {
    "emails": {
        "display_name": "Emails",
        "exclude_columns": ["body_html", "body_text", "raw_headers"],
        "search_columns": ["subject", "sender_email", "sender_name"],
        "default_sort": "sent_date",
        "count_column": "id",
    },
    "mailboxes": {
        "display_name": "Mailboxes",
        "exclude_columns": ["connection_config"],
        "search_columns": ["name", "email_address"],
        "default_sort": "created_at",
        "count_column": "id",
    },
    "folders": {
        "display_name": "Folders",
        "exclude_columns": [],
        "search_columns": ["folder_path"],
        "default_sort": "folder_path",
        "count_column": "id",
    },
    "email_categories": {
        "display_name": "Email Categories",
        "exclude_columns": [],
        "search_columns": ["category"],
        "default_sort": "category",
        "count_column": "id",
    },
    "processing_jobs": {
        "display_name": "Processing Jobs",
        "exclude_columns": ["error_log"],
        "search_columns": ["status", "job_type"],
        "default_sort": "created_at",
        "count_column": "id",
    },
    "customer_companies": {
        "display_name": "Customer Companies",
        "exclude_columns": [],
        "search_columns": ["company_name", "industry"],
        "default_sort": "created_at",
        "count_column": "id",
    },
    "customer_contacts": {
        "display_name": "Customer Contacts",
        "exclude_columns": [],
        "search_columns": ["full_name", "email_address", "job_title"],
        "default_sort": "created_at",
        "count_column": "id",
    },
    "customer_recognition_rules": {
        "display_name": "Recognition Rules",
        "exclude_columns": [],
        "search_columns": ["rule_name", "rule_type", "pattern"],
        "default_sort": "created_at",
        "count_column": "id",
    },
    "extraction_jobs": {
        "display_name": "Extraction Jobs",
        "exclude_columns": [],
        "search_columns": ["status", "current_step"],
        "default_sort": "created_at",
        "count_column": "id",
    },
    "email_response_metrics": {
        "display_name": "Response Metrics",
        "exclude_columns": [],
        "search_columns": [],
        "default_sort": "created_at",
        "count_column": "id",
    },
    "thread_status": {
        "display_name": "Thread Status",
        "exclude_columns": [],
        "search_columns": ["subject", "status", "thread_id"],
        "default_sort": "updated_at",
        "count_column": "id",
    },
    "unified_email_rules": {
        "display_name": "Unified Email Rules",
        "exclude_columns": [],
        "search_columns": ["rule_name", "source_type"],
        "default_sort": "created_at",
        "count_column": "id",
    },
    "internal_domains": {
        "display_name": "Internal Domains",
        "exclude_columns": [],
        "search_columns": ["domain"],
        "default_sort": "domain",
        "count_column": "id",
    },
    "free_email_providers": {
        "display_name": "Free Email Providers",
        "exclude_columns": [],
        "search_columns": ["domain"],
        "default_sort": "domain",
        "count_column": "domain",
    },
    "user_profiles": {
        "display_name": "User Profiles",
        "exclude_columns": [],
        "search_columns": ["name", "email"],
        "default_sort": "created_at",
        "count_column": "id",
    },
    "clients": {
        "display_name": "Clients",
        "exclude_columns": ["quickbase_api_token", "printiq_api_key"],
        "search_columns": ["client_name", "client_label", "industry"],
        "default_sort": "created_at",
        "count_column": "id",
    },
    "job_errors": {
        "display_name": "Job Errors",
        "exclude_columns": ["error_stack"],
        "search_columns": ["error_message", "error_type", "error_phase"],
        "default_sort": "created_at",
        "count_column": "id",
    },
    "user_client_assignments": {
        "display_name": "User-Client Assignments",
        "exclude_columns": [],
        "search_columns": [],
        "default_sort": "created_at",
        "count_column": "id",
    },
    "client_manager_assignments": {
        "display_name": "Client Manager Assignments",
        "exclude_columns": [],
        "search_columns": [],
        "default_sort": "created_at",
        "count_column": "id",
    },
}

ALLOWED_TABLES = set(TABLE_CONFIG.keys())


def _strip_excluded_columns(rows: list, table_name: str) -> list:
    """Remove excluded columns from each row."""
    exclude = set(TABLE_CONFIG[table_name].get("exclude_columns", []))
    if not exclude:
        return rows
    return [{k: v for k, v in row.items() if k not in exclude} for row in rows]


def _get_columns_from_rows(rows: list, table_name: str) -> list:
    """Extract column names from first data row, excluding sensitive columns."""
    if not rows:
        return []
    exclude = set(TABLE_CONFIG[table_name].get("exclude_columns", []))
    return [k for k in rows[0].keys() if k not in exclude]


# ============================================================================
# ENDPOINT 1: List available tables with row counts
# ============================================================================

@router.get("/tables")
async def list_tables(
    current_user: dict = Depends(require_role('admin'))
):
    """
    List all available tables with row counts.
    Admin-only endpoint.
    """
    try:
        tables = []
        for table_name, config in TABLE_CONFIG.items():
            try:
                count_col = config.get("count_column", "id")
                count_result = _execute_with_retry(
                    _supabase.table(table_name).select(
                        count_col, count='exact'
                    ).limit(1)
                )
                row_count = count_result.count if count_result.count is not None else 0
            except Exception as e:
                logger.warning(f"Failed to count rows for {table_name}: {e}")
                row_count = -1

            tables.append({
                "table_name": table_name,
                "display_name": config["display_name"],
                "row_count": row_count,
                "searchable": len(config.get("search_columns", [])) > 0,
            })

        tables.sort(key=lambda t: t["display_name"])
        logger.info(f"Listed {len(tables)} tables for admin data view")
        return {"tables": tables}

    except Exception as e:
        logger.error(f"Failed to list tables: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ENDPOINT 2: Get table data with search, sort, pagination
# ============================================================================

@router.get("/tables/{table_name}")
async def get_table_data(
    table_name: str,
    search: str = Query(default="", description="Global search text"),
    sort_by: str = Query(default="", description="Sort column (defaults to table's default)"),
    sort_dir: str = Query(default="desc", description="asc or desc"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(require_role('admin'))
):
    """
    Get paginated data from a whitelisted table.
    Supports global text search, column sorting, and offset pagination.
    """
    if table_name not in ALLOWED_TABLES:
        raise HTTPException(
            status_code=400,
            detail=f"Table '{table_name}' is not available. Allowed tables: {sorted(ALLOWED_TABLES)}"
        )

    try:
        config = TABLE_CONFIG[table_name]
        search_columns = config.get("search_columns", [])
        effective_sort = sort_by if sort_by else config.get("default_sort", "created_at")
        desc = sort_dir.lower() == "desc"

        # --- Build data query ---
        query = _supabase.table(table_name).select('*')

        # Apply global search
        search_term = search.strip().replace('%', r'\%').replace('_', r'\_') if search else ""
        if search_term and search_columns:
            or_conditions = ",".join(
                f"{col}.ilike.%{search_term}%"
                for col in search_columns
            )
            query = query.or_(or_conditions)

        # Apply sorting
        try:
            query = query.order(effective_sort, desc=desc)
        except Exception:
            # Fallback if sort column doesn't exist
            pass

        # Apply pagination
        query = query.range(offset, offset + limit - 1)

        result = _execute_with_retry(query)
        raw_data = result.data or []

        # Strip excluded columns
        data = _strip_excluded_columns(raw_data, table_name)
        columns = _get_columns_from_rows(raw_data, table_name)

        # --- Build count query (same search filter, no pagination) ---
        count_col = config.get("count_column", "id")
        count_query = _supabase.table(table_name).select(count_col, count='exact')

        if search_term and search_columns:
            or_conditions = ",".join(
                f"{col}.ilike.%{search_term}%"
                for col in search_columns
            )
            count_query = count_query.or_(or_conditions)

        count_result = _execute_with_retry(count_query.limit(1))
        total = count_result.count if count_result.count is not None else len(data)

        return {
            "table_name": table_name,
            "display_name": config["display_name"],
            "columns": columns,
            "data": data,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get table data for '{table_name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
