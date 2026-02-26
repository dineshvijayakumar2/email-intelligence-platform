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

    def __init__(self, mailbox_id: str, client_id: str):
        """
        Initialize thread tracker

        Args:
            mailbox_id: Mailbox UUID to track threads for
            client_id: Client UUID for filtering
        """
        self.mailbox_id = mailbox_id
        self.client_id = client_id
        self.client = SupabaseClient.get_client(use_service_key=True)

        logger.info(f"ThreadTracker initialized for mailbox {mailbox_id}")

    def evaluate_threads(self, limit: Optional[int] = None) -> List[ThreadStatus]:
        """
        Evaluate status of all email threads

        Args:
            limit: Optional limit for testing

        Returns:
            List of ThreadStatus objects
        """
        logger.info("Starting thread evaluation")

        # Fetch all threads
        threads = self._fetch_threads(limit=limit)
        total_threads = len(threads)

        logger.info(f"Evaluating {total_threads} threads")

        thread_statuses = []
        processed_count = 0

        for thread_id, emails in threads.items():
            # Sort emails by sent_date
            emails.sort(key=lambda e: e['sent_date'])

            # Evaluate thread status
            status = self._evaluate_thread_status(thread_id, emails)
            thread_statuses.append(status)

            processed_count += 1
            if processed_count % 100 == 0:
                logger.info(f"Evaluated {processed_count}/{total_threads} threads")

        # Log status breakdown
        status_counts = {}
        for status in thread_statuses:
            status_counts[status.status] = status_counts.get(status.status, 0) + 1

        logger.info(f"Thread evaluation complete. Status breakdown: {status_counts}")

        return thread_statuses

    def _fetch_threads(self, limit: Optional[int] = None) -> Dict[str, List[Dict]]:
        """
        Fetch all emails grouped by thread_id, paginating in batches of 500.

        Args:
            limit: Optional limit for testing

        Returns:
            Dict mapping thread_id to list of email dicts
        """
        PAGE_SIZE = 500
        COLUMNS = ('id, thread_id, sent_date, is_outbound, '
                   'customer_contact_id, customer_company_id, processing_status')
        try:
            all_emails = []
            offset = 0

            while True:
                query = (
                    self.client.table('emails')
                    .select(COLUMNS)
                    .eq('mailbox_id', self.mailbox_id)
                    .not_.is_('thread_id', 'null')
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
            primary_company_id=primary_company_id
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
        Get primary contact and company for thread (most frequent)

        Args:
            emails: List of emails in thread

        Returns:
            Tuple of (primary_contact_id, primary_company_id)
        """
        # Count frequency of contacts and companies
        contact_counts = {}
        company_counts = {}

        for email in emails:
            contact_id = email.get('customer_contact_id')
            company_id = email.get('customer_company_id')

            if contact_id:
                contact_counts[contact_id] = contact_counts.get(contact_id, 0) + 1

            if company_id:
                company_counts[company_id] = company_counts.get(company_id, 0) + 1

        # Get most frequent
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

        for status in thread_statuses:
            record = {
                'thread_id': status.thread_id,
                'status': status.status,
                'last_email_id': status.last_email_id,
                'last_email_date': status.last_email_date.isoformat(),
                'last_sender_is_outbound': status.last_sender_is_outbound,
                'thread_depth': status.thread_depth,
                'days_since_last_email': status.days_since_last_email,
                'is_overdue': status.is_overdue,
                'primary_contact_id': status.primary_contact_id,
                'primary_company_id': status.primary_company_id,
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
                self.client.table('thread_status').upsert(
                    batch,
                    on_conflict='thread_id'
                ).execute()
                created_count += len(batch)
                logger.info(f"Saved batch {i//batch_size + 1}: {len(batch)} thread statuses")
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
