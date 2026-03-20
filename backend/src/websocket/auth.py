"""
WebSocket Authentication

JWT authentication adapted for WebSocket connections.
Reuses verification logic from dependencies/auth.py but without FastAPI Depends.
"""

import os
import logging
from typing import Dict, Optional, List
from fastapi import WebSocketException, status

logger = logging.getLogger(__name__)

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
        # Verify token via Supabase admin API — no JWKS dependency
        try:
            user_response = _supabase.auth.get_user(token)
        except Exception as e:
            err_str = str(e).lower()
            if 'expired' in err_str:
                raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Token has expired")
            logger.warning(f"[WebSocket Auth] get_user failed: {e}")
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")

        if not user_response or not user_response.user:
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token payload")

        user_id = user_response.user.id

        # Get user profile with roles
        user_data = await _get_user_profile(user_id, {})

        return user_data

    except WebSocketException:
        raise
    except Exception as e:
        logger.error(f"[WebSocket Auth] Authentication error: {e}")
        raise WebSocketException(
            code=status.WS_1011_INTERNAL_ERROR,
            reason="Authentication error"
        )



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
