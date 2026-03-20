"""
AI Prompt Loader — Loads configurable prompts from DB with auto-seeding.

Resolution order:
  1. Client-specific prompt (ai_prompt_config WHERE client_id = X AND prompt_key = Y)
  2. Global default prompt (ai_prompt_config WHERE client_id IS NULL AND prompt_key = Y)
  3. Auto-seed: inserts the builtin default as a global DB row (client_id IS NULL),
     then returns it — so every prompt key is editable via the playground from first use.

Caching: In-memory TTL cache (5 minutes) to avoid DB hits on every API call.

JSON sync: On startup, sync_from_json_files() reads backend/src/prompts/*.json and
UPSERTs global DB rows when the JSON version is newer — keeping JSON files and DB
always synchronised. Client-specific overrides are never touched.
"""

import time
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Tuple

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

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
    try:
        supabase_client.table("ai_prompt_config").insert({
            "prompt_key": prompt_key,
            "prompt_text": prompt_text,
            "client_id": None,
            "is_active": True,
            "description": f"Auto-seeded default for {prompt_key}",
            "version": "v1.0",
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


def sync_from_json_files(supabase_client) -> None:
    """
    Sync prompt JSON files → ai_prompt_config DB table (global rows only).

    Called once at startup. For each *.json file in backend/src/prompts/:
    - If no global DB row exists → INSERT
    - If global DB row exists and JSON version > DB version → UPDATE
    - Client-specific overrides (client_id IS NOT NULL) are never touched.
    """
    if not PROMPTS_DIR.exists():
        logger.warning(f"[PromptSync] Prompts directory not found: {PROMPTS_DIR}")
        return

    synced, skipped, failed = 0, 0, 0
    for json_file in sorted(PROMPTS_DIR.glob("*.json")):
        try:
            with open(json_file, encoding="utf-8") as f:
                data = json.load(f)

            prompt_key = data.get("prompt_key")
            json_version = data.get("version")
            prompt_text = data.get("prompt_text")
            description = data.get("description", f"Default for {prompt_key}")

            if not (prompt_key and json_version and prompt_text):
                logger.warning(f"[PromptSync] Skipping {json_file.name}: missing required fields")
                continue

            existing = _load_global_from_db(supabase_client, prompt_key)

            if existing is None:
                supabase_client.table("ai_prompt_config").insert({
                    "prompt_key": prompt_key,
                    "prompt_text": prompt_text,
                    "version": json_version,
                    "client_id": None,
                    "is_active": True,
                    "description": description,
                }).execute()
                logger.info(f"[PromptSync] Seeded '{prompt_key}' ({json_version})")
                synced += 1
            elif _version_gt(json_version, existing[1]):
                supabase_client.table("ai_prompt_config").update({
                    "prompt_text": prompt_text,
                    "version": json_version,
                    "description": description,
                }).eq("prompt_key", prompt_key).is_("client_id", "null").execute()
                _cache.pop((None, prompt_key), None)  # Invalidate cache
                logger.info(f"[PromptSync] Updated '{prompt_key}': {existing[1]} → {json_version}")
                synced += 1
            else:
                logger.debug(f"[PromptSync] '{prompt_key}' DB ({existing[1]}) >= JSON ({json_version}), skipped")
                skipped += 1

        except Exception as e:
            logger.warning(f"[PromptSync] Failed to process {json_file.name}: {e}")
            failed += 1

    logger.info(f"[PromptSync] Complete — {synced} synced, {skipped} skipped, {failed} failed")


def _version_gt(v1: str, v2: str) -> bool:
    """Returns True if version string v1 > v2 (e.g. 'v1.4' > 'v1.3')."""
    def parse(v):
        try:
            return [int(x) for x in v.lstrip("v").split(".")]
        except Exception:
            return [0]
    return parse(v1) > parse(v2)


# Prompt key constants (used across services)
PROMPT_KEY_EMAIL_ANALYSIS_SYSTEM = "email_analysis_system"
PROMPT_KEY_EMAIL_ANALYSIS_USER = "email_analysis_user"
PROMPT_KEY_STRATEGIC_DIGEST = "strategic_digest"
PROMPT_KEY_DAILY_DIGEST = "daily_digest"
PROMPT_KEY_WEEKLY_DIGEST = "weekly_digest"
PROMPT_KEY_INSIGHT_COMPANY = "insight_company"
PROMPT_KEY_INSIGHT_CONTACT = "insight_contact"
PROMPT_KEY_INSIGHT_THREAD = "insight_thread"
