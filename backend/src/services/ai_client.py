"""
AI Client — Shared Claude API wrapper for Sprint 3 Intelligence Layer.

Uses the official `anthropic` Python SDK with two model configs:
  - Haiku (email intelligence): fast, cheap (~$0.001/email)
  - Sonnet (digests/summaries): higher quality for synthesis tasks

Handles: retries, rate limiting, cost calculation, graceful degradation.
"""

import os
import time
import logging
from typing import Optional
from dataclasses import dataclass, field

import anthropic

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model configuration
# ---------------------------------------------------------------------------
HAIKU_MODEL = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-4-6"

# Pricing per million tokens (USD)
MODEL_PRICING = {
    HAIKU_MODEL: {"input": 0.80, "output": 4.00},
    SONNET_MODEL: {"input": 3.00, "output": 15.00},
}

# Rate limiting
MAX_REQUESTS_PER_SECOND = 10
MIN_REQUEST_INTERVAL = 1.0 / MAX_REQUESTS_PER_SECOND  # 0.1s

# Retry configuration
MAX_RETRIES = 3
BASE_RETRY_DELAY = 2.0  # seconds, doubles each retry


# ---------------------------------------------------------------------------
# AI Control Settings — runtime-adjustable switches
# ---------------------------------------------------------------------------
@dataclass
class AIControlSettings:
    """Runtime controls for AI features. Persisted to system_settings DB table."""
    # Master kill switch — disables ALL AI calls
    ai_enabled: bool = True
    # Per-feature toggles
    email_analysis_enabled: bool = True
    digest_enabled: bool = True
    relationship_summary_enabled: bool = True
    # Budget controls
    daily_budget_usd: float = 2.00       # Max spend per day ($2 default)
    monthly_budget_usd: float = 16.00    # Max spend per month
    # Batch controls
    batch_size: int = 10                 # Emails per Claude call
    max_emails_per_run: int = 500        # Max emails per analysis trigger
    # Rate controls
    max_requests_per_second: float = 10.0
    # Model preferences — default from env, overridden by DB
    cheap_model: str = field(default_factory=lambda: os.getenv("AI_CHEAP_MODEL", "haiku"))
    strategic_model: str = field(default_factory=lambda: os.getenv("AI_STRATEGIC_MODEL", "sonnet"))


# Global settings singleton
_ai_settings = AIControlSettings()
_settings_loaded_from_db = False

# Spend cache — avoids hitting DB on every AI call (60s TTL)
_spend_cache: dict = {}


# ---------------------------------------------------------------------------
# DB key mapping: dataclass field name → system_settings key
# ---------------------------------------------------------------------------
_SETTINGS_DB_KEYS = {
    'ai_enabled': 'ai_enabled',
    'email_analysis_enabled': 'email_analysis_enabled',
    'digest_enabled': 'digest_enabled',
    'relationship_summary_enabled': 'relationship_summary_enabled',
    'daily_budget_usd': 'daily_budget_usd',
    'monthly_budget_usd': 'monthly_budget_usd',
    'batch_size': 'batch_size',
    'max_emails_per_run': 'max_emails_per_run',
    'max_requests_per_second': 'max_requests_per_second',
    'cheap_model': 'ai_cheap_model',
    'strategic_model': 'ai_strategic_model',
}

_BOOL_FIELDS = {'ai_enabled', 'email_analysis_enabled', 'digest_enabled', 'relationship_summary_enabled'}
_FLOAT_FIELDS = {'daily_budget_usd', 'monthly_budget_usd', 'max_requests_per_second'}
_INT_FIELDS = {'batch_size', 'max_emails_per_run'}


