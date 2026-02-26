"""
Domain Parser Utility
=====================
Extract and classify email domains for customer data extraction.

Functions:
    - extract_domain(email): Extract domain from email address
    - get_root_domain(domain): Extract root domain from subdomain
    - normalize_domain(domain): Normalize domain (lowercase, strip)
    - domain_to_company_name(domain): Convert domain to readable company name
    - is_noreply_address(email): Detect system/no-reply email addresses

Usage:
    from utils.domain_parser import extract_domain, domain_to_company_name

    domain = extract_domain("john@acme.com")  # "acme.com"
    company = domain_to_company_name("acme.com")  # "Acme"
    root = get_root_domain("mail.acme.com")  # "acme.com"
"""

import re
from typing import Optional


def extract_domain(email: str) -> Optional[str]:
    """
    Extract domain from email address, lowercased.

    Args:
        email: Email address (e.g., "john@acme.com")

    Returns:
        Domain portion lowercased (e.g., "acme.com"), or None if invalid

    Examples:
        >>> extract_domain("john@acme.com")
        'acme.com'
        >>> extract_domain("JOHN@ACME.COM")
        'acme.com'
        >>> extract_domain("invalid")
        None
    """
    if not email or '@' not in email:
        return None

    try:
        return email.strip().lower().split('@')[1]
    except IndexError:
        return None


def get_root_domain(domain: str) -> str:
    """
    Extract root domain from subdomain.

    Args:
        domain: Domain (e.g., "mail.google.com" or "google.com")

    Returns:
        Root domain (e.g., "google.com")

    Examples:
        >>> get_root_domain("mail.google.com")
        'google.com'
        >>> get_root_domain("google.com")
        'google.com'
        >>> get_root_domain("subdomain.example.co.uk")
        'example.co.uk'
    """
    if not domain:
        return domain

    domain = domain.lower().strip()

    # Handle special TLDs like .co.uk, .com.au, etc.
    special_tlds = [
        '.co.uk', '.com.au', '.co.in', '.co.jp', '.co.za',
        '.com.br', '.com.cn', '.com.mx', '.gov.uk', '.ac.uk'
    ]

    for tld in special_tlds:
        if domain.endswith(tld):
            parts = domain[:-len(tld)].split('.')
            if len(parts) >= 1:
                return parts[-1] + tld
            return domain

    # Standard case: take last two parts (e.g., example.com)
    parts = domain.split('.')
    if len(parts) >= 2:
        return '.'.join(parts[-2:])

    return domain


def normalize_domain(domain: str) -> str:
    """
    Normalize domain: lowercase, strip whitespace.

    Args:
        domain: Domain name (e.g., "  ACME.COM  ")

    Returns:
        Normalized domain (e.g., "acme.com")

    Examples:
        >>> normalize_domain("  ACME.COM  ")
        'acme.com'
        >>> normalize_domain("AcMe.CoM")
        'acme.com'
    """
    return domain.strip().lower()


def domain_to_company_name(domain: str) -> str:
    """
    Convert domain to a readable company name.

    Rules:
        - Remove TLD(s): acme.com → Acme
        - Remove TLD(s): acme.co.uk → Acme
        - Replace hyphens/underscores with spaces: my-company.io → My Company
        - Title case: acme → Acme

    Args:
        domain: Domain name (e.g., "acme.com", "my-company.io")

    Returns:
        Readable company name (e.g., "Acme", "My Company")

    Examples:
        >>> domain_to_company_name("acme.com")
        'Acme'
        >>> domain_to_company_name("acme.co.uk")
        'Acme'
        >>> domain_to_company_name("my-company.io")
        'My Company'
        >>> domain_to_company_name("the_cool_startup.com")
        'The Cool Startup'
    """
    # Remove TLD(s) - take first part before first dot
    name = domain.split('.')[0]

    # Replace hyphens and underscores with spaces
    name = re.sub(r'[-_]', ' ', name)

    # Title case
    return name.title()


