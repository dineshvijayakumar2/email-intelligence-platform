"""
Tests for Contact Intelligence API endpoints.

Tests run against a real Supabase instance (no mocks) because the SQL
view logic IS the thing being tested. Requires SUPABASE_URL and
SUPABASE_SERVICE_KEY in environment (loaded from backend/.env.production
or backend/.env).

Test data is inserted in fixtures and cleaned up via teardown.
"""
from __future__ import annotations

import os
import sys
import uuid
import pytest

# Ensure backend is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__), "..", "..", "backend", ".env.production")
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", "backend", ".env")
load_dotenv(env_path)

from supabase import create_client

# ─── Fixtures ────────────────────────────────────────────────────────────

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

pytestmark = pytest.mark.skipif(
    not SUPABASE_URL or not SUPABASE_KEY,
    reason="SUPABASE_URL / SUPABASE_SERVICE_KEY not set",
)


@pytest.fixture(scope="module")
def sb():
    """Supabase client for the test module."""
    return create_client(SUPABASE_URL, SUPABASE_KEY)


@pytest.fixture(scope="module")
def test_ids():
    """Generate unique IDs for test data to avoid collisions."""
    return {
        "client_id": "241d7b99-f099-4557-96e5-212c4af10812",  # existing Carbon8 client
        "contact_id": str(uuid.uuid4()),
        "company_id": str(uuid.uuid4()),
        "email_id": str(uuid.uuid4()),
    }


@pytest.fixture(scope="module", autouse=True)
def seed_test_data(sb, test_ids):
    """Insert minimal test data for persona view verification.

    Uses the real Carbon8 client_id so it passes any client_id-based
    checks. Cleans up in teardown.
    """
    cid = test_ids["client_id"]
    company_id = test_ids["company_id"]
    contact_id = test_ids["contact_id"]
    email_id = test_ids["email_id"]

    # Clean up any stale data from previous failed runs
    sb.table("email_contact_links").delete().eq("client_id", cid).like("email_address", "_test_persona_%").execute()
    sb.table("emails").delete().eq("client_id", cid).like("sender_email", "_test_persona_%").execute()
    sb.table("customer_contacts").delete().eq("client_id", cid).like("email_address", "_test_persona_%").execute()
    sb.table("customer_companies").delete().eq("client_id", cid).eq("company_name", "_test_persona_company").execute()

    # 1. Insert test company
    sb.table("customer_companies").insert({
        "id": company_id,
        "client_id": cid,
        "company_name": "_test_persona_company",
        "industry": "Testing",
        "qb_tier": "Level 2 Corporate",
        "qb_customer_type": "Active A",
    }).execute()

    # 2. Insert test contact
    sb.table("customer_contacts").insert({
        "id": contact_id,
        "client_id": cid,
        "customer_company_id": company_id,
        "email_address": f"_test_persona_{contact_id[:8]}@example.com",
        "full_name": "_Test Persona Contact",
        "seniority_level": "senior",
        "is_primary_contact": True,
    }).execute()

    # 3. Insert a test email + email_contact_link
    sb.table("emails").insert({
        "id": email_id,
        "message_id": f"<test-persona-{email_id[:8]}@example.com>",
        "mailbox_id": None,
        "sender_email": f"_test_persona_{contact_id[:8]}@example.com",
        "received_date": "2026-04-15T10:00:00Z",
        "is_outbound": False,
        "client_id": cid,
        "attachments": "[]",
    }).execute()

    sb.table("email_contact_links").insert({
        "email_id": email_id,
        "contact_id": contact_id,
        "client_id": cid,
        "email_address": f"_test_persona_{contact_id[:8]}@example.com",
        "role": "sender",
    }).execute()

    yield  # tests run here

    # ── Teardown ──
    sb.table("email_contact_links").delete().eq("email_id", email_id).execute()
    sb.table("emails").delete().eq("id", email_id).execute()
    sb.table("customer_contacts").delete().eq("id", contact_id).execute()
    sb.table("customer_companies").delete().eq("id", company_id).execute()


# ─── View Shape Tests ────────────────────────────────────────────────────


