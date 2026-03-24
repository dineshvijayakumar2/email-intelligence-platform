"""
Google Drive OAuth2 Authentication Router

Handles Google Drive OAuth2 token exchange, status checking, and disconnection.
Extracted from main.py for cleaner separation of concerns.
"""

import os
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Callable

from fastapi import APIRouter, HTTPException, Depends
from google_auth_oauthlib.flow import Flow

from ..models.api_models import OAuth2ExchangeRequest
from ..dependencies.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/google", tags=["google_auth"])

# Supabase client getter — injected from main.py via init function
_get_supabase: Callable = None


def init_google_auth_router(supabase_getter: Callable):
    """Initialize the Google Auth router with a Supabase client getter."""
    global _get_supabase
    _get_supabase = supabase_getter


# =========================================================================
# Helper Functions for Google Drive Token Management
# =========================================================================

def store_user_google_tokens(user_id: str, access_token: str, refresh_token: str) -> bool:
    """Store user's Google Drive tokens in database."""
    try:
        existing = (
            _get_supabase()
            .table("user_integrations")
            .select("id")
            .eq("user_id", user_id)
            .eq("provider", "google_drive")
            .execute()
        )

        token_data = {
            "user_id": user_id,
            "provider": "google_drive",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        if existing.data:
            _get_supabase().table("user_integrations").update(token_data).eq(
                "user_id", user_id
            ).eq("provider", "google_drive").execute()
        else:
            token_data["created_at"] = datetime.now(timezone.utc).isoformat()
            _get_supabase().table("user_integrations").insert(token_data).execute()

        logger.info(f"Stored Google Drive tokens for user {user_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to store Google Drive tokens for user {user_id}: {e}")
        return False


def get_user_google_tokens(user_id: str) -> Optional[Dict]:
    """Get user's Google Drive tokens from database."""
    try:
        result = (
            _get_supabase()
            .table("user_integrations")
            .select("access_token,refresh_token")
            .eq("user_id", user_id)
            .eq("provider", "google_drive")
            .execute()
        )

        if result.data:
            return result.data[0]
        return None

    except Exception as e:
        logger.error(f"Failed to get Google Drive tokens for user {user_id}: {e}")
        return None


def update_user_access_token(user_id: str, new_access_token: str) -> bool:
    """Update user's access token after refresh."""
    try:
        _get_supabase().table("user_integrations").update(
            {
                "access_token": new_access_token,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("user_id", user_id).eq("provider", "google_drive").execute()

        return True

    except Exception as e:
        logger.error(f"Failed to update access token for user {user_id}: {e}")
        return False


# =========================================================================
# Endpoints
# =========================================================================

@router.post("/exchange")
async def exchange_oauth_code(
    request: OAuth2ExchangeRequest,
    current_user: dict = Depends(get_current_user),
):
    """Exchange OAuth2 authorization code for tokens and store securely."""
    try:
        logger.info(f"Starting OAuth2 token exchange for user: {request.user_id}")

        # Validate required environment variables
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")

        if not client_id or not client_secret:
            logger.error("Missing Google OAuth credentials")
            raise HTTPException(
                status_code=500,
                detail="Server configuration error: Missing Google credentials",
            )

        # For popup-based OAuth flow (frontend uses ux_mode: 'popup'), Google uses "postmessage"
        # This works for both local development and Railway deployment
        redirect_uri = os.getenv("GOOGLE_REDIRECT_URI_OVERRIDE", "postmessage")
        logger.info(f"Using redirect URI: {redirect_uri}")

        # Create OAuth2 flow
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [redirect_uri],
                }
            },
            scopes=[
                "https://www.googleapis.com/auth/drive.readonly",
                "https://www.googleapis.com/auth/userinfo.email",
                "openid",
                "https://www.googleapis.com/auth/userinfo.profile",
            ],
        )

        flow.redirect_uri = redirect_uri

        logger.info("Exchanging authorization code...")

        # Exchange authorization code for tokens
        flow.fetch_token(code=request.code)

        logger.info("Token exchange successful, storing tokens...")

        # Store tokens securely in database
        access_token = flow.credentials.token
        refresh_token = flow.credentials.refresh_token

        if not access_token:
            raise HTTPException(
                status_code=500, detail="No access token received from Google"
            )

        success = store_user_google_tokens(
            user_id=request.user_id,
            access_token=access_token,
            refresh_token=refresh_token or "",
        )

        if not success:
            logger.error(f"Failed to store tokens for user: {request.user_id}")
            raise HTTPException(
                status_code=500, detail="Failed to store Google Drive tokens"
            )

        logger.info(f"Google Drive connection successful for user: {request.user_id}")

        return {
            "status": "success",
            "message": "Google Drive connected successfully",
            "user_id": request.user_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OAuth2 token exchange failed for user {request.user_id}: {e}")
        logger.error(f"Exception type: {type(e).__name__}")
        logger.error(f"Exception details: {str(e)}")
        raise HTTPException(
            status_code=400, detail=f"Token exchange failed: {str(e)}"
        )


@router.get("/status/{user_id}")
async def get_google_drive_status(
    user_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Check if user has connected their Google Drive."""
    try:
        tokens = get_user_google_tokens(user_id)

        return {
            "user_id": user_id,
            "connected": tokens is not None,
            "provider": "google_drive",
        }

    except Exception as e:
        logger.error(f"Failed to check Google Drive status for user {user_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to check connection status"
        )


@router.delete("/disconnect/{user_id}")
async def disconnect_google_drive(
    user_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Disconnect user's Google Drive integration."""
    try:
        _get_supabase().table("user_integrations").delete().eq(
            "user_id", user_id
        ).eq("provider", "google_drive").execute()

        logger.info(f"Disconnected Google Drive for user {user_id}")

        return {
            "status": "success",
            "message": "Google Drive disconnected successfully",
            "user_id": user_id,
        }

    except Exception as e:
        logger.error(f"Failed to disconnect Google Drive for user {user_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to disconnect Google Drive"
        )
