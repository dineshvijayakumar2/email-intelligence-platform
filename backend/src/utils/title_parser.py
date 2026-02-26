"""
Title Parser Utility
===================
Parse job titles into seniority_level and functional_role for contact classification.

Seniority Levels:
    - c_level: CEO, CFO, CTO, etc.
    - vp: Vice President, SVP, EVP
    - director: Director, Head of, Managing Director
    - manager: Manager, Supervisor, Team Lead
    - senior: Senior, Staff, Principal, Lead
    - mid: Analyst, Specialist, Engineer, Developer
    - junior: Junior, Assistant, Entry Level
    - intern: Intern, Co-op, Fellow, Trainee
    - unknown: Could not determine

Functional Roles:
    - executive: CEO, COO, President, Founder
    - sales: Sales, Business Development, Account Manager
    - marketing: Marketing, Brand, Content, PR
    - operations: Operations, Logistics, Supply Chain
    - finance: Finance, Accounting, Controller
    - engineering: Engineering, Software, IT, Data
    - support: Support, Customer Service, Customer Success
    - procurement: Procurement, Purchasing, Sourcing
    - legal: Legal, Counsel, Compliance
    - hr: HR, Human Resources, People, Talent
    - other: Other functions
    - unknown: Could not determine

Usage:
    from utils.title_parser import parse_title

    result = parse_title("Vice President of Sales")
    # TitleInfo(seniority='vp', role='sales', is_decision_maker=True, confidence=0.7)
"""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class TitleInfo:
    """
    Result of job title parsing.

    Attributes:
        seniority_level: One of: c_level, vp, director, manager, senior, mid, junior, intern, unknown
        functional_role: One of: executive, sales, marketing, operations, finance, engineering,
                        support, procurement, legal, hr, other, unknown
        is_decision_maker: True if seniority is c_level, vp, or director
        confidence: Confidence score 0.0-1.0 based on source and match quality
    """
    seniority_level: str  # c_level, vp, director, manager, senior, mid, junior, intern, unknown
    functional_role: str  # executive, sales, marketing, operations, finance, engineering, support, procurement, legal, hr, other, unknown
    is_decision_maker: bool
    confidence: float  # 0.0-1.0


# Seniority patterns (ordered by priority - check c_level first)
SENIORITY_PATTERNS = [
    ('c_level', [
        r'\bceo\b', r'\bcfo\b', r'\bcto\b', r'\bcoo\b', r'\bcmo\b', r'\bcio\b',
        r'\bcso\b', r'\bcdo\b', r'\bcpo\b', r'\bcco\b', r'\bcro\b', r'\bcao\b',
        r'\bchief\b', r'\bpresident\b', r'\bowner\b', r'\bfounder\b', r'\bco-founder\b',
        r'\bpartner\b', r'\bprincipal\b(?!.*engineer)', r'\bmanaging\s+partner\b',
    ]),
    ('vp', [
        r'\bvp\b', r'\bvice.?president\b', r'\bsvp\b', r'\bevp\b', r'\bavp\b',
        r'\bv\.p\b', r'\bvice-president\b',
    ]),
    ('director', [
        r'\bdirector\b', r'\bhead\s+of\b', r'\bmanaging\s+director\b',
        r'\bgm\b', r'\bgeneral\s+manager\b', r'\bexecutive\s+director\b',
    ]),
    ('manager', [
        r'\bmanager\b', r'\bsupervisor\b', r'\bteam\s+lead\b', r'\bcoordinator\b',
        r'\blead\b(?!.*developer|.*engineer|.*developer)', r'\bsuperintendent\b',
    ]),
    ('senior', [
        r'\bsenior\b', r'\bsr\.?\b', r'\blead\b', r'\bprincipal\b', r'\bstaff\b',
        r'\bsenior-level\b',
    ]),
    ('mid', [
        r'\banalyst\b', r'\bspecialist\b', r'\bassociate\b', r'\bengineer\b',
        r'\bdeveloper\b', r'\bdesigner\b', r'\bconsultant\b', r'\badvisor\b',
        r'\bcontroller\b', r'\barchitect\b', r'\bstrategist\b',
    ]),
    ('junior', [
        r'\bjunior\b', r'\bjr\.?\b', r'\bassistant\b', r'\bentry\b',
        r'\bentry-level\b', r'\bassociate\s+(?!director|manager)',
    ]),
    ('intern', [
        r'\bintern\b', r'\bco-?op\b', r'\bfellow\b', r'\btrainee\b',
        r'\bapprentice\b', r'\bgraduate\s+trainee\b',
    ]),
]

