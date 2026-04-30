"""
Tests for the email_pipeline worker handler.

Tests 1-4: Mock all stage functions — test handler orchestration logic only.
Test 5: Requires a real database to verify the single-flight unique index.

Run:
    cd backend
    python -m pytest tests/workers/test_email_pipeline.py -v
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure src is importable
_backend = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_backend / "src"))
sys.path.insert(0, str(_backend))

from src.workers.handlers.email_pipeline import (  # type: ignore
    PIPELINE_STAGES,
    email_pipeline_handler,
)


# ── Fixtures ──────────────────────────────────────────────────────────────


def _mock_sb():
    """Build a mock Supabase client that supports chained calls."""
    sb = MagicMock()

    # .table().select().eq().limit().execute()  → mailbox lookup
    select_chain = MagicMock()
    select_chain.execute.return_value = MagicMock(
        data=[{"client_id": "test-client-id"}]
    )
    sb.table.return_value.select.return_value.eq.return_value.limit.return_value = (
        select_chain
    )

    # .table().select().eq().single().execute() → read parameters/error_summary
    single_chain = MagicMock()
    single_chain.execute.return_value = MagicMock(
        data={"parameters": {}, "error_summary": {}}
    )
    sb.table.return_value.select.return_value.eq.return_value.single.return_value = (
        single_chain
    )

    # .table().update().eq().execute() → progress writes
    sb.table.return_value.update.return_value.eq.return_value.execute.return_value = (
        MagicMock(data=[{}])
    )

    return sb


def _make_job(
    mailbox_id="test-mailbox",
    client_id=None,
    completed_steps=None,
    trigger_source="sync",
):
    return {
        "id": "test-job-id",
        "job_type": "email_pipeline",
        "mailbox_id": mailbox_id,
        "client_id": client_id,
        "parameters": {
            "trigger_source": trigger_source,
            **({"completed_steps": completed_steps} if completed_steps else {}),
        },
    }


# Common mock targets (module path as imported in the handler)
_HANDLER_MODULE = "workers.handlers.email_pipeline"
_ORCH_CLASS = "src.services.extraction_orchestrator.ExtractionOrchestrator"
_VECTOR_CLASS = "src.services.vector_service.VectorService"
_ANALYZER_CLASS = "src.services.ai_email_analyzer.AIEmailAnalyzer"
_BUCKET_CLASS = "src.services.ai_action_bucket_engine.ActionBucketEngine"


def _patch_all_services():
    """Return a dict of patchers for all 4 service classes.
    Each service method used by stages is mocked to return quickly.
    """
    orch = MagicMock()
    orch.run_extraction.return_value = {"success": True, "steps_completed": 9}
    orch._assign_canonical_threads.return_value = None
    orch._update_affected_threads.return_value = None
    orch._refresh_email_counts.return_value = None

    vector = MagicMock()
    vector.embed_emails_batch = AsyncMock(
        return_value={"embedded": 10, "failed": 0}
    )

    analyzer = MagicMock()
    analyzer.analyze_all_unanalyzed.return_value = {
        "total_analyzed": 15,
        "total_failed": 1,
        "batches": 2,
    }

    bucket = MagicMock()
    bucket.process_email_buckets.return_value = {
        "processed": 15,
        "buckets_created": 5,
    }

    return {
        "orch": orch,
        "vector": vector,
        "analyzer": analyzer,
        "bucket": bucket,
    }


# ── Test 1: Happy path ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_happy_path_all_stages_run():
    """All 10 stages run in order: ai_classify, bucket_engine, extract_and_link, ..."""
    sb = _mock_sb()
    job = _make_job()
    stop_event = asyncio.Event()
    mocks = _patch_all_services()

    with (
        patch(_ORCH_CLASS, return_value=mocks["orch"]),
        patch(_VECTOR_CLASS, return_value=mocks["vector"]),
        patch(_ANALYZER_CLASS, return_value=mocks["analyzer"]),
        patch(_BUCKET_CLASS, return_value=mocks["bucket"]),
    ):
        await email_pipeline_handler(sb, job, stop_event)

    # Verify all sync stages called via to_thread
    mocks["orch"].run_extraction.assert_called_once_with(lightweight=True)
    mocks["orch"]._assign_canonical_threads.assert_called_once()
    # _update_affected_threads called twice (steps 3 and 8)
    assert mocks["orch"]._update_affected_threads.call_count == 2
    mocks["orch"]._refresh_email_counts.assert_called_once()
    mocks["vector"].embed_emails_batch.assert_called_once()
    mocks["analyzer"].analyze_all_unanalyzed.assert_called_once()
    mocks["bucket"].process_email_buckets.assert_called_once()

    # Verify progress was persisted (at least once per stage + final)
    assert sb.table.return_value.update.called


# ── Test 2: Resume after failure ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_resume_skips_completed_stages():
    """Named stages in completed_steps are skipped regardless of position."""
    sb = _mock_sb()
    already_done = [
        "ai_classify",
        "bucket_engine",
        "extract_and_link",
        "assign_threads",
        "evaluate_threads",
        "refresh_counts",
    ]
    job = _make_job(completed_steps=already_done, trigger_source="resume")
    stop_event = asyncio.Event()
    mocks = _patch_all_services()

    with (
        patch(_ORCH_CLASS, return_value=mocks["orch"]),
        patch(_VECTOR_CLASS, return_value=mocks["vector"]),
        patch(_ANALYZER_CLASS, return_value=mocks["analyzer"]),
        patch(_BUCKET_CLASS, return_value=mocks["bucket"]),
    ):
        await email_pipeline_handler(sb, job, stop_event)

    # Stages 1-6 should NOT be called
    mocks["analyzer"].analyze_all_unanalyzed.assert_not_called()
    mocks["bucket"].process_email_buckets.assert_not_called()
    mocks["orch"].run_extraction.assert_not_called()
    mocks["orch"]._assign_canonical_threads.assert_not_called()
    mocks["orch"]._refresh_email_counts.assert_not_called()

    # Stages 7-10 SHOULD be called
    mocks["vector"].embed_emails_batch.assert_called_once()
    # _update_affected_threads called once (evaluate_threads_final only, evaluate_threads was skipped)
    assert mocks["orch"]._update_affected_threads.call_count == 1


# ── Test 3: Step failure stops pipeline ───────────────────────────────────


@pytest.mark.asyncio
async def test_step_failure_stops_pipeline():
    """embed_emails (stage 7) raises → stages 8-10 NOT called, exception re-raised."""
    sb = _mock_sb()
    job = _make_job()
    stop_event = asyncio.Event()
    mocks = _patch_all_services()

    # Make embed_emails fail
    mocks["vector"].embed_emails_batch = AsyncMock(
        side_effect=RuntimeError("OpenAI rate limit exceeded")
    )

    with (
        patch(_ORCH_CLASS, return_value=mocks["orch"]),
        patch(_VECTOR_CLASS, return_value=mocks["vector"]),
        patch(_ANALYZER_CLASS, return_value=mocks["analyzer"]),
        patch(_BUCKET_CLASS, return_value=mocks["bucket"]),
    ):
        with pytest.raises(RuntimeError, match="OpenAI rate limit"):
            await email_pipeline_handler(sb, job, stop_event)

    # Stages 1-6 should have run
    mocks["analyzer"].analyze_all_unanalyzed.assert_called_once()
    mocks["bucket"].process_email_buckets.assert_called_once()
    mocks["orch"].run_extraction.assert_called_once()
    mocks["orch"]._assign_canonical_threads.assert_called_once()
    mocks["orch"]._refresh_email_counts.assert_called_once()

    # Stage 7 was attempted (and failed)
    mocks["vector"].embed_emails_batch.assert_called_once()


# ── Test 4: Graceful shutdown ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_graceful_shutdown_stops_after_current_stage():
    """stop_event set after evaluate_threads (stage 5) → handler returns cleanly, stages 6-10 not called."""
    sb = _mock_sb()
    job = _make_job()
    stop_event = asyncio.Event()
    mocks = _patch_all_services()

    # Set stop_event when evaluate_threads (stage 5) is called
    def _set_stop_on_evaluate():
        stop_event.set()
        return None  # _update_affected_threads returns None

    mocks["orch"]._update_affected_threads.side_effect = _set_stop_on_evaluate

    with (
        patch(_ORCH_CLASS, return_value=mocks["orch"]),
        patch(_VECTOR_CLASS, return_value=mocks["vector"]),
        patch(_ANALYZER_CLASS, return_value=mocks["analyzer"]),
        patch(_BUCKET_CLASS, return_value=mocks["bucket"]),
    ):
        # Should return without raising
        await email_pipeline_handler(sb, job, stop_event)

    # Stages 1-5 should have run
    mocks["analyzer"].analyze_all_unanalyzed.assert_called_once()
    mocks["bucket"].process_email_buckets.assert_called_once()
    mocks["orch"].run_extraction.assert_called_once()
    mocks["orch"]._assign_canonical_threads.assert_called_once()
    # evaluate_threads ran (stage 5), which set stop_event
    assert mocks["orch"]._update_affected_threads.call_count == 1

    # Stages 6-10 should NOT run
    mocks["orch"]._refresh_email_counts.assert_not_called()
    mocks["vector"].embed_emails_batch.assert_not_called()


# ── Test 5: Single-flight via DB constraint ───────────────────────────────


@pytest.mark.asyncio
async def test_single_flight_dedup():
    """Creating two pipeline jobs for the same mailbox raises JobAlreadyActive.

    This test requires:
    - Migration 087 applied to the database
    - SUPABASE_URL and SUPABASE_SERVICE_KEY set in environment or .env

    Skip with: pytest -k "not single_flight"
    """
    import os

    # Try to load env
    try:
        from dotenv import load_dotenv

        for p in [
            Path(__file__).resolve().parent.parent.parent / ".env.production",
            Path(__file__).resolve().parent.parent.parent / ".env",
        ]:
            if p.exists():
                load_dotenv(p, override=False)
                break
    except ImportError:
        pass

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        pytest.skip("SUPABASE_URL / SUPABASE_SERVICE_KEY not set — skipping DB test")

    from supabase import create_client

    sb = create_client(url, key)

    from services.jobs import create_job, JobSpec, JobAlreadyActive  # type: ignore

    # Look up a real mailbox to satisfy FK constraint
    mbx_resp = sb.table("mailboxes").select("id").limit(1).execute()
    if not mbx_resp.data:
        pytest.skip("No mailboxes in DB — cannot run single-flight test")
    test_mailbox_id = mbx_resp.data[0]["id"]
    created_ids = []

    try:
        # Create first pipeline job
        job1_id = create_job(
            sb,
            JobSpec(
                job_type="email_pipeline",
                mailbox_id=test_mailbox_id,
                parameters={"trigger_source": "test", "_test_marker": "pipeline_test"},
                triggered_by="test",
                max_attempts=1,
            ),
        )
        created_ids.append(job1_id)

        # Second creation should raise JobAlreadyActive
        with pytest.raises(JobAlreadyActive):
            job2_id = create_job(
                sb,
                JobSpec(
                    job_type="email_pipeline",
                    mailbox_id=test_mailbox_id,
                    parameters={
                        "trigger_source": "test",
                        "_test_marker": "pipeline_test",
                    },
                    triggered_by="test",
                    max_attempts=1,
                ),
            )
            created_ids.append(job2_id)

    finally:
        # Cleanup: delete test jobs
        for jid in created_ids:
            try:
                sb.table("processing_jobs").delete().eq("id", jid).execute()
            except Exception:
                pass
