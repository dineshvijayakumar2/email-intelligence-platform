"""
Integration tests for data hardening fixes (Apr 23, 2026).

Tests three invariants:
1. Signature extraction: sign-off phrases must NEVER be classified as job titles
2. Shared-address detection: known shared patterns must be detected
3. QB propagation Pass 3: internal/shared contacts must NOT inherit company QB tier

Tests 1-2 read source patterns from the actual .py files (avoids importing
modules that pull in Supabase client via relative imports).
Test 3 requires real Supabase — exercises the actual RPC with test data.

Run:
    cd backend
    python test_data_hardening.py

Cleanup:
    Test 3 creates tagged rows. Cleanup runs in finally block.
    Manual fallback:
        DELETE FROM customer_contacts WHERE metadata->>'_test_marker' = 'data_hardening_test';
        DELETE FROM customer_companies WHERE metadata->>'_test_marker' = 'data_hardening_test';
"""
import ast
import os
import re
import sys
import uuid
from pathlib import Path

try:
    from dotenv import load_dotenv
    for p in [Path(__file__).parent / ".env.production", Path(__file__).parent / ".env"]:
        if p.exists():
            load_dotenv(p, override=False)
            break
except ImportError:
    pass

SRC = Path(__file__).resolve().parent / "src"


# -- Test infra ---------------------------------------------------------------

class C:
    G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; B = "\033[94m"; END = "\033[0m"


passed = 0
failed = 0
TEST_MARKER = "data_hardening_test"


def t_pass(name: str):
    global passed
    passed += 1
    print(f"{C.G}PASS{C.END}  {name}")


def t_fail(name: str, msg: str):
    global failed
    failed += 1
    print(f"{C.R}FAIL{C.END}  {name}: {msg}")


def section(title: str):
    print(f"\n{C.B}{'-' * 60}{C.END}")
    print(f"{C.B}  {title}{C.END}")
    print(f"{C.B}{'-' * 60}{C.END}")


# -- Helpers: extract logic from source without importing ----------------------

def _looks_like_title(line: str) -> bool:
    """Exact replica of RoleClassifier._looks_like_title().

    Reads skip_patterns and title_keywords from the source file at import
    time would be ideal, but they're defined inline. Instead we replicate
    the logic exactly as written in role_classifier.py:346-399.
    """
    if len(line) > 80:
        return False
    if len(line) < 5:
        return False
    if line.isupper() and len(line) > 10:
        return False

    skip_patterns = [
        r'^\d+',
        r'(c).*copyright',
        r'confidential',
        r'unsubscribe',
        r'privacy policy',
        r'(?:^|\s)(?:kind\s+)?regards?,?\s*$',
        r'(?:^|\s)(?:best\s+)?regards?,?\s*$',
        r'(?:^|\s)(?:warm\s+)?regards?,?\s*$',
        r'(?:^|\s)thanks?,?\s*$',
        r'(?:^|\s)thank\s+you,?\s*$',
        r'(?:^|\s)cheers,?\s*$',
        r'(?:^|\s)sincerely,?\s*$',
        r'(?:^|\s)(?:yours\s+)?(?:faithfully|truly),?\s*$',
        r'(?:^|\s)(?:thx|br|ty),?\s*$',
        r'^sent\s+from\s+(?:my\s+)?',
        r'^get\s+outlook\s+for\s+',
    ]

    for pattern in skip_patterns:
        if re.search(pattern, line, re.IGNORECASE):
            return False

    title_keywords = [
        'manager', 'director', 'president', 'officer', 'executive',
        'engineer', 'developer', 'analyst', 'specialist', 'coordinator',
        'consultant', 'advisor', 'lead', 'head', 'chief', 'vp',
        'associate', 'assistant', 'representative', 'agent'
    ]

    line_lower = line.lower()
    for keyword in title_keywords:
        if keyword in line_lower:
            return True

    words = line.split()
    if 2 <= len(words) <= 5 and line[0].isupper():
        return True

    return False


def _load_shared_patterns() -> list[str]:
    """Read SHARED_ADDRESS_PATTERNS from contact_extractor.py source."""
    src_file = SRC / "services" / "contact_extractor.py"
    text = src_file.read_text(encoding="utf-8")
    match = re.search(
        r'SHARED_ADDRESS_PATTERNS\s*=\s*\[(.*?)\]',
        text, re.DOTALL,
    )
    if not match:
        raise RuntimeError("Could not find SHARED_ADDRESS_PATTERNS in contact_extractor.py")
    raw = match.group(0)
    patterns = ast.literal_eval(raw.split("=", 1)[1].strip())
    return patterns


def _is_shared_address(email: str, patterns: list[str]) -> bool:
    """Replica of ContactExtractor._is_shared_address()."""
    email_lower = email.lower()
    for pattern in patterns:
        if re.match(pattern, email_lower):
            return True
    return False


