"""
Action Bucket Engine — AM-centric signal engine (v3.0)

Layer 2 of the intelligence system. Derives 6 AM-actionable signals from:
- Layer 1 AI classification (intent, business_signal, entities)
- Sprint 2 data (engagement, threads, seniority, frequency)
- Sprint 3 QB data (revenue, customer type, order recency, quotes)

$0 cost — pure Python, no API calls.

6 Signals (replace old 10 buckets):
  response_urgency   — Inbound email(s) awaiting AM reply
  deal_at_risk       — Open quote stalled 30+ days + low engagement
  retention_risk     — At-risk/dormant customer with no recent AM contact
  revenue_opportunity — Active customer, high engagement, no recent quote
  new_relationship   — First-time contact appearing in emails
  account_neglect    — Company has inbound but AM silent 14+ days

Customer Lifecycle Tiers (computed, not AI-guessed):
  prospect      — No QB record or QB type = prospective, zero orders
  new_customer  — First order within last 90 days
  active_customer — Orders in last 6 months, regular communication
  at_risk        — Was active, no orders 90+ days AND declining engagement
  dormant        — No email + no QB activity 180+ days
  champion       — Top 20% revenue, high engagement, tier A
"""

import json
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------
BUCKET_ENGINE_VERSION = "v3.0"  # AM-centric signals + lifecycle tiers

# ---------------------------------------------------------------------------
# Signal configuration (used by frontend for display)
# ---------------------------------------------------------------------------
BUCKET_CONFIG = {
    "response_urgency": {
        "label": "Response Urgency",
        "color": "red",
        "severity": "critical",
        "action": "Reply now — inbound email(s) awaiting your response",
    },
    "deal_at_risk": {
        "label": "Deal at Risk",
        "color": "orange",
        "severity": "critical",
        "action": "Follow up on stalled quote before customer disengages",
    },
    "retention_risk": {
        "label": "Retention Risk",
        "color": "red",
        "severity": "critical",
        "action": "Proactive check-in — customer cooling, contact overdue",
    },
    "revenue_opportunity": {
        "label": "Revenue Opportunity",
        "color": "green",
        "severity": "high",
        "action": "Send a quote — engaged customer with no recent proposal",
    },
    "new_relationship": {
        "label": "New Relationship",
        "color": "blue",
        "severity": "high",
        "action": "Introduce yourself and qualify this new contact",
    },
    "account_neglect": {
        "label": "Account Neglect",
        "color": "yellow",
        "severity": "high",
        "action": "AM has not replied in 14+ days — respond or reassign",
    },
}

# Lifecycle tier display config
LIFECYCLE_CONFIG = {
    "prospect": {"label": "Prospect", "color": "purple"},
    "new_customer": {"label": "New Customer", "color": "blue"},
    "active_customer": {"label": "Active Customer", "color": "green"},
    "at_risk": {"label": "At Risk", "color": "orange"},
    "dormant": {"label": "Dormant", "color": "gray"},
    "champion": {"label": "Champion", "color": "gold"},
}

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

# Lifecycle thresholds (days)
NEW_CUSTOMER_DAYS = 90       # First order within this window = new_customer
AT_RISK_DAYS = 90            # No order beyond this = at_risk (if was active)
DORMANT_DAYS = 180           # No email + no QB beyond this = dormant
CHAMPION_REVENUE = 100_000   # Revenue threshold for champion tier
ACCOUNT_NEGLECT_DAYS = 14    # AM silence beyond this = account_neglect signal
DEAL_STALE_DAYS = 30         # Quote older than this without acceptance = deal_at_risk
NO_QUOTE_DAYS = 60           # No quote in this window = revenue_opportunity candidate


