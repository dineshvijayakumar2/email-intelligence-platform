"""
Quickbase Integration Router — Sync config, trigger sync, view cached data.
"""

import json
import logging
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

logger = logging.getLogger(__name__)


def _sanitize_search(term: str) -> str:
    """Escape SQL ILIKE wildcards in user-supplied search terms."""
    return term.replace('%', r'\%').replace('_', r'\_')

router = APIRouter(prefix="/quickbase", tags=["quickbase"])

_supabase = None


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

VALID_TABLES = {'customers', 'contacts', 'quotes', 'jobs', 'sales_line_items', 'operations'}


@router.post("/sync", response_model=QBSyncResult)
async def trigger_sync(
    client_id: str = Query(...),
    tables: Optional[str] = Query(None, description="Comma-separated table names to sync (omit for full sync)"),
    background_tasks: BackgroundTasks = None,
):
    """Trigger a Quickbase sync (full or per-table). Runs in background."""
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

        async def _run_sync():
            try:
                syncer = QuickbaseSync(_supabase, config)
                counts = await syncer.sync_all(tables=tables_list)
                # Propagate QB data to existing company columns
                await syncer.propagate_qb_data_to_companies()
                logger.info(f"Background QB sync complete: {counts}")
            except Exception as e:
                logger.error(f"Background QB sync failed: {e}")

        background_tasks.add_task(_run_sync)

        label = ', '.join(tables_list) if tables_list else 'all tables'
        return QBSyncResult(
            status="started",
            message=f"Quickbase sync started in background ({label})",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to trigger QB sync: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sync-status", response_model=QBSyncStatus)
async def get_sync_status(client_id: str = Query(...)):
    """Get sync status and record counts for a client."""
    try:
        cfg_result = _supabase.table('qb_sync_config').select(
            'client_id, last_sync_at, is_active'
        ).eq('client_id', client_id).limit(1).execute()

        if not cfg_result.data:
            raise HTTPException(status_code=404, detail="No QB config found")

        # Count records per table
        counts = {}
        for table in ['qb_customers', 'qb_contacts', 'qb_quotes', 'qb_jobs', 'qb_sales_line_items']:
            result = _supabase.table(table).select(
                'id', count='exact'
            ).eq('client_id', client_id).limit(0).execute()
            counts[table.replace('qb_', '')] = result.count or 0

        # Fetch latest sync log entry per table — gracefully skips if table not yet created
        table_logs: list[QBTableSyncLog] = []
        try:
            log_result = _supabase.table('qb_sync_log').select(
                'table_name, table_id, record_count, synced_at, status, error_message'
            ).eq('client_id', client_id).order('synced_at', desc=True).limit(50).execute()

            seen: set[str] = set()
            for row in (log_result.data or []):
                tn = row['table_name']
                if tn not in seen:
                    seen.add(tn)
                    table_logs.append(QBTableSyncLog(
                        table_name=tn,
                        table_id=row.get('table_id'),
                        record_count=row.get('record_count', 0),
                        synced_at=row.get('synced_at'),
                        status=row.get('status', 'success'),
                        error_message=row.get('error_message'),
                    ))
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

@router.get("/customers")
async def list_qb_customers(
    client_id: str = Query(...),
    matched: Optional[bool] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """List cached QB customers with optional match filter."""
    try:
        query = _supabase.table('qb_customers').select(
            '*, customer_companies(company_name)',
            count='exact'
        ).eq('client_id', client_id)

        if matched is True:
            query = query.not_.is_('matched_company_id', 'null')
        elif matched is False:
            query = query.is_('matched_company_id', 'null')

        result = query.order('customer_name').range(offset, offset + limit - 1).execute()

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
):
    """List cached QB contacts."""
    try:
        query = _supabase.table('qb_contacts').select('*', count='exact').eq('client_id', client_id)
        if search:
            s = _sanitize_search(search)
            query = query.or_(f"first_name.ilike.%{s}%,surname.ilike.%{s}%,email.ilike.%{s}%")
        result = query.order('surname').range(offset, offset + limit - 1).execute()
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
):
    """List cached QB quotes."""
    try:
        query = _supabase.table('qb_quotes').select('*', count='exact').eq('client_id', client_id)
        if search:
            s = _sanitize_search(search)
            query = query.or_(f"quote_no.ilike.%{s}%,contact_name.ilike.%{s}%")
        result = query.order('date_created', desc=True).range(offset, offset + limit - 1).execute()
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
):
    """List cached QB jobs."""
    try:
        query = _supabase.table('qb_jobs').select('*', count='exact').eq('client_id', client_id)
        if search:
            s = _sanitize_search(search)
            query = query.or_(f"job_no.ilike.%{s}%,job_status.ilike.%{s}%")
        result = query.order('accepted_date', desc=True).range(offset, offset + limit - 1).execute()
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
):
    """List cached QB sales line items."""
    try:
        query = _supabase.table('qb_sales_line_items').select('*', count='exact').eq('client_id', client_id)
        if search:
            s = _sanitize_search(search)
            query = query.or_(f"customer_name.ilike.%{s}%,job_no.ilike.%{s}%,invoice_no.ilike.%{s}%")
        result = query.order('inv_date', desc=True).range(offset, offset + limit - 1).execute()
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
        result = query.order('date_accepted', desc=True).range(offset, offset + limit - 1).execute()
        return {"operations": result.data or [], "total": result.count or 0}
    except Exception as e:
        logger.error(f"Failed to list QB operations: {e}")
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

        async def _run():
            try:
                engine = RecommendationEngine(_supabase, client_id)
                count = engine.recompute_affinities()
                logger.info(f"Affinity recompute done: {count} pairs for client {client_id}")
            except Exception as e:
                logger.error(f"Affinity recompute failed: {e}")

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
    background_tasks: BackgroundTasks = None,
):
    """Re-run QB matching + propagation without re-syncing from QuickBase API.
    Useful after extraction adds new companies/contacts that can now match."""
    try:
        cfg_result = _supabase.table('qb_sync_config').select('*').eq(
            'client_id', client_id
        ).limit(1).execute()
        if not cfg_result.data:
            raise HTTPException(status_code=404, detail="No QB config found")

        config = cfg_result.data[0]

        async def _run_rematch():
            try:
                syncer = QuickbaseSync(_supabase, config)
                c1 = await syncer.match_to_companies()
                c2 = await syncer.match_to_contacts()
                c3 = await syncer.match_customers_via_contacts()
                c4 = await syncer.propagate_qb_data_to_companies()
                logger.info(f"Rematch complete: {c1} companies by name, {c2} contacts by email, "
                            f"{c3} companies via contacts, {c4} propagated")
            except Exception as e:
                logger.error(f"Rematch failed: {e}")

        if background_tasks:
            background_tasks.add_task(_run_rematch)
            return {"status": "accepted", "message": "Re-matching started in background"}
        else:
            await _run_rematch()
            return {"status": "completed", "message": "Re-matching completed"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.get("/health")
async def qb_health(client_id: str = Query(...)):
    """QB data health: match rates, enrichment coverage, data quality."""
    try:
        # QB customer match rate
        total_qb = _supabase.table('qb_customers').select('id', count='exact').eq('client_id', client_id).execute()
        matched_qb = _supabase.table('qb_customers').select('id', count='exact').eq('client_id', client_id).not_.is_('matched_company_id', 'null').execute()

        # QB contact match rate
        total_qb_contacts = _supabase.table('qb_contacts').select('id', count='exact').eq('client_id', client_id).execute()
        matched_qb_contacts = _supabase.table('qb_contacts').select('id', count='exact').eq('client_id', client_id).not_.is_('matched_contact_id', 'null').execute()

        # Company enrichment coverage
        total_companies = _supabase.table('customer_companies').select('id', count='exact').eq('client_id', client_id).execute()
        enriched_companies = _supabase.table('customer_companies').select('id', count='exact').eq('client_id', client_id).not_.is_('qb_total_revenue', 'null').execute()

        total_c = total_qb.count or 0
        matched_c = matched_qb.count or 0
        total_ct = total_qb_contacts.count or 0
        matched_ct = matched_qb_contacts.count or 0
        total_co = total_companies.count or 0
        enriched_co = enriched_companies.count or 0

        # Enriched companies with email activity (the meaningful metric)
        active_enriched = 0
        try:
            active_resp = _supabase.table('customer_companies').select('id', count='exact').eq(
                'client_id', client_id
            ).not_.is_('qb_total_revenue', 'null').gt('total_emails', '0').execute()
            active_enriched = active_resp.count or 0
        except Exception:
            pass

        # Companies with email activity
        active_companies = 0
        try:
            ac_resp = _supabase.table('customer_companies').select('id', count='exact').eq(
                'client_id', client_id
            ).gt('total_emails', '0').execute()
            active_companies = ac_resp.count or 0
        except Exception:
            pass

        return {
            "qb_customers": {"total": total_c, "matched": matched_c, "unmatched": total_c - matched_c, "match_rate_pct": round(matched_c / total_c * 100, 1) if total_c else 0},
            "qb_contacts": {"total": total_ct, "matched": matched_ct, "unmatched": total_ct - matched_ct, "match_rate_pct": round(matched_ct / total_ct * 100, 1) if total_ct else 0},
            "company_enrichment": {"total": total_co, "enriched": enriched_co, "not_enriched": total_co - enriched_co, "coverage_pct": round(enriched_co / total_co * 100, 1) if total_co else 0},
            "active_companies": {"total": active_companies, "with_qb_data": active_enriched, "coverage_pct": round(active_enriched / active_companies * 100, 1) if active_companies else 0},
        }
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
