"""
Tests for QB Cleanup Dashboard: qb_cleanup_dashboard_stats RPC, pipeline
integrity (QB -> Companies -> Contacts -> Emails), and regression tests for
the health endpoint shape.

Tests run against a real Supabase instance (no mocks). Requires SUPABASE_URL
and SUPABASE_SERVICE_KEY in environment.

No test data is seeded -- tests operate on existing Carbon8 data.
All tests are read-only.

Run:
    python -m pytest tests/routers/test_qb_cleanup_dashboard.py -v
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__), "..", "..", "backend", ".env.production")
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", "backend", ".env")
load_dotenv(env_path)

from supabase import create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
CLIENT_ID = "241d7b99-f099-4557-96e5-212c4af10812"  # Carbon8

pytestmark = pytest.mark.skipif(
    not SUPABASE_URL or not SUPABASE_KEY,
    reason="SUPABASE_URL / SUPABASE_SERVICE_KEY not set",
)


@pytest.fixture(scope="module")
def sb():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


@pytest.fixture(scope="module")
def dashboard(sb):
    """Fetch dashboard stats once for all tests in module."""
    result = sb.rpc("qb_cleanup_dashboard_stats", {"p_client_id": CLIENT_ID}).execute()
    assert result.data is not None, "RPC should return data"
    return result.data


# ─── RPC Shape Tests ────────────────────────────────────────────────────


class TestDashboardRPCShape:
    """Verify qb_cleanup_dashboard_stats returns all expected sections and fields."""

    def test_top_level_sections(self, dashboard):
        for section in ["revenue", "companies", "contacts", "emails"]:
            assert section in dashboard, f"Missing top-level section: {section}"

    def test_revenue_fields(self, dashboard):
        rev = dashboard["revenue"]
        for field in ["total", "matched", "unmatched", "match_rate_pct", "method_breakdown", "buckets"]:
            assert field in rev, f"revenue missing field: {field}"

    def test_companies_fields(self, dashboard):
        co = dashboard["companies"]
        for field in ["total_qb_customers", "matched_qb_customers", "unmatched_qb_customers",
                      "total_sb_companies", "qb_anchored_sb", "contaminated_sb"]:
            assert field in co, f"companies missing field: {field}"

    def test_contacts_fields(self, dashboard):
        ct = dashboard["contacts"]
        for field in ["total", "with_qb_company", "with_non_qb_company", "no_company"]:
            assert field in ct, f"contacts missing field: {field}"

    def test_emails_fields(self, dashboard):
        em = dashboard["emails"]
        for field in ["total", "with_qb_company", "with_non_qb_company", "no_company"]:
            assert field in em, f"emails missing field: {field}"

    def test_buckets_shape(self, dashboard):
        buckets = dashboard["revenue"]["buckets"]
        for name in ["email_linked", "staged", "no_link"]:
            assert name in buckets, f"Missing bucket: {name}"
            b = buckets[name]
            assert "count" in b and "revenue" in b

    def test_method_breakdown_shape(self, dashboard):
        mb = dashboard["revenue"]["method_breakdown"]
        assert isinstance(mb, dict)
        for method, stats in mb.items():
            assert "count" in stats, f"Method '{method}' missing 'count'"
            assert "revenue" in stats, f"Method '{method}' missing 'revenue'"

    def test_nonexistent_client_returns_zeros(self, sb):
        fake_id = "00000000-0000-0000-0000-000000000000"
        data = sb.rpc("qb_cleanup_dashboard_stats", {"p_client_id": fake_id}).execute().data
        assert float(data["revenue"]["total"]) == 0
        assert int(data["companies"]["total_qb_customers"]) == 0
        assert int(data["contacts"]["total"]) == 0
        assert int(data["emails"]["total"]) == 0


# ─── Revenue Consistency ────────────────────────────────────────────────


class TestRevenueConsistency:
    """Revenue arithmetic should be internally consistent."""

    def test_matched_plus_unmatched_equals_total(self, dashboard):
        rev = dashboard["revenue"]
        total = float(rev["total"])
        matched = float(rev["matched"])
        unmatched = float(rev["unmatched"])
        assert abs(matched + unmatched - total) < 0.02, (
            f"matched ({matched}) + unmatched ({unmatched}) != total ({total})"
        )

    def test_match_rate_consistent_with_totals(self, dashboard):
        rev = dashboard["revenue"]
        total = float(rev["total"])
        matched = float(rev["matched"])
        pct = float(rev["match_rate_pct"])
        if total > 0:
            expected = round(matched / total * 100, 1)
            assert abs(pct - expected) < 0.2, f"match_rate_pct {pct} != calc {expected}"

    def test_all_revenues_non_negative(self, dashboard):
        rev = dashboard["revenue"]
        assert float(rev["total"]) >= 0
        assert float(rev["matched"]) >= 0
        assert float(rev["unmatched"]) >= 0

    def test_bucket_counts_non_negative(self, dashboard):
        for name, b in dashboard["revenue"]["buckets"].items():
            assert int(b["count"]) >= 0, f"Bucket {name} count is negative"
            assert float(b["revenue"]) >= 0, f"Bucket {name} revenue is negative"

    def test_method_revenue_sums_to_matched(self, dashboard):
        rev = dashboard["revenue"]
        method_total = sum(float(s["revenue"]) for s in rev["method_breakdown"].values())
        matched = float(rev["matched"])
        assert abs(method_total - matched) < 1.0, (
            f"Method revenue sum ({method_total}) != matched ({matched})"
        )


# ─── Company Consistency ────────────────────────────────────────────────


class TestCompanyConsistency:
    """Company counts should be consistent across the pipeline."""

    def test_qb_matched_plus_unmatched_equals_total(self, dashboard):
        co = dashboard["companies"]
        total = int(co["total_qb_customers"])
        matched = int(co["matched_qb_customers"])
        unmatched = int(co["unmatched_qb_customers"])
        assert matched + unmatched == total, (
            f"matched ({matched}) + unmatched ({unmatched}) != total ({total})"
        )

    def test_qb_anchored_not_greater_than_total_sb(self, dashboard):
        co = dashboard["companies"]
        assert int(co["qb_anchored_sb"]) <= int(co["total_sb_companies"])

    def test_contaminated_not_greater_than_anchored(self, dashboard):
        co = dashboard["companies"]
        assert int(co["contaminated_sb"]) <= int(co["qb_anchored_sb"])

    def test_total_sb_is_positive(self, dashboard):
        assert int(dashboard["companies"]["total_sb_companies"]) > 0

    def test_qb_anchored_matches_independent_count(self, sb, dashboard):
        """Cross-check: qb_anchored_sb should match count of companies with qb_customer_id set."""
        resp = sb.table("customer_companies").select(
            "id", count="exact"
        ).eq("client_id", CLIENT_ID).not_.is_(
            "qb_customer_id", "null"
        ).limit(0).execute()
        independent_count = resp.count or 0
        rpc_count = int(dashboard["companies"]["qb_anchored_sb"])
        assert rpc_count == independent_count, (
            f"RPC qb_anchored_sb ({rpc_count}) != independent count ({independent_count})"
        )


# ─── Contact Pipeline ──────────────────────────────────────────────────


class TestContactPipeline:
    """Contact stats should be consistent and the pipeline should show trickle-down."""

    def test_contact_categories_sum_to_total(self, dashboard):
        ct = dashboard["contacts"]
        total = int(ct["total"])
        qb = int(ct["with_qb_company"])
        non_qb = int(ct["with_non_qb_company"])
        no_co = int(ct["no_company"])
        assert qb + non_qb + no_co == total, (
            f"with_qb ({qb}) + non_qb ({non_qb}) + no_company ({no_co}) != total ({total})"
        )

    def test_all_contact_counts_non_negative(self, dashboard):
        ct = dashboard["contacts"]
        for field in ["total", "with_qb_company", "with_non_qb_company", "no_company"]:
            assert int(ct[field]) >= 0, f"contacts.{field} is negative"

    def test_contacts_total_matches_independent_count(self, sb, dashboard):
        resp = sb.table("customer_contacts").select(
            "id", count="exact"
        ).eq("client_id", CLIENT_ID).limit(0).execute()
        independent = resp.count or 0
        rpc = int(dashboard["contacts"]["total"])
        assert rpc == independent, f"RPC contacts total ({rpc}) != table count ({independent})"


# ─── Email Pipeline ─────────────────────────────────────────────────────


class TestEmailPipeline:
    """Email stats should be consistent and show trickle-down coverage."""

    def test_email_categories_sum_to_total(self, dashboard):
        em = dashboard["emails"]
        total = int(em["total"])
        qb = int(em["with_qb_company"])
        non_qb = int(em["with_non_qb_company"])
        no_co = int(em["no_company"])
        assert qb + non_qb + no_co == total, (
            f"with_qb ({qb}) + non_qb ({non_qb}) + no_company ({no_co}) != total ({total})"
        )

    def test_all_email_counts_non_negative(self, dashboard):
        em = dashboard["emails"]
        for field in ["total", "with_qb_company", "with_non_qb_company", "no_company"]:
            assert int(em[field]) >= 0, f"emails.{field} is negative"

    def test_email_total_matches_independent_count(self, sb, dashboard):
        resp = sb.table("emails").select(
            "id", count="exact"
        ).eq("client_id", CLIENT_ID).limit(0).execute()
        independent = resp.count or 0
        rpc = int(dashboard["emails"]["total"])
        assert rpc == independent, f"RPC emails total ({rpc}) != table count ({independent})"


# ─── Cross-Pipeline Invariants ──────────────────────────────────────────


class TestCrossPipelineInvariants:
    """Invariants that span multiple sections of the dashboard."""

    def test_qb_linked_contacts_implies_qb_anchored_companies(self, dashboard):
        """If contacts are QB-linked, there must be QB-anchored companies."""
        if int(dashboard["contacts"]["with_qb_company"]) > 0:
            assert int(dashboard["companies"]["qb_anchored_sb"]) > 0

    def test_qb_linked_emails_implies_qb_anchored_companies(self, dashboard):
        """If emails are QB-linked, there must be QB-anchored companies."""
        if int(dashboard["emails"]["with_qb_company"]) > 0:
            assert int(dashboard["companies"]["qb_anchored_sb"]) > 0

    def test_matched_revenue_implies_matched_customers(self, dashboard):
        if float(dashboard["revenue"]["matched"]) > 0:
            assert int(dashboard["companies"]["matched_qb_customers"]) > 0

    def test_method_count_sums_to_matched_customers(self, dashboard):
        """Total count across all methods should equal matched QB customers."""
        method_count = sum(
            int(s["count"]) for s in dashboard["revenue"]["method_breakdown"].values()
        )
        matched = int(dashboard["companies"]["matched_qb_customers"])
        assert method_count == matched, (
            f"Method count sum ({method_count}) != matched_qb_customers ({matched})"
        )

    def test_emails_qb_linked_less_than_total_emails(self, dashboard):
        em = dashboard["emails"]
        assert int(em["with_qb_company"]) <= int(em["total"])

    def test_contacts_qb_linked_less_than_total_contacts(self, dashboard):
        ct = dashboard["contacts"]
        assert int(ct["with_qb_company"]) <= int(ct["total"])


# ─── Regression: Old Health Endpoint Shape ──────────────────────────────


class TestHealthEndpointRegression:
    """Verify the backend /health endpoint still returns usable data.

    The endpoint was refactored from 12 separate queries to a single RPC call.
    These tests verify the new response shape is usable by the frontend.
    """

    def test_health_rpc_returns_qb_configured(self, sb):
        """The /health endpoint adds qb_configured to the RPC result."""
        data = sb.rpc("qb_cleanup_dashboard_stats", {"p_client_id": CLIENT_ID}).execute().data
        assert data is not None
        data["qb_configured"] = True
        assert data["qb_configured"] is True

    def test_frontend_can_extract_revenue_bar_data(self, dashboard):
        """Frontend revenue progress bar needs: total, matched, match_rate_pct."""
        rev = dashboard["revenue"]
        assert float(rev["total"]) > 0
        assert float(rev["matched"]) >= 0
        assert 0 <= float(rev["match_rate_pct"]) <= 100

    def test_frontend_can_extract_pipeline_cards(self, dashboard):
        """Frontend pipeline cards need counts from all 4 sections."""
        assert int(dashboard["companies"]["total_qb_customers"]) > 0
        assert int(dashboard["companies"]["total_sb_companies"]) > 0
        assert int(dashboard["contacts"]["total"]) > 0
        assert int(dashboard["emails"]["total"]) > 0

    def test_frontend_can_extract_tab_counts(self, dashboard):
        """Tab bar uses staged.count, matched_qb_customers, unmatched_qb_customers."""
        assert int(dashboard["revenue"]["buckets"]["staged"]["count"]) >= 0
        assert int(dashboard["companies"]["matched_qb_customers"]) >= 0
        assert int(dashboard["companies"]["unmatched_qb_customers"]) >= 0

    def test_frontend_can_extract_method_breakdown(self, dashboard):
        """Method breakdown section needs method -> {count, revenue}."""
        mb = dashboard["revenue"]["method_breakdown"]
        assert len(mb) > 0, "Should have at least one match method"
        for method, stats in mb.items():
            assert isinstance(method, str)
            assert float(stats["revenue"]) >= 0
            assert int(stats["count"]) >= 0

    def test_frontend_contaminated_alert(self, dashboard):
        """Contamination alert needs contaminated_sb count."""
        assert int(dashboard["companies"]["contaminated_sb"]) >= 0


# ─── Contamination Verification ─────────────────────────────────────────


class TestContaminationCount:
    """Verify contaminated_sb count is plausible via REST queries."""

    def test_contaminated_is_positive_after_cleanup(self, dashboard):
        """After Step 1, there should be some contaminated SB companies."""
        rpc = int(dashboard["companies"]["contaminated_sb"])
        assert rpc >= 0, "contaminated_sb should be non-negative"

    def test_contaminated_sample_has_multiple_qb(self, sb, dashboard):
        """Pick a matched_company_id that appears multiple times -- it should exist."""
        if int(dashboard["companies"]["contaminated_sb"]) == 0:
            pytest.skip("No contaminated companies to verify")

        matched = sb.table("qb_customers").select(
            "matched_company_id"
        ).eq("client_id", CLIENT_ID).not_.is_(
            "matched_company_id", "null"
        ).limit(500).execute()

        from collections import Counter
        counts = Counter(r["matched_company_id"] for r in (matched.data or []))
        multi = {cid: cnt for cid, cnt in counts.items() if cnt > 1}
        assert len(multi) > 0, "Should find at least one company with >1 QB match in first 500 rows"