def load_ai_settings_from_db(client_id: Optional[str] = None):
    """Load AI control settings from system_settings DB table.

    Called on startup and after settings updates. Falls back to env vars then defaults.
    """
    global _ai_settings, _settings_loaded_from_db
    if not client_id:
        logger.info("No client_id for AI settings — using defaults + env vars")
        _settings_loaded_from_db = True
        return

    try:
        from ..database.supabase_client import SupabaseClient
        sb = SupabaseClient.get_client(use_service_key=True)

        resp = sb.table('system_settings').select('key, value').eq(
            'client_id', client_id
        ).execute()
        db_map = {r['key']: r['value'] for r in (resp.data or [])}

        for field_name, db_key in _SETTINGS_DB_KEYS.items():
            if db_key in db_map:
                raw = db_map[db_key]
                if field_name in _BOOL_FIELDS:
                    setattr(_ai_settings, field_name, raw.lower() in ('true', '1', 'yes'))
                elif field_name in _FLOAT_FIELDS:
                    setattr(_ai_settings, field_name, float(raw))
                elif field_name in _INT_FIELDS:
                    setattr(_ai_settings, field_name, int(raw))
                else:
                    setattr(_ai_settings, field_name, raw)

        _settings_loaded_from_db = True
        logger.info(f"AI settings loaded from DB for client {client_id}: ai_enabled={_ai_settings.ai_enabled}, "
                     f"budget=${_ai_settings.daily_budget_usd}")
    except Exception as e:
        logger.warning(f"Failed to load AI settings from DB (using defaults): {e}")
        _settings_loaded_from_db = True


def save_ai_setting_to_db(field_name: str, value, client_id: Optional[str] = None):
    """Persist a single AI setting to system_settings DB table."""
    if not client_id:
        return
    db_key = _SETTINGS_DB_KEYS.get(field_name)
    if not db_key:
        return
    try:
        from ..database.supabase_client import SupabaseClient
        sb = SupabaseClient.get_client(use_service_key=True)

        str_value = str(value).lower() if isinstance(value, bool) else str(value)

        existing = sb.table('system_settings').select('id').eq(
            'key', db_key
        ).eq('client_id', client_id).limit(1).execute()

        from datetime import datetime
        row = {'key': db_key, 'value': str_value, 'client_id': client_id,
               'updated_at': datetime.utcnow().isoformat()}

        if existing.data:
            sb.table('system_settings').update(row).eq('id', existing.data[0]['id']).execute()
        else:
            sb.table('system_settings').insert(row).execute()
    except Exception as e:
        logger.warning(f"Failed to save AI setting {field_name}={value} to DB: {e}")


def get_ai_settings() -> AIControlSettings:
    """Get the current AI control settings."""
    return _ai_settings


def update_ai_settings(client_id: Optional[str] = None, **kwargs) -> AIControlSettings:
    """Update AI control settings in memory AND persist to DB."""
    global _ai_settings
    for key, value in kwargs.items():
        if hasattr(_ai_settings, key):
            setattr(_ai_settings, key, value)
            # Persist to DB
            if client_id:
                save_ai_setting_to_db(key, value, client_id)
    logger.info(f"AI settings updated: {kwargs}")
    return _ai_settings


def get_actual_spend(client_id: Optional[str] = None, period: str = 'daily') -> float:
    """Query ai_usage_log for actual spend. Cached 60s in-memory.

    Args:
        client_id: Client UUID (optional — if None, returns all clients' spend)
        period: 'daily' (since midnight UTC) or 'monthly' (since 1st of month)
    """
    import time as _time
    cache_key = f"spend_{client_id or 'all'}_{period}"
    cached = _spend_cache.get(cache_key)
    if cached and cached['expires'] > _time.time():
        return cached['value']

    try:
        from ..database.supabase_client import SupabaseClient
        from datetime import datetime, timezone
        sb = SupabaseClient.get_client(use_service_key=True)

        now = datetime.now(timezone.utc)
        if period == 'daily':
            since = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        else:
            since = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

        query = sb.table('ai_usage_log').select('estimated_cost_usd').gte(
            'created_at', since
        ).eq('success', 'true')
        if client_id:
            query = query.eq('client_id', client_id)

        total = 0.0
        offset = 0
        while True:
            resp = query.range(offset, offset + 499).execute()
            rows = resp.data or []
            if not rows:
                break
            for r in rows:
                total += float(r.get('estimated_cost_usd') or 0)
            offset += len(rows)

        _spend_cache[cache_key] = {'value': round(total, 4), 'expires': _time.time() + 60}
        return round(total, 4)
    except Exception as e:
        logger.warning(f"Failed to query actual spend: {e}")
        return 0.0


