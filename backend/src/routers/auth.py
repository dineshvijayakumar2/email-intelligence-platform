"""
Authentication API Router

Endpoints for user profile management and role-based access control.
Authentication is handled by Supabase Auth - this router manages user profiles and roles.

Stage 2 - Role-Based Access Control Implementation
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, EmailStr
from typing import List, Optional
import logging

from ..dependencies.auth import get_current_user, require_role, get_accessible_mailbox_ids

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Supabase client will be injected from main.py
_supabase = None


def init_auth_router(supabase_client):
    """Initialize the router with Supabase client"""
    global _supabase
    _supabase = supabase_client


# =============================================================================
# Pydantic Models
# =============================================================================

class UserProfile(BaseModel):
    """User profile response model"""
    id: str
    email: str
    name: str
    role: str
    is_active: bool
    avatar_url: Optional[str] = None
    accessible_mailbox_ids: List[str] = []


class UserProfileUpdate(BaseModel):
    """User profile update request"""
    name: Optional[str] = None
    avatar_url: Optional[str] = None


class UpdateRoleRequest(BaseModel):
    """Role update request (admin only)"""
    role: str


class UserListResponse(BaseModel):
    """List of users response"""
    users: List[UserProfile]
    total: int


class ClientAssignment(BaseModel):
    """Client assignment for client_manager"""
    client_id: str
    client_name: str


class UserStatusUpdate(BaseModel):
    """User status update request"""
    is_active: bool


class ClientAssignmentsUpdate(BaseModel):
    """Bulk client assignments update"""
    client_ids: List[str]


class UserWithClients(BaseModel):
    """User with assigned clients"""
    id: str
    email: str
    name: str
    role: str
    is_active: bool
    avatar_url: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    assigned_clients: List[dict] = []


# =============================================================================
# Current User Endpoints
# =============================================================================

@router.get("/me", response_model=UserProfile)
async def get_current_user_profile(current_user: dict = Depends(get_current_user)):
    """
    Get current user profile with accessible mailboxes.

    Returns the authenticated user's profile including their role and
    list of mailbox IDs they have access to based on their role.

    Returns:
        UserProfile with accessible_mailbox_ids
    """
    try:
        # Get accessible mailboxes using RPC function
        result = _supabase.rpc(
            'get_user_accessible_mailboxes',
            {'p_user_id': current_user['user_id']}
        ).execute()

        mailbox_ids = [str(r['mailbox_id']) for r in (result.data or [])]

        # Get full profile
        profile_result = _supabase.table('user_profiles').select(
            'id, email, name, role, is_active, avatar_url'
        ).eq('id', current_user['user_id']).single().execute()

        if not profile_result.data:
            raise HTTPException(status_code=404, detail="Profile not found")

        return UserProfile(
            id=str(profile_result.data['id']),
            email=profile_result.data['email'],
            name=profile_result.data['name'],
            role=profile_result.data['role'],
            is_active=profile_result.data['is_active'],
            avatar_url=profile_result.data.get('avatar_url'),
            accessible_mailbox_ids=mailbox_ids
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get user profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/me", response_model=UserProfile)
async def update_current_user_profile(
    data: UserProfileUpdate,
    current_user: dict = Depends(get_current_user)
):
    """
    Update current user's profile.

    Users can update their own name and avatar_url.
    Role cannot be self-modified (admin only).

    Args:
        data: Profile fields to update

    Returns:
        Updated UserProfile
    """
    try:
        update_data = {}

        if data.name is not None:
            update_data['name'] = data.name
        if data.avatar_url is not None:
            update_data['avatar_url'] = data.avatar_url

        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        result = _supabase.table('user_profiles').update(
            update_data
        ).eq('id', current_user['user_id']).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to update profile")

        # Return updated profile
        return await get_current_user_profile(current_user)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/me/clients", response_model=List[ClientAssignment])
async def get_assigned_clients(current_user: dict = Depends(get_current_user)):
    """
    Get clients assigned to the current user (for client_manager role).

    Returns empty list for admin (they have access to all) and account_manager.

    Returns:
        List of assigned clients
    """
    try:
        if current_user['role'] != 'client_manager':
            return []

        result = _supabase.table('user_client_assignments').select(
            'client_id, clients(client_name)'
        ).eq('user_id', current_user['user_id']).execute()

        return [
            ClientAssignment(
                client_id=str(r['client_id']),
                client_name=r['clients']['client_name'] if r.get('clients') else 'Unknown'
            )
            for r in (result.data or [])
        ]

    except Exception as e:
        logger.error(f"Failed to get assigned clients: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Admin User Management Endpoints
# =============================================================================

@router.get("/users", response_model=List[UserWithClients])
async def list_users(
    role: Optional[str] = Query(default=None),
    active_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(require_role('admin'))
):
    """
    List all users with their assigned clients (admin only).

    Args:
        role: Filter by role (admin, client_manager, account_manager)
        active_only: Only return active users
        limit: Maximum results
        offset: Pagination offset

    Returns:
        List of users with assigned clients
    """
    try:
        query = _supabase.table('user_profiles').select(
            'id, email, name, role, is_active, avatar_url, created_at, updated_at'
        )

        if role:
            query = query.eq('role', role)
        if active_only:
            query = query.eq('is_active', True)

        # Get paginated results
        result = query.order('name').range(offset, offset + limit - 1).execute()

        users = []
        for u in (result.data or []):
            # Get assigned clients for client_manager users
            assigned_clients = []
            if u['role'] == 'client_manager':
                clients_result = _supabase.table('user_client_assignments').select(
                    'client_id, clients(id, client_name, email)'
                ).eq('user_id', u['id']).execute()

                assigned_clients = [
                    {
                        'id': str(c['client_id']),
                        'name': c['clients']['client_name'] if c.get('clients') else 'Unknown',
                        'email': c['clients'].get('email') if c.get('clients') else None
                    }
                    for c in (clients_result.data or [])
                ]

            users.append(UserWithClients(
                id=str(u['id']),
                email=u['email'],
                name=u['name'],
                role=u['role'],
                is_active=u['is_active'],
                avatar_url=u.get('avatar_url'),
                created_at=u.get('created_at'),
                updated_at=u.get('updated_at'),
                assigned_clients=assigned_clients
            ))

        return users

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list users: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/{user_id}", response_model=UserProfile)
async def get_user(
    user_id: str,
    current_user: dict = Depends(require_role('admin'))
):
    """
    Get a specific user's profile (admin only).

    Args:
        user_id: UUID of the user

    Returns:
        UserProfile with accessible mailboxes
    """
    try:
        result = _supabase.table('user_profiles').select(
            'id, email, name, role, is_active, avatar_url'
        ).eq('id', user_id).single().execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="User not found")

        # Get accessible mailboxes
        mailbox_result = _supabase.rpc(
            'get_user_accessible_mailboxes',
            {'p_user_id': user_id}
        ).execute()

        mailbox_ids = [str(r['mailbox_id']) for r in (mailbox_result.data or [])]

        return UserProfile(
            id=str(result.data['id']),
            email=result.data['email'],
            name=result.data['name'],
            role=result.data['role'],
            is_active=result.data['is_active'],
            avatar_url=result.data.get('avatar_url'),
            accessible_mailbox_ids=mailbox_ids
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get user: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    request: UpdateRoleRequest,
    current_user: dict = Depends(require_role('admin'))
):
    """
    Update a user's role (admin only).

    Args:
        user_id: UUID of the user
        request: New role

    Returns:
        Success message
    """
    try:
        valid_roles = ['admin', 'client_manager', 'account_manager']
        if request.role not in valid_roles:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}"
            )

        # Prevent admin from demoting themselves
        if user_id == current_user['user_id'] and request.role != 'admin':
            raise HTTPException(
                status_code=400,
                detail="Cannot change your own role"
            )

        result = _supabase.table('user_profiles').update({
            'role': request.role
        }).eq('id', user_id).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="User not found")

        logger.info(f"User {user_id} role updated to {request.role} by {current_user['user_id']}")

        return {
            "success": True,
            "message": f"Role updated to {request.role}",
            "user_id": user_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update user role: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: str,
    current_user: dict = Depends(require_role('admin'))
):
    """
    Deactivate a user account (admin only).

    Deactivated users cannot log in.

    Args:
        user_id: UUID of the user

    Returns:
        Success message
    """
    try:
        # Prevent admin from deactivating themselves
        if user_id == current_user['user_id']:
            raise HTTPException(
                status_code=400,
                detail="Cannot deactivate your own account"
            )

        result = _supabase.table('user_profiles').update({
            'is_active': False
        }).eq('id', user_id).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="User not found")

        logger.info(f"User {user_id} deactivated by {current_user['user_id']}")

        return {
            "success": True,
            "message": "User deactivated",
            "user_id": user_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to deactivate user: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/users/{user_id}/activate")
async def activate_user(
    user_id: str,
    current_user: dict = Depends(require_role('admin'))
):
    """
    Reactivate a deactivated user account (admin only).

    Args:
        user_id: UUID of the user

    Returns:
        Success message
    """
    try:
        result = _supabase.table('user_profiles').update({
            'is_active': True
        }).eq('id', user_id).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="User not found")

        logger.info(f"User {user_id} activated by {current_user['user_id']}")

        return {
            "success": True,
            "message": "User activated",
            "user_id": user_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to activate user: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/users/{user_id}/status")
async def update_user_status(
    user_id: str,
    request: UserStatusUpdate,
    current_user: dict = Depends(require_role('admin'))
):
    """
    Update a user's active status (admin only).

    Args:
        user_id: UUID of the user
        request: New status (is_active: true/false)

    Returns:
        Success message
    """
    try:
        # Prevent admin from deactivating themselves
        if user_id == current_user['user_id'] and not request.is_active:
            raise HTTPException(
                status_code=400,
                detail="Cannot deactivate your own account"
            )

        result = _supabase.table('user_profiles').update({
            'is_active': request.is_active
        }).eq('id', user_id).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="User not found")

        status = "activated" if request.is_active else "deactivated"
        logger.info(f"User {user_id} {status} by {current_user['user_id']}")

        return {
            "success": True,
            "message": f"User {status}",
            "user_id": user_id,
            "is_active": request.is_active
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update user status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/users/{user_id}/client-assignments")
async def update_user_client_assignments(
    user_id: str,
    request: ClientAssignmentsUpdate,
    current_user: dict = Depends(require_role('admin'))
):
    """
    Bulk update client assignments for a user (admin only).

    Replaces all current client assignments with the provided list.

    Args:
        user_id: UUID of the user
        request: List of client_ids to assign

    Returns:
        Success message
    """
    try:
        # Verify user exists
        user_result = _supabase.table('user_profiles').select('id, role').eq(
            'id', user_id
        ).single().execute()

        if not user_result.data:
            raise HTTPException(status_code=404, detail="User not found")

        # Delete all existing assignments
        _supabase.table('user_client_assignments').delete().eq(
            'user_id', user_id
        ).execute()

        # Insert new assignments
        if request.client_ids:
            # Verify all clients exist
            clients_result = _supabase.table('clients').select('id').in_(
                'id', request.client_ids
            ).execute()

            valid_client_ids = [str(c['id']) for c in (clients_result.data or [])]
            invalid_ids = set(request.client_ids) - set(valid_client_ids)

            if invalid_ids:
                logger.warning(f"Invalid client IDs provided: {invalid_ids}")

            # Insert valid assignments
            if valid_client_ids:
                assignments = [
                    {'user_id': user_id, 'client_id': client_id}
                    for client_id in valid_client_ids
                ]
                _supabase.table('user_client_assignments').insert(assignments).execute()

        logger.info(f"User {user_id} client assignments updated by {current_user['user_id']}")

        return {
            "success": True,
            "message": f"Updated {len(request.client_ids)} client assignments",
            "user_id": user_id,
            "assigned_count": len(request.client_ids)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update client assignments: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Client Assignment Endpoints (for client_manager role)
# =============================================================================

@router.post("/users/{user_id}/clients/{client_id}")
async def assign_client_to_user(
    user_id: str,
    client_id: str,
    current_user: dict = Depends(require_role('admin'))
):
    """
    Assign a client to a user (admin only).

    This is primarily used for client_manager role to grant them access
    to specific clients' mailboxes.

    Args:
        user_id: UUID of the user
        client_id: UUID of the client

    Returns:
        Success message
    """
    try:
        # Verify user exists
        user_result = _supabase.table('user_profiles').select('id, role').eq(
            'id', user_id
        ).single().execute()

        if not user_result.data:
            raise HTTPException(status_code=404, detail="User not found")

        # Verify client exists
        client_result = _supabase.table('clients').select('id, client_name').eq(
            'id', client_id
        ).single().execute()

        if not client_result.data:
            raise HTTPException(status_code=404, detail="Client not found")

        # Check if assignment already exists
        existing = _supabase.table('user_client_assignments').select('id').eq(
            'user_id', user_id
        ).eq('client_id', client_id).execute()

        if existing.data:
            raise HTTPException(status_code=400, detail="Client already assigned to user")

        # Create assignment
        _supabase.table('user_client_assignments').insert({
            'user_id': user_id,
            'client_id': client_id
        }).execute()

        logger.info(f"Client {client_id} assigned to user {user_id} by {current_user['user_id']}")

        return {
            "success": True,
            "message": f"Client '{client_result.data['client_name']}' assigned to user",
            "user_id": user_id,
            "client_id": client_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to assign client to user: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/users/{user_id}/clients/{client_id}")
async def unassign_client_from_user(
    user_id: str,
    client_id: str,
    current_user: dict = Depends(require_role('admin'))
):
    """
    Remove client assignment from a user (admin only).

    Args:
        user_id: UUID of the user
        client_id: UUID of the client

    Returns:
        Success message
    """
    try:
        result = _supabase.table('user_client_assignments').delete().eq(
            'user_id', user_id
        ).eq('client_id', client_id).execute()

        # Note: Supabase delete returns empty data if nothing matched
        logger.info(f"Client {client_id} unassigned from user {user_id} by {current_user['user_id']}")

        return {
            "success": True,
            "message": "Client assignment removed",
            "user_id": user_id,
            "client_id": client_id
        }

    except Exception as e:
        logger.error(f"Failed to unassign client from user: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/{user_id}/clients", response_model=List[ClientAssignment])
async def get_user_clients(
    user_id: str,
    current_user: dict = Depends(require_role('admin'))
):
    """
    Get clients assigned to a specific user (admin only).

    Args:
        user_id: UUID of the user

    Returns:
        List of assigned clients
    """
    try:
        result = _supabase.table('user_client_assignments').select(
            'client_id, clients(client_name)'
        ).eq('user_id', user_id).execute()

        return [
            ClientAssignment(
                client_id=str(r['client_id']),
                client_name=r['clients']['client_name'] if r.get('clients') else 'Unknown'
            )
            for r in (result.data or [])
        ]

    except Exception as e:
        logger.error(f"Failed to get user clients: {e}")
        raise HTTPException(status_code=500, detail=str(e))
