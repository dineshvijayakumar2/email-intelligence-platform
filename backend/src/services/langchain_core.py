"""
LangChain Core — Shared AI backbone for the platform (Sprint 3).

Multi-model support: Claude (Anthropic) + Gemini (Google) with automatic
budget tracking via existing ai_usage_tracker.

Usage:
    from .langchain_core import get_llm, get_cheap_llm, get_strategic_llm

    # For per-email / fast tasks (Gemini free tier or Haiku)
    llm = get_cheap_llm()

    # For strategic / high-quality tasks (Sonnet)
    llm = get_strategic_llm()

    # Explicit model selection
    llm = get_llm("gemini")  # or "haiku" or "sonnet"
"""

import os
import logging
from typing import Literal, Optional

from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.language_models import BaseChatModel

try:
    from langchain_openai import ChatOpenAI
    _openai_available = True
except ImportError:
    _openai_available = False

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model configs
# ---------------------------------------------------------------------------
MODEL_CONFIGS = {
    "haiku": {
        "provider": "anthropic",
        "model": "claude-haiku-4-5-20251001",
        "cost_input_per_mtok": 0.80,
        "cost_output_per_mtok": 4.00,
        "max_tokens": 4096,
        "label": "Claude Haiku (fast, cheap)",
    },
    "sonnet": {
        "provider": "anthropic",
        "model": "claude-sonnet-4-6-20250514",
        "cost_input_per_mtok": 3.00,
        "cost_output_per_mtok": 15.00,
        "max_tokens": 8192,
        "label": "Claude Sonnet (strategic)",
    },
    "gemini": {
        "provider": "google",
        "model": "gemini-2.5-flash",
        "cost_input_per_mtok": 0.15,
        "cost_output_per_mtok": 0.60,
        "max_tokens": 8192,
        "label": "Gemini 2.5 Flash",
    },
    "gpt4o-mini": {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "cost_input_per_mtok": 0.15,
        "cost_output_per_mtok": 0.60,
        "max_tokens": 4096,
        "label": "GPT-4o Mini (cheap)",
    },
    "gpt4o": {
        "provider": "openai",
        "model": "gpt-4o",
        "cost_input_per_mtok": 2.50,
        "cost_output_per_mtok": 10.00,
        "max_tokens": 8192,
        "label": "GPT-4o (strategic)",
    },
}

ModelName = Literal["haiku", "sonnet", "gemini", "gpt4o-mini", "gpt4o"]

# ---------------------------------------------------------------------------
# Default model preferences — read from env so Railway config persists across restarts
# ---------------------------------------------------------------------------
_default_cheap_model: ModelName = os.environ.get("AI_CHEAP_MODEL", "haiku")  # type: ignore[assignment]
_default_strategic_model: ModelName = os.environ.get("AI_STRATEGIC_MODEL", "sonnet")  # type: ignore[assignment]


def set_default_models(cheap: ModelName = "haiku", strategic: ModelName = "sonnet"):
    """Update default model preferences (called from AI controls API)."""
    global _default_cheap_model, _default_strategic_model
    _default_cheap_model = cheap
    _default_strategic_model = strategic
    logger.info(f"LangChain defaults updated: cheap={cheap}, strategic={strategic}")