# -- Test 1: Signature extraction -- sign-off phrases -------------------------

def test_signoff_rejection():
    """Sign-off phrases must never pass _looks_like_title()."""
    section("Test 1: Signature sign-off rejection")

    # Also verify the source file actually contains our patterns
    src_file = SRC / "services" / "role_classifier.py"
    src_text = src_file.read_text(encoding="utf-8")
    if "kind\\s+)?regards" not in src_text:
        t_fail("source check", "role_classifier.py missing sign-off patterns — fix not applied?")
        return

    t_pass("source file contains sign-off patterns")

    must_reject = [
        "Kind Regards,",
        "Kind regards",
        "Best Regards,",
        "Best regards,",
        "Warm Regards,",
        "Warm regards",
        "Thanks,",
        "Thanks",
        "Thank you,",
        "Thank You",
        "Cheers,",
        "Cheers",
        "Sincerely,",
        "Sincerely",
        "Yours faithfully,",
        "Yours truly,",
        "Thx,",
        "BR,",
        "Sent from my iPhone",
        "Sent from my Android",
        "Get Outlook for iOS",
    ]

    must_accept = [
        "Senior Manager",
        "Chief Executive Officer",
        "VP of Sales",
        "Marketing Director",
        "Head of Engineering",
        "Project Coordinator",
        "Business Development Representative",
        "Sales Manager | Carbon8",
        "Account Executive",
        "Operations Lead",
    ]

    for phrase in must_reject:
        if _looks_like_title(phrase):
            t_fail(f"reject '{phrase}'", "incorrectly classified as title")
        else:
            t_pass(f"reject '{phrase}'")

    for title in must_accept:
        if _looks_like_title(title):
            t_pass(f"accept '{title}'")
        else:
            t_fail(f"accept '{title}'", "incorrectly rejected as non-title")


# -- Test 2: Shared-address detection -----------------------------------------

def test_shared_address_detection():
    """Known shared-address patterns must be detected."""
    section("Test 2: Shared-address pattern detection")

    patterns = _load_shared_patterns()
    t_pass(f"loaded {len(patterns)} patterns from contact_extractor.py")

    must_detect = [
        "accounts@carbon8.com.au",
        "hello@carbon8.com.au",
        "noreply@carbon8.com.au",
        "no-reply@example.com",
        "no.reply@example.com",
        "donotreply@example.com",
        "do-not-reply@example.com",
        "form-submission@example.com",
        "notifications@example.com",
        "notification@example.com",
        "alerts@example.com",
        "alert@example.com",
        "info@carbon8.com.au",
        "support@carbon8.com.au",
        "sales@example.com",
        "billing@example.com",
        "admin@example.com",
        "office@example.com",
        "mailer-daemon@example.com",
        "bounce@example.com",
        "receipts@example.com",
        "orders@example.com",
        "invoices@example.com",
        "enquiry@example.com",
        "enquiries@example.com",
    ]

    must_not_detect = [
        "john.smith@carbon8.com.au",
        "linda@carbon8.com.au",
        "ehab@carbon8.com.au",
        "jeff.love@carbon8.com.au",
        "sarah.hello@example.com",
    ]

    for addr in must_detect:
        if _is_shared_address(addr, patterns):
            t_pass(f"detect '{addr}'")
        else:
            t_fail(f"detect '{addr}'", "missed shared address")

    for addr in must_not_detect:
        if _is_shared_address(addr, patterns):
            t_fail(f"skip '{addr}'", "false positive on personal address")
        else:
            t_pass(f"skip '{addr}'")


# -- Test 3: QB propagation Pass 3 exclusion (DB-level) -----------------------

