"""
Search utilities shared across routers.
"""


def sanitize_search_term(term: str) -> str:
    """Escape SQL ILIKE wildcards in user-supplied search terms to prevent wildcard abuse."""
    return term.replace('%', r'\%').replace('_', r'\_')