# Functional role patterns
ROLE_PATTERNS = [
    ('executive', [
        r'\bceo\b', r'\bcoo\b', r'\bchief\b', r'\bpresident\b', r'\bowner\b',
        r'\bfounder\b', r'\bexecutive\b', r'\bmanaging\s+partner\b',
    ]),
    ('sales', [
        r'\bsales\b', r'\bbd\b', r'\bbusiness\s+dev', r'\baccount\b',
        r'\brevenue\b', r'\bcommercial\b', r'\b(?:account|sales)\s+executive\b',
    ]),
    ('marketing', [
        r'\bmarketing\b', r'\bbrand\b', r'\bcontent\b', r'\bpr\b',
        r'\bcommunications\b', r'\bgrowth\b', r'\bcmo\b', r'\bdigital\s+marketing\b',
        r'\bsocial\s+media\b', r'\bseo\b', r'\bdem\s+(digital|email|marketing)\b',
    ]),
    ('operations', [
        r'\boperations\b', r'\bops\b', r'\blogistics\b', r'\bsupply\s+chain\b',
        r'\bproject\b', r'\bprogram\s+manager\b', r'\bcoo\b', r'\bfacilities\b',
    ]),
    ('finance', [
        r'\bfinance\b', r'\bcfo\b', r'\baccounting\b', r'\bcontroller\b',
        r'\btreasur', r'\bfp&a\b', r'\bbookkeeper\b', r'\baudit',
    ]),
    ('engineering', [
        r'\bengineering\b', r'\bcto\b', r'\btechnolog', r'\bsoftware\b',
        r'\bit\b', r'\bdata\b', r'\bdev', r'\bqa\b', r'\bdevops\b',
        r'\bsre\b', r'\binfrastructure\b', r'\barchitect\b(?!.*business)',
    ]),
    ('support', [
        r'\bsupport\b', r'\bcustomer\s+service\b', r'\bcustomer\s+success\b',
        r'\bhelpdesk\b', r'\btechnical\s+support\b', r'\bclient\s+services\b',
    ]),
    ('procurement', [
        r'\bprocurement\b', r'\bpurchasing\b', r'\bbuying\b', r'\bsourcing\b',
        r'\bvendor\b', r'\bsupply\b', r'\bbuyer\b',
    ]),
    ('legal', [
        r'\blegal\b', r'\bcounsel\b', r'\bcompliance\b', r'\battorney\b',
        r'\blawyer\b', r'\bgeneral\s+counsel\b', r'\bparalegal\b',
    ]),
    ('hr', [
        r'\bhr\b', r'\bhuman\s+resource', r'\bpeople\b', r'\btalent\b',
        r'\brecruiting\b', r'\brecruiter\b', r'\bchro\b',
    ]),
]

# Decision maker seniorities
DECISION_MAKER_SENIORITIES = {'c_level', 'vp', 'director'}


def parse_title(title: Optional[str], source: str = 'email_signature') -> TitleInfo:
    """
    Parse a job title into seniority, functional role, and decision-maker flag.

    Args:
        title: Job title string (e.g., "Vice President of Sales")
        source: Source of title (manual, email_signature, ai_enriched, inferred, csv_import, unknown)
                Used to set confidence score.

    Returns:
        TitleInfo object with seniority, role, is_decision_maker, and confidence

    Examples:
        >>> result = parse_title("Chief Executive Officer")
        >>> (result.seniority_level, result.functional_role, result.is_decision_maker)
        ('c_level', 'executive', True)

        >>> result = parse_title("Senior Software Engineer")
        >>> (result.seniority_level, result.functional_role, result.is_decision_maker)
        ('senior', 'engineering', False)

        >>> result = parse_title("VP of Sales")
        >>> (result.seniority_level, result.functional_role, result.is_decision_maker)
        ('vp', 'sales', True)

        >>> result = parse_title("Marketing Manager")
        >>> (result.seniority_level, result.functional_role)
        ('manager', 'marketing')

        >>> result = parse_title("")
        >>> result.seniority_level
        'unknown'
    """
    if not title or not title.strip():
        return TitleInfo(
            seniority_level='unknown',
            functional_role='unknown',
            is_decision_maker=False,
            confidence=0.0
        )

    # Normalize title for pattern matching
    normalized = title.lower().strip()

    # Extract seniority and role
    seniority = _match_patterns(normalized, SENIORITY_PATTERNS) or 'unknown'
    role = _match_patterns(normalized, ROLE_PATTERNS) or 'unknown'

    # Determine if decision maker
    is_decision_maker = seniority in DECISION_MAKER_SENIORITIES

    # Calculate confidence based on source
    confidence = _calculate_confidence(source, seniority, role)

    return TitleInfo(
        seniority_level=seniority,
        functional_role=role,
        is_decision_maker=is_decision_maker,
        confidence=round(confidence, 2)
    )


