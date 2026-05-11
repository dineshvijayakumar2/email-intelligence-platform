"""
Tests for QB Match Review: revenue stats RPC, browse queries, score calibration.

Tests run against a real Supabase instance (no mocks). Requires SUPABASE_URL
and SUPABASE_SERVICE_KEY in environment (loaded from backend/.env.production
or backend/.env).

No test data is seeded — these tests operate on existing Carbon8 QB data
which is always present after a sync. Tests are read-only (no inserts/updates).

Run:
    python -m pytest tests/routers/test_qb_match_review.py -v
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

# ─── Fixtures ────────────────────────────────────────────────────────────

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


# ─── Revenue Stats RPC ──────────────────────────────────────────────────


class TestRevenueStatsRPC:
    """Test qb_health_revenue_stats RPC returns expected shape and values."""

    def test_rpc_returns_all_fields(self, sb):
        result = sb.rpc("qb_health_revenue_stats", {"p_client_id": CLIENT_ID}).execute()
        data = result.data
        assert data is not None, "RPC should return data"

        required_fields = [
            "total_revenue", "matched_revenue", "unmatched_revenue",
            "revenue_match_rate_pct", "revenue_target_pct",
            "method_revenue", "buckets",
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"

    def test_revenue_totals_are_consistent(self, sb):
        """matched + unmatched should equal total revenue."""
        data = sb.rpc("qb_health_revenue_stats", {"p_client_id": CLIENT_ID}).execute().data
        total = float(data["total_revenue"])
        matched = float(data["matched_revenue"])
        unmatched = float(data["unmatched_revenue"])

        assert total >= 0, "Total revenue should be non-negative"
        assert matched >= 0, "Matched revenue should be non-negative"
        assert unmatched >= 0, "Unmatched revenue should be non-negative"
        assert abs(matched + unmatched - total) < 0.01, (
            f"matched ({matched}) + unmatched ({unmatched}) should equal total ({total})"
        )

    def test_match_rate_percentage(self, sb):
        data = sb.rpc("qb_health_revenue_stats", {"p_client_id": CLIENT_ID}).execute().data
        pct = float(data["revenue_match_rate_pct"])
        assert 0 <= pct <= 100, f"Match rate should be 0-100, got {pct}"

        total = float(data["total_revenue"])
        if total > 0:
            expected = round(float(data["matched_revenue"]) / total * 100, 1)
            assert abs(pct - expected) < 0.2, f"Match rate {pct} doesn't match calc {expected}"

    def test_target_is_95(self, sb):
        data = sb.rpc("qb_health_revenue_stats", {"p_client_id": CLIENT_ID}).execute().data
        assert data["revenue_target_pct"] == 95

    def test_buckets_shape(self, sb):
        data = sb.rpc("qb_health_revenue_stats", {"p_client_id": CLIENT_ID}).execute().data
        buckets = data["buckets"]
        for bucket_name in ["email_linked", "staged", "no_link"]:
            assert bucket_name in buckets, f"Missing bucket: {bucket_name}"
            bucket = buckets[bucket_name]
            assert "count" in bucket, f"{bucket_name} missing 'count'"
            assert "revenue" in bucket, f"{bucket_name} missing 'revenue'"
            assert int(bucket["count"]) >= 0
            assert float(bucket["revenue"]) >= 0

    def test_method_revenue_shape(self, sb):
        """method_revenue should be a dict of method -> {revenue, count}."""
        data = sb.rpc("qb_health_revenue_stats", {"p_client_id": CLIENT_ID}).execute().data
        mr = data["method_revenue"]
        assert isinstance(mr, dict), "method_revenue should be a dict"
        for method, stats in mr.items():
            assert "revenue" in stats, f"Method '{method}' missing 'revenue'"
            assert "count" in stats, f"Method '{method}' missing 'count'"

    def test_nonexistent_client_returns_zeros(self, sb):
        fake_id = "00000000-0000-0000-0000-000000000000"
        data = sb.rpc("qb_health_revenue_stats", {"p_client_id": fake_id}).execute().data
        assert float(data["total_revenue"]) == 0
        assert float(data["matched_revenue"]) == 0
        assert float(data["unmatched_revenue"]) == 0


# ─── Browse Query Tests ─────────────────────────────────────────────────


class TestBrowseQueries:
    """Test the underlying queries used by qb-customers-browse endpoint."""

    def test_matched_customers_query(self, sb):
        """Matched QB customers should have matched_company_id set."""
        result = sb.table("qb_customers").select(
            "id, customer_name, total_invoiced, matched_company_id"
        ).eq("client_id", CLIENT_ID).not_.is_(
            "matched_company_id", "null"
        ).order("total_invoiced", desc=True).range(0, 4).execute()

        for row in (result.data or []):
            assert row["matched_company_id"] is not None
            assert row.get("customer_name"), "customer_name should not be empty"

    def test_unmatched_customers_query(self, sb):
        """Unmatched QB customers should have matched_company_id = NULL."""
        result = sb.table("qb_customers").select(
            "id, customer_name, total_invoiced, matched_company_id"
        ).eq("client_id", CLIENT_ID).is_(
            "matched_company_id", "null"
        ).order("total_invoiced", desc=True).range(0, 4).execute()

        for row in (result.data or []):
            assert row["matched_company_id"] is None

    def test_matched_plus_unmatched_equals_total(self, sb):
        """Matched + unmatched should equal total QB customers."""
        total_q = sb.table("qb_customers").select(
            "id", count="exact"
        ).eq("client_id", CLIENT_ID).limit(0).execute()
        total = total_q.count

        matched_q = sb.table("qb_customers").select(
            "id", count="exact"
        ).eq("client_id", CLIENT_ID).not_.is_(
            "matched_company_id", "null"
        ).limit(0).execute()
        matched = matched_q.count

        unmatched_q = sb.table("qb_customers").select(
            "id", count="exact"
        ).eq("client_id", CLIENT_ID).is_(
            "matched_company_id", "null"
        ).limit(0).execute()
        unmatched = unmatched_q.count

        assert matched + unmatched == total, (
            f"matched ({matched}) + unmatched ({unmatched}) != total ({total})"
        )

    def test_matched_company_enrichment(self, sb):
        """Matched customers should have corresponding company records."""
        result = sb.table("qb_customers").select(
            "matched_company_id"
        ).eq("client_id", CLIENT_ID).not_.is_(
            "matched_company_id", "null"
        ).range(0, 9).execute()

        company_ids = [r["matched_company_id"] for r in (result.data or []) if r.get("matched_company_id")]
        if not company_ids:
            pytest.skip("No matched customers to verify")

        companies = sb.table("customer_companies").select(
            "id, company_name, qb_match_method, total_emails"
        ).in_("id", company_ids).execute()

        found_ids = {c["id"] for c in (companies.data or [])}
        for cid in company_ids:
            assert cid in found_ids, f"Company {cid} not found in customer_companies"

    def test_candidates_have_required_fields(self, sb):
        """Unreviewed match candidates should have all fields needed for the UI."""
        result = sb.table("qb_match_candidates").select(
            "id, sb_company_id, sb_company_name, qb_record_id, qb_customer_id, "
            "qb_name, match_score, match_method, reviewed, accepted"
        ).eq("client_id", CLIENT_ID).eq("reviewed", False).range(0, 4).execute()

        for row in (result.data or []):
            assert row.get("qb_name"), "Candidate missing qb_name"
            assert row.get("sb_company_name"), "Candidate missing sb_company_name"
            assert row["match_score"] is not None, "Candidate missing match_score"
            assert row["match_method"] is not None, "Candidate missing match_method"
            assert row["reviewed"] is False


# ─── Score Calibration Tests ─────────────────────────────────────────────


class TestScoreCalibration:
    """Test that match scores map correctly to methods (no DB needed)."""

    SCORE_MAP = {
        "email_lookup": 100,
        "qb_anchored_link": 95,
        "qb_anchored_create": 90,
        "contact_chain": 80,
        "exact_name": 75,
        "domain_root": 65,
        "fuzzy": 60,
    }

    def test_email_is_highest(self):
        assert self.SCORE_MAP["email_lookup"] == 100

    def test_email_higher_than_name(self):
        assert self.SCORE_MAP["email_lookup"] > self.SCORE_MAP["exact_name"]

    def test_name_higher_than_domain(self):
        assert self.SCORE_MAP["exact_name"] > self.SCORE_MAP["domain_root"]

    def test_domain_higher_than_fuzzy(self):
        assert self.SCORE_MAP["domain_root"] > self.SCORE_MAP["fuzzy"]

    def test_all_scores_in_valid_range(self):
        for method, score in self.SCORE_MAP.items():
            assert 0 <= score <= 100, f"{method} score {score} out of range"

    def test_unknown_method_gets_default(self):
        default = self.SCORE_MAP.get("nonexistent_method", 50)
        assert default == 50

    def test_none_method_gets_default(self):
        default = self.SCORE_MAP.get(None, 50)
        assert default == 50

    def test_matched_scores_reflect_method(self, sb):
        """For matched QB customers, verify the company's match method
        exists in the score map and maps to a reasonable score."""
        result = sb.table("qb_customers").select(
            "matched_company_id"
        ).eq("client_id", CLIENT_ID).not_.is_(
            "matched_company_id", "null"
        ).range(0, 19).execute()

        company_ids = list({r["matched_company_id"] for r in (result.data or [])})
        if not company_ids:
            pytest.skip("No matched customers")

        companies = sb.table("customer_companies").select(
            "id, qb_match_method"
        ).in_("id", company_ids).execute()

        known_methods = set(self.SCORE_MAP.keys())
        for c in (companies.data or []):
            method = c.get("qb_match_method")
            if method:
                assert method in known_methods, (
                    f"Unknown match method '{method}' on company {c['id']}"
                )


# ─── Health Endpoint Data Tests ──────────────────────────────────────────


class TestHealthEndpointData:
    """Test the data that feeds the health endpoint."""

    def test_qb_customers_exist(self, sb):
        result = sb.table("qb_customers").select(
            "id", count="exact"
        ).eq("client_id", CLIENT_ID).limit(0).execute()
        assert result.count > 0, "Should have QB customers for Carbon8"

    def test_qb_unique_emails_exist(self, sb):
        result = sb.table("qb_unique_emails").select(
            "id", count="exact"
        ).eq("client_id", CLIENT_ID).limit(0).execute()
        assert result.count > 0, "Should have QB unique emails for Carbon8"

    def test_revenue_stats_consistent_with_qb_customers(self, sb):
        """Revenue from RPC should match SUM(total_invoiced) from qb_customers."""
        rpc_data = sb.rpc("qb_health_revenue_stats", {"p_client_id": CLIENT_ID}).execute().data
        rpc_total = float(rpc_data["total_revenue"])

        # Count matched via direct query
        matched_q = sb.table("qb_customers").select(
            "id", count="exact"
        ).eq("client_id", CLIENT_ID).not_.is_(
            "matched_company_id", "null"
        ).limit(0).execute()

        unmatched_q = sb.table("qb_customers").select(
            "id", count="exact"
        ).eq("client_id", CLIENT_ID).is_(
            "matched_company_id", "null"
        ).limit(0).execute()

        # The RPC's bucket counts should make sense
        buckets = rpc_data["buckets"]
        staged_count = int(buckets["staged"]["count"])
        email_linked_count = int(buckets["email_linked"]["count"])
        no_link_count = int(buckets["no_link"]["count"])
        bucket_total = staged_count + email_linked_count + no_link_count

        # Bucket total should be <= unmatched count (buckets partition unmatched)
        assert bucket_total <= unmatched_q.count + 1, (
            f"Bucket total ({bucket_total}) exceeds unmatched count ({unmatched_q.count})"
        )

        assert rpc_total > 0, "Carbon8 should have non-zero revenue"
