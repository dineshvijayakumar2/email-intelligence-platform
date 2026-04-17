"""
AI Prompt Loader — Loads configurable prompts from DB with auto-seeding.

Resolution order:
  1. Client-specific prompt (ai_prompt_config WHERE client_id = X AND prompt_key = Y)
  2. Global default prompt (ai_prompt_config WHERE client_id IS NULL AND prompt_key = Y)
  3. Auto-seed: inserts the builtin default as a global DB row (client_id IS NULL),
     then returns it — so every prompt key is editable via the playground from first use.

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
    # Check cache (client-specific key if client_id provided, else global key)
    cache_key = (client_id, prompt_key)
    cached = _cache.get(cache_key)
    if cached and (time.time() - cached[2]) < CACHE_TTL:
        return cached[0]

    # Try client-specific prompt from DB (only if client_id provided)
    if client_id:
        result = _load_from_db(supabase_client, prompt_key, client_id)
        if result:
            _cache[cache_key] = (result[0], result[1], time.time())
            return result[0]

    # Try global prompt from DB (client_id IS NULL)
    global_key = (None, prompt_key)
    global_cached = _cache.get(global_key)
    if global_cached and (time.time() - global_cached[2]) < CACHE_TTL:
        return global_cached[0]

    result = _load_global_from_db(supabase_client, prompt_key)
    if result:
        _cache[global_key] = (result[0], result[1], time.time())
        return result[0]

    # No DB entry exists — seed the builtin default as a global record so it's
    # immediately visible and editable in the playground.
    _seed_global_prompt(supabase_client, prompt_key, hardcoded_default)
    _cache[global_key] = (hardcoded_default, "v1.0", time.time())
    return hardcoded_default


def _load_from_db(
    supabase_client,
    prompt_key: str,
    client_id: str,
) -> Optional[Tuple[str, str]]:
    """Load prompt from ai_prompt_config for a specific client. Returns (prompt_text, version) or None."""
    try:
        resp = (
            supabase_client.table("ai_prompt_config")
            .select("prompt_text, version")
            .eq("prompt_key", prompt_key)
            .eq("client_id", client_id)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if rows:
            return (rows[0]["prompt_text"], rows[0].get("version", "v1.0"))
    except Exception as e:
        logger.debug(f"Failed to load prompt '{prompt_key}' for client {client_id}: {e}")
    return None


def _load_global_from_db(
    supabase_client,
    prompt_key: str,
) -> Optional[Tuple[str, str]]:
    """Load global prompt (client_id IS NULL) from ai_prompt_config. Returns (prompt_text, version) or None."""
    try:
        resp = (
            supabase_client.table("ai_prompt_config")
            .select("prompt_text, version")
            .eq("prompt_key", prompt_key)
            .is_("client_id", "null")
            .eq("is_active", True)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if rows:
            return (rows[0]["prompt_text"], rows[0].get("version", "v1.0"))
    except Exception as e:
        logger.debug(f"Failed to load global prompt '{prompt_key}': {e}")
    return None


def _seed_global_prompt(supabase_client, prompt_key: str, prompt_text: str) -> None:
    """Insert a global (client_id IS NULL) prompt row if one doesn't already exist."""
    import hashlib
    content_hash = hashlib.sha256(prompt_text.encode()).hexdigest()[:8]
    try:
        supabase_client.table("ai_prompt_config").insert({
            "prompt_key": prompt_key,
            "prompt_text": prompt_text,
            "client_id": None,
            "is_active": True,
            "description": f"Auto-seeded default for {prompt_key}",
            "version": content_hash,
        }).execute()
        logger.info(f"Auto-seeded global prompt '{prompt_key}' into DB")
    except Exception as e:
        # Ignore unique-constraint violations (already seeded) and other errors
        logger.debug(f"Seed skipped for '{prompt_key}': {e}")


def get_prompt_version(
    supabase_client,
    prompt_key: str,
    hardcoded_version: str,
    client_id: Optional[str] = None,
) -> str:
    """
    Return the effective version for a prompt key — from DB if available, else hardcoded_version.
    Follows the same Client → Global → hardcoded resolution order as get_prompt().
    Used to stamp prompt_version on analyzed emails so reprocessing stays accurate
    when prompts are edited via the playground.
    """
    if client_id:
        result = _load_from_db(supabase_client, prompt_key, client_id)
        if result:
            return result[1]

    result = _load_global_from_db(supabase_client, prompt_key)
    if result:
        return result[1]

    return hardcoded_version


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
PROMPT_KEY_WEEKLY_DIGEST = "weekly_digest"
PROMPT_KEY_INSIGHT_COMPANY = "insight_company"
PROMPT_KEY_INSIGHT_CONTACT = "insight_contact"
PROMPT_KEY_INSIGHT_THREAD = "insight_thread"
