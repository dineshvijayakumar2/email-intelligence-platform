"""
Action Bucket Engine — Zero-cost Python rule engine (Session 3)

Layer 2 of the intelligence system. Derives 8 action buckets from:
- Layer 1 AI classification (intent, business_signal, entities)
- Sprint 2 data (engagement, threads, seniority, frequency)

$0 cost — pure Python, no API calls. All rules are deterministic and
version-tracked for traceability.

8 Buckets (4 email-level + 4 relationship-level):
  Email-level:   buying_signal, expansion_signal, churn_risk, competitor_threat
  Relationship:  missed_opportunity, stakeholder_entry, silent_champion, unresolved_block
"""

import time
import logging
from typing import Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Version — stored per row for traceability
# ---------------------------------------------------------------------------
BUCKET_ENGINE_VERSION = "v1.0"

# ---------------------------------------------------------------------------
# Bucket configuration (used by frontend for display)
# ---------------------------------------------------------------------------
BUCKET_CONFIG = {
    "buying_signal": {
        "label": "Buying Signal",
        "color": "green",
        "severity": "critical",
        "action": "Trigger a proposal or sales follow-up",
    },
    "expansion_signal": {
        "label": "Expansion Signal",
        "color": "blue",
        "severity": "critical",
        "action": "Schedule an upsell or strategy call",
    },
    "churn_risk": {
        "label": "Churn Risk",
        "color": "red",
        "severity": "critical",
        "action": "Immediate retention outreach required",
    },
    "competitor_threat": {
        "label": "Competitor Threat",
        "color": "red",
        "severity": "high",
        "action": "Review competitive positioning",
    },
    "missed_opportunity": {
        "label": "Missed Opportunity",
        "color": "red",
        "severity": "critical",
        "action": "Business signal with no response - act now",
    },
    "stakeholder_entry": {
        "label": "Stakeholder Entry",
        "color": "purple",
        "severity": "high",
        "action": "Multi-thread the account",
    },
    "silent_champion": {
        "label": "Silent Champion",
        "color": "orange",
        "severity": "medium",
        "action": "Send personalized check-in",
    },
    "unresolved_block": {
        "label": "Unresolved Block",
        "color": "yellow",
        "severity": "medium",
        "action": "Bump thread to resolve blocker",
    },
}

# Severity ordering for sorting action items
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


# ---------------------------------------------------------------------------
# Email-level bucket rules (derived from AI classification)
# ---------------------------------------------------------------------------
def derive_email_buckets(intel_row: dict) -> list[dict]:
    """
    Derive action buckets for a single email from its AI classification.

    Pure Python — no API calls. Takes the ai_email_intelligence row
    and returns a list of {bucket, confidence, justification}.

    Called during post-processing (after AI classification).
    """
    buckets = []

    intent = intel_row.get("intent")
    business_signal = intel_row.get("business_signal")
    sentiment = intel_row.get("sentiment")
    urgency = intel_row.get("urgency")
    confidence = float(intel_row.get("confidence") or 0.5)
    has_budget = intel_row.get("has_budget_signal", False)
    has_buying = intel_row.get("has_buying_signal", False)
    has_competitor = intel_row.get("has_competitor_mention", False)

    # --- BUYING SIGNAL ---
    # Trigger: pricing inquiry + budget OR buying intent signal
    if intent == "pricing_inquiry" or business_signal == "buying_intent":
        bucket_conf = confidence
        if has_budget:
            bucket_conf = min(bucket_conf + 0.1, 1.0)
        if has_buying:
            bucket_conf = min(bucket_conf + 0.1, 1.0)
        buckets.append({
            "bucket": "buying_signal",
            "confidence": round(bucket_conf, 2),
            "justification": _buying_justification(intel_row),
        })

    # Budget discussion without explicit pricing inquiry
    elif business_signal == "budget_discussion" and has_budget:
        buckets.append({
            "bucket": "buying_signal",
            "confidence": round(confidence * 0.8, 2),
            "justification": "Budget discussion with specific budget signal detected",
        })

    # --- EXPANSION SIGNAL ---
    if intent == "expansion_signal" or business_signal == "expansion_interest":
        buckets.append({
            "bucket": "expansion_signal",
            "confidence": round(confidence, 2),
            "justification": _expansion_justification(intel_row),
        })

    # Renewal intent as a weaker expansion signal
    elif business_signal == "renewal_intent":
        buckets.append({
            "bucket": "expansion_signal",
            "confidence": round(confidence * 0.7, 2),
            "justification": "Renewal intent detected - potential upsell opportunity",
        })

    # --- CHURN RISK (strict — only explicit exit intent) ---
    if intent == "churn_risk" or business_signal == "churn_signal":
        bucket_conf = confidence
        if sentiment in ("negative", "very_negative"):
            bucket_conf = min(bucket_conf + 0.15, 1.0)
        if urgency in ("critical", "high"):
            bucket_conf = min(bucket_conf + 0.1, 1.0)
        # Only flag as churn if confidence is high enough (AI was confident about exit intent)
        if bucket_conf >= 0.6:
            buckets.append({
                "bucket": "churn_risk",
                "confidence": round(bucket_conf, 2),
                "justification": _churn_justification(intel_row),
            })

    # Complaint + very negative sentiment + high urgency (strong implicit churn)
    # Removed: plain complaints with negative sentiment — those are just support issues
    elif intent == "complaint" and sentiment == "very_negative" and urgency in ("critical", "high"):
        buckets.append({
            "bucket": "churn_risk",
            "confidence": round(confidence * 0.5, 2),
            "justification": "Critical complaint with very negative sentiment — potential churn risk",
        })

    # Escalation only counts as churn if also very negative
    elif business_signal == "escalation" and urgency == "critical" and sentiment in ("negative", "very_negative"):
        buckets.append({
            "bucket": "churn_risk",
            "confidence": round(confidence * 0.5, 2),
            "justification": "Critical escalation with negative sentiment suggests potential churn risk",
        })

    # --- COMPETITOR THREAT ---
    if has_competitor and business_signal == "competitive_evaluation":
        buckets.append({
            "bucket": "competitor_threat",
            "confidence": round(confidence, 2),
            "justification": _competitor_justification(intel_row),
        })
    elif has_competitor and intent in ("churn_risk", "complaint", "pricing_inquiry"):
        buckets.append({
            "bucket": "competitor_threat",
            "confidence": round(confidence * 0.7, 2),
            "justification": "Competitor mentioned in context of " + (intent or "inquiry"),
        })

    return buckets


