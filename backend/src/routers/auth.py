"""
Authentication API Router

Endpoints for user profile management and role-based access control.
Authentication is handled by Supabase Auth - this router manages user profiles and roles.

Stage 2 - Role-Based Access Control Implementation
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, EmailStr
from typing import List, Optional, Any
import logging

from ..dependencies.auth import get_current_user, require_role, get_accessible_mailbox_ids
from ..utils.audit import audit_from_user

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
    roles: List[str]
    is_active: bool
    avatar_url: Optional[str] = None
    accessible_mailbox_ids: List[str] = []


class UserProfileUpdate(BaseModel):
    """User profile update request"""
    name: Optional[str] = None
    avatar_url: Optional[str] = None


class BusinessHoursSettings(BaseModel):
    """Business hours configuration for a user"""
    timezone: Optional[str] = None
    business_hours_start: Optional[int] = None
    business_hours_end: Optional[int] = None
    business_days: Optional[List[int]] = None


class BusinessHoursResponse(BaseModel):
    """Business hours configuration response"""
    timezone: str
    business_hours_start: int
    business_hours_end: int
    business_days: List[int]


class UpdateRolesRequest(BaseModel):
    """Roles update request (admin only)"""
    roles: List[str]


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


class MailboxSummary(BaseModel):
    """Summary of a mailbox for user assignment display"""
    id: str
    name: str
    email_address: Optional[str] = None
    mailbox_type: str


class UserWithClients(BaseModel):
    """User with assigned clients and mailboxes"""
    id: str
    email: str
    name: str
    roles: List[str]
    is_active: bool
    avatar_url: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    assigned_clients: List[dict] = []
    assigned_mailboxes: List[MailboxSummary] = []


# =============================================================================
# Current User Endpoints
# =============================================================================

@router.post("/login-event")
async def record_login_event(current_user: dict = Depends(get_current_user)):
    """
    Record a successful login event in the audit log.

    Called by the frontend once after OAuth or email/password sign-in.
    Idempotent — safe to call multiple times (each call creates a log entry).
    """
    audit_from_user(current_user, "login", "auth", details={"method": "session"})
    return {"ok": True}


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
            'id, email, name, roles, is_active, avatar_url'
        ).eq('id', current_user['user_id']).single().execute()

        if not profile_result.data:
            raise HTTPException(status_code=404, detail="Profile not found")

        return UserProfile(
            id=str(profile_result.data['id']),
            email=profile_result.data['email'],
            name=profile_result.data['name'],
            roles=profile_result.data.get('roles', ['account_manager']),
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


@router.get("/me/settings", response_model=BusinessHoursResponse)
async def get_business_hours_settings(current_user: dict = Depends(get_current_user)):
    """Get the current user's business hours settings (timezone, working hours, business days)."""
    try:
        result = _supabase.table('user_profiles').select(
            'timezone, business_hours_start, business_hours_end, business_days'
        ).eq('id', current_user['user_id']).single().execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Profile not found")

        return BusinessHoursResponse(
            timezone=result.data.get('timezone') or 'UTC',
            business_hours_start=result.data.get('business_hours_start', 9),
            business_hours_end=result.data.get('business_hours_end', 18),
            business_days=result.data.get('business_days') or [1, 2, 3, 4, 5],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get business hours settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/me/settings", response_model=BusinessHoursResponse)
async def update_business_hours_settings(
    data: BusinessHoursSettings,
    current_user: dict = Depends(get_current_user),
):
    """Update the current user's business hours settings."""
    try:
        update_data = {}

        if data.timezone is not None:
            update_data['timezone'] = data.timezone
        if data.business_hours_start is not None:
            if not (0 <= data.business_hours_start <= 23):
                raise HTTPException(status_code=400, detail="business_hours_start must be 0-23")
            update_data['business_hours_start'] = data.business_hours_start
        if data.business_hours_end is not None:
            if not (0 <= data.business_hours_end <= 23):
                raise HTTPException(status_code=400, detail="business_hours_end must be 0-23")
            update_data['business_hours_end'] = data.business_hours_end
        if data.business_days is not None:
            if not all(1 <= d <= 7 for d in data.business_days):
                raise HTTPException(status_code=400, detail="business_days must contain values 1-7")
            update_data['business_days'] = data.business_days

        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        _supabase.table('user_profiles').update(update_data).eq(
            'id', current_user['user_id']
        ).execute()

        audit_from_user(current_user, "settings_change", "settings", details={"changed_fields": list(update_data.keys())})

        return await get_business_hours_settings(current_user)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update business hours settings: {e}")
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
        if 'client_manager' not in current_user.get('roles', []):
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
            'id, email, name, roles, is_active, avatar_url, created_at, updated_at'
        )

        if role:
            # Filter users that have the specified role in their roles array
            query = query.contains('roles', [role])
        if active_only:
            query = query.eq('is_active', True)

        # Get paginated results
        result = query.order('name').range(offset, offset + limit - 1).execute()

        users = []
        for u in (result.data or []):
            # Get assigned clients based on user role
            assigned_clients = []
            user_roles = u.get('roles', [])

            # Determine which table to query based on role priority
            # Priority: client_manager > account_manager
            if 'client_manager' in user_roles:
                # Client managers: fetch from client_manager_assignments (oversight)
                clients_result = _supabase.table('client_manager_assignments').select(
                    'client_id, clients(id, client_name, client_label, status)'
                ).eq('user_id', u['id']).execute()

                assigned_clients = [
                    {
                        'id': str(c['client_id']),
                        'client_name': c['clients']['client_name'] if c.get('clients') else 'Unknown',
                        'client_label': c['clients'].get('client_label') if c.get('clients') else None,
                        'status': c['clients'].get('status') if c.get('clients') else 'active'
                    }
                    for c in (clients_result.data or [])
                ]
            elif 'account_manager' in user_roles:
                # Account managers: fetch from user_client_assignments (operational)
                clients_result = _supabase.table('user_client_assignments').select(
                    'client_id, clients(id, client_name, client_label, status)'
                ).eq('user_id', u['id']).execute()

                assigned_clients = [
                    {
                        'id': str(c['client_id']),
                        'client_name': c['clients']['client_name'] if c.get('clients') else 'Unknown',
                        'client_label': c['clients'].get('client_label') if c.get('clients') else None,
                        'status': c['clients'].get('status') if c.get('clients') else 'active'
                    }
                    for c in (clients_result.data or [])
                ]

            # Fetch mailboxes directly assigned to this user
            mailboxes_result = _supabase.table('mailboxes').select(
                'id, name, email_address, mailbox_type'
            ).eq('user_id', u['id']).execute()

            assigned_mailboxes = [
                MailboxSummary(
                    id=str(m['id']),
                    name=m['name'],
                    email_address=m.get('email_address'),
                    mailbox_type=m['mailbox_type']
                )
                for m in (mailboxes_result.data or [])
            ]

            users.append(UserWithClients(
                id=str(u['id']),
                email=u['email'],
                name=u['name'],
                roles=user_roles,
                is_active=u['is_active'],
                avatar_url=u.get('avatar_url'),
                created_at=u.get('created_at'),
                updated_at=u.get('updated_at'),
                assigned_clients=assigned_clients,
                assigned_mailboxes=assigned_mailboxes
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
            'id, email, name, roles, is_active, avatar_url'
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
            roles=result.data.get('roles', ['account_manager']),
            is_active=result.data['is_active'],
            avatar_url=result.data.get('avatar_url'),
            accessible_mailbox_ids=mailbox_ids
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get user: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/users/{user_id}/roles")
async def update_user_roles(
    user_id: str,
    request: UpdateRolesRequest,
    current_user: dict = Depends(require_role('admin'))
):
    """
    Update a user's roles (admin only).

    Users can have multiple roles. For example, an admin can also be an account_manager
    to monitor mailboxes linked to clients.

    Args:
        user_id: UUID of the user
        request: Array of new roles

    Returns:
        Success message
    """
    try:
        valid_roles = ['admin', 'client_manager', 'account_manager']

        # Validate all roles
        if not request.roles or len(request.roles) == 0:
            raise HTTPException(
                status_code=400,
                detail="At least one role is required"
            )

        for role in request.roles:
            if role not in valid_roles:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid role '{role}'. Must be one of: {', '.join(valid_roles)}"
                )

        # Prevent admin from removing their own admin role
        if user_id == current_user['user_id'] and 'admin' not in request.roles:
            raise HTTPException(
                status_code=400,
                detail="Cannot remove your own admin role"
            )

        result = _supabase.table('user_profiles').update({
            'roles': request.roles
        }).eq('id', user_id).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="User not found")

        logger.info(f"User {user_id} roles updated to {request.roles} by {current_user['user_id']}")
        audit_from_user(current_user, "role_change", "user", resource_id=user_id, details={"new_roles": request.roles})

        return {
            "success": True,
            "message": f"Roles updated to {', '.join(request.roles)}",
            "user_id": user_id,
            "roles": request.roles
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update user roles: {e}")
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
        audit_from_user(current_user, "user_deactivate", "user", resource_id=user_id)

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
        audit_from_user(current_user, "user_activate", "user", resource_id=user_id)

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

    Automatically determines the correct assignment table based on user's role:
    - account_manager: Uses user_client_assignments (operational access)
    - client_manager: Uses client_manager_assignments (oversight access)

    Replaces all current assignments with the provided list.

    Args:
        user_id: UUID of the user
        request: List of client_ids to assign

    Returns:
        Success message
    """
    try:
        # Verify user exists and get their roles
        user_result = _supabase.table('user_profiles').select('id, roles').eq(
            'id', user_id
        ).single().execute()

        if not user_result.data:
            raise HTTPException(status_code=404, detail="User not found")

        user_roles = user_result.data.get('roles', [])

        # Determine which table to use based on role
        # Priority: client_manager > account_manager
        if 'client_manager' in user_roles:
            assignment_table = 'client_manager_assignments'
            assignment_type = 'oversight'
        elif 'account_manager' in user_roles:
            assignment_table = 'user_client_assignments'
            assignment_type = 'operational'
        else:
            raise HTTPException(
                status_code=400,
                detail="User must have account_manager or client_manager role for client assignments"
            )

        # Delete all existing assignments from the appropriate table
        _supabase.table(assignment_table).delete().eq(
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
                _supabase.table(assignment_table).insert(assignments).execute()

        logger.info(f"User {user_id} {assignment_type} client assignments updated by {current_user['user_id']}")
        audit_from_user(current_user, "client_assign", "user", resource_id=user_id, details={"client_ids": request.client_ids, "assignment_type": assignment_type})

        return {
            "success": True,
            "message": f"Updated {len(request.client_ids)} {assignment_type} client assignments",
            "user_id": user_id,
            "assigned_count": len(request.client_ids),
            "assignment_type": assignment_type
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update client assignments: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class MailboxAssignmentsUpdate(BaseModel):
    """Bulk mailbox assignments update"""
    mailbox_ids: List[str]


@router.put("/users/{user_id}/mailbox-assignments")
async def update_user_mailbox_assignments(
    user_id: str,
    request: MailboxAssignmentsUpdate,
    current_user: dict = Depends(require_role('admin'))
):
    """
    Bulk update mailbox assignments for a user (admin only).

    Assigns the specified mailboxes directly to the user (sets user_id on mailbox).
    Any mailboxes previously assigned to this user but not in the new list
    will have their user_id set to NULL.

    Args:
        user_id: UUID of the user
        request: List of mailbox_ids to assign

    Returns:
        Success message with assignment counts
    """
    try:
        # Verify user exists
        user_result = _supabase.table('user_profiles').select('id, name').eq(
            'id', user_id
        ).single().execute()

        if not user_result.data:
            raise HTTPException(status_code=404, detail="User not found")

        # Get currently assigned mailboxes
        current_result = _supabase.table('mailboxes').select('id').eq(
            'user_id', user_id
        ).execute()
        current_mailbox_ids = {str(m['id']) for m in (current_result.data or [])}

        # Calculate which mailboxes to add and remove
        new_mailbox_ids = set(request.mailbox_ids)
        to_add = new_mailbox_ids - current_mailbox_ids
        to_remove = current_mailbox_ids - new_mailbox_ids

        # Remove assignments (set user_id to NULL)
        if to_remove:
            _supabase.table('mailboxes').update({
                'user_id': None
            }).in_('id', list(to_remove)).execute()
            logger.info(f"Removed {len(to_remove)} mailbox assignments from user {user_id}")

        # Add new assignments
        if to_add:
            # Verify mailboxes exist
            mailboxes_result = _supabase.table('mailboxes').select('id').in_(
                'id', list(to_add)
            ).execute()
            valid_mailbox_ids = [str(m['id']) for m in (mailboxes_result.data or [])]

            if valid_mailbox_ids:
                _supabase.table('mailboxes').update({
                    'user_id': user_id
                }).in_('id', valid_mailbox_ids).execute()
                logger.info(f"Added {len(valid_mailbox_ids)} mailbox assignments to user {user_id}")

        logger.info(f"User {user_id} mailbox assignments updated by {current_user['user_id']}")

        return {
            "success": True,
            "message": f"Updated mailbox assignments: {len(to_add)} added, {len(to_remove)} removed",
            "user_id": user_id,
            "total_assigned": len(new_mailbox_ids),
            "added": len(to_add),
            "removed": len(to_remove)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update mailbox assignments: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Account Manager Client Assignment Endpoints
# =============================================================================
# Assigns account_managers to clients for operational access to mailboxes

@router.post("/users/{user_id}/clients/{client_id}")
async def assign_client_to_account_manager(
    user_id: str,
    client_id: str,
    current_user: dict = Depends(require_role('admin'))
):
    """
    Assign a client to an account_manager (admin only).

    This gives the account_manager operational access to mailboxes
    belonging to the specified client.

    Args:
        user_id: UUID of the account_manager
        client_id: UUID of the client

    Returns:
        Success message
    """
    try:
        # Verify user exists
        user_result = _supabase.table('user_profiles').select('id, roles').eq(
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


# =============================================================================
# Client Manager Assignment Endpoints
# =============================================================================
# Assigns client_managers to clients for oversight/management (not direct mailbox access)

@router.post("/users/{user_id}/managed-clients/{client_id}")
async def assign_client_to_manager(
    user_id: str,
    client_id: str,
    current_user: dict = Depends(require_role('admin'))
):
    """
    Assign a client to a client_manager for oversight (admin only).

    This allows the client_manager to oversee account_managers working on this client
    and view mailboxes for this client.

    Args:
        user_id: UUID of the client_manager
        client_id: UUID of the client

    Returns:
        Success message
    """
    try:
        # Verify user exists and has client_manager role
        user_result = _supabase.table('user_profiles').select('id, roles').eq(
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
        existing = _supabase.table('client_manager_assignments').select('id').eq(
            'user_id', user_id
        ).eq('client_id', client_id).execute()

        if existing.data:
            raise HTTPException(status_code=400, detail="Client already assigned to this manager")

        # Create assignment
        _supabase.table('client_manager_assignments').insert({
            'user_id': user_id,
            'client_id': client_id
        }).execute()

        logger.info(f"Client {client_id} assigned to client_manager {user_id} by {current_user['user_id']}")

        return {
            "success": True,
            "message": f"Client '{client_result.data['client_name']}' assigned to client manager",
            "user_id": user_id,
            "client_id": client_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to assign client to manager: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/users/{user_id}/managed-clients/{client_id}")
async def unassign_client_from_manager(
    user_id: str,
    client_id: str,
    current_user: dict = Depends(require_role('admin'))
):
    """
    Remove client assignment from a client_manager (admin only).

    Args:
        user_id: UUID of the client_manager
        client_id: UUID of the client

    Returns:
        Success message
    """
    try:
        result = _supabase.table('client_manager_assignments').delete().eq(
            'user_id', user_id
        ).eq('client_id', client_id).execute()

        logger.info(f"Client {client_id} unassigned from client_manager {user_id} by {current_user['user_id']}")

        return {
            "success": True,
            "message": "Client manager assignment removed",
            "user_id": user_id,
            "client_id": client_id
        }

    except Exception as e:
        logger.error(f"Failed to unassign client from manager: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/{user_id}/managed-clients", response_model=List[ClientAssignment])
async def get_manager_clients(
    user_id: str,
    current_user: dict = Depends(require_role('admin'))
):
    """
    Get clients assigned to a specific client_manager (admin only).

    Args:
        user_id: UUID of the client_manager

    Returns:
        List of clients they manage
    """
    try:
        result = _supabase.table('client_manager_assignments').select(
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
        logger.error(f"Failed to get manager clients: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Audit Log Endpoints (Admin Only)
# =============================================================================

class AuditLogEntry(BaseModel):
    """Single audit log entry"""
    id: str
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    details: Optional[Any] = None
    ip_address: Optional[str] = None
    created_at: str


class AuditLogResponse(BaseModel):
    """Paginated audit log response"""
    data: List[AuditLogEntry]
    total: int
    page: int
    page_size: int


class AuditLogStats(BaseModel):
    """Audit log summary statistics"""
    total_entries: int
    actions: List[dict]
    resource_types: List[dict]
    active_users: List[dict]


@router.get("/audit-logs", response_model=AuditLogResponse)
async def list_audit_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    action: Optional[str] = Query(default=None, description="Filter by action type"),
    resource_type: Optional[str] = Query(default=None, description="Filter by resource type"),
    user_email: Optional[str] = Query(default=None, description="Filter by user email (partial match)"),
    date_from: Optional[str] = Query(default=None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(default=None, description="End date (YYYY-MM-DD)"),
    search: Optional[str] = Query(default=None, description="Search action, resource_type, resource_id, user_email"),
    current_user: dict = Depends(require_role('admin')),
):
    """
    List audit log entries with pagination, filtering, and search (admin only).

    Supports filtering by action, resource_type, user_email, date range.
    Search performs partial match across action, resource_type, resource_id, user_email.
    """
    try:
        # Count query
        count_query = _supabase.table('audit_log').select('id', count='exact')
        # Data query
        data_query = _supabase.table('audit_log').select(
            'id, user_id, user_email, action, resource_type, resource_id, details, ip_address, created_at'
        )

        # Apply filters to both queries
        for q_ref in [count_query, data_query]:
            if action:
                q_ref = q_ref if q_ref is count_query else data_query
                # We need to apply filters inline
                pass

        # Rebuild with filters applied properly
        if action:
            count_query = count_query.eq('action', action)
            data_query = data_query.eq('action', action)
        if resource_type:
            count_query = count_query.eq('resource_type', resource_type)
            data_query = data_query.eq('resource_type', resource_type)
        if user_email:
            count_query = count_query.ilike('user_email', f'%{user_email}%')
            data_query = data_query.ilike('user_email', f'%{user_email}%')
        if date_from:
            count_query = count_query.gte('created_at', f'{date_from}T00:00:00Z')
            data_query = data_query.gte('created_at', f'{date_from}T00:00:00Z')
        if date_to:
            count_query = count_query.lte('created_at', f'{date_to}T23:59:59Z')
            data_query = data_query.lte('created_at', f'{date_to}T23:59:59Z')

        # Search across multiple fields — use Python-side filtering
        # (Supabase .or_() can be unreliable)
        search_filter = None
        if search:
            search_filter = search.lower()

        # Execute count
        count_result = count_query.execute()
        total = count_result.count if count_result.count is not None else 0

        # Execute data with pagination and ordering
        offset = (page - 1) * page_size
        data_query = data_query.order('created_at', desc=True).range(offset, offset + page_size - 1)
        data_result = data_query.execute()

        rows = data_result.data or []

        # Apply search filter in Python if needed
        if search_filter:
            rows = [
                r for r in rows
                if search_filter in (r.get('action', '') or '').lower()
                or search_filter in (r.get('resource_type', '') or '').lower()
                or search_filter in (r.get('resource_id', '') or '').lower()
                or search_filter in (r.get('user_email', '') or '').lower()
            ]
            total = len(rows)  # Approximate — search reduces count

        entries = [
            AuditLogEntry(
                id=str(r['id']),
                user_id=str(r['user_id']) if r.get('user_id') else None,
                user_email=r.get('user_email'),
                action=r['action'],
                resource_type=r['resource_type'],
                resource_id=r.get('resource_id'),
                details=r.get('details'),
                ip_address=r.get('ip_address'),
                created_at=r['created_at'],
            )
            for r in rows
        ]

        return AuditLogResponse(data=entries, total=total, page=page, page_size=page_size)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list audit logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/audit-logs/stats", response_model=AuditLogStats)
async def get_audit_log_stats(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to aggregate"),
    current_user: dict = Depends(require_role('admin')),
):
    """
    Get audit log summary statistics for the last N days (admin only).

    Returns action counts, resource type counts, and top active users.
    """
    try:
        from datetime import datetime, timedelta, timezone

        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        # Fetch all entries in range (up to 1000 for aggregation)
        result = _supabase.table('audit_log').select(
            'action, resource_type, user_email'
        ).gte('created_at', cutoff).order('created_at', desc=True).limit(1000).execute()

        rows = result.data or []
        total_entries = len(rows)

        # Aggregate action counts
        action_counts: dict = {}
        resource_counts: dict = {}
        user_counts: dict = {}

        for r in rows:
            a = r.get('action', 'unknown')
            action_counts[a] = action_counts.get(a, 0) + 1

            rt = r.get('resource_type', 'unknown')
            resource_counts[rt] = resource_counts.get(rt, 0) + 1

            ue = r.get('user_email') or 'system'
            user_counts[ue] = user_counts.get(ue, 0) + 1

        actions = sorted(
            [{'name': k, 'count': v} for k, v in action_counts.items()],
            key=lambda x: x['count'], reverse=True
        )
        resource_types = sorted(
            [{'name': k, 'count': v} for k, v in resource_counts.items()],
            key=lambda x: x['count'], reverse=True
        )
        active_users = sorted(
            [{'email': k, 'count': v} for k, v in user_counts.items()],
            key=lambda x: x['count'], reverse=True
        )[:10]

        return AuditLogStats(
            total_entries=total_entries,
            actions=actions,
            resource_types=resource_types,
            active_users=active_users,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get audit log stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
