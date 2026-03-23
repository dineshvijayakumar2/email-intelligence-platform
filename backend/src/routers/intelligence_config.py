"""
Intelligence Config Router — Manage capability taxonomy, classifier rules, and cache.

Endpoints:
  GET/PUT  /intelligence-config/capability-tags   — list/update the 8 MVP tags
  GET      /intelligence-config/classifier-rules  — paginated classifier rules
  POST     /intelligence-config/classifier-rules/import — bulk import (CSV/JSON)
  GET/PUT  /intelligence-config/rush-settings     — rush detection thresholds
  POST     /intelligence-config/reclassify        — re-tag all qb_operations with current rules
  GET      /intelligence-config/cache             — cache status per company
  DELETE   /intelligence-config/cache             — clear cache (forces recompute)
"""

import csv
import io
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel

from ..dependencies.auth import get_current_user, require_role
from fastapi import Depends
from ..services import capability_classifier
from ..services.quickbase_sync import QuickbaseSync

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/intelligence-config", tags=["intelligence-config"])

_supabase = None


def init_intelligence_config_router(supabase_client):
    global _supabase
    _supabase = supabase_client


def _get_client_id(user_id: str) -> str:
    result = _supabase.table('user_client_assignments').select(
        'client_id'
    ).eq('user_id', user_id).limit(1).execute()
    if result.data:
        return result.data[0]['client_id']
    raise HTTPException(status_code=404, detail="No client assignment found for user")


def _get_config(client_id: str, config_type: str) -> dict:
    result = _supabase.table('client_taxonomy_config').select(
        'config_data, version, updated_at'
    ).eq('client_id', client_id).eq('config_type', config_type).limit(1).execute()
    return result.data[0] if result.data else None


def _upsert_config(client_id: str, config_type: str, config_data: dict) -> dict:
    existing = _get_config(client_id, config_type)
    new_version = (existing['version'] + 1) if existing else 1
    now = datetime.now(timezone.utc).isoformat()

    _supabase.table('client_taxonomy_config').upsert({
        'client_id':   client_id,
        'config_type': config_type,
        'config_data': config_data,
        'version':     new_version,
        'updated_at':  now,
    }, on_conflict='client_id,config_type').execute()

    capability_classifier.invalidate_cache(client_id)
    return {'version': new_version, 'updated_at': now}


# ── Capability Tags ───────────────────────────────────────────────────────────

@router.get("/capability-tags")
async def get_capability_tags(current_user: dict = Depends(get_current_user)):
    client_id = _get_client_id(current_user['user_id'])

    # Auto-seed if missing
    capability_classifier._get_client_state(_supabase, client_id)

    cfg = _get_config(client_id, 'capability_tags')
    if not cfg:
        return {'tags': capability_classifier.DEFAULT_CAPABILITY_TAGS, 'version': 0}
    return {
        'tags':    cfg['config_data'].get('tags', []),
        'version': cfg['version'],
        'updated_at': cfg.get('updated_at'),
    }


class CapabilityTagsUpdate(BaseModel):
    tags: list[dict]


@router.put("/capability-tags")
async def update_capability_tags(
    body: CapabilityTagsUpdate,
    current_user: dict = Depends(require_role('admin', 'client_manager')),
):
    client_id = _get_client_id(current_user['user_id'])
    meta = _upsert_config(client_id, 'capability_tags', {'tags': body.tags})
    return {'ok': True, **meta}


# ── Classifier Rules ──────────────────────────────────────────────────────────

@router.get("/classifier-rules")
async def get_classifier_rules(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    tag: Optional[str] = Query(None),
    dept: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    client_id = _get_client_id(current_user['user_id'])

    # Auto-seed if missing
    capability_classifier._get_client_state(_supabase, client_id)

    cfg = _get_config(client_id, 'classifier_rules')
    rules = cfg['config_data'].get('rules', []) if cfg else []

    # Filter
    if tag:
        rules = [r for r in rules if r.get('tag') == tag]
    if dept:
        rules = [r for r in rules if (r.get('dept') or '').lower() == dept.lower()]

    total = len(rules)
    start = (page - 1) * page_size
    page_rules = rules[start:start + page_size]

    return {
        'rules':     page_rules,
        'total':     total,
        'page':      page,
        'page_size': page_size,
        'version':   cfg['version'] if cfg else 0,
    }


class RulesImport(BaseModel):
    rules: Optional[list[dict]] = None   # JSON import
    csv_text: Optional[str] = None       # CSV import (clipboard paste)
    replace: bool = False                # True = replace all; False = merge (upsert by dept+op+machine)


@router.post("/classifier-rules/import")
async def import_classifier_rules(
    body: RulesImport,
    current_user: dict = Depends(require_role('admin', 'client_manager')),
):
    """
    Bulk import classifier rules from JSON list or CSV text.

    CSV format (matches the Excel export):
      Department,Operation,Machine,Count,MVP Tag,Flags,Row Type

    Flags column: comma-separated flag names (has_coating, has_sewing, etc.)
    """
    client_id = _get_client_id(current_user['user_id'])

    incoming: list[dict] = []

    if body.rules:
        incoming = body.rules

    elif body.csv_text:
        try:
            reader = csv.DictReader(io.StringIO(body.csv_text.strip()))
            for row in reader:
                flags_raw = row.get('Flags', '') or ''
                flags = [f.strip() for f in flags_raw.split(',') if f.strip()]
                incoming.append({
                    'dept':         row.get('Department', '').strip(),
                    'op':           row.get('Operation', '').strip(),
                    'machine':      row.get('Machine', '').strip(),
                    'count':        int(row.get('Count', 0) or 0),
                    'tag':          row.get('MVP Tag', '').strip() or None,
                    'granular_tags': [],
                    'flags':        flags,
                    'row_type':     row.get('Row Type', '').strip() or None,
                })
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"CSV parse error: {e}")
    else:
        raise HTTPException(status_code=400, detail="Provide either 'rules' (JSON) or 'csv_text'")

    if not incoming:
        raise HTTPException(status_code=400, detail="No rules found in import")

    if body.replace:
        # Full replace
        new_rules = incoming
    else:
        # Merge: keep existing rules, overwrite matching (dept, op, machine)
        cfg = _get_config(client_id, 'classifier_rules')
        existing_rules = cfg['config_data'].get('rules', []) if cfg else []
        existing_map = {
            (r.get('dept', ''), r.get('op', ''), r.get('machine', '')): r
            for r in existing_rules
        }
        for r in incoming:
            r.setdefault('granular_tags', [])
            key = (r.get('dept', ''), r.get('op', ''), r.get('machine', ''))
            existing_map[key] = r
        new_rules = list(existing_map.values())

    meta = _upsert_config(client_id, 'classifier_rules', {'rules': new_rules})
    return {
        'ok':           True,
        'imported':     len(incoming),
        'total_rules':  len(new_rules),
        'replace_mode': body.replace,
        **meta,
    }


