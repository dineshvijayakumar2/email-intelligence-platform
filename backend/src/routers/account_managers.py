"""
Account Managers API Router

CRUD endpoints for managing account managers.

Stage 2 Phase 2 - Business Hierarchy Implementation
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
import logging

from ..models.account_manager import (
    AccountManagerCreate,
    AccountManagerUpdate,
    AccountManagerResponse,
    AccountManagerWithStats,
    AccountManagerListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/account-managers", tags=["account-managers"])

# Supabase client will be injected from main.py
_supabase = None


def init_account_managers_router(supabase_client):
    """Initialize the router with Supabase client"""
    global _supabase
    _supabase = supabase_client


@router.post("/", response_model=AccountManagerResponse)
async def create_account_manager(data: AccountManagerCreate):
    """
    Create a new account manager.

    Args:
        data: Account manager creation data

    Returns:
        Created account manager record
    """
    try:
        # Check if email already exists
        existing = _supabase.table('account_managers').select('id').eq(
            'email', data.email
        ).execute()

        if existing.data:
            raise HTTPException(
                status_code=400,
                detail=f"Account manager with email {data.email} already exists"
            )

        # Create account manager
        insert_data = {
            'name': data.name,
            'email': data.email,
            'role': data.role.value,
            'is_active': True,
        }

        # TODO: Hash password if provided
        if data.password:
            insert_data['password_hash'] = data.password  # Should be hashed

        result = _supabase.table('account_managers').insert(insert_data).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to create account manager")

        return AccountManagerResponse(**result.data[0])

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create account manager: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=AccountManagerListResponse)
async def list_account_managers(
    active_only: bool = Query(default=True),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0)
):
    """
    List all account managers.

    Args:
        active_only: If true, only return active account managers
        limit: Maximum number of results
        offset: Offset for pagination

    Returns:
        List of account managers
    """
    try:
        query = _supabase.table('account_managers').select(
            'id, name, email, role, is_active, created_at, updated_at'
        )

        if active_only:
            query = query.eq('is_active', True)

        # Get total count first
        count_result = _supabase.table('account_managers').select(
            'id', count='exact'
        )
        if active_only:
            count_result = count_result.eq('is_active', True)
        count_result = count_result.execute()
        total = count_result.count if count_result.count else len(count_result.data)

        # Get paginated results
        result = query.order('name').range(offset, offset + limit - 1).execute()

        return AccountManagerListResponse(
            account_managers=[AccountManagerResponse(**am) for am in result.data],
            total=total
        )

    except Exception as e:
        logger.error(f"Failed to list account managers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{manager_id}", response_model=AccountManagerWithStats)
async def get_account_manager(manager_id: str):
    """
    Get account manager details with statistics.

    Args:
        manager_id: UUID of the account manager

    Returns:
        Account manager with client statistics
    """
    try:
        # Get account manager
        result = _supabase.table('account_managers').select(
            'id, name, email, role, is_active, created_at, updated_at'
        ).eq('id', manager_id).single().execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Account manager not found")

        am_data = result.data

        # Get statistics
        clients_result = _supabase.table('clients').select(
            'id, status', count='exact'
        ).eq('account_manager_id', manager_id).execute()

        total_clients = clients_result.count if clients_result.count else len(clients_result.data)
        active_clients = sum(1 for c in clients_result.data if c.get('status') == 'active')

        mailboxes_result = _supabase.table('mailboxes').select(
            'id', count='exact'
        ).eq('account_manager_id', manager_id).execute()

        total_mailboxes = mailboxes_result.count if mailboxes_result.count else len(mailboxes_result.data)

        return AccountManagerWithStats(
            **am_data,
            total_clients=total_clients,
            active_clients=active_clients,
            total_mailboxes=total_mailboxes
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get account manager: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{manager_id}", response_model=AccountManagerResponse)
async def update_account_manager(manager_id: str, data: AccountManagerUpdate):
    """
    Update an account manager.

    Args:
        manager_id: UUID of the account manager
        data: Fields to update

    Returns:
        Updated account manager record
    """
    try:
        # Check if exists
        existing = _supabase.table('account_managers').select('id').eq(
            'id', manager_id
        ).single().execute()

        if not existing.data:
            raise HTTPException(status_code=404, detail="Account manager not found")

        # Build update data
        update_data = {}
        if data.name is not None:
            update_data['name'] = data.name
        if data.email is not None:
            # Check email uniqueness
            email_check = _supabase.table('account_managers').select('id').eq(
                'email', data.email
            ).neq('id', manager_id).execute()
            if email_check.data:
                raise HTTPException(status_code=400, detail="Email already in use")
            update_data['email'] = data.email
        if data.role is not None:
            update_data['role'] = data.role.value
        if data.is_active is not None:
            update_data['is_active'] = data.is_active

        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        result = _supabase.table('account_managers').update(
            update_data
        ).eq('id', manager_id).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to update account manager")

        return AccountManagerResponse(**result.data[0])

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update account manager: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{manager_id}")
async def delete_account_manager(manager_id: str):
    """
    Delete an account manager.

    Note: This will set account_manager_id to NULL on related clients and mailboxes.

    Args:
        manager_id: UUID of the account manager

    Returns:
        Success message
    """
    try:
        # Check if exists
        existing = _supabase.table('account_managers').select('id, name').eq(
            'id', manager_id
        ).single().execute()

        if not existing.data:
            raise HTTPException(status_code=404, detail="Account manager not found")

        # Delete (foreign keys with ON DELETE SET NULL will handle relations)
        _supabase.table('account_managers').delete().eq('id', manager_id).execute()

        return {
            "message": f"Account manager '{existing.data['name']}' deleted successfully",
            "id": manager_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete account manager: {e}")
        raise HTTPException(status_code=500, detail=str(e))
