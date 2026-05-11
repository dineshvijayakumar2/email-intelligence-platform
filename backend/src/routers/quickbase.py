"""
Quickbase Integration Router — Sync config, trigger sync, view cached data.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from ..models.quickbase import (
    QBSyncConfigCreate,
    QBSyncConfigResponse,
    QBSyncResult,
    QBSyncStatus,
    QBTableSyncLog,
)
from ..services.quickbase_sync import QuickbaseSync
from ..utils.log_stream import set_log_context, clear_log_context

logger = logging.getLogger(__name__)


def _sanitize_search(term: str) -> str:
    """Escape SQL ILIKE wildcards in user-supplied search terms."""
    return term.replace('%', r'\%').replace('_', r'\_')

router = APIRouter(prefix="/quickbase", tags=["quickbase"])

_supabase = None


def _create_sync_supabase():
    """Create a dedicated Supabase client for sync/rematch background tasks.

    This prevents long-running sync operations from saturating the shared
    connection pool used by frontend API requests.
    """
    from supabase import create_client
    url = os.getenv('SUPABASE_URL')
    key = os.getenv('SUPABASE_SERVICE_KEY') or os.getenv('SUPABASE_KEY')
    if not url or not key:
        logger.warning("Cannot create dedicated sync client — falling back to shared client")
        return _supabase
    return create_client(url, key)


import threading

# Per-client sync state: tracks running syncs and cancellation flags
_sync_state: dict[str, dict] = {}  # client_id → {'running': bool, 'cancel': threading.Event}
_sync_state_lock = threading.Lock()


def _get_sync_state(client_id: str) -> dict:
    """Get or create sync state for a client."""
    with _sync_state_lock:
        if client_id not in _sync_state:
            _sync_state[client_id] = {'running': False, 'cancel': threading.Event()}
        return _sync_state[client_id]


def init_quickbase_router(supabase_client):
    """Initialize the Quickbase router with Supabase client."""
    global _supabase
    _supabase = supabase_client


def _get_client_id_from_user(user_id: str) -> Optional[str]:
    """Get first assigned client_id for a user."""
    result = _supabase.table('user_client_assignments').select(
        'client_id'
    ).eq('user_id', user_id).limit(1).execute()
    if result.data:
        return result.data[0]['client_id']
    return None


# --- Config endpoints ---

@router.get("/config", response_model=QBSyncConfigResponse)
async def get_config(client_id: str = Query(...)):
    """Get Quickbase sync configuration for a client (admin-only, token returned as-is)."""
    try:
        result = _supabase.table('qb_sync_config').select('*').eq(
            'client_id', client_id
        ).limit(1).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="No QB config found for this client")

        cfg = result.data[0]

        return QBSyncConfigResponse(
            client_id=cfg['client_id'],
            realm_hostname=cfg['realm_hostname'],
            app_id=cfg['app_id'],
            user_token=cfg.get('user_token_encrypted', ''),
            customers_table_id=cfg['customers_table_id'],
            contacts_table_id=cfg['contacts_table_id'],
            quotes_table_id=cfg['quotes_table_id'],
            jobs_table_id=cfg['jobs_table_id'],
            sales_line_items_table_id=cfg['sales_line_items_table_id'],
            operations_table_id=cfg.get('operations_table_id', 'bvqsudnif'),
            unique_emails_table_id=cfg.get('unique_emails_table_id', 'bvmtc5re6'),
            audit_logs_table_id=cfg.get('audit_logs_table_id', 'bu9yjc3ne'),
            field_mappings=cfg.get('field_mappings'),
            sync_interval_hours=cfg.get('sync_interval_hours', 6),
            last_sync_at=cfg.get('last_sync_at'),
            is_active=cfg.get('is_active', True),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get QB config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/config")
async def upsert_config(client_id: str = Query(...), config: QBSyncConfigCreate = ...):
    """Create or update Quickbase sync configuration."""
    try:
        row = {
            'client_id': client_id,
            'realm_hostname': config.realm_hostname,
            'app_id': config.app_id,
            'customers_table_id': config.customers_table_id,
            'contacts_table_id': config.contacts_table_id,
            'quotes_table_id': config.quotes_table_id,
            'jobs_table_id': config.jobs_table_id,
            'sales_line_items_table_id': config.sales_line_items_table_id,
            'operations_table_id': config.operations_table_id or 'bvqsudnif',
            'unique_emails_table_id': config.unique_emails_table_id or 'bvmtc5re6',
            'audit_logs_table_id': config.audit_logs_table_id or 'bu9yjc3ne',
            'field_mappings': config.field_mappings or {},
            'sync_interval_hours': config.sync_interval_hours,
            'is_active': True,
            'updated_at': datetime.now(timezone.utc).isoformat(),
        }

        if config.user_token:
            # New token provided — store it and activate sync
            row['user_token_encrypted'] = config.user_token
            row['is_active'] = True
        else:
            # Token explicitly cleared — disable sync and wipe token
            existing = _supabase.table('qb_sync_config').select(
                'user_token_encrypted'
            ).eq('client_id', client_id).limit(1).execute()
            if not existing.data:
                raise HTTPException(status_code=400, detail="user_token is required for new config")
            row['user_token_encrypted'] = ''
            row['is_active'] = False

        _supabase.table('qb_sync_config').upsert(
            row, on_conflict='client_id'
        ).execute()

        return {"status": "ok", "message": "QB config saved"}

    except Exception as e:
        logger.error(f"Failed to save QB config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- Sync endpoints ---

VALID_TABLES = {'customers', 'contacts', 'quotes', 'jobs', 'sales_line_items', 'operations', 'unique_emails', 'job_status_log'}


@router.post("/sync", response_model=QBSyncResult)
async def trigger_sync(
    client_id: str = Query(...),
    tables: Optional[str] = Query(None, description="Comma-separated table names to sync (omit for all)"),
    full: bool = Query(False, description="Force full sync instead of incremental"),
    background_tasks: BackgroundTasks = None,
):
    """Trigger a Quickbase sync. Incremental by default (only records modified since last sync).
    Pass full=true to re-sync everything (e.g. after adding a new field mapping)."""
    tables_list: Optional[list[str]] = None
    if tables:
        tables_list = [t.strip() for t in tables.split(',') if t.strip() in VALID_TABLES]
        if not tables_list:
            raise HTTPException(status_code=400, detail=f"Invalid table names. Valid: {', '.join(sorted(VALID_TABLES))}")

    try:
        # Load config
        cfg_result = _supabase.table('qb_sync_config').select('*').eq(
            'client_id', client_id
        ).limit(1).execute()

        if not cfg_result.data:
            raise HTTPException(status_code=404, detail="No QB config found. Set up config first.")

        config = cfg_result.data[0]
        if not config.get('is_active'):
            raise HTTPException(status_code=400, detail="QB sync is disabled for this client")

        state = _get_sync_state(client_id)
        if state['running']:
            # Cancel the existing sync and start a new one
            logger.info(f"Cancelling existing sync for client {client_id}")
            state['cancel'].set()
            # Brief wait for the old task to notice the flag
            import time; time.sleep(0.5)

        state['cancel'].clear()
        state['running'] = True
        cancel_event = state['cancel']

        def _run_sync():
            """Run in thread pool with a dedicated Supabase client."""
            set_log_context(client_id=client_id)
            try:
                sync_sb = _create_sync_supabase()
                loop = asyncio.new_event_loop()
                syncer = QuickbaseSync(sync_sb, config, cancel_event=cancel_event)
                counts = loop.run_until_complete(syncer.sync_all(tables=tables_list, full=full))
                if not cancel_event.is_set():
                    loop.run_until_complete(syncer.propagate_qb_data_to_companies())
                    loop.run_until_complete(syncer.propagate_qb_data_to_contacts())
                loop.close()
                if cancel_event.is_set():
                    logger.info(f"QB sync cancelled for client {client_id}")
                else:
                    logger.info(f"Background QB sync complete: {counts}")
            except Exception as e:
                logger.error(f"Background QB sync failed: {e}")
            finally:
                state['running'] = False
                clear_log_context()

        background_tasks.add_task(_run_sync)

        mode = 'full' if full else 'incremental'
        label = ', '.join(tables_list) if tables_list else 'all tables'
        return QBSyncResult(
            status="started",
            message=f"QB {mode} sync started in background ({label})",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to trigger QB sync: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync/cancel")
async def cancel_sync(client_id: str = Query(...)):
    """Cancel a running QB sync for this client."""
    state = _get_sync_state(client_id)
    if not state['running']:
        return {"status": "ok", "message": "No sync is running"}
    state['cancel'].set()
    return {"status": "ok", "message": "Cancel signal sent — sync will stop after current batch"}


@router.get("/sync-status", response_model=QBSyncStatus)
async def get_sync_status(client_id: str = Query(...)):
    """Get sync status and record counts for a client."""
    try:
        cfg_result = _supabase.table('qb_sync_config').select(
            'client_id, last_sync_at, is_active'
        ).eq('client_id', client_id).limit(1).execute()

        if not cfg_result.data:
            raise HTTPException(status_code=404, detail="No QB config found")

        # Count records per table (gracefully skip tables not yet created)
        counts = {}
        for table in ['qb_customers', 'qb_contacts', 'qb_quotes', 'qb_jobs', 'qb_sales_line_items', 'qb_operations', 'qb_unique_emails', 'qb_job_status_log']:
            try:
                result = _supabase.table(table).select(
                    'id', count='exact'
                ).eq('client_id', client_id).limit(0).execute()
                counts[table.replace('qb_', '')] = result.count or 0
            except Exception:
                counts[table.replace('qb_', '')] = 0

        # Fetch latest sync log entry per table — one query per table for reliability
        # Falls back to MAX(synced_at) from the actual cache table if no log entry exists
        table_logs: list[QBTableSyncLog] = []
        table_name_to_cache = {
            'customers': 'qb_customers', 'contacts': 'qb_contacts',
            'quotes': 'qb_quotes', 'jobs': 'qb_jobs',
            'sales_line_items': 'qb_sales_line_items',
            'operations': 'qb_operations', 'unique_emails': 'qb_unique_emails',
            'job_status_log': 'qb_job_status_log',
        }
        try:
            for tn, cache_table in table_name_to_cache.items():
                try:
                    log_result = _supabase.table('qb_sync_log').select(
                        'table_name, table_id, record_count, synced_at, status, error_message'
                    ).eq('client_id', client_id).eq(
                        'table_name', tn
                    ).order('synced_at', desc=True).limit(1).execute()

                    if log_result.data:
                        row = log_result.data[0]
                        table_logs.append(QBTableSyncLog(
                            table_name=row['table_name'],
                            table_id=row.get('table_id'),
                            record_count=counts.get(tn, 0),
                            synced_at=row.get('synced_at'),
                            status=row.get('status', 'success'),
                            error_message=row.get('error_message'),
                        ))
                    else:
                        # No log entry — fall back to most recent synced_at from the cache table
                        try:
                            fallback = _supabase.table(cache_table).select(
                                'synced_at'
                            ).eq('client_id', client_id).order(
                                'synced_at', desc=True
                            ).limit(1).execute()
                            if fallback.data and fallback.data[0].get('synced_at'):
                                table_logs.append(QBTableSyncLog(
                                    table_name=tn,
                                    record_count=counts.get(tn, 0),
                                    synced_at=fallback.data[0]['synced_at'],
                                    status='success',
                                ))
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception as log_err:
            logger.warning(f"qb_sync_log not available (run migration 023): {log_err}")

        cfg = cfg_result.data[0]
        return QBSyncStatus(
            client_id=cfg['client_id'],
            last_sync_at=cfg.get('last_sync_at'),
            is_active=cfg.get('is_active', True),
            record_counts=counts,
            table_logs=table_logs,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get sync status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/fields")
async def get_table_fields(
    client_id: str = Query(...),
    table: str = Query(...),
    force: bool = Query(False, description="Force re-fetch from QB, bypassing cache"),
):
    """
    Get field definitions for a QB table.
    Returns cached data from qb_field_definitions unless force=true.
    On force or cache miss, fetches from QB and writes through to the cache.
    """
    table_map = {
        'customers': 'customers_table_id',
        'contacts': 'contacts_table_id',
        'quotes': 'quotes_table_id',
        'jobs': 'jobs_table_id',
        'sales_line_items': 'sales_line_items_table_id',
        'operations': 'operations_table_id',
        'unique_emails': 'unique_emails_table_id',
        'job_status_log': 'audit_logs_table_id',
    }
    if table not in table_map:
        raise HTTPException(status_code=400, detail=f"Unknown table: {table}")

    try:
        # --- Resolve QB table ID from config (needed for both cache key and QB call) ---
        cfg_result = _supabase.table('qb_sync_config').select('*').eq(
            'client_id', client_id
        ).limit(1).execute()
        if not cfg_result.data:
            raise HTTPException(status_code=404, detail="No QB config found for this client")
        cfg = cfg_result.data[0]
        qb_table_id = cfg[table_map[table]]

        # --- Try cache first (unless force refresh) ---
        if not force:
            cached = _supabase.table('qb_field_definitions').select('*').eq(
                'client_id', client_id
            ).eq('table_id', qb_table_id).order('field_id').execute()

            if cached.data:
                synced_at = cached.data[0].get('synced_at')
                fields = [{"id": r['field_id'], "label": r['field_label'], "type": r.get('field_type')} for r in cached.data]
                return {"fields": fields, "synced_at": synced_at, "from_cache": True}

            # --- Cache miss: check for local bundled field schema (avoids requiring live QB call) ---
            project_root = Path(__file__).parent.parent.parent.parent
            local_seed = project_root / 'quickbase-integration' / f'operations_{qb_table_id}_fields_list.json'
            if local_seed.exists():
                raw = json.loads(local_seed.read_text())
                fields = [{"id": f["id"], "label": f["label"], "type": f.get("fieldType")} for f in raw]
                now = datetime.now(timezone.utc).isoformat()
                rows = [
                    {"client_id": client_id, "table_id": qb_table_id, "table_name": table,
                     "field_id": f["id"], "field_label": f["label"], "field_type": f.get("fieldType"),
                     "synced_at": now}
                    for f in raw
                ]
                if rows:
                    _supabase.table('qb_field_definitions').upsert(
                        rows, on_conflict='client_id,table_id,field_id'
                    ).execute()
                logger.info(f"QB fields seeded from local JSON: table={table} count={len(fields)}")
                return {"fields": fields, "synced_at": now, "from_cache": False}

        # --- Cache miss or force: fetch from QB ---
        from ..services.quickbase_client import QuickbaseClient
        qb = QuickbaseClient(
            realm_hostname=cfg['realm_hostname'],
            user_token=cfg['user_token_encrypted'],
        )
        fields = await qb.get_fields(qb_table_id)

        # --- Write through to cache ---
        now = datetime.now(timezone.utc).isoformat()
        rows = [
            {
                "client_id": client_id,
                "table_id": qb_table_id,
                "table_name": table,          # logical name e.g. "customers"
                "field_id": f["id"],
                "field_label": f["label"],
                "field_type": f.get("type"),
                "synced_at": now,
            }
            for f in fields
        ]
        if rows:
            _supabase.table('qb_field_definitions').upsert(
                rows, on_conflict='client_id,table_id,field_id'
            ).execute()
            # Prune stale fields no longer in QB
            live_ids = [f["id"] for f in fields]
            _supabase.table('qb_field_definitions').delete().eq(
                'client_id', client_id
            ).eq('table_id', qb_table_id).not_.in_('field_id', live_ids).execute()

        logger.info(f"QB fields synced: client={client_id} table_id={qb_table_id} count={len(fields)}")
        return {"fields": fields, "synced_at": now, "from_cache": False}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get QB fields: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- Data browsing endpoints ---

# Default sort per table — no hardcoded column whitelist.
# Any column name is accepted; PostgREST returns 400 for invalid ones (caught in try/except).
_QB_DEFAULT_SORT = {
    'customers': ('customer_name', False),
    'contacts': ('surname', False),
    'quotes': ('date_created', True),
    'jobs': ('accepted_date', True),
    'sales_line_items': ('inv_date', True),
    'operations': ('date_accepted', True),
    'unique_emails': ('email', False),
    'job_status_log': ('changed_at', True),
}


def _qb_sort(table_key: str, sort_by: Optional[str], sort_dir: Optional[str]):
    """Resolve sort column and direction. Accepts any column — invalid ones fall back to default."""
    default_col, default_desc = _QB_DEFAULT_SORT.get(table_key, ('id', False))
    col = sort_by.strip() if sort_by and sort_by.strip() else default_col
    desc = (sort_dir or ('desc' if default_desc else 'asc')).lower() != 'asc'
    return col, desc


@router.get("/customers")
async def list_qb_customers(
    client_id: str = Query(...),
    search: str = Query('', description="Search QB customer name"),
    matched: Optional[bool] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    sort_by: Optional[str] = Query(default=None),
    sort_dir: Optional[str] = Query(default=None),
):
    """List cached QB customers with optional search and match filter."""
    try:
        query = _supabase.table('qb_customers').select(
            '*, customer_companies(company_name)',
            count='exact'
        ).eq('client_id', client_id)

        if search and len(search) >= 2:
            query = query.ilike('customer_name', f'%{_sanitize_search(search)}%')

        if matched is True:
            query = query.not_.is_('matched_company_id', 'null')
        elif matched is False:
            query = query.is_('matched_company_id', 'null')

        col, desc = _qb_sort('customers', sort_by, sort_dir)
        result = query.order(col, desc=desc).range(offset, offset + limit - 1).execute()

        customers = []
        for row in (result.data or []):
            company_data = row.pop('customer_companies', None)
            row['matched_company_name'] = company_data.get('company_name') if company_data else None
            customers.append(row)

        return {
            "customers": customers,
            "total": result.count or len(customers),
        }

    except Exception as e:
        logger.error(f"Failed to list QB customers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/contacts")
async def list_qb_contacts(
    client_id: str = Query(...),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    search: Optional[str] = Query(default=None),
    sort_by: Optional[str] = Query(default=None),
    sort_dir: Optional[str] = Query(default=None),
):
    """List cached QB contacts."""
    try:
        query = _supabase.table('qb_contacts').select('*', count='exact').eq('client_id', client_id)
        if search:
            s = _sanitize_search(search)
            query = query.or_(f"first_name.ilike.%{s}%,surname.ilike.%{s}%,email.ilike.%{s}%")
        col, desc = _qb_sort('contacts', sort_by, sort_dir)
        result = query.order(col, desc=desc).range(offset, offset + limit - 1).execute()
        return {"contacts": result.data or [], "total": result.count or 0}
    except Exception as e:
        logger.error(f"Failed to list QB contacts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quotes")
async def list_qb_quotes(
    client_id: str = Query(...),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    search: Optional[str] = Query(default=None),
    sort_by: Optional[str] = Query(default=None),
    sort_dir: Optional[str] = Query(default=None),
):
    """List cached QB quotes."""
    try:
        query = _supabase.table('qb_quotes').select('*', count='exact').eq('client_id', client_id)
        if search:
            s = _sanitize_search(search)
            query = query.or_(f"quote_no.ilike.%{s}%,contact_name.ilike.%{s}%")
        col, desc = _qb_sort('quotes', sort_by, sort_dir)
        result = query.order(col, desc=desc).range(offset, offset + limit - 1).execute()
        return {"quotes": result.data or [], "total": result.count or 0}
    except Exception as e:
        logger.error(f"Failed to list QB quotes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs")
async def list_qb_jobs(
    client_id: str = Query(...),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    search: Optional[str] = Query(default=None),
    sort_by: Optional[str] = Query(default=None),
    sort_dir: Optional[str] = Query(default=None),
):
    """List cached QB jobs."""
    try:
        query = _supabase.table('qb_jobs').select('*', count='exact').eq('client_id', client_id)
        if search:
            s = _sanitize_search(search)
            query = query.or_(f"job_no.ilike.%{s}%,job_status.ilike.%{s}%")
        col, desc = _qb_sort('jobs', sort_by, sort_dir)
        result = query.order(col, desc=desc).range(offset, offset + limit - 1).execute()
        return {"jobs": result.data or [], "total": result.count or 0}
    except Exception as e:
        logger.error(f"Failed to list QB jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sales-line-items")
async def list_qb_sales_line_items(
    client_id: str = Query(...),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    search: Optional[str] = Query(default=None),
    sort_by: Optional[str] = Query(default=None),
    sort_dir: Optional[str] = Query(default=None),
):
    """List cached QB sales line items."""
    try:
        query = _supabase.table('qb_sales_line_items').select('*', count='exact').eq('client_id', client_id)
        if search:
            s = _sanitize_search(search)
            query = query.or_(f"customer_name.ilike.%{s}%,job_no.ilike.%{s}%,invoice_no.ilike.%{s}%")
        col, desc = _qb_sort('sales_line_items', sort_by, sort_dir)
        result = query.order(col, desc=desc).range(offset, offset + limit - 1).execute()
        return {"sales_line_items": result.data or [], "total": result.count or 0}
    except Exception as e:
        logger.error(f"Failed to list QB sales line items: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/operations")
async def list_qb_operations(
    client_id: str = Query(...),
    company_id: Optional[str] = Query(default=None, description="Filter by matched company UUID"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    search: Optional[str] = Query(default=None),
    sort_by: Optional[str] = Query(default=None),
    sort_dir: Optional[str] = Query(default=None),
):
    """List cached QB operations (product/service detail per job)."""
    try:
        query = _supabase.table('qb_operations').select('*', count='exact').eq('client_id', client_id)
        if company_id:
            query = query.eq('matched_company_id', company_id)
        if search:
            s = _sanitize_search(search)
            query = query.or_(
                f"operation_name.ilike.%{s}%,department.ilike.%{s}%,customer_name.ilike.%{s}%"
            )
        col, desc = _qb_sort('operations', sort_by, sort_dir)
        result = query.order(col, desc=desc).range(offset, offset + limit - 1).execute()
        return {"operations": result.data or [], "total": result.count or 0}
    except Exception as e:
        logger.error(f"Failed to list QB operations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/unique-emails")
async def list_qb_unique_emails(
    client_id: str = Query(...),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    search: Optional[str] = Query(default=None),
    sort_by: Optional[str] = Query(default=None),
    sort_dir: Optional[str] = Query(default=None),
):
    """List cached QB unique emails."""
    try:
        query = _supabase.table('qb_unique_emails').select('*', count='exact').eq('client_id', client_id)
        if search:
            s = _sanitize_search(search)
            query = query.or_(f"email.ilike.%{s}%,customer_name.ilike.%{s}%,first_name.ilike.%{s}%,last_name.ilike.%{s}%")
        col, desc = _qb_sort('unique_emails', sort_by, sort_dir)
        result = query.order(col, desc=desc).range(offset, offset + limit - 1).execute()
        return {"unique_emails": result.data or [], "total": result.count or 0}
    except Exception as e:
        logger.error(f"Failed to list QB unique emails: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/job-status-log")
async def list_qb_job_status_log(
    client_id: str = Query(...),
    job_no: Optional[str] = Query(default=None, description="Filter to one job's timeline"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    search: Optional[str] = Query(default=None),
    sort_by: Optional[str] = Query(default=None),
    sort_dir: Optional[str] = Query(default=None),
):
    """List cached QB job-status audit rows (filtered to Field Name = 'Job Status')."""
    try:
        query = _supabase.table('qb_job_status_log').select('*', count='exact').eq('client_id', client_id)
        if job_no:
            query = query.eq('job_no', job_no)
        if search:
            s = _sanitize_search(search)
            query = query.or_(
                f"job_no.ilike.%{s}%,old_status.ilike.%{s}%,new_status.ilike.%{s}%,changed_by.ilike.%{s}%"
            )
        col, desc = _qb_sort('job_status_log', sort_by, sort_dir)
        result = query.order(col, desc=desc).range(offset, offset + limit - 1).execute()
        return {"job_status_log": result.data or [], "total": result.count or 0}
    except Exception as e:
        logger.error(f"Failed to list QB job status log: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/recommendations/recompute-affinities")
async def recompute_affinities(
    client_id: str = Query(...),
    background_tasks: BackgroundTasks = None,
):
    """
    Recompute product_affinities for a client from all qb_operations.
    Triggered automatically after QB sync; can also be called manually.
    """
    try:
        from ..services.recommendation_engine import RecommendationEngine

        def _run():
            """Run in thread pool to avoid blocking the event loop."""
            set_log_context(client_id=client_id)
            try:
                engine = RecommendationEngine(_supabase, client_id)
                count = engine.recompute_affinities()
                logger.info(f"Affinity recompute done: {count} pairs for client {client_id}")
            except Exception as e:
                logger.error(f"Affinity recompute failed: {e}")
            finally:
                clear_log_context()

        if background_tasks:
            background_tasks.add_task(_run)
            return {"status": "accepted", "message": "Affinity recomputation started in background"}
        else:
            engine = RecommendationEngine(_supabase, client_id)
            count = engine.recompute_affinities()
            return {"status": "completed", "affinity_pairs_stored": count}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rematch")
async def rematch_qb_data(
    client_id: str = Query(...),
    reset: bool = Query(False, description="Clear all existing matches before re-matching"),
    background_tasks: BackgroundTasks = None,
):
    """Re-run QB matching + propagation without re-syncing from QuickBase API.

    Default: processes only unmatched records (safe to interrupt and resume).
    Pass reset=true to clear all matches and rebuild from scratch.
    """
    try:
        cfg_result = _supabase.table('qb_sync_config').select('*').eq(
            'client_id', client_id
        ).limit(1).execute()
        if not cfg_result.data:
            raise HTTPException(status_code=404, detail="No QB config found")

        config = cfg_result.data[0]
        do_reset = reset

        state = _get_sync_state(client_id)
        if state['running']:
            state['cancel'].set()
            import time; time.sleep(0.5)
        state['cancel'].clear()
        state['running'] = True
        cancel_event = state['cancel']

        def _run_rematch():
            """Run in thread pool with a dedicated Supabase client."""
            set_log_context(client_id=client_id)
            try:
                sync_sb = _create_sync_supabase()
                loop = asyncio.new_event_loop()
                syncer = QuickbaseSync(sync_sb, config, cancel_event=cancel_event)

                # Step 0: Sync unique emails (get fresh data from QB)
                logger.info("QB rematch — Step 0: Sync unique emails from QB")
                loop.run_until_complete(syncer.sync_unique_emails())

                # Step 1: Optionally clear existing matches
                if do_reset:
                    logger.info("QB rematch — Step 1: Clearing ALL existing matches (reset=true)")
                    sync_sb.table('qb_customers').update({
                        'matched_company_id': None
                    }).eq('client_id', client_id).not_.is_('matched_company_id', 'null').execute()
                    sync_sb.table('customer_companies').update({
                        'qb_customer_id': None,
                        'qb_customer_code': None,
                        'qb_match_method': None,
                        'qb_matched_at': None,
                    }).eq('client_id', client_id).not_.is_('qb_match_method', 'null').execute()
                else:
                    logger.info("QB rematch — Step 1: Skipped (incremental mode, processing unmatched only)")

                if cancel_event.is_set():
                    logger.info("QB rematch cancelled"); return

                # Step 2: Email-based matching (Pass 0 — highest priority)
                logger.info("QB rematch — Step 2: Email-based matching via unique emails")
                e1 = loop.run_until_complete(syncer.match_companies_via_unique_emails())

                if cancel_event.is_set():
                    logger.info("QB rematch cancelled after email matching"); return

                # Step 3: Name-based matching (Pass 1-3 for remaining unmatched)
                logger.info("QB rematch — Step 3: Name-based matching (exact + domain + fuzzy)")
                match_stats = loop.run_until_complete(syncer.match_to_companies())

                if cancel_event.is_set():
                    logger.info("QB rematch cancelled after name matching"); return

                # Step 4: Contact email matching
                logger.info("QB rematch — Step 4: Match contacts by email")
                c2 = loop.run_until_complete(syncer.match_to_contacts())

                # Step 5: Chain-match via contacts
                logger.info("QB rematch — Step 5: Chain-match customers via contacts")
                c3 = loop.run_until_complete(syncer.match_customers_via_contacts())

                # Step 6: Propagate QB data (companies + contacts)
                logger.info("QB rematch — Step 6: Propagate QB data to companies")
                c4 = loop.run_until_complete(syncer.propagate_qb_data_to_companies())
                logger.info("QB rematch — Step 6b: Propagate QB data to contacts")
                c5 = loop.run_until_complete(syncer.propagate_qb_data_to_contacts())
                loop.close()

                logger.info(
                    f"QB rematch complete: email_lookup={e1}, name_based={match_stats}, "
                    f"{c2} contacts, {c3} chain-matched, {c4} companies propagated, "
                    f"{c5} contact rows propagated"
                )
            except Exception as e:
                logger.error(f"Rematch failed: {e}")
            finally:
                state['running'] = False
                clear_log_context()

        if background_tasks:
            background_tasks.add_task(_run_rematch)
            mode = "reset" if do_reset else "incremental"
            return {"status": "accepted", "message": f"Re-matching started ({mode} mode)"}
        else:
            _run_rematch()
            return {"status": "completed", "message": "Re-matching completed"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.get("/health")
async def qb_health(client_id: str = Query(...)):
    """QB cleanup dashboard: single RPC returns all stats in one DB round-trip."""
    try:
        cfg = _supabase.table('qb_sync_config').select('client_id').eq(
            'client_id', client_id
        ).limit(1).execute()
        if not cfg.data:
            return {"qb_configured": False}

        resp = _supabase.rpc('qb_cleanup_dashboard_stats', {
            'p_client_id': client_id
        }).execute()
        data = resp.data or {}
        data['qb_configured'] = True
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.get("/match-preview")
async def match_preview(client_id: str = Query(...)):
    """Preview proposed company matches (unmatched QB customers vs existing companies)."""
    try:
        # Get unmatched QB customers
        qb_result = _supabase.table('qb_customers').select(
            'id, customer_name, customer_tier, total_invoiced'
        ).eq('client_id', client_id).is_('matched_company_id', 'null').execute()

        # Get all companies
        company_result = _supabase.table('customer_companies').select(
            'id, company_name'
        ).eq('client_id', client_id).execute()

        companies = {
            c['company_name'].strip().lower(): {'id': c['id'], 'name': c['company_name']}
            for c in (company_result.data or [])
            if c.get('company_name')
        }

        previews = []
        for qb in (qb_result.data or []):
            name = (qb.get('customer_name') or '').strip().lower()
            match = companies.get(name)
            if not match:
                for suffix in [' pty ltd', ' pty. ltd.', ' ltd', ' inc', ' llc', ' corp']:
                    clean = name.rstrip('.').removesuffix(suffix).strip()
                    match = companies.get(clean)
                    if match:
                        break

            previews.append({
                'qb_id': qb['id'],
                'qb_name': qb['customer_name'],
                'qb_tier': qb.get('customer_tier'),
                'qb_revenue': qb.get('total_invoiced'),
                'matched_company_id': match['id'] if match else None,
                'matched_company_name': match['name'] if match else None,
                'match_type': 'exact' if match else 'none',
            })

        return {
            "previews": previews,
            "total_unmatched": len(qb_result.data or []),
            "proposed_matches": sum(1 for p in previews if p['matched_company_id']),
        }

    except Exception as e:
        logger.error(f"Failed to generate match preview: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- Match candidate review endpoints ---


@router.get("/match-candidates")
async def list_match_candidates(
    client_id: str = Query(...),
    reviewed: Optional[bool] = Query(None, description="Filter by review status"),
    search: Optional[str] = Query(None, description="Search QB or SB company name"),
    sort_by: str = Query('match_score', description="Column to sort by"),
    sort_desc: bool = Query(True, description="Sort descending"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List fuzzy match candidates for review."""
    ALLOWED_SORTS = {'match_score', 'qb_name', 'sb_company_name', 'created_at'}
    sort_col = sort_by if sort_by in ALLOWED_SORTS else 'match_score'
    sort_in_memory = sort_by in ('total_invoiced', 'sb_total_emails')

    try:
        q = _supabase.table('qb_match_candidates').select(
            'id, sb_company_id, sb_company_name, qb_record_id, qb_customer_id, '
            'qb_name, match_score, match_method, reviewed, accepted, '
            'reviewed_by, reviewed_at, created_at'
        ).eq('client_id', client_id)

        if reviewed is not None:
            q = q.eq('reviewed', reviewed)

        if search and search.strip():
            q = q.or_(f"qb_name.ilike.%{search.strip()}%,sb_company_name.ilike.%{search.strip()}%")

        if sort_in_memory:
            q = q.order('match_score', desc=True)
            result = q.range(0, 999).execute()
        else:
            q = q.order(sort_col, desc=sort_desc)
            result = q.range(offset, offset + limit - 1).execute()

        candidates = result.data or []

        total_q = _supabase.table('qb_match_candidates').select(
            'id', count='exact'
        ).eq('client_id', client_id)
        if reviewed is not None:
            total_q = total_q.eq('reviewed', reviewed)
        if search and search.strip():
            total_q = total_q.or_(f"qb_name.ilike.%{search.strip()}%,sb_company_name.ilike.%{search.strip()}%")
        total_result = total_q.limit(0).execute()

        # Enrich candidates with QB revenue + SB email count
        if candidates:
            qb_record_ids = list({c['qb_record_id'] for c in candidates if c.get('qb_record_id')})
            sb_company_ids = list({c['sb_company_id'] for c in candidates if c.get('sb_company_id')})

            qb_revenue_map: dict = {}
            if qb_record_ids:
                for i in range(0, len(qb_record_ids), 500):
                    batch = qb_record_ids[i:i + 500]
                    qb_resp = _supabase.table('qb_customers').select(
                        'qb_record_id, total_invoiced'
                    ).eq('client_id', client_id).in_('qb_record_id', batch).execute()
                    for r in (qb_resp.data or []):
                        if r.get('qb_record_id'):
                            qb_revenue_map[r['qb_record_id']] = r.get('total_invoiced')

            sb_emails_map: dict = {}
            if sb_company_ids:
                for i in range(0, len(sb_company_ids), 500):
                    batch = sb_company_ids[i:i + 500]
                    sb_resp = _supabase.table('customer_companies').select(
                        'id, total_emails'
                    ).in_('id', batch).execute()
                    for r in (sb_resp.data or []):
                        if r.get('id'):
                            sb_emails_map[r['id']] = r.get('total_emails') or 0

            for c in candidates:
                c['qb_total_revenue'] = qb_revenue_map.get(c.get('qb_record_id'))
                c['sb_total_emails'] = sb_emails_map.get(c.get('sb_company_id'), 0)

        if sort_in_memory:
            if sort_by == 'sb_total_emails':
                candidates.sort(key=lambda c: int(c.get('sb_total_emails') or 0), reverse=sort_desc)
            else:
                candidates.sort(key=lambda c: float(c.get('qb_total_revenue') or 0), reverse=sort_desc)
            candidates = candidates[offset:offset + limit]

        return {
            "candidates": candidates,
            "total": total_result.count or 0,
            "limit": limit,
            "offset": offset,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.get("/qb-customers-browse")
async def browse_qb_customers(
    client_id: str = Query(...),
    view: str = Query('candidates', description="'matched' | 'candidates' | 'unmatched'"),
    search: Optional[str] = Query(None, description="Search by customer name"),
    method: Optional[str] = Query(None, description="Filter by match method (e.g. email_lookup, exact_name)"),
    sort_by: str = Query('total_invoiced', description="Sort column"),
    sort_desc: bool = Query(True),
    limit: int = Query(30, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Browse QB customers by match status — matched, staged candidates, or unmatched."""
    try:
        if view == 'matched':
            q = _supabase.table('qb_customers').select(
                'id, qb_record_id, customer_name, total_invoiced, matched_company_id'
            ).eq('client_id', client_id).not_.is_('matched_company_id', 'null')
            if search and search.strip():
                q = q.ilike('customer_name', f'%{search.strip()}%')

            in_memory = sort_by == 'sb_total_emails' or bool(method)
            sort_col = sort_by if sort_by in {'total_invoiced', 'customer_name'} else 'total_invoiced'
            q = q.order(sort_col, desc=sort_desc)

            if not in_memory:
                total_q = _supabase.table('qb_customers').select(
                    'id', count='exact'
                ).eq('client_id', client_id).not_.is_('matched_company_id', 'null')
                if search and search.strip():
                    total_q = total_q.ilike('customer_name', f'%{search.strip()}%')
                total_q = total_q.limit(0).execute()

            if in_memory:
                all_rows = []
                fetch_offset = 0
                while True:
                    batch_result = q.range(fetch_offset, fetch_offset + 999).execute()
                    all_rows.extend(batch_result.data or [])
                    if len(batch_result.data or []) < 1000:
                        break
                    fetch_offset += 1000
                rows = all_rows
            else:
                result = q.range(offset, offset + limit - 1).execute()
                rows = result.data or []

            # Enrich with company names + match method + email counts
            company_ids = list({r['matched_company_id'] for r in rows if r.get('matched_company_id')})
            company_map: dict = {}
            for i in range(0, len(company_ids), 500):
                batch = company_ids[i:i + 500]
                resp = _supabase.table('customer_companies').select(
                    'id, company_name, qb_match_method, total_emails'
                ).in_('id', batch).execute()
                for c in (resp.data or []):
                    company_map[c['id']] = c

            items = []
            for r in rows:
                cc = company_map.get(r.get('matched_company_id'), {})
                row_method = cc.get('qb_match_method')
                if method and row_method != method:
                    continue
                items.append({
                    'id': r['id'],
                    'qb_record_id': r.get('qb_record_id'),
                    'qb_name': r.get('customer_name'),
                    'qb_total_revenue': r.get('total_invoiced'),
                    'match_status': 'matched',
                    'match_method': row_method,
                    'match_score': {'email_lookup': 100, 'contact_chain': 80, 'exact_name': 75, 'domain_root': 65, 'fuzzy': 60}.get(row_method or '', 50),
                    'sb_company_id': r.get('matched_company_id'),
                    'sb_company_name': cc.get('company_name'),
                    'sb_total_emails': cc.get('total_emails') or 0,
                    'candidate_id': None,
                })

            if in_memory:
                if sort_by == 'sb_total_emails':
                    items.sort(key=lambda x: int(x.get('sb_total_emails') or 0), reverse=sort_desc)
                total_count = len(items)
                items = items[offset:offset + limit]
                return {"items": items, "total": total_count}

            return {"items": items, "total": total_q.count or 0}

        elif view == 'unmatched':
            q = _supabase.table('qb_customers').select(
                'id, qb_record_id, customer_name, total_invoiced'
            ).eq('client_id', client_id).is_('matched_company_id', 'null')
            if search and search.strip():
                q = q.ilike('customer_name', f'%{search.strip()}%')

            sort_col = sort_by if sort_by in {'total_invoiced', 'customer_name'} else 'total_invoiced'
            q = q.order(sort_col, desc=sort_desc)

            total_q = _supabase.table('qb_customers').select(
                'id', count='exact'
            ).eq('client_id', client_id).is_('matched_company_id', 'null')
            if search and search.strip():
                total_q = total_q.ilike('customer_name', f'%{search.strip()}%')
            total_q = total_q.limit(0).execute()

            result = q.range(offset, offset + limit - 1).execute()
            rows = result.data or []

            items = []
            for r in rows:
                items.append({
                    'id': r['id'],
                    'qb_record_id': r.get('qb_record_id'),
                    'qb_name': r.get('customer_name'),
                    'qb_total_revenue': r.get('total_invoiced'),
                    'match_status': 'unmatched',
                    'match_method': None,
                    'match_score': None,
                    'sb_company_id': None,
                    'sb_company_name': None,
                    'sb_total_emails': 0,
                    'candidate_id': None,
                })

            return {"items": items, "total": total_q.count or 0}

        else:
            # Candidates view — delegate then normalize to {items, total} shape
            effective_sort = sort_by if sort_by in {'match_score', 'qb_name', 'sb_company_name', 'created_at', 'total_invoiced', 'sb_total_emails'} else 'match_score'
            result = await list_match_candidates(
                client_id=client_id,
                reviewed=False,
                search=search,
                sort_by=effective_sort,
                sort_desc=sort_desc,
                limit=limit,
                offset=offset,
            )
            items = []
            for c in (result.get('candidates') or []):
                items.append({
                    'id': c['id'],
                    'qb_record_id': c.get('qb_record_id'),
                    'qb_name': c.get('qb_name'),
                    'qb_total_revenue': c.get('qb_total_revenue'),
                    'match_status': 'candidate',
                    'match_method': c.get('match_method'),
                    'match_score': c.get('match_score'),
                    'sb_company_id': c.get('sb_company_id'),
                    'sb_company_name': c.get('sb_company_name'),
                    'sb_total_emails': c.get('sb_total_emails', 0),
                    'candidate_id': c['id'],
                    'qb_customer_id': c.get('qb_customer_id'),
                })
            return {"items": items, "total": result.get('total', 0)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.post("/link-company")
async def link_company_to_qb(
    client_id: str = Query(...),
    sb_company_id: str = Query(..., description="Supabase customer_companies.id"),
    qb_record_id: str = Query(..., description="QB customers qb_record_id"),
):
    """Manually link an SB company to a QB customer. Sets matched_company_id on
    qb_customers and writes match metadata + QB enrichment to customer_companies."""
    try:
        now = datetime.now(timezone.utc).isoformat()

        # Set matched_company_id on qb_customers
        _supabase.table('qb_customers').update({
            'matched_company_id': sb_company_id
        }).eq('client_id', client_id).eq('qb_record_id', qb_record_id).execute()

        # Write match metadata on customer_companies
        _supabase.table('customer_companies').update({
            'qb_customer_id': qb_record_id,
            'qb_match_method': 'manual',
            'qb_matched_at': now,
        }).eq('id', sb_company_id).execute()

        # Propagate QB financial data for this one company
        try:
            qb_data = _supabase.table('qb_customers').select(
                'customer_status, customer_tier, account_manager, total_invoiced, '
                'invoiced_ty, invoiced_ly, growth_90d, days_since_last_invoice, '
                'recency_days, customer_code'
            ).eq('client_id', client_id).eq('qb_record_id', qb_record_id).limit(1).execute()

            if qb_data.data:
                qb = qb_data.data[0]
                from ..services.quickbase_sync import _derive_growth, _derive_tier, _parse_recency_html
                ty = qb.get('invoiced_ty')
                ly = qb.get('invoiced_ly')
                total = qb.get('total_invoiced')
                enrich = {
                    'qb_customer_type': qb.get('customer_status'),
                    'qb_tier': qb.get('customer_tier') or _derive_tier(total),
                    'qb_total_revenue': total,
                    'qb_invoiced_ty': ty,
                    'qb_invoiced_ly': ly,
                    'qb_growth_90d': qb.get('growth_90d') or _derive_growth(ty, ly),
                    'qb_days_since_last_invoice': _parse_recency_html(
                        qb.get('days_since_last_invoice') or qb.get('recency_days')
                    ),
                    'qb_account_manager': qb.get('account_manager'),
                    'qb_customer_code': qb.get('customer_code'),
                }
                enrich = {k: v for k, v in enrich.items() if v is not None}
                if enrich:
                    _supabase.table('customer_companies').update(enrich).eq('id', sb_company_id).execute()
        except Exception as e:
            logger.warning(f"link-company propagation failed (non-critical): {e}")

        return {"status": "linked", "sb_company_id": sb_company_id, "qb_record_id": qb_record_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.post("/link-contact")
async def link_contact_to_qb(
    client_id: str = Query(...),
    sb_contact_id: str = Query(..., description="Supabase customer_contacts.id"),
    qb_record_id: str = Query(..., description="QB contacts qb_record_id"),
):
    """Manually link an SB contact to a QB contact."""
    try:
        _supabase.table('qb_contacts').update({
            'matched_contact_id': sb_contact_id
        }).eq('client_id', client_id).eq('qb_record_id', qb_record_id).execute()

        return {"status": "linked", "sb_contact_id": sb_contact_id, "qb_record_id": qb_record_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.get("/companies-lookup")
async def companies_lookup(
    client_id: str = Query(...),
    search: str = Query('', description="Search by company name"),
    limit: int = Query(50, ge=1, le=500),
):
    """Fast company lookup for the match selector. Returns id + name only."""
    try:
        q = _supabase.table('customer_companies').select(
            'id, company_name'
        ).eq('client_id', client_id).order('company_name')

        if search and len(search) >= 2:
            q = q.ilike('company_name', f'%{_sanitize_search(search)}%')

        result = q.limit(limit).execute()
        return {"companies": result.data or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.post("/match-candidates/{candidate_id}/review")
async def review_match_candidate(
    candidate_id: str,
    accepted: bool = Query(..., description="Accept (true) or skip (false) this candidate"),
    sb_company_id: str = Query(None, description="Override: map to this SB company instead of the suggested one"),
    user_id: str = Query(None, description="Reviewer user ID"),
    background_tasks: BackgroundTasks = None,
):
    """Confirm or skip a match candidate.

    When accepted, the QB customer is linked to the SB company. If sb_company_id is provided,
    it overrides the fuzzy suggestion — allowing manual mapping to any SB company.
    """
    try:
        now = datetime.now(timezone.utc).isoformat()

        # Update candidate review status
        update_payload: dict = {
            'reviewed': True,
            'accepted': accepted,
            'reviewed_by': user_id,
            'reviewed_at': now,
        }
        # If user picked a different company, update the candidate record too
        if sb_company_id and accepted:
            update_payload['sb_company_id'] = sb_company_id

        _supabase.table('qb_match_candidates').update(update_payload).eq('id', candidate_id).execute()

        # If accepted, promote the match immediately
        if accepted:
            candidate = _supabase.table('qb_match_candidates').select(
                'client_id, sb_company_id, sb_company_name, qb_record_id, qb_customer_id, qb_name'
            ).eq('id', candidate_id).limit(1).execute()

            if candidate.data:
                c = candidate.data[0]
                target_company_id = sb_company_id or c['sb_company_id']
                method = 'manual' if sb_company_id else 'fuzzy'

                # Set matched_company_id on qb_customers
                _supabase.table('qb_customers').update({
                    'matched_company_id': target_company_id
                }).eq('client_id', c['client_id']).eq(
                    'qb_record_id', c['qb_record_id']
                ).execute()

                # Write match metadata on customer_companies
                _supabase.table('customer_companies').update({
                    'qb_customer_id': c.get('qb_customer_id'),
                    'qb_match_method': method,
                    'qb_matched_at': now,
                }).eq('id', target_company_id).execute()

                # Propagate QB data for THIS one company only (not all matched)
                try:
                    qb_data = _supabase.table('qb_customers').select(
                        'customer_status, customer_tier, account_manager, '
                        'total_invoiced, invoiced_ty, invoiced_ly, growth_90d, '
                        'days_since_last_invoice, recency_days, customer_code'
                    ).eq('client_id', c['client_id']).eq(
                        'qb_record_id', c['qb_record_id']
                    ).limit(1).execute()

                    if qb_data.data:
                        qb = qb_data.data[0]
                        from ..services.quickbase_sync import _derive_growth, _derive_tier, _parse_recency_html
                        ty = qb.get('invoiced_ty')
                        ly = qb.get('invoiced_ly')
                        total = qb.get('total_invoiced')
                        enrich = {
                            'qb_customer_type': qb.get('customer_status'),
                            'qb_tier': qb.get('customer_tier') or _derive_tier(total),
                            'qb_total_revenue': total,
                            'qb_invoiced_ty': ty,
                            'qb_invoiced_ly': ly,
                            'qb_growth_90d': qb.get('growth_90d') or _derive_growth(ty, ly),
                            'qb_days_since_last_invoice': _parse_recency_html(
                                qb.get('days_since_last_invoice') or qb.get('recency_days')
                            ),
                            'qb_account_manager': qb.get('account_manager'),
                            'qb_customer_code': qb.get('customer_code'),
                        }
                        enrich = {k: v for k, v in enrich.items() if v is not None}
                        if enrich:
                            _supabase.table('customer_companies').update(enrich).eq(
                                'id', target_company_id
                            ).execute()
                except Exception as e:
                    logger.warning(f"Single-company propagation failed (non-critical): {e}")

                return {
                    "status": "accepted",
                    "promoted": True,
                    "qb_name": c.get('qb_name'),
                    "sb_company_name": c.get('sb_company_name'),
                }

        return {
            "status": "rejected" if not accepted else "accepted",
            "promoted": False,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.post("/match-candidates/bulk-review")
async def bulk_review_candidates(
    client_id: str = Query(...),
    candidate_ids: list[str] = Query(..., description="List of candidate IDs"),
    accepted: bool = Query(..., description="Accept or reject all"),
    user_id: str = Query(None),
    background_tasks: BackgroundTasks = None,
):
    """Bulk accept/reject multiple fuzzy match candidates."""
    try:
        now = datetime.now(timezone.utc).isoformat()
        promoted = 0

        for cid in candidate_ids:
            _supabase.table('qb_match_candidates').update({
                'reviewed': True,
                'accepted': accepted,
                'reviewed_by': user_id,
                'reviewed_at': now,
            }).eq('id', cid).execute()

            if accepted:
                candidate = _supabase.table('qb_match_candidates').select(
                    'client_id, sb_company_id, qb_record_id, qb_customer_id'
                ).eq('id', cid).limit(1).execute()

                if candidate.data:
                    c = candidate.data[0]
                    _supabase.table('qb_customers').update({
                        'matched_company_id': c['sb_company_id']
                    }).eq('client_id', c['client_id']).eq(
                        'qb_record_id', c['qb_record_id']
                    ).execute()

                    _supabase.table('customer_companies').update({
                        'qb_customer_id': c.get('qb_customer_id'),
                        'qb_match_method': 'fuzzy',
                        'qb_matched_at': now,
                    }).eq('id', c['sb_company_id']).execute()
                    promoted += 1

        # Trigger propagation for all accepted
        if accepted and promoted > 0 and background_tasks:
            def _propagate():
                """Run in thread pool to avoid blocking the event loop."""
                set_log_context(client_id=client_id)
                try:
                    cfg = _supabase.table('qb_sync_config').select('*').eq(
                        'client_id', client_id
                    ).limit(1).execute()
                    if cfg.data:
                        loop = asyncio.new_event_loop()
                        syncer = QuickbaseSync(_supabase, cfg.data[0])
                        loop.run_until_complete(syncer.propagate_qb_data_to_companies())
                        loop.run_until_complete(syncer.propagate_qb_data_to_contacts())
                        loop.close()
                except Exception as e:
                    logger.error(f"Post-bulk-accept propagation failed: {e}")
                finally:
                    clear_log_context()
            background_tasks.add_task(_propagate)

        return {
            "status": "completed",
            "reviewed": len(candidate_ids),
            "promoted": promoted,
            "accepted": accepted,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.delete("/match-candidates/clear")
async def clear_match_candidates(
    client_id: str = Query(...),
    reviewed_only: bool = Query(True, description="Only clear reviewed candidates"),
):
    """Clear match candidates (before a re-match run)."""
    try:
        q = _supabase.table('qb_match_candidates').delete().eq('client_id', client_id)
        if reviewed_only:
            q = q.eq('reviewed', True)
        q.execute()
        return {"status": "cleared", "reviewed_only": reviewed_only}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200])