def get_llm(model_name: Optional[ModelName] = None, temperature: float = 0.0, json_mode: bool = False) -> BaseChatModel:
    """
    Get a LangChain LLM instance for the specified model.

    Args:
        model_name: "haiku", "sonnet", or "gemini". Defaults to cheap model.
        temperature: LLM temperature (0.0 = deterministic)
        json_mode: For Gemini — forces response_mime_type="application/json" so the
                   model always emits valid JSON. Has no effect on Anthropic models
                   (Claude reliably follows JSON instructions without it).

    Returns:
        LangChain ChatModel instance
    """
    name = model_name or _default_cheap_model
    config = MODEL_CONFIGS[name]

    if config["provider"] == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        return ChatAnthropic(
            model=config["model"],
            anthropic_api_key=api_key,
            temperature=temperature,
            max_tokens=config["max_tokens"],
        )
    elif config["provider"] == "google":
        api_key = os.environ.get("GOOGLE_GENAI_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            logger.warning("GOOGLE_GENAI_API_KEY not set — falling back to Haiku")
            return get_llm("haiku", temperature)
        kwargs = dict(
            model=config["model"],
            google_api_key=api_key,
            temperature=temperature,
            max_output_tokens=config["max_tokens"],
        )
        if json_mode:
            kwargs["response_mime_type"] = "application/json"
        return ChatGoogleGenerativeAI(**kwargs)
    elif config["provider"] == "openai":
        if not _openai_available:
            logger.warning("langchain-openai not installed — falling back to Gemini")
            return get_llm("gemini", temperature)
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY not set — falling back to Gemini")
            return get_llm("gemini", temperature)
        return ChatOpenAI(
            model=config["model"],
            api_key=api_key,
            temperature=temperature,
            max_tokens=config["max_tokens"],
        )
    else:
        raise ValueError(f"Unknown provider: {config['provider']}")


def get_cheap_llm(temperature: float = 0.0) -> BaseChatModel:
    """Get the default cheap/fast LLM (Gemini free tier or Haiku)."""
    return get_llm(_default_cheap_model, temperature)


def get_strategic_llm(temperature: float = 0.1) -> BaseChatModel:
    """Get the default high-quality LLM (Sonnet)."""
    return get_llm(_default_strategic_model, temperature)


def get_model_config(model_name: ModelName) -> dict:
    """Get config dict for a model (for cost tracking)."""
    return MODEL_CONFIGS[model_name]


# ---------------------------------------------------------------------------
# Per-task model resolution (reads from DB > env > defaults)
# ---------------------------------------------------------------------------
TASK_MODEL_DEFAULTS = {
    'email_analysis': 'haiku',
    'daily_digest': 'sonnet',
    'strategic_digest': 'sonnet',
    'entity_insights': 'haiku',
    # Future tasks — registered now so DB keys and UI dropdowns work
    # before the services themselves are built.
    'action_items': 'haiku',
    'feedback_learning': 'haiku',
    'industry_profile': 'sonnet',
    'thread_intent': 'haiku',
}

# Legacy mapping: task → which tier it belonged to
_TASK_LEGACY_TIER = {
    'email_analysis': 'cheap',
    'daily_digest': 'strategic',
    'strategic_digest': 'strategic',
    'entity_insights': 'cheap',
    'action_items': 'cheap',
    'feedback_learning': 'cheap',
    'industry_profile': 'strategic',
    'thread_intent': 'cheap',
}

# In-memory cache for task models (loaded from DB)
_task_model_cache: dict = {}
_task_model_cache_expires: float = 0


def get_task_model(task: str, client_id: str = None, temperature: float = 0.0, json_mode: bool = False) -> BaseChatModel:
    """Get a LangChain LLM for a specific AI task.

    Priority: DB setting (ai_model_{task}) > legacy cheap/strategic > env var > default.

    Args:
        task: 'email_analysis', 'daily_digest', 'strategic_digest', 'entity_insights'
        client_id: Client UUID for per-client settings
        temperature: LLM temperature
        json_mode: Force JSON output (Gemini only)
    """
    model_name = resolve_task_model_name(task, client_id)
    return get_llm(model_name, temperature, json_mode)


def resolve_task_model_name(task: str, client_id: str = None) -> ModelName:
    """Resolve the model name for a task. DB > legacy tier > env > default."""
    import time as _time
    global _task_model_cache, _task_model_cache_expires

    # Check cache (60s TTL)
    cache_key = f"{client_id or 'none'}_{task}"
    if cache_key in _task_model_cache and _task_model_cache_expires > _time.time():
        return _task_model_cache[cache_key]

    model_name = None
    db_key = f"ai_model_{task}"

    # Try DB
    if client_id:
        try:
            from ..database.supabase_client import SupabaseClient
            sb = SupabaseClient.get_client(use_service_key=True)
            resp = sb.table('system_settings').select('value').eq(
                'key', db_key
            ).eq('client_id', client_id).limit(1).execute()
            if resp.data and resp.data[0].get('value'):
                model_name = resp.data[0]['value']
        except Exception:
            pass

    # Fallback to legacy cheap/strategic tier
    if not model_name:
        tier = _TASK_LEGACY_TIER.get(task, 'cheap')
        if tier == 'cheap':
            model_name = _default_cheap_model
        else:
            model_name = _default_strategic_model

    # Validate model exists
    if model_name not in MODEL_CONFIGS:
        model_name = TASK_MODEL_DEFAULTS.get(task, 'haiku')

    # Cache
    _task_model_cache[cache_key] = model_name
    _task_model_cache_expires = _time.time() + 60

    return model_name


def get_all_task_models(client_id: str = None) -> dict:
    """Get current model assignment for all tasks. Used by GET /ai/task-models."""
    result = {}
    for task in TASK_MODEL_DEFAULTS:
        db_key = f"ai_model_{task}"
        source = 'default'
        model = TASK_MODEL_DEFAULTS[task]

        # Check DB
        if client_id:
            try:
                from ..database.supabase_client import SupabaseClient
                sb = SupabaseClient.get_client(use_service_key=True)
                resp = sb.table('system_settings').select('value').eq(
                    'key', db_key
                ).eq('client_id', client_id).limit(1).execute()
                if resp.data and resp.data[0].get('value'):
                    model = resp.data[0]['value']
                    source = 'db'
            except Exception:
                pass

        # If not in DB, check legacy tier settings
        if source == 'default':
            tier = _TASK_LEGACY_TIER.get(task, 'cheap')
            tier_model = _default_cheap_model if tier == 'cheap' else _default_strategic_model
            if tier_model != TASK_MODEL_DEFAULTS[task]:
                model = tier_model
                source = 'env'

        result[task] = {'model': model, 'source': source}

    return result


def set_task_model(task: str, model_name: str, client_id: str):
    """Save a task model assignment to DB."""
    if task not in TASK_MODEL_DEFAULTS:
        raise ValueError(f"Unknown task: {task}")
    if model_name not in MODEL_CONFIGS:
        raise ValueError(f"Unknown model: {model_name}")
    try:
        from ..database.supabase_client import SupabaseClient
        from datetime import datetime
        sb = SupabaseClient.get_client(use_service_key=True)
        db_key = f"ai_model_{task}"

        existing = sb.table('system_settings').select('id').eq(
            'key', db_key
        ).eq('client_id', client_id).limit(1).execute()

        row = {'key': db_key, 'value': model_name, 'client_id': client_id,
               'updated_at': datetime.utcnow().isoformat()}

        if existing.data:
            sb.table('system_settings').update(row).eq('id', existing.data[0]['id']).execute()
        else:
            sb.table('system_settings').insert(row).execute()

        # Invalidate cache
        global _task_model_cache_expires
        _task_model_cache_expires = 0
    except Exception as e:
        logger.warning(f"Failed to save task model {task}={model_name}: {e}")
        raise


def get_available_models() -> list[dict]:
    """Return list of available models with their configs (for frontend)."""
    models = []
    for name, config in MODEL_CONFIGS.items():
        available = True
        if config["provider"] == "anthropic":
            available = bool(os.environ.get("ANTHROPIC_API_KEY"))
        elif config["provider"] == "google":
            available = bool(os.environ.get("GOOGLE_GENAI_API_KEY") or os.environ.get("GEMINI_API_KEY"))
        elif config["provider"] == "openai":
            available = _openai_available and bool(os.environ.get("OPENAI_API_KEY"))

        models.append({
            "name": name,
            "label": config["label"],
            "provider": config["provider"],
            "cost_input_per_mtok": config["cost_input_per_mtok"],
            "cost_output_per_mtok": config["cost_output_per_mtok"],
            "available": available,
        })
    return models
