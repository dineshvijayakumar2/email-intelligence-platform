"""
Response Time Tracker Service - Sprint 2 Phase 4

Purpose: Calculate and track email response times for engagement analytics
Part of 13-step extraction pipeline (used in Step 11)

Features:
- Calculates response times between inbound-outbound email pairs
- Detects auto-replies (Out of Office, vacation responders)
- Tracks bidirectional response times (you → them, them → you)
- Populates email_response_metrics table
- Updates contact/company avg_response_time fields

Author: Sprint 2 Implementation
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import re

from ..database.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)


@dataclass
class ResponseMetric:
    """Response time metric for an email pair"""
    email_id: str
    responding_to_email_id: str
    response_time_seconds: int
    is_auto_reply: bool
    responder_contact_id: Optional[str]
    responder_company_id: Optional[str]


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

        logger.info(f"ResponseTimeTracker initialized for mailbox {mailbox_id}")

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
        Fetch all emails grouped by thread_id, paginating in batches of 500.

        Args:
            limit: Optional limit for testing

        Returns:
            Dict mapping thread_id to list of email dicts
        """
        PAGE_SIZE = 500
        COLUMNS = ('id, thread_id, sent_date, subject, is_outbound, '
                   'customer_contact_id, customer_company_id, raw_headers')
        try:
            all_emails = []
            offset = 0

            while True:
                query = (
                    self.client.table('emails')
                    .select(COLUMNS)
                    .eq('mailbox_id', self.mailbox_id)
                    .or_('processing_status.neq.failed,processing_status.is.null')
                    .not_.is_('thread_id', 'null')
                    .order('sent_date', desc=False)
                )

                if limit and limit <= PAGE_SIZE:
                    query = query.limit(limit)
                    response = query.execute()
                    all_emails = response.data or []
                    break

                response = query.range(offset, offset + PAGE_SIZE - 1).execute()
                batch = response.data or []
                all_emails.extend(batch)

                if len(batch) < PAGE_SIZE:
                    break
                offset += PAGE_SIZE

                if limit and len(all_emails) >= limit:
                    all_emails = all_emails[:limit]
                    break

            # Group by thread_id
            threads = {}
            for email in all_emails:
                thread_id = email['thread_id']
                if thread_id not in threads:
                    threads[thread_id] = []
                threads[thread_id].append(email)

            logger.info(f"Fetched {len(all_emails)} emails in {len(threads)} threads")

            return threads

        except Exception as e:
            logger.error(f"Failed to fetch threads: {e}")
            raise

    def _find_response_pairs(self, emails: List[Dict]) -> List[ResponseMetric]:
        """
        Find response pairs within a thread

        A response pair is defined as:
        - Inbound email followed by outbound email (we responded)
        - Outbound email followed by inbound email (they responded)

        Args:
            emails: Sorted list of emails in thread (by sent_date)

        Returns:
            List of ResponseMetric objects
        """
        metrics = []

        for i in range(len(emails) - 1):
            current_email = emails[i]
            next_email = emails[i + 1]

            current_outbound = current_email.get('is_outbound', False)
            next_outbound = next_email.get('is_outbound', False)

            # Check if this is a response pair (direction changed)
            if current_outbound != next_outbound:
                # Calculate response time
                current_time = datetime.fromisoformat(current_email['sent_date'].replace('Z', '+00:00'))
                next_time = datetime.fromisoformat(next_email['sent_date'].replace('Z', '+00:00'))

                response_time_seconds = int((next_time - current_time).total_seconds())

                # Ignore negative response times (data error) or unreasonably long times
                if response_time_seconds <= 0 or response_time_seconds > self.MAX_RESPONSE_TIME_SECONDS:
                    continue

                # Check if response is auto-reply
                is_auto_reply = self._is_auto_reply(next_email)

                # Create metric
                metric = ResponseMetric(
                    email_id=next_email['id'],
                    responding_to_email_id=current_email['id'],
                    response_time_seconds=response_time_seconds,
                    is_auto_reply=is_auto_reply,
                    responder_contact_id=next_email.get('customer_contact_id'),
                    responder_company_id=next_email.get('customer_company_id')
                )

                metrics.append(metric)

        return metrics

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
        Update avg_response_time_seconds for all contacts based on response metrics

        Uses database-side calculation + batch update for maximum performance
        - Before: 744 individual SELECT queries + 744 UPDATEs (~5 minutes)
        - After: 1 calculation query + 1 batch UPDATE (~2 seconds)

        Calculates average response time for:
        - Outbound → Inbound (their response time to us)
        - Inbound → Outbound (our response time to them)

        Returns:
            Update results
        """
        logger.info("Updating contact average response times (database-side calculation)")

        try:
            # Calculate all averages in ONE database query
            logger.info(f"Calculating all contact response times on database...")

            calc_result = self.client.rpc(
                'calculate_all_contact_response_times',
                {'p_client_id': self.client_id}
            ).execute()

            calculations = calc_result.data
            logger.info(f"Calculated response times for {len(calculations)} contacts")

            # Prepare batch update
            updates = []
            for calc in calculations:
                updates.append({
                    'contact_id': calc['contact_id'],
                    'avg_response_time_seconds': str(calc['avg_response_time_seconds']),
                    'their_avg_response_time': str(calc['their_avg_response_time'])
                })

            # Batch update via RPC
            if updates:
                logger.info(f"Batch updating {len(updates)} contacts with response times")

                result = self.client.rpc(
                    'batch_update_contact_analytics',
                    {'updates': updates}
                ).execute()

                updated_count = result.data[0]['updated_count'] if result.data else 0

                logger.info(f"Contact response times updated: {updated_count} contacts (database-calculated)")
            else:
                updated_count = 0
                logger.info("No contacts with response time data to update")

            return {
                'total_contacts': len(calculations),
                'updated_count': updated_count
            }

        except Exception as e:
            logger.error(f"Failed to update contact averages: {e}")
            raise

    def _calculate_contact_response_times(self, contact_id: str) -> Tuple[Optional[int], Optional[int]]:
        """
        Calculate average response times for a contact

        Args:
            contact_id: Contact UUID

        Returns:
            Tuple of (our_avg_response_time, their_avg_response_time) in seconds
        """
        try:
            # Get all response metrics for this contact
            response = (
                self.client.table('email_response_metrics')
                .select('response_time_seconds, is_auto_reply')
                .eq('responder_contact_id', contact_id)
                .eq('is_auto_reply', 'false')  # Exclude auto-replies (PostgREST expects lowercase string)
                .execute()
            )

            metrics = response.data

            if not metrics:
                return None, None

            # Calculate average (simple average for now, could be weighted by recency)
            total_time = sum(m['response_time_seconds'] for m in metrics)
            avg_time = int(total_time / len(metrics))

            # For now, we'll use same value for both directions
            # TODO: Separate by direction in future enhancement

            return avg_time, avg_time

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
