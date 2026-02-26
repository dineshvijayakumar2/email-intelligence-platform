"""
Name Parser Utility
==================
Parse display names into first_name, last_name for contact extraction.

Handles various name formats:
    - "John Doe" → John, Doe
    - "Doe, John" → John, Doe
    - "john.doe@company.com" → John, Doe (inferred from email)
    - "Dr. John A. Doe III" → John, Doe (strips prefixes/suffixes)
    - "John" → John, "" (single name)

Usage:
    from utils.name_parser import parse_display_name

    result = parse_display_name("John Doe")
    print(result.first_name)  # "John"
    print(result.last_name)   # "Doe"
    print(result.full_name)   # "John Doe"
"""

import re
from dataclasses import dataclass
from typing import Optional


# Common name prefixes and suffixes
PREFIXES = {'mr', 'mrs', 'ms', 'miss', 'dr', 'prof', 'professor', 'sir', 'dame', 'rev', 'reverend'}
SUFFIXES = {'jr', 'sr', 'ii', 'iii', 'iv', 'v', 'vi', 'phd', 'md', 'esq', 'cpa', 'dds', 'dvm'}


@dataclass
class ParsedName:
    """
    Result of name parsing.

    Attributes:
        first_name: First name (or given name)
        last_name: Last name (or family name)
        full_name: Complete name formatted as "First Last"
    """
    first_name: str
    last_name: str
    full_name: str


def parse_display_name(display_name: Optional[str], email: Optional[str] = None) -> ParsedName:
    """
    Parse a display name into first/last names. Falls back to email prefix if no display name.

    Args:
        display_name: Display name from email headers (e.g., "John Doe", "Doe, John")
        email: Email address for fallback inference (optional)

    Returns:
        ParsedName object with first_name, last_name, and full_name

    Examples:
        >>> result = parse_display_name("John Doe")
        >>> (result.first_name, result.last_name, result.full_name)
        ('John', 'Doe', 'John Doe')

        >>> result = parse_display_name("Doe, John")
        >>> (result.first_name, result.last_name)
        ('John', 'Doe')

        >>> result = parse_display_name("Dr. John A. Doe III")
        >>> (result.first_name, result.last_name)
        ('John', 'Doe')

        >>> result = parse_display_name(None, "john.doe@company.com")
        >>> (result.first_name, result.last_name)
        ('John', 'Doe')

        >>> result = parse_display_name("John")
        >>> (result.first_name, result.last_name)
        ('John', '')
    """
    # Try to parse display name first
    if display_name:
        name = _clean_display_name(display_name)
        if name:
            return _parse_name_string(name)

    # Fallback: infer from email
    if email and '@' in email:
        return _infer_name_from_email(email)

    # Empty result
    return ParsedName(first_name='', last_name='', full_name='')


def _clean_display_name(display_name: str) -> Optional[str]:
    """
    Clean display name by removing email addresses and extra quotes.

    Examples:
        "John Doe <john@company.com>" → "John Doe"
        '"John Doe"' → "John Doe"
        "  John Doe  " → "John Doe"
    """
    name = display_name.strip()

    # Remove quotes
    name = name.strip('"').strip("'").strip()

    # Remove email in angle brackets: "John Doe <john@x.com>" → "John Doe"
    name = re.sub(r'<[^>]+>', '', name).strip()

    # Remove parenthetical info: "John Doe (CEO)" → "John Doe"
    name = re.sub(r'\([^)]+\)', '', name).strip()

    return name if name else None


def _parse_name_string(name: str) -> ParsedName:
    """
    Parse a cleaned name string into first and last names.

    Handles:
        - "Last, First" format (reversed)
        - "First Last" format (standard)
        - Prefixes (Dr., Mr., Ms., etc.)
        - Suffixes (Jr., Sr., III, PhD, etc.)
        - Initials (A., B.)
    """
    # Handle "Last, First" format
    if ',' in name:
        parts = [p.strip() for p in name.split(',', 1)]
        if len(parts) == 2 and len(parts[0].split()) <= 2 and len(parts[1].split()) <= 2:
            # Looks like "Last, First" format
            last_name = parts[0]
            first_name = parts[1]
            return ParsedName(
                first_name=first_name,
                last_name=last_name,
                full_name=f"{first_name} {last_name}"
            )

    # Split into words
    words = name.split()

    # Remove prefixes (Mr., Dr., etc.)
    words = [w for w in words if w.lower().rstrip('.') not in PREFIXES]

    # Remove suffixes (Jr., Sr., III, etc.)
    words = [w for w in words if w.lower().rstrip('.') not in SUFFIXES]

    # Remove single initials (A., B., etc.)
    words = [w for w in words if not (len(w) <= 2 and w.endswith('.'))]

    # Parse based on remaining words
    if not words:
        # All words were prefixes/suffixes/initials - return original
        return ParsedName(first_name=name, last_name='', full_name=name)
    elif len(words) == 1:
        # Single name (first name only)
        return ParsedName(first_name=words[0], last_name='', full_name=words[0])
    else:
        # Multiple words: first word is first name, last word is last name
        first_name = words[0]
        last_name = words[-1]
        full_name = ' '.join(words)
        return ParsedName(first_name=first_name, last_name=last_name, full_name=full_name)


