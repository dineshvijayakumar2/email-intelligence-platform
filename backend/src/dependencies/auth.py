"""
Authentication Dependencies

FastAPI dependencies for verifying Supabase JWT tokens and managing user access.
Uses Supabase Auth - tokens are issued by Supabase, we just verify them.

Stage 2 - Role-Based Access Control Implementation
"""

from fastapi import Header, HTTPException, Depends
from typing import Optional, Dict, Callable
import jwt
import os
import logging

logger = logging.getLogger(__name__)

# Supabase client will be injected from main.py
_supabase = None

# Supabase JWT secret (found in Supabase Dashboard → Settings → API → JWT Secret)
SUPABASE_JWT_SECRET = os.getenv('SUPABASE_JWT_SECRET')


def init_auth_dependencies(supabase_client):
    """Initialize auth dependencies with Supabase client"""
    global _supabase
    _supabase = supabase_client


async def get_current_user(authorization: Optional[str] = Header(None)) -> Dict:
    """
    Verify Supabase JWT and return user info with role.

    This is the main authentication dependency. It:
    1. Extracts the JWT from Authorization header
    2. Verifies the token using Supabase JWT secret
    3. Fetches user profile from user_profiles table
    4. Returns user info dict with id, email, name, role

    Args:
        authorization: Bearer token from Authorization header

    Returns:
        Dict with user_id, email, name, role

    Raises:
        HTTPException 401: If not authenticated or token invalid
        HTTPException 403: If account is deactivated
    """
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = authorization.replace('Bearer ', '')

    # Check if JWT secret is configured
    if not SUPABASE_JWT_SECRET:
        logger.error("SUPABASE_JWT_SECRET not configured")
        raise HTTPException(
            status_code=500,
            detail="Authentication not configured"
        )

    try:
        # Verify Supabase JWT
        # Supabase uses HS256 for older projects and ES256 for newer ones
        payload = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=['HS256', 'ES256', 'RS256'],
            audience='authenticated',
            options={"verify_signature": True}
        )

        user_id = payload.get('sub')  # Supabase uses 'sub' for user ID

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token payload")

        # Get user profile with role
        result = _supabase.table('user_profiles').select(
            'id, email, name, role, is_active'
        ).eq('id', user_id).single().execute()

        if not result.data:
            # User profile doesn't exist yet - this can happen if trigger didn't fire
            # Create a minimal profile
            logger.warning(f"User profile not found for {user_id}, creating default")
            email = payload.get('email', '')
            name = email.split('@')[0] if email else 'User'

            try:
                insert_result = _supabase.table('user_profiles').insert({
                    'id': user_id,
                    'email': email,
                    'name': name,
                    'role': 'account_manager',
                    'is_active': True
                }).execute()

                if insert_result.data:
                    result_data = insert_result.data[0]
                else:
                    raise HTTPException(status_code=401, detail="Failed to create user profile")
            except Exception as e:
                logger.error(f"Failed to create user profile: {e}")
                raise HTTPException(status_code=401, detail="User profile not found")
        else:
            result_data = result.data

        if not result_data.get('is_active'):
            raise HTTPException(status_code=403, detail="Account is deactivated")

        return {
            'user_id': user_id,
            'email': result_data['email'],
            'name': result_data['name'],
            'role': result_data['role']
        }

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"}
        )
    except jwt.InvalidAudienceError:
        raise HTTPException(
            status_code=401,
            detail="Invalid token audience",
            headers={"WWW-Authenticate": "Bearer"}
        )
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid token: {e}")
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        raise HTTPException(status_code=500, detail="Authentication error")


def require_role(*roles: str) -> Callable:
    """
    Dependency factory to require specific roles.

    Usage:
        @router.get("/admin-only")
        async def admin_endpoint(user: dict = Depends(require_role('admin'))):
            ...

        @router.get("/manager-or-admin")
        async def manager_endpoint(user: dict = Depends(require_role('admin', 'client_manager'))):
            ...

    Args:
        *roles: One or more role names that are allowed

    Returns:
        Dependency function that validates role

    Raises:
        HTTPException 403: If user's role not in allowed roles
    """
    async def role_checker(current_user: Dict = Depends(get_current_user)) -> Dict:
        if current_user['role'] not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions. Required role: {', '.join(roles)}"
            )
        return current_user

    return role_checker


async def get_optional_user(authorization: Optional[str] = Header(None)) -> Optional[Dict]:
    """
    Get current user if authenticated, None otherwise.

    Useful for endpoints that have different behavior for authenticated vs anonymous users.

    Args:
        authorization: Bearer token from Authorization header

    Returns:
        User dict if authenticated, None otherwise
    """
    if not authorization or not authorization.startswith('Bearer '):
        return None

    try:
        return await get_current_user(authorization)
    except HTTPException:
        return None


async def get_accessible_mailbox_ids(current_user: Dict = Depends(get_current_user)) -> list:
    """
    Get list of mailbox IDs accessible to the current user based on their role.

    Uses the get_user_accessible_mailboxes database function.

    Args:
        current_user: Current authenticated user

    Returns:
        List of UUID strings for accessible mailboxes
    """
    try:
        result = _supabase.rpc(
            'get_user_accessible_mailboxes',
            {'p_user_id': current_user['user_id']}
        ).execute()

        return [r['mailbox_id'] for r in (result.data or [])]
    except Exception as e:
        logger.error(f"Failed to get accessible mailboxes: {e}")
        return []
