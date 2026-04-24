"""
Tests for vector_service embedding + audit column logic.

Run:
    cd backend
    python -m pytest tests/test_vector_service.py -v
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_backend = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_backend / "src"))
sys.path.insert(0, str(_backend))

from src.services.vector_service import (
    VectorService,
    _embedding_model_tag,
    _resolve_provider,
    reset_embedding_model,
)


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_provider():
    """Reset provider state before each test."""
    reset_embedding_model(None)
    yield
    reset_embedding_model(None)


@pytest.fixture
def mock_sb():
    return MagicMock()


@pytest.fixture
def svc(mock_sb):
    return VectorService(mock_sb)


# ── _resolve_provider ────────────────────────────────────────────────────


def test_resolve_provider_from_env():
    os.environ["EMBEDDING_PROVIDER"] = "openai"
    assert _resolve_provider() == "openai"
    os.environ["EMBEDDING_PROVIDER"] = "google"
    assert _resolve_provider() == "google"
    del os.environ["EMBEDDING_PROVIDER"]


def test_resolve_provider_override():
    reset_embedding_model("openai")
    os.environ["EMBEDDING_PROVIDER"] = "google"
    assert _resolve_provider() == "openai"
    del os.environ["EMBEDDING_PROVIDER"]


def test_resolve_provider_missing_raises():
    os.environ.pop("EMBEDDING_PROVIDER", None)
    with pytest.raises(RuntimeError, match="EMBEDDING_PROVIDER env var not set"):
        _resolve_provider()


# ── _embedding_model_tag ─────────────────────────────────────────────────


def test_model_tag_openai():
    os.environ["EMBEDDING_PROVIDER"] = "openai"
    tag = _embedding_model_tag()
    assert tag == "openai/text-embedding-3-small-768"
    del os.environ["EMBEDDING_PROVIDER"]


def test_model_tag_google():
    os.environ["EMBEDDING_PROVIDER"] = "google"
    tag = _embedding_model_tag()
    assert tag == "google/gemini-embedding-001-768"
    del os.environ["EMBEDDING_PROVIDER"]


# ── _build_email_embed_text ──────────────────────────────────────────────


def test_build_email_embed_text(svc):
    row = {
        "subject": "Quote request",
        "body_text": "Please send a quote for 500 labels",
        "sender_email": "buyer@example.com",
        "sender_name": "John",
        "is_outbound": False,
    }
    text = svc._build_email_embed_text(row)
    assert "Subject: Quote request" in text
    assert "From: John" in text
    assert "500 labels" in text
    assert "Direction:" not in text


def test_build_email_embed_text_outbound(svc):
    row = {"subject": "Re: Quote", "body_text": "", "sender_email": "us@co.com",
           "sender_name": None, "is_outbound": True}
    text = svc._build_email_embed_text(row)
    assert "Direction: outbound" in text
    assert "From: us@co.com" in text


# ── _build_company_embed_text ────────────────────────────────────────────


def test_build_company_embed_text(svc):
    row = {
        "company_name": "Acme Corp",
        "industry": "Manufacturing",
        "email_domains": ["acme.com", "acme.com.au"],
        "qb_tier": "Gold",
        "qb_customer_type": "Active",
        "qb_total_revenue": 150000.50,
        "qb_account_manager": "Jane",
    }
    text = svc._build_company_embed_text(row)
    assert "Acme Corp" in text
    assert "Industry: Manufacturing" in text
    assert "Tier: Gold" in text
    assert "$150,001" in text or "$150,000" in text


# ── _build_operation_embed_text ──────────────────────────────────────────


def test_build_operation_embed_text_prefers_qb_tags(svc):
    row = {
        "operation_name": "Digital Print",
        "department": "Print",
        "machine": "HP Indigo",
        "customer_name": "Acme",
        "capability_tags": ["offset"],
        "row_type": "production",
        "finishing_type": "lamination",
        "qb_capability_tag": "Digital",
        "qb_process_tag": "CMYK",
        "qb_machine_tier_tag": "Tier 1",
        "qb_row_type_tag": "Production",
        "qb_embellishment_tag": "Foil",
    }
    text = svc._build_operation_embed_text(row)
    assert "Capability: Digital" in text
    assert "offset" not in text
    assert "Process: CMYK" in text
    assert "Embellishment: Foil" in text


# ── _build_quote_embed_text ──────────────────────────────────────────────


def test_build_quote_embed_text(svc):
    row = {
        "category": "Labels",
        "sell_ex_tax": 2500.00,
        "quantity": 1000,
        "kinds": 3,
        "contact_name": "Bob",
        "quote_am_name": "Jane",
        "job_no": "J-123",
        "qb_customer_id": "CK-42",
    }
    customer_map = {
        "CK-42": {"customer_key_id": "CK-42", "customer_name": "Acme Corp", "industry": "Packaging"},
    }
    text = svc._build_quote_embed_text(row, customer_map)
    assert "Labels" in text
    assert "Customer: Acme Corp" in text
    assert "Industry: Packaging" in text
    assert "1000 qty" in text
    assert "3 kinds" in text
    assert "$2,500" in text
    assert "Job J-123" in text
    assert "Contact: Bob" in text
    assert "AM: Jane" in text


def test_build_quote_embed_text_minimal(svc):
    row = {"category": "Stickers", "sell_ex_tax": None, "quantity": None,
           "kinds": None, "contact_name": None, "quote_am_name": None,
           "job_no": None, "qb_customer_id": None}
    text = svc._build_quote_embed_text(row, {})
    assert text == "Stickers"
    assert len(text) < svc.MIN_EMBED_TEXT_LEN, "Thin quote text should be below quality gate"


def test_quality_gate_threshold(svc):
    """MIN_EMBED_TEXT_LEN filters out thin texts across all embed methods."""
    assert svc.MIN_EMBED_TEXT_LEN == 20
    thin_email = svc._build_email_embed_text(
        {"subject": "", "body_text": "", "sender_email": "a@b.com",
         "sender_name": None, "is_outbound": False})
    assert len(thin_email.strip()) < svc.MIN_EMBED_TEXT_LEN

    rich_email = svc._build_email_embed_text(
        {"subject": "Quote request for 500 labels", "body_text": "Please send pricing",
         "sender_email": "buyer@acme.com", "sender_name": "John", "is_outbound": False})
    assert len(rich_email.strip()) >= svc.MIN_EMBED_TEXT_LEN


# ── embed_companies audit columns (integration-style with mock DB) ───────


@pytest.mark.asyncio
async def test_embed_companies_passes_audit_cols(svc, mock_sb):
    os.environ["EMBEDDING_PROVIDER"] = "google"

    call_count = {"n": 0}

    def select_side_effect(*args, **kwargs):
        chain = MagicMock()
        chain.eq.return_value = chain
        chain.is_.return_value = chain
        chain.range.return_value = chain
        call_count["n"] += 1
        if call_count["n"] == 1:
            chain.execute.return_value = MagicMock(data=[
                {"id": "co-1", "company_name": "Test Co", "industry": "Tech",
                 "email_domains": [], "qb_tier": None, "qb_total_revenue": None,
                 "qb_account_manager": None, "qb_customer_type": None},
            ])
        else:
            chain.execute.return_value = MagicMock(data=[])
        return chain

    mock_sb.table.return_value = MagicMock(select=select_side_effect)

    rpc_mock = MagicMock()
    rpc_mock.execute.return_value = MagicMock(data=1)
    mock_sb.rpc.return_value = rpc_mock

    fake_embedding = [[0.2] * 768]
    with patch("src.services.vector_service.embed_texts", new_callable=AsyncMock, return_value=fake_embedding):
        result = await svc.embed_companies("client-1", limit=1)

    assert result["embedded"] == 1
    rpc_call = mock_sb.rpc.call_args
    params = rpc_call[0][1]
    assert params["p_embedding_model"] == "google/gemini-embedding-001-768"
    assert "p_embedded_at" in params

    del os.environ["EMBEDDING_PROVIDER"]


# ── Verify audit col params are constructed correctly ────────────────────


def test_rpc_params_include_audit_fields():
    """Verify the model_tag + timestamp are the right shape for RPC calls."""
    os.environ["EMBEDDING_PROVIDER"] = "openai"
    tag = _embedding_model_tag()
    from datetime import datetime, timezone
    now_ts = datetime.now(timezone.utc).isoformat()
    params = {
        "p_ids": ["id-1"],
        "p_embeddings": ["[0.1,0.2]"],
        "p_embedding_model": tag,
        "p_embedded_at": now_ts,
    }
    assert params["p_embedding_model"] == "openai/text-embedding-3-small-768"
    assert "T" in params["p_embedded_at"]
    del os.environ["EMBEDDING_PROVIDER"]