def _infer_name_from_email(email: str) -> ParsedName:
    """
    Infer name from email address local part.

    Examples:
        john.doe@company.com → John, Doe
        j.smith@company.com → J, Smith
        jdoe123@company.com → Jdoe, ""
    """
    try:
        local = email.split('@')[0]
    except IndexError:
        return ParsedName(first_name='', last_name='', full_name='')

    # Split by common delimiters
    parts = re.split(r'[._\-]', local)

    # Remove numeric-only parts (john.doe123 → [john, doe])
    parts = [p for p in parts if not p.isdigit() and len(p) > 1]

    if len(parts) >= 2:
        # Multiple parts: assume first is first name, last is last name
        first_name = parts[0].title()
        last_name = parts[-1].title()
        full_name = ' '.join(p.title() for p in parts)
        return ParsedName(first_name=first_name, last_name=last_name, full_name=full_name)
    elif parts:
        # Single part: use as first name
        first_name = parts[0].title()
        return ParsedName(first_name=first_name, last_name='', full_name=first_name)
    else:
        # No valid parts
        return ParsedName(first_name='', last_name='', full_name='')


def is_likely_personal_name(name: str) -> bool:
    """
    Determine if a name is likely a personal name vs. a company/system name.

    Rules:
        - Has at least 2 alphabetic characters
        - Doesn't contain common system words
        - Doesn't look like a company name

    Args:
        name: Name to check

    Returns:
        True if likely a personal name, False if likely system/company

    Examples:
        >>> is_likely_personal_name("John Doe")
        True
        >>> is_likely_personal_name("Acme Corp Support Team")
        False
        >>> is_likely_personal_name("Notification Service")
        False
    """
    if not name or len(name) < 2:
        return False

    name_lower = name.lower()

    # System/company keywords
    non_personal_keywords = [
        'team', 'support', 'service', 'notification', 'system', 'admin',
        'info', 'sales', 'help', 'contact', 'noreply', 'corp', 'inc',
        'llc', 'ltd', 'company', 'group', 'department', 'desk',
    ]

    # Check for system keywords
    if any(keyword in name_lower for keyword in non_personal_keywords):
        return False

    # Check if it has at least 2 alpha characters
    alpha_count = sum(c.isalpha() for c in name)
    if alpha_count < 2:
        return False

    return True


def split_full_name(full_name: str) -> tuple[str, str]:
    """
    Quick utility to split a full name into first and last names.

    Args:
        full_name: Complete name string

    Returns:
        Tuple of (first_name, last_name)

    Examples:
        >>> split_full_name("John Doe")
        ('John', 'Doe')
        >>> split_full_name("Jane")
        ('Jane', '')
    """
    result = parse_display_name(full_name)
    return (result.first_name, result.last_name)


if __name__ == "__main__":
    # Quick tests
    import doctest
    doctest.testmod()

    # Manual tests
    print("Name Parser Utility Tests")
    print("=" * 50)

    test_cases = [
        ("John Doe", None),
        ("Doe, John", None),
        ("Dr. John A. Doe III", None),
        ("Jane Smith", None),
        ("John", None),
        (None, "john.doe@company.com"),
        (None, "j.smith@acme.io"),
        ('"John Doe" <john@company.com>', None),
        ("Mr. James T. Kirk", None),
        ("Mary-Jane Watson", None),
    ]

    for display_name, email in test_cases:
        result = parse_display_name(display_name, email)
        print(f"\nInput: display_name='{display_name}', email='{email}'")
        print(f"  First Name: {result.first_name}")
        print(f"  Last Name: {result.last_name}")
        print(f"  Full Name: {result.full_name}")
