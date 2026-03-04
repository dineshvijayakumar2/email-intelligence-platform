"""
AI Privacy Filter — Sanitize email bodies before sending to Claude API.

Strips sensitive data (credit cards, SSN, API keys, tokens, passwords)
while preserving business-relevant content (names, titles, company info).

Truncates to MAX_BODY_LENGTH after sanitization to control API costs.
"""

import re
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MAX_BODY_LENGTH = 300  # chars after sanitization — reduced from 500 for ~40% cost savings


# ---------------------------------------------------------------------------
# Regex patterns for sensitive data
# ---------------------------------------------------------------------------

# Credit card numbers (13-19 digits, with optional separators)
_CREDIT_CARD_RE = re.compile(
    r'\b(?:\d[ -]*?){13,19}\b'
)

# SSN (XXX-XX-XXXX)
_SSN_RE = re.compile(
    r'\b\d{3}-\d{2}-\d{4}\b'
)

# API keys — 32+ character alphanumeric strings (common formats)
_API_KEY_RE = re.compile(
    r'\b[A-Za-z0-9_\-]{32,}\b'
)

# JWT-like tokens (eyJ...)
_JWT_RE = re.compile(
    r'\beyJ[A-Za-z0-9_\-]+\.eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b'
)

# Bearer tokens
_BEARER_RE = re.compile(
    r'Bearer\s+[A-Za-z0-9_\-\.]+',
    re.IGNORECASE,
)

# OAuth tokens (access_token=..., token=...)
_OAUTH_TOKEN_RE = re.compile(
    r'(?:access_token|refresh_token|token)\s*[=:]\s*["\']?[A-Za-z0-9_\-\.]{20,}["\']?',
    re.IGNORECASE,
)

# Password patterns (password: ..., pwd=..., passwd:...)
_PASSWORD_RE = re.compile(
    r'(?:password|passwd|pwd)\s*[=:]\s*\S+',
    re.IGNORECASE,
)

# Email signature separator (-- followed by newline)
_SIGNATURE_RE = re.compile(
    r'\n--\s*\n.*',
    re.DOTALL,
)

# Common signature indicators
_SIGNATURE_BLOCK_RE = re.compile(
    r'\n(?:Sent from my (?:iPhone|iPad|Android|Samsung)|'
    r'Get Outlook for (?:iOS|Android)|'
    r'Disclaimer:|Confidentiality Notice:).*',
    re.DOTALL | re.IGNORECASE,
)


# Replacement placeholder
_REDACTED = "[REDACTED]"


def sanitize_email_body(body: str) -> str:
    """
    Sanitize an email body for AI processing.

    Strips sensitive data while preserving business-relevant content
    (names, titles, companies, discussion topics).

    Args:
        body: Raw email body text.

    Returns:
        Sanitized, truncated email body safe for AI processing.
    """
    if not body:
        return ""

    text = body

    # Strip email signatures first (reduces noise + cost)
    text = _SIGNATURE_RE.sub("", text)
    text = _SIGNATURE_BLOCK_RE.sub("", text)

    # Strip sensitive patterns (order matters — JWT before API key)
    text = _JWT_RE.sub(_REDACTED, text)
    text = _BEARER_RE.sub(f"Bearer {_REDACTED}", text)
    text = _OAUTH_TOKEN_RE.sub(_REDACTED, text)
    text = _CREDIT_CARD_RE.sub(_REDACTED, text)
    text = _SSN_RE.sub(_REDACTED, text)
    text = _PASSWORD_RE.sub(_REDACTED, text)
    text = _API_KEY_RE.sub(_REDACTED, text)

    # Collapse excessive whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {3,}', ' ', text)
    text = text.strip()

    # Truncate to control cost
    if len(text) > MAX_BODY_LENGTH:
        text = text[:MAX_BODY_LENGTH] + "..."

    return text
