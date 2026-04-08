"""
Thread Tracker Service - Sprint 2 Phase 4

Purpose: Track and evaluate email thread completeness for engagement analytics
Part of 13-step extraction pipeline (used in Step 12)

Features:
- Evaluates thread status (complete/awaiting/overdue/dropped/ongoing)
- Identifies open threads needing attention
- Tracks thread depth (number of back-and-forth exchanges)
- Populates thread_status table
- Updates contact/company thread counts

Thread Status States:
- complete: Thread closed naturally
- awaiting_response: Waiting for contact's response (we sent last)
- awaiting_our_response: Contact waiting for our response (they sent last)
- overdue: Response overdue (past reasonable time)
- dropped: Thread abandoned by one party
- ongoing: Active back-and-forth conversation

Author: Sprint 2 Implementation
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

from ..database.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)


@dataclass
class ThreadStatus:
    """Thread status evaluation result"""
    thread_id: str
    status: str  # complete, awaiting_response, awaiting_our_response, overdue, dropped, ongoing
    last_email_id: str
    last_email_date: datetime
    last_sender_is_outbound: bool
    thread_depth: int  # Number of direction changes
    days_since_last_email: int
    is_overdue: bool
    primary_contact_id: Optional[str]
    primary_company_id: Optional[str]
    subject: Optional[str] = None
    message_count: int = 0
    # Intent-based intelligence (from ai_email_intelligence)
    intent_status: Optional[str] = None           # urgent, revenue_opportunity, closing, escalation, informational
    intent_override_reason: Optional[str] = None   # human-readable reason for intent override
    last_email_intent: Optional[str] = None        # cached intent from AI classification
    last_email_urgency: Optional[str] = None       # cached urgency
    last_email_sentiment: Optional[str] = None     # cached sentiment


class ThreadTracker:
    """
    Track and evaluate email thread status for engagement analytics

    Usage:
        tracker = ThreadTracker(mailbox_id="uuid-here", client_id="uuid-here")
        thread_statuses = tracker.evaluate_threads()
        tracker.save_thread_statuses(thread_statuses)
        tracker.update_thread_counts()
    """

    # Thread status evaluation thresholds
    ACTIVE_THREAD_DAYS = 3  # Thread is "ongoing" if last email within 3 days
    OVERDUE_DAYS = 7  # Thread is "overdue" if waiting > 7 days
    DROPPED_DAYS = 30  # Thread is "dropped" if no activity > 30 days
    MIN_DEPTH_FOR_COMPLETE = 2  # Minimum exchanges to consider complete

    def __init__(self, mailbox_id: str = None, client_id: str = None):
        """
        Initialize thread tracker.

        Can operate in two modes:
        - Client-wide (client_id only): evaluates threads across ALL mailboxes for a client.
          This is the correct mode — threads span mailboxes when multiple people are involved.
        - Per-mailbox (mailbox_id + client_id): legacy mode, evaluates one mailbox only.

        Args:
            mailbox_id: Optional mailbox UUID (legacy per-mailbox mode)
            client_id: Client UUID for filtering
        """
        self.mailbox_id = mailbox_id
        self.client_id = client_id
        self.client = SupabaseClient.get_client(use_service_key=True)

        if not client_id and mailbox_id:
            # Auto-fetch client_id from mailbox
            resp = self.client.table('mailboxes').select('client_id').eq('id', mailbox_id).limit(1).execute()
            if resp.data:
                self.client_id = resp.data[0]['client_id']

        mode = 'client-wide' if not mailbox_id else f'mailbox {mailbox_id}'
        logger.info(f"ThreadTracker initialized ({mode}, client {self.client_id})")

    def evaluate_threads(self, limit: Optional[int] = None) -> List[ThreadStatus]:
        """
        Evaluate status of all email threads.

        Preloads junction table data into memory for fast company/contact resolution,
        then evaluates threads and saves in batches (no 91K buffer).
        """
        logger.info("Starting thread evaluation")

        # Preload junction table data: email_id → {contact_id, company_id}
        self._preload_junction_cache()

        # Preload AI intent data: email_id → {intent, urgency, sentiment}
        self._preload_intent_cache()

        # Fetch all threads
        threads = self._fetch_threads(limit=limit)
        total_threads = len(threads)

        logger.info(f"Evaluating and saving {total_threads} threads")

        MAX_THREAD_SIZE = 200
        skipped_large = 0
        processed_count = 0
        saved_count = 0
        batch_buffer: list = []
        SAVE_BATCH_SIZE = 500
        status_counts: dict = {}

        for thread_id, emails in threads.items():
            if len(emails) > MAX_THREAD_SIZE:
                skipped_large += 1
                continue

            emails.sort(key=lambda e: e['sent_date'])
            status = self._evaluate_thread_status(thread_id, emails)
            batch_buffer.append(status)
            status_counts[status.status] = status_counts.get(status.status, 0) + 1

            processed_count += 1

            # Save in batches during evaluation (don't buffer 91K in memory)
            if len(batch_buffer) >= SAVE_BATCH_SIZE:
                result = self.save_thread_statuses(batch_buffer)
                saved_count += result.get('created_count', 0)
                batch_buffer = []
                logger.info(f"Evaluated {processed_count}/{total_threads}, saved {saved_count}")

        # Save remaining
        if batch_buffer:
            result = self.save_thread_statuses(batch_buffer)
            saved_count += result.get('created_count', 0)

        if skipped_large:
            logger.warning(f"Skipped {skipped_large} oversized threads (>{MAX_THREAD_SIZE} emails)")

        logger.info(f"Thread evaluation complete: {saved_count} saved. Status breakdown: {status_counts}")

        return []  # Already saved — no need to return full list

    def _preload_junction_cache(self):
        """Preload email_contact_links into memory for fast company/contact resolution.

        Builds: self._junction_cache: dict[email_id] → list of {contact_id, company_id}
        """
        self._junction_cache: Dict[str, List[Dict]] = {}
        try:
            offset = 0
            total = 0
            while True:
                resp = self.client.table('email_contact_links').select(
                    'email_id, contact_id, company_id'
                ).eq('client_id', self.client_id).range(offset, offset + 999).execute()
                rows = resp.data or []
                if not rows:
                    break
                for r in rows:
                    eid = r.get('email_id')
                    if eid:
                        if eid not in self._junction_cache:
                            self._junction_cache[eid] = []
                        self._junction_cache[eid].append({
                            'contact_id': r.get('contact_id'),
                            'company_id': r.get('company_id'),
                        })
                total += len(rows)
                offset += len(rows)
                if total % 50000 == 0:
                    logger.info(f"Junction cache loading: {total} links loaded")

            logger.info(f"Junction cache loaded: {total} links for {len(self._junction_cache)} emails")
        except Exception as e:
            logger.warning(f"Failed to preload junction cache (will use email FK fallback): {e}")
            self._junction_cache = {}

    def _preload_intent_cache(self):
        """Preload ai_email_intelligence into memory for fast intent lookup.

        Builds: self._intent_cache: dict[email_id] → {intent, urgency, sentiment, business_signal, action_type}
        Only loads completed classifications.
        """
        self._intent_cache: Dict[str, Dict] = {}
        try:
            offset = 0
            total = 0
            while True:
                resp = self.client.table('ai_email_intelligence').select(
                    'email_id, intent, urgency, sentiment, business_signal, action_type'
                ).eq('client_id', self.client_id).eq(
                    'processing_status', 'completed'
                ).range(offset, offset + 999).execute()
                rows = resp.data or []
                if not rows:
                    break
                for r in rows:
                    eid = r.get('email_id')
                    if eid:
                        self._intent_cache[eid] = {
                            'intent': r.get('intent'),
                            'urgency': r.get('urgency'),
                            'sentiment': r.get('sentiment'),
                            'business_signal': r.get('business_signal'),
                            'action_type': r.get('action_type'),
                        }
                total += len(rows)
                offset += len(rows)
                if total % 50000 == 0:
                    logger.info(f"Intent cache loading: {total} classifications loaded")

            logger.info(f"Intent cache loaded: {total} classifications for {len(self._intent_cache)} emails")
        except Exception as e:
            logger.warning(f"Failed to preload intent cache (threads will use timing-only status): {e}")
            self._intent_cache = {}

    def _apply_intent_override(self, status: str, last_email: dict) -> tuple:
        """Apply intent-based status override using cached AI classification.

        Returns: (intent_status, intent_override_reason, last_email_intent,
                  last_email_urgency, last_email_sentiment)

        intent_status supplements (not replaces) the timing-based status.
        """
        intent_cache = getattr(self, '_intent_cache', {})
        last_intent_data = intent_cache.get(last_email.get('id'))

        if not last_intent_data:
            return None, None, None, None, None

        intent = last_intent_data.get('intent')
        urgency = last_intent_data.get('urgency')
        sentiment = last_intent_data.get('sentiment')

        intent_status = None
        reason = None

        # Override rules (ordered by priority):

        # 1. Complaint/churn with high urgency → urgent
        if intent in ('complaint', 'churn_risk') or urgency in ('critical', 'high'):
            intent_status = 'urgent'
            reason = f"Last email intent: {intent}, urgency: {urgency}"

        # 2. Pricing inquiry / expansion signal → revenue_opportunity
        elif intent in ('pricing_inquiry', 'expansion_signal', 'feature_request'):
            intent_status = 'revenue_opportunity'
            reason = f"Last email shows {intent}"

        # 3. Positive feedback / FYI on a thread that timing says "awaiting" → closing
        elif intent in ('positive_feedback', 'fyi_update') and status in (
            'awaiting_our_response', 'awaiting_response'
        ):
            intent_status = 'closing'
            reason = f"Last email is {intent} — thread naturally concluding"

        # 4. Action required → escalation (if we haven't responded)
        elif intent == 'action_required' and status != 'ongoing':
            intent_status = 'escalation'
            reason = f"Action required by contact, current status: {status}"

        # 5. Meeting/follow-up/introduction → informational
        elif intent in ('meeting_scheduling', 'follow_up', 'introduction', 'other'):
            intent_status = 'informational'
            reason = None  # No override, just metadata

        return intent_status, reason, intent, urgency, sentiment

    def _fetch_threads(self, limit: Optional[int] = None) -> Dict[str, List[Dict]]:
        """
        Fetch all emails grouped by thread_id.

        In client-wide mode, fetches per-mailbox (using indexed mailbox_id) then merges.
        This avoids timeout on unindexed client_id scans across 261K+ emails.

        Args:
            limit: Optional limit for testing

        Returns:
            Dict mapping thread_id to list of email dicts
        """
        PAGE_SIZE = 500  # Larger pages reduce API calls (was 200, caused timeouts on 160K+ mailboxes)
        COLUMNS = ('id, thread_id, canonical_thread_id, subject, subject_normalized, sent_date, is_outbound, '
                   'customer_contact_id, customer_company_id, processing_status, folder_path')
        EXCLUDED_FOLDERS = {'trash', 'junk', 'spam', 'deleted items', 'deleted',
                            'junk email', 'junk e-mail', 'drafts', 'draft'}

        threads: Dict[str, List[Dict]] = {}
        total_emails = 0
        self._mailbox_errors: List[Dict] = []  # Track fetch failures per mailbox

        # Determine which mailboxes to process
        if self.client_id and not self.mailbox_id:
            # Client-wide: get all mailbox IDs, process each
            mb_resp = self.client.table('mailboxes').select('id').eq(
                'client_id', self.client_id
            ).execute()
            mailbox_ids = [m['id'] for m in (mb_resp.data or [])]
        else:
            mailbox_ids = [self.mailbox_id]

        try:
            for mb_idx, mb_id in enumerate(mailbox_ids):
                offset = 0
                mb_count = 0

                while True:
                    import time as _time
                    try:
                        response = (
                            self.client.table('emails')
                            .select(COLUMNS)
                            .eq('mailbox_id', mb_id)
                            .order('sent_date', desc=False)
                            .range(offset, offset + PAGE_SIZE - 1)
                            .execute()
                        )
                    except Exception as fetch_err:
                        logger.warning(f"Thread fetch retry at offset {offset}: {fetch_err}")
                        _time.sleep(2)
                        try:
                            response = (
                                self.client.table('emails')
                                .select(COLUMNS)
                                .eq('mailbox_id', mb_id)
                                .order('sent_date', desc=False)
                                .range(offset, offset + PAGE_SIZE - 1)
                                .execute()
                            )
                        except Exception as e2:
                            logger.error(f"Thread fetch failed at offset {offset}, skipping rest of mailbox")
                            self._mailbox_errors.append({
                                'mailbox_id': mb_id,
                                'offset': offset,
                                'emails_fetched': mb_count,
                                'error': str(e2)[:200],
                            })
                            break
                    batch = response.data or []
                    if not batch:
                        break

                    for e in batch:
                        if e.get('processing_status') == 'failed':
                            continue
                        if (e.get('folder_path') or '').lower() in EXCLUDED_FOLDERS:
                            continue
                        # Prefer canonical_thread_id (cross-mailbox resolved), fall back to thread_id
                        tid = e.get('canonical_thread_id') or e.get('thread_id')
                        if not tid:
                            continue
                        if not tid:
                            continue
                        if tid not in threads:
                            threads[tid] = []
                        threads[tid].append(e)
                        mb_count += 1

                    offset += len(batch)

                    if limit and sum(len(v) for v in threads.values()) >= limit:
                        break

                total_emails += mb_count
                if len(mailbox_ids) > 1:
                    logger.info(f"Mailbox {mb_idx + 1}/{len(mailbox_ids)}: "
                                f"{mb_count} emails, {len(threads)} threads so far")

            # Sort each thread's emails by sent_date
            for tid in threads:
                threads[tid].sort(key=lambda e: e.get('sent_date', ''))

            logger.info(f"Fetched {total_emails} emails in {len(threads)} threads "
                        f"across {len(mailbox_ids)} mailboxes")

            # Merge threads with same subject (canonical resolution may create duplicates
            # when emails from different mailboxes get different canonical_thread_ids)
            threads = self._merge_threads_by_subject(threads)

            return threads

        except Exception as e:
            logger.error(f"Failed to fetch threads: {e}")
            raise

    def _merge_threads_by_subject(self, threads: Dict[str, List[Dict]]) -> Dict[str, List[Dict]]:
        """Merge threads that share the same subject_normalized.

        When the same conversation exists in multiple mailboxes, each mailbox may
        assign a different thread_id (different provider_thread_id or heuristic).
        Merging by normalized subject consolidates them into one logical thread.

        Only merges threads with ≤50 emails each (avoids merging unrelated bulk subjects).
        """
        import re
        PREFIX_RE = re.compile(r'^(?:\s*(?:Re|Fwd|Fw|AW|SV|TR|RES|Rif)\s*:\s*)+', re.IGNORECASE)

        def normalize(s: str) -> str:
            if not s:
                return ''
            return ' '.join(PREFIX_RE.sub('', s).strip().lower().split())

        # Group thread_ids by normalized subject
        subject_to_tids: Dict[str, List[str]] = {}
        for tid, emails in threads.items():
            # Try subject_normalized first, then normalize the raw subject
            subj = ''
            for e in emails:
                subj = (e.get('subject_normalized') or '').strip().lower()
                if subj:
                    break
            if not subj:
                subj = normalize(emails[0].get('subject', ''))
            if not subj or len(subj) < 5:
                continue
            if subj not in subject_to_tids:
                subject_to_tids[subj] = []
            subject_to_tids[subj].append(tid)

        # Merge groups with >1 thread_id
        merged_count = 0
        for subj, tids in subject_to_tids.items():
            if len(tids) <= 1:
                continue
            # Don't merge if total emails would be too large (unrelated generic subjects)
            total_emails = sum(len(threads[t]) for t in tids if t in threads)
            if total_emails > 200:
                continue

            # Pick the thread_id with the most emails as the canonical one
            canonical = max(tids, key=lambda t: len(threads.get(t, [])))
            for tid in tids:
                if tid != canonical and tid in threads:
                    threads[canonical].extend(threads[tid])
                    del threads[tid]
                    merged_count += 1

            # Re-sort merged thread
            threads[canonical].sort(key=lambda e: e.get('sent_date', ''))

        if merged_count:
            logger.info(f"Merged {merged_count} duplicate threads by subject → {len(threads)} unique threads")

        return threads

    def _evaluate_thread_status(self, thread_id: str, emails: List[Dict]) -> ThreadStatus:
        """
        Evaluate status of a single thread

        Args:
            thread_id: Thread ID
            emails: Sorted list of emails in thread (by sent_date)

        Returns:
            ThreadStatus object
        """
        if not emails:
            raise ValueError(f"Thread {thread_id} has no emails")

        # Get last email
        last_email = emails[-1]
        last_email_date = datetime.fromisoformat(last_email['sent_date'].replace('Z', '+00:00'))
        last_is_outbound = last_email.get('is_outbound', False)

        # Calculate days since last email
        now = datetime.utcnow()
        days_since_last = (now - last_email_date.replace(tzinfo=None)).days

        # Calculate thread depth (number of direction changes)
        thread_depth = self._calculate_thread_depth(emails)

        # Determine primary contact and company (most frequent in thread)
        primary_contact_id, primary_company_id = self._get_primary_entities(emails)

        # Determine thread status
        status = self._determine_status(
            emails=emails,
            last_is_outbound=last_is_outbound,
            days_since_last=days_since_last,
            thread_depth=thread_depth
        )

        # Check if overdue
        is_overdue = days_since_last > self.OVERDUE_DAYS and status in ['awaiting_response', 'awaiting_our_response']

        # Apply intent-based override from AI classification
        intent_status, intent_reason, last_intent, last_urgency, last_sentiment = \
            self._apply_intent_override(status, last_email)

        # Get subject from first email in thread
        subject = None
        for email in emails:
            s = email.get('subject')
            if s and s.strip():
                subject = s.strip()
                break

        return ThreadStatus(
            thread_id=thread_id,
            status=status,
            last_email_id=last_email['id'],
            last_email_date=last_email_date,
            last_sender_is_outbound=last_is_outbound,
            thread_depth=thread_depth,
            days_since_last_email=days_since_last,
            is_overdue=is_overdue,
            primary_contact_id=primary_contact_id,
            primary_company_id=primary_company_id,
            subject=subject,
            message_count=len(emails),
            intent_status=intent_status,
            intent_override_reason=intent_reason,
            last_email_intent=last_intent,
            last_email_urgency=last_urgency,
            last_email_sentiment=last_sentiment,
        )

    def _calculate_thread_depth(self, emails: List[Dict]) -> int:
        """
        Calculate thread depth (number of direction changes)

        Thread depth = number of times the direction switches (in → out or out → in)

        Args:
            emails: Sorted list of emails

        Returns:
            Thread depth count
        """
        if len(emails) <= 1:
            return 0

        depth = 0
        prev_direction = emails[0].get('is_outbound', False)

        for email in emails[1:]:
            current_direction = email.get('is_outbound', False)
            if current_direction != prev_direction:
                depth += 1
                prev_direction = current_direction

        return depth

    def _get_primary_entities(self, emails: List[Dict]) -> Tuple[Optional[str], Optional[str]]:
        """
        Get primary contact and company for thread (most frequent).

        Uses preloaded junction cache for fast in-memory lookup (includes CC/BCC),
        falling back to emails.customer_company_id if cache is empty.
        """
        contact_counts: dict = {}
        company_counts: dict = {}
        junction_cache = getattr(self, '_junction_cache', {})

        # Try preloaded junction cache first
        junction_used = False
        for email in emails:
            eid = email.get('id')
            links = junction_cache.get(eid, []) if eid else []
            for link in links:
                cid = link.get('contact_id')
                comp = link.get('company_id')
                if cid:
                    contact_counts[cid] = contact_counts.get(cid, 0) + 1
                if comp:
                    company_counts[comp] = company_counts.get(comp, 0) + 1
            if links:
                junction_used = True

        # Fallback: use emails.customer_contact_id / customer_company_id
        if not junction_used:
            for email in emails:
                contact_id = email.get('customer_contact_id')
                company_id = email.get('customer_company_id')
                if contact_id:
                    contact_counts[contact_id] = contact_counts.get(contact_id, 0) + 1
                if company_id:
                    company_counts[company_id] = company_counts.get(company_id, 0) + 1

        primary_contact_id = max(contact_counts, key=contact_counts.get) if contact_counts else None
        primary_company_id = max(company_counts, key=company_counts.get) if company_counts else None

        return primary_contact_id, primary_company_id

    def _determine_status(
        self,
        emails: List[Dict],
        last_is_outbound: bool,
        days_since_last: int,
        thread_depth: int
    ) -> str:
        """
        Determine thread status based on various factors

        Args:
            emails: List of emails in thread
            last_is_outbound: True if last email was outbound
            days_since_last: Days since last email
            thread_depth: Number of direction changes

        Returns:
            Status string (complete/awaiting_response/awaiting_our_response/overdue/dropped/ongoing)
        """
        # Dropped: No activity for > 30 days
        if days_since_last > self.DROPPED_DAYS:
            return 'dropped'

        # Ongoing: Active conversation (last email within 3 days)
        if days_since_last <= self.ACTIVE_THREAD_DAYS:
            return 'ongoing'

        # Complete: Natural end with good back-and-forth
        # (Inbound as last email with sufficient depth)
        if not last_is_outbound and thread_depth >= self.MIN_DEPTH_FOR_COMPLETE:
            if days_since_last > self.ACTIVE_THREAD_DAYS and days_since_last <= self.OVERDUE_DAYS:
                return 'complete'

        # Overdue: Waiting too long
        if days_since_last > self.OVERDUE_DAYS:
            return 'overdue'

        # Awaiting response from contact (we sent last)
        if last_is_outbound:
            return 'awaiting_response'

        # Awaiting our response (they sent last)
        return 'awaiting_our_response'

    def save_thread_statuses(self, thread_statuses: List[ThreadStatus]) -> Dict:
        """
        Save thread statuses to thread_status table

        Args:
            thread_statuses: List of ThreadStatus objects

        Returns:
            Save results
        """
        if not thread_statuses:
            logger.info("No thread statuses to save")
            return {'created_count': 0}

        logger.info(f"Saving {len(thread_statuses)} thread statuses to database")

        # Prepare records for insert
        records = []
        timestamp = datetime.utcnow().isoformat()

        import uuid as _uuid

        def _ensure_uuid(tid: str) -> str:
            """Convert non-UUID thread IDs (e.g. Outlook base64) to deterministic UUIDs."""
            if not tid:
                return str(_uuid.uuid4())
            try:
                _uuid.UUID(tid)  # Already a valid UUID
                return tid
            except ValueError:
                # Hash the non-UUID string into a deterministic UUID5
                return str(_uuid.uuid5(_uuid.NAMESPACE_URL, tid))

        for status in thread_statuses:
            safe_tid = _ensure_uuid(status.thread_id)
            record = {
                'thread_id': safe_tid,
                'canonical_thread_id': safe_tid,
                'mailbox_id': self.mailbox_id,  # NULL in client-wide mode
                'subject': status.subject,
                'message_count': status.message_count,
                'status': status.status,
                'last_email_id': status.last_email_id,
                'last_email_date': status.last_email_date.isoformat(),
                'last_message_at': status.last_email_date.isoformat(),
                'last_sender_is_outbound': status.last_sender_is_outbound,
                'thread_depth': status.thread_depth,
                'days_since_last_email': status.days_since_last_email,
                'is_overdue': status.is_overdue,
                'primary_contact_id': status.primary_contact_id,
                'primary_company_id': status.primary_company_id,
                'customer_contact_id': status.primary_contact_id,
                'customer_company_id': status.primary_company_id,
                # Intent-based intelligence
                'intent_status': status.intent_status,
                'intent_override_reason': status.intent_override_reason,
                'last_email_intent': status.last_email_intent,
                'last_email_urgency': status.last_email_urgency,
                'last_email_sentiment': status.last_email_sentiment,
                'created_at': timestamp,
                'updated_at': timestamp
            }
            records.append(record)

        # Dedup records before saving — same thread_id should only have one row
        deduped: dict[str, dict] = {}
        for r in records:
            tid = r['thread_id']
            existing = deduped.get(tid)
            if existing:
                # Keep higher message count
                if (r.get('message_count') or 0) > (existing.get('message_count') or 0):
                    deduped[tid] = r
            else:
                deduped[tid] = r
        records = list(deduped.values())

        # Delete-then-insert strategy: more reliable than upsert with constraint issues
        # Delete existing rows for these thread_ids, then insert fresh
        batch_size = 100
        created_count = 0
        errors = []

        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            batch_thread_ids = [r['thread_id'] for r in batch]
            try:
                # Delete existing rows for these thread_ids (any mailbox_id)
                self.client.table('thread_status').delete().in_(
                    'thread_id', batch_thread_ids
                ).execute()
                # Also delete by canonical_thread_id
                self.client.table('thread_status').delete().in_(
                    'canonical_thread_id', batch_thread_ids
                ).execute()
                # Insert fresh
                self.client.table('thread_status').insert(batch).execute()
                created_count += len(batch)
                if (i // batch_size + 1) % 10 == 0:
                    logger.info(f"Saved batch {i//batch_size + 1}: {created_count} thread statuses so far")
            except Exception as e:
                logger.error(f"Failed to save batch {i//batch_size + 1}: {e}")
                errors.append({'batch': i//batch_size + 1, 'error': str(e)})

        logger.info(f"Thread statuses saved: {created_count} records, {len(errors)} errors")

        return {
            'created_count': created_count,
            'total_statuses': len(thread_statuses),
            'errors': errors
        }

    def update_thread_counts(self) -> Dict:
        """
        Update open_thread_count and dropped_thread_count for contacts and companies

        Returns:
            Update results
        """
        logger.info("Updating thread counts for contacts and companies")

        try:
            # Update contact thread counts
            contact_results = self._update_contact_thread_counts()

            # Update company thread counts
            company_results = self._update_company_thread_counts()

            logger.info(f"Thread counts updated: {contact_results['updated_count']} contacts, "
                       f"{company_results['updated_count']} companies")

            return {
                'contacts_updated': contact_results['updated_count'],
                'companies_updated': company_results['updated_count']
            }

        except Exception as e:
            logger.error(f"Failed to update thread counts: {e}")
            raise

    def _update_contact_thread_counts(self) -> Dict:
        """
        Update thread counts for all contacts using database-side calculation

        Returns:
            Update results
        """
        logger.info("Calculating thread counts for all contacts (database-side)")

        # Calculate all thread counts in ONE database query
        calc_result = self.client.rpc(
            'calculate_all_contact_thread_counts',
            {'p_client_id': self.client_id}
        ).execute()

        calculations = calc_result.data
        logger.info(f"Calculated thread counts for {len(calculations)} contacts")

        # Prepare batch update
        updates = []
        for calc in calculations:
            updates.append({
                'contact_id': calc['contact_id'],
                'open_thread_count': str(calc['open_thread_count']),
                'dropped_thread_count': str(calc['dropped_thread_count'])
            })

        # Batch update via RPC
        if updates:
            logger.info(f"Batch updating {len(updates)} contacts with thread counts")

            result = self.client.rpc(
                'batch_update_contact_analytics',
                {'updates': updates}
            ).execute()

            updated_count = result.data[0]['updated_count'] if result.data else 0
        else:
            updated_count = 0

        return {'updated_count': updated_count}

    def _update_company_thread_counts(self) -> Dict:
        """
        Update thread counts for all companies using database-side calculation

        Returns:
            Update results
        """
        logger.info("Calculating thread counts for all companies (database-side)")

        # Calculate all thread counts in ONE database query
        calc_result = self.client.rpc(
            'calculate_all_company_thread_counts',
            {'p_client_id': self.client_id}
        ).execute()

        calculations = calc_result.data
        logger.info(f"Calculated thread counts for {len(calculations)} companies")

        # Prepare batch update
        updates = []
        for calc in calculations:
            updates.append({
                'company_id': calc['company_id'],
                'open_thread_count': str(calc['open_thread_count']),
                'dropped_thread_count': str(calc['dropped_thread_count'])
            })

        # Batch update via RPC
        if updates:
            logger.info(f"Batch updating {len(updates)} companies with thread counts")

            result = self.client.rpc(
                'batch_update_company_analytics',
                {'updates': updates}
            ).execute()

            updated_count = result.data[0]['updated_count'] if result.data else 0
        else:
            updated_count = 0

        return {'updated_count': updated_count}

    def get_thread_summary(self) -> Dict:
        """
        Get summary statistics of thread statuses

        Returns:
            Dictionary with thread statistics
        """
        try:
            # Get status counts
            response = (
                self.client.table('thread_status')
                .select('status')
                .execute()
            )

            statuses = response.data

            # Count by status
            status_counts = {}
            for status in statuses:
                status_type = status['status']
                status_counts[status_type] = status_counts.get(status_type, 0) + 1

            # Count overdue threads
            overdue_response = (
                self.client.table('thread_status')
                .select('id', count='exact')
                .eq('is_overdue', 'true')  # PostgREST expects lowercase string
                .execute()
            )

            overdue_count = overdue_response.count

            return {
                'total_threads': len(statuses),
                'status_breakdown': status_counts,
                'overdue_threads': overdue_count
            }

        except Exception as e:
            logger.error(f"Failed to get thread summary: {e}")
            return {
                'total_threads': 0,
                'status_breakdown': {},
                'overdue_threads': 0
            }

    def get_health_report(self) -> Dict:
        """Return thread processing health metrics including fetch errors and intent coverage.

        Designed for the Data Health page — shows per-mailbox status and
        intent classification coverage.
        """
        mailbox_errors = getattr(self, '_mailbox_errors', [])

        # Get intent coverage from thread_status
        intent_coverage = {'with_intent': 0, 'without_intent': 0, 'coverage_pct': 0.0}
        try:
            total_resp = self.client.table('thread_status').select(
                'id', count='exact'
            ).eq('client_id', self.client_id).execute()
            total = total_resp.count or 0

            with_intent_resp = self.client.table('thread_status').select(
                'id', count='exact'
            ).eq('client_id', self.client_id).not_.is_(
                'last_email_intent', 'null'
            ).execute()
            with_intent = with_intent_resp.count or 0

            intent_coverage = {
                'with_intent': with_intent,
                'without_intent': total - with_intent,
                'coverage_pct': round(with_intent / total * 100, 1) if total > 0 else 0.0,
            }
        except Exception as e:
            logger.warning(f"Failed to compute intent coverage: {e}")

        return {
            'mailbox_errors': mailbox_errors,
            'intent_coverage': intent_coverage,
        }


# Example usage
if __name__ == '__main__':
    import sys

    if len(sys.argv) < 3:
        print("Usage: python -m backend.src.services.thread_tracker <mailbox_id> <client_id>")
        sys.exit(1)

    mailbox_id = sys.argv[1]
    client_id = sys.argv[2]

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Track threads
    tracker = ThreadTracker(mailbox_id=mailbox_id, client_id=client_id)

    # Evaluate thread statuses
    thread_statuses = tracker.evaluate_threads()

    # Save to database
    save_results = tracker.save_thread_statuses(thread_statuses)

    # Update thread counts
    update_results = tracker.update_thread_counts()

    # Print summary
    summary = tracker.get_thread_summary()
    print("\n=== Thread Tracking Summary ===")
    print(f"Total threads: {summary['total_threads']}")
    print("\nStatus breakdown:")
    for status, count in summary['status_breakdown'].items():
        print(f"  {status}: {count}")
    print(f"\nOverdue threads: {summary['overdue_threads']}")

    print(f"\nThread statuses evaluated: {len(thread_statuses)}")
    print(f"Statuses saved: {save_results['created_count']}")
    print(f"Contacts updated: {update_results['contacts_updated']}")
    print(f"Companies updated: {update_results['companies_updated']}")
