"""
Analytics API Router - Sprint 2 Phase 5A

Comprehensive analytics endpoints for:
- Extraction job control (5 endpoints)
- Contact analytics (6 endpoints)
- Company analytics (5 endpoints)
- Thread analytics (4 endpoints)
- Response time analytics (4 endpoints)
- Communication patterns (4 endpoints)
- Dashboard summaries (2 endpoints)

Total: ~30 endpoints

Author: Sprint 2 Phase 5A Implementation
"""

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks, Depends
from typing import List, Optional
from datetime import datetime, timedelta, timezone
import logging

from ..dependencies.auth import get_current_user, require_role
from ..utils.audit import log_audit, audit_from_user
from ..models.analytics import (
    # Enums
    ExtractionStatus, ExtractionMode, ThreadStatus, ContactType, EngagementStatus,
    # Extraction models
    ExtractionJobCreate, ExtractionJobResponse, ExtractionJobDetail,
    ExtractionJobListResponse, ExtractionProgressResponse,
    # Contact models
    ContactAnalytics, ContactAnalyticsListResponse, TopEngagedContact,
    AtRiskContact, ContactTypeGrouping,
    # Company models
    CompanyAnalytics, CompanyAnalyticsListResponse, TopEngagedCompany,
    AtRiskCompany, EngagementStatusGrouping,
    # Thread models
    ThreadStatusSummary, ThreadStatusListResponse, OverdueThread, ThreadStatusCount,
    ThreadDetail, ThreadEmail,
    # Response time models
    ResponseTimeMetric, ResponseTimeListResponse, ResponseTimeStats, SlowestResponder,
    # Communication pattern models
    InitiationPattern, FrequencyPattern, EngagementTrend, CommunicationPattern,
    # Dashboard models
    DashboardSummary, ClientSummary,
)
from ..services.extraction_orchestrator import ExtractionOrchestrator

logger = logging.getLogger(__name__)


def _sanitize_search_term(term: str) -> str:
    """Escape SQL ILIKE wildcards in user-supplied search terms."""
    return term.replace('%', r'\%').replace('_', r'\_')


router = APIRouter(prefix="/analytics", tags=["analytics"])

# Supabase client will be injected from main.py
_supabase = None


def init_analytics_router(supabase_client):
    """Initialize the router with Supabase client"""
    global _supabase
    _supabase = supabase_client


# ============================================================================
# EXTRACTION CONTROL ENDPOINTS (5 endpoints)
# ============================================================================

