"""
Engagement Scorer Service - Sprint 2 Phase 4

Purpose: Calculate comprehensive engagement scores for contacts and companies
Part of 13-step extraction pipeline (used in Step 10)

Features:
- 8-factor engagement scoring algorithm
- Calculates scores for both contacts (0-100) and companies (0-100)
- Factors:
  1. Response time (faster = higher score)
  2. Thread completeness (closed threads = good)
  3. Initiation balance (50/50 = ideal)
  4. Reply rate (higher = better)
  5. Email frequency (regular communication = good)
  6. Recency (recent activity = engaged)
  7. Decision maker multiplier (+20% bonus)
  8. Seniority level bonus (C-level +15%, VP +10%, etc.)

Author: Sprint 2 Implementation
"""

from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

from ..database.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)


@dataclass
class EngagementScore:
    """Engagement score for a contact or company"""
    entity_id: str
    entity_type: str  # 'contact' or 'company'

    # Individual factor scores (0-100)
    response_time_score: float
    thread_completeness_score: float
    initiation_balance_score: float
    reply_rate_score: float
    frequency_score: float
    recency_score: float
    decision_maker_bonus: float
    seniority_bonus: float

    # Final engagement score (0-100)
    total_score: int

    # Factor weights (for transparency)
    weights: Dict[str, float]


