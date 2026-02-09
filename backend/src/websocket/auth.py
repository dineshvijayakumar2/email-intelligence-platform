"""
WebSocket Authentication

JWT authentication adapted for WebSocket connections.
Reuses verification logic from dependencies/auth.py but without FastAPI Depends.
"""

import os
import logging
from typing import Dict, Optional, List
import jwt
from jwt import PyJWKClient
from fastapi import WebSocketException, status

logger = logging.getLogger(__name__)

# Supabase configuration
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_JWT_SECRET = os.getenv('SUPABASE_JWT_SECRET')

# JWKS client for ES256 tokens (lazy loaded)
_jwks_client: Optional[PyJWKClient] = None

# Supabase client (injected from main)
_supabase = None


def init_websocket_auth(supabase_client):
    """Initialize WebSocket auth with Supabase client."""
    global _supabase
    _supabase = supabase_client


async def authenticate_websocket(token: str) -> Dict:
    """
    Verify Supabase JWT and return user info for WebSocket connection.

    Args:
        token: JWT token from query parameter

    Returns:
        Dict with user_id, email, name, roles

    Raises:
        WebSocketException: If authentication fails
    """
    if not token:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Authentication required"
        )

    try:
        # Verify JWT
        payload = _verify_jwt(token)

        user_id = payload.get('sub')  # Supabase uses 'sub' for user ID
        if not user_id:
            raise WebSocketException(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Invalid token payload"
            )

        # Get user profile with roles
        user_data = await _get_user_profile(user_id, payload)

        return user_data

    except jwt.ExpiredSignatureError:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Token has expired"
        )
    except jwt.InvalidAudienceError:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Invalid token audience"
        )
    except jwt.InvalidTokenError as e:
        logger.warning(f"[WebSocket Auth] Invalid token: {e}")
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Invalid token"
        )
    except WebSocketException:
        raise
    except Exception as e:
        logger.error(f"[WebSocket Auth] Authentication error: {e}")
        raise WebSocketException(
            code=status.WS_1011_INTERNAL_ERROR,
            reason="Authentication error"
        )


def _verify_jwt(token: str) -> Dict:
    """
    Verify JWT token and return payload.

    Supports both ES256/RS256 (via JWKS) and HS256 (via shared secret).
    """
    global _jwks_client

    # Decode header to check algorithm
    unverified_header = jwt.get_unverified_header(token)
    alg = unverified_header.get('alg', 'HS256')

    payload = None

    if alg in ['ES256', 'RS256']:
        # Use JWKS for ES256/RS256
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
                logger.warning(f"[WebSocket Auth] JWKS verification failed: {e}, trying HS256")

    # Fall back to HS256 if ES256/RS256 failed or not applicable
    if payload is None:
        if not SUPABASE_JWT_SECRET:
            raise WebSocketException(
                code=status.WS_1011_INTERNAL_ERROR,
                reason="Authentication not configured"
            )
        payload = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=['HS256'],
            audience='authenticated',
            options={"verify_signature": True}
        )

    return payload


async def _get_user_profile(user_id: str, payload: Dict) -> Dict:
    """
    Get user profile from database.

    Args:
        user_id: User ID from JWT
        payload: JWT payload (for fallback data)

    Returns:
        User info dict
    """
    if not _supabase:
        raise WebSocketException(
            code=status.WS_1011_INTERNAL_ERROR,
            reason="Database not configured"
        )

    result = _supabase.table('user_profiles').select(
        'id, email, name, roles, is_active'
    ).eq('id', user_id).single().execute()

    if not result.data:
        # User profile doesn't exist - create minimal profile
        logger.warning(f"[WebSocket Auth] User profile not found for {user_id}, creating default")
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
                raise WebSocketException(
                    code=status.WS_1008_POLICY_VIOLATION,
                    reason="Failed to create user profile"
                )
        except Exception as e:
            logger.error(f"[WebSocket Auth] Failed to create user profile: {e}")
            raise WebSocketException(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="User profile not found"
            )
    else:
        result_data = result.data

    if not result_data.get('is_active'):
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Account is deactivated"
        )

    return {
        'user_id': user_id,
        'email': result_data['email'],
        'name': result_data['name'],
        'roles': result_data.get('roles', ['account_manager'])
    }


async def get_accessible_mailbox_ids_for_user(user_id: str) -> List[str]:
    """
    Get list of mailbox IDs accessible to a user.

    Args:
        user_id: The user ID

    Returns:
        List of accessible mailbox ID strings
    """
    if not _supabase:
        logger.error("[WebSocket Auth] Supabase not initialized")
        return []

    try:
        result = _supabase.rpc(
            'get_user_accessible_mailboxes',
            {'p_user_id': user_id}
        ).execute()

        mailbox_ids = [r['mailbox_id'] for r in (result.data or [])]
        logger.debug(f"[WebSocket Auth] User {user_id} has access to {len(mailbox_ids)} mailboxes")
        return mailbox_ids

    except Exception as e:
        logger.error(f"[WebSocket Auth] Failed to get accessible mailboxes: {e}")
        return []
