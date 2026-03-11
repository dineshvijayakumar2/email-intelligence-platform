"""
Quickbase Integration Router — Sync config, trigger sync, view cached data.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from ..models.quickbase import (
    QBSyncConfigCreate,
    QBSyncConfigResponse,
    QBSyncResult,
    QBSyncStatus,
)
from ..services.quickbase_sync import QuickbaseSync

logger = logging.getLogger(__name__)

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
    """Get Quickbase sync configuration for a client (token masked)."""
    try:
        result = _supabase.table('qb_sync_config').select('*').eq(
            'client_id', client_id
        ).single().execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="No QB config found for this client")

        cfg = result.data
        # Mask token
        token = cfg.get('user_token_encrypted', '')
        masked = token[:4] + '****' + token[-4:] if len(token) > 8 else '****'

        return QBSyncConfigResponse(
            client_id=cfg['client_id'],
            realm_hostname=cfg['realm_hostname'],
            app_id=cfg['app_id'],
            user_token_masked=masked,
            customers_table_id=cfg['customers_table_id'],
            contacts_table_id=cfg['contacts_table_id'],
            quotes_table_id=cfg['quotes_table_id'],
            jobs_table_id=cfg['jobs_table_id'],
            sales_line_items_table_id=cfg['sales_line_items_table_id'],
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
            'user_token_encrypted': config.user_token,
            'customers_table_id': config.customers_table_id,
            'contacts_table_id': config.contacts_table_id,
            'quotes_table_id': config.quotes_table_id,
            'jobs_table_id': config.jobs_table_id,
            'sales_line_items_table_id': config.sales_line_items_table_id,
            'field_mappings': config.field_mappings or {},
            'sync_interval_hours': config.sync_interval_hours,
            'is_active': True,
            'updated_at': datetime.now(timezone.utc).isoformat(),
        }

        _supabase.table('qb_sync_config').upsert(
            row, on_conflict='client_id'
        ).execute()

        return {"status": "ok", "message": "QB config saved"}

    except Exception as e:
        logger.error(f"Failed to save QB config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- Sync endpoints ---

@router.post("/sync", response_model=QBSyncResult)
async def trigger_sync(client_id: str = Query(...), background_tasks: BackgroundTasks = None):
    """Trigger a full Quickbase sync (runs in background)."""
    try:
        # Load config
        cfg_result = _supabase.table('qb_sync_config').select('*').eq(
            'client_id', client_id
        ).single().execute()

        if not cfg_result.data:
            raise HTTPException(status_code=404, detail="No QB config found. Set up config first.")

        config = cfg_result.data
        if not config.get('is_active'):
            raise HTTPException(status_code=400, detail="QB sync is disabled for this client")

        async def _run_sync():
            try:
                syncer = QuickbaseSync(_supabase, config)
                counts = await syncer.sync_all()
                # Propagate QB data to existing company columns
                await syncer.propagate_qb_data_to_companies()
                logger.info(f"Background QB sync complete: {counts}")
            except Exception as e:
                logger.error(f"Background QB sync failed: {e}")

        background_tasks.add_task(_run_sync)

        return QBSyncResult(
            status="started",
            message="Quickbase sync started in background",
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
        ).eq('client_id', client_id).single().execute()

        if not cfg_result.data:
            raise HTTPException(status_code=404, detail="No QB config found")

        # Count records per table
        counts = {}
        for table in ['qb_customers', 'qb_contacts', 'qb_quotes', 'qb_jobs', 'qb_sales_line_items']:
            result = _supabase.table(table).select(
                'id', count='exact'
            ).eq('client_id', client_id).limit(0).execute()
            counts[table.replace('qb_', '')] = result.count or 0

        cfg = cfg_result.data
        return QBSyncStatus(
            client_id=cfg['client_id'],
            last_sync_at=cfg.get('last_sync_at'),
            is_active=cfg.get('is_active', True),
            record_counts=counts,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get sync status: {e}")
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
