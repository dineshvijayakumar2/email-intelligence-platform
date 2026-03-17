"""
Number Format Utility — Per-client currency formatting (mirrors timezone pattern).

Usage:
    from ..utils.number_format import get_client_currency_code, format_currency

    currency = get_client_currency_code(supabase, client_id)   # e.g. "AUD"
    label    = format_currency(123456.78, currency)             # "$123,457"
    label    = format_currency(123456.78, currency, decimals=2) # "$123,456.78"

Supported ISO 4217 codes and their display symbols:

    AUD  →  $     (Australian Dollar)
    USD  →  $     (US Dollar)
    NZD  →  $     (New Zealand Dollar)
    CAD  →  $     (Canadian Dollar)
    GBP  →  £     (British Pound)
    EUR  →  €     (Euro)
    SGD  →  $     (Singapore Dollar)
    HKD  →  $     (Hong Kong Dollar)
    JPY  →  ¥     (Japanese Yen — no decimals)
    INR  →  ₹     (Indian Rupee)

All dollar-sign currencies are disambiguated by their code label when needed in AI
prompts (e.g. "AUD $123,456") so the LLM understands the context.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Currency metadata
# ---------------------------------------------------------------------------
_CURRENCY_META = {
    "AUD": {"symbol": "$", "code_label": "AUD", "decimals": 0, "thousands_sep": ",", "decimal_sep": "."},
    "USD": {"symbol": "$", "code_label": "USD", "decimals": 0, "thousands_sep": ",", "decimal_sep": "."},
    "NZD": {"symbol": "$", "code_label": "NZD", "decimals": 0, "thousands_sep": ",", "decimal_sep": "."},
    "CAD": {"symbol": "$", "code_label": "CAD", "decimals": 0, "thousands_sep": ",", "decimal_sep": "."},
    "SGD": {"symbol": "$", "code_label": "SGD", "decimals": 0, "thousands_sep": ",", "decimal_sep": "."},
    "HKD": {"symbol": "$", "code_label": "HKD", "decimals": 0, "thousands_sep": ",", "decimal_sep": "."},
    "GBP": {"symbol": "£", "code_label": "GBP", "decimals": 0, "thousands_sep": ",", "decimal_sep": "."},
    "EUR": {"symbol": "€", "code_label": "EUR", "decimals": 0, "thousands_sep": ".", "decimal_sep": ","},
    "JPY": {"symbol": "¥", "code_label": "JPY", "decimals": 0, "thousands_sep": ",", "decimal_sep": "."},
    "INR": {"symbol": "₹", "code_label": "INR", "decimals": 0, "thousands_sep": ",", "decimal_sep": "."},
}

_DEFAULT_CURRENCY = "AUD"


# ---------------------------------------------------------------------------
# Client currency loader (same pattern as _get_client_timezone)
# ---------------------------------------------------------------------------
def get_client_currency_code(supabase, client_id: Optional[str]) -> str:
    """
    Load per-client currency code from the clients table.

    Falls back to AUD if the column is missing, null, or the DB call fails.
    Mirrors _get_client_timezone() in am_efficiency_analyzer.py.
    """
    if not client_id:
        return _DEFAULT_CURRENCY
    try:
        resp = (
            supabase.table("clients")
            .select("currency_code")
            .eq("id", client_id)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        code = (rows[0].get("currency_code") or _DEFAULT_CURRENCY) if rows else _DEFAULT_CURRENCY
        return code.upper().strip() if code else _DEFAULT_CURRENCY
    except Exception:
        return _DEFAULT_CURRENCY


# ---------------------------------------------------------------------------
# Formatter
# ---------------------------------------------------------------------------
def format_currency(
    amount,
    currency_code: str = _DEFAULT_CURRENCY,
    decimals: Optional[int] = None,
    include_code: bool = False,
) -> str:
    """
    Format a numeric amount as a currency string.

    Args:
        amount:        Numeric value (int / float / None). None → "N/A".
        currency_code: ISO 4217 code (e.g. "AUD"). Unknown codes fall back to AUD.
        decimals:      Override decimal places (default: from currency meta).
        include_code:  Prefix with code label, e.g. "AUD $123,456". Useful in AI
                       prompts so the LLM knows which currency is intended.

    Returns:
        Formatted string, e.g. "$123,456" or "AUD $1,234.56" or "N/A".
    """
    if amount is None:
        return "N/A"

    meta = _CURRENCY_META.get(currency_code.upper(), _CURRENCY_META[_DEFAULT_CURRENCY])
    dp = decimals if decimals is not None else meta["decimals"]
    symbol = meta["symbol"]
    code_label = meta["code_label"]

    try:
        value = float(amount)
    except (TypeError, ValueError):
        return "N/A"

    # Format with Python's built-in comma thousands + configurable decimals
    formatted = f"{value:,.{dp}f}"

    result = f"{symbol}{formatted}"
    if include_code:
        result = f"{code_label} {result}"
    return result


def format_currency_range(low, high, currency_code: str = _DEFAULT_CURRENCY) -> str:
    """Format a value range, e.g. '$50,000 – $100,000'."""
    return f"{format_currency(low, currency_code)} – {format_currency(high, currency_code)}"
