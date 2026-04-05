"""
Temporal Query Parser — Phase 2 Hybrid Retrieval Layer

Extracts natural language date references from search queries and converts
them to structured date_from/date_to filters. The cleaned query (with time
references stripped) is returned for the retriever.

Examples:
    "what happened with Acme last quarter" → ("what happened with Acme", Q1 start, Q1 end)
    "emails since January"                 → ("emails", Jan 1, today)
    "before the March renewal"             → ("before the renewal", None, Mar 31)
    "recent activity with Smith Co"        → ("activity with Smith Co", 30 days ago, today)
"""

import re
import logging
from datetime import date, timedelta
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ParsedQuery:
    """Result of temporal parsing."""
    cleaned_query: str          # Query with time expressions stripped
    date_from: Optional[str]    # ISO date string or None
    date_to: Optional[str]      # ISO date string or None
    has_temporal: bool           # Whether any time expression was found


# Month name → number
_MONTHS = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'may': 5, 'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12,
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
    'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9, 'sept': 9,
    'oct': 10, 'nov': 11, 'dec': 12,
}

# Compiled patterns — order matters (longer patterns first)
_PATTERNS: list[tuple[re.Pattern, str]] = []


def _build_patterns():
    """Build regex patterns on first use."""
    if _PATTERNS:
        return

    month_names = '|'.join(_MONTHS.keys())

    patterns = [
        # "last N days/weeks/months/years"
        (r'\b(?:in\s+the\s+)?last\s+(\d+)\s+(day|week|month|year)s?\b', 'last_n'),
        # "past N days/weeks/months"
        (r'\b(?:in\s+the\s+)?past\s+(\d+)\s+(day|week|month|year)s?\b', 'last_n'),
        # "last quarter" / "this quarter" / "previous quarter"
        (r'\b(last|previous|this|current)\s+quarter\b', 'quarter'),
        # "last month" / "this month" / "previous month"
        (r'\b(last|previous|this|current)\s+month\b', 'rel_month'),
        # "last week" / "this week"
        (r'\b(last|previous|this|current)\s+week\b', 'rel_week'),
        # "last year" / "this year" / "previous year"
        (r'\b(last|previous|this|current)\s+year\b', 'rel_year'),
        # "since January" / "since March 2025"
        (rf'\bsince\s+({month_names})(?:\s+(\d{{4}}))?\b', 'since_month'),
        # "before January" / "before March 2025"
        (rf'\bbefore\s+({month_names})(?:\s+(\d{{4}}))?\b', 'before_month'),
        # "in January" / "in March 2025"
        (rf'\bin\s+({month_names})(?:\s+(\d{{4}}))?\b', 'in_month'),
        # "Q1 2025" / "Q2" / "q3 2024"
        (r'\bq([1-4])(?:\s+(\d{4}))?\b', 'named_quarter'),
        # "yesterday"
        (r'\byesterday\b', 'yesterday'),
        # "today"
        (r'\btoday\b', 'today'),
        # "recently" / "recent"
        (r'\brecent(?:ly)?\b', 'recent'),
    ]

    for pattern_str, tag in patterns:
        _PATTERNS.append((re.compile(pattern_str, re.IGNORECASE), tag))


def _quarter_range(year: int, q: int) -> tuple[date, date]:
    """Return (start, end) for a given quarter."""
    starts = {1: (1, 1), 2: (4, 1), 3: (7, 1), 4: (10, 1)}
    ends = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
    return date(year, *starts[q]), date(year, *ends[q])


def _month_range(year: int, month: int) -> tuple[date, date]:
    """Return (start, end) for a given month."""
    start = date(year, month, 1)
    if month == 12:
        end = date(year, 12, 31)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return start, end


def _current_quarter(d: date) -> int:
    """Return quarter number (1-4) for a date."""
    return (d.month - 1) // 3 + 1