# ---------------------------------------------------------------------------
# Lifecycle tier computation (deterministic, no AI)
# ---------------------------------------------------------------------------
def compute_lifecycle_tier(
    qb_customer_type: str,
    qb_tier: str,
    qb_total_revenue: Optional[float],
    qb_days_since_last_invoice: Optional[int],
    qb_days_since_first_invoice: Optional[int],
    engagement_score: int,
    engagement_trend: str,
) -> str:
    """
    Compute customer lifecycle tier from QB + engagement data.

    Priority order:
      champion > prospect > new_customer > active_customer > at_risk > dormant
    """
    ctype = (qb_customer_type or "").lower()
    tier = (qb_tier or "").upper()
    revenue = float(qb_total_revenue or 0)
    days_since = qb_days_since_last_invoice  # None = never invoiced
    days_first = qb_days_since_first_invoice

    # Champion: top revenue + high tier + recent activity
    if (
        (tier in ("A", "1") or revenue >= CHAMPION_REVENUE)
        and (days_since is None or days_since <= DORMANT_DAYS)
        and engagement_score >= 50
    ):
        return "champion"

    # Prospect: explicitly marked prospective, OR no QB record AND low engagement
    # (Companies with significant email engagement are likely active, not prospects)
    if ctype in ("prospective", "prospect"):
        return "prospect"
    if ctype == "" and days_since is None and engagement_score < 20:
        return "prospect"

    # New customer: first invoice within NEW_CUSTOMER_DAYS
    if days_first is not None and days_first <= NEW_CUSTOMER_DAYS:
        return "new_customer"

    # At-risk: had activity but gone quiet + engagement declining
    if days_since is not None and days_since > AT_RISK_DAYS:
        if engagement_trend in ("declining", "decreasing") or engagement_score < 30:
            return "at_risk"

    # Dormant: no QB activity AND low engagement
    if (days_since is None or days_since > DORMANT_DAYS) and engagement_score < 20:
        return "dormant"

    # Default: active customer
    return "active_customer"


