"""
Authentication Dependencies

FastAPI dependencies for verifying Supabase JWT tokens and managing user access.
Uses Supabase Auth - tokens are issued by Supabase, we just verify them.

Stage 2 - Role-Based Access Control Implementation
"""

from fastapi import Header, HTTPException, Depends
from typing import Optional, Dict, Callable
import jwt
from jwt import PyJWKClient
import os
import logging

logger = logging.getLogger(__name__)

# Supabase client will be injected from main.py
_supabase = None

# Supabase configuration
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_JWT_SECRET = os.getenv('SUPABASE_JWT_SECRET')

# JWKS client for ES256 tokens (lazy loaded)
_jwks_client = None


def init_auth_dependencies(supabase_client):
    """Initialize auth dependencies with Supabase client"""
    global _supabase
    _supabase = supabase_client


async def get_current_user(authorization: Optional[str] = Header(None)) -> Dict:
    """
    Verify Supabase JWT and return user info with roles.

    This is the main authentication dependency. It:
    1. Extracts the JWT from Authorization header
    2. Verifies the token using Supabase JWT secret
    3. Fetches user profile from user_profiles table
    4. Returns user info dict with id, email, name, roles

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

    try:
        # Verify Supabase JWT
        # Try ES256/RS256 first (using JWKS), then fall back to HS256 (using secret)
        payload = None

        # Decode header to check algorithm
        unverified_header = jwt.get_unverified_header(token)
        alg = unverified_header.get('alg', 'HS256')

        if alg in ['ES256', 'RS256']:
            # Use JWKS for ES256/RS256
            global _jwks_client
            if _jwks_client is None and SUPABASE_URL:
                jwks_url = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
                _jwks_client = PyJWKClient(jwks_url)

            if _jwks_client:
                try:
                    signing_key = _jwks_client.get_signing_key_from_jwt(token)
                    payload = jwt.decode(
                        token,
                        signing_key.key,
                        algorithms=['ES256', 'RS256'],
                        audience='authenticated',
                        options={"verify_signature": True}
                    )
                except Exception as e:
                    logger.warning(f"JWKS verification failed: {e}, trying HS256")

        # Fall back to HS256 if ES256/RS256 failed or not applicable
        if payload is None:
            if not SUPABASE_JWT_SECRET:
                raise HTTPException(
                    status_code=500,
                    detail="Authentication not configured"
                )
            payload = jwt.decode(
                token,
                SUPABASE_JWT_SECRET,
                algorithms=['HS256'],
                audience='authenticated',
                options={"verify_signature": True}
            )

        user_id = payload.get('sub')  # Supabase uses 'sub' for user ID

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token payload")

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
            raise HTTPException(status_code=403, detail="Account is deactivated")

        return {
            'user_id': user_id,
            'email': result_data['email'],
            'name': result_data['name'],
            'roles': result_data.get('roles', ['account_manager'])  # Default to array if missing
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
        result = _supabase.rpc(
            'get_user_accessible_mailboxes',
            {'p_user_id': current_user['user_id']}
        ).execute()

        return [r['mailbox_id'] for r in (result.data or [])]
    except Exception as e:
        logger.error(f"Failed to get accessible mailboxes: {e}")
        return []