def _match_patterns(text: str, pattern_groups: list) -> Optional[str]:
    """
    Match text against ordered pattern groups, return first match.

    Patterns are checked in order, so c_level is checked before vp, etc.
    """
    for label, patterns in pattern_groups:
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return label
    return None


def _calculate_confidence(source: str, seniority: str, role: str) -> float:
    """
    Calculate confidence score based on source and match quality.

    Source confidence:
        - manual: 1.0 (human verified)
        - csv_import: 0.9 (from structured data)
        - ai_enriched: 0.85 (AI verified)
        - email_signature: 0.7 (parsed from signature)
        - inferred: 0.3 (guessed from context)
        - unknown: 0.0 (no source)

    Adjustments:
        - Reduce by 0.3 if both seniority and role are unknown
        - Reduce by 0.1 if one is unknown
    """
    # Base confidence from source
    confidence_map = {
        'manual': 1.0,
        'csv_import': 0.9,
        'ai_enriched': 0.85,
        'email_signature': 0.7,
        'inferred': 0.3,
        'unknown': 0.0,
    }

    confidence = confidence_map.get(source, 0.5)

    # Adjust for match quality
    if seniority == 'unknown' and role == 'unknown':
        confidence = max(confidence - 0.3, 0.0)
    elif seniority == 'unknown' or role == 'unknown':
        confidence = max(confidence - 0.1, 0.0)

    return confidence


def batch_parse_titles(titles: list[tuple[str, str]]) -> list[TitleInfo]:
    """
    Parse multiple titles at once for efficiency.

    Args:
        titles: List of (title, source) tuples

    Returns:
        List of TitleInfo results

    Example:
        >>> titles = [("CEO", "manual"), ("Senior Engineer", "email_signature")]
        >>> results = batch_parse_titles(titles)
        >>> len(results)
        2
    """
    return [parse_title(title, source) for title, source in titles]


def is_technical_role(title: str) -> bool:
    """
    Determine if a title is a technical/engineering role.

    Args:
        title: Job title

    Returns:
        True if technical role, False otherwise

    Examples:
        >>> is_technical_role("Senior Software Engineer")
        True
        >>> is_technical_role("VP of Sales")
        False
    """
    result = parse_title(title)
    return result.functional_role == 'engineering'


def is_customer_facing_role(title: str) -> bool:
    """
    Determine if a title is customer-facing (sales, support, customer success).

    Args:
        title: Job title

    Returns:
        True if customer-facing, False otherwise

    Examples:
        >>> is_customer_facing_role("Account Manager")
        True
        >>> is_customer_facing_role("Software Engineer")
        False
    """
    result = parse_title(title)
    return result.functional_role in ('sales', 'support')