@dataclass
class AIResponse:
    """Structured response from a Claude API call."""
    content: str
    input_tokens: int
    output_tokens: int
    model: str
    raw_response: dict
    estimated_cost_usd: float
    processing_time_ms: int


class AIClient:
    """Shared Claude API client with retry, rate limiting, and cost tracking."""

    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY not set — AI features will be unavailable")
            self._client = None
        else:
            self._client = anthropic.Anthropic(api_key=api_key)
        self._last_request_time = 0.0
        self.last_error: Optional[str] = None  # Sprint 3: capture error detail for UI

    @property
    def is_available(self) -> bool:
        """Check if the AI client is configured and ready."""
        return self._client is not None

    def _rate_limit(self):
        """Enforce rate limiting between API calls."""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.time()

    def _calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Calculate estimated cost in USD for a given API call."""
        pricing = MODEL_PRICING.get(model, MODEL_PRICING[HAIKU_MODEL])
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        return round(input_cost + output_cost, 6)

    def _call_model(
        self,
        model: str,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> Optional[AIResponse]:
        """
        Call Claude with retry logic and graceful degradation.

        Returns None if the API is unavailable or all retries fail.
        The caller should mark the item as 'failed' with error_type.
        """
        if not self.is_available:
            logger.error("AI client not configured — ANTHROPIC_API_KEY missing")
            return None

        # Check AI control switches
        settings = get_ai_settings()
        if not settings.ai_enabled:
            logger.warning("AI is disabled via kill switch")
            return None

        # Check daily budget against actual DB spend (cached 60s)
        actual_daily = get_actual_spend(period='daily')
        if actual_daily >= settings.daily_budget_usd:
            logger.warning(
                f"Daily budget exceeded: ${actual_daily:.4f} >= "
                f"${settings.daily_budget_usd:.2f}. Blocking API call."
            )
            return None

        last_error = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                self._rate_limit()

                start_ms = int(time.time() * 1000)

                response = self._client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_message}],
                )

                end_ms = int(time.time() * 1000)

                content = response.content[0].text if response.content else ""
                input_tokens = response.usage.input_tokens
                output_tokens = response.usage.output_tokens

                cost = self._calculate_cost(model, input_tokens, output_tokens)

                return AIResponse(
                    content=content,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    model=model,
                    raw_response={
                        "id": response.id,
                        "model": response.model,
                        "stop_reason": response.stop_reason,
                        "usage": {
                            "input_tokens": input_tokens,
                            "output_tokens": output_tokens,
                        },
                        "content": content,
                    },
                    estimated_cost_usd=cost,
                    processing_time_ms=end_ms - start_ms,
                )

            except anthropic.RateLimitError as e:
                last_error = e
                if attempt < MAX_RETRIES:
                    delay = BASE_RETRY_DELAY * (2 ** attempt)
                    logger.warning(
                        f"Rate limited (attempt {attempt + 1}/{MAX_RETRIES + 1}), "
                        f"retrying in {delay}s"
                    )
                    time.sleep(delay)
                    continue

            except anthropic.APIStatusError as e:
                last_error = e
                # Retry on 5xx server errors
                if e.status_code >= 500 and attempt < MAX_RETRIES:
                    delay = BASE_RETRY_DELAY * (2 ** attempt)
                    logger.warning(
                        f"API server error {e.status_code} (attempt {attempt + 1}/{MAX_RETRIES + 1}), "
                        f"retrying in {delay}s"
                    )
                    time.sleep(delay)
                    continue
                # Non-retryable API errors (4xx except rate limit)
                error_msg = str(e)
                # Extract human-readable message from API error
                if hasattr(e, 'body') and isinstance(e.body, dict):
                    error_msg = e.body.get('error', {}).get('message', str(e))
                self.last_error = error_msg
                logger.error(f"Claude API error (non-retryable): {error_msg}")
                return None

            except anthropic.APIConnectionError as e:
                last_error = e
                if attempt < MAX_RETRIES:
                    delay = BASE_RETRY_DELAY * (2 ** attempt)
                    logger.warning(
                        f"Connection error (attempt {attempt + 1}/{MAX_RETRIES + 1}), "
                        f"retrying in {delay}s: {str(e)[:200]}"
                    )
                    time.sleep(delay)
                    continue

            except Exception as e:
                last_error = e
                logger.error(f"Unexpected error calling Claude API: {e}")
                return None

        self.last_error = str(last_error) if last_error else "All retries failed"
        logger.error(f"All {MAX_RETRIES + 1} attempts failed for Claude API: {last_error}")
        return None

    def _call_via_langchain(
        self,
        model_name: str,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        json_mode: bool = False,
    ) -> Optional[AIResponse]:
        """
        Call a non-Anthropic model (e.g. Gemini) via LangChain and wrap the
        result in an AIResponse so existing callers need no changes.
        """
        try:
            from .langchain_core import get_llm, MODEL_CONFIGS
            from langchain_core.messages import HumanMessage, SystemMessage

            start_ms = int(time.time() * 1000)
            llm = get_llm(model_name, temperature, json_mode=json_mode)  # type: ignore[arg-type]
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_message),
            ]
            response = llm.invoke(messages)
            end_ms = int(time.time() * 1000)

            content = response.content if isinstance(response.content, str) else str(response.content)
            usage = getattr(response, "usage_metadata", None) or {}
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)

            cfg = MODEL_CONFIGS.get(model_name, {})
            cost = round(
                (input_tokens / 1_000_000) * cfg.get("cost_input_per_mtok", 0.0)
                + (output_tokens / 1_000_000) * cfg.get("cost_output_per_mtok", 0.0),
                6,
            )

            # Track session spend
            settings = get_ai_settings()
            settings.session_spend_usd += cost
            settings.session_requests += 1

            return AIResponse(
                content=content,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=cfg.get("model", model_name),
                raw_response={"content": content, "usage": usage},
                estimated_cost_usd=cost,
                processing_time_ms=end_ms - start_ms,
            )
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"LangChain call failed for model '{model_name}': {e}")
            return None

    def call_haiku(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        json_mode: bool = False,
    ) -> Optional[AIResponse]:
        """Call cheap/fast model. Respects configured cheap_model preference."""
        cheap = get_ai_settings().cheap_model  # "haiku" or "gemini"
        if cheap != "haiku":
            return self._call_via_langchain(cheap, system_prompt, user_message, max_tokens, temperature, json_mode=json_mode)
        return self._call_model(
            model=HAIKU_MODEL,
            system_prompt=system_prompt,
            user_message=user_message,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    def call_sonnet(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> Optional[AIResponse]:
        """Call strategic/quality model. Respects configured strategic_model preference."""
        strategic = get_ai_settings().strategic_model  # "sonnet" or "gemini"
        if strategic != "sonnet":
            return self._call_via_langchain(strategic, system_prompt, user_message, max_tokens, temperature)
        return self._call_model(
            model=SONNET_MODEL,
            system_prompt=system_prompt,
            user_message=user_message,
            max_tokens=max_tokens,
            temperature=temperature,
        )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_ai_client: Optional[AIClient] = None


def get_ai_client() -> AIClient:
    """Get or create the singleton AI client instance."""
    global _ai_client
    if _ai_client is None:
        _ai_client = AIClient()
    return _ai_client
