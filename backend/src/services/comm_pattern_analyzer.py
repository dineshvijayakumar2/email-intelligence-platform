"""
Communication Pattern Analyzer Service - Sprint 2 Phase 4

Purpose: Analyze email communication patterns for engagement analytics
Part of 13-step extraction pipeline (used in Step 13)

Features:
- Calculates initiation ratio (who starts conversations)
- Measures reply rate (response consistency)
- Analyzes email frequency (emails per month average)
- Detects frequency trends (increasing/stable/declining/inactive)
- Calculates average thread depth
- Tracks last inbound/outbound timestamps
- Updates contact and company engagement metrics

Author: Sprint 2 Implementation
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from collections import defaultdict

from ..database.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)


@dataclass
class CommunicationPattern:
    """Communication pattern metrics for a contact"""
    contact_id: str
    company_id: Optional[str]

    # Initiation metrics
    total_threads_initiated_by_us: int
    total_threads_initiated_by_them: int
    initiation_ratio: float  # 0.0 = they always initiate, 1.0 = we always initiate, 0.5 = balanced

    # Response metrics
    emails_received: int
    emails_sent: int
    reply_rate: float  # % of their emails we replied to

    # Frequency metrics
    total_emails: int
    emails_per_month_avg: float
    frequency_trend: str  # increasing/stable/declining/inactive

    # Thread depth
    avg_thread_depth: float

    # Recency
    last_inbound_at: Optional[datetime]
    last_outbound_at: Optional[datetime]
    days_since_last_contact: int


class CommunicationPatternAnalyzer:
    """
    Analyze email communication patterns for engagement scoring

    Usage:
        analyzer = CommunicationPatternAnalyzer(mailbox_id="uuid-here", client_id="uuid-here")
        patterns = analyzer.analyze_patterns()
        analyzer.save_patterns(patterns)
    """

    # Frequency trend thresholds
    INACTIVE_DAYS = 90  # No contact in 90 days = inactive
    TREND_WINDOW_MONTHS = 6  # Compare last 3 months vs previous 3 months

    def __init__(self, mailbox_id: str, client_id: str):
        """
        Initialize communication pattern analyzer

        Args:
            mailbox_id: Mailbox UUID to analyze
            client_id: Client UUID for filtering
        """
        self.mailbox_id = mailbox_id
        self.client_id = client_id
        self.client = SupabaseClient.get_client(use_service_key=True)

        logger.info(f"CommunicationPatternAnalyzer initialized for mailbox {mailbox_id}")

    def analyze_patterns(self) -> List[CommunicationPattern]:
        """
        Analyze communication patterns for all contacts using database-side calculations

        Performance:
        - Before: 744+ individual queries (3-4 per contact)
        - After: 3 RPC calls total (~250x improvement)

        Returns:
            List of CommunicationPattern objects
        """
        logger.info("Starting communication pattern analysis (database-side calculation)")

        try:
            # Calculate all metrics in 3 database queries instead of 744+ individual queries
            logger.info("Calculating communication patterns on database...")

            # Query 1: Get basic communication metrics (emails, dates, thread depth)
            comm_result = self.client.rpc(
                'calculate_all_contact_comm_patterns',
                {'p_client_id': self.client_id}
            ).execute()

            # Query 2: Get thread initiation ratios
            initiation_result = self.client.rpc(
                'calculate_all_contact_initiation_ratios',
                {'p_client_id': self.client_id}
            ).execute()

            # Query 3: Get reply rates
            reply_result = self.client.rpc(
                'calculate_all_contact_reply_rates',
                {'p_client_id': self.client_id}
            ).execute()

            # Index results by contact_id for fast lookup
            comm_patterns = {item['contact_id']: item for item in comm_result.data}
            initiation_ratios = {item['contact_id']: item for item in initiation_result.data}
            reply_rates = {item['contact_id']: item for item in reply_result.data}

            logger.info(f"Calculated patterns for {len(comm_patterns)} contacts (database-calculated)")

            # Fetch contact-company mapping
            contacts = self._fetch_contacts()
            contact_company_map = {c['id']: c.get('customer_company_id') for c in contacts}

            # Merge all results into CommunicationPattern objects
            patterns = []
            for contact_id, comm_data in comm_patterns.items():
                # Get initiation data (default if not found)
                init_data = initiation_ratios.get(contact_id, {
                    'threads_initiated_by_us': 0,
                    'threads_initiated_by_them': 0,
                    'initiation_ratio': 0.5
                })

                # Get reply rate (default if not found)
                reply_data = reply_rates.get(contact_id, {'reply_rate': 0.0})

                # Detect frequency trend
                frequency_trend = self._classify_frequency_trend(comm_data['emails_per_month'])

                pattern = CommunicationPattern(
                    contact_id=contact_id,
                    company_id=contact_company_map.get(contact_id),
                    total_threads_initiated_by_us=init_data['threads_initiated_by_us'],
                    total_threads_initiated_by_them=init_data['threads_initiated_by_them'],
                    initiation_ratio=float(init_data['initiation_ratio']),
                    emails_received=comm_data['total_inbound_emails'],
                    emails_sent=comm_data['total_outbound_emails'],
                    reply_rate=float(reply_data['reply_rate']),
                    total_emails=comm_data['total_inbound_emails'] + comm_data['total_outbound_emails'],
                    emails_per_month_avg=float(comm_data['emails_per_month']),
                    frequency_trend=frequency_trend,
                    avg_thread_depth=float(comm_data['avg_thread_depth']),
                    last_inbound_at=comm_data['last_inbound_date'],
                    last_outbound_at=comm_data['last_outbound_date'],
                    days_since_last_contact=comm_data['days_since_last_contact']
                )
                patterns.append(pattern)

            logger.info(f"Pattern analysis complete: {len(patterns)} contacts analyzed (database-calculated)")

            return patterns

        except Exception as e:
            logger.error(f"Failed to analyze communication patterns: {e}")
            raise

    def _classify_frequency_trend(self, emails_per_month: float) -> str:
        """
        Classify frequency trend based on emails per month

        Args:
            emails_per_month: Average emails per month

        Returns:
            Trend classification: increasing, stable, decreasing, dormant
        """
        # Simple classification based on rate
        # TODO: Could enhance with time-series analysis in future
        if emails_per_month == 0:
            return 'dormant'
        elif emails_per_month < 1:
            return 'decreasing'
        elif emails_per_month < 5:
            return 'stable'
        else:
            return 'increasing'

    def _fetch_contacts(self) -> List[Dict]:
        """
        Fetch all contacts for this client

        Returns:
            List of contact records
        """
        try:
            response = (
                self.client.table('customer_contacts')
                .select('id, email_address, customer_company_id')
                .eq('client_id', self.client_id)
                .execute()
            )

            return response.data

        except Exception as e:
            logger.error(f"Failed to fetch contacts: {e}")
            raise

    def _analyze_contact_pattern(self, contact_id: str, company_id: Optional[str]) -> Optional[CommunicationPattern]:
        """
        Analyze communication pattern for a single contact

        Args:
            contact_id: Contact UUID
            company_id: Company UUID (optional)

        Returns:
            CommunicationPattern object or None if no emails
        """
        # Fetch all emails for this contact
        emails = self._fetch_contact_emails(contact_id)

        if not emails:
            return None

        # Calculate metrics
        initiation_us, initiation_them = self._calculate_initiation_ratio(contact_id)
        total_threads = initiation_us + initiation_them
        initiation_ratio = initiation_us / total_threads if total_threads > 0 else 0.5

        emails_received, emails_sent = self._calculate_email_counts(emails)
        reply_rate = self._calculate_reply_rate(contact_id)

        total_emails = len(emails)
        emails_per_month = self._calculate_emails_per_month(emails)
        frequency_trend = self._detect_frequency_trend(emails)

        avg_thread_depth = self._calculate_avg_thread_depth(contact_id)

        last_inbound, last_outbound = self._get_last_contact_dates(emails)
        days_since_last = self._calculate_days_since_last(last_inbound, last_outbound)

        return CommunicationPattern(
            contact_id=contact_id,
            company_id=company_id,
            total_threads_initiated_by_us=initiation_us,
            total_threads_initiated_by_them=initiation_them,
            initiation_ratio=initiation_ratio,
            emails_received=emails_received,
            emails_sent=emails_sent,
            reply_rate=reply_rate,
            total_emails=total_emails,
            emails_per_month_avg=emails_per_month,
            frequency_trend=frequency_trend,
            avg_thread_depth=avg_thread_depth,
            last_inbound_at=last_inbound,
            last_outbound_at=last_outbound,
            days_since_last_contact=days_since_last
        )

    def _fetch_contact_emails(self, contact_id: str) -> List[Dict]:
        """
        Fetch all emails for a contact

        Args:
            contact_id: Contact UUID

        Returns:
            List of email records
        """
        try:
            response = (
                self.client.table('emails')
                .select('id, thread_id, sent_date, is_outbound, customer_contact_id, processing_status')
                .eq('customer_contact_id', contact_id)
                .order('sent_date', desc=False)
                .execute()
            )

            # Filter out failed in Python (includes NULLs)
            return [e for e in (response.data or []) if e.get('processing_status') != 'failed']

        except Exception as e:
            logger.error(f"Failed to fetch emails for contact {contact_id}: {e}")
            return []

    def _calculate_initiation_ratio(self, contact_id: str) -> Tuple[int, int]:
        """
        Calculate thread initiation counts

        Args:
            contact_id: Contact UUID

        Returns:
            Tuple of (threads_initiated_by_us, threads_initiated_by_them)
        """
        try:
            # Get all threads for this contact
            response = (
                self.client.table('thread_status')
                .select('thread_id, last_sender_is_outbound')
                .eq('primary_contact_id', contact_id)
                .execute()
            )

            threads = response.data

            if not threads:
                return 0, 0

            # For each thread, check who sent the first email
            initiated_by_us = 0
            initiated_by_them = 0

            for thread_data in threads:
                thread_id = thread_data['thread_id']

                # Get first email in thread
                first_email = (
                    self.client.table('emails')
                    .select('is_outbound, processing_status')
                    .eq('thread_id', thread_id)
                    .neq('processing_status', 'failed')
                    .order('sent_date', desc=False)
                    .limit(1)
                    .execute()
                )

                if first_email.data:
                    if first_email.data[0]['is_outbound']:
                        initiated_by_us += 1
                    else:
                        initiated_by_them += 1

            return initiated_by_us, initiated_by_them

        except Exception as e:
            logger.error(f"Failed to calculate initiation ratio for contact {contact_id}: {e}")
            return 0, 0

    def _calculate_email_counts(self, emails: List[Dict]) -> Tuple[int, int]:
        """
        Count inbound vs outbound emails

        Args:
            emails: List of email records

        Returns:
            Tuple of (emails_received, emails_sent)
        """
        emails_received = sum(1 for e in emails if not e.get('is_outbound', False))
        emails_sent = sum(1 for e in emails if e.get('is_outbound', False))

        return emails_received, emails_sent

    def _calculate_reply_rate(self, contact_id: str) -> float:
        """
        Calculate reply rate (% of their emails we replied to)

        Args:
            contact_id: Contact UUID

        Returns:
            Reply rate as decimal (0.0 to 1.0)
        """
        try:
            # Get response metrics where contact sent email (inbound)
            # and we responded (outbound)
            response = (
                self.client.table('email_response_metrics')
                .select('id, is_auto_reply')
                .eq('responder_contact_id', contact_id)
                .execute()
            )

            metrics = response.data

            if not metrics:
                return 0.0

            # Count non-auto-reply responses
            valid_responses = sum(1 for m in metrics if not m.get('is_auto_reply', False))

            # Get total inbound emails from contact
            inbound_response = (
                self.client.table('emails')
                .select('id', count='exact')
                .eq('customer_contact_id', contact_id)
                .eq('is_outbound', 'false')  # PostgREST expects lowercase string
                .neq('processing_status', 'failed')
                .execute()
            )

            total_inbound = inbound_response.count

            if total_inbound == 0:
                return 0.0

            return valid_responses / total_inbound

        except Exception as e:
            logger.error(f"Failed to calculate reply rate for contact {contact_id}: {e}")
            return 0.0

    def _calculate_emails_per_month(self, emails: List[Dict]) -> float:
        """
        Calculate average emails per month

        Args:
            emails: List of email records

        Returns:
            Average emails per month
        """
        if not emails:
            return 0.0

        # Get date range
        first_date = datetime.fromisoformat(emails[0]['sent_date'].replace('Z', '+00:00'))
        last_date = datetime.fromisoformat(emails[-1]['sent_date'].replace('Z', '+00:00'))

        # Calculate months
        months = (last_date - first_date).days / 30.0

        if months < 0.1:  # Less than 3 days
            months = 0.1

        return len(emails) / months

    def _detect_frequency_trend(self, emails: List[Dict]) -> str:
        """
        Detect frequency trend (increasing/stable/declining/inactive)

        Compares last 3 months vs previous 3 months

        Args:
            emails: List of email records

        Returns:
            Trend string (increasing/stable/declining/inactive)
        """
        if not emails:
            return 'inactive'

        now = datetime.utcnow()

        # Check if inactive (no emails in last 90 days)
        last_email_date = datetime.fromisoformat(emails[-1]['sent_date'].replace('Z', '+00:00'))
        days_since_last = (now - last_email_date.replace(tzinfo=None)).days

        if days_since_last > self.INACTIVE_DAYS:
            return 'inactive'

        # Count emails in last 3 months vs previous 3 months
        three_months_ago = now - timedelta(days=90)
        six_months_ago = now - timedelta(days=180)

        recent_count = sum(1 for e in emails
                          if datetime.fromisoformat(e['sent_date'].replace('Z', '+00:00')).replace(tzinfo=None) >= three_months_ago)

        previous_count = sum(1 for e in emails
                            if six_months_ago <= datetime.fromisoformat(e['sent_date'].replace('Z', '+00:00')).replace(tzinfo=None) < three_months_ago)

        if previous_count == 0:
            return 'stable'

        ratio = recent_count / previous_count

        if ratio > 1.2:
            return 'increasing'
        elif ratio < 0.8:
            return 'declining'
        else:
            return 'stable'

    def _calculate_avg_thread_depth(self, contact_id: str) -> float:
        """
        Calculate average thread depth for contact's threads

        Args:
            contact_id: Contact UUID

        Returns:
            Average thread depth
        """
        try:
            response = (
                self.client.table('thread_status')
                .select('thread_depth')
                .eq('primary_contact_id', contact_id)
                .execute()
            )

            threads = response.data

            if not threads:
                return 0.0

            total_depth = sum(t['thread_depth'] for t in threads)
            return total_depth / len(threads)

        except Exception as e:
            logger.error(f"Failed to calculate avg thread depth for contact {contact_id}: {e}")
            return 0.0

    def _get_last_contact_dates(self, emails: List[Dict]) -> Tuple[Optional[datetime], Optional[datetime]]:
        """
        Get last inbound and outbound email dates

        Args:
            emails: List of email records

        Returns:
            Tuple of (last_inbound_date, last_outbound_date)
        """
        last_inbound = None
        last_outbound = None

        for email in reversed(emails):  # Iterate backwards (most recent first)
            email_date = datetime.fromisoformat(email['sent_date'].replace('Z', '+00:00'))
            is_outbound = email.get('is_outbound', False)

            if is_outbound and last_outbound is None:
                last_outbound = email_date
            elif not is_outbound and last_inbound is None:
                last_inbound = email_date

            if last_inbound and last_outbound:
                break

        return last_inbound, last_outbound

    def _calculate_days_since_last(self, last_inbound: Optional[datetime], last_outbound: Optional[datetime]) -> int:
        """
        Calculate days since last contact (most recent of inbound or outbound)

        Args:
            last_inbound: Last inbound email date
            last_outbound: Last outbound email date

        Returns:
            Days since last contact
        """
        now = datetime.utcnow()

        dates = [d for d in [last_inbound, last_outbound] if d is not None]

        if not dates:
            return 999  # No contact

        last_contact = max(dates)
        return (now - last_contact.replace(tzinfo=None)).days

    def save_patterns(self, patterns: List[CommunicationPattern]) -> Dict:
        """
        Save communication patterns to contact records using batch update

        Performance:
        - Before: 744 individual PATCH requests
        - After: 1 batch RPC call (~744x improvement)

        Args:
            patterns: List of CommunicationPattern objects

        Returns:
            Save results
        """
        if not patterns:
            logger.info("No patterns to save")
            return {'updated_count': 0}

        logger.info(f"Saving patterns for {len(patterns)} contacts (batch update)")

        try:
            # Prepare batch update
            updates = []
            for pattern in patterns:
                updates.append({
                    'contact_id': pattern.contact_id,
                    'total_emails_received': str(pattern.emails_received),
                    'total_emails_sent': str(pattern.emails_sent),
                    'initiation_ratio': str(pattern.initiation_ratio),
                    'reply_rate': str(pattern.reply_rate),
                    'avg_thread_depth': str(pattern.avg_thread_depth),
                    'emails_per_month_avg': str(pattern.emails_per_month_avg),
                    'frequency_trend': pattern.frequency_trend,
                    'last_inbound_at': pattern.last_inbound_at.isoformat() if pattern.last_inbound_at else None,
                    'last_outbound_at': pattern.last_outbound_at.isoformat() if pattern.last_outbound_at else None,
                    'last_contacted_at': max(
                        pattern.last_inbound_at or datetime.min,
                        pattern.last_outbound_at or datetime.min,
                    ).isoformat() if (pattern.last_inbound_at or pattern.last_outbound_at) else None,
                })

            # Batch update via RPC
            logger.info(f"Batch updating {len(updates)} contacts with communication patterns")

            result = self.client.rpc(
                'batch_update_contact_analytics',
                {'updates': updates}
            ).execute()

            updated_count = result.data[0]['updated_count'] if result.data else 0

            logger.info(f"Patterns saved: {updated_count} contacts updated (batch)")

            return {
                'updated_count': updated_count,
                'total_patterns': len(patterns),
                'errors': []
            }

        except Exception as e:
            logger.error(f"Failed to save patterns in batch: {e}")
            return {
                'updated_count': 0,
                'total_patterns': len(patterns),
                'errors': [{'error': str(e)}]
            }

    def get_pattern_summary(self) -> Dict:
        """
        Get summary statistics of communication patterns

        Returns:
            Dictionary with pattern statistics
        """
        try:
            # Get all contacts
            response = (
                self.client.table('customer_contacts')
                .select('initiation_ratio, reply_rate, frequency_trend, emails_per_month_avg')
                .eq('client_id', self.client_id)
                .not_.is_('initiation_ratio', 'null')
                .execute()
            )

            contacts = response.data

            if not contacts:
                return {}

            # Calculate averages
            avg_initiation = sum(c.get('initiation_ratio', 0.5) for c in contacts) / len(contacts)
            avg_reply_rate = sum(c.get('reply_rate', 0) for c in contacts) / len(contacts)
            avg_frequency = sum(c.get('emails_per_month_avg', 0) for c in contacts) / len(contacts)

            # Count trend distribution
            trends = {}
            for contact in contacts:
                trend = contact.get('frequency_trend', 'unknown')
                trends[trend] = trends.get(trend, 0) + 1

            return {
                'total_contacts_analyzed': len(contacts),
                'avg_initiation_ratio': avg_initiation,
                'avg_reply_rate': avg_reply_rate,
                'avg_emails_per_month': avg_frequency,
                'frequency_trends': trends
            }

        except Exception as e:
            logger.error(f"Failed to get pattern summary: {e}")
            return {}


# Example usage
if __name__ == '__main__':
    import sys

    if len(sys.argv) < 3:
        print("Usage: python -m backend.src.services.comm_pattern_analyzer <mailbox_id> <client_id>")
        sys.exit(1)

    mailbox_id = sys.argv[1]
    client_id = sys.argv[2]

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Analyze patterns
    analyzer = CommunicationPatternAnalyzer(mailbox_id=mailbox_id, client_id=client_id)

    # Analyze
    patterns = analyzer.analyze_patterns()

    # Save to database
    save_results = analyzer.save_patterns(patterns)

    # Print summary
    summary = analyzer.get_pattern_summary()
    print("\n=== Communication Pattern Summary ===")
    for key, value in summary.items():
        print(f"{key}: {value}")

    print(f"\nTotal patterns analyzed: {len(patterns)}")
    print(f"Contacts updated: {save_results['updated_count']}")