def is_noreply_address(email: str) -> bool:
    """
    Detect system/no-reply email addresses that should be excluded from contact extraction.

    Detects patterns like:
        - noreply@domain.com
        - no-reply@domain.com
        - donotreply@domain.com
        - mailer-daemon@domain.com
        - notifications@domain.com
        - system@domain.com
        - automated@domain.com
        - bounce@domain.com
        - feedback@domain.com
        - newsletter@domain.com
        - updates@domain.com
        - info@domain.com (sometimes)
        - alerts@domain.com

    Args:
        email: Email address to check

    Returns:
        True if email is a no-reply/system address, False otherwise

    Examples:
        >>> is_noreply_address("noreply@acme.com")
        True
        >>> is_noreply_address("john.doe@acme.com")
        False
        >>> is_noreply_address("notifications@github.com")
        True
        >>> is_noreply_address("automated-alerts@system.io")
        True
    """
    if not email:
        return False

    # Extract local part (before @)
    try:
        local = email.lower().split('@')[0]
    except IndexError:
        return False

    # No-reply patterns (comprehensive list)
    noreply_patterns = [
        # No reply variations
        'noreply', 'no-reply', 'no_reply', 'donotreply', 'do-not-reply', 'do_not_reply',

        # System addresses
        'mailer-daemon', 'postmaster', 'daemon',

        # Notification/alert addresses
        'notifications', 'notification', 'alert', 'alerts', 'notify',

        # System/automated
        'system', 'automated', 'auto-', 'automatic',

        # Bounce/feedback
        'bounce', 'bounces', 'unsubscribe', 'feedback-', 'return-path',

        # Marketing/newsletter
        'news@', 'newsletter', 'newsletters', 'updates@', 'marketing@',

        # Generic contact addresses (often distribution lists, not individuals)
        'info@', 'support@', 'hello@', 'contact@', 'sales@', 'help@',
        'admin@', 'webmaster@', 'hostmaster@',

        # Event/calendar
        'calendar-', 'cal-', 'event-',
    ]

    # Check if any pattern is in the local part
    return any(pattern in local for pattern in noreply_patterns)


def is_distribution_list(email: str) -> bool:
    """
    Detect distribution list or shared inbox addresses.

    These are typically generic addresses managed by multiple people,
    not individual contacts.

    Patterns:
        - team@domain.com
        - dept@domain.com
        - group@domain.com
        - all@domain.com
        - everyone@domain.com

    Args:
        email: Email address to check

    Returns:
        True if email appears to be a distribution list

    Examples:
        >>> is_distribution_list("team@acme.com")
        True
        >>> is_distribution_list("john.doe@acme.com")
        False
        >>> is_distribution_list("everyone@company.io")
        True
    """
    if not email:
        return False

    try:
        local = email.lower().split('@')[0]
    except IndexError:
        return False

    # Distribution list patterns
    dist_patterns = [
        'team', 'dept', 'department', 'group', 'all', 'everyone',
        'staff', 'crew', 'members', 'list-', '-list',
    ]

    return any(pattern in local for pattern in dist_patterns)


def classify_email_type(email: str) -> str:
    """
    Classify email address type for extraction filtering.

    Types:
        - "noreply": System/automated address (exclude from extraction)
        - "distribution": Distribution list/shared inbox (flag for review)
        - "personal": Individual contact (include in extraction)

    Args:
        email: Email address to classify

    Returns:
        Classification: "noreply", "distribution", or "personal"

    Examples:
        >>> classify_email_type("noreply@acme.com")
        'noreply'
        >>> classify_email_type("team@acme.com")
        'distribution'
        >>> classify_email_type("john.doe@acme.com")
        'personal'
    """
    if is_noreply_address(email):
        return "noreply"
    elif is_distribution_list(email):
        return "distribution"
    else:
        return "personal"


# Utility for extracting root domain (handles subdomains)
def extract_root_domain(domain: str) -> str:
    """
    Extract root domain from a domain that might have subdomains.

    Examples:
        - mail.acme.com → acme.com
        - www.acme.com → acme.com
        - acme.com → acme.com
        - support.mail.acme.com → acme.com

    Note: This is a simple implementation. For production use, consider
    using the `tldextract` library for more robust TLD handling.

    Args:
        domain: Domain with possible subdomains

    Returns:
        Root domain (domain + TLD only)

    Examples:
        >>> extract_root_domain("mail.acme.com")
        'acme.com'
        >>> extract_root_domain("www.github.com")
        'github.com'
        >>> extract_root_domain("acme.com")
        'acme.com'
    """
    parts = domain.split('.')

    # Handle common TLDs
    if len(parts) >= 2:
        # Check for two-part TLDs like .co.uk, .com.au
        if len(parts) >= 3 and parts[-2] in ['co', 'com', 'ac', 'gov', 'net', 'org']:
            # Examples: acme.co.uk → acme.co.uk, mail.acme.co.uk → acme.co.uk
            return '.'.join(parts[-3:]) if len(parts) > 3 else '.'.join(parts)
        else:
            # Standard TLD: mail.acme.com → acme.com
            return '.'.join(parts[-2:])

    # Already a root domain
    return domain


if __name__ == "__main__":
    # Quick tests
    import doctest
    doctest.testmod()

    # Manual tests
    print("Domain Parser Utility Tests")
    print("=" * 50)

    test_emails = [
        "john.doe@acme.com",
        "noreply@github.com",
        "team@startup.io",
        "Jane.Smith@My-Company.co.uk",
        "notifications@system.io",
    ]

    for email in test_emails:
        domain = extract_domain(email)
        company = domain_to_company_name(domain) if domain else None
        email_type = classify_email_type(email)

        print(f"\nEmail: {email}")
        print(f"  Domain: {domain}")
        print(f"  Company: {company}")
        print(f"  Type: {email_type}")
        print(f"  Is No-Reply: {is_noreply_address(email)}")
        print(f"  Is Distribution: {is_distribution_list(email)}")
