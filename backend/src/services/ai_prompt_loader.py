"""
AI Prompt Loader — Loads configurable prompts from DB with multi-level fallback.

Resolution order:
  1. Client-specific prompt (ai_prompt_config WHERE client_id = X AND prompt_key = Y)
  2. Global default prompt (ai_prompt_config WHERE client_id IS NULL AND prompt_key = Y)
  3. Hardcoded default (passed by caller)

Caching: In-memory TTL cache (5 minutes) to avoid DB hits on every API call.
"""

import time
import logging
from typing import Optional, Dict, Tuple

logger = logging.getLogger(__name__)

# In-memory cache: key = (client_id, prompt_key) → (prompt_text, version, timestamp)
_cache: Dict[Tuple[Optional[str], str], Tuple[str, str, float]] = {}
CACHE_TTL = 300  # 5 minutes


def get_prompt(
    supabase_client,
    prompt_key: str,
    hardcoded_default: str,
    client_id: Optional[str] = None,
) -> str:
    """
    Load a prompt by key with client → global → hardcoded fallback.

    Args:
        supabase_client: Supabase client instance
        prompt_key: e.g. 'email_analysis_system', 'strategic_digest', 'daily_digest'
        hardcoded_default: The code-level default prompt (final fallback)
        client_id: Optional client ID for client-specific overrides

    Returns:
        The prompt text to use
    """
    # Check cache first (client-specific)
    cache_key = (client_id, prompt_key)
    cached = _cache.get(cache_key)
    if cached and (time.time() - cached[2]) < CACHE_TTL:
        return cached[0]

    # Try client-specific prompt
    if client_id:
        result = _load_from_db(supabase_client, prompt_key, client_id)
        if result:
            _cache[cache_key] = (result[0], result[1], time.time())
            return result[0]

    # Try global default
    global_key = (None, prompt_key)
    cached_global = _cache.get(global_key)
    if cached_global and (time.time() - cached_global[2]) < CACHE_TTL:
        return cached_global[0]

    result = _load_from_db(supabase_client, prompt_key, client_id=None)
    if result:
        _cache[global_key] = (result[0], result[1], time.time())
        return result[0]

    # Final fallback: hardcoded default
    return hardcoded_default


def _load_from_db(
    supabase_client,
    prompt_key: str,
    client_id: Optional[str],
) -> Optional[Tuple[str, str]]:
    """Load prompt from ai_prompt_config. Returns (prompt_text, version) or None."""
    try:
        query = (
            supabase_client.table("ai_prompt_config")
            .select("prompt_text, version")
            .eq("prompt_key", prompt_key)
            .eq("is_active", True)
        )
        if client_id:
            query = query.eq("client_id", client_id)
        else:
            query = query.is_("client_id", "null")

        resp = query.limit(1).execute()
        rows = resp.data or []
        if rows:
            return (rows[0]["prompt_text"], rows[0].get("version", "v1.0"))
    except Exception as e:
        logger.debug(f"Failed to load prompt '{prompt_key}' from DB: {e}")
    return None


def invalidate_cache(client_id: Optional[str] = None, prompt_key: Optional[str] = None):
    """Clear cached prompts. Call after updating prompts via API."""
    if prompt_key and client_id is not None:
        _cache.pop((client_id, prompt_key), None)
    elif prompt_key:
        # Clear all entries for this key
        to_remove = [k for k in _cache if k[1] == prompt_key]
        for k in to_remove:
            del _cache[k]
    else:
        _cache.clear()


# Prompt key constants (used across services)
PROMPT_KEY_EMAIL_ANALYSIS_SYSTEM = "email_analysis_system"
PROMPT_KEY_EMAIL_ANALYSIS_USER = "email_analysis_user"
PROMPT_KEY_STRATEGIC_DIGEST = "strategic_digest"
PROMPT_KEY_DAILY_DIGEST = "daily_digest"
PROMPT_KEY_INSIGHT_COMPANY = "insight_company"
PROMPT_KEY_INSIGHT_CONTACT = "insight_contact"
PROMPT_KEY_INSIGHT_THREAD = "insight_thread"