def _buying_justification(row: dict) -> str:
    parts = []
    if row.get("intent") == "pricing_inquiry":
        parts.append("pricing inquiry")
    if row.get("business_signal") == "buying_intent":
        parts.append("buying intent signal")
    if row.get("has_budget_signal"):
        parts.append("budget signal present")
    if row.get("has_buying_signal"):
        parts.append("explicit buying phrases")
    return "Detected: " + ", ".join(parts) if parts else "Buying signal detected"


def _expansion_justification(row: dict) -> str:
    parts = []
    if row.get("intent") == "expansion_signal":
        parts.append("expansion intent")
    if row.get("business_signal") == "expansion_interest":
        parts.append("expansion interest signal")
    return "Detected: " + ", ".join(parts) if parts else "Expansion signal detected"


def _churn_justification(row: dict) -> str:
    parts = []
    if row.get("intent") == "churn_risk":
        parts.append("churn risk intent")
    if row.get("business_signal") == "churn_signal":
        parts.append("churn signal")
    if row.get("sentiment") in ("negative", "very_negative"):
        parts.append("negative sentiment")
    if row.get("urgency") in ("critical", "high"):
        parts.append("high urgency")
    return "Detected: " + ", ".join(parts) if parts else "Churn risk detected"


def _competitor_justification(row: dict) -> str:
    competitors = row.get("competitors_mentioned", [])
    if competitors:
        return f"Competitor(s) mentioned: {', '.join(competitors[:3])}"
    return "Competitor mention detected"