# ── Rush Settings ─────────────────────────────────────────────────────────────

@router.get("/rush-settings")
async def get_rush_settings(current_user: dict = Depends(get_current_user)):
    client_id = _get_client_id(current_user['user_id'])
    capability_classifier._get_client_state(_supabase, client_id)  # auto-seed
    cfg = _get_config(client_id, 'rush_settings')
    data = cfg['config_data'] if cfg else capability_classifier.DEFAULT_RUSH_SETTINGS
    return {'settings': data, 'version': cfg['version'] if cfg else 0}


class RushSettingsUpdate(BaseModel):
    am_rush_pattern: str
    rush_pct_threshold: int
    gap_count_threshold: int


@router.put("/rush-settings")
async def update_rush_settings(
    body: RushSettingsUpdate,
    current_user: dict = Depends(require_role('admin', 'client_manager')),
):
    client_id = _get_client_id(current_user['user_id'])
    meta = _upsert_config(client_id, 'rush_settings', body.model_dump())
    return {'ok': True, **meta}


# ── Reclassify ────────────────────────────────────────────────────────────────

_reclassify_status: dict[str, dict] = {}


@router.post("/reclassify")
async def trigger_reclassify(
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(require_role('admin', 'client_manager')),
):
    """Re-classify all qb_operations for this client using current rules. Runs in background."""
    client_id = _get_client_id(current_user['user_id'])

    if _reclassify_status.get(client_id, {}).get('status') == 'running':
        return {'ok': False, 'message': 'Reclassify already in progress'}

    _reclassify_status[client_id] = {'status': 'running', 'started_at': datetime.now(timezone.utc).isoformat()}

    def _run():
        try:
            count = capability_classifier.reclassify_all(_supabase, client_id)
            _reclassify_status[client_id] = {
                'status': 'complete',
                'updated': count,
                'completed_at': datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            logger.error(f"Reclassify failed for client {client_id}: {e}")
            _reclassify_status[client_id] = {
                'status': 'error',
                'error': str(e),
                'completed_at': datetime.now(timezone.utc).isoformat(),
            }

    background_tasks.add_task(_run)
    return {'ok': True, 'message': 'Reclassification started in background', 'client_id': client_id}


@router.get("/reclassify/status")
async def get_reclassify_status(current_user: dict = Depends(get_current_user)):
    client_id = _get_client_id(current_user['user_id'])
    return _reclassify_status.get(client_id, {'status': 'idle'})


# ── Cache ─────────────────────────────────────────────────────────────────────

@router.get("/cache")
async def get_cache_status(
    cache_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    """List customer_intelligence_cache entries — shows what's computed and when."""
    client_id = _get_client_id(current_user['user_id'])

    query = _supabase.table('customer_intelligence_cache').select(
        'id, company_id, contact_id, cache_type, computed_at, customer_companies(company_name)'
    ).eq('client_id', client_id).is_('contact_id', 'null')

    if cache_type:
        query = query.eq('cache_type', cache_type)

    offset = (page - 1) * page_size
    result = query.order('computed_at', desc=True).range(offset, offset + page_size - 1).execute()

    return {
        'entries':   result.data or [],
        'page':      page,
        'page_size': page_size,
    }


@router.delete("/cache")
async def clear_cache(
    cache_type: Optional[str] = Query(None),
    current_user: dict = Depends(require_role('admin', 'client_manager')),
):
    """Clear intelligence cache — forces recompute on next request."""
    client_id = _get_client_id(current_user['user_id'])

    query = _supabase.table('customer_intelligence_cache').delete().eq('client_id', client_id)
    if cache_type:
        query = query.eq('cache_type', cache_type)
    result = query.execute()

    deleted = len(result.data or [])
    return {'ok': True, 'deleted': deleted, 'cache_type': cache_type or 'all'}