# ---------------------------------------------------------------------------
# Email-level signal derivation
# ---------------------------------------------------------------------------
def derive_email_buckets(intel_row: dict) -> list[dict]:
    """
    Derive AM-centric signals for a single email from its AI classification.

    Pure Python — no API calls.
    Returns list of {bucket, confidence, justification}.
    """
    buckets = []

    intent = intel_row.get("intent")
    business_signal = intel_row.get("business_signal")
    sentiment = intel_row.get("sentiment")
    urgency = intel_row.get("urgency")
    confidence = float(intel_row.get("confidence") or 0.5)
    direction = intel_row.get("email_direction", "inbound")
    lifecycle_tier = intel_row.get("customer_lifecycle_tier", "")

    qb_customer_type = (intel_row.get("qb_customer_type") or "").lower()
    qb_revenue = intel_row.get("qb_total_revenue")
    qb_days_since = intel_row.get("qb_days_since_last_invoice")
    qb_tier = (intel_row.get("qb_tier") or "").upper()

    # --- RESPONSE URGENCY ---
    # Inbound email with action required, critical/high urgency, or complaint
    if direction == "inbound":
        is_urgent = urgency in ("critical", "high")
        needs_action = intent in ("action_required", "complaint", "pricing_inquiry",
                                  "question", "meeting_scheduling")
        is_escalation = business_signal == "escalation"

        if is_urgent and needs_action:
            buckets.append({
                "bucket": "response_urgency",
                "confidence": round(min(confidence + 0.1, 1.0), 2),
                "justification": f"Inbound {urgency}-urgency {intent or 'email'} requires response",
            })
        elif is_escalation:
            buckets.append({
                "bucket": "response_urgency",
                "confidence": round(confidence, 2),
                "justification": "Escalation signal — requires immediate AM attention",
            })
        elif needs_action and sentiment in ("negative", "very_negative"):
            buckets.append({
                "bucket": "response_urgency",
                "confidence": round(confidence * 0.8, 2),
                "justification": f"Negative-sentiment {intent or 'email'} needing AM response",
            })

    # --- DEAL AT RISK ---
    # Stalled quote context: customer mentions quote/pricing but engagement declining
    # or churn/negative signals on a customer with open quotes
    has_churn_signal = (
        intent in ("churn_risk",)
        or business_signal in ("churn_signal", "competitive_evaluation")
        or sentiment == "very_negative"
    )
    has_qb_stale = qb_days_since is not None and qb_days_since > DEAL_STALE_DAYS

    if has_churn_signal and (qb_revenue and qb_revenue > 5000):
        rev_str = f"${qb_revenue:,.0f}"
        justification = f"Churn/negative signal on {rev_str} customer"
        if has_qb_stale:
            justification += f" ({qb_days_since}d since last order)"
        buckets.append({
            "bucket": "deal_at_risk",
            "confidence": round(min(confidence + 0.05, 1.0), 2),
            "justification": justification,
        })

    # --- RETENTION RISK ---
    # At-risk/dormant tier + negative signals or complaint
    if lifecycle_tier in ("at_risk", "dormant"):
        if intent in ("complaint", "churn_risk") or sentiment in ("negative", "very_negative"):
            buckets.append({
                "bucket": "retention_risk",
                "confidence": round(confidence, 2),
                "justification": f"{lifecycle_tier.replace('_', ' ').title()} customer with negative signal",
            })

    # --- REVENUE OPPORTUNITY ---
    # Active/champion customer showing interest signals (positive engagement, expansion, renewal)
    if lifecycle_tier in ("active_customer", "champion") or qb_customer_type in ("existing", "active"):
        is_opportunity = (
            business_signal in ("expansion_interest", "renewal_intent", "buying_intent")
            or intent in ("expansion_signal", "pricing_inquiry")
            or (sentiment in ("positive", "very_positive") and intent == "question")
        )
        if is_opportunity:
            tier_label = qb_tier or qb_customer_type or "existing"
            buckets.append({
                "bucket": "revenue_opportunity",
                "confidence": round(confidence, 2),
                "justification": f"{tier_label} customer showing {business_signal or intent or 'interest'} signal",
            })

    # --- NEW RELATIONSHIP ---
    # Very low email count + introduction or first contact
    email_count = int(intel_row.get("_contact_email_count") or 0)
    if email_count <= 3 or intent == "introduction":
        if direction == "inbound":
            buckets.append({
                "bucket": "new_relationship",
                "confidence": 0.8 if intent == "introduction" else 0.65,
                "justification": "New inbound contact — first or very early email exchange",
            })

    # Boost confidence for high-value/top-tier customers on any critical signal
    if qb_tier in ("A", "1") or (qb_revenue and qb_revenue > 50000):
        for b in buckets:
            if b["bucket"] in ("retention_risk", "deal_at_risk", "response_urgency"):
                b["confidence"] = round(min(b["confidence"] + 0.1, 1.0), 2)
                b["justification"] += f" [High-value customer: ${qb_revenue:,.0f}]" if qb_revenue else ""

    return buckets