# Test cases for validation (100+ titles covering all categories)
TEST_TITLES = [
    # C-Level (20 titles)
    "Chief Executive Officer", "CEO", "Chief Financial Officer", "CFO",
    "Chief Technology Officer", "CTO", "Chief Operating Officer", "COO",
    "Chief Marketing Officer", "CMO", "Chief Information Officer", "CIO",
    "Chief Security Officer", "CSO", "Chief Data Officer", "CDO",
    "Chief Product Officer", "CPO", "President", "Owner", "Founder",
    "Co-Founder", "Partner", "Managing Partner",

    # VP (10 titles)
    "Vice President", "VP", "VP of Sales", "SVP", "Senior Vice President",
    "EVP", "Executive Vice President", "AVP", "Assistant Vice President",
    "Vice President of Engineering",

    # Director (12 titles)
    "Director", "Director of Marketing", "Head of Sales", "Managing Director",
    "Executive Director", "Director of Operations", "GM", "General Manager",
    "Director of Engineering", "Head of Product", "Head of Data",
    "Director of Customer Success",

    # Manager (15 titles)
    "Manager", "Marketing Manager", "Sales Manager", "Project Manager",
    "Program Manager", "Product Manager", "Engineering Manager",
    "Team Lead", "Supervisor", "Department Manager", "Operations Manager",
    "Account Manager", "Customer Success Manager", "Finance Manager",
    "HR Manager",

    # Senior (12 titles)
    "Senior Software Engineer", "Senior Analyst", "Senior Developer",
    "Senior Designer", "Staff Engineer", "Principal Engineer",
    "Lead Developer", "Senior Consultant", "Senior Specialist",
    "Senior Accountant", "Senior Recruiter", "Sr. Engineer",

    # Mid-Level (15 titles)
    "Software Engineer", "Data Analyst", "Business Analyst",
    "Financial Analyst", "Marketing Specialist", "Sales Representative",
    "Account Executive", "Consultant", "Designer", "Developer",
    "Architect", "Specialist", "Coordinator", "Administrator",
    "Associate Consultant",

    # Junior (10 titles)
    "Junior Developer", "Junior Analyst", "Assistant Manager",
    "Junior Designer", "Entry Level Engineer", "Associate",
    "Jr. Developer", "Assistant", "Entry Level Analyst",
    "Junior Software Engineer",

    # Intern (6 titles)
    "Intern", "Summer Intern", "Co-op", "Fellow", "Graduate Trainee",
    "Apprentice",

    # Mixed Examples (covering different functional areas)
    "VP of Business Development",  # vp + sales
    "Chief People Officer",  # c_level + hr
    "Director of Finance",  # director + finance
    "Senior Legal Counsel",  # senior + legal
    "Procurement Manager",  # manager + procurement
    "IT Support Specialist",  # mid + engineering
    "Customer Service Representative",  # mid + support
    "Marketing Coordinator",  # mid + marketing
    "Operations Analyst",  # mid + operations
    "Supply Chain Manager",  # manager + operations
]


if __name__ == "__main__":
    # Quick tests
    import doctest
    doctest.testmod()

    # Comprehensive test suite
    print("Title Parser Utility - Test Suite")
    print("=" * 70)
    print(f"Testing {len(TEST_TITLES)} job titles...\n")

    # Test all titles
    results_by_seniority = {}
    results_by_role = {}

    for title in TEST_TITLES:
        result = parse_title(title)

        # Group by seniority
        if result.seniority_level not in results_by_seniority:
            results_by_seniority[result.seniority_level] = []
        results_by_seniority[result.seniority_level].append(title)

        # Group by role
        if result.functional_role not in results_by_role:
            results_by_role[result.functional_role] = []
        results_by_role[result.functional_role].append(title)

    # Print results by seniority
    print("Results by Seniority Level:")
    print("-" * 70)
    for seniority, titles in sorted(results_by_seniority.items()):
        print(f"\n{seniority.upper()}: {len(titles)} titles")
        for t in titles[:3]:  # Show first 3 examples
            print(f"  - {t}")

    # Print results by role
    print("\n\nResults by Functional Role:")
    print("-" * 70)
    for role, titles in sorted(results_by_role.items()):
        print(f"\n{role.upper()}: {len(titles)} titles")
        for t in titles[:3]:  # Show first 3 examples
            print(f"  - {t}")

    # Show some detailed examples
    print("\n\nDetailed Examples:")
    print("-" * 70)
    example_titles = [
        "Chief Executive Officer",
        "VP of Sales",
        "Senior Software Engineer",
        "Marketing Manager",
        "Junior Developer",
    ]

    for title in example_titles:
        result = parse_title(title)
        print(f"\nTitle: {title}")
        print(f"  Seniority: {result.seniority_level}")
        print(f"  Role: {result.functional_role}")
        print(f"  Decision Maker: {result.is_decision_maker}")
        print(f"  Confidence: {result.confidence}")
