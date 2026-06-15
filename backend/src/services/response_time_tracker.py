"""
Response Time Tracker Service - Sprint 2 Phase 4

Purpose: Calculate and track email response times for engagement analytics
Part of 13-step extraction pipeline (used in Step 11)

Features:
- Calculates response times between inbound-outbound email pairs
- Pairs within the CANONICAL thread (not the raw provider thread_id) and validates each pair
  is the same conversation — prevents cross-conversation mis-pairs that produced implausibly
  fast latencies for some mailboxes (15.3c)
- Detects auto-replies (Out of Office, vacation responders) and excludes automated/no-reply
  senders from anchoring a pair
- Tracks bidirectional response times (you → them, them → you)
- Populates email_response_metrics table
- Updates contact/company avg_response_time fields

Author: Sprint 2 Implementation
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import logging
import re
import json

from ..database.supabase_client import SupabaseClient
from ..utils.business_hours import calculate_business_seconds

logger = logging.getLogger(__name__)


@dataclass
class BusinessHoursConfig:
    """Business hours configuration for a user"""
    timezone: str = "UTC"
    business_hours_start: int = 9
    business_hours_end: int = 18
    business_days: list = field(default_factory=lambda: [1, 2, 3, 4, 5])


@dataclass
class ResponseMetric:
    """Response time metric for an email pair"""
    email_id: str
    responding_to_email_id: str
    response_time_seconds: int
    is_auto_reply: bool
    responder_contact_id: Optional[str]
    responder_company_id: Optional[str]
    business_hours_response_time_seconds: Optional[int] = None


class ResponseTimeTracker:
    """
    Track and calculate email response times for engagement analytics

    Usage:
        tracker = ResponseTimeTracker(mailbox_id="uuid-here", client_id="uuid-here")
        metrics = tracker.calculate_response_times()
        tracker.save_metrics(metrics)
        tracker.update_contact_averages()
    """

    # Auto-reply detection patterns
    AUTO_REPLY_SUBJECT_PATTERNS = [
        r'out of office',
        r'out of the office',
        r'automatic reply',
        r'auto reply',
        r'auto-reply',
        r'autoreply',
        r'vacation',
        r'away from office',
        r'currently out',
        r'i am away',
        r'i\'m away',
        r'absence notification',
        r'delivery status notification',
        r'mail delivery failed',
        r'undeliverable',
    ]

    # Auto-reply header markers
    AUTO_REPLY_HEADERS = [
        'X-Autoreply',
        'X-Autorespond',
        'Auto-Submitted',
        'X-Auto-Response-Suppress',
    ]

    # Automated / no-reply / system senders. An inbound from one of these is not a genuine
    # human message to respond to, so it must not anchor a response pair (15.3c). These
    # senders (couriers, mailer-daemon, notification bots) formed spurious near-instant
    # "reply" pairs once the canonical-thread grouping put them next to an unrelated outbound.
    AUTOMATED_SENDER_PATTERNS = [
        r'no-?reply',
        r'do-?not-?reply',
        r'donotreply',
        r'mailer-?daemon',
        r'postmaster@',
        r'notifications?@',
        r'@notifications?\.',
        r'bounces?@',
    ]

    # Maximum reasonable response time (7 days)
    MAX_RESPONSE_TIME_SECONDS = 7 * 24 * 60 * 60

    def __init__(self, mailbox_id: str, client_id: str):
        """
        Initialize response time tracker

        Args:
            mailbox_id: Mailbox UUID to track responses for
            client_id: Client UUID for filtering
        """
        self.mailbox_id = mailbox_id
        self.client_id = client_id
        self.client = SupabaseClient.get_client(use_service_key=True)
        self._bh_config: Optional[BusinessHoursConfig] = None

        logger.info(f"ResponseTimeTracker initialized for mailbox {mailbox_id}")

    def _get_business_hours_config(self) -> BusinessHoursConfig:
        """
        Fetch business hours config for the mailbox.

        Timezone is sourced from clients.timezone (the authoritative zone for the client this
        mailbox belongs to) — NOT user_profiles.timezone. user_profiles.timezone defaults to
        'UTC' and is not maintained per AM; sourcing the zone from there caused the historical
        backfill to evaluate business hours in UTC, zeroing ~85% of
        business_hours_response_time_seconds for Carbon8 (Australia/Sydney). See
        scripts/db/_recompute_bh_response_time.py for the one-off repair of that backlog.

        The business-hours WINDOW (start/end) and business_days still come from user_profiles
        (mailbox owner), falling back to 9-18 Mon-Fri. Cached per tracker instance.
        """
        if self._bh_config is not None:
            return self._bh_config

        tz_name = 'UTC'
        bh_start, bh_end, business_days = 9, 18, [1, 2, 3, 4, 5]

        try:
            # Authoritative timezone: the client this mailbox belongs to.
            cl = (
                self.client.table('clients')
                .select('timezone')
                .eq('id', self.client_id)
                .limit(1)
                .execute()
            )
            if cl.data and cl.data[0].get('timezone'):
                tz_name = cl.data[0]['timezone']

            # Business-hours window/days: mailbox owner's profile (if set).
            mb = (
                self.client.table('mailboxes')
                .select('user_id')
                .eq('id', self.mailbox_id)
                .limit(1)
                .execute()
            )
            user_id = (mb.data[0]['user_id'] if mb.data else None)
            if user_id:
                up = (
                    self.client.table('user_profiles')
                    .select('business_hours_start, business_hours_end, business_days')
                    .eq('id', user_id)
                    .limit(1)
                    .execute()
                )
                if up.data:
                    row = up.data[0]
                    bh_start = row.get('business_hours_start', 9)
                    bh_end = row.get('business_hours_end', 18)
                    business_days = row.get('business_days') or [1, 2, 3, 4, 5]
        except Exception as e:
            logger.warning(f"Could not fetch business hours config (using {tz_name} {bh_start}-{bh_end}): {e}")

        self._bh_config = BusinessHoursConfig(
            timezone=tz_name,
            business_hours_start=bh_start,
            business_hours_end=bh_end,
            business_days=business_days,
        )
        logger.info(f"Business hours config: tz={self._bh_config.timezone} (from clients.timezone) "
                    f"{self._bh_config.business_hours_start}-{self._bh_config.business_hours_end}")
        return self._bh_config

    def calculate_response_times(self, limit: Optional[int] = None) -> List[ResponseMetric]:
        """
        Calculate response times for all email pairs in threads

        Args:
            limit: Optional limit for testing

        Returns:
            List of ResponseMetric objects
        """
        logger.info("Starting response time calculation")

        # Fetch all emails grouped by thread
        threads = self._fetch_threads(limit=limit)
        total_threads = len(threads)

        logger.info(f"Processing {total_threads} threads for response time calculation")

        metrics = []
        processed_count = 0

        for thread_id, emails in threads.items():
            # Sort emails by sent_date
            emails.sort(key=lambda e: e['sent_date'])

            # Find response pairs in thread
            thread_metrics = self._find_response_pairs(emails)
            metrics.extend(thread_metrics)

            processed_count += 1
            if processed_count % 100 == 0:
                logger.info(f"Processed {processed_count}/{total_threads} threads, "
                           f"found {len(metrics)} response pairs")

        logger.info(f"Response time calculation complete: {len(metrics)} response pairs found")

        return metrics

    def _fetch_threads(self, limit: Optional[int] = None) -> Dict[str, List[Dict]]:
        """
        Fetch all emails grouped by canonical_thread_id, paginating in batches of 500.

        Grouping is by canonical_thread_id (the 4-tier resolved conversation), NOT the raw
        provider thread_id (15.3c). For some mailboxes the provider thread_id over-collapses
        distinct conversations, so pairing consecutive direction-changes inside a provider
        thread manufactured cross-conversation "reply" pairs with implausibly fast latencies
        (e.g. an inbound courier notification paired with an unrelated outbound quote seconds
        later). canonical_thread_id is populated before this runs in the live pipeline
        (orchestrator._assign_canonical_threads, step 9, precedes the engagement step 10).

        Args:
            limit: Optional limit for testing

        Returns:
            Dict mapping canonical_thread_id to list of email dicts
        """
        PAGE_SIZE = 500
        COLUMNS = ('id, thread_id, canonical_thread_id, sent_date, subject, subject_normalized, '
                   'sender_email, recipients, is_outbound, customer_contact_id, '
                   'customer_company_id, raw_headers, processing_status')
        try:
            all_emails = []
            offset = 0

            while True:
                query = (
                    self.client.table('emails')
                    .select(COLUMNS)
                    .eq('mailbox_id', self.mailbox_id)
                    .not_.is_('canonical_thread_id', 'null')
                    .order('sent_date', desc=False)
                )

                if limit and limit <= PAGE_SIZE:
                    query = query.limit(limit)
                    response = query.execute()
                    all_emails = [e for e in (response.data or []) if e.get('processing_status') != 'failed']
                    break

                response = query.range(offset, offset + PAGE_SIZE - 1).execute()
                batch = response.data or []
                filtered = [e for e in batch if e.get('processing_status') != 'failed']
                all_emails.extend(filtered)

                if len(batch) == 0:
                    break
                offset += len(batch)

                if limit and len(all_emails) >= limit:
                    all_emails = all_emails[:limit]
                    break

            # Group by canonical_thread_id (resolved conversation), not provider thread_id.
            threads = {}
            for email in all_emails:
                ct_id = email.get('canonical_thread_id')
                if not ct_id:
                    continue
                threads.setdefault(ct_id, []).append(email)

            logger.info(f"Fetched {len(all_emails)} emails in {len(threads)} canonical threads")

            return threads

        except Exception as e:
            logger.error(f"Failed to fetch threads: {e}")
            raise

    def _find_response_pairs(self, emails: List[Dict]) -> List[ResponseMetric]:
        """
        Find response pairs within a canonical thread.

        A response pair is a consecutive direction change in the thread:
        - Inbound email followed by outbound email (we responded)
        - Outbound email followed by inbound email (they responded)

        where ``current_email`` is the message being responded to and ``next_email`` is the
        responding message. Two validity gates guard against spurious pairs (15.3c):

        1. The message being responded to must be a genuine human message — not an
           auto-reply/OOO and not from an automated/no-reply sender (couriers, mailer-daemon,
           notification bots). These anchored near-instant fake "replies".
        2. The pair must be the same conversation — the reply's normalized subject matches the
           original, OR the reply is addressed back to the original sender. This catches
           over-merged canonical threads that interleave unrelated sub-conversations.

        Args:
            emails: Sorted list of emails in the canonical thread (by sent_date)

        Returns:
            List of ResponseMetric objects
        """
        metrics = []

        for i in range(len(emails) - 1):
            current_email = emails[i]
            next_email = emails[i + 1]

            current_outbound = current_email.get('is_outbound', False)
            next_outbound = next_email.get('is_outbound', False)

            # Must be a direction change to be a response pair
            if current_outbound == next_outbound:
                continue

            # Gate 1: the message being responded to must be a genuine human message.
            if (self._is_auto_reply(current_email)
                    or self._is_automated_sender(current_email.get('sender_email'))):
                continue

            # Gate 2: the pair must be the same conversation.
            if not (self._subjects_match(current_email, next_email)
                    or self._reply_addressed_back(current_email, next_email)):
                continue

            # Calculate response time
            current_time = datetime.fromisoformat(current_email['sent_date'].replace('Z', '+00:00'))
            next_time = datetime.fromisoformat(next_email['sent_date'].replace('Z', '+00:00'))

            response_time_seconds = int((next_time - current_time).total_seconds())

            # Ignore negative response times (data error) or unreasonably long times
            if response_time_seconds <= 0 or response_time_seconds > self.MAX_RESPONSE_TIME_SECONDS:
                continue

            # Check if response is auto-reply (stored flag; metric consumers filter on it)
            is_auto_reply = self._is_auto_reply(next_email)

            # Calculate business hours response time
            bh_config = self._get_business_hours_config()
            bh_seconds = calculate_business_seconds(
                start_utc=current_time,
                end_utc=next_time,
                tz_name=bh_config.timezone,
                bh_start=bh_config.business_hours_start,
                bh_end=bh_config.business_hours_end,
                business_days=bh_config.business_days,
            )

            # Create metric
            metric = ResponseMetric(
                email_id=next_email['id'],
                responding_to_email_id=current_email['id'],
                response_time_seconds=response_time_seconds,
                is_auto_reply=is_auto_reply,
                responder_contact_id=next_email.get('customer_contact_id'),
                responder_company_id=next_email.get('customer_company_id'),
                business_hours_response_time_seconds=bh_seconds,
            )

            metrics.append(metric)

        return metrics

    def _is_automated_sender(self, sender_email: Optional[str]) -> bool:
        """True if the sender address is an automated / no-reply / system mailbox."""
        if not sender_email:
            return False
        s = sender_email.lower()
        for pattern in self.AUTOMATED_SENDER_PATTERNS:
            if re.search(pattern, s):
                return True
        return False

    @staticmethod
    def _subjects_match(a: Dict, b: Dict) -> bool:
        """True if both emails share the same non-empty normalized subject (case-insensitive)."""
        sa = (a.get('subject_normalized') or '').strip().lower()
        sb = (b.get('subject_normalized') or '').strip().lower()
        return bool(sa) and sa == sb

    @staticmethod
    def _reply_addressed_back(original: Dict, reply: Dict) -> bool:
        """True if ``reply`` is addressed (in recipients) back to ``original``'s sender."""
        sender = (original.get('sender_email') or '').strip().lower()
        if not sender:
            return False
        recips = reply.get('recipients') or []
        if isinstance(recips, str):
            try:
                recips = json.loads(recips)
            except (ValueError, TypeError):
                return False
        if not isinstance(recips, list):
            return False
        for r in recips:
            if isinstance(r, dict) and (r.get('email') or '').strip().lower() == sender:
                return True
        return False

    def _is_auto_reply(self, email: Dict) -> bool:
        """
        Detect if email is an automatic reply

        Checks:
        1. Subject line patterns (Out of Office, etc.)
        2. Auto-reply headers

        Args:
            email: Email record

        Returns:
            True if email is detected as auto-reply
        """
        # Check subject line
        subject = email.get('subject', '').lower()

        for pattern in self.AUTO_REPLY_SUBJECT_PATTERNS:
            if re.search(pattern, subject, re.IGNORECASE):
                logger.debug(f"Email {email['id']} detected as auto-reply (subject pattern: {pattern})")
                return True

        # Check headers
        raw_headers = email.get('raw_headers', {})

        if raw_headers:
            for header in self.AUTO_REPLY_HEADERS:
                if header in raw_headers:
                    logger.debug(f"Email {email['id']} detected as auto-reply (header: {header})")
                    return True

            # Check Auto-Submitted header value
            auto_submitted = raw_headers.get('Auto-Submitted', '').lower()
            if auto_submitted and auto_submitted != 'no':
                logger.debug(f"Email {email['id']} detected as auto-reply (Auto-Submitted: {auto_submitted})")
                return True

        return False

    def save_metrics(self, metrics: List[ResponseMetric]) -> Dict:
        """
        Save response metrics to email_response_metrics table

        Args:
            metrics: List of ResponseMetric objects

        Returns:
            Save results
        """
        if not metrics:
            logger.info("No response metrics to save")
            return {'created_count': 0}

        logger.info(f"Saving {len(metrics)} response metrics to database")

        # Prepare records for insert
        records = []
        timestamp = datetime.utcnow().isoformat()

        for metric in metrics:
            record = {
                'email_id': metric.email_id,
                'responding_to_email_id': metric.responding_to_email_id,
                'response_time_seconds': metric.response_time_seconds,
                'is_auto_reply': metric.is_auto_reply,
                'responder_contact_id': metric.responder_contact_id,
                'responder_company_id': metric.responder_company_id,
                'business_hours_response_time_seconds': metric.business_hours_response_time_seconds,
                'created_at': timestamp,
                'updated_at': timestamp
            }
            records.append(record)

        # Batch insert
        batch_size = 100
        created_count = 0
        errors = []

        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            try:
                # Use upsert to handle duplicates
                self.client.table('email_response_metrics').upsert(
                    batch,
                    on_conflict='email_id'
                ).execute()
                created_count += len(batch)
                logger.info(f"Saved batch {i//batch_size + 1}: {len(batch)} metrics")
            except Exception as e:
                logger.error(f"Failed to save batch {i//batch_size + 1}: {e}")
                errors.append({'batch': i//batch_size + 1, 'error': str(e)})

        logger.info(f"Response metrics saved: {created_count} records, {len(errors)} errors")

        return {
            'created_count': created_count,
            'total_metrics': len(metrics),
            'errors': errors
        }

    def update_contact_averages(self) -> Dict:
        """
        Update avg_response_time_seconds / their_avg_response_time for all of the
        client's contacts based on response metrics.

        Calculation AND update both run server-side in a single RPC
        (update_all_contact_response_times, migration 122). This:
        - splits the two directions correctly:
            * outbound responding email → WE replied → avg_response_time_seconds
            * inbound  responding email → THEY replied → their_avg_response_time
        - avoids the PostgREST db-max-rows cap that previously truncated the
          calc-then-batch-update path at 1000 contacts (the older RPC RETURNED
          rows to the client; this one performs the UPDATE in SQL and returns
          only the affected-row count).

        Returns:
            Update results
        """
        logger.info("Updating contact average response times (server-side calc + update)")

        try:
            result = self.client.rpc(
                'update_all_contact_response_times',
                {'p_client_id': self.client_id}
            ).execute()

            # RPC returns a scalar INTEGER (affected row count).
            updated_count = result.data if isinstance(result.data, int) else (result.data or 0)

            logger.info(f"Contact response times updated: {updated_count} contacts (database-calculated)")

            return {
                'total_contacts': updated_count,
                'updated_count': updated_count
            }

        except Exception as e:
            logger.error(f"Failed to update contact averages: {e}")
            raise

    def _calculate_contact_response_times(self, contact_id: str) -> Tuple[Optional[int], Optional[int]]:
        """
        Calculate average response times for a contact, separated by direction.

        Args:
            contact_id: Contact UUID

        Returns:
            Tuple of (our_avg_response_time, their_avg_response_time) in seconds
            - our_avg: how long WE take to reply to their emails
            - their_avg: how long THEY take to reply to our emails
        """
        try:
            # Get response metrics with the responding email's direction
            response = (
                self.client.table('email_response_metrics')
                .select('response_time_seconds, is_auto_reply, email_id, emails!email_response_metrics_email_id_fkey(is_outbound)')
                .eq('responder_contact_id', contact_id)
                .eq('is_auto_reply', 'false')
                .execute()
            )

            metrics = response.data

            if not metrics:
                return None, None

            our_times = []
            their_times = []

            for m in metrics:
                email_data = m.get('emails')
                time_sec = m.get('response_time_seconds', 0)
                if not email_data or not time_sec:
                    continue
                if email_data.get('is_outbound') is True:
                    # Our outbound reply to their inbound
                    our_times.append(time_sec)
                else:
                    # Their inbound reply to our outbound
                    their_times.append(time_sec)

            our_avg = int(sum(our_times) / len(our_times)) if our_times else None
            their_avg = int(sum(their_times) / len(their_times)) if their_times else None

            return our_avg, their_avg

        except Exception as e:
            logger.error(f"Failed to calculate response times for contact {contact_id}: {e}")
            return None, None

    def get_response_summary(self) -> Dict:
        """
        Get summary statistics of response metrics

        Returns:
            Dictionary with response statistics
        """
        try:
            # Count total metrics
            total_response = (
                self.client.table('email_response_metrics')
                .select('id', count='exact')
                .execute()
            )

            total_metrics = total_response.count

            # Count auto-replies
            auto_reply_response = (
                self.client.table('email_response_metrics')
                .select('id', count='exact')
                .eq('is_auto_reply', 'true')  # PostgREST expects lowercase string
                .execute()
            )

            auto_reply_count = auto_reply_response.count

            return {
                'total_response_pairs': total_metrics,
                'auto_replies': auto_reply_count,
                'valid_responses': total_metrics - auto_reply_count,
                'auto_reply_rate': (auto_reply_count / total_metrics * 100) if total_metrics > 0 else 0
            }

        except Exception as e:
            logger.error(f"Failed to get response summary: {e}")
            return {
                'total_response_pairs': 0,
                'auto_replies': 0,
                'valid_responses': 0,
                'auto_reply_rate': 0
            }


# Example usage
if __name__ == '__main__':
    import sys

    if len(sys.argv) < 3:
        print("Usage: python -m backend.src.services.response_time_tracker <mailbox_id> <client_id>")
        sys.exit(1)

    mailbox_id = sys.argv[1]
    client_id = sys.argv[2]

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Track response times
    tracker = ResponseTimeTracker(mailbox_id=mailbox_id, client_id=client_id)

    # Calculate metrics
    metrics = tracker.calculate_response_times()

    # Save to database
    save_results = tracker.save_metrics(metrics)

    # Update contact averages
    update_results = tracker.update_contact_averages()

    # Print summary
    summary = tracker.get_response_summary()
    print("\n=== Response Time Summary ===")
    for key, value in summary.items():
        print(f"{key}: {value}")

    print(f"\nTotal response pairs found: {len(metrics)}")
    print(f"Metrics saved: {save_results['created_count']}")
    print(f"Contacts updated: {update_results['updated_count']}")