# ---------------------------------------------------------------------------
# Relationship-level signal derivation (account / company level)
# ---------------------------------------------------------------------------
def derive_relationship_buckets(
    intel_rows: list[dict],
    contact_data: dict,
    company_data: dict,
    thread_data: list[dict],
) -> list[dict]:
    """
    Derive relationship-level signals using AI classification + engagement data.

    Args:
        intel_rows: Recent ai_email_intelligence rows for this contact/company
        contact_data: customer_contacts row
        company_data: customer_companies row
        thread_data: thread_status rows

    Returns: List of {bucket, confidence, justification, context}
    """
    buckets = []

    engagement = int(contact_data.get("engagement_score") or 0)
    frequency_trend = contact_data.get("frequency_trend", "stable")
    seniority = contact_data.get("seniority_level", "unknown")
    is_dm = contact_data.get("is_decision_maker", False)

    # --- NEW RELATIONSHIP ---
    # Senior decision-maker or first-time contact with few emails
    total_emails = int(contact_data.get("total_emails_sent", 0)) + int(contact_data.get("total_emails_received", 0))
    if total_emails <= 5 and direction_is_mostly_inbound(intel_rows):
        conf = 0.85 if (is_dm and seniority in ("c_level", "vp", "director")) else 0.7
        buckets.append({
            "bucket": "new_relationship",
            "confidence": conf,
            "justification": f"New contact ({total_emails} total emails), seniority: {seniority}",
            "context": {"total_emails": total_emails, "seniority": seniority, "is_dm": is_dm},
        })

    # --- RESPONSE URGENCY (relationship-level: multiple unanswered inbound) ---
    unanswered = _count_unanswered_inbound(intel_rows)
    if unanswered >= 2:
        buckets.append({
            "bucket": "response_urgency",
            "confidence": min(0.6 + (unanswered - 2) * 0.1, 0.95),
            "justification": f"{unanswered} inbound emails awaiting AM reply",
            "context": {"unanswered_count": unanswered},
        })

    # --- ACCOUNT NEGLECT ---
    # Overdue threads where AM has not replied
    for thread in thread_data:
        status = thread.get("status")
        days = int(thread.get("days_since_last_email") or 0)
        if status in ("overdue", "stalled") and days >= ACCOUNT_NEGLECT_DAYS:
            buckets.append({
                "bucket": "account_neglect",
                "confidence": min(0.5 + (days - ACCOUNT_NEGLECT_DAYS) / 30.0 * 0.2, 0.95),
                "justification": f"Thread stalled {days} days — AM has not followed up",
                "context": {"thread_id": thread.get("thread_id"), "days_stalled": days},
            })

    # --- RETENTION RISK (relationship-level: cooling relationship) ---
    rel_status = company_data.get("relationship_status", "active")
    comm_health = company_data.get("communication_health", "good")
    if rel_status in ("cooling", "at_risk") or comm_health in ("needs_attention", "critical"):
        if frequency_trend in ("declining", "decreasing") or engagement < 25:
            buckets.append({
                "bucket": "retention_risk",
                "confidence": 0.75,
                "justification": f"Relationship {rel_status}, comms {comm_health}, engagement {engagement}",
                "context": {"relationship_status": rel_status, "communication_health": comm_health,
                            "engagement": engagement},
            })

    return buckets


def direction_is_mostly_inbound(intel_rows: list[dict]) -> bool:
    if not intel_rows:
        return True
    inbound = sum(1 for r in intel_rows if r.get("email_direction") == "inbound")
    return inbound >= len(intel_rows) * 0.6


def _count_unanswered_inbound(intel_rows: list[dict]) -> int:
    """Count inbound emails in threads that have no outbound reply."""
    threads_with_inbound = {}
    threads_with_outbound = set()

    for row in intel_rows:
        tid = row.get("thread_id")
        direction = row.get("email_direction", "")
        if not tid:
            continue
        if direction == "inbound":
            threads_with_inbound[tid] = threads_with_inbound.get(tid, 0) + 1
        elif direction == "outbound":
            threads_with_outbound.add(tid)

    unanswered = sum(
        count for tid, count in threads_with_inbound.items()
        if tid not in threads_with_outbound
    )
    return unanswered