# ---------------------------------------------------------------------------
# Relationship-level bucket rules (derived from Sprint 2 data)
# ---------------------------------------------------------------------------
def derive_relationship_buckets(
    intel_rows: list[dict],
    contact_data: dict,
    company_data: dict,
    thread_data: list[dict],
) -> list[dict]:
    """
    Derive relationship-level buckets using AI classification + Sprint 2 data.

    These operate across multiple emails / the account relationship, not per-email.

    Args:
        intel_rows: Recent ai_email_intelligence rows for this contact/company
        contact_data: customer_contacts row (engagement, seniority, frequency)
        company_data: customer_companies row (relationship_status, thread counts)
        thread_data: thread_status rows for this contact/company

    Returns:
        List of {bucket, confidence, justification, context}
    """
    buckets = []

    # --- MISSED OPPORTUNITY ---
    # High-signal emails with no outbound response
    for row in intel_rows:
        signal_score = int(row.get("business_signal_score") or 0)
        direction = row.get("email_direction", "inbound")  # joined from emails table
        if signal_score >= 50 and direction == "inbound":
            # Check if there's a response to this email
            email_thread = row.get("thread_id")
            has_response = any(
                r.get("email_direction") == "outbound" and r.get("thread_id") == email_thread
                for r in intel_rows
            ) if email_thread else False

            if not has_response:
                buckets.append({
                    "bucket": "missed_opportunity",
                    "confidence": min(signal_score / 100.0, 1.0),
                    "justification": f"High-signal email (score {signal_score}) with no outbound response",
                    "context": {"email_id": row.get("email_id"), "signal_score": signal_score},
                })

    # --- STAKEHOLDER ENTRY ---
    # New decision-maker or senior contact appearing
    seniority = contact_data.get("seniority_level", "unknown")
    is_dm = contact_data.get("is_decision_maker", False)
    engagement = int(contact_data.get("engagement_score") or 0)

    if is_dm and seniority in ("c_level", "vp", "director") and engagement < 30:
        # Senior DM with low engagement = new/under-engaged stakeholder
        buckets.append({
            "bucket": "stakeholder_entry",
            "confidence": 0.8,
            "justification": f"Decision-maker ({seniority}) with low engagement ({engagement})",
            "context": {"seniority": seniority, "engagement": engagement},
        })
    elif seniority in ("c_level", "vp") and len(intel_rows) <= 3:
        # Very senior person with few emails = new stakeholder
        buckets.append({
            "bucket": "stakeholder_entry",
            "confidence": 0.6,
            "justification": f"Senior contact ({seniority}) with only {len(intel_rows)} emails",
            "context": {"seniority": seniority, "email_count": len(intel_rows)},
        })

    # --- SILENT CHAMPION ---
    # Previously engaged contact going quiet
    frequency_trend = contact_data.get("frequency_trend", "stable")
    if frequency_trend == "declining" and engagement >= 40:
        buckets.append({
            "bucket": "silent_champion",
            "confidence": 0.7,
            "justification": f"Declining frequency despite decent engagement ({engagement})",
            "context": {"frequency_trend": frequency_trend, "engagement": engagement},
        })

    # Company-level: relationship cooling
    rel_status = company_data.get("relationship_status", "active")
    comm_health = company_data.get("communication_health", "good")
    if rel_status == "cooling" or comm_health in ("needs_attention", "critical"):
        existing = [b for b in buckets if b["bucket"] == "silent_champion"]
        if not existing:
            buckets.append({
                "bucket": "silent_champion",
                "confidence": 0.6,
                "justification": f"Company relationship {rel_status}, communication {comm_health}",
                "context": {"relationship_status": rel_status, "communication_health": comm_health},
            })

    # --- UNRESOLVED BLOCK ---
    # Overdue or dropped threads
    for thread in thread_data:
        status = thread.get("status")
        days_since = int(thread.get("days_since_last_email") or 0)
        is_overdue = thread.get("is_overdue", False)

        if status == "overdue" or is_overdue:
            buckets.append({
                "bucket": "unresolved_block",
                "confidence": min(0.5 + (days_since / 30.0) * 0.3, 0.95),
                "justification": f"Overdue thread ({days_since} days since last email)",
                "context": {"thread_id": thread.get("thread_id"), "days_since": days_since},
            })
        elif status == "dropped" and days_since > 14:
            buckets.append({
                "bucket": "unresolved_block",
                "confidence": 0.6,
                "justification": f"Dropped thread ({days_since} days inactive)",
                "context": {"thread_id": thread.get("thread_id"), "days_since": days_since},
            })

    return buckets