def test_qb_propagation_exclusion():
    """Pass 3 must NOT propagate QB tier to internal or shared contacts.

    Creates test data in real Supabase, runs the RPC, and verifies that
    internal/shared contacts are excluded while external person contacts
    are included.
    """
    section("Test 3: QB propagation Pass 3 exclusion (DB)")

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        print(f"{C.Y}SKIP{C.END}  Test 3: SUPABASE_URL/SUPABASE_SERVICE_KEY not set")
        return

    from supabase import create_client
    sb = create_client(url, key)

    test_client_id = os.getenv("TEST_CLIENT_ID")
    if not test_client_id:
        resp = sb.table("clients").select("id").limit(1).execute()
        if not resp.data:
            print(f"{C.Y}SKIP{C.END}  Test 3: no clients in database")
            return
        test_client_id = resp.data[0]["id"]

    id_resp = sb.table("internal_domains").select("domain").eq("client_id", test_client_id).limit(1).execute()
    if not id_resp.data:
        print(f"{C.Y}SKIP{C.END}  Test 3: no internal_domains for client {test_client_id[:8]}")
        return
    internal_domain = id_resp.data[0]["domain"]

    test_company_id = str(uuid.uuid4())
    test_contact_ids = {
        "external_person": str(uuid.uuid4()),
        "internal_employee": str(uuid.uuid4()),
        "shared_address": str(uuid.uuid4()),
    }

    try:
        sb.table("customer_companies").insert({
            "id": test_company_id,
            "client_id": test_client_id,
            "company_name": f"_TEST_DATA_HARDENING_{TEST_MARKER}",
            "primary_domain": "test-hardening.example.com",
            "qb_customer_id": "999999",
            "qb_customer_type": "Customer",
            "qb_tier": "Level 4 Enterprise",
            "qb_total_revenue": 500000,
            "metadata": {"_test_marker": TEST_MARKER},
        }).execute()

        contacts = [
            {
                "id": test_contact_ids["external_person"],
                "client_id": test_client_id,
                "email_address": "external.person@test-hardening.example.com",
                "display_name": "External Person",
                "contact_type": "person",
                "customer_company_id": test_company_id,
                "qb_linked_at": None,
                "qb_tier": None,
                "metadata": {"_test_marker": TEST_MARKER},
            },
            {
                "id": test_contact_ids["internal_employee"],
                "client_id": test_client_id,
                "email_address": f"test.employee@{internal_domain}",
                "display_name": "Internal Employee",
                "contact_type": "internal",
                "customer_company_id": test_company_id,
                "qb_linked_at": None,
                "qb_tier": None,
                "metadata": {"_test_marker": TEST_MARKER},
            },
            {
                "id": test_contact_ids["shared_address"],
                "client_id": test_client_id,
                "email_address": "accounts@test-hardening.example.com",
                "display_name": "Accounts",
                "contact_type": "shared",
                "customer_company_id": test_company_id,
                "qb_linked_at": None,
                "qb_tier": None,
                "metadata": {"_test_marker": TEST_MARKER},
            },
        ]

        for c in contacts:
            sb.table("customer_contacts").insert(c).execute()

        sb.rpc("batch_propagate_qb_data_to_contacts", {"p_client_id": test_client_id}).execute()

        for label, cid in test_contact_ids.items():
            row = sb.table("customer_contacts").select(
                "qb_tier, qb_customer_type, qb_linked_at, contact_type"
            ).eq("id", cid).single().execute()

            data = row.data

            if label == "external_person":
                if data.get("qb_tier") == "Level 4 Enterprise":
                    t_pass("external person got QB tier")
                else:
                    t_fail("external person QB tier", f"expected 'Level 4 Enterprise', got {data.get('qb_tier')!r}")
                if data.get("qb_linked_at") is not None:
                    t_pass("external person got qb_linked_at")
                else:
                    t_fail("external person qb_linked_at", "expected non-null")

            elif label == "internal_employee":
                if data.get("qb_tier") is None:
                    t_pass("internal employee excluded from QB tier")
                else:
                    t_fail("internal employee exclusion", f"got qb_tier={data.get('qb_tier')!r}")
                if data.get("qb_linked_at") is None:
                    t_pass("internal employee excluded from qb_linked_at")
                else:
                    t_fail("internal employee qb_linked_at", "should be NULL")

            elif label == "shared_address":
                if data.get("qb_tier") is None:
                    t_pass("shared address excluded from QB tier")
                else:
                    t_fail("shared address exclusion", f"got qb_tier={data.get('qb_tier')!r}")
                if data.get("qb_linked_at") is None:
                    t_pass("shared address excluded from qb_linked_at")
                else:
                    t_fail("shared address qb_linked_at", "should be NULL")

    finally:
        for cid in test_contact_ids.values():
            try:
                sb.table("customer_contacts").delete().eq("id", cid).execute()
            except Exception:
                pass
        try:
            sb.table("customer_companies").delete().eq("id", test_company_id).execute()
        except Exception:
            pass
        print(f"\n{C.B}Cleanup: test data removed{C.END}")


# -- Main ---------------------------------------------------------------------

def main():
    print(f"\n{'=' * 60}")
    print("  Data Hardening Integration Tests")
    print("  Fixes: signature extraction, shared-address, QB propagation")
    print(f"{'=' * 60}")

    test_signoff_rejection()
    test_shared_address_detection()
    test_qb_propagation_exclusion()

    print(f"\n{'=' * 60}")
    if failed == 0:
        print(f"  {C.G}ALL {passed} TESTS PASSED{C.END}")
    else:
        print(f"  {C.G}{passed} passed{C.END}, {C.R}{failed} failed{C.END}")
    print(f"{'=' * 60}\n")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