# ---------------------------------------------------------------------------
# Main engine class
# ---------------------------------------------------------------------------
class ActionBucketEngine:
    """
    Derives and stores AM-centric signals. Zero-cost Python rules.
    """

    def __init__(self, supabase_client):
        self.client = supabase_client

    @staticmethod
    def _execute_with_retry(query_builder, max_retries: int = 3, base_delay: float = 2.0):
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                return query_builder.execute()
            except Exception as e:
                last_error = e
                error_str = str(e)
                is_transient = any(keyword in error_str for keyword in [
                    'SSL handshake failed', '525', '502', '503', '504',
                    'Connection reset', 'Connection refused', 'timed out',
                    'JSON could not be generated', 'ECONNRESET', 'ETIMEDOUT',
                    'ConnectionTerminated', 'PROTOCOL_ERROR', 'SEND_HEADERS',
                    'StreamInput', 'state 5',
                ])
                if is_transient and attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        f"Transient error (attempt {attempt + 1}/{max_retries + 1}), "
                        f"retrying in {delay}s: {error_str[:200]}"
                    )
                    time.sleep(delay)
                    continue
                raise
        raise last_error

    # ------------------------------------------------------------------
    # Process email-level signals for all completed intel rows
    # ------------------------------------------------------------------
    def process_email_buckets(self, mailbox_id: str, force: bool = False) -> dict:
        """
        Derive email-level signals for all completed intel rows.

        Args:
            force: If True, re-derive buckets for ALL rows (even those with existing buckets).
                   Use this after bucket engine version upgrades.
        """
        all_rows = []
        offset = 0
        PAGE_SIZE = 500
        while True:
            resp = self._execute_with_retry(
                self.client.table("ai_email_intelligence")
                .select("id,email_id,intent,urgency,sentiment,confidence,business_signal,"
                        "has_budget_signal,has_competitor_mention,has_deadline,"
                        "business_signal_score,competitors_mentioned,action_buckets,"
                        "customer_lifecycle_tier")
                .eq("mailbox_id", mailbox_id)
                .eq("processing_status", "completed")
                .range(offset, offset + PAGE_SIZE - 1)
            )
            batch = resp.data or []
            all_rows.extend(batch)
            if len(batch) == 0:
                break
            offset += len(batch)

        processed = 0
        buckets_assigned = 0
        update_batch = []

        for row in all_rows:
            if not force:
                existing_buckets = row.get("action_buckets")
                if existing_buckets and existing_buckets != "[]" and existing_buckets != []:
                    continue

            buckets = derive_email_buckets(row)
            primary = buckets[0]["bucket"] if buckets else None
            has_urgency = any(b["bucket"] == "response_urgency" for b in buckets)

            update_batch.append({
                "id": row["id"],
                "action_buckets": buckets,
                "primary_bucket": primary,
                "has_response_urgency": has_urgency,
                "bucket_engine_version": BUCKET_ENGINE_VERSION,
            })

            processed += 1
            buckets_assigned += len(buckets)

            if len(update_batch) >= 100:
                self._flush_bucket_updates(update_batch)
                update_batch = []

        if update_batch:
            self._flush_bucket_updates(update_batch)

        logger.info(f"Signals: {processed} processed, {buckets_assigned} signals assigned")
        return {"processed": processed, "buckets_assigned": buckets_assigned}

    def _flush_bucket_updates(self, updates: list[dict]):
        for update in updates:
            try:
                self._execute_with_retry(
                    self.client.table("ai_email_intelligence")
                    .update({
                        "action_buckets": update["action_buckets"],
                        "primary_bucket": update["primary_bucket"],
                        "has_response_urgency": update.get("has_response_urgency", False),
                        "bucket_engine_version": update["bucket_engine_version"],
                    })
                    .eq("id", update["id"])
                )
            except Exception as e:
                logger.error(f"Failed to update signals for {update['id']}: {e}")

    # ------------------------------------------------------------------
    # Compute relationship-level signals for a company
    # ------------------------------------------------------------------
    def compute_relationship_buckets(
        self,
        company_id: str,
        mailbox_id: str,
        client_id: Optional[str] = None,
    ) -> list[dict]:
        intel_rows = self._get_company_intel(company_id, mailbox_id)
        company_data = self._get_company_data(company_id)
        contacts = self._get_company_contacts(company_id)
        thread_data = self._get_company_threads(company_id)

        all_buckets = []
        for contact in contacts:
            contact_intel = [
                r for r in intel_rows
                if r.get("customer_contact_id") == contact.get("id")
            ]
            contact_name = (
                f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()
                or contact.get("email_address", "unknown")
            )
            buckets = derive_relationship_buckets(
                contact_intel, contact, company_data, thread_data
            )
            for b in buckets:
                b["contact_id"] = contact.get("id")
                b["contact_name"] = contact_name
            all_buckets.extend(buckets)

        return all_buckets

    def _get_company_intel(self, company_id: str, mailbox_id: str) -> list[dict]:
        email_resp = self._execute_with_retry(
            self.client.table("emails")
            .select("id,thread_id,direction")
            .eq("customer_company_id", company_id)
            .eq("mailbox_id", mailbox_id)
            .order("sent_date", desc=True)
            .range(0, 99)
        )
        emails = email_resp.data or []
        if not emails:
            return []

        email_ids = [e["id"] for e in emails]
        email_lookup = {e["id"]: e for e in emails}

        all_intel = []
        for i in range(0, len(email_ids), 500):
            chunk = email_ids[i:i + 500]
            resp = self._execute_with_retry(
                self.client.table("ai_email_intelligence")
                .select("*")
                .in_("email_id", chunk)
                .eq("processing_status", "completed")
            )
            for row in (resp.data or []):
                email = email_lookup.get(row.get("email_id"), {})
                row["email_direction"] = email.get("direction", "")
                row["thread_id"] = email.get("thread_id", "")
                all_intel.append(row)

        return all_intel

    def _get_company_data(self, company_id: str) -> dict:
        resp = self._execute_with_retry(
            self.client.table("customer_companies")
            .select("id,engagement_score,open_thread_count,dropped_thread_count,"
                    "decision_maker_count,communication_health,relationship_status,"
                    "frequency_trend")
            .eq("id", company_id)
            .range(0, 0)
        )
        data = resp.data or []
        return data[0] if data else {}

    def _get_company_contacts(self, company_id: str) -> list[dict]:
        all_contacts = []
        offset = 0
        PAGE_SIZE = 500
        while True:
            resp = self._execute_with_retry(
                self.client.table("customer_contacts")
                .select("id,first_name,last_name,email_address,seniority_level,"
                        "functional_role,is_decision_maker,engagement_score,"
                        "frequency_trend,total_emails_sent,total_emails_received")
                .eq("company_id", company_id)
                .range(offset, offset + PAGE_SIZE - 1)
            )
            batch = resp.data or []
            all_contacts.extend(batch)
            if len(batch) == 0:
                break
            offset += len(batch)
        return all_contacts

    def _get_company_threads(self, company_id: str) -> list[dict]:
        all_threads = []
        offset = 0
        PAGE_SIZE = 500
        while True:
            resp = self._execute_with_retry(
                self.client.table("thread_status")
                .select("thread_id,status,is_overdue,days_since_last_email")
                .eq("primary_company_id", company_id)
                .range(offset, offset + PAGE_SIZE - 1)
            )
            batch = resp.data or []
            all_threads.extend(batch)
            if len(batch) == 0:
                break
            offset += len(batch)
        return all_threads

    def _get_email_ids_in_date_range(
        self, mailbox_id: str, date_from: str = None, date_to: str = None
    ) -> Optional[set]:
        if not date_from and not date_to:
            return None

        query = self.client.table("emails").select("id").eq("mailbox_id", mailbox_id)
        if date_from:
            query = query.gte("sent_date", date_from)
        if date_to:
            query = query.lte("sent_date", date_to)

        all_ids = set()
        offset = 0
        while True:
            resp = self._execute_with_retry(query.range(offset, offset + 499))
            batch = resp.data or []
            all_ids.update(e["id"] for e in batch)
            if len(batch) == 0:
                break
            offset += len(batch)
        return all_ids

    # ------------------------------------------------------------------
    # Action items — prioritized list
    # ------------------------------------------------------------------
    def get_action_items(
        self,
        client_id: str,
        mailbox_id: str,
        min_confidence: float = 0.5,
        limit: int = 50,
        date_from: str = None,
        date_to: str = None,
    ) -> list[dict]:
        email_id_set = self._get_email_ids_in_date_range(mailbox_id, date_from, date_to)
        if email_id_set is not None and not email_id_set:
            return []

        all_rows = []
        offset = 0
        PAGE_SIZE = 500
        while True:
            query = (
                self.client.table("ai_email_intelligence")
                .select("id,email_id,intent,urgency,sentiment,summary,"
                        "suggested_action,confidence,action_buckets,primary_bucket,"
                        "business_signal,business_signal_score,customer_lifecycle_tier")
                .eq("mailbox_id", mailbox_id)
                .eq("processing_status", "completed")
            )
            if client_id:
                query = query.eq("client_id", client_id)
            resp = self._execute_with_retry(
                query.range(offset, offset + PAGE_SIZE - 1)
            )
            batch = resp.data or []
            all_rows.extend(batch)
            if len(batch) == 0:
                break
            offset += len(batch)

        if email_id_set is not None:
            all_rows = [r for r in all_rows if r.get("email_id") in email_id_set]

        action_items = []
        for row in all_rows:
            buckets = row.get("action_buckets") or []
            if isinstance(buckets, str):
                try:
                    buckets = json.loads(buckets)
                except Exception:
                    continue

            for bucket_entry in buckets:
                if not isinstance(bucket_entry, dict):
                    continue
                bucket_name = bucket_entry.get("bucket")
                conf = float(bucket_entry.get("confidence", 0))
                if conf < min_confidence:
                    continue
                if bucket_name not in BUCKET_CONFIG:
                    continue

                config = BUCKET_CONFIG[bucket_name]
                lifecycle = row.get("customer_lifecycle_tier", "")
                action_items.append({
                    "email_id": row.get("email_id"),
                    "bucket": bucket_name,
                    "bucket_label": config["label"],
                    "bucket_color": config["color"],
                    "severity": config["severity"],
                    "recommended_action": config["action"],
                    "confidence": conf,
                    "justification": bucket_entry.get("justification", ""),
                    "email_summary": row.get("summary", ""),
                    "email_suggested_action": row.get("suggested_action", ""),
                    "intent": row.get("intent"),
                    "urgency": row.get("urgency"),
                    "business_signal_score": row.get("business_signal_score", 0),
                    "lifecycle_tier": lifecycle,
                    "lifecycle_label": LIFECYCLE_CONFIG.get(lifecycle, {}).get("label", ""),
                })

        action_items.sort(
            key=lambda x: (
                SEVERITY_ORDER.get(x["severity"], 3),
                -x["confidence"],
                -(x.get("business_signal_score") or 0),
            )
        )

        trimmed = action_items[:limit]

        # Enrich with email metadata
        email_ids = list({item["email_id"] for item in trimmed if item.get("email_id")})
        if email_ids:
            email_map = {}
            for i in range(0, len(email_ids), 50):
                batch_ids = email_ids[i:i + 50]
                try:
                    resp = self.client.table("emails").select(
                        "id,subject,sender_email,sender_name,sent_date"
                    ).in_("id", batch_ids).execute()
                    for e in (resp.data or []):
                        email_map[e["id"]] = e
                except Exception:
                    pass
            for item in trimmed:
                email = email_map.get(item.get("email_id"), {})
                item["email_subject"] = email.get("subject", "")
                item["email_sender"] = email.get("sender_email", "")
                item["email_sender_name"] = email.get("sender_name", "")
                item["email_date"] = email.get("sent_date", "")

        return trimmed

    # ------------------------------------------------------------------
    # Signal summary — counts per signal type
    # ------------------------------------------------------------------
    def get_bucket_summary(
        self,
        mailbox_id: str,
        client_id: Optional[str] = None,
        date_from: str = None,
        date_to: str = None,
    ) -> dict:
        email_id_set = self._get_email_ids_in_date_range(mailbox_id, date_from, date_to)
        if email_id_set is not None and not email_id_set:
            return {bucket: 0 for bucket in BUCKET_CONFIG}

        query = (
            self.client.table("ai_email_intelligence")
            .select("primary_bucket,email_id")
            .eq("mailbox_id", mailbox_id)
            .eq("processing_status", "completed")
        )
        if client_id:
            query = query.eq("client_id", client_id)

        all_rows = []
        offset = 0
        PAGE_SIZE = 500
        while True:
            resp = self._execute_with_retry(query.range(offset, offset + PAGE_SIZE - 1))
            batch = resp.data or []
            all_rows.extend(batch)
            if len(batch) == 0:
                break
            offset += len(batch)

        summary = {bucket: 0 for bucket in BUCKET_CONFIG}
        for row in all_rows:
            if email_id_set is not None and row.get("email_id") not in email_id_set:
                continue
            bucket = row.get("primary_bucket")
            if bucket and bucket in summary:
                summary[bucket] += 1

        return summary


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_bucket_engine: Optional[ActionBucketEngine] = None


def init_bucket_engine(supabase_client) -> ActionBucketEngine:
    global _bucket_engine
    _bucket_engine = ActionBucketEngine(supabase_client)
    return _bucket_engine


def get_bucket_engine() -> Optional[ActionBucketEngine]:
    return _bucket_engine