@router.post("/extraction/run", response_model=ExtractionJobResponse)
async def trigger_extraction_job(data: ExtractionJobCreate, background_tasks: BackgroundTasks, current_user: dict = Depends(get_current_user)):
    """
    Trigger the email pipeline for a mailbox.

    Creates an email_pipeline worker job that runs all 8 stages:
    extract_and_link, assign_threads, evaluate_threads, refresh_counts,
    embed_emails, ai_classify, bucket_engine, evaluate_threads_final.
    """
    try:
        from ..services.jobs import create_job, JobSpec, JobAlreadyActive

        # Validate mailbox exists
        mailbox_check = _supabase.table('mailboxes').select('id, client_id').eq(
            'id', data.mailbox_id
        ).execute()

        if not mailbox_check.data:
            raise HTTPException(status_code=404, detail="Mailbox not found")

        client_id = mailbox_check.data[0]['client_id']

        try:
            job_id = create_job(_supabase, JobSpec(
                job_type='email_pipeline',
                mailbox_id=data.mailbox_id,
                client_id=client_id,
                parameters={
                    'trigger_source': 'manual_extraction',
                    'extraction_mode': data.mode.value,
                },
                triggered_by='user',
                max_attempts=1,
            ))
        except JobAlreadyActive as e:
            job_id = e.existing_job.get('id', 'active')
            return {
                "id": job_id,
                "client_id": client_id,
                "mailbox_id": data.mailbox_id,
                "status": ExtractionStatus.RUNNING,
                "extraction_mode": data.mode.value,
                "current_step": "Pipeline already running",
                "current_step_number": 0,
                "total_steps": 8
            }

        audit_from_user(current_user, "extract", "mailbox", resource_id=data.mailbox_id, details={"mode": data.mode.value, "trigger": "email_pipeline"})

        return {
            "id": job_id,
            "client_id": client_id,
            "mailbox_id": data.mailbox_id,
            "status": ExtractionStatus.PENDING,
            "extraction_mode": data.mode.value,
            "current_step": "Pipeline queued",
            "current_step_number": 0,
            "total_steps": 8
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to trigger pipeline job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/extraction/resolve-threads")
async def resolve_canonical_threads(
    client_id: str = Query(...),
    mailbox_id: Optional[str] = Query(None, description="Resolve a single mailbox only (for retry)"),
    skip_recompute: bool = Query(False, description="Skip thread_status recompute after resolution"),
    background_tasks: BackgroundTasks = None,
):
    """Resolve canonical thread IDs using Message-ID chain + subject heuristics.

    Step 1: Resolve canonical_thread_id on emails (all mailboxes or single if mailbox_id specified)
    Step 2: Recompute thread_status from canonical threads (unless skip_recompute=true)
    """
    try:
        def _run():
            from ..services.canonical_thread_resolver import CanonicalThreadResolver
            from ..services.thread_tracker import ThreadTracker

            logger.info(f"Starting canonical thread resolution for client {client_id}"
                        f"{f' mailbox {mailbox_id}' if mailbox_id else ' (all mailboxes)'}")
            resolver = CanonicalThreadResolver(client_id=client_id, mailbox_id=mailbox_id)
            stats = resolver.resolve_all()
            logger.info(f"Thread resolution stats: {stats}")

            if not skip_recompute:
                logger.info("Recomputing thread statuses from canonical threads...")
                # Clear existing thread_status
                mailboxes = _supabase.table('mailboxes').select('id').eq(
                    'client_id', client_id
                ).execute()
                for m in (mailboxes.data or []):
                    _supabase.table('thread_status').delete().eq('mailbox_id', m['id']).execute()
                _supabase.table('thread_status').delete().is_('mailbox_id', 'null').execute()

                tracker = ThreadTracker(client_id=client_id)
                tracker.evaluate_threads()
                logger.info("Thread resolution + recompute complete")
            else:
                logger.info("Skipping thread_status recompute (skip_recompute=true)")

        background_tasks.add_task(_run)
        mode = f"mailbox {mailbox_id}" if mailbox_id else "all mailboxes"
        return {"status": "started", "message": f"Resolving threads for {mode} in background"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/extraction/recompute-threads")
async def recompute_threads(
    client_id: str = Query(...),
    background_tasks: BackgroundTasks = None,
):
    """Recompute thread statuses for a client (across all mailboxes).

    Runs only the thread tracking step — no full extraction.
    Clears ALL existing thread_status rows for this client and rebuilds from scratch.
    Progress stored in Redis for frontend polling via GET /extraction/thread-recompute-progress.
    """
    try:
        import redis, json as _json
        redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379')
        _redis = redis.from_url(redis_url, decode_responses=True)
        progress_key = f"thread_recompute:{client_id}"

        def _set_progress(phase: str, pct: int, message: str):
            _redis.setex(progress_key, 600, _json.dumps({
                'phase': phase, 'pct': pct, 'message': message,
                'timestamp': datetime.utcnow().isoformat(),
            }))

        def _run_recompute():
            from ..services.thread_tracker import ThreadTracker

            try:
                _set_progress('clearing', 5, 'Clearing existing thread data...')

                mailboxes = _supabase.table('mailboxes').select('id').eq(
                    'client_id', client_id
                ).execute()
                mb_ids = [m['id'] for m in (mailboxes.data or [])]
                for m_id in mb_ids:
                    _supabase.table('thread_status').delete().eq('mailbox_id', m_id).execute()
                _supabase.table('thread_status').delete().is_('mailbox_id', 'null').not_.is_(
                    'customer_company_id', 'null'
                ).execute()

                _set_progress('evaluating', 15, f'Evaluating threads across {len(mb_ids)} mailboxes...')

                tracker = ThreadTracker(client_id=client_id)
                # Hook into tracker to report progress
                _original_save = tracker.save_thread_statuses
                _saved_total = [0]

                def _progress_save(statuses):
                    result = _original_save(statuses)
                    _saved_total[0] += len(statuses)
                    _set_progress('saving', min(90, 15 + int(_saved_total[0] / 100)),
                                  f'Saved {_saved_total[0]} threads...')
                    return result

                tracker.save_thread_statuses = _progress_save
                tracker.evaluate_threads()

                # Check for mailbox errors
                mb_errors = getattr(tracker, '_mailbox_errors', [])
                if mb_errors:
                    error_summary = '; '.join(
                        f"Mailbox {e['mailbox_id'][:8]}… failed at {e['emails_fetched']} emails"
                        for e in mb_errors
                    )
                    _set_progress('completed_with_errors', 100,
                                  f'Done — {_saved_total[0]} threads. {len(mb_errors)} mailbox(es) had errors: {error_summary}')
                    # Store detailed errors for the health page
                    import json as _json2
                    _redis.setex(f"thread_recompute_errors:{client_id}", 86400,
                                 _json2.dumps(mb_errors))
                else:
                    _set_progress('completed', 100, f'Done — {_saved_total[0]} threads computed')

                logger.info(f"Thread recompute complete: {_saved_total[0]} threads for client {client_id}"
                            f"{f', {len(mb_errors)} mailbox errors' if mb_errors else ''}")

            except Exception as e:
                _set_progress('failed', 0, f'Error: {str(e)[:200]}')
                logger.error(f"Thread recompute failed: {e}")

        background_tasks.add_task(_run_recompute)
        return {"status": "started", "message": "Recomputing threads client-wide in background"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/extraction/thread-recompute-progress")
async def get_thread_recompute_progress(client_id: str = Query(...)):
    """Poll progress of a running thread recompute job. Includes mailbox errors if any."""
    try:
        import redis, json as _json
        redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379')
        _redis = redis.from_url(redis_url, decode_responses=True)
        data = _redis.get(f"thread_recompute:{client_id}")
        if data:
            result = _json.loads(data)
            # Attach detailed errors if present
            errors_data = _redis.get(f"thread_recompute_errors:{client_id}")
            if errors_data:
                result['mailbox_errors'] = _json.loads(errors_data)
            return result
        return {'phase': 'idle', 'pct': 0, 'message': 'No active recompute'}
    except Exception:
        return {'phase': 'idle', 'pct': 0, 'message': 'No active recompute'}


@router.post("/extraction/re-resolve-threads")
async def re_resolve_threads(
    client_id: str = Query(...),
    background_tasks: BackgroundTasks = None,
):
    """Full thread re-resolve: clear canonical IDs, re-run resolver, rebuild thread_status.

    Use when threads are incorrectly split (e.g., Re: variants not merged).
    This is a heavy operation (~30-40 min for 250K+ emails).
    Progress stored in Redis for frontend polling via GET /extraction/thread-recompute-progress.
    """
    try:
        import redis, json as _json
        redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379')
        _redis = redis.from_url(redis_url, decode_responses=True)
        progress_key = f"thread_recompute:{client_id}"

        existing = _redis.get(progress_key)
        if existing:
            data = _json.loads(existing)
            if data.get('phase') in ('clearing', 'resolving', 'evaluating', 'saving'):
                return {"status": "already_running", "message": "Thread re-resolve already in progress"}

        def _set_progress(phase: str, pct: int, message: str):
            _redis.setex(progress_key, 1800, _json.dumps({
                'phase': phase, 'pct': pct, 'message': message,
                'timestamp': datetime.utcnow().isoformat(),
            }))

        def _run_re_resolve():
            import time as _time
            from ..services.canonical_thread_resolver import CanonicalThreadResolver
            from ..services.thread_tracker import ThreadTracker

            try:
                _set_progress('clearing', 5, 'Clearing canonical thread IDs...')

                mailboxes = _supabase.table('mailboxes').select('id').eq(
                    'client_id', client_id
                ).execute()
                mb_ids = [m['id'] for m in (mailboxes.data or [])]

                # Phase 1: Clear canonical_thread_ids via exec_sql (avoids REST timeout)
                CLEAR_BATCH = 500
                total_cleared = 0
                for mb_id in mb_ids:
                    while True:
                        try:
                            _supabase.rpc('exec_sql', {'query': f"""
                                UPDATE emails SET
                                    canonical_thread_id = NULL,
                                    thread_match_method = NULL,
                                    thread_match_confidence = NULL
                                WHERE id IN (
                                    SELECT id FROM emails
                                    WHERE mailbox_id = '{mb_id}'
                                      AND canonical_thread_id IS NOT NULL
                                    LIMIT {CLEAR_BATCH}
                                )
                            """}).execute()
                        except Exception as e:
                            logger.warning(f"Clear batch retry for {mb_id}: {e}")
                            _time.sleep(2)
                            continue

                        # Check remaining
                        check = _supabase.table("emails").select(
                            "id", count="exact"
                        ).eq("mailbox_id", mb_id).not_.is_(
                            "canonical_thread_id", "null"
                        ).limit(0).execute()
                        remaining = check.count or 0
                        total_cleared += CLEAR_BATCH
                        if remaining == 0:
                            break
                        if total_cleared % 5000 == 0:
                            _set_progress('clearing', min(25, 5 + int(total_cleared / 12000)),
                                          f'Cleared ~{total_cleared:,} emails...')

                _set_progress('resolving', 30, f'Cleared {total_cleared:,}. Running thread resolver...')
                logger.info(f"Re-resolve: cleared {total_cleared} canonical IDs for client {client_id}")

                # Phase 2: Run resolver
                resolver = CanonicalThreadResolver(client_id=client_id)
                stats = resolver.resolve_all()
                _set_progress('evaluating', 70,
                              f"Resolved {stats.get('total_emails', 0):,} emails into "
                              f"{stats.get('canonical_threads', 0):,} threads. Rebuilding statuses...")
                logger.info(f"Re-resolve: resolver done — {stats}")

                # Phase 3: Clear and rebuild thread_status
                for m_id in mb_ids:
                    _supabase.table('thread_status').delete().eq('mailbox_id', m_id).execute()

                tracker = ThreadTracker(client_id=client_id)
                _original_save = tracker.save_thread_statuses
                _saved_total = [0]

                def _progress_save(statuses):
                    result = _original_save(statuses)
                    _saved_total[0] += len(statuses)
                    _set_progress('saving', min(95, 70 + int(_saved_total[0] / 500)),
                                  f'Saved {_saved_total[0]:,} thread statuses...')
                    return result

                tracker.save_thread_statuses = _progress_save
                tracker.evaluate_threads()

                _set_progress('completed', 100,
                              f'Done — {stats.get("canonical_threads", 0):,} threads, '
                              f'{_saved_total[0]:,} statuses. '
                              f'T1={stats.get("tier1_message_id", 0)}, '
                              f'T2={stats.get("tier2_references", 0)}, '
                              f'T3={stats.get("tier3_subject", 0)}')
                logger.info(f"Re-resolve complete for client {client_id}: "
                            f"{_saved_total[0]} thread statuses saved")

            except Exception as e:
                _set_progress('failed', 0, f'Error: {str(e)[:300]}')
                logger.error(f"Thread re-resolve failed: {e}", exc_info=True)

        background_tasks.add_task(_run_re_resolve)
        return {"status": "started", "message": "Full thread re-resolve started (~30-40 min for 250K emails)"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/extraction/backfill-email-links")
async def backfill_email_contact_links(
    client_id: str = Query(...),
    background_tasks: BackgroundTasks = None,  # noqa: injected by FastAPI
):
    """Backfill email_contact_links junction table for all mailboxes of a client.

    Only runs email linking (Step 9) with junction table creation — no full extraction.
    Processes ALL emails (force_relink=True) to capture CC/BCC recipients.
    """
    try:
        # Get all mailboxes for this client
        mailboxes = _supabase.table('mailboxes').select('id').eq(
            'client_id', client_id
        ).execute()
        mailbox_ids = [m['id'] for m in (mailboxes.data or [])]

        if not mailbox_ids:
            raise HTTPException(status_code=404, detail="No mailboxes found for this client")

        def _run_backfill():
            """Process all emails in pages, creating junction links directly.

            Does NOT re-run full email linking — just reads existing emails
            and creates email_contact_links rows for all participants.
            """
            from ..services.email_linker import EmailLinker
            from ..database.supabase_client import SupabaseClient

            sb = SupabaseClient.get_client(use_service_key=True)
            total_links = 0
            PAGE_SIZE = 500
            BATCH_SIZE = 100

            for i, mb_id in enumerate(mailbox_ids, 1):
                try:
                    logger.info(f"Backfill junction links: mailbox {i}/{len(mailbox_ids)} ({mb_id})")

                    # Init linker just for its caches
                    linker = EmailLinker(mailbox_id=mb_id, client_id=client_id)
                    linker._load_contact_cache()
                    linker._load_company_cache()

                    # Page through emails for this mailbox
                    offset = 0
                    mb_links = 0
                    while True:
                        try:
                            resp = sb.table('emails').select(
                                'id, sender_email, recipients, cc_list, bcc_list, is_outbound'
                            ).eq('mailbox_id', mb_id).order(
                                'sent_date', desc=False
                            ).range(offset, offset + PAGE_SIZE - 1).execute()
                        except Exception as e:
                            logger.warning(f"Backfill page fetch failed at offset {offset}: {e}")
                            break

                        rows = resp.data or []
                        if not rows:
                            break

                        # Build junction link rows
                        batch: list[dict] = []
                        for email in rows:
                            eid = email['id']

                            # Sender
                            sender = email.get('sender_email')
                            if sender:
                                addr = sender.strip().lower()
                                cid = linker._contact_cache.get(addr)
                                comp = linker._contact_company_cache.get(cid) if cid else None
                                if not comp:
                                    domain = linker._extract_domain(addr)
                                    comp = linker._company_cache.get(domain) if domain else None
                                batch.append({
                                    'email_id': eid, 'email_address': addr, 'role': 'sender',
                                    'contact_id': cid, 'company_id': comp, 'client_id': client_id,
                                })

                            # TO, CC, BCC
                            for role, field in [('to', 'recipients'), ('cc', 'cc_list'), ('bcc', 'bcc_list')]:
                                for r in (email.get(field) or []):
                                    addr = (r.get('email') if isinstance(r, dict) else r if isinstance(r, str) else None)
                                    if not addr or '@' not in addr:
                                        continue
                                    addr = addr.strip().lower()
                                    cid = linker._contact_cache.get(addr)
                                    comp = linker._contact_company_cache.get(cid) if cid else None
                                    if not comp:
                                        domain = linker._extract_domain(addr)
                                        comp = linker._company_cache.get(domain) if domain else None
                                    batch.append({
                                        'email_id': eid, 'email_address': addr, 'role': role,
                                        'contact_id': cid, 'company_id': comp, 'client_id': client_id,
                                    })

                        # Deduplicate within batch (same email+address+role can appear if address listed twice)
                        seen = set()
                        deduped = []
                        for row in batch:
                            key = (row['email_id'], row['email_address'], row['role'])
                            if key not in seen:
                                seen.add(key)
                                deduped.append(row)
                        batch = deduped

                        # Upsert batch
                        for j in range(0, len(batch), BATCH_SIZE):
                            chunk = batch[j:j + BATCH_SIZE]
                            try:
                                sb.table('email_contact_links').upsert(
                                    chunk, on_conflict='email_id,email_address,role'
                                ).execute()
                                mb_links += len(chunk)
                            except Exception as e:
                                logger.warning(f"Junction upsert failed: {e}")

                        offset += len(rows)
                        if offset % 5000 == 0:
                            logger.info(f"  Mailbox {i}: {offset} emails processed, {mb_links} links")

                    total_links += mb_links
                    logger.info(f"Mailbox {i}/{len(mailbox_ids)} complete: {mb_links} junction links")

                except Exception as e:
                    logger.error(f"Backfill failed for mailbox {mb_id}: {e}")

            logger.info(f"Backfill complete: {total_links} total junction links across {len(mailbox_ids)} mailboxes")

            # Update contact + company email counts from junction table
            logger.info("Updating email counts from junction table...")
            try:
                result1 = sb.rpc('update_contact_email_counts_from_junction', {
                    'p_client_id': client_id,
                }).execute()
                logger.info(f"Contact email counts updated: {result1.data}")
                result2 = sb.rpc('update_company_email_counts_from_junction', {
                    'p_client_id': client_id,
                }).execute()
                logger.info(f"Company email counts updated: {result2.data}")
            except Exception as e:
                logger.warning(f"RPC update_contact_email_counts failed, doing manual update: {e}")
                # Fallback: manual per-contact update
                offset = 0
                updated = 0
                while True:
                    contacts_page = sb.table('customer_contacts').select(
                        'id'
                    ).eq('client_id', client_id).range(offset, offset + 999).execute()
                    rows = contacts_page.data or []
                    if not rows:
                        break
                    for ct in rows:
                        try:
                            ecl = sb.table('email_contact_links').select(
                                'email_id'
                            ).eq('contact_id', ct['id']).execute()
                            email_ids = list({r['email_id'] for r in (ecl.data or [])})
                            total = len(email_ids)
                            if total == 0:
                                offset += len(rows)
                                continue
                            sent = 0
                            for i in range(0, len(email_ids), 500):
                                batch = email_ids[i:i + 500]
                                s = sb.table('emails').select('id', count='exact').in_(
                                    'id', batch
                                ).eq('is_outbound', True).limit(0).execute()
                                sent += s.count or 0
                            sb.table('customer_contacts').update({
                                'total_emails_sent': sent,
                                'total_emails_received': total - sent,
                            }).eq('id', ct['id']).execute()
                            updated += 1
                        except Exception:
                            pass
                    offset += len(rows)
                    if updated % 500 == 0 and updated > 0:
                        logger.info(f"Contact count update progress: {updated} updated")
                logger.info(f"Contact email counts updated: {updated} contacts")

        background_tasks.add_task(_run_backfill)
        return {
            "status": "started",
            "message": f"Backfilling email links for {len(mailbox_ids)} mailboxes in background",
            "mailbox_count": len(mailbox_ids),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/extraction/jobs/{job_id}", response_model=ExtractionJobDetail)
async def get_extraction_job(job_id: str):
    """
    Get extraction job details by ID.

    Args:
        job_id: Extraction job UUID

    Returns:
        Detailed extraction job record
    """
    try:
        result = _supabase.table('extraction_jobs').select('*').eq('id', job_id).single().execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Extraction job not found")

        job = result.data

        # Calculate duration if completed
        duration = None
        if job.get('completed_at') and job.get('started_at'):
            started = datetime.fromisoformat(job['started_at'].replace('Z', '+00:00'))
            completed = datetime.fromisoformat(job['completed_at'].replace('Z', '+00:00'))
            duration = (completed - started).total_seconds()

        return ExtractionJobDetail(
            **job,
            duration_seconds=duration
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get extraction job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/extraction/jobs", response_model=ExtractionJobListResponse)
async def list_extraction_jobs(
    client_id: Optional[str] = Query(default=None),
    mailbox_id: Optional[str] = Query(default=None),
    status: Optional[ExtractionStatus] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0)
):
    """
    List extraction jobs with filters.

    Args:
        client_id: Filter by client
        mailbox_id: Filter by mailbox
        status: Filter by status
        limit: Maximum number of results
        offset: Offset for pagination

    Returns:
        List of extraction jobs
    """
    try:
        query = _supabase.table('extraction_jobs').select('*')

        if client_id:
            query = query.eq('client_id', client_id)
        if mailbox_id:
            query = query.eq('mailbox_id', mailbox_id)
        if status:
            query = query.eq('status', status.value)

        result = query.order('started_at', desc=True).range(offset, offset + limit - 1).execute()

        # Get total count
        count_query = _supabase.table('extraction_jobs').select('id', count='exact')
        if client_id:
            count_query = count_query.eq('client_id', client_id)
        if mailbox_id:
            count_query = count_query.eq('mailbox_id', mailbox_id)
        if status:
            count_query = count_query.eq('status', status.value)
        count_result = count_query.execute()
        total = count_result.count if count_result.count else len(count_result.data)

        return ExtractionJobListResponse(
            jobs=[ExtractionJobResponse(**job) for job in result.data],
            total=total
        )

    except Exception as e:
        logger.error(f"Failed to list extraction jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/extraction/jobs/{job_id}/cancel")
async def cancel_extraction_job(job_id: str):
    """
    Cancel a running extraction job.

    Args:
        job_id: Extraction job UUID

    Returns:
        Success message
    """
    try:
        # Check if job exists and is cancellable
        job_check = _supabase.table('extraction_jobs').select('id, status').eq(
            'id', job_id
        ).single().execute()

        if not job_check.data:
            raise HTTPException(status_code=404, detail="Extraction job not found")

        if job_check.data['status'] not in ['pending', 'processing']:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot cancel job with status '{job_check.data['status']}'"
            )

        # Update status to failed with cancellation message
        _supabase.table('extraction_jobs').update({
            'status': 'failed',
            'errors': ['Job cancelled by user'],
            'updated_at': datetime.utcnow().isoformat()
        }).eq('id', job_id).execute()

        return {
            "message": "Extraction job cancelled successfully",
            "job_id": job_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel extraction job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/extraction/progress/{job_id}", response_model=ExtractionProgressResponse)
async def get_extraction_progress(job_id: str):
    """
    Get real-time extraction progress from Redis.

    Args:
        job_id: Extraction job UUID

    Returns:
        Real-time progress information
    """
    try:
        from ..database.redis_client import JobProgressManager

        # Try Redis first for real-time progress
        try:
            redis_manager = JobProgressManager()
            progress = redis_manager.get_progress(job_id)

            if progress:
                return ExtractionProgressResponse(
                    job_id=job_id,
                    **progress
                )
        except Exception as e:
            logger.warning(f"Redis unavailable, falling back to database: {e}")

        # Fallback to database
        result = _supabase.table('extraction_jobs').select(
            'status, current_step, current_step_number, total_steps, mailbox_id, client_id, errors'
        ).eq('id', job_id).single().execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Extraction job not found")

        job = result.data

        return ExtractionProgressResponse(
            job_id=job_id,
            status=job['status'],
            current_step=job.get('current_step'),
            current_step_number=job.get('current_step_number'),
            total_steps=job.get('total_steps'),
            mailbox_id=job.get('mailbox_id'),
            client_id=job.get('client_id'),
            error=job.get('errors', [None])[0] if job.get('errors') else None
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get extraction progress: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# CONTACT ANALYTICS ENDPOINTS (6 endpoints)
# ============================================================================

CONTACT_SORT_COLUMNS = {
    'engagement_score', 'full_name', 'email_address',
    'total_emails_sent', 'total_emails_received',
    'last_contacted_at', 'created_at', 'company_name',
    'qb_quotes_count', 'qb_tier', 'qb_customer_type',
}

COMPANY_SORT_COLUMNS = {
    'engagement_score', 'company_name', 'total_emails',
    'contact_count', 'decision_maker_count',
    'last_contact_date', 'created_at',
    'qb_total_revenue', 'qb_tier', 'qb_growth_90d',
    'qb_customer_type', 'qb_days_since_last_invoice',
}

THREAD_SORT_COLUMNS = {
    'last_message_at', 'message_count', 'days_since_last_email',
    'status', 'created_at', 'subject', 'qb_link_count',
}


@router.get("/contacts", response_model=ContactAnalyticsListResponse)
async def list_contact_analytics(
    client_id: Optional[str] = Query(default=None),
    company_id: Optional[str] = Query(default=None),
    contact_type: Optional[ContactType] = Query(default=None),
    is_decision_maker: Optional[bool] = Query(default=None),
    min_engagement_score: Optional[float] = Query(default=None, ge=0, le=100),
    qb_linked: Optional[bool] = Query(default=None, description="Filter contacts linked to QB customers"),
    customer_type: Optional[str] = Query(default=None, description="Filter by QB customer_status prefix (e.g. 'Active' matches 'Active A Customer')"),
    search: Optional[str] = Query(default=None, description="Search by name, email, or company"),
    sort_by: Optional[str] = Query(default=None, description="Sort column"),
    sort_dir: str = Query(default="desc", description="asc or desc"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0)
):
    """List contacts with analytics data."""
    try:
        query = _supabase.table('customer_contacts').select(
            '''
            id, email_address, full_name, job_title, company_name,
            customer_company_id, client_id, contact_type,
            is_decision_maker, seniority_level,
            engagement_score, total_emails_sent, total_emails_received,
            first_contacted_at, last_contacted_at,
            initiation_ratio, reply_rate, avg_response_time_seconds, avg_thread_depth,
            created_at, updated_at,
            qb_customer_type, qb_tier, qb_quotes_count, qb_last_quote_date,
            customer_companies!customer_contacts_customer_company_id_fkey(company_name)
            '''
        )

        if client_id:
            query = query.eq('client_id', client_id)
        if company_id:
            query = query.eq('customer_company_id', company_id)
        if contact_type:
            query = query.eq('contact_type', contact_type.value)
        if is_decision_maker is not None:
            # Use lowercase string for boolean filter (PostgREST requirement)
            query = query.eq('is_decision_maker', 'true' if is_decision_maker else 'false')
        if min_engagement_score is not None:
            query = query.gte('engagement_score', int(min_engagement_score))
        if qb_linked is True:
            query = query.not_.is_('qb_customer_type', 'null')
        if customer_type and customer_type.strip():
            ct_term = _sanitize_search_term(customer_type.strip())
            query = query.ilike('qb_customer_type', f'{ct_term}%')
        if search and search.strip():
            term = _sanitize_search_term(search.strip())
            query = query.or_(f"full_name.ilike.%{term}%,email_address.ilike.%{term}%,company_name.ilike.%{term}%")

        effective_sort = sort_by if sort_by in CONTACT_SORT_COLUMNS else 'engagement_score'
        desc = sort_dir.lower() != 'asc'
        result = query.order(effective_sort, desc=desc, nullsfirst=False).range(offset, offset + limit - 1).execute()

        # Batch lookup persona + quote metrics from contact_persona view
        contact_ids = [c['id'] for c in result.data]
        persona_map: dict[str, dict] = {}
        if contact_ids:
            try:
                for i in range(0, len(contact_ids), 500):
                    batch_ids = contact_ids[i:i+500]
                    persona_result = _supabase.table('contact_persona').select(
                        'contact_id, persona_classification, strike_rate, accepted_quote_count, total_job_value'
                    ).in_('contact_id', batch_ids).execute()
                    for p in (persona_result.data or []):
                        persona_map[p['contact_id']] = p
            except Exception as e:
                logger.warning(f"Persona lookup failed (non-critical): {e}")

        contacts = []
        for c in result.data:
            customer_company_name = None
            if c.get('customer_companies'):
                customer_company_name = c['customer_companies'].get('company_name')

            pm = persona_map.get(c['id']) or {}
            contacts.append(ContactAnalytics(
                **c,
                customer_company_name=customer_company_name,
                persona_classification=pm.get('persona_classification'),
                strike_rate=pm.get('strike_rate'),
                accepted_quote_count=pm.get('accepted_quote_count'),
                total_job_value=pm.get('total_job_value'),
            ))

        # Get total count
        count_query = _supabase.table('customer_contacts').select('id', count='exact')
        if client_id:
            count_query = count_query.eq('client_id', client_id)
        if company_id:
            count_query = count_query.eq('customer_company_id', company_id)
        if contact_type:
            count_query = count_query.eq('contact_type', contact_type.value)
        if is_decision_maker is not None:
            count_query = count_query.eq('is_decision_maker', 'true' if is_decision_maker else 'false')
        if min_engagement_score is not None:
            count_query = count_query.gte('engagement_score', int(min_engagement_score))
        if qb_linked is True:
            count_query = count_query.not_.is_('qb_customer_type', 'null')
        if customer_type and customer_type.strip():
            ct_term = _sanitize_search_term(customer_type.strip())
            count_query = count_query.ilike('qb_customer_type', f'{ct_term}%')
        if search and search.strip():
            term = _sanitize_search_term(search.strip())
            count_query = count_query.or_(f"full_name.ilike.%{term}%,email_address.ilike.%{term}%,company_name.ilike.%{term}%")

        count_result = count_query.execute()
        total = count_result.count if count_result.count else len(count_result.data)

        return ContactAnalyticsListResponse(contacts=contacts, total=total)

    except Exception as e:
        logger.error(f"Failed to list contact analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/contacts/top-engaged", response_model=List[TopEngagedContact])
async def get_top_engaged_contacts(
    client_id: Optional[str] = Query(default=None),
    limit: int = Query(default=10, ge=1, le=100)
):
    """
    Get top engaged contacts.

    Args:
        client_id: Filter by client
        limit: Number of results (default 10)

    Returns:
        List of top engaged contacts
    """
    try:
        query = _supabase.table('customer_contacts').select(
            'id, email_address, full_name, company_name, engagement_score, total_emails_sent, total_emails_received, last_contacted_at, qb_customer_type, qb_tier'
        ).not_.is_('engagement_score', 'null')

        if client_id:
            query = query.eq('client_id', client_id)

        result = query.order('engagement_score', desc=True).limit(limit).execute()

        return [
            TopEngagedContact(
                id=c['id'],
                email_address=c['email_address'],
                full_name=c.get('full_name'),
                company_name=c.get('company_name'),
                engagement_score=c['engagement_score'],
                total_emails=(c.get('total_emails_sent', 0) or 0) + (c.get('total_emails_received', 0) or 0),
                last_contacted_at=c.get('last_contacted_at')
            )
            for c in result.data
        ]

    except Exception as e:
        logger.error(f"Failed to get top engaged contacts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/contacts/at-risk", response_model=List[AtRiskContact])
async def get_at_risk_contacts(
    client_id: Optional[str] = Query(default=None),
    days_threshold: int = Query(default=60, ge=1),
    limit: int = Query(default=50, ge=1, le=500)
):
    """
    Get at-risk contacts (no contact in N days).

    Args:
        client_id: Filter by client
        days_threshold: Days since last contact (default 60)
        limit: Maximum number of results

    Returns:
        List of at-risk contacts
    """
    try:
        cutoff_date = (datetime.utcnow() - timedelta(days=days_threshold)).isoformat()
        now = datetime.utcnow()

        # Get contacts with old last_contacted_at
        query = _supabase.table('customer_contacts').select(
            'id, email_address, full_name, company_name, last_contacted_at, engagement_score, qb_total_revenue, qb_tier'
        ).not_.is_('last_contacted_at', 'null').lte('last_contacted_at', cutoff_date)

        if client_id:
            query = query.eq('client_id', client_id)

        result = query.order('last_contacted_at').limit(limit).execute()

        # Also get contacts with NULL last_contacted_at (never contacted = at risk)
        null_query = _supabase.table('customer_contacts').select(
            'id, email_address, full_name, company_name, last_contacted_at, engagement_score, qb_total_revenue, qb_tier'
        ).is_('last_contacted_at', 'null')

        if client_id:
            null_query = null_query.eq('client_id', client_id)

        null_result = null_query.limit(limit).execute()

        at_risk = []
        # Contacts with null last_contacted_at first (most at-risk)
        for c in (null_result.data or []):
            at_risk.append(AtRiskContact(
                id=c['id'],
                email_address=c['email_address'],
                full_name=c.get('full_name'),
                company_name=c.get('company_name'),
                last_contacted_at=None,
                days_since_contact=999,
                engagement_score=c.get('engagement_score')
            ))

        for c in (result.data or []):
            last_contact = datetime.fromisoformat(c['last_contacted_at'].replace('Z', '+00:00'))
            days_since = (now - last_contact.replace(tzinfo=None)).days

            at_risk.append(AtRiskContact(
                id=c['id'],
                email_address=c['email_address'],
                full_name=c.get('full_name'),
                company_name=c.get('company_name'),
                last_contacted_at=c['last_contacted_at'],
                days_since_contact=days_since,
                engagement_score=c.get('engagement_score')
            ))

        return at_risk[:limit]

    except Exception as e:
        logger.error(f"Failed to get at-risk contacts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/contacts/decision-makers", response_model=ContactAnalyticsListResponse)
async def get_decision_makers(
    client_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0)
):
    """
    Get decision makers only.

    Args:
        client_id: Filter by client
        limit: Maximum number of results
        offset: Offset for pagination

    Returns:
        List of decision maker contacts
    """
    try:
        query = _supabase.table('customer_contacts').select(
            '''
            id, email_address, full_name, job_title, company_name,
            customer_company_id, client_id, contact_type,
            is_decision_maker, seniority_level,
            engagement_score, total_emails_sent, total_emails_received,
            first_contacted_at, last_contacted_at,
            created_at, updated_at,
            customer_companies!customer_contacts_customer_company_id_fkey(company_name)
            '''
        ).eq('is_decision_maker', 'true')  # Use lowercase string

        if client_id:
            query = query.eq('client_id', client_id)

        result = query.order('engagement_score', desc=True).range(offset, offset + limit - 1).execute()

        contacts = []
        for c in result.data:
            customer_company_name = None
            if c.get('customer_companies'):
                customer_company_name = c['customer_companies'].get('company_name')

            contacts.append(ContactAnalytics(**c, customer_company_name=customer_company_name))

        # Get total count
        count_query = _supabase.table('customer_contacts').select('id', count='exact').eq('is_decision_maker', 'true')
        if client_id:
            count_query = count_query.eq('client_id', client_id)
        count_result = count_query.execute()
        total = count_result.count if count_result.count else len(count_result.data)

        return ContactAnalyticsListResponse(contacts=contacts, total=total)

    except Exception as e:
        logger.error(f"Failed to get decision makers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/contacts/by-type", response_model=List[ContactTypeGrouping])
async def group_contacts_by_type(client_id: Optional[str] = Query(default=None)):
    """
    Group contacts by contact type.

    Args:
        client_id: Filter by client

    Returns:
        Contact counts grouped by type
    """
    try:
        # Fetch all contacts for this client
        query = _supabase.table('customer_contacts').select('contact_type, engagement_score')

        if client_id:
            query = query.eq('client_id', client_id)

        result = query.execute()

        # Group by type in memory
        from collections import defaultdict
        type_groups = defaultdict(lambda: {'count': 0, 'scores': []})

        for c in result.data:
            contact_type = c.get('contact_type', 'unknown')
            type_groups[contact_type]['count'] += 1
            if c.get('engagement_score') is not None:
                type_groups[contact_type]['scores'].append(c['engagement_score'])

        # Calculate averages and build response
        groupings = []
        for contact_type, data in type_groups.items():
            avg_score = None
            if data['scores']:
                avg_score = sum(data['scores']) / len(data['scores'])

            groupings.append(ContactTypeGrouping(
                contact_type=ContactType(contact_type),
                count=data['count'],
                avg_engagement_score=avg_score
            ))

        return sorted(groupings, key=lambda x: x.count, reverse=True)

    except Exception as e:
        logger.error(f"Failed to group contacts by type: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# NOTE: Parameterized route MUST be after all static /contacts/* routes to avoid
# FastAPI matching "top-engaged", "at-risk", etc. as {contact_identifier}
@router.get("/contacts/{contact_identifier}", response_model=ContactAnalytics)
async def get_contact_analytics(contact_identifier: str):
    """
    Get single contact with full analytics.

    Args:
        contact_identifier: Contact UUID or email address

    Returns:
        Contact with analytics data
    """
    try:
        # Check if identifier is an email (contains @) or UUID
        if '@' in contact_identifier:
            # Query by email address
            filter_field = 'email_address'
            filter_value = contact_identifier
        else:
            # Query by UUID
            filter_field = 'id'
            filter_value = contact_identifier

        result = _supabase.table('customer_contacts').select(
            '''
            id, email_address, full_name, job_title, company_name,
            customer_company_id, client_id, contact_type,
            is_decision_maker, seniority_level,
            engagement_score, total_emails_sent, total_emails_received,
            first_contacted_at, last_contacted_at,
            initiation_ratio, reply_rate, avg_response_time_seconds, avg_thread_depth,
            created_at, updated_at,
            qb_customer_type, qb_tier, qb_quotes_count, qb_last_quote_date,
            customer_companies!customer_contacts_customer_company_id_fkey(company_name)
            '''
        ).eq(filter_field, filter_value).single().execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Contact not found")

        c = result.data
        customer_company_name = None
        if c.get('customer_companies'):
            customer_company_name = c['customer_companies'].get('company_name')

        # Check if this contact is linked to a QB contact
        qb_contact_id = None
        try:
            qb_link = _supabase.table('qb_contacts').select('qb_record_id').eq(
                'matched_contact_id', c['id']
            ).limit(1).execute()
            if qb_link.data:
                qb_contact_id = qb_link.data[0].get('qb_record_id')
        except Exception:
            pass

        # Live email counts from junction table (includes CC/BCC)
        try:
            ecl_count = _supabase.table('email_contact_links').select(
                'email_id', count='exact'
            ).eq('contact_id', c['id']).limit(0).execute()
            junction_total = ecl_count.count or 0

            if junction_total > 0:
                # Get distinct email IDs
                ecl_resp = _supabase.table('email_contact_links').select('email_id').eq('contact_id', c['id']).execute()
                email_ids = list({r['email_id'] for r in (ecl_resp.data or [])})
                live_total = len(email_ids)

                live_sent = 0
                for i in range(0, len(email_ids), 500):
                    batch = email_ids[i:i + 500]
                    sent_resp = _supabase.table('emails').select(
                        'id', count='exact'
                    ).in_('id', batch).eq('is_outbound', True).limit(0).execute()
                    live_sent += sent_resp.count or 0

                c['total_emails_sent'] = live_sent
                c['total_emails_received'] = live_total - live_sent
        except Exception:
            pass  # Keep stored values if junction table fails

        return ContactAnalytics(**c, customer_company_name=customer_company_name, qb_contact_id=qb_contact_id)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get contact analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/contacts/{contact_id}/emails")
async def get_contact_emails(contact_id: str, limit: int = 50, offset: int = 0):
    """Get emails linked to a contact via email_contact_links junction table.

    Falls back to emails.customer_contact_id if junction table not populated yet.
    The junction table includes emails where this contact is sender, TO, CC, or BCC.
    """
    try:
        # Try junction table first (includes CC/BCC)
        total = 0
        try:
            junction_count = _supabase.table('email_contact_links').select(
                'email_id', count='exact'
            ).eq('contact_id', contact_id).limit(0).execute()
            total = junction_count.count or 0
        except Exception:
            pass

        if total > 0:
            # Get distinct email IDs from junction table
            junction_resp = _supabase.table('email_contact_links').select(
                'email_id'
            ).eq('contact_id', contact_id).execute()
            email_ids = list({r['email_id'] for r in (junction_resp.data or [])})
            total = len(email_ids)

            # Count outbound
            total_sent = 0
            for i in range(0, len(email_ids), 500):
                batch = email_ids[i:i + 500]
                sent_resp = _supabase.table('emails').select(
                    'id', count='exact'
                ).in_('id', batch).eq('is_outbound', True).limit(0).execute()
                total_sent += sent_resp.count or 0
            total_received = total - total_sent

            # Paginated emails
            page_ids = email_ids[offset:offset + limit] if email_ids else []
            if page_ids:
                result = _supabase.table('emails').select(
                    'id, subject, sender_email, sender_name, sent_date, folder_path, is_outbound'
                ).in_('id', page_ids).order('sent_date', desc=True).execute()
                paginated = result.data or []
            else:
                paginated = []
        else:
            total = 0
            total_sent = 0
            total_received = 0
            paginated = []

        return {'emails': paginated, 'total': total, 'total_sent': total_sent, 'total_received': total_received}

    except Exception as e:
        logger.error(f"Failed to get contact emails: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# COMPANY ANALYTICS ENDPOINTS (5 endpoints)
# ============================================================================

@router.get("/companies/filter-options")
async def get_company_filter_options(client_id: str = Query(...)):
    """Get distinct values for company filter dropdowns (Tier, Account Manager)."""
    try:
        tiers = set()
        ams = set()
        offset = 0
        while True:
            resp = _supabase.table('customer_companies').select(
                'qb_tier, qb_account_manager'
            ).eq('client_id', client_id).not_.is_(
                'qb_customer_id', 'null'
            ).range(offset, offset + 999).execute()
            rows = resp.data or []
            if not rows:
                break
            for r in rows:
                if r.get('qb_tier'):
                    tiers.add(r['qb_tier'])
                if r.get('qb_account_manager'):
                    ams.add(r['qb_account_manager'])
            offset += len(rows)

        return {
            'tiers': sorted(tiers),
            'account_managers': sorted(ams),
        }
    except Exception as e:
        logger.error(f"Failed to get filter options: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/companies", response_model=CompanyAnalyticsListResponse)
async def list_company_analytics(
    client_id: Optional[str] = Query(default=None),
    engagement_status: Optional[EngagementStatus] = Query(default=None),
    min_engagement_score: Optional[float] = Query(default=None, ge=0, le=100),
    has_activity: Optional[bool] = Query(default=None, description="Filter to companies with emails > 0"),
    qb_matched: Optional[bool] = Query(default=None, description="Filter companies matched to QB customers"),
    qb_tier: Optional[str] = Query(default=None, description="Filter by QB tier (e.g. 'Level 1')"),
    qb_account_manager: Optional[str] = Query(default=None, description="Filter by account manager name"),
    search: Optional[str] = Query(default=None, description="Search by company name or industry"),
    sort_by: Optional[str] = Query(default=None, description="Sort column"),
    sort_dir: str = Query(default="desc", description="asc or desc"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0)
):
    """List companies with analytics data."""
    try:
        query = _supabase.table('customer_companies').select(
            '''
            id, company_name, client_id, email_domains, industry,
            engagement_score, total_emails, total_inbound, total_outbound,
            first_contact_date, last_contact_date,
            contact_count, decision_maker_count,
            created_at, updated_at,
            qb_customer_id, qb_match_method, qb_customer_type, qb_tier, qb_total_revenue, qb_invoiced_ty, qb_invoiced_ly, qb_growth_90d, qb_days_since_last_invoice, qb_account_manager,
            clients(client_name)
            '''
        )

        if client_id:
            query = query.eq('client_id', client_id)
        if has_activity is True:
            query = query.gte('total_emails', 1)
        if min_engagement_score is not None:
            query = query.gte('engagement_score', int(min_engagement_score))
        if qb_matched is True:
            query = query.not_.is_('qb_customer_id', 'null')
        if qb_tier:
            query = query.ilike('qb_tier', f'{qb_tier}%')
        if qb_account_manager:
            query = query.eq('qb_account_manager', qb_account_manager)
        if search and search.strip():
            term = _sanitize_search_term(search.strip())
            query = query.or_(f"company_name.ilike.%{term}%,industry.ilike.%{term}%")

        effective_sort = sort_by if sort_by in COMPANY_SORT_COLUMNS else 'engagement_score'
        desc = sort_dir.lower() != 'asc'
        result = query.order(effective_sort, desc=desc, nullsfirst=False).range(offset, offset + limit - 1).execute()

        # Calculate engagement status for each company
        def calculate_engagement_status(last_contact_date):
            if not last_contact_date:
                return EngagementStatus.UNKNOWN

            if isinstance(last_contact_date, str):
                last_contact_date = datetime.fromisoformat(last_contact_date.replace('Z', '+00:00'))

            now = datetime.utcnow()
            days_since = (now - last_contact_date.replace(tzinfo=None)).days

            if days_since <= 30:
                return EngagementStatus.ACTIVE
            elif days_since <= 90:
                return EngagementStatus.QUIET
            else:
                return EngagementStatus.AT_RISK

        companies = []
        for comp in result.data:
            status = calculate_engagement_status(comp.get('last_contact_date'))

            # Apply engagement_status filter
            if engagement_status and status != engagement_status:
                continue

            client_name = None
            if comp.get('clients'):
                client_name = comp['clients'].get('client_name')

            companies.append(CompanyAnalytics(
                **comp,
                engagement_status=status,
                client_name=client_name
            ))

        # Get total count
        # engagement_status is computed in Python (not a DB column), so when
        # that filter is active the DB count is unreliable — use len(companies).
        if engagement_status:
            total = len(companies)
        else:
            count_query = _supabase.table('customer_companies').select('id', count='exact')
            if client_id:
                count_query = count_query.eq('client_id', client_id)
            if has_activity is True:
                count_query = count_query.gte('total_emails', 1)
            if min_engagement_score is not None:
                count_query = count_query.gte('engagement_score', int(min_engagement_score))
            if qb_matched is True:
                count_query = count_query.not_.is_('qb_customer_id', 'null')
            if qb_tier:
                count_query = count_query.ilike('qb_tier', f'{qb_tier}%')
            if qb_account_manager:
                count_query = count_query.eq('qb_account_manager', qb_account_manager)
            if search and search.strip():
                term = _sanitize_search_term(search.strip())
                count_query = count_query.or_(f"company_name.ilike.%{term}%,industry.ilike.%{term}%")
            count_result = count_query.execute()
            total = count_result.count if count_result.count else len(count_result.data)

        return CompanyAnalyticsListResponse(companies=companies, total=total)

    except Exception as e:
        logger.error(f"Failed to list company analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/companies/top-engaged", response_model=List[TopEngagedCompany])
async def get_top_engaged_companies(
    client_id: Optional[str] = Query(default=None),
    limit: int = Query(default=10, ge=1, le=100)
):
    """
    Get top engaged companies.

    Args:
        client_id: Filter by client
        limit: Number of results (default 10)

    Returns:
        List of top engaged companies
    """
    try:
        query = _supabase.table('customer_companies').select(
            'id, company_name, engagement_score, total_emails, contact_count, last_contact_date, qb_tier, qb_total_revenue'
        ).not_.is_('engagement_score', 'null')

        if client_id:
            query = query.eq('client_id', client_id)

        result = query.order('engagement_score', desc=True).limit(limit).execute()

        return [
            TopEngagedCompany(
                id=comp['id'],
                company_name=comp['company_name'],
                engagement_score=comp['engagement_score'],
                total_emails=comp.get('total_emails', 0) or 0,
                contact_count=comp.get('contact_count', 0) or 0,
                last_contact_date=comp.get('last_contact_date')
            )
            for comp in result.data
        ]

    except Exception as e:
        logger.error(f"Failed to get top engaged companies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/companies/at-risk", response_model=List[AtRiskCompany])
async def get_at_risk_companies(
    client_id: Optional[str] = Query(default=None),
    days_threshold: int = Query(default=90, ge=1),
    limit: int = Query(default=50, ge=1, le=500)
):
    """
    Get at-risk companies (no contact in N days).

    Args:
        client_id: Filter by client
        days_threshold: Days since last contact (default 90)
        limit: Maximum number of results

    Returns:
        List of at-risk companies
    """
    try:
        cutoff_date = (datetime.utcnow() - timedelta(days=days_threshold)).isoformat()
        now = datetime.utcnow()

        # Companies with old last_contact_date
        query = _supabase.table('customer_companies').select(
            'id, company_name, last_contact_date, contact_count, engagement_score, qb_total_revenue, qb_days_since_last_invoice, qb_tier'
        ).not_.is_('last_contact_date', 'null').lte('last_contact_date', cutoff_date)

        if client_id:
            query = query.eq('client_id', client_id)

        result = query.order('last_contact_date').limit(limit).execute()

        # Also get companies with NULL last_contact_date (never contacted = at risk)
        null_query = _supabase.table('customer_companies').select(
            'id, company_name, last_contact_date, contact_count, engagement_score, qb_total_revenue, qb_days_since_last_invoice, qb_tier'
        ).is_('last_contact_date', 'null')

        if client_id:
            null_query = null_query.eq('client_id', client_id)

        null_result = null_query.limit(limit).execute()

        at_risk = []
        # Companies with null last_contact_date first (most at-risk)
        for comp in (null_result.data or []):
            at_risk.append(AtRiskCompany(
                id=comp['id'],
                company_name=comp['company_name'],
                last_contact_date=None,
                days_since_contact=999,
                contact_count=comp.get('contact_count', 0) or 0,
                engagement_score=comp.get('engagement_score')
            ))

        for comp in (result.data or []):
            last_contact = datetime.fromisoformat(comp['last_contact_date'].replace('Z', '+00:00'))
            days_since = (now - last_contact.replace(tzinfo=None)).days

            at_risk.append(AtRiskCompany(
                id=comp['id'],
                company_name=comp['company_name'],
                last_contact_date=comp['last_contact_date'],
                days_since_contact=days_since,
                contact_count=comp.get('contact_count', 0) or 0,
                engagement_score=comp.get('engagement_score')
            ))

        return at_risk[:limit]

    except Exception as e:
        logger.error(f"Failed to get at-risk companies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/companies/by-engagement", response_model=List[EngagementStatusGrouping])
async def group_companies_by_engagement(client_id: Optional[str] = Query(default=None)):
    """
    Group companies by engagement status.

    Args:
        client_id: Filter by client

    Returns:
        Company counts grouped by engagement status
    """
    try:
        query = _supabase.table('customer_companies').select('last_contact_date, engagement_score')

        if client_id:
            query = query.eq('client_id', client_id)

        result = query.execute()

        # Calculate engagement status and group
        from collections import defaultdict
        status_groups = defaultdict(lambda: {'count': 0, 'scores': []})

        def calculate_engagement_status(last_contact_date):
            if not last_contact_date:
                return EngagementStatus.UNKNOWN

            if isinstance(last_contact_date, str):
                last_contact_date = datetime.fromisoformat(last_contact_date.replace('Z', '+00:00'))

            now = datetime.utcnow()
            days_since = (now - last_contact_date.replace(tzinfo=None)).days

            if days_since <= 30:
                return EngagementStatus.ACTIVE
            elif days_since <= 90:
                return EngagementStatus.QUIET
            else:
                return EngagementStatus.AT_RISK

        for comp in result.data:
            status = calculate_engagement_status(comp.get('last_contact_date'))
            status_groups[status.value]['count'] += 1
            if comp.get('engagement_score') is not None:
                status_groups[status.value]['scores'].append(comp['engagement_score'])

        # Build response
        groupings = []
        for status, data in status_groups.items():
            avg_score = None
            if data['scores']:
                avg_score = sum(data['scores']) / len(data['scores'])

            groupings.append(EngagementStatusGrouping(
                engagement_status=EngagementStatus(status),
                count=data['count'],
                avg_engagement_score=avg_score
            ))

        return sorted(groupings, key=lambda x: x.count, reverse=True)

    except Exception as e:
        logger.error(f"Failed to group companies by engagement: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# NOTE: Parameterized route MUST be after all static /companies/* routes to avoid
# FastAPI matching "top-engaged", "at-risk", etc. as {company_id}
@router.get("/companies/{company_id}", response_model=CompanyAnalytics)
async def get_company_analytics(company_id: str):
    """
    Get single company with full analytics.

    Args:
        company_id: Company UUID

    Returns:
        Company with analytics data
    """
    try:
        result = _supabase.table('customer_companies').select(
            '''id, company_name, client_id, email_domains, industry,
            engagement_score, total_emails, total_inbound, total_outbound,
            first_contact_date, last_contact_date,
            contact_count, decision_maker_count,
            created_at, updated_at,
            qb_customer_id, qb_customer_code, qb_match_method, qb_matched_at,
            qb_customer_type, qb_tier, qb_total_revenue, qb_invoiced_ty, qb_invoiced_ly, qb_growth_90d, qb_days_since_last_invoice, qb_account_manager'''
        ).eq('id', company_id).limit(1).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Company not found")

        comp = result.data[0]

        # Calculate engagement status
        def calculate_engagement_status(last_contact_date):
            if not last_contact_date:
                return EngagementStatus.UNKNOWN

            if isinstance(last_contact_date, str):
                last_contact_date = datetime.fromisoformat(last_contact_date.replace('Z', '+00:00'))

            now = datetime.utcnow()
            days_since = (now - last_contact_date.replace(tzinfo=None)).days

            if days_since <= 30:
                return EngagementStatus.ACTIVE
            elif days_since <= 90:
                return EngagementStatus.QUIET
            else:
                return EngagementStatus.AT_RISK

        status = calculate_engagement_status(comp.get('last_contact_date'))

        client_name = None
        if comp.get('client_id'):
            try:
                cl = _supabase.table('clients').select('client_name').eq('id', comp['client_id']).limit(1).execute()
                if cl.data:
                    client_name = cl.data[0].get('client_name')
            except Exception:
                pass

        # Live contact count — authoritative. Do NOT fall back to the stored
        # aggregate: when the true live count is 0 (e.g. contacts re-pointed to
        # a canonical company during dedup), a `live or stored` fallback would
        # resurrect a stale value and disagree with the drilldown.
        try:
            live_contacts = _supabase.table('customer_contacts').select(
                'id', count='exact'
            ).eq('customer_company_id', company_id).limit(0).execute()
            comp['contact_count'] = live_contacts.count or 0

            dm_contacts = _supabase.table('customer_contacts').select(
                'id', count='exact'
            ).eq('customer_company_id', company_id).eq('is_decision_maker', True).limit(0).execute()
            comp['decision_maker_count'] = dm_contacts.count or 0
        except Exception as e:
            logger.warning(f"Live contact-count query failed for company {company_id}: {e}")

        # Thread counts: active + overdue
        active_threads = 0
        overdue_threads = 0
        try:
            threads_result = _supabase.table('thread_status').select(
                'id, status'
            ).eq('customer_company_id', company_id).execute()
            for t in (threads_result.data or []):
                s = (t.get('status') or '').lower()
                if s in ('ongoing', 'awaiting_response', 'awaiting_our_response',
                         'outbound_pending', 'awaiting_reply'):
                    active_threads += 1
                elif s == 'overdue':
                    overdue_threads += 1
        except Exception:
            pass

        # QB capability tags from Unique Emails
        # customer_companies.qb_customer_id = qb_customers.qb_record_id (field 3, e.g. "44050")
        # qb_unique_emails.qb_customer_id = QB "Customer ID (key)" (field 92, e.g. "28035")
        # Join through qb_customers: qb_record_id → customer_key_id → qb_unique_emails.qb_customer_id
        qb_capabilities, qb_processes, qb_embellishments = [], [], []
        qb_cid = comp.get('qb_customer_id')
        if qb_cid:
            try:
                # Translate qb_record_id → customer_key_id (field 92) via qb_customers
                key_resp = _supabase.table('qb_customers').select(
                    'customer_key_id'
                ).eq('client_id', comp['client_id']).eq(
                    'qb_record_id', qb_cid
                ).limit(1).execute()
                qb_key_id = (key_resp.data[0].get('customer_key_id') or '') if key_resp.data else ''

                if qb_key_id:
                    ue_resp = _supabase.table('qb_unique_emails').select(
                        'capabilities_used, processes_used, embellishments_used'
                    ).eq('client_id', comp['client_id']).eq(
                        'qb_customer_id', qb_key_id
                    ).eq('hide', False).execute()
                else:
                    ue_resp = type('R', (), {'data': []})()
                caps_set, procs_set, emb_set = set(), set(), set()
                for r in (ue_resp.data or []):
                    for v in (r.get('capabilities_used') or '').split('|'):
                        v = v.strip()
                        if v:
                            caps_set.add(v)
                    for v in (r.get('processes_used') or '').split('|'):
                        v = v.strip()
                        if v:
                            procs_set.add(v)
                    for v in (r.get('embellishments_used') or '').split('|'):
                        v = v.strip()
                        if v:
                            emb_set.add(v)
                qb_capabilities = sorted(caps_set)
                qb_processes = sorted(procs_set)
                qb_embellishments = sorted(emb_set)
            except Exception:
                pass

        return CompanyAnalytics(
            **comp,
            engagement_status=status,
            client_name=client_name,
            active_threads=active_threads,
            overdue_threads=overdue_threads,
            qb_capabilities=qb_capabilities or None,
            qb_processes=qb_processes or None,
            qb_embellishments=qb_embellishments or None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get company analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/companies/{company_id}/emails")
async def get_company_emails(company_id: str, limit: int = 50, offset: int = 0):
    """Get emails linked to a company via email_contact_links junction table.

    Falls back to emails.customer_company_id if junction table not populated yet.
    The junction table includes TO, CC, and BCC recipients — giving accurate counts.
    """
    try:
        # Try junction table first (includes CC/BCC)
        try:
            # Get distinct email IDs linked to this company
            junction_count = _supabase.table('email_contact_links').select(
                'email_id', count='exact'
            ).eq('company_id', company_id).limit(0).execute()
            total = junction_count.count or 0
        except Exception:
            total = 0

        if total > 0:
            # Junction table has data — use it
            # Count sent (outbound) via join: get email_ids, then count outbound
            junction_emails = _supabase.table('email_contact_links').select(
                'email_id'
            ).eq('company_id', company_id).execute()
            email_ids = list({r['email_id'] for r in (junction_emails.data or [])})
            total = len(email_ids)

            total_sent = 0
            for i in range(0, len(email_ids), 500):
                batch = email_ids[i:i + 500]
                sent_resp = _supabase.table('emails').select(
                    'id', count='exact'
                ).in_('id', batch).eq('is_outbound', True).limit(0).execute()
                total_sent += sent_resp.count or 0
            total_received = total - total_sent

            # Fetch paginated emails
            page_ids = email_ids[offset:offset + limit] if email_ids else []
            if page_ids:
                result = _supabase.table('emails').select(
                    'id, subject, sender_email, sender_name, sent_date, folder_path, is_outbound'
                ).in_('id', page_ids).order('sent_date', desc=True).execute()
                paginated = result.data or []
            else:
                paginated = []
        else:
            total = 0
            total_sent = 0
            total_received = 0
            paginated = []

        return {'emails': paginated, 'total': total, 'total_sent': total_sent, 'total_received': total_received}

    except Exception as e:
        logger.error(f"Failed to get company emails: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# THREAD ANALYTICS ENDPOINTS (4 endpoints)
# ============================================================================

# Map database thread status values to ThreadStatus enum
# DB: complete, awaiting_reply, overdue, dropped, outbound_pending, stale
# Enum: complete, awaiting_response, awaiting_our_response, overdue, dropped, ongoing
_THREAD_STATUS_MAP = {
    'complete': ThreadStatus.COMPLETE,
    'awaiting_reply': ThreadStatus.AWAITING_RESPONSE,
    'overdue': ThreadStatus.OVERDUE,
    'dropped': ThreadStatus.DROPPED,
    'outbound_pending': ThreadStatus.AWAITING_OUR_RESPONSE,
    'stale': ThreadStatus.DROPPED,
    'ongoing': ThreadStatus.ONGOING,
    # Also accept enum values directly
    'awaiting_response': ThreadStatus.AWAITING_RESPONSE,
    'awaiting_our_response': ThreadStatus.AWAITING_OUR_RESPONSE,
}

def _map_thread_status(db_status: str) -> ThreadStatus:
    return _THREAD_STATUS_MAP.get(db_status, ThreadStatus.COMPLETE)

@router.get("/threads/status", response_model=ThreadStatusListResponse)
async def list_thread_statuses(
    client_id: Optional[str] = Query(default=None),
    mailbox_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None, description="Thread status filter (or 'active' for ongoing+awaiting_our_response)"),
    intent: Optional[str] = Query(default=None, description="Filter by intent_status"),
    has_qb_links: Optional[bool] = Query(default=None, description="Filter to threads with QB links"),
    search: Optional[str] = Query(default=None, description="Search by thread subject"),
    sort_by: Optional[str] = Query(default=None, description="Sort column"),
    sort_dir: str = Query(default="desc", description="asc or desc"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0)
):
    """List thread statuses with filters."""
    try:
        query = _supabase.table('thread_status').select(
            '''
            thread_id, canonical_thread_id, subject, customer_contact_id, customer_company_id,
            status, message_count, last_message_at, last_sender_is_outbound, days_since_last_email,
            mailbox_id, qb_customer_type, qb_customer_tier,
            intent_status, intent_override_reason, last_email_intent, last_email_urgency, last_email_sentiment,
            created_at, qb_link_count
            '''
        )

        # Apply client_id filter via mailbox_id lookup
        mailbox_ids = []
        if client_id:
            mailbox_result = _supabase.table('mailboxes').select('id').eq('client_id', client_id).execute()
            mailbox_ids = [m['id'] for m in (mailbox_result.data or [])]
            if mailbox_ids:
                # Include both mailbox-specific and client-wide (NULL mailbox_id) threads
                mb_filter = ','.join(f"mailbox_id.eq.{mid}" for mid in mailbox_ids[:100])
                query = query.or_(f"{mb_filter},mailbox_id.is.null")
            else:
                return ThreadStatusListResponse(threads=[], total=0)
        elif mailbox_id:
            query = query.eq('mailbox_id', mailbox_id)

        # Status filter: map frontend enum values to all possible DB values.
        # The `status` column holds the EFFECTIVE status post-override (migration 077).
        # It can hold both timing-derived values (ongoing, awaiting_*, overdue, ...)
        # AND override values (urgent, revenue_opportunity, closing, escalation).
        # Composite keys (active, needs_attention) expand to multiple actual values.
        _STATUS_DB_VALUES = {
            # Composite: threads the user should look at (in-progress + override-flagged)
            'active': [
                'ongoing', 'awaiting_our_response', 'stale', 'outbound_pending',
                'urgent', 'revenue_opportunity', 'escalation',
            ],
            # Composite: threads that need attention RIGHT NOW (override-flagged only)
            'needs_attention': ['urgent', 'escalation'],

            # Timing-derived
            'ongoing': ['ongoing', 'stale'],
            'awaiting_response': ['awaiting_response', 'awaiting_reply'],
            'awaiting_our_response': ['awaiting_our_response', 'outbound_pending'],
            'overdue': ['overdue'],
            'complete': ['complete', 'closing'],   # 'closing' = naturally concluding; folded under Complete
            'dropped': ['dropped'],

            # Override-derived (each is its own filter value)
            'urgent': ['urgent'],
            'revenue_opportunity': ['revenue_opportunity'],
            'closing': ['closing'],
            'escalation': ['escalation'],
        }
        status_db_values = None
        if status:
            status_key = status.value if hasattr(status, 'value') else status
            status_db_values = _STATUS_DB_VALUES.get(status_key, [status_key])
            if len(status_db_values) == 1:
                query = query.eq('status', status_db_values[0])
            else:
                query = query.in_('status', status_db_values)
        if intent and intent.strip():
            query = query.eq('intent_status', intent.strip())
        if search and search.strip():
            term = _sanitize_search_term(search.strip())
            query = query.ilike('subject', f'%{term}%')

        # has_qb_links: pre-fetch linked canonical_thread_ids, then filter main query.
        # MUST use .in_() not .or_() — supabase-py's .or_() uses params.update()
        # which silently replaces any prior .or_() (the mailbox filter above).
        linked_thread_ids: list | None = None
        if has_qb_links:
            link_client_id = client_id
            if not link_client_id and mailbox_id:
                mb_r = _supabase.table('mailboxes').select('client_id').eq('id', mailbox_id).limit(1).execute()
                link_client_id = mb_r.data[0]['client_id'] if mb_r.data else None
            if not link_client_id:
                logger.warning("has_qb_links: no client_id available, returning empty")
                return ThreadStatusListResponse(threads=[], total=0)

            lq = _supabase.table('thread_qb_links').select('canonical_thread_id').eq('client_id', link_client_id).execute()
            linked_thread_ids = list({r['canonical_thread_id'] for r in (lq.data or []) if r.get('canonical_thread_id')})
            logger.info(f"has_qb_links: {len(linked_thread_ids)} linked thread IDs for client {link_client_id[:8]}...")

            if not linked_thread_ids:
                return ThreadStatusListResponse(threads=[], total=0)

            query = query.in_('canonical_thread_id', linked_thread_ids[:500])

        effective_sort = sort_by if sort_by in THREAD_SORT_COLUMNS else 'last_message_at'
        desc = sort_dir.lower() != 'asc'
        result = query.order(effective_sort, desc=desc, nullsfirst=False).range(offset, offset + limit - 1).execute()

        # Batch-fetch contacts and companies (not N+1)
        contact_ids = list(set(t['customer_contact_id'] for t in result.data if t.get('customer_contact_id')))
        company_ids = list(set(t['customer_company_id'] for t in result.data if t.get('customer_company_id')))

        contact_map = {}
        if contact_ids:
            try:
                cr = _supabase.table('customer_contacts').select('id, email_address, full_name').in_('id', contact_ids[:500]).execute()
                contact_map = {c['id']: c for c in (cr.data or [])}
            except Exception:
                pass

        company_map = {}
        if company_ids:
            try:
                cr = _supabase.table('customer_companies').select('id, company_name').in_('id', company_ids[:500]).execute()
                company_map = {c['id']: c for c in (cr.data or [])}
            except Exception:
                pass

        # Two-pass dedup to eliminate cross-mailbox duplicates:
        #  Pass 1: by canonical_thread_id (exact thread merge)
        #  Pass 2: by normalized subject + contact (catches same conversation across mailboxes)
        import re as _re
        _SUBJECT_STRIP = _re.compile(r'^(re|fwd?|fw):\s*', _re.IGNORECASE)

        def _norm_subject(s: str | None) -> str:
            if not s:
                return ''
            cleaned = _SUBJECT_STRIP.sub('', s.strip()).strip().lower()
            # Strip again for multiple prefixes like "Re: Fwd: ..."
            while _SUBJECT_STRIP.match(cleaned):
                cleaned = _SUBJECT_STRIP.sub('', cleaned).strip()
            return cleaned

        def _merge_thread(existing: dict, new_row: dict) -> dict:
            """Keep the row with higher message count, or most recent date."""
            existing_count = existing.get('message_count', 0) or 0
            new_count = new_row.get('message_count', 0) or 0
            if new_count > existing_count:
                return new_row
            if new_count == existing_count:
                if (new_row.get('last_message_at') or '') > (existing.get('last_message_at') or ''):
                    return new_row
            return existing

        # Pass 1: dedup by canonical_thread_id
        canon_map: dict[str, dict] = {}
        no_canon: list[dict] = []
        for t in result.data:
            canon = t.get('canonical_thread_id') or ''
            if canon:
                if canon in canon_map:
                    canon_map[canon] = _merge_thread(canon_map[canon], t)
                else:
                    canon_map[canon] = t
            else:
                no_canon.append(t)

        after_pass1 = list(canon_map.values()) + no_canon

        # Pass 2: dedup by normalized subject + contact_id (catches cross-mailbox same conversation)
        seen_threads: dict[str, dict] = {}
        for t in after_pass1:
            subj_norm = _norm_subject(t.get('subject'))
            contact_id = t.get('customer_contact_id') or ''
            company_id = t.get('customer_company_id') or ''
            # Key: subject + contact (or subject + company if no contact)
            dedup_key = f"{subj_norm}|{contact_id or company_id}"

            if dedup_key in seen_threads:
                seen_threads[dedup_key] = _merge_thread(seen_threads[dedup_key], t)
            else:
                seen_threads[dedup_key] = t

        threads = []
        for t in seen_threads.values():
            thread_data = {
                'thread_id': t.get('canonical_thread_id') or t.get('thread_id'),
                'subject': t.get('subject'),
                'contact_id': t.get('customer_contact_id'),
                'company_id': t.get('customer_company_id'),
                'status': _map_thread_status(t.get('status', 'complete')),
                'total_messages': t.get('message_count', 0),
                'last_message_date': t.get('last_message_at'),
                'last_sender_type': 'outbound' if t.get('last_sender_is_outbound') else 'inbound',
                'days_since_last_message': t.get('days_since_last_email', 0),
                # Intent intelligence
                'intent_status': t.get('intent_status'),
                'intent_override_reason': t.get('intent_override_reason'),
                'last_email_intent': t.get('last_email_intent'),
                'last_email_urgency': t.get('last_email_urgency'),
                'last_email_sentiment': t.get('last_email_sentiment'),
                'created_at': t.get('created_at')
            }

            thread = ThreadStatusSummary(**thread_data)

            # Enrich from batch-fetched lookups
            contact = contact_map.get(t.get('customer_contact_id'))
            if contact:
                thread.contact_email = contact.get('email_address')
                thread.contact_name = contact.get('full_name')

            company = company_map.get(t.get('customer_company_id'))
            if company:
                thread.company_name = company.get('company_name')

            threads.append(thread)

        # Batch-fetch QB links for all threads in one query
        canon_ids = [t.thread_id for t in threads if t.thread_id]
        qb_link_map: dict = {}
        if canon_ids:
            try:
                for i in range(0, len(canon_ids), 100):
                    batch = canon_ids[i:i + 100]
                    qb_resp = _supabase.table('thread_qb_links').select(
                        'canonical_thread_id, qb_reference, link_type'
                    ).in_('canonical_thread_id', batch).execute()
                    for ql in (qb_resp.data or []):
                        cid = ql['canonical_thread_id']
                        ref = ql.get('qb_reference') or ''
                        if cid not in qb_link_map:
                            qb_link_map[cid] = []
                        if ref and ref not in qb_link_map[cid]:
                            qb_link_map[cid].append(ref)
            except Exception:
                pass

        for thread in threads:
            refs = qb_link_map.get(thread.thread_id)
            if refs:
                thread.qb_links = refs

        # Get total count (same filters — must match main query exactly)
        count_query = _supabase.table('thread_status').select('thread_id', count='exact')
        if client_id and mailbox_ids:
            # Match main query: include both mailbox-specific AND null-mailbox threads
            mb_filter_count = ','.join(f"mailbox_id.eq.{mid}" for mid in mailbox_ids[:100])
            count_query = count_query.or_(f"{mb_filter_count},mailbox_id.is.null")
        elif mailbox_id:
            count_query = count_query.eq('mailbox_id', mailbox_id)
        if status and status_db_values:
            if len(status_db_values) == 1:
                count_query = count_query.eq('status', status_db_values[0])
            else:
                count_query = count_query.in_('status', status_db_values)
        if intent and intent.strip():
            count_query = count_query.eq('intent_status', intent.strip())
        if search and search.strip():
            term = _sanitize_search_term(search.strip())
            count_query = count_query.ilike('subject', f'%{term}%')
        if linked_thread_ids is not None:
            count_query = count_query.in_('canonical_thread_id', linked_thread_ids[:500])
        count_result = count_query.execute()
        total = count_result.count if count_result.count is not None else len(count_result.data or [])

        return ThreadStatusListResponse(threads=threads, total=total)

    except Exception as e:
        logger.error(f"Failed to list thread statuses: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/threads/overdue", response_model=List[OverdueThread])
async def get_overdue_threads(
    client_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500)
):
    """
    Get overdue threads only.

    Args:
        client_id: Filter by client
        limit: Maximum number of results

    Returns:
        List of overdue threads
    """
    try:
        query = _supabase.table('thread_status').select(
            'thread_id, subject, customer_contact_id, customer_company_id, last_message_at, days_since_last_email, qb_customer_type, qb_customer_tier'
        ).eq('status', ThreadStatus.OVERDUE.value)

        # Filter by client via mailbox_ids
        if client_id:
            mailbox_result = _supabase.table('mailboxes').select('id').eq('client_id', client_id).execute()
            mailbox_ids = [m['id'] for m in (mailbox_result.data or [])]
            if mailbox_ids:
                query = query.in_('mailbox_id', mailbox_ids[:500])
            else:
                return []

        result = query.order(
            'days_since_last_email', desc=True
        ).limit(limit).execute()

        threads = []
        for t in result.data:
            contact_email = None
            contact_name = None
            company_name = None

            # Enrich with contact info
            if t.get('customer_contact_id'):
                contact_result = _supabase.table('customer_contacts').select(
                    'email_address, full_name'
                ).eq('id', t['customer_contact_id']).execute()
                if contact_result.data:
                    contact_email = contact_result.data[0].get('email_address')
                    contact_name = contact_result.data[0].get('full_name')

            # Enrich with company name
            if t.get('customer_company_id'):
                company_result = _supabase.table('customer_companies').select(
                    'company_name'
                ).eq('id', t['customer_company_id']).execute()
                if company_result.data:
                    company_name = company_result.data[0].get('company_name')

            threads.append(OverdueThread(
                thread_id=t['thread_id'],
                subject=t.get('subject'),
                contact_email=contact_email,
                contact_name=contact_name,
                company_name=company_name,
                last_message_date=t.get('last_message_at'),  # Map database column to model field
                days_overdue=t.get('days_since_last_email', 0)
            ))

        return threads

    except Exception as e:
        logger.error(f"Failed to get overdue threads: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/threads/by-status", response_model=List[ThreadStatusCount])
async def count_threads_by_status(client_id: Optional[str] = Query(default=None)):
    """
    Count threads by status.

    Args:
        client_id: Filter by client

    Returns:
        Thread counts grouped by status
    """
    try:
        # Paginate to handle >1000 threads
        all_threads: list = []
        offset = 0
        while True:
            page = _supabase.table('thread_status').select('status').range(offset, offset + 999).execute()
            rows = page.data or []
            all_threads.extend(rows)
            if len(rows) == 0:
                break
            offset += len(rows)

        # Count by status in memory
        from collections import Counter
        status_counts = Counter()

        for t in all_threads:
            status = t.get('status', 'unknown')
            status_counts[status] += 1

        result_list = []
        for status, count in status_counts.items():
            enum_val = _map_thread_status(status)
            result_list.append(ThreadStatusCount(status=enum_val, count=count))

        return result_list

    except Exception as e:
        logger.error(f"Failed to count threads by status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/threads/by-contact/{contact_id}", response_model=ThreadStatusListResponse)
async def get_contact_threads(
    contact_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0)
):
    """
    Get all threads for a specific contact.

    Args:
        contact_id: Contact UUID
        limit: Maximum number of results
        offset: Offset for pagination

    Returns:
        List of thread statuses for contact
    """
    try:
        result = _supabase.table('thread_status').select(
            '''
            thread_id, subject, customer_contact_id, customer_company_id,
            status, message_count, last_message_at, last_sender_is_outbound, days_since_last_email,
            intent_status, intent_override_reason, last_email_intent, last_email_urgency, last_email_sentiment,
            created_at
            '''
        ).eq('customer_contact_id', contact_id).order(
            'last_message_at', desc=True
        ).range(offset, offset + limit - 1).execute()

        # Fetch contact/company info once
        contact_info = _supabase.table('customer_contacts').select(
            'email_address, full_name, customer_company_id, customer_companies!customer_contacts_customer_company_id_fkey(company_name)'
        ).eq('id', contact_id).single().execute()

        contact_email = None
        contact_name = None
        company_name = None

        if contact_info.data:
            contact_email = contact_info.data.get('email_address')
            contact_name = contact_info.data.get('full_name')
            if contact_info.data.get('customer_companies'):
                company_name = contact_info.data['customer_companies'].get('company_name')

        threads = []
        for t in result.data:
            # Map database column names to model field names
            thread_data = {
                'thread_id': t.get('canonical_thread_id') or t.get('thread_id'),
                'subject': t.get('subject'),
                'contact_id': t.get('customer_contact_id'),
                'company_id': t.get('customer_company_id'),
                'status': _map_thread_status(t.get('status', 'complete')),
                'total_messages': t.get('message_count', 0),
                'last_message_date': t.get('last_message_at'),
                'last_sender_type': 'outbound' if t.get('last_sender_is_outbound') else 'inbound',
                'days_since_last_message': t.get('days_since_last_email', 0),
                'intent_status': t.get('intent_status'),
                'intent_override_reason': t.get('intent_override_reason'),
                'last_email_intent': t.get('last_email_intent'),
                'last_email_urgency': t.get('last_email_urgency'),
                'last_email_sentiment': t.get('last_email_sentiment'),
                'created_at': t.get('created_at'),
                'contact_email': contact_email,
                'contact_name': contact_name,
                'company_name': company_name
            }
            threads.append(ThreadStatusSummary(**thread_data))

        # Get total count
        count_result = _supabase.table('thread_status').select(
            'thread_id', count='exact'
        ).eq('customer_contact_id', contact_id).execute()
        total = count_result.count if count_result.count else len(count_result.data)

        return ThreadStatusListResponse(threads=threads, total=total)

    except Exception as e:
        logger.error(f"Failed to get contact threads: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/threads/by-company/{company_id}", response_model=ThreadStatusListResponse)
async def get_company_threads(
    company_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0)
):
    """Get all threads for a specific company, deduplicated by canonical_thread_id."""
    try:
        result = _supabase.table('thread_status').select(
            '''
            thread_id, canonical_thread_id, subject, customer_contact_id, customer_company_id,
            status, message_count, last_message_at, last_sender_is_outbound, days_since_last_email,
            intent_status, intent_override_reason, last_email_intent, last_email_urgency, last_email_sentiment,
            created_at
            '''
        ).eq('customer_company_id', company_id).order(
            'last_message_at', desc=True
        ).range(offset, offset + limit - 1).execute()

        # Dedup pass 1: by canonical_thread_id
        # Dedup pass 2: by normalized subject (catches cross-mailbox duplicates with different canonical IDs)
        seen_threads: dict = {}
        seen_subjects: dict = {}  # normalized_subject → canonical key
        for t in (result.data or []):
            key = t.get('canonical_thread_id') or t.get('thread_id')
            # Normalize subject for secondary dedup
            subj_norm = (t.get('subject') or '').strip().lower()

            # Check if we already have a thread with the same subject
            if subj_norm and subj_norm in seen_subjects:
                key = seen_subjects[subj_norm]  # merge into existing

            if key not in seen_threads:
                seen_threads[key] = t
                if subj_norm:
                    seen_subjects[subj_norm] = key
            else:
                # Merge: keep higher message_count, most recent date
                existing = seen_threads[key]
                existing['message_count'] = max(
                    existing.get('message_count') or 0,
                    t.get('message_count') or 0
                )
                if (t.get('last_message_at') or '') > (existing.get('last_message_at') or ''):
                    existing['last_message_at'] = t['last_message_at']
                    existing['last_sender_is_outbound'] = t.get('last_sender_is_outbound')
                    existing['days_since_last_email'] = t.get('days_since_last_email')
                    existing['status'] = t.get('status')

        deduped = list(seen_threads.values())

        # Fetch company name once
        company_name = None
        company_result = _supabase.table('customer_companies').select('company_name').eq('id', company_id).execute()
        if company_result.data:
            company_name = company_result.data[0].get('company_name')

        # Batch-fetch contacts
        contact_ids = list(set(t['customer_contact_id'] for t in deduped if t.get('customer_contact_id')))
        contact_map = {}
        if contact_ids:
            try:
                for i in range(0, len(contact_ids), 500):
                    batch = contact_ids[i:i + 500]
                    cr = _supabase.table('customer_contacts').select('id, email_address, full_name').in_('id', batch).execute()
                    for c in (cr.data or []):
                        contact_map[c['id']] = c
            except Exception:
                pass

        threads = []
        for t in deduped:
            contact = contact_map.get(t.get('customer_contact_id'), {})
            thread_data = {
                'thread_id': t.get('canonical_thread_id') or t.get('thread_id'),
                'subject': t.get('subject'),
                'contact_id': t.get('customer_contact_id'),
                'company_id': t.get('customer_company_id'),
                'status': _map_thread_status(t.get('status', 'complete')),
                'total_messages': t.get('message_count', 0),
                'last_message_date': t.get('last_message_at'),
                'last_sender_type': 'outbound' if t.get('last_sender_is_outbound') else 'inbound',
                'days_since_last_message': t.get('days_since_last_email', 0),
                'intent_status': t.get('intent_status'),
                'intent_override_reason': t.get('intent_override_reason'),
                'last_email_intent': t.get('last_email_intent'),
                'last_email_urgency': t.get('last_email_urgency'),
                'last_email_sentiment': t.get('last_email_sentiment'),
                'created_at': t.get('created_at'),
                'company_name': company_name,
                'contact_email': contact.get('email_address'),
                'contact_name': contact.get('full_name'),
            }
            threads.append(ThreadStatusSummary(**thread_data))

        return ThreadStatusListResponse(threads=threads, total=len(threads))

    except Exception as e:
        logger.error(f"Failed to get company threads: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/threads/{thread_id}/emails", response_model=ThreadDetail)
async def get_thread_detail(
    thread_id: str,
    limit: int = Query(default=100, ge=1, le=500),
):
    """Get thread detail with all emails in the thread."""
    try:
        # Get thread_status record — try canonical_thread_id first, fall back to thread_id
        ts_result = _supabase.table('thread_status').select(
            '''
            thread_id, canonical_thread_id, subject, customer_contact_id, customer_company_id,
            status, message_count, last_message_at, days_since_last_email,
            thread_depth, created_at
            '''
        ).or_(f"thread_id.eq.{thread_id},canonical_thread_id.eq.{thread_id}").limit(1).execute()

        if not ts_result.data:
            raise HTTPException(status_code=404, detail="Thread not found")

        ts = ts_result.data[0]

        # Fetch emails by canonical_thread_id (cross-mailbox)
        canonical_id = ts.get('canonical_thread_id') or thread_id
        original_thread_id = ts.get('thread_id')
        subject = ts.get('subject', '')
        # body_text excluded here — fetched SQL-side truncated below (this view
        # only renders a 500-char preview, so the full body never crosses the wire).
        COLS = 'id, subject, sender_email, sender_name, recipients, sent_date, is_outbound, folder_path'

        all_emails: list = []
        seen_ids: set = set()

        # Source 1: canonical_thread_id match
        r1 = _supabase.table('emails').select(COLS).eq(
            'canonical_thread_id', canonical_id
        ).order('sent_date', desc=False).limit(limit).execute()
        for e in (r1.data or []):
            if e['id'] not in seen_ids:
                all_emails.append(e)
                seen_ids.add(e['id'])

        # Source 2: original thread_id match (emails not yet canonical-resolved)
        if original_thread_id and original_thread_id != canonical_id:
            r2 = _supabase.table('emails').select(COLS).eq(
                'thread_id', original_thread_id
            ).order('sent_date', desc=False).limit(limit).execute()
            for e in (r2.data or []):
                if e['id'] not in seen_ids:
                    all_emails.append(e)
                    seen_ids.add(e['id'])

        # Source 3: thread_id = canonical_id (thread tracker stored canonical UUID as thread_id)
        if not all_emails:
            r3 = _supabase.table('emails').select(COLS).eq(
                'thread_id', canonical_id
            ).order('sent_date', desc=False).limit(limit).execute()
            for e in (r3.data or []):
                if e['id'] not in seen_ids:
                    all_emails.append(e)
                    seen_ids.add(e['id'])

        # Source 4: sibling threads — same normalized subject, different canonical_thread_id
        # Finds emails from threads that should logically be merged (e.g., Re: variants)
        if subject and len(subject) >= 10:
            from ..services.canonical_thread_resolver import _normalize_subject
            norm_subj = _normalize_subject(subject)
            if norm_subj and len(norm_subj) >= 5:
                sibling_threads = _supabase.table('thread_status').select(
                    'canonical_thread_id'
                ).neq('canonical_thread_id', canonical_id).ilike(
                    'subject', f'%{norm_subj[:80]}%'
                ).limit(10).execute()
                sibling_ids = [s['canonical_thread_id'] for s in (sibling_threads.data or []) if s.get('canonical_thread_id')]
                for sib_id in sibling_ids:
                    r4 = _supabase.table('emails').select(COLS).eq(
                        'canonical_thread_id', sib_id
                    ).order('sent_date', desc=False).limit(limit).execute()
                    for e in (r4.data or []):
                        if e['id'] not in seen_ids:
                            all_emails.append(e)
                            seen_ids.add(e['id'])

        # Sort merged results
        all_emails.sort(key=lambda e: e.get('sent_date', ''))
        emails_result = type('R', (), {'data': all_emails})()

        # Fetch SQL-side-truncated bodies for the preview (501 chars so we can still
        # append the '...' truncation marker for bodies that were longer than 500).
        body_by_id: dict = {}
        email_ids = [e['id'] for e in all_emails if e.get('id')]
        if email_ids:
            body_resp = _supabase.rpc(
                'emails_body_left', {'email_ids': email_ids, 'n': 501}
            ).execute()
            body_by_id = {r['id']: (r.get('body') or '') for r in (body_resp.data or [])}

        thread_emails = []
        for e in (emails_result.data or []):
            # Truncate body_text for preview
            body = body_by_id.get(e['id'], '')
            if len(body) > 500:
                body = body[:500] + '...'
            thread_emails.append(ThreadEmail(
                id=e['id'],
                subject=e.get('subject'),
                sender_email=e.get('sender_email'),
                sender_name=e.get('sender_name'),
                recipients=e.get('recipients'),
                sent_date=e.get('sent_date'),
                is_outbound=e.get('is_outbound'),
                body_text=body,
                folder_path=e.get('folder_path'),
            ))

        # Enrich with contact/company names
        contact_email = None
        contact_name = None
        company_name = None

        if ts.get('customer_contact_id'):
            contact_result = _supabase.table('customer_contacts').select(
                'email_address, full_name'
            ).eq('id', ts['customer_contact_id']).execute()
            if contact_result.data:
                contact_email = contact_result.data[0].get('email_address')
                contact_name = contact_result.data[0].get('full_name')

        if ts.get('customer_company_id'):
            company_result = _supabase.table('customer_companies').select(
                'company_name'
            ).eq('id', ts['customer_company_id']).execute()
            if company_result.data:
                company_name = company_result.data[0].get('company_name')

        return ThreadDetail(
            thread_id=thread_id,
            subject=ts.get('subject'),
            status=_map_thread_status(ts.get('status', 'complete')),
            total_messages=len(thread_emails) or ts.get('message_count', 0),
            last_message_date=ts.get('last_message_at'),
            days_since_last_message=ts.get('days_since_last_email', 0),
            contact_id=ts.get('customer_contact_id'),
            contact_email=contact_email,
            contact_name=contact_name,
            company_id=ts.get('customer_company_id'),
            company_name=company_name,
            thread_depth=ts.get('thread_depth'),
            created_at=ts.get('created_at'),
            emails=thread_emails,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get thread detail: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# RESPONSE TIME ANALYTICS ENDPOINTS (4 endpoints)
# ============================================================================

@router.get("/response-times", response_model=ResponseTimeListResponse)
async def list_response_times(
    client_id: Optional[str] = Query(default=None),
    contact_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0)
):
    """
    List response time metrics with filters.

    Args:
        client_id: Filter by client
        contact_id: Filter by contact
        limit: Maximum number of results
        offset: Offset for pagination

    Returns:
        List of response time metrics
    """
    try:
        query = _supabase.table('email_response_metrics').select(
            '''
            id, email_id, responding_to_email_id, responder_contact_id, responder_company_id,
            response_time_seconds, business_hours_response_time_seconds, is_auto_reply, created_at, updated_at
            '''
        )

        if contact_id:
            query = query.eq('responder_contact_id', contact_id)

        result = query.order('created_at', desc=True).range(offset, offset + limit - 1).execute()

        # Enrich with contact email
        metrics = []
        for m in result.data:
            contact_email = None
            if m.get('responder_contact_id'):
                contact_result = _supabase.table('customer_contacts').select(
                    'email_address'
                ).eq('id', m['responder_contact_id']).execute()
                if contact_result.data:
                    contact_email = contact_result.data[0].get('email_address')

            metrics.append(ResponseTimeMetric(**m, contact_email=contact_email))

        # Get total count
        count_query = _supabase.table('email_response_metrics').select('id', count='exact')
        if contact_id:
            count_query = count_query.eq('responder_contact_id', contact_id)
        count_result = count_query.execute()
        total = count_result.count if count_result.count else len(count_result.data)

        return ResponseTimeListResponse(metrics=metrics, total=total)

    except Exception as e:
        logger.error(f"Failed to list response times: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/response-times/stats", response_model=ResponseTimeStats)
async def get_response_time_stats(
    client_id: Optional[str] = Query(default=None),
    contact_id: Optional[str] = Query(default=None)
):
    """
    Get aggregate response time statistics.

    Args:
        client_id: Filter by client
        contact_id: Filter by contact

    Returns:
        Aggregate statistics
    """
    try:
        query = _supabase.table('email_response_metrics').select(
            'response_time_seconds, business_hours_response_time_seconds, is_auto_reply, email_id'
        )

        if contact_id:
            query = query.eq('responder_contact_id', contact_id)

        result = query.execute()

        if not result.data:
            return ResponseTimeStats(
                total_responses=0,
                avg_response_time_hours=0,
                median_response_time_hours=None,
                min_response_time_hours=0,
                max_response_time_hours=0,
                avg_business_hours_response_time_hours=None,
                median_business_hours_response_time_hours=None,
                our_avg_response_time=None,
                their_avg_response_time=None,
                auto_reply_count=0,
                auto_reply_percentage=0
            )

        # Convert seconds to hours
        response_times_hours = [m['response_time_seconds'] / 3600.0 for m in result.data if m.get('response_time_seconds')]
        bh_times_hours = [m['business_hours_response_time_seconds'] / 3600.0 for m in result.data if m.get('business_hours_response_time_seconds')]
        auto_replies = sum(1 for m in result.data if m.get('is_auto_reply') is True)

        import statistics

        # Separate by direction if contact_id provided
        our_avg = None
        their_avg = None
        if contact_id and result.data:
            email_ids = [m['email_id'] for m in result.data if m.get('email_id') and m.get('is_auto_reply') is not True]
            if email_ids:
                # Fetch direction for responding emails (batch 500)
                direction_map = {}
                for i in range(0, len(email_ids), 500):
                    batch_ids = email_ids[i:i+500]
                    dir_result = _supabase.table('emails').select('id, is_outbound').in_('id', batch_ids).execute()
                    for e in (dir_result.data or []):
                        direction_map[e['id']] = e.get('is_outbound', False)

                our_times = []
                their_times = []
                for m in result.data:
                    if m.get('is_auto_reply') is True or not m.get('response_time_seconds'):
                        continue
                    is_outbound = direction_map.get(m['email_id'])
                    if is_outbound is True:
                        our_times.append(m['response_time_seconds'] / 3600.0)
                    elif is_outbound is False:
                        their_times.append(m['response_time_seconds'] / 3600.0)

                our_avg = statistics.mean(our_times) if our_times else None
                their_avg = statistics.mean(their_times) if their_times else None

        return ResponseTimeStats(
            total_responses=len(result.data),
            avg_response_time_hours=statistics.mean(response_times_hours) if response_times_hours else 0,
            median_response_time_hours=statistics.median(response_times_hours) if response_times_hours else None,
            min_response_time_hours=min(response_times_hours) if response_times_hours else 0,
            max_response_time_hours=max(response_times_hours) if response_times_hours else 0,
            avg_business_hours_response_time_hours=statistics.mean(bh_times_hours) if bh_times_hours else None,
            median_business_hours_response_time_hours=statistics.median(bh_times_hours) if bh_times_hours else None,
            our_avg_response_time=our_avg,
            their_avg_response_time=their_avg,
            auto_reply_count=auto_replies,
            auto_reply_percentage=(auto_replies / len(result.data) * 100) if result.data else 0
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get response time stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/response-times/slowest", response_model=List[SlowestResponder])
async def get_slowest_responders(
    client_id: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100)
):
    """
    Get slowest responders.

    Args:
        client_id: Filter by client
        limit: Number of results

    Returns:
        List of slowest responders
    """
    try:
        # Fetch response metrics
        query = _supabase.table('email_response_metrics').select(
            'responder_contact_id, response_time_seconds'
        ).not_.is_('responder_contact_id', 'null')

        result = query.execute()

        # Group by contact and calculate average
        from collections import defaultdict
        contact_times = defaultdict(list)

        for m in result.data:
            if m.get('response_time_seconds'):
                # Convert seconds to hours
                contact_times[m['responder_contact_id']].append(m['response_time_seconds'] / 3600.0)

        # Calculate averages
        contact_avgs = []
        for contact_id, times in contact_times.items():
            avg_time = sum(times) / len(times)
            contact_avgs.append((contact_id, avg_time, len(times)))

        # Sort by slowest
        contact_avgs.sort(key=lambda x: x[1], reverse=True)

        # Enrich with contact info
        slowest = []
        for contact_id, avg_time, count in contact_avgs[:limit]:
            contact_result = _supabase.table('customer_contacts').select(
                'email_address, full_name, company_name'
            ).eq('id', contact_id).execute()

            if contact_result.data:
                c = contact_result.data[0]
                slowest.append(SlowestResponder(
                    contact_id=contact_id,
                    contact_email=c['email_address'],
                    contact_name=c.get('full_name'),
                    company_name=c.get('company_name'),
                    avg_response_time_hours=avg_time,
                    response_count=count
                ))

        return slowest

    except Exception as e:
        logger.error(f"Failed to get slowest responders: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/response-times/by-contact/{contact_id}", response_model=ResponseTimeListResponse)
async def get_contact_response_history(
    contact_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0)
):
    """
    Get response time history for a specific contact.

    Args:
        contact_id: Contact UUID
        limit: Maximum number of results
        offset: Offset for pagination

    Returns:
        List of response time metrics for contact
    """
    try:
        result = _supabase.table('email_response_metrics').select(
            '''
            id, email_id, responding_to_email_id, responder_contact_id, responder_company_id,
            response_time_seconds, business_hours_response_time_seconds, is_auto_reply, created_at, updated_at
            '''
        ).eq('responder_contact_id', contact_id).order(
            'created_at', desc=True
        ).range(offset, offset + limit - 1).execute()

        # Fetch contact email once
        contact_result = _supabase.table('customer_contacts').select(
            'email_address'
        ).eq('id', contact_id).single().execute()

        contact_email = None
        if contact_result.data:
            contact_email = contact_result.data.get('email_address')

        metrics = [ResponseTimeMetric(**m, contact_email=contact_email) for m in result.data]

        # Get total count
        count_result = _supabase.table('email_response_metrics').select(
            'id', count='exact'
        ).eq('responder_contact_id', contact_id).execute()
        total = count_result.count if count_result.count else len(count_result.data)

        return ResponseTimeListResponse(metrics=metrics, total=total)

    except Exception as e:
        logger.error(f"Failed to get contact response history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# COMMUNICATION PATTERN ENDPOINTS (4 endpoints)
# ============================================================================

@router.get("/patterns/initiation", response_model=List[InitiationPattern])
async def get_initiation_patterns(
    client_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500)
):
    """
    Get thread initiation patterns.

    Args:
        client_id: Filter by client
        limit: Maximum number of results

    Returns:
        List of initiation patterns
    """
    try:
        if not client_id:
            raise HTTPException(status_code=400, detail="client_id is required")

        # Call RPC function to get thread initiation data
        result = _supabase.rpc(
            'calculate_all_contact_initiation_ratios',
            {'p_client_id': client_id}
        ).execute()

        if not result.data:
            return []

        # Enrich with contact info
        patterns = []
        for item in result.data[:limit]:  # Limit in memory for simplicity
            contact_result = _supabase.table('customer_contacts').select(
                'email_address, full_name, company_name'
            ).eq('id', item['contact_id']).single().execute()

            if contact_result.data:
                c = contact_result.data
                patterns.append(InitiationPattern(
                    contact_id=item['contact_id'],
                    contact_email=c['email_address'],
                    contact_name=c.get('full_name'),
                    company_name=c.get('company_name'),
                    total_threads=item['threads_initiated_by_us'] + item['threads_initiated_by_them'],
                    threads_initiated_by_us=item['threads_initiated_by_us'],
                    threads_initiated_by_them=item['threads_initiated_by_them'],
                    initiation_ratio=float(item['initiation_ratio'])
                ))

        # Sort by initiation ratio descending
        patterns.sort(key=lambda x: x.initiation_ratio, reverse=True)

        return patterns

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get initiation patterns: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/patterns/frequency", response_model=List[FrequencyPattern])
async def get_frequency_patterns(
    client_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500)
):
    """
    Get communication frequency patterns.

    Args:
        client_id: Filter by client
        limit: Maximum number of results

    Returns:
        List of frequency patterns
    """
    try:
        query = _supabase.table('customer_contacts').select(
            '''
            id, email_address, full_name, company_name,
            total_emails_sent, total_emails_received,
            first_contacted_at, last_contacted_at
            '''
        ).not_.is_('first_contacted_at', 'null')

        if client_id:
            query = query.eq('client_id', client_id)

        result = query.order('total_emails_sent', desc=True).limit(limit).execute()

        patterns = []
        for c in result.data:
            total_emails = (c.get('total_emails_sent', 0) or 0) + (c.get('total_emails_received', 0) or 0)

            # Calculate frequency metrics
            emails_per_week = None
            emails_per_month = None
            days_active = None

            if c.get('first_contacted_at') and c.get('last_contacted_at'):
                first = datetime.fromisoformat(c['first_contacted_at'].replace('Z', '+00:00'))
                last = datetime.fromisoformat(c['last_contacted_at'].replace('Z', '+00:00'))
                days_active = (last - first).days + 1

                if days_active > 0:
                    emails_per_week = (total_emails / days_active) * 7
                    emails_per_month = (total_emails / days_active) * 30

            patterns.append(FrequencyPattern(
                contact_id=c['id'],
                contact_email=c['email_address'],
                contact_name=c.get('full_name'),
                company_name=c.get('company_name'),
                total_emails=total_emails,
                emails_per_week=emails_per_week,
                emails_per_month=emails_per_month,
                first_contact_date=c.get('first_contacted_at'),
                last_contact_date=c.get('last_contacted_at'),
                days_active=days_active
            ))

        return patterns

    except Exception as e:
        logger.error(f"Failed to get frequency patterns: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/patterns/engagement-trends", response_model=List[EngagementTrend])
async def get_engagement_trends(
    client_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500)
):
    """
    Get engagement trends over time.

    Args:
        client_id: Filter by client
        limit: Maximum number of results

    Returns:
        List of engagement trends
    """
    try:
        from collections import defaultdict

        now = datetime.utcnow()
        thirty_days_ago = (now - timedelta(days=30)).isoformat()
        sixty_days_ago = (now - timedelta(days=60)).isoformat()

        # Get contacts with engagement scores
        contacts_query = _supabase.table('customer_contacts').select(
            'id, email_address, full_name, company_name, engagement_score'
        ).not_.is_('engagement_score', 'null')

        if client_id:
            contacts_query = contacts_query.eq('client_id', client_id)

        contacts_result = contacts_query.order('engagement_score', desc=True).limit(limit).execute()

        if not contacts_result.data:
            return []

        contact_ids = [c['id'] for c in contacts_result.data]
        contact_map = {c['id']: c for c in contacts_result.data}

        # Get email counts for last 60 days in one query, then split by period
        last30 = defaultdict(int)
        prev30 = defaultdict(int)

        # Fetch all emails for these contacts from the last 60 days
        emails_result = _supabase.table('emails').select(
            'customer_contact_id, sent_date'
        ).in_('customer_contact_id', contact_ids).gte('sent_date', sixty_days_ago).execute()

        for e in (emails_result.data or []):
            cid = e.get('customer_contact_id')
            sd = e.get('sent_date', '')
            if not cid or not sd:
                continue
            if sd >= thirty_days_ago:
                last30[cid] += 1
            else:
                prev30[cid] += 1

        trends = []
        for cid, contact in contact_map.items():
            l30 = last30[cid]
            p30 = prev30[cid]

            if p30 > 0:
                change_pct = ((l30 - p30) / p30) * 100
            elif l30 > 0:
                change_pct = 100.0
            else:
                change_pct = 0.0

            if change_pct > 10:
                trend = 'increasing'
            elif change_pct < -10:
                trend = 'decreasing'
            else:
                trend = 'stable'

            trends.append(EngagementTrend(
                contact_id=cid,
                contact_email=contact['email_address'],
                contact_name=contact.get('full_name'),
                company_name=contact.get('company_name'),
                current_engagement_score=contact.get('engagement_score', 0),
                trend=trend,
                last_30_days_emails=l30,
                previous_30_days_emails=p30,
                change_percentage=round(change_pct, 1)
            ))

        # Sort: decreasing first (at-risk), then stable, then increasing
        trend_order = {'decreasing': 0, 'stable': 1, 'increasing': 2}
        trends.sort(key=lambda t: (trend_order.get(t.trend, 1), -abs(t.change_percentage)))

        return trends

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get engagement trends: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/patterns/by-contact/{contact_id}", response_model=CommunicationPattern)
async def get_contact_pattern(contact_id: str):
    """
    Get complete communication pattern for a contact.

    Args:
        contact_id: Contact UUID

    Returns:
        Complete communication pattern
    """
    try:
        result = _supabase.table('customer_contacts').select(
            '''
            id, email_address, full_name, company_name,
            initiation_ratio,
            reply_rate, avg_response_time_seconds, their_avg_response_time, avg_thread_depth,
            total_emails_sent, total_emails_received,
            first_contacted_at, last_contacted_at
            '''
        ).eq('id', contact_id).single().execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Contact not found")

        c = result.data

        total_emails = (c.get('total_emails_sent', 0) or 0) + (c.get('total_emails_received', 0) or 0)

        # Calculate emails per week
        emails_per_week = None
        if c.get('first_contacted_at') and c.get('last_contacted_at'):
            first = datetime.fromisoformat(c['first_contacted_at'].replace('Z', '+00:00'))
            last = datetime.fromisoformat(c['last_contacted_at'].replace('Z', '+00:00'))
            days_active = (last - first).days + 1

            if days_active > 0:
                emails_per_week = (total_emails / days_active) * 7

        # Convert response times from seconds to hours
        avg_response_time_hours = None
        if c.get('avg_response_time_seconds'):
            avg_response_time_hours = c['avg_response_time_seconds'] / 3600.0

        their_avg_response_time_hours = None
        if c.get('their_avg_response_time'):
            their_avg_response_time_hours = c['their_avg_response_time'] / 3600.0

        return CommunicationPattern(
            contact_id=c['id'],
            contact_email=c['email_address'],
            contact_name=c.get('full_name'),
            company_name=c.get('company_name'),
            thread_initiation_ratio=c.get('initiation_ratio'),
            total_threads=None,  # Not tracked separately in schema
            reply_rate=c.get('reply_rate'),
            avg_response_time_hours=avg_response_time_hours,
            their_avg_response_time_hours=their_avg_response_time_hours,
            emails_per_week=emails_per_week,
            total_emails=total_emails,
            avg_thread_depth=c.get('avg_thread_depth')
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get contact pattern: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# DASHBOARD ENDPOINTS (2 endpoints)
# ============================================================================

@router.get("/dashboard", response_model=DashboardSummary)
async def get_dashboard(
    client_id: str = Query(...),
    period_days: Optional[int] = Query(default=None, description="Filter engagement data to last N days (7, 30, 90, 180, 365)")
):
    """
    Get complete dashboard summary for a client.

    Args:
        client_id: Client UUID (required)
        period_days: Optional time period filter in days

    Returns:
        Complete dashboard with all metrics
    """
    try:
        now = datetime.utcnow()
        period_cutoff = None
        if period_days:
            period_cutoff = (now - timedelta(days=period_days)).isoformat()

        # Count totals
        contacts_result = _supabase.table('customer_contacts').select(
            'id, last_contacted_at, engagement_score', count='exact'
        ).eq('client_id', client_id).execute()

        companies_result = _supabase.table('customer_companies').select(
            'id', count='exact'
        ).eq('client_id', client_id).execute()

        # Email count — scoped to period if set
        emails_query = _supabase.table('emails').select('id', count='exact').eq('client_id', client_id)
        if period_cutoff:
            emails_query = emails_query.gte('sent_date', period_cutoff)
        emails_result = emails_query.execute()

        # Calculate engagement distribution — filter contacts by period if set
        active = 0
        quiet = 0
        at_risk = 0
        engagement_scores = []

        for c in contacts_result.data:
            last_at = c.get('last_contacted_at')
            # If period set, skip contacts with no activity in the period
            if period_cutoff and last_at and last_at < period_cutoff:
                continue
            if not period_cutoff and not last_at:
                continue

            if c.get('engagement_score'):
                engagement_scores.append(c['engagement_score'])

            if last_at:
                last = datetime.fromisoformat(last_at.replace('Z', '+00:00'))
                days_since = (now - last.replace(tzinfo=None)).days

                if days_since <= 30:
                    active += 1
                elif days_since <= 90:
                    quiet += 1
                else:
                    at_risk += 1

        avg_score = sum(engagement_scores) / len(engagement_scores) if engagement_scores else None

        # Thread counts — filtered by client via mailbox_ids
        mailbox_result = _supabase.table('mailboxes').select('id').eq('client_id', client_id).execute()
        mailbox_ids = [m['id'] for m in (mailbox_result.data or [])]

        thread_counts = {'active': 0, 'overdue': 0, 'awaiting_response': 0, 'total': 0}
        if mailbox_ids:
            threads_query = _supabase.table('thread_status').select('status, last_message_at').in_('mailbox_id', mailbox_ids[:500])
            threads_result = threads_query.execute()

            for t in threads_result.data:
                # Filter by period if set
                if period_cutoff and t.get('last_message_at') and t['last_message_at'] < period_cutoff:
                    continue

                thread_counts['total'] += 1
                status = t.get('status', '')
                mapped = _map_thread_status(status)
                if mapped in (ThreadStatus.ONGOING, ThreadStatus.AWAITING_OUR_RESPONSE):
                    thread_counts['active'] += 1
                elif mapped == ThreadStatus.OVERDUE:
                    thread_counts['overdue'] += 1
                elif mapped == ThreadStatus.AWAITING_RESPONSE:
                    thread_counts['awaiting_response'] += 1

        # Response time average — filtered by client's contacts
        avg_response = None
        contact_ids = [c['id'] for c in contacts_result.data] if contacts_result.data else []
        if contact_ids:
            # Process in batches of 500 for .in_() limit
            all_times = []
            for i in range(0, len(contact_ids), 500):
                batch_ids = contact_ids[i:i + 500]
                resp_query = _supabase.table('email_response_metrics').select(
                    'response_time_seconds, created_at'
                ).in_('responder_contact_id', batch_ids)
                if period_cutoff:
                    resp_query = resp_query.gte('created_at', period_cutoff)
                resp_result = resp_query.execute()
                if resp_result.data:
                    all_times.extend([r['response_time_seconds'] / 3600.0 for r in resp_result.data if r.get('response_time_seconds')])
            if all_times:
                avg_response = sum(all_times) / len(all_times)

        # Get top engaged contacts — within period if set
        top_contacts_query = _supabase.table('customer_contacts').select(
            'id, email_address, full_name, company_name, engagement_score, total_emails_sent, total_emails_received, last_contacted_at, qb_customer_type, qb_tier'
        ).eq('client_id', client_id).not_.is_('engagement_score', 'null')
        if period_cutoff:
            top_contacts_query = top_contacts_query.gte('last_contacted_at', period_cutoff)
        top_contacts_result = top_contacts_query.order(
            'engagement_score', desc=True
        ).limit(5).execute()

        top_contacts = [
            TopEngagedContact(
                id=c['id'],
                email_address=c['email_address'],
                full_name=c.get('full_name'),
                company_name=c.get('company_name'),
                engagement_score=c['engagement_score'],
                total_emails=(c.get('total_emails_sent', 0) or 0) + (c.get('total_emails_received', 0) or 0),
                last_contacted_at=c.get('last_contacted_at')
            )
            for c in top_contacts_result.data
        ]

        top_companies_query = _supabase.table('customer_companies').select(
            'id, company_name, engagement_score, total_emails, contact_count, last_contact_date, qb_tier, qb_total_revenue'
        ).eq('client_id', client_id).not_.is_('engagement_score', 'null')
        if period_cutoff:
            top_companies_query = top_companies_query.gte('last_contact_date', period_cutoff)
        top_companies_result = top_companies_query.order(
            'engagement_score', desc=True
        ).limit(5).execute()

        top_companies = [
            TopEngagedCompany(
                id=comp['id'],
                company_name=comp['company_name'],
                engagement_score=comp['engagement_score'],
                total_emails=comp.get('total_emails', 0) or 0,
                contact_count=comp.get('contact_count', 0) or 0,
                last_contact_date=comp.get('last_contact_date')
            )
            for comp in top_companies_result.data
        ]

        # Get at-risk contacts/companies
        cutoff_date_contacts = (now - timedelta(days=60)).isoformat()
        at_risk_contacts_result = _supabase.table('customer_contacts').select(
            'id, email_address, full_name, company_name, last_contacted_at, engagement_score, qb_total_revenue, qb_tier'
        ).eq('client_id', client_id).not_.is_('last_contacted_at', 'null').lte(
            'last_contacted_at', cutoff_date_contacts
        ).order('last_contacted_at').limit(10).execute()

        at_risk_contacts_list = []
        for c in at_risk_contacts_result.data:
            last = datetime.fromisoformat(c['last_contacted_at'].replace('Z', '+00:00'))
            days_since = (now - last.replace(tzinfo=None)).days
            at_risk_contacts_list.append(AtRiskContact(
                id=c['id'],
                email_address=c['email_address'],
                full_name=c.get('full_name'),
                company_name=c.get('company_name'),
                last_contacted_at=c['last_contacted_at'],
                days_since_contact=days_since,
                engagement_score=c.get('engagement_score')
            ))

        cutoff_date_companies = (now - timedelta(days=90)).isoformat()
        at_risk_companies_result = _supabase.table('customer_companies').select(
            'id, company_name, last_contact_date, contact_count, engagement_score, qb_total_revenue, qb_days_since_last_invoice, qb_tier'
        ).eq('client_id', client_id).not_.is_('last_contact_date', 'null').lte(
            'last_contact_date', cutoff_date_companies
        ).order('last_contact_date').limit(10).execute()

        at_risk_companies_list = []
        for comp in at_risk_companies_result.data:
            last = datetime.fromisoformat(comp['last_contact_date'].replace('Z', '+00:00'))
            days_since = (now - last.replace(tzinfo=None)).days
            at_risk_companies_list.append(AtRiskCompany(
                id=comp['id'],
                company_name=comp['company_name'],
                last_contact_date=comp['last_contact_date'],
                days_since_contact=days_since,
                contact_count=comp.get('contact_count', 0) or 0,
                engagement_score=comp.get('engagement_score')
            ))

        # Get last extraction date
        last_extraction = _supabase.table('extraction_jobs').select(
            'completed_at'
        ).eq('client_id', client_id).eq('status', 'completed').order(
            'completed_at', desc=True
        ).limit(1).execute()

        last_extraction_date = None
        if last_extraction.data:
            last_extraction_date = last_extraction.data[0].get('completed_at')

        # Get last contact date
        last_contact = None
        if contacts_result.data:
            contact_dates = [c.get('last_contacted_at') for c in contacts_result.data if c.get('last_contacted_at')]
            if contact_dates:
                last_contact = max(contact_dates)

        return DashboardSummary(
            client_id=client_id,
            total_contacts=contacts_result.count or 0,
            total_companies=companies_result.count or 0,
            total_emails=emails_result.count or 0,
            active_contacts=active,
            quiet_contacts=quiet,
            at_risk_contacts=at_risk,
            avg_engagement_score=avg_score,
            total_threads=thread_counts['total'],
            active_threads=thread_counts['active'],
            overdue_threads=thread_counts['overdue'],
            awaiting_response_threads=thread_counts['awaiting_response'],
            avg_response_time_hours=avg_response,
            top_engaged_contacts=top_contacts,
            top_engaged_companies=top_companies,
            at_risk_contacts_list=at_risk_contacts_list,
            at_risk_companies_list=at_risk_companies_list,
            last_extraction_date=last_extraction_date,
            last_contact_date=last_contact
        )

    except Exception as e:
        logger.error(f"Failed to get dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary/{client_id}", response_model=ClientSummary)
async def get_client_summary(client_id: str):
    """
    Get client-specific summary.

    Args:
        client_id: Client UUID

    Returns:
        Client summary with key metrics
    """
    try:
        # Get client info
        client_result = _supabase.table('clients').select('client_name').eq('id', client_id).single().execute()

        if not client_result.data:
            raise HTTPException(status_code=404, detail="Client not found")

        client_name = client_result.data.get('client_name')

        # Count mailboxes
        mailboxes_result = _supabase.table('mailboxes').select('id', count='exact').eq('client_id', client_id).execute()

        # Count contacts
        contacts_result = _supabase.table('customer_contacts').select(
            'id, engagement_score, last_contacted_at', count='exact'
        ).eq('client_id', client_id).execute()

        # Count companies
        companies_result = _supabase.table('customer_companies').select('id', count='exact').eq('client_id', client_id).execute()

        # Count emails
        emails_result = _supabase.table('emails').select('id', count='exact').eq('client_id', client_id).execute()

        # Calculate engagement metrics
        engagement_scores = [c.get('engagement_score') for c in contacts_result.data if c.get('engagement_score')]
        avg_score = sum(engagement_scores) / len(engagement_scores) if engagement_scores else None

        active = 0
        at_risk = 0
        now = datetime.utcnow()
        for c in contacts_result.data:
            if c.get('last_contacted_at'):
                last = datetime.fromisoformat(c['last_contacted_at'].replace('Z', '+00:00'))
                days_since = (now - last.replace(tzinfo=None)).days

                if days_since <= 30:
                    active += 1
                elif days_since > 90:
                    at_risk += 1

        # Get last extraction
        last_extraction = _supabase.table('extraction_jobs').select('completed_at').eq(
            'client_id', client_id
        ).eq('status', 'completed').order('completed_at', desc=True).limit(1).execute()

        last_extraction_date = None
        if last_extraction.data:
            last_extraction_date = last_extraction.data[0].get('completed_at')

        # Get last contact
        last_contact = None
        if contacts_result.data:
            contact_dates = [c.get('last_contacted_at') for c in contacts_result.data if c.get('last_contacted_at')]
            if contact_dates:
                last_contact = max(contact_dates)

        return ClientSummary(
            client_id=client_id,
            client_name=client_name,
            mailbox_count=mailboxes_result.count or 0,
            contact_count=contacts_result.count or 0,
            company_count=companies_result.count or 0,
            total_emails=emails_result.count or 0,
            avg_engagement_score=avg_score,
            active_contacts=active,
            at_risk_contacts=at_risk,
            last_extraction_date=last_extraction_date,
            last_contact_date=last_contact
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get client summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# NOTE: Duplicate extraction endpoints removed (S3.1 cleanup).
# Original extraction endpoints are at the top of this file (lines ~67-274).


# ============================================================================
# METRIC HISTORY ENDPOINTS
# ============================================================================

@router.get("/metric-history/{entity_type}/{entity_id}")
async def get_metric_history(
    entity_type: str,
    entity_id: str,
    limit: int = Query(default=30, ge=1, le=200),
):
    """
    Get engagement score history for a contact or company.

    Returns chronological list of scores with factor breakdowns for trend charts.
    """
    if entity_type not in ('contact', 'company'):
        raise HTTPException(status_code=400, detail="entity_type must be 'contact' or 'company'")

    try:
        result = (
            _supabase.table('metric_history')
            .select(
                'engagement_score, scoring_version, '
                'response_time_score, thread_completeness_score, '
                'initiation_balance_score, reply_rate_score, '
                'frequency_score, recency_score, '
                'decision_maker_bonus, seniority_bonus, '
                'emails_per_month_avg, avg_response_time_seconds, reply_rate, '
                'calculated_at'
            )
            .eq('entity_id', entity_id)
            .eq('entity_type', entity_type)
            .order('calculated_at', desc=True)
            .limit(limit)
            .execute()
        )

        # Return in chronological order (oldest first) for charts
        data = list(reversed(result.data or []))
        return {'history': data, 'total': len(data)}

    except Exception as e:
        logger.error(f"Failed to get metric history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# DATA HEALTH ENDPOINTS
# ============================================================================

@router.get("/data-health")
async def get_data_health(client_id: Optional[str] = Query(default=None)):
    """
    Data health dashboard — sync lag, identity resolution coverage,
    thread confidence distribution, and missing-day detection.
    """
    try:
        logger.info("data-health: starting step 1 - mailboxes")
        # ---------- 1. Sync lag per mailbox ----------
        mb_query = _supabase.table('mailboxes').select(
            'id, name, email_address, mailbox_type, is_active, last_sync_at, last_extraction_at'
        )
        if client_id:
            mb_query = mb_query.eq('client_id', client_id)
        mb_result = mb_query.execute()
        logger.info(f"data-health: step 1 done, {len(mb_result.data or [])} mailboxes")

        now = datetime.utcnow()
        mailbox_health = []
        for mb in (mb_result.data or []):
            sync_lag_hours = None
            extraction_lag_hours = None
            if mb.get('last_sync_at'):
                try:
                    last_sync = datetime.fromisoformat(mb['last_sync_at'].replace('Z', '+00:00')).replace(tzinfo=None)
                    sync_lag_hours = round((now - last_sync).total_seconds() / 3600, 1)
                except Exception:
                    pass
            if mb.get('last_extraction_at'):
                try:
                    last_ext = datetime.fromisoformat(mb['last_extraction_at'].replace('Z', '+00:00')).replace(tzinfo=None)
                    extraction_lag_hours = round((now - last_ext).total_seconds() / 3600, 1)
                except Exception:
                    pass

            mailbox_health.append({
                'mailbox_id': mb['id'],
                'email_address': mb.get('email_address') or mb.get('name', 'Unknown'),
                'provider': mb.get('mailbox_type'),
                'status': 'active' if mb.get('is_active') else 'inactive',
                'last_sync_at': mb.get('last_sync_at'),
                'last_extraction_at': mb.get('last_extraction_at'),
                'sync_lag_hours': sync_lag_hours,
                'extraction_lag_hours': extraction_lag_hours,
            })

        # ---------- 2. Identity resolution coverage ----------
        logger.info("data-health: step 2 - identity resolution")
        email_query = _supabase.table('emails').select('id', count='exact')
        if client_id:
            email_query = email_query.eq('client_id', client_id)
        total_emails_result = email_query.execute()
        total_emails = total_emails_result.count or 0

        # Count unresolved (customer_contact_id IS NULL), then subtract
        logger.info("data-health: step 2b - unresolved count")
        unresolved_query = _supabase.table('emails').select('id', count='exact').is_('customer_contact_id', 'null')
        if client_id:
            unresolved_query = unresolved_query.eq('client_id', client_id)
        unresolved_result = unresolved_query.execute()
        unresolved_emails = unresolved_result.count or 0
        resolved_emails = total_emails - unresolved_emails

        identity_resolution = {
            'total_emails': total_emails,
            'resolved_emails': resolved_emails,
            'unresolved_emails': unresolved_emails,
            'coverage_percent': round((resolved_emails / total_emails * 100), 1) if total_emails > 0 else 0,
        }

        # ---------- 2c. Junction table (email_contact_links) coverage ----------
        logger.info("data-health: step 2c - junction table coverage")
        junction_coverage = {'emails_with_links': 0, 'emails_without_links': 0, 'total_links': 0, 'coverage_percent': 0}
        try:
            # Count distinct email_ids in junction table
            ecl_query = _supabase.table('email_contact_links').select('email_id', count='exact')
            if client_id:
                ecl_query = ecl_query.eq('client_id', client_id)
            ecl_result = ecl_query.execute()
            total_links = ecl_result.count or 0

            # Distinct emails with at least one link — use a different approach:
            # Count emails that have NO junction row
            # Supabase doesn't support COUNT(DISTINCT) easily, so approximate:
            # emails_with_links ≈ total_emails - emails_without_any_link
            # But that's expensive. Instead, just report total_links and coverage based on
            # the ratio: if links > emails, coverage is high (CC/BCC create multiple links per email)
            emails_with_links = min(total_links, total_emails)  # Conservative: can't have more linked emails than total
            # Better approach: total_links / total_emails gives avg links per email, not coverage.
            # Just report the raw numbers and let the frontend display them.
            junction_coverage = {
                'total_links': total_links,
                'total_emails': total_emails,
                'avg_links_per_email': round(total_links / total_emails, 1) if total_emails > 0 else 0,
            }
        except Exception as ecl_err:
            logger.warning(f"Junction coverage check failed: {ecl_err}")

        # ---------- 3. Thread confidence distribution ----------
        logger.info("data-health: step 3 - thread distribution")
        # Use per-status COUNT queries instead of paginating all rows (52K+ rows = timeout)
        mailbox_ids = [m['mailbox_id'] for m in mailbox_health]
        THREAD_STATUSES = ['ongoing', 'awaiting_response', 'awaiting_our_response', 'overdue', 'dropped', 'complete']
        status_counts = {}
        mb_filter = None
        if mailbox_ids:
            mb_filter = ','.join(f"mailbox_id.eq.{mid}" for mid in mailbox_ids[:100])
            or_filter = f"{mb_filter},mailbox_id.is.null"
        for s in THREAD_STATUSES:
            try:
                q = _supabase.table('thread_status').select('id', count='exact').eq('status', s)
                if mb_filter:
                    q = q.or_(or_filter)
                r = q.execute()
                status_counts[s] = r.count or 0
            except Exception:
                status_counts[s] = 0
        thread_total = sum(status_counts.values())
        thread_distribution = [
            {
                'status': status,
                'count': count,
                'percent': round(count / thread_total * 100, 1) if thread_total > 0 else 0,
            }
            for status, count in sorted(status_counts.items(), key=lambda x: -x[1])
            if count > 0
        ]

        logger.info("data-health: step 4 - missing days")
        # ---------- 4. Missing days (gaps in email data, last 30 days) ----------
        # Fetch only sent_date for last 30 days — single column, fast index scan
        # Even at 100K emails, sent_date is ~20 bytes each so 100K = ~2MB, well within timeout
        thirty_days_ago = (now - timedelta(days=30)).isoformat()
        all_dates = set()
        try:
            recent_q = _supabase.table('emails').select('sent_date').gte('sent_date', thirty_days_ago).limit(200000)
            if client_id:
                recent_q = recent_q.eq('client_id', client_id)
            recent_result = recent_q.execute()
            for r in (recent_result.data or []):
                if r.get('sent_date'):
                    try:
                        d = datetime.fromisoformat(r['sent_date'].replace('Z', '+00:00')).date()
                        all_dates.add(d)
                    except Exception:
                        pass
        except Exception:
            pass

        expected_dates = set()
        for i in range(30):
            expected_dates.add((now - timedelta(days=i)).date())

        missing_dates = sorted(expected_dates - all_dates)
        # Only flag weekdays as truly missing
        missing_weekdays = [d.isoformat() for d in missing_dates if d.isoweekday() <= 5]

        logger.info("data-health: step 5 - extraction jobs")
        # ---------- 5. Extraction jobs health ----------
        jobs_query = _supabase.table('extraction_jobs').select(
            'id, status, extraction_mode, started_at, completed_at, total_emails, processed_emails, errors'
        )
        if client_id:
            jobs_query = jobs_query.eq('client_id', client_id)
        jobs_result = jobs_query.order('started_at', desc=True).limit(10).execute()
        recent_jobs = jobs_result.data or []

        # ---------- 6. Thread duplication health ----------
        # ---------- 6. Thread health (simple count — UNIQUE(thread_id) prevents dupes) ----------
        logger.info("data-health: step 6 - thread health")
        thread_health = {'total_rows': 0, 'unique_threads': 0, 'duplicate_rows': 0, 'duplicate_pct': 0}
        try:
            total_rows_r = _supabase.table('thread_status').select('id', count='exact')
            if mailbox_ids:
                mb_filter_th = ','.join(f"mailbox_id.eq.{mid}" for mid in mailbox_ids[:100])
                total_rows_r = total_rows_r.or_(f"{mb_filter_th},mailbox_id.is.null")
            total_rows_r = total_rows_r.execute()
            total_rows = total_rows_r.count or 0

            # With UNIQUE(thread_id) constraint from migration 060,
            # total_rows == unique_threads by definition. No RPC needed.
            thread_health = {
                'total_rows': total_rows,
                'unique_threads': total_rows,
                'duplicate_rows': 0,
                'duplicate_pct': 0,
            }
        except Exception as th_err:
            logger.warning(f"Thread health count failed: {th_err}")

        return {
            'mailbox_health': mailbox_health,
            'identity_resolution': identity_resolution,
            'junction_coverage': junction_coverage,
            'thread_distribution': thread_distribution,
            'thread_health': thread_health,
            'missing_weekdays': missing_weekdays,
            'missing_weekday_count': len(missing_weekdays),
            'recent_extraction_jobs': recent_jobs,
        }

    except Exception as e:
        logger.error(f"Failed to get data health: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/data-health/fetch-missing-dates")
async def fetch_missing_dates(
    data: dict,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(require_role('admin')),
):
    """
    Trigger date-range email fetch for all active mailboxes of a client.
    Dispatches a background job per mailbox (Gmail or Outlook) to pull
    emails for the specified date range — useful for filling sync gaps.
    """
    from datetime import datetime as dt
    client_id = data.get('client_id')
    start_date = data.get('start_date')
    end_date = data.get('end_date')

    if not client_id or not start_date or not end_date:
        raise HTTPException(status_code=400, detail="client_id, start_date, end_date required")

    try:
        dt.strptime(start_date, '%Y-%m-%d')
        dt.strptime(end_date, '%Y-%m-%d')
    except ValueError:
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")

    # Fetch all active mailboxes for this client
    mb_result = _supabase.table('mailboxes').select(
        'id, email_address, mailbox_type, connection_config, user_id'
    ).eq('client_id', client_id).eq('is_active', True).execute()
    mailboxes = mb_result.data or []

    if not mailboxes:
        raise HTTPException(status_code=404, detail="No active mailboxes found for client")

    now = datetime.now(timezone.utc).isoformat()
    jobs = []
    skipped = []

    for mb in mailboxes:
        mb_id = mb['id']
        connection_config = mb.get('connection_config') or {}
        has_gmail = connection_config.get('gmail_sync_enabled')
        has_outlook = connection_config.get('outlook_sync_enabled')

        if not has_gmail and not has_outlook:
            skipped.append({'mailbox_id': mb_id, 'email': mb.get('email_address'), 'reason': 'no live sync'})
            continue

        provider = 'gmail' if has_gmail else 'outlook'
        job_type = f'{provider}_date_range_fetch'
        user_id = connection_config.get('gmail_user_id') or connection_config.get('outlook_user_id') or mb.get('user_id')

        # Create processing job
        from ..services.jobs import create_job, JobSpec
        job_id = create_job(_supabase, JobSpec(
            job_type=job_type,
            mailbox_id=mb_id,
            initial_status="running",  # BackgroundTasks execution — prevent worker claiming
            filter_start_date=f"{start_date}T00:00:00Z",
            filter_end_date=f"{end_date}T23:59:59Z",
            triggered_by="user",
        ))

        # Dispatch background fetch
        if provider == 'gmail':
            from ..routers.gmail import _run_date_range_fetch as _gmail_fetch
            background_tasks.add_task(_gmail_fetch, job_id, mb_id, user_id, start_date, end_date, None)
        else:
            from ..routers.outlook import _run_date_range_fetch as _outlook_fetch
            background_tasks.add_task(_outlook_fetch, job_id, mb_id, user_id, start_date, end_date, None)

        jobs.append({
            'mailbox_id': mb_id,
            'email': mb.get('email_address'),
            'provider': provider,
            'job_id': job_id,
        })

    return {
        'status': 'started',
        'start_date': start_date,
        'end_date': end_date,
        'jobs_started': len(jobs),
        'jobs': jobs,
        'skipped': skipped,
    }


@router.get("/data-health/classification")
async def get_classification_health(client_id: Optional[str] = Query(default=None)):
    """
    AI classification coverage — how many emails have intent/urgency/sentiment.
    Single RPC call replaces the previous N+1 per-mailbox loop (was 5×N queries).
    """
    try:
        params: dict = {}
        if client_id:
            params['p_client_id'] = client_id

        resp = _supabase.rpc('get_classification_health', params).execute()
        raw = resp.data
        # RETURNS JSONB → PostgREST returns the JSON array directly as a Python list,
        # or sometimes wraps scalar JSONB in a single-element list
        if isinstance(raw, list) and len(raw) > 0 and isinstance(raw[0], list):
            per_mailbox = raw[0]  # Unwrap [[...]]
        elif isinstance(raw, list):
            per_mailbox = raw
        else:
            per_mailbox = []
        logger.debug(f"Classification health RPC returned {type(raw).__name__}, {len(per_mailbox)} mailboxes")

        # Ensure numeric types from JSONB
        # coverage_pct = "work complete" — (classified + skipped) / total.
        # Skipped emails (spam, bounces) are intentional pre-filter hits, not gaps.
        for mb in per_mailbox:
            for k in ('total_emails', 'classified', 'pending', 'failed', 'skipped'):
                mb[k] = int(mb.get(k, 0))
            mb['coverage_pct'] = round(
                (mb['classified'] + mb['skipped']) / mb['total_emails'] * 100, 1
            ) if mb['total_emails'] > 0 else 0.0

        total_emails_all = sum(m['total_emails'] for m in per_mailbox)
        total_classified_all = sum(m['classified'] for m in per_mailbox)
        total_pending_all = sum(m['pending'] for m in per_mailbox)
        total_failed_all = sum(m['failed'] for m in per_mailbox)
        total_skipped_all = sum(m['skipped'] for m in per_mailbox)
        overall_coverage = round(
            (total_classified_all + total_skipped_all) / total_emails_all * 100, 1
        ) if total_emails_all > 0 else 0.0

        return {
            'mailboxes': per_mailbox,
            'totals': {
                'total_emails': total_emails_all,
                'classified': total_classified_all,
                'pending': total_pending_all,
                'failed': total_failed_all,
                'skipped': total_skipped_all,
                'coverage_pct': overall_coverage,
            },
        }

    except Exception as e:
        logger.error(f"Failed to get classification health: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data-health/threads")
async def get_thread_health(client_id: Optional[str] = Query(default=None)):
    """
    Thread processing health — per-mailbox intent coverage and status distribution.
    Single RPC call replaces the previous N+1 loop + pagination (was 2N+pagination queries).
    """
    try:
        # RPC returns mailboxes + status/intent distributions in one call
        params: dict = {}
        if client_id:
            params['p_client_id'] = client_id

        rpc_resp = _supabase.rpc('get_thread_health', params).execute()
        rpc_data = rpc_resp.data or {}
        if isinstance(rpc_data, list) and len(rpc_data) > 0:
            rpc_data = rpc_data[0]

        mailbox_stats = rpc_data.get('mailboxes', [])
        status_counts = rpc_data.get('status_distribution', {})
        intent_counts = rpc_data.get('intent_distribution', {})

        # Ensure numeric types from JSONB
        for mb in mailbox_stats:
            mb['thread_count'] = int(mb.get('thread_count', 0))
            mb['with_intent'] = int(mb.get('with_intent', 0))
            mb['intent_coverage_pct'] = float(mb.get('intent_coverage_pct', 0))

        # Totals
        total_threads = sum(m['thread_count'] for m in mailbox_stats)
        total_with_intent = sum(m['with_intent'] for m in mailbox_stats)

        # Last thread evaluation job (cheap — single indexed query)
        last_job = None
        try:
            mb_query = _supabase.table('mailboxes').select('id')
            if client_id:
                mb_query = mb_query.eq('client_id', client_id)
            mb_result = mb_query.execute()
            mailbox_ids = [m['id'] for m in (mb_result.data or [])]

            if mailbox_ids:
                jobs_query = _supabase.table('processing_jobs').select(
                    'id, status, started_at, completed_at, error_summary, error_log'
                ).eq('job_type', 'thread_recompute').order('started_at', desc=True).limit(1)
                jobs_query = jobs_query.in_('mailbox_id', mailbox_ids[:500])
                job_result = jobs_query.execute()
                last_job = job_result.data[0] if job_result.data else None
        except Exception as job_err:
            logger.warning(f"Could not fetch thread recompute job: {job_err}")

        # Convert status/intent counts to int values
        status_counts = {k: int(v) for k, v in status_counts.items()}
        intent_counts = {k: int(v) for k, v in intent_counts.items()}

        return {
            'last_evaluation': {
                'job_id': last_job.get('id') if last_job else None,
                'status': last_job.get('status') if last_job else None,
                'started_at': last_job.get('started_at') if last_job else None,
                'completed_at': last_job.get('completed_at') if last_job else None,
            },
            'mailboxes': mailbox_stats,
            'totals': {
                'total_threads': total_threads,
                'with_intent': total_with_intent,
                'without_intent': total_threads - total_with_intent,
                'intent_coverage_pct': round(
                    total_with_intent / total_threads * 100, 1
                ) if total_threads > 0 else 0.0,
            },
            'status_distribution': dict(sorted(status_counts.items(), key=lambda x: -x[1])),
            'intent_distribution': dict(sorted(intent_counts.items(), key=lambda x: -x[1])),
        }

    except Exception as e:
        logger.error(f"Failed to get thread health: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data-health/ai-link-refs")
async def get_ai_link_ref_health(client_id: Optional[str] = Query(default=None)):
    """
    AI-extracted QB reference linking health — per-mailbox extraction stats + client-wide link totals.
    Single RPC call via get_ai_link_ref_health().
    """
    try:
        params: dict = {}
        if client_id:
            params['p_client_id'] = client_id

        resp = _supabase.rpc('get_ai_link_ref_health', params).execute()
        raw = resp.data
        # RPC returns JSONB object; PostgREST may wrap in a list
        if isinstance(raw, list) and len(raw) > 0 and isinstance(raw[0], dict) and 'mailboxes' in raw[0]:
            rpc_data = raw[0]
        elif isinstance(raw, dict):
            rpc_data = raw
        else:
            rpc_data = {'mailboxes': [], 'link_totals': {}}

        per_mailbox = rpc_data.get('mailboxes') or []
        link_totals = rpc_data.get('link_totals') or {}

        for mb in per_mailbox:
            for k in ('total_classified', 'emails_with_refs', 'total_refs_found',
                       'total_quote_refs', 'total_job_refs'):
                mb[k] = int(mb.get(k, 0))

        total_refs = sum(m['total_refs_found'] for m in per_mailbox)
        total_classified = sum(m['total_classified'] for m in per_mailbox)
        total_with_refs = sum(m['emails_with_refs'] for m in per_mailbox)

        total_links = int(link_totals.get('total_links', 0))
        threads_linked = int(link_totals.get('threads_linked', 0))
        quote_links = int(link_totals.get('quote_links', 0))
        job_links = int(link_totals.get('job_links', 0))

        return {
            'mailboxes': per_mailbox,
            'totals': {
                'total_classified': total_classified,
                'emails_with_refs': total_with_refs,
                'total_refs_found': total_refs,
                'total_quote_refs': sum(m['total_quote_refs'] for m in per_mailbox),
                'total_job_refs': sum(m['total_job_refs'] for m in per_mailbox),
                'threads_linked': threads_linked,
                'total_links': total_links,
                'quote_links': quote_links,
                'job_links': job_links,
                'link_rate_pct': round(total_links / total_refs * 100, 1) if total_refs > 0 else 0.0,
                'extraction_rate_pct': round(total_with_refs / total_classified * 100, 1) if total_classified > 0 else 0.0,
            },
        }
    except Exception as e:
        logger.error(f"Failed to get AI link ref health: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/data-health/ai-link-refs/backfill")
async def backfill_ai_link_refs(
    background_tasks: BackgroundTasks,
    client_id: str = Query(...),
    lookback_days: Optional[int] = Query(default=None, description="Only process last N days (null = full backfill)"),
):
    """
    Trigger AI reference linking backfill — validates extracted refs against QB
    and upserts thread_qb_links. Runs in background.
    """
    import re as _re

    PAGE = 500

    async def _run_link_refs():
        try:
            mb_resp = _supabase.table("mailboxes").select(
                "id, name, email_address, client_id"
            ).eq("client_id", client_id).execute()
            mailboxes = mb_resp.data or []

            grand_total = 0
            for mb in mailboxes:
                mb_id = mb["id"]
                mb_client_id = mb.get("client_id")
                if not mb_client_id:
                    continue

                all_rows = []
                offset = 0
                while True:
                    query = _supabase.table("ai_email_intelligence").select(
                        "email_id, extracted_references"
                    ).eq("mailbox_id", mb_id).eq(
                        "processing_status", "completed"
                    ).not_.is_("extracted_references", "null")

                    if lookback_days is not None:
                        cutoff = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()
                        query = query.gte("processed_at", cutoff)

                    resp = query.range(offset, offset + PAGE - 1).execute()
                    batch = resp.data or []
                    all_rows.extend(batch)
                    if len(batch) < PAGE:
                        break
                    offset += PAGE

                if not all_rows:
                    continue

                email_ids = [r["email_id"] for r in all_rows]
                thread_map: dict[str, str] = {}
                for i in range(0, len(email_ids), PAGE):
                    chunk = email_ids[i:i + PAGE]
                    thread_resp = _supabase.table("emails").select(
                        "id, canonical_thread_id"
                    ).in_("id", chunk).execute()
                    for r in (thread_resp.data or []):
                        tid = r.get("canonical_thread_id")
                        if tid:
                            thread_map[r["id"]] = tid

                all_quote_refs: set[str] = set()
                all_job_refs: set[str] = set()
                row_refs: list[tuple[str, dict[str, set[str]]]] = []

                for row in all_rows:
                    refs_raw = row.get("extracted_references") or []
                    if not refs_raw:
                        continue
                    thread_id = thread_map.get(row["email_id"])
                    if not thread_id:
                        continue

                    refs: dict[str, set[str]] = {}
                    for ref in refs_raw:
                        ref_type = ref.get("type")
                        ref_number = ref.get("number")
                        if ref_type and ref_number:
                            digits = _re.sub(r'[^0-9]', '', str(ref_number))
                            if not digits:
                                continue
                            prefix = "Q" if ref_type == "quote" else "J"
                            canonical = f"{prefix}{digits}"
                            refs.setdefault(ref_type, set()).add(canonical)
                            if ref_type == "quote":
                                all_quote_refs.add(canonical)
                            else:
                                all_job_refs.add(canonical)

                    if refs:
                        row_refs.append((thread_id, refs))

                if not row_refs:
                    continue

                valid_quotes: dict[str, str] = {}
                valid_jobs: dict[str, str] = {}

                for i in range(0, len(list(all_quote_refs)), PAGE):
                    chunk = list(all_quote_refs)[i:i + PAGE]
                    resp = _supabase.table("qb_quotes").select("quote_no, qb_record_id").eq(
                        "client_id", mb_client_id
                    ).in_("quote_no", chunk).execute()
                    for r in (resp.data or []):
                        valid_quotes[r["quote_no"]] = str(r["qb_record_id"])

                for i in range(0, len(list(all_job_refs)), PAGE):
                    chunk = list(all_job_refs)[i:i + PAGE]
                    resp = _supabase.table("qb_jobs").select("job_no, qb_record_id").eq(
                        "client_id", mb_client_id
                    ).in_("job_no", chunk).execute()
                    for r in (resp.data or []):
                        valid_jobs[r["job_no"]] = str(r["qb_record_id"])

                if not valid_quotes and not valid_jobs:
                    continue

                total_linked = 0
                for thread_id, refs in row_refs:
                    validated: dict[str, dict[str, str]] = {}
                    for ref_str in refs.get("quote", set()):
                        if ref_str in valid_quotes:
                            validated.setdefault("quote", {})[ref_str] = valid_quotes[ref_str]
                    for ref_str in refs.get("job", set()):
                        if ref_str in valid_jobs:
                            validated.setdefault("job", {})[ref_str] = valid_jobs[ref_str]

                    if not validated:
                        continue

                    rows = []
                    for link_type, ref_map in validated.items():
                        for ref_str, record_id in ref_map.items():
                            rows.append({
                                "client_id": mb_client_id,
                                "canonical_thread_id": thread_id,
                                "link_type": link_type,
                                "qb_record_id": record_id,
                                "qb_reference": ref_str,
                                "confidence": 0.9,
                                "source": "ai",
                                "verified": False,
                            })

                    try:
                        _supabase.table("thread_qb_links").upsert(
                            rows,
                            on_conflict="client_id,canonical_thread_id,link_type,qb_record_id",
                        ).execute()
                        total_linked += len(rows)
                    except Exception as e:
                        logger.warning(f"Link ref upsert error for thread {thread_id[:16]}: {e}")

                grand_total += total_linked

            logger.info(f"AI link ref backfill complete: {grand_total} links upserted for client {client_id}")

        except Exception as e:
            logger.error(f"AI link ref backfill failed: {e}", exc_info=True)

    background_tasks.add_task(_run_link_refs)

    scope = f"last {lookback_days} days" if lookback_days else "full (all time)"
    return {
        "status": "accepted",
        "message": f"AI link ref backfill started ({scope})",
        "lookback_days": lookback_days,
    }


@router.get("/data-health/db-performance")
async def get_db_performance(
    current_user: dict = Depends(require_role('admin')),
):
    """
    Database performance metrics — top slow queries, table sizes, index usage,
    and cache hit ratios. Used by the admin dashboard for proactive IO monitoring.
    """
    try:
        slow_queries = []
        table_stats = []
        index_stats = []
        cache_stats = {}

        # Fire all 4 RPCs (independent, but Supabase client is sync so sequential)
        try:
            resp = _supabase.rpc('get_db_slow_queries', {'p_limit': 15}).execute()
            slow_queries = resp.data if isinstance(resp.data, list) else (resp.data or [])
        except Exception as e:
            logger.warning(f"get_db_slow_queries RPC failed: {e}")

        try:
            resp = _supabase.rpc('get_db_table_stats', {}).execute()
            table_stats = resp.data if isinstance(resp.data, list) else (resp.data or [])
        except Exception as e:
            logger.warning(f"get_db_table_stats RPC failed: {e}")

        try:
            resp = _supabase.rpc('get_db_index_stats', {}).execute()
            index_stats = resp.data if isinstance(resp.data, list) else (resp.data or [])
        except Exception as e:
            logger.warning(f"get_db_index_stats RPC failed: {e}")

        try:
            resp = _supabase.rpc('get_db_cache_stats', {}).execute()
            raw = resp.data
            if isinstance(raw, list) and len(raw) > 0:
                cache_stats = raw[0]
            elif isinstance(raw, dict):
                cache_stats = raw
        except Exception as e:
            logger.warning(f"get_db_cache_stats RPC failed: {e}")

        return {
            'slow_queries': slow_queries,
            'table_stats': table_stats,
            'index_stats': index_stats,
            'cache_stats': cache_stats,
        }

    except Exception as e:
        logger.error(f"Failed to get DB performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/data-health/db-performance/reset")
async def reset_db_performance_stats(
    current_user: dict = Depends(require_role('admin')),
):
    """Reset pg_stat_statements — clears cumulative query stats for a fresh baseline."""
    try:
        _supabase.rpc('reset_db_stats', {}).execute()
        return {"status": "ok", "message": "Query stats reset"}
    except Exception as e:
        logger.error(f"Failed to reset DB stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# SEASONALITY & OUTREACH INTELLIGENCE
# ============================================================================

@router.get("/outreach-windows")
async def get_outreach_windows(
    client_id: Optional[str] = Query(default=None),
    weeks_ahead: int = Query(default=8, ge=2, le=16),
    current_user: dict = Depends(get_current_user),
):
    """Upcoming outreach windows — companies with historical peak months approaching.

    Returns companies where a seasonal revenue peak is 4-8 weeks away,
    sorted by historical peak revenue. Use this to prioritise proactive outreach.
    """
    if not client_id:
        raise HTTPException(status_code=400, detail="client_id required")
    try:
        resp = _supabase.rpc('get_outreach_windows', {
            'p_client_id': client_id,
            'p_weeks_ahead': weeks_ahead,
        }).execute()
        raw = resp.data
        if isinstance(raw, list) and len(raw) == 1 and isinstance(raw[0], list):
            windows = raw[0]
        elif isinstance(raw, list):
            windows = raw
        else:
            windows = []

        # Ensure numeric types
        for w in windows:
            w['revenue_in_peak'] = float(w.get('revenue_in_peak', 0))
            w['order_count'] = int(w.get('order_count', 0))
            w['years_active'] = int(w.get('years_active', 0))
            w['avg_annual_peak'] = float(w.get('avg_annual_peak', 0))

        return {'windows': windows, 'weeks_ahead': weeks_ahead, 'total': len(windows)}
    except Exception as e:
        logger.error(f"Failed to get outreach windows: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/seasonality/industry/{industry}")
async def get_industry_seasonality(
    industry: str,
    client_id: Optional[str] = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    """Industry-level seasonality — monthly revenue patterns aggregated across all
    companies in the specified industry.
    """
    try:
        params: dict = {'p_industry': industry}
        if client_id:
            params['p_client_id'] = client_id

        resp = _supabase.rpc('get_industry_seasonality', params).execute()
        raw = resp.data
        if isinstance(raw, list) and len(raw) == 1 and isinstance(raw[0], list):
            monthly = raw[0]
        elif isinstance(raw, list):
            monthly = raw
        else:
            monthly = []

        # Ensure numeric types + add month names
        month_names = ['', 'January', 'February', 'March', 'April', 'May', 'June',
                       'July', 'August', 'September', 'October', 'November', 'December']
        for m in monthly:
            mo = int(m.get('month', 0))
            m['month'] = mo
            m['month_name'] = month_names[mo] if 0 < mo <= 12 else '?'
            m['order_count'] = int(m.get('order_count', 0))
            m['revenue'] = float(m.get('revenue', 0))
            m['company_count'] = int(m.get('company_count', 0))

        return {'industry': industry, 'monthly': monthly}
    except Exception as e:
        logger.error(f"Failed to get industry seasonality: {e}")
        raise HTTPException(status_code=500, detail=str(e))