# ---------------------------------------------------------------------------
# Main engine class
# ---------------------------------------------------------------------------
class ActionBucketEngine:
    """
    Derives and stores action buckets. Zero-cost Python rules.
    Reads from ai_email_intelligence + Sprint 2 tables, writes
    bucket data back to ai_email_intelligence.
    """

    def __init__(self, supabase_client):
        self.client = supabase_client

    @staticmethod
    def _execute_with_retry(query_builder, max_retries: int = 3, base_delay: float = 2.0):
        """Execute a Supabase query with retry for transient errors."""
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
                    'JSON could not be generated', 'ECONNRESET', 'ETIMEDOUT', 'ConnectionTerminated', 'PROTOCOL_ERROR',
                ])
                if is_transient and attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        f"Transient Supabase error (attempt {attempt + 1}/{max_retries + 1}), "
                        f"retrying in {delay}s: {error_str[:200]}"
                    )
                    time.sleep(delay)
                    continue
                raise
        raise last_error

    # ------------------------------------------------------------------
    # Process email-level buckets for all completed intel rows
    # ------------------------------------------------------------------
    def process_email_buckets(self, mailbox_id: str) -> dict:
        """
        Derive email-level buckets for all completed intel rows that
        don't have buckets assigned yet.

        Returns: {"processed": int, "buckets_assigned": int}
        """
        # Fetch completed intel rows without buckets
        all_rows = []
        offset = 0
        PAGE_SIZE = 500
        while True:
            resp = self._execute_with_retry(
                self.client.table("ai_email_intelligence")
                .select("id,email_id,intent,urgency,sentiment,confidence,business_signal,"
                        "has_budget_signal,has_buying_signal,has_competitor_mention,"
                        "has_deadline,business_signal_score,competitors_mentioned,"
                        "action_buckets")
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
            # Skip if already has buckets
            existing_buckets = row.get("action_buckets")
            if existing_buckets and existing_buckets != "[]" and existing_buckets != []:
                continue

            buckets = derive_email_buckets(row)
            primary = buckets[0]["bucket"] if buckets else None

            update_batch.append({
                "id": row["id"],
                "action_buckets": buckets,
                "primary_bucket": primary,
                "bucket_engine_version": BUCKET_ENGINE_VERSION,
            })

            processed += 1
            buckets_assigned += len(buckets)

            # Flush in batches of 100
            if len(update_batch) >= 100:
                self._flush_bucket_updates(update_batch)
                update_batch = []

        # Flush remaining
        if update_batch:
            self._flush_bucket_updates(update_batch)

        logger.info(f"Email buckets: {processed} processed, {buckets_assigned} buckets assigned")
        return {"processed": processed, "buckets_assigned": buckets_assigned}

    def _flush_bucket_updates(self, updates: list[dict]):
        """Write bucket updates back to ai_email_intelligence in batches."""
        for update in updates:
            try:
                self._execute_with_retry(
                    self.client.table("ai_email_intelligence")
                    .update({
                        "action_buckets": update["action_buckets"],
                        "primary_bucket": update["primary_bucket"],
                        "bucket_engine_version": update["bucket_engine_version"],
                    })
                    .eq("id", update["id"])
                )
            except Exception as e:
                logger.error(f"Failed to update buckets for {update['id']}: {e}")

    # ------------------------------------------------------------------
    # Compute relationship-level buckets for a company
    # ------------------------------------------------------------------
    def compute_relationship_buckets(
        self,
        company_id: str,
        mailbox_id: str,
        client_id: Optional[str] = None,
    ) -> list[dict]:
        """
        Compute relationship-level buckets for a company by combining
        AI classification data with Sprint 2 engagement/thread/seniority data.

        Returns: List of relationship bucket dicts.
        """
        # Get AI intelligence rows for this company's contacts
        intel_rows = self._get_company_intel(company_id, mailbox_id)

        # Get company data
        company_data = self._get_company_data(company_id)

        # Get contact data for the company's contacts
        contacts = self._get_company_contacts(company_id)

        # Get thread data
        thread_data = self._get_company_threads(company_id)

        all_buckets = []
        for contact in contacts:
            contact_intel = [
                r for r in intel_rows
                if r.get("customer_contact_id") == contact.get("id")
            ]
            buckets = derive_relationship_buckets(
                contact_intel, contact, company_data, thread_data
            )
            for b in buckets:
                b["contact_id"] = contact.get("id")
                b["contact_name"] = contact.get("name") or contact.get("email")
            all_buckets.extend(buckets)

        return all_buckets

    def _get_company_intel(self, company_id: str, mailbox_id: str) -> list[dict]:
        """Fetch AI intelligence rows for emails linked to a company."""
        # Get email IDs linked to this company
        email_resp = self._execute_with_retry(
            self.client.table("emails")
            .select("id,thread_id,direction")
            .eq("customer_company_id", company_id)
            .eq("mailbox_id", mailbox_id)
            .order("sent_date", desc=True)
            .range(0, 99)  # Last 100 emails
        )
        emails = email_resp.data or []
        if not emails:
            return []

        email_ids = [e["id"] for e in emails]
        email_lookup = {e["id"]: e for e in emails}

        # Fetch intel for these emails
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
        """Fetch company row from customer_companies."""
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
        """Fetch contacts for a company."""
        all_contacts = []
        offset = 0
        PAGE_SIZE = 500
        while True:
            resp = self._execute_with_retry(
                self.client.table("customer_contacts")
                .select("id,name,email,seniority_level,functional_role,"
                        "is_decision_maker,engagement_score,frequency_trend")
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
        """Fetch thread status rows for a company."""
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

    # ------------------------------------------------------------------
    # Helper: get email IDs within a sent_date range
    # ------------------------------------------------------------------
    def _get_email_ids_in_date_range(
        self, mailbox_id: str, date_from: str = None, date_to: str = None
    ) -> Optional[set]:
        """Get email IDs from the emails table within a sent_date range.

        Returns None if no date filtering needed, empty set if no emails match.
        """
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
    # Action items — prioritized list across all buckets
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
        """
        Get prioritized action items from all buckets.

        Returns items sorted by severity (critical > high > medium) then confidence.
        Each item includes the email context for display.
        Date-scoped via email sent_date when date_from/date_to provided.
        """
        # Date filter: get valid email IDs in range
        email_id_set = self._get_email_ids_in_date_range(mailbox_id, date_from, date_to)
        if email_id_set is not None and not email_id_set:
            return []

        # Fetch intel rows with buckets
        all_rows = []
        offset = 0
        PAGE_SIZE = 500
        while True:
            resp = self._execute_with_retry(
                self.client.table("ai_email_intelligence")
                .select("id,email_id,intent,urgency,sentiment,summary,"
                        "suggested_action,confidence,action_buckets,primary_bucket,"
                        "business_signal,business_signal_score")
                .eq("mailbox_id", mailbox_id)
                .eq("processing_status", "completed")
                .range(offset, offset + PAGE_SIZE - 1)
            )
            batch = resp.data or []
            all_rows.extend(batch)
            if len(batch) == 0:
                break
            offset += len(batch)

        # Filter by client if provided
        if client_id:
            # Fetch filtered intel by client_id instead
            all_rows_filtered = []
            offset = 0
            while True:
                resp = self._execute_with_retry(
                    self.client.table("ai_email_intelligence")
                    .select("id,email_id,intent,urgency,sentiment,summary,"
                            "suggested_action,confidence,action_buckets,primary_bucket,"
                            "business_signal,business_signal_score")
                    .eq("client_id", client_id)
                    .eq("mailbox_id", mailbox_id)
                    .eq("processing_status", "completed")
                    .range(offset, offset + PAGE_SIZE - 1)
                )
                batch = resp.data or []
                all_rows_filtered.extend(batch)
                if len(batch) == 0:
                    break
                offset += len(batch)
            all_rows = all_rows_filtered

        # Apply date filter (post-filter by email_id)
        if email_id_set is not None:
            all_rows = [r for r in all_rows if r.get("email_id") in email_id_set]

        # Build action items from buckets
        action_items = []
        for row in all_rows:
            buckets = row.get("action_buckets") or []
            if isinstance(buckets, str):
                try:
                    import json
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
                })

        # Sort by severity then confidence
        action_items.sort(
            key=lambda x: (
                SEVERITY_ORDER.get(x["severity"], 3),
                -x["confidence"],
                -(x.get("business_signal_score") or 0),
            )
        )

        return action_items[:limit]

    # ------------------------------------------------------------------
    # Bucket summary — counts per bucket type
    # ------------------------------------------------------------------
    def get_bucket_summary(
        self,
        mailbox_id: str,
        client_id: Optional[str] = None,
        date_from: str = None,
        date_to: str = None,
    ) -> dict:
        """
        Get summary counts per bucket type.
        Date-scoped via email sent_date when date_from/date_to provided.

        Returns: {"buying_signal": 5, "churn_risk": 2, ...}
        """
        # Date filter: get valid email IDs in range
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
            resp = self._execute_with_retry(
                query.range(offset, offset + PAGE_SIZE - 1)
            )
            batch = resp.data or []
            all_rows.extend(batch)
            if len(batch) == 0:
                break
            offset += len(batch)

        # Count by bucket (with date filter applied)
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
    """Initialize the global bucket engine with a Supabase client."""
    global _bucket_engine
    _bucket_engine = ActionBucketEngine(supabase_client)
    return _bucket_engine


def get_bucket_engine() -> Optional[ActionBucketEngine]:
    """Get the initialized bucket engine instance."""
    return _bucket_engine