def parse_temporal_query(query: str, reference_date: Optional[date] = None) -> ParsedQuery:
    """
    Parse temporal expressions from a query string.

    Args:
        query: The user's search query
        reference_date: Date to resolve relative expressions against (default: today)

    Returns:
        ParsedQuery with cleaned query and optional date range
    """
    _build_patterns()
    today = reference_date or date.today()
    cleaned = query
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    found = False

    for pattern, tag in _PATTERNS:
        match = pattern.search(cleaned)
        if not match:
            continue

        found = True

        if tag == 'last_n':
            n = int(match.group(1))
            unit = match.group(2).lower()
            if unit == 'day':
                date_from = today - timedelta(days=n)
            elif unit == 'week':
                date_from = today - timedelta(weeks=n)
            elif unit == 'month':
                date_from = today.replace(day=1) - timedelta(days=30 * n - 1)
            elif unit == 'year':
                date_from = today.replace(year=today.year - n)
            date_to = today

        elif tag == 'quarter':
            qualifier = match.group(1).lower()
            cq = _current_quarter(today)
            cy = today.year
            if qualifier in ('last', 'previous'):
                cq -= 1
                if cq < 1:
                    cq = 4
                    cy -= 1
            date_from, date_to = _quarter_range(cy, cq)

        elif tag == 'rel_month':
            qualifier = match.group(1).lower()
            m, y = today.month, today.year
            if qualifier in ('last', 'previous'):
                m -= 1
                if m < 1:
                    m = 12
                    y -= 1
            date_from, date_to = _month_range(y, m)

        elif tag == 'rel_week':
            qualifier = match.group(1).lower()
            weekday = today.weekday()  # Monday=0
            week_start = today - timedelta(days=weekday)
            if qualifier in ('last', 'previous'):
                week_start -= timedelta(weeks=1)
            date_from = week_start
            date_to = week_start + timedelta(days=6)

        elif tag == 'rel_year':
            qualifier = match.group(1).lower()
            y = today.year
            if qualifier in ('last', 'previous'):
                y -= 1
            date_from = date(y, 1, 1)
            date_to = date(y, 12, 31) if y < today.year else today

        elif tag == 'since_month':
            month_name = match.group(1).lower()
            year_str = match.group(2)
            m = _MONTHS[month_name]
            y = int(year_str) if year_str else (today.year if m <= today.month else today.year - 1)
            date_from = date(y, m, 1)
            date_to = today

        elif tag == 'before_month':
            month_name = match.group(1).lower()
            year_str = match.group(2)
            m = _MONTHS[month_name]
            y = int(year_str) if year_str else today.year
            date_to = date(y, m, 1) - timedelta(days=1)

        elif tag == 'in_month':
            month_name = match.group(1).lower()
            year_str = match.group(2)
            m = _MONTHS[month_name]
            y = int(year_str) if year_str else (today.year if m <= today.month else today.year - 1)
            date_from, date_to = _month_range(y, m)

        elif tag == 'named_quarter':
            q = int(match.group(1))
            year_str = match.group(2)
            y = int(year_str) if year_str else today.year
            date_from, date_to = _quarter_range(y, q)

        elif tag == 'yesterday':
            date_from = today - timedelta(days=1)
            date_to = today - timedelta(days=1)

        elif tag == 'today':
            date_from = today
            date_to = today

        elif tag == 'recent':
            date_from = today - timedelta(days=30)
            date_to = today

        # Strip the matched expression from the query
        cleaned = cleaned[:match.start()] + cleaned[match.end():]
        break  # Only extract the first temporal expression

    # Clean up whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    # Remove dangling prepositions left after stripping
    cleaned = re.sub(r'\b(from|in|during|for|of)\s*$', '', cleaned).strip()
    cleaned = re.sub(r'^\s*(from|in|during|for|of)\s+', '', cleaned).strip()

    return ParsedQuery(
        cleaned_query=cleaned or query,
        date_from=date_from.isoformat() if date_from else None,
        date_to=date_to.isoformat() if date_to else None,
        has_temporal=found,
    )