class EngagementScorer:
    """
    Calculate engagement scores using 8-factor formula

    Usage:
        scorer = EngagementScorer(client_id="uuid-here")
        contact_scores = scorer.score_contacts()
        company_scores = scorer.score_companies()
        scorer.save_scores(contact_scores, company_scores)
    """

    # Factor weights (must sum to 1.0)
    FACTOR_WEIGHTS = {
        'response_time': 0.20,      # 20% - How quickly they respond
        'thread_completeness': 0.15,  # 15% - How many threads are completed
        'initiation_balance': 0.10,   # 10% - Balance in who starts conversations
        'reply_rate': 0.15,           # 15% - How consistently they reply
        'frequency': 0.15,            # 15% - How often they communicate
        'recency': 0.25,              # 25% - How recently they communicated
    }

    # Bonus multipliers
    DECISION_MAKER_BONUS = 0.20  # +20% for decision makers
    SENIORITY_BONUSES = {
        'c_level': 0.15,     # +15%
        'vp': 0.10,          # +10%
        'director': 0.07,    # +7%
        'manager': 0.05,     # +5%
        'senior': 0.03,      # +3%
    }

    # Scoring thresholds
    EXCELLENT_RESPONSE_SECONDS = 4 * 3600  # 4 hours
    GOOD_RESPONSE_SECONDS = 24 * 3600      # 24 hours
    EXCELLENT_EMAILS_PER_MONTH = 20
    GOOD_EMAILS_PER_MONTH = 5
    RECENT_DAYS = 7  # Contact within last week = very recent
    STALE_DAYS = 90  # No contact in 90 days = stale

    def __init__(self, client_id: str):
        """
        Initialize engagement scorer

        Args:
            client_id: Client UUID for filtering
        """
        self.client_id = client_id
        self.client = SupabaseClient.get_client(use_service_key=True)

        logger.info(f"EngagementScorer initialized for client {client_id}")

    def score_contacts(self) -> List[EngagementScore]:
        """
        Calculate engagement scores for all contacts

        Returns:
            List of EngagementScore objects for contacts
        """
        logger.info("Starting contact engagement scoring")

        # Fetch all contacts with analytics data
        contacts = self._fetch_contacts()
        total_contacts = len(contacts)

        logger.info(f"Scoring {total_contacts} contacts")

        scores = []
        processed_count = 0

        for contact in contacts:
            # Calculate score
            score = self._score_contact(contact)

            if score:
                scores.append(score)

            processed_count += 1
            if processed_count % 50 == 0:
                logger.info(f"Scored {processed_count}/{total_contacts} contacts")

        # Log score distribution
        self._log_score_distribution(scores, 'contacts')

        logger.info(f"Contact scoring complete: {len(scores)} contacts scored")

        return scores

    def score_companies(self) -> List[EngagementScore]:
        """
        Calculate engagement scores for all companies

        Returns:
            List of EngagementScore objects for companies
        """
        logger.info("Starting company engagement scoring")

        # Fetch all companies with analytics data
        companies = self._fetch_companies()
        total_companies = len(companies)

        logger.info(f"Scoring {total_companies} companies")

        scores = []
        processed_count = 0

        for company in companies:
            # Calculate score
            score = self._score_company(company)

            if score:
                scores.append(score)

            processed_count += 1
            if processed_count % 20 == 0:
                logger.info(f"Scored {processed_count}/{total_companies} companies")

        # Log score distribution
        self._log_score_distribution(scores, 'companies')

        logger.info(f"Company scoring complete: {len(scores)} companies scored")

        return scores

    def _fetch_contacts(self) -> List[Dict]:
        """
        Fetch all contacts with analytics data

        Returns:
            List of contact records
        """
        try:
            response = (
                self.client.table('customer_contacts')
                .select('id, email_address, '
                       'avg_response_time_seconds, their_avg_response_time, '
                       'open_thread_count, dropped_thread_count, '
                       'initiation_ratio, reply_rate, '
                       'emails_per_month_avg, frequency_trend, '
                       'last_inbound_at, last_outbound_at, '
                       'is_decision_maker, seniority_level')
                .eq('client_id', self.client_id)
                .execute()
            )

            return response.data

        except Exception as e:
            logger.error(f"Failed to fetch contacts: {e}")
            raise

    def _fetch_companies(self) -> List[Dict]:
        """
        Fetch all companies with analytics data

        Returns:
            List of company records
        """
        try:
            response = (
                self.client.table('customer_companies')
                .select('id, company_name, '
                       'avg_response_time_seconds, '
                       'open_thread_count, dropped_thread_count, '
                       'avg_emails_per_month, frequency_trend, '
                       'decision_maker_count, highest_seniority')
                .eq('client_id', self.client_id)
                .execute()
            )

            return response.data

        except Exception as e:
            logger.error(f"Failed to fetch companies: {e}")
            raise

    def _score_contact(self, contact: Dict) -> Optional[EngagementScore]:
        """
        Calculate engagement score for a single contact

        Args:
            contact: Contact record with analytics data

        Returns:
            EngagementScore object or None
        """
        contact_id = contact['id']

        # Calculate individual factor scores
        response_time_score = self._score_response_time(contact.get('their_avg_response_time'))
        thread_completeness_score = self._score_thread_completeness(
            contact.get('open_thread_count', 0),
            contact.get('dropped_thread_count', 0)
        )
        initiation_balance_score = self._score_initiation_balance(contact.get('initiation_ratio'))
        reply_rate_score = self._score_reply_rate(contact.get('reply_rate'))
        frequency_score = self._score_frequency(contact.get('emails_per_month_avg'))
        recency_score = self._score_recency(contact.get('last_inbound_at'), contact.get('last_outbound_at'))

        # Calculate bonuses
        decision_maker_bonus = self.DECISION_MAKER_BONUS if contact.get('is_decision_maker') else 0.0
        seniority_bonus = self.SENIORITY_BONUSES.get(contact.get('seniority_level', ''), 0.0)

        # Calculate weighted total
        base_score = (
            response_time_score * self.FACTOR_WEIGHTS['response_time'] +
            thread_completeness_score * self.FACTOR_WEIGHTS['thread_completeness'] +
            initiation_balance_score * self.FACTOR_WEIGHTS['initiation_balance'] +
            reply_rate_score * self.FACTOR_WEIGHTS['reply_rate'] +
            frequency_score * self.FACTOR_WEIGHTS['frequency'] +
            recency_score * self.FACTOR_WEIGHTS['recency']
        )

        # Apply bonuses (multiplicative)
        total_bonus = decision_maker_bonus + seniority_bonus
        total_score = int(min(100, base_score * (1 + total_bonus)))

        return EngagementScore(
            entity_id=contact_id,
            entity_type='contact',
            response_time_score=response_time_score,
            thread_completeness_score=thread_completeness_score,
            initiation_balance_score=initiation_balance_score,
            reply_rate_score=reply_rate_score,
            frequency_score=frequency_score,
            recency_score=recency_score,
            decision_maker_bonus=decision_maker_bonus * 100,
            seniority_bonus=seniority_bonus * 100,
            total_score=total_score,
            weights=self.FACTOR_WEIGHTS
        )

    def _score_company(self, company: Dict) -> Optional[EngagementScore]:
        """
        Calculate engagement score for a single company

        Args:
            company: Company record with analytics data

        Returns:
            EngagementScore object or None
        """
        company_id = company['id']

        # Calculate individual factor scores (similar to contact but aggregated)
        response_time_score = self._score_response_time(company.get('avg_response_time_seconds'))
        thread_completeness_score = self._score_thread_completeness(
            company.get('open_thread_count', 0),
            company.get('dropped_thread_count', 0)
        )
        initiation_balance_score = 50.0  # Neutral for companies (calculated from contacts)
        reply_rate_score = 70.0  # Placeholder for companies
        frequency_score = self._score_frequency(company.get('avg_emails_per_month'))
        recency_score = 60.0  # Placeholder (would need to calculate from emails)

        # Calculate bonuses
        decision_maker_bonus = 0.10 if company.get('decision_maker_count', 0) > 0 else 0.0
        seniority_bonus = self.SENIORITY_BONUSES.get(company.get('highest_seniority', ''), 0.0)

        # Calculate weighted total
        base_score = (
            response_time_score * self.FACTOR_WEIGHTS['response_time'] +
            thread_completeness_score * self.FACTOR_WEIGHTS['thread_completeness'] +
            initiation_balance_score * self.FACTOR_WEIGHTS['initiation_balance'] +
            reply_rate_score * self.FACTOR_WEIGHTS['reply_rate'] +
            frequency_score * self.FACTOR_WEIGHTS['frequency'] +
            recency_score * self.FACTOR_WEIGHTS['recency']
        )

        # Apply bonuses
        total_bonus = decision_maker_bonus + seniority_bonus
        total_score = int(min(100, base_score * (1 + total_bonus)))

        return EngagementScore(
            entity_id=company_id,
            entity_type='company',
            response_time_score=response_time_score,
            thread_completeness_score=thread_completeness_score,
            initiation_balance_score=initiation_balance_score,
            reply_rate_score=reply_rate_score,
            frequency_score=frequency_score,
            recency_score=recency_score,
            decision_maker_bonus=decision_maker_bonus * 100,
            seniority_bonus=seniority_bonus * 100,
            total_score=total_score,
            weights=self.FACTOR_WEIGHTS
        )

    def _score_response_time(self, avg_response_time_seconds: Optional[int]) -> float:
        """
        Score based on average response time (0-100)

        Faster response = higher score

        Args:
            avg_response_time_seconds: Average response time in seconds

        Returns:
            Score (0-100)
        """
        if avg_response_time_seconds is None or avg_response_time_seconds <= 0:
            return 50.0  # Neutral if no data

        if avg_response_time_seconds <= self.EXCELLENT_RESPONSE_SECONDS:
            return 100.0
        elif avg_response_time_seconds <= self.GOOD_RESPONSE_SECONDS:
            return 80.0
        elif avg_response_time_seconds <= 3 * 24 * 3600:  # 3 days
            return 60.0
        elif avg_response_time_seconds <= 7 * 24 * 3600:  # 1 week
            return 40.0
        else:
            return 20.0

    def _score_thread_completeness(self, open_threads: int, dropped_threads: int) -> float:
        """
        Score based on thread completion ratio (0-100)

        Fewer open/dropped threads = higher score

        Args:
            open_threads: Number of open threads
            dropped_threads: Number of dropped threads

        Returns:
            Score (0-100)
        """
        total_threads = open_threads + dropped_threads

        if total_threads == 0:
            return 70.0  # Neutral if no threads

        # Dropped threads are worse than open threads
        problem_score = (open_threads * 0.5 + dropped_threads * 1.0) / total_threads

        # Invert: fewer problems = higher score
        return max(0, 100 - (problem_score * 100))

    def _score_initiation_balance(self, initiation_ratio: Optional[float]) -> float:
        """
        Score based on conversation initiation balance (0-100)

        0.5 (50/50) is ideal, deviations reduce score

        Args:
            initiation_ratio: Ratio of threads we initiated (0.0 to 1.0)

        Returns:
            Score (0-100)
        """
        if initiation_ratio is None:
            return 50.0  # Neutral if no data

        # Perfect balance = 0.5
        # Calculate deviation from perfect balance
        deviation = abs(initiation_ratio - 0.5)

        # Convert deviation to score (0.0 deviation = 100, 0.5 deviation = 0)
        score = 100 - (deviation * 200)

        return max(0, min(100, score))

    def _score_reply_rate(self, reply_rate: Optional[float]) -> float:
        """
        Score based on reply rate (0-100)

        Higher reply rate = higher score

        Args:
            reply_rate: Reply rate (0.0 to 1.0)

        Returns:
            Score (0-100)
        """
        if reply_rate is None:
            return 50.0  # Neutral if no data

        # Direct conversion: reply_rate (0-1) to score (0-100)
        return reply_rate * 100

    def _score_frequency(self, emails_per_month: Optional[float]) -> float:
        """
        Score based on email frequency (0-100)

        Regular communication = higher score

        Args:
            emails_per_month: Average emails per month

        Returns:
            Score (0-100)
        """
        if emails_per_month is None or emails_per_month <= 0:
            return 0.0

        if emails_per_month >= self.EXCELLENT_EMAILS_PER_MONTH:
            return 100.0
        elif emails_per_month >= self.GOOD_EMAILS_PER_MONTH:
            return 75.0
        elif emails_per_month >= 2:
            return 50.0
        elif emails_per_month >= 1:
            return 30.0
        else:
            return 15.0

    def _score_recency(self, last_inbound: Optional[str], last_outbound: Optional[str]) -> float:
        """
        Score based on recency of last contact (0-100)

        More recent = higher score

        Args:
            last_inbound: Last inbound email timestamp
            last_outbound: Last outbound email timestamp

        Returns:
            Score (0-100)
        """
        now = datetime.utcnow()

        dates = []
        if last_inbound:
            dates.append(datetime.fromisoformat(last_inbound.replace('Z', '+00:00')).replace(tzinfo=None))
        if last_outbound:
            dates.append(datetime.fromisoformat(last_outbound.replace('Z', '+00:00')).replace(tzinfo=None))

        if not dates:
            return 0.0  # No contact

        last_contact = max(dates)
        days_since = (now - last_contact).days

        if days_since <= self.RECENT_DAYS:
            return 100.0
        elif days_since <= 30:
            return 80.0
        elif days_since <= 60:
            return 60.0
        elif days_since <= self.STALE_DAYS:
            return 40.0
        else:
            return 10.0

    def save_scores(self, contact_scores: List[EngagementScore], company_scores: List[EngagementScore]) -> Dict:
        """
        Save engagement scores to database

        Args:
            contact_scores: List of contact EngagementScore objects
            company_scores: List of company EngagementScore objects

        Returns:
            Save results
        """
        logger.info(f"Saving engagement scores: {len(contact_scores)} contacts, {len(company_scores)} companies")

        contacts_updated = self._save_contact_scores(contact_scores)
        companies_updated = self._save_company_scores(company_scores)

        logger.info(f"Engagement scores saved: {contacts_updated} contacts, {companies_updated} companies")

        return {
            'contacts_updated': contacts_updated,
            'companies_updated': companies_updated
        }

    def _save_contact_scores(self, scores: List[EngagementScore]) -> int:
        """
        Save contact engagement scores using batch update

        Performance:
        - Before: Individual PATCH per contact
        - After: 1 batch RPC call

        Args:
            scores: List of EngagementScore objects

        Returns:
            Number of contacts updated
        """
        if not scores:
            return 0

        try:
            # Prepare batch update
            updates = []
            for score in scores:
                updates.append({
                    'contact_id': score.entity_id,
                    'engagement_score': str(score.total_score)
                })

            # Batch update via RPC
            logger.info(f"Batch updating {len(updates)} contacts with engagement scores")

            result = self.client.rpc(
                'batch_update_contact_analytics',
                {'updates': updates}
            ).execute()

            updated_count = result.data[0]['updated_count'] if result.data else 0

            logger.info(f"Contact engagement scores updated: {updated_count} contacts (batch)")

            return updated_count

        except Exception as e:
            logger.error(f"Failed to batch update contact scores: {e}")
            return 0

    def _save_company_scores(self, scores: List[EngagementScore]) -> int:
        """
        Save company engagement scores using batch update

        Performance:
        - Before: Individual PATCH per company
        - After: 1 batch RPC call

        Args:
            scores: List of EngagementScore objects

        Returns:
            Number of companies updated
        """
        if not scores:
            return 0

        try:
            # Prepare batch update
            updates = []
            for score in scores:
                updates.append({
                    'company_id': score.entity_id,
                    'engagement_score': str(score.total_score)
                })

            # Batch update via RPC
            logger.info(f"Batch updating {len(updates)} companies with engagement scores")

            result = self.client.rpc(
                'batch_update_company_analytics',
                {'updates': updates}
            ).execute()

            updated_count = result.data[0]['updated_count'] if result.data else 0

            logger.info(f"Company engagement scores updated: {updated_count} companies (batch)")

            return updated_count

        except Exception as e:
            logger.error(f"Failed to batch update company scores: {e}")
            return 0

    def _log_score_distribution(self, scores: List[EngagementScore], entity_type: str):
        """
        Log distribution of engagement scores

        Args:
            scores: List of EngagementScore objects
            entity_type: 'contacts' or 'companies'
        """
        if not scores:
            return

        score_values = [s.total_score for s in scores]

        buckets = {
            '90-100 (Excellent)': sum(1 for s in score_values if 90 <= s <= 100),
            '70-89 (Good)': sum(1 for s in score_values if 70 <= s < 90),
            '50-69 (Fair)': sum(1 for s in score_values if 50 <= s < 70),
            '30-49 (Low)': sum(1 for s in score_values if 30 <= s < 50),
            '0-29 (Very Low)': sum(1 for s in score_values if 0 <= s < 30),
        }

        avg_score = sum(score_values) / len(score_values)

        logger.info(f"\n{entity_type.capitalize()} Score Distribution:")
        logger.info(f"  Average score: {avg_score:.1f}")
        for bucket, count in buckets.items():
            percentage = (count / len(scores)) * 100
            logger.info(f"  {bucket}: {count} ({percentage:.1f}%)")


# Example usage
if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m backend.src.services.engagement_scorer <client_id>")
        sys.exit(1)

    client_id = sys.argv[1]

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Score engagement
    scorer = EngagementScorer(client_id=client_id)

    # Calculate scores
    contact_scores = scorer.score_contacts()
    company_scores = scorer.score_companies()

    # Save to database
    results = scorer.save_scores(contact_scores, company_scores)

    print(f"\nEngagement scoring complete:")
    print(f"  Contacts scored: {len(contact_scores)}")
    print(f"  Companies scored: {len(company_scores)}")
    print(f"  Contacts updated: {results['contacts_updated']}")
    print(f"  Companies updated: {results['companies_updated']}")