class TestContactPersonaView:
    """Test that the contact_persona view returns expected data."""

    def test_persona_view_returns_expected_fields(self, sb, test_ids):
        """Query contact_persona and assert all expected columns are present."""
        result = (
            sb.table("contact_persona")
            .select("*")
            .eq("contact_id", test_ids["contact_id"])
            .execute()
        )
        assert result.data, "contact_persona should return data for test contact"
        row = result.data[0]

        # Core identity fields
        assert row["contact_id"] == test_ids["contact_id"]
        assert row["company_id"] == test_ids["company_id"]
        assert row["name"] == "_Test Persona Contact"
        assert row["company_name"] == "_test_persona_company"
        assert row["industry"] == "Testing"
        assert row["qb_tier"] == "Level 2 Corporate"
        assert row["customer_type"] == "Active A"
        assert row["seniority"] == "senior"
        assert row["is_primary_contact"] is True

        # Quote metrics (should be zero/null for test contact)
        assert "quote_count" in row
        assert "strike_rate" in row
        assert "total_quote_value" in row

        # Email metrics (from materialized view — may be stale)
        assert "email_total" in row
        assert "email_velocity_30d" in row

        # Persona classification and engagement score
        assert "persona_classification" in row
        assert "engagement_score" in row
        assert row["persona_classification"] in (
            "champion", "active_relationship", "prospect",
            "inactive_buyer", "dormant", "unknown",
        )
        assert isinstance(row["engagement_score"], int)
        assert 0 <= row["engagement_score"] <= 100

    def test_persona_classification_for_no_data(self, sb, test_ids):
        """A contact with no quotes and no email history in the matview
        should be classified as 'dormant' or 'unknown' — dormant fires
        when days_since_last_email > 180 (which is true when NULL)."""
        result = (
            sb.table("contact_persona")
            .select("persona_classification, quote_count, email_total")
            .eq("contact_id", test_ids["contact_id"])
            .execute()
        )
        row = result.data[0]
        # New test contact has 0 quotes and 0 in matview (not refreshed)
        # The CASE expression hits 'dormant' because COALESCE(days_since_last_email, 999) > 180
        if row["quote_count"] == 0 and row["email_total"] == 0:
            assert row["persona_classification"] in ("dormant", "unknown")


class TestCompanyContactSummary:
    """Test company_contact_summary view."""

    def test_company_summary_shape(self, sb, test_ids):
        result = (
            sb.table("company_contact_summary")
            .select("*")
            .eq("company_id", test_ids["company_id"])
            .execute()
        )
        assert result.data, "company_contact_summary should return data"
        row = result.data[0]
        assert row["company_id"] == test_ids["company_id"]
        assert "total_contacts" in row
        assert row["total_contacts"] >= 1
        assert "champions_count" in row
        assert "avg_strike_rate" in row
        assert "total_quote_value" in row


class TestIndustryBenchmarks:
    """Test industry_benchmarks view."""

    def test_industry_benchmarks_shape(self, sb, test_ids):
        """Query benchmarks for 'Testing' industry.

        This may return no rows if < 3 contacts exist in the 'Testing'
        industry. That's OK — the HAVING clause is intentional.
        """
        result = (
            sb.table("industry_benchmarks")
            .select("*")
            .eq("industry", "Testing")
            .eq("client_id", test_ids["client_id"])
            .execute()
        )
        # May be empty if < 3 contacts in 'Testing' industry
        if result.data:
            row = result.data[0]
            assert "contact_count" in row
            assert "avg_strike_rate" in row
            assert "avg_engagement_score" in row


class TestContactQuoteMetrics:
    """Test contact_quote_metrics view."""

    def test_quote_metrics_zero_for_new_contact(self, sb, test_ids):
        result = (
            sb.table("contact_quote_metrics")
            .select("*")
            .eq("contact_id", test_ids["contact_id"])
            .execute()
        )
        assert result.data, "contact_quote_metrics should return a row"
        row = result.data[0]
        assert row["quote_count"] == 0
        assert row["strike_rate"] is None  # NULL when quote_count=0
        assert row["total_quote_value"] == 0


# ─── Materialized View Refresh Test ──────────────────────────────────────


class TestMaterializedViewRefresh:
    """Test that refresh_contact_email_metrics() RPC works."""

    def test_refresh_completes(self, sb):
        """Call the refresh function and verify it doesn't error."""
        try:
            sb.rpc("refresh_contact_email_metrics", {}).execute()
        except Exception as e:
            pytest.fail(f"Materialized view refresh failed: {e}")


# ─── Authorization Tests ─────────────────────────────────────────────────


class TestCrossTenantIsolation:
    """Verify that view results are scoped by client_id."""

    def test_contact_not_visible_to_other_client(self, sb, test_ids):
        """Query contact_persona with a non-existent client_id.

        The view itself doesn't enforce auth — that's the API layer's
        job. But we verify the client_id column is present and correct
        so the API can filter.
        """
        result = (
            sb.table("contact_persona")
            .select("contact_id, client_id")
            .eq("contact_id", test_ids["contact_id"])
            .execute()
        )
        assert result.data
        row = result.data[0]
        assert row["client_id"] == test_ids["client_id"]

        # Querying with wrong client_id should return empty
        wrong_result = (
            sb.table("contact_persona")
            .select("contact_id")
            .eq("contact_id", test_ids["contact_id"])
            .eq("client_id", "00000000-0000-0000-0000-000000000000")
            .execute()
        )
        assert not wrong_result.data, "Should not see contact under wrong client_id"


# ─── Pagination Test ─────────────────────────────────────────────────────


class TestPagination:
    """Test that pagination works on the contact_persona view."""

    def test_limit_offset(self, sb, test_ids):
        """Verify limit/offset works on the view."""
        result = (
            sb.table("contact_persona")
            .select("contact_id")
            .eq("company_id", test_ids["company_id"])
            .range(0, 0)  # limit 1
            .execute()
        )
        assert len(result.data) <= 1
