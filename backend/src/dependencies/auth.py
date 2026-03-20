"""
Authentication Dependencies

FastAPI dependencies for verifying Supabase JWT tokens and managing user access.
Uses Supabase Auth - tokens are issued by Supabase, we just verify them.

Stage 2 - Role-Based Access Control Implementation
"""

from fastapi import Header, HTTPException, Depends
from typing import Optional, Dict, Callable, Tuple
import os
import time
import hashlib
import logging
from ..utils.audit import log_audit

logger = logging.getLogger(__name__)

# Supabase client will be injected from main.py
_supabase = None

# In-process auth cache: token_hash -> (user_dict, expires_at)
# Avoids a Supabase auth API call on every request (5-min TTL)
_auth_cache: Dict[str, Tuple[Dict, float]] = {}
_AUTH_CACHE_TTL = 300  # seconds


def _cache_key(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def init_auth_dependencies(supabase_client):
    """Initialize auth dependencies with Supabase client"""
    global _supabase
    _supabase = supabase_client


async def get_current_user(authorization: Optional[str] = Header(None)) -> Dict:
    """
    Verify Supabase JWT and return user info with roles.

    This is the main authentication dependency. It:
    1. Extracts the JWT from Authorization header
    2. Checks in-process cache (5-min TTL) to avoid hitting Supabase on every request
    3. On cache miss: verifies via supabase.auth.get_user() — works for ES256/RS256/HS256
    4. Fetches user profile from user_profiles table
    5. Returns user info dict with id, email, name, roles

    Args:
        authorization: Bearer token from Authorization header

    Returns:
        Dict with user_id, email, name, roles (array of role strings)

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

    # Check cache first
    key = _cache_key(token)
    cached = _auth_cache.get(key)
    if cached and cached[1] > time.time():
        return cached[0]

    try:
        # Verify token via Supabase admin API — works for ES256, RS256, and HS256
        # without any JWKS dependency or local JWT secret
        try:
            user_response = _supabase.auth.get_user(token)
        except Exception as e:
            err_str = str(e).lower()
            if 'expired' in err_str:
                log_audit(action="login_failure", resource_type="auth", details={"reason": "token_expired"})
                raise HTTPException(status_code=401, detail="Token has expired", headers={"WWW-Authenticate": "Bearer"})
            logger.warning(f"Supabase auth.get_user failed: {e}")
            raise HTTPException(status_code=401, detail="Invalid token", headers={"WWW-Authenticate": "Bearer"})

        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid token payload")

        user_id = user_response.user.id

        # Get user profile with roles
        result = _supabase.table('user_profiles').select(
            'id, email, name, roles, is_active'
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
                    'roles': ['account_manager'],
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
            log_audit(action="login_blocked", resource_type="user", user_id=user_id, user_email=result_data.get('email'), details={"reason": "account_deactivated"})
            raise HTTPException(status_code=403, detail="Account is deactivated")

        user_info = {
            'user_id': user_id,
            'email': result_data['email'],
            'name': result_data['name'],
            'roles': result_data.get('roles', ['account_manager'])
        }

        # Cache for 5 minutes to avoid per-request Supabase auth calls
        _auth_cache[key] = (user_info, time.time() + _AUTH_CACHE_TTL)

        return user_info

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
        HTTPException 403: If user doesn't have any of the required roles
    """
    async def role_checker(current_user: Dict = Depends(get_current_user)) -> Dict:
        user_roles = current_user.get('roles', [])
        # Check if user has any of the required roles
        if not any(role in user_roles for role in roles):
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
        logger.info(f"[Auth] Getting accessible mailboxes for user {current_user['user_id']} with roles {current_user.get('roles', [])}")
        result = _supabase.rpc(
            'get_user_accessible_mailboxes',
            {'p_user_id': current_user['user_id']}
        ).execute()

        mailbox_ids = [r['mailbox_id'] for r in (result.data or [])]
        logger.info(f"[Auth] Found {len(mailbox_ids)} accessible mailboxes")
        return mailbox_ids
    except Exception as e:
        logger.error(f"Failed to get accessible mailboxes: {e}")
        return []
