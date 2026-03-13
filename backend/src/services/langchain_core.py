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
}

ModelName = Literal["haiku", "sonnet", "gemini"]

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


def get_available_models() -> list[dict]:
    """Return list of available models with their configs (for frontend)."""
    models = []
    for name, config in MODEL_CONFIGS.items():
        available = True
        if config["provider"] == "anthropic":
            available = bool(os.environ.get("ANTHROPIC_API_KEY"))
        elif config["provider"] == "google":
            available = bool(os.environ.get("GOOGLE_GENAI_API_KEY") or os.environ.get("GEMINI_API_KEY"))

        models.append({
            "name": name,
            "label": config["label"],
            "provider": config["provider"],
            "cost_input_per_mtok": config["cost_input_per_mtok"],
            "cost_output_per_mtok": config["cost_output_per_mtok"],
            "available": available,
        })
    return models
