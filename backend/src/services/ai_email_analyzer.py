"""
AI Email Analyzer — Core Intelligence Engine (Session 2)

The heart of Sprint 3: sends batches of emails to Claude Haiku for
classification + entity extraction in ONE API call per batch. Then
post-processes results deterministically in Python (boolean flags,
business_signal_score). Bucket derivation happens in Session 3.

Design principles:
- ONE Claude call per batch (10 emails) — cost-efficient
- Strict Pydantic validation of every LLM response
- Per-item failure — one bad email never kills the batch
- Idempotent — safe to re-run (processing_status field)
- Version tracking on every row (prompt, scoring, bucket engine)
- Raw AI response stored for debugging + compliance
- No business logic in prompts — LLM classifies, Python decides
"""

import json
import re
import time
import logging
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime, timedelta
from pydantic import BaseModel, confloat, constr

from .ai_client import get_ai_client, AIResponse
from .ai_privacy_filter import sanitize_email_body
from .ai_usage_tracker import get_usage_tracker
from .ai_action_bucket_engine import derive_email_buckets, BUCKET_ENGINE_VERSION

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Versioning constants
# ---------------------------------------------------------------------------
PROMPT_VERSION = "v1.2"
SCORING_VERSION = "v1.0"
BATCH_SIZE = 20  # emails per Claude Haiku call (doubled from 10 for cost reduction)
DEFAULT_LOOKBACK_DAYS = 7  # Default: only analyze emails from last 7 days

# ---------------------------------------------------------------------------
# Pre-filter patterns — skip these emails entirely (saves ~$0.001/email)
# Leverages Sprint 2's contact classification + response_time_tracker patterns
# ---------------------------------------------------------------------------
AUTOMATED_SUBJECT_PATTERNS = [
    # Auto-replies (mirrors response_time_tracker.py patterns)
    r'out of office', r'out of the office', r'automatic reply',
    r'auto reply', r'auto-reply', r'autoreply', r'vacation',
    r'away from office', r'currently out', r'i am away', r"i'm away",
    r'absence notification',
    # Delivery failures
    r'delivery status notification', r'mail delivery failed',
    r'undeliverable', r'returned mail', r'delivery failure',
    r'message not delivered', r'delivery has failed',
    # System/calendar
    r'calendar invitation', r'meeting accepted', r'meeting declined',
    r'meeting tentative', r'event reminder', r'invitation:',
    # Transactional/receipts
    r'payment received', r'payment confirmation', r'invoice #',
    r'order confirmation', r'shipping notification', r'tracking number',
    r'receipt for your', r'your receipt from', r'transaction alert',
    r'statement available', r'account statement',
    # Subscriptions/marketing
    r'unsubscribe', r'email preferences', r'newsletter',
]

AUTOMATED_SENDER_PATTERNS = [
    r'^noreply@', r'^no-reply@', r'^no\.reply@',
    r'^mailer-daemon@', r'^postmaster@',
    r'^notifications?@', r'^alerts?@', r'^system@',
    r'^donotreply@', r'^do-not-reply@', r'^do\.not\.reply@',
    r'^support@.*\.noreply\.',
]

_AUTOMATED_SUBJECT_RE = [re.compile(p, re.IGNORECASE) for p in AUTOMATED_SUBJECT_PATTERNS]
_AUTOMATED_SENDER_RE = [re.compile(p, re.IGNORECASE) for p in AUTOMATED_SENDER_PATTERNS]

# Forward-only pattern: subject starts with Fwd:/FW: and body is short (just forwarding, no commentary)
_FORWARD_SUBJECT_RE = re.compile(r'^(?:fwd?|fw)\s*:', re.IGNORECASE)


def is_automated_email(email: dict) -> bool:
    """
    Detect automated/transactional emails using subject + sender patterns.
    These emails waste AI credits with low-value classifications.
    """
    subject = (email.get("subject") or "").lower()
    sender = (email.get("sender_email") or "").lower()

    # Check subject patterns
    for pattern in _AUTOMATED_SUBJECT_RE:
        if pattern.search(subject):
            return True

    # Check sender patterns
    for pattern in _AUTOMATED_SENDER_RE:
        if pattern.search(sender):
            return True

    return False


def is_forward_only_email(email: dict) -> bool:
    """
    Detect forward-only emails with no commentary added.
    These are low-value for AI analysis — the original email they forwarded
    will be analyzed separately when it arrives.
    """
    subject = email.get("subject") or ""
    body = email.get("body_text") or ""

    if not _FORWARD_SUBJECT_RE.match(subject):
        return False

    # Forward-only: body is very short (< 50 chars of original content)
    # or body starts with forwarded message markers with no text before them
    body_stripped = body.strip()
    if len(body_stripped) < 50:
        return True

    # Check if body is just forwarded content with no added commentary
    forward_markers = [
        "---------- forwarded message ----------",
        "-----original message-----",
        "begin forwarded message",
        "from:",  # Sometimes forwards just start with the headers
    ]
    body_lower = body_stripped.lower()
    for marker in forward_markers:
        idx = body_lower.find(marker)
        if idx != -1 and idx < 30:  # Marker appears near the start
            return True

    return False


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are a structured email intelligence engine for a B2B account management platform.

Your task is to analyze business emails and return STRICT JSON.

You must:
- Follow the schema exactly.
- Use only the allowed enum values.
- Return null if uncertain.
- Never invent entities.
- Never guess missing data.
- Never include markdown.
- Never include explanations.
- Return only a valid JSON array.

If the email does not contain enough information for a field, return null or an empty array.
Do not add fields not defined in the schema.

DIRECTION-AWARE RULES:
- Each email has a "direction" field: "outbound" means OUR team sent it, "inbound" means we received it.
- For OUTBOUND emails (direction="outbound"): set action_type to "no_action". Do NOT suggest follow-up actions in suggested_action — instead describe what was communicated. Focus on extracting entities, topics, and business signals from what was sent.
- For INBOUND emails: analyze normally and suggest appropriate actions.
- For financial transaction emails (payment confirmations, invoices, receipts, statements): set sentiment to "neutral", urgency to "low" or "none", business_signal to "contract_activity" or null. Do not classify routine payments as negative sentiment.

CHURN RISK CLASSIFICATION — BE STRICT:
- "churn_risk" intent and "churn_signal" business_signal are ONLY for emails that contain EXPLICIT indicators of a customer considering leaving, cancelling, or switching providers.
- Examples of TRUE churn risk: "We're evaluating alternatives", "considering not renewing", "this isn't working for us anymore", "looking to switch", "cancel our subscription", "downgrade our plan", threats to leave.
- These are NOT churn risk — classify them as "complaint", "question", or "feature_request" instead:
  - A customer reporting a bug or issue they want fixed
  - A customer asking how to do something (support request)
  - A customer expressing mild frustration about a feature
  - A customer asking about pricing changes (use "pricing_inquiry")
  - General negative feedback without exit intent (use "negative_feedback" business signal)
- Only use "churn_signal" business_signal when the email explicitly signals the customer may leave. Dissatisfaction alone is NOT churn — it's "negative_feedback".

PRE-CLASSIFICATION HINTS:
- Some emails include a "pre_classification" field with rule-based tags already applied (e.g., "urgent", "financial", "meeting", "reply").
- Use these as strong hints. For example, if tags include "urgent", lean toward higher urgency. If sender_type is "human", treat as a real person.
- These hints are deterministic and reliable, but you may override them if the email content clearly contradicts them.
- Do NOT copy pre_classification values verbatim; use your own judgment informed by these hints."""

USER_PROMPT_TEMPLATE = """Analyze the following emails.
For each email, return one JSON object with the following schema:

{{
  "email_id": string,
  "intent": one of ["action_required", "fyi_update", "meeting_scheduling", "question",
    "complaint", "positive_feedback", "pricing_inquiry", "feature_request",
    "expansion_signal", "churn_risk", "follow_up", "introduction", "other"],
  "urgency": one of ["critical", "high", "medium", "low", "none"],
  "sentiment": one of ["very_positive", "positive", "neutral", "negative", "very_negative"],
  "sentiment_score": number between -1.0 and 1.0,
  "action_type": one of ["respond_to_inquiry", "provide_quote", "schedule_meeting",
    "escalate_internally", "send_follow_up", "resolve_issue", "acknowledge_receipt",
    "no_action", "delegate", "prepare_document"],
  "business_signal": one of ["buying_intent", "renewal_intent", "expansion_interest",
    "churn_signal", "competitive_evaluation", "budget_discussion", "escalation",
    "positive_feedback", "negative_feedback", "contract_activity", "neutral"] or null,
  "thread_role": one of ["initial", "reply", "forward", "auto_reply",
    "cc_addition", "internal"] or null,
  "summary": short 1-2 sentence factual summary,
  "suggested_action": one short sentence describing what the account manager should do,
  "key_topics": array of 1-3 short strings,
  "confidence": number between 0.0 and 1.0,
  "justification": one short sentence referencing specific words or phrases from the
    email that justify the intent and urgency,
  "entities": {{
    "competitors_mentioned": array of company names,
    "products_mentioned": array of product/service names,
    "budget_signal": {{"amount": string or null, "timeframe": string or null,
      "context": string or null}} or null,
    "buying_signals": array of short phrases from the email indicating buying intent,
    "people_mentioned": [{{"name": string, "role": string or null, "context": string}}],
    "dates_mentioned": [{{"date": string, "context": string}}],
    "action_items_extracted": array of short action items explicitly mentioned
  }}
}}

Rules:
- Do not hallucinate competitors.
- Do not hallucinate budget amounts.
- Only extract information explicitly present.
- If no entities exist, return empty arrays.
- If no budget signal exists, return null.

EMAILS:
{emails_json}

Return ONLY a JSON array in the same order as input."""


# ---------------------------------------------------------------------------
# Pydantic validation models
# ---------------------------------------------------------------------------
class EntityExtraction(BaseModel):
    competitors_mentioned: list[str] = []
    products_mentioned: list[str] = []
    budget_signal: Optional[dict] = None
    buying_signals: list[str] = []
    people_mentioned: list[dict] = []
    dates_mentioned: list[dict] = []
    action_items_extracted: list[str] = []


class EmailClassificationResult(BaseModel):
    """Validates each email's AI output. LLM response MUST match this exactly."""
    email_id: str
    intent: Literal[
        "action_required", "fyi_update", "meeting_scheduling", "question",
        "complaint", "positive_feedback", "pricing_inquiry", "feature_request",
        "expansion_signal", "churn_risk", "follow_up", "introduction", "other"
    ]
    urgency: Literal["critical", "high", "medium", "low", "none"]
    sentiment: Literal["very_positive", "positive", "neutral", "negative", "very_negative"]
    sentiment_score: confloat(ge=-1.0, le=1.0)
    action_type: Literal[
        "respond_to_inquiry", "provide_quote", "schedule_meeting",
        "escalate_internally", "send_follow_up", "resolve_issue",
        "acknowledge_receipt", "no_action", "delegate", "prepare_document"
    ]
    business_signal: Optional[Literal[
        "buying_intent", "renewal_intent", "expansion_interest",
        "churn_signal", "competitive_evaluation", "budget_discussion",
        "escalation", "positive_feedback", "negative_feedback",
        "contract_activity", "neutral"
    ]] = None
    thread_role: Optional[Literal[
        "initial", "reply", "forward", "auto_reply", "cc_addition", "internal"
    ]] = None
    summary: constr(max_length=500) = ""
    suggested_action: constr(max_length=300) = ""
    key_topics: list[str] = []
    confidence: confloat(ge=0.0, le=1.0) = 0.5
    justification: str = ""
    entities: EntityExtraction = EntityExtraction()


# ---------------------------------------------------------------------------
# JSON guard layer
# ---------------------------------------------------------------------------
def clean_llm_output(text: str) -> str:
    """Strip markdown fences and whitespace before JSON parsing."""
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 3:
            text = parts[1]
        elif len(parts) >= 2:
            text = parts[1]
        # Remove optional language tag (e.g., "json")
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


def repair_truncated_json(text: str) -> Optional[list]:
    """Try to recover partial results from truncated JSON array.

    When max_tokens cuts off the LLM response mid-JSON, we find the last
    complete object in the array and parse everything up to that point.
    Returns None if repair fails.
    """
    text = text.strip()
    if not text.startswith("["):
        return None

    # Find the last complete object by looking for "},\n  {" or "}\n]" boundaries
    last_complete = -1
    brace_depth = 0
    in_string = False
    escape_next = False

    for i, ch in enumerate(text):
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '{':
            brace_depth += 1
        elif ch == '}':
            brace_depth -= 1
            if brace_depth == 0:
                last_complete = i

    if last_complete <= 0:
        return None

    # Take everything up to last complete object, close the array
    truncated = text[:last_complete + 1].rstrip().rstrip(",") + "\n]"
    try:
        parsed = json.loads(truncated)
        if isinstance(parsed, list) and len(parsed) > 0:
            logger.info(f"Repaired truncated JSON: recovered {len(parsed)} items")
            return parsed
    except json.JSONDecodeError:
        pass
    return None


# ---------------------------------------------------------------------------
# Business signal scoring (deterministic Python — never in prompts)
# ---------------------------------------------------------------------------
SIGNAL_WEIGHTS = {
    "has_budget_signal": 30,
    "has_buying_signal": 25,
    "has_competitor_mention": 15,
    "has_deadline": 10,
    # business_signal field weights
    "buying_intent": 20,
    "expansion_interest": 15,
    "churn_signal": 15,
    "budget_discussion": 10,
    "competitive_evaluation": 10,
}


def compute_business_signal_score(flags: dict, business_signal: Optional[str]) -> int:
    """
    Compute 0-100 score from boolean flags + business_signal field.
    Pure Python — deterministic, no LLM involvement.
    """
    score = 0
    for flag_key in ["has_budget_signal", "has_buying_signal", "has_competitor_mention", "has_deadline"]:
        if flags.get(flag_key):
            score += SIGNAL_WEIGHTS[flag_key]
    if business_signal and business_signal in SIGNAL_WEIGHTS:
        score += SIGNAL_WEIGHTS[business_signal]
    return min(score, 100)


# ---------------------------------------------------------------------------
# Post-processing: extract boolean flags from entities
# ---------------------------------------------------------------------------
def post_process_classification(result: EmailClassificationResult) -> dict:
    """
    Convert validated Pydantic result into a database row dict.
    Computes boolean flags and business_signal_score deterministically.
    """
    entities = result.entities

    flags = {
        "has_budget_signal": entities.budget_signal is not None,
        "has_buying_signal": len(entities.buying_signals) > 0,
        "has_competitor_mention": len(entities.competitors_mentioned) > 0,
        "has_deadline": len(entities.dates_mentioned) > 0,
    }

    signal_score = compute_business_signal_score(flags, result.business_signal)

    row_data = {
        # Classification
        "intent": result.intent,
        "urgency": result.urgency,
        "sentiment": result.sentiment,
        "sentiment_score": result.sentiment_score,
        "summary": result.summary,
        "suggested_action": result.suggested_action,
        "key_topics": result.key_topics,
        "confidence": result.confidence,
        "justification": result.justification,

        # Multi-axis
        "action_type": result.action_type,
        "business_signal": result.business_signal,
        "thread_role": result.thread_role,

        # Entities (stored as separate columns)
        "competitors_mentioned": entities.competitors_mentioned,
        "products_mentioned": entities.products_mentioned,
        "budget_signals": entities.budget_signal,  # JSONB column name is budget_signals
        "buying_signals": entities.buying_signals,
        "people_mentioned": entities.people_mentioned,
        "dates_mentioned": entities.dates_mentioned,
        "action_items_extracted": entities.action_items_extracted,

        # Boolean flags (computed in Python)
        "has_budget_signal": flags["has_budget_signal"],
        "has_buying_signal": flags["has_buying_signal"],
        "has_competitor_mention": flags["has_competitor_mention"],
        "has_deadline": flags["has_deadline"],
        "business_signal_score": signal_score,
    }

    # Derive email-level action buckets (Layer 2 — zero cost)
    buckets = derive_email_buckets(row_data)
    row_data["action_buckets"] = buckets
    row_data["primary_bucket"] = buckets[0]["bucket"] if buckets else None
    row_data["bucket_engine_version"] = BUCKET_ENGINE_VERSION

    return row_data


# ---------------------------------------------------------------------------
# Main analyzer class
# ---------------------------------------------------------------------------
class AIEmailAnalyzer:
    """
    Core intelligence engine — classifies emails, extracts entities,
    computes business signals. Uses Claude Haiku via ai_client.
    """

    def __init__(self, supabase_client):
        self.client = supabase_client
        self.ai_client = get_ai_client()

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
                    'JSON could not be generated', 'ECONNRESET', 'ETIMEDOUT',
                    'ConnectionTerminated', 'PROTOCOL_ERROR',
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
    # Fetch unanalyzed emails (with Sprint 2 pre-filtering)
    # ------------------------------------------------------------------
    def _get_auto_reply_ids(self, mailbox_id: str) -> set:
        """
        Get email IDs flagged as auto-replies by Sprint 2's response_time_tracker.
        Uses email_response_metrics.is_auto_reply = true.
        """
        auto_reply_ids = set()
        offset = 0
        PAGE_SIZE = 500
        while True:
            try:
                resp = self._execute_with_retry(
                    self.client.table("email_response_metrics")
                    .select("email_id")
                    .eq("is_auto_reply", 'true')
                    .range(offset, offset + PAGE_SIZE - 1)
                )
                batch = resp.data or []
                for row in batch:
                    if row.get("email_id"):
                        auto_reply_ids.add(row["email_id"])
                if len(batch) == 0:
                    break
                offset += len(batch)
            except Exception as e:
                logger.warning(f"Could not fetch auto-reply IDs: {e}")
                break
        return auto_reply_ids

    def _get_noreply_contact_ids(self, mailbox_id: str) -> set:
        """
        Get email IDs linked to automated/mailing-list contacts (Sprint 2 classification).
        Uses customer_contacts.contact_type IN ('automated', 'mailing_list').
        """
        noreply_emails = set()
        try:
            # Get automated + mailing_list contact IDs
            # Supabase lacks .or_(), so fetch both types separately
            all_noreply_ids = []
            for ctype in ("automated", "mailing_list"):
                resp = self._execute_with_retry(
                    self.client.table("customer_contacts")
                    .select("id")
                    .eq("contact_type", ctype)
                    .range(0, 499)
                )
                all_noreply_ids.extend(r["id"] for r in (resp.data or []) if r.get("id"))
            noreply_ids = list(set(all_noreply_ids))
            if not noreply_ids:
                return noreply_emails

            # Get emails linked to those contacts
            for i in range(0, len(noreply_ids), 500):
                chunk = noreply_ids[i:i + 500]
                resp = self._execute_with_retry(
                    self.client.table("emails")
                    .select("id")
                    .eq("mailbox_id", mailbox_id)
                    .in_("customer_contact_id", chunk)
                    .range(0, 4999)
                )
                for row in (resp.data or []):
                    if row.get("id"):
                        noreply_emails.add(row["id"])
        except Exception as e:
            logger.warning(f"Could not fetch noreply contact emails: {e}")
        return noreply_emails

    def _get_rule_based_skip_ids(self, mailbox_id: str) -> set:
        """
        Get email IDs that EmailTagger already classified as low-value.
        Reads from email_categories table — zero cost, rule-based tags.
        Skips: spam, marketing, system, automated emails.
        """
        skip_categories = [
            'spam', 'marketing', 'system', 'automated',
            '_meta_spam', '_meta_marketing',
            '_meta_sender_system', '_meta_sender_marketing', '_meta_sender_automated',
        ]
        skip_ids = set()
        offset = 0
        PAGE_SIZE = 500
        while True:
            try:
                resp = self._execute_with_retry(
                    self.client.table("email_categories")
                    .select("email_id")
                    .in_("category", skip_categories)
                    .range(offset, offset + PAGE_SIZE - 1)
                )
                batch = resp.data or []
                for row in batch:
                    if row.get("email_id"):
                        skip_ids.add(row["email_id"])
                if len(batch) == 0:
                    break
                offset += len(batch)
            except Exception as e:
                logger.warning(f"Could not fetch rule-based skip IDs: {e}")
                break
        return skip_ids

    def _get_unanalyzed_emails(
        self,
        mailbox_id: str,
        limit: int = 50,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> List[dict]:
        """
        Get emails that haven't been analyzed yet OR failed previously.

        Args:
            mailbox_id: Target mailbox UUID
            limit: Max emails to return
            date_from: ISO date string — only analyze emails sent after this date
            date_to: ISO date string — only analyze emails sent before this date

        Hybrid pre-filtering (4 layers, all free):
        1. Date range filter (default: last 7 days) — avoids processing old emails
        2. Rule-based tags from EmailTagger (email_categories: spam, marketing, system, automated)
        3. Sprint 2 auto-replies (email_response_metrics) + noreply contacts (customer_contacts)
        4. Local regex patterns (forward-only, automated subjects/senders)

        This saves ~$0.001/email by avoiding AI calls on low-value emails.
        """
        # Step 1: Get already-analyzed email IDs (completed or skipped)
        analyzed_ids = set()
        offset = 0
        PAGE_SIZE = 500
        while True:
            resp = self._execute_with_retry(
                self.client.table("ai_email_intelligence")
                .select("email_id,processing_status")
                .eq("mailbox_id", mailbox_id)
                .range(offset, offset + PAGE_SIZE - 1)
            )
            batch = resp.data or []
            for row in batch:
                status = row.get("processing_status")
                if row.get("email_id") and status in ("completed", "skipped"):
                    analyzed_ids.add(row["email_id"])
            if len(batch) == 0:
                break
            offset += len(batch)

        # Step 2: Get IDs to skip (rule-based tags + Sprint 2 auto-replies + noreply contacts)
        skip_ids = self._get_rule_based_skip_ids(mailbox_id)
        rule_based_count = len(skip_ids)
        skip_ids |= self._get_auto_reply_ids(mailbox_id)
        skip_ids |= self._get_noreply_contact_ids(mailbox_id)
        logger.info(f"Pre-filter: {len(skip_ids)} emails to skip ({rule_based_count} rule-based tags, {len(skip_ids) - rule_based_count} auto-reply/noreply)")

        # Step 3: Fetch emails from mailbox with date filter
        all_emails = []
        skipped_count = 0
        forward_skipped = 0
        offset = 0
        while len(all_emails) < limit:
            fetch_size = min(PAGE_SIZE, limit - len(all_emails) + 200)  # overfetch to account for filtering
            query = (
                self.client.table("emails")
                .select("id,mailbox_id,subject,body_text,sender_email,sender_name,sent_date,direction,thread_id,is_reply,client_id,customer_contact_id,customer_company_id")
                .eq("mailbox_id", mailbox_id)
                .order("sent_date", desc=True)
            )
            # Apply date range filter
            if date_from:
                query = query.gte("sent_date", date_from)
            if date_to:
                query = query.lte("sent_date", date_to)
            resp = self._execute_with_retry(
                query.range(offset, offset + fetch_size - 1)
            )
            batch = resp.data or []
            if len(batch) == 0:
                break
            offset += len(batch)

            for email in batch:
                eid = email.get("id")
                # Already analyzed or skipped
                if eid in analyzed_ids:
                    continue

                # Hybrid pre-filter: rule-based tags + Sprint 2 auto-replies + noreply
                if eid in skip_ids:
                    self._mark_skipped(eid, mailbox_id, email.get("client_id"), "rule_based_or_auto_reply")
                    analyzed_ids.add(eid)  # Don't re-process
                    skipped_count += 1
                    continue

                # Fallback: local pattern detection for untagged emails
                if is_automated_email(email):
                    self._mark_skipped(eid, mailbox_id, email.get("client_id"), "automated_pattern")
                    analyzed_ids.add(eid)
                    skipped_count += 1
                    continue

                # Skip forward-only emails (no commentary added)
                if is_forward_only_email(email):
                    self._mark_skipped(eid, mailbox_id, email.get("client_id"), "forward_only")
                    analyzed_ids.add(eid)
                    forward_skipped += 1
                    continue

                # Skip trivial emails — body too short for meaningful analysis
                body = (email.get("body_text") or "").strip()
                if len(body) < 50:
                    self._mark_skipped(eid, mailbox_id, email.get("client_id"), "trivial_body")
                    analyzed_ids.add(eid)
                    skipped_count += 1
                    continue

                all_emails.append(email)
                if len(all_emails) >= limit:
                    break

        total_skipped = skipped_count + forward_skipped
        if total_skipped > 0:
            logger.info(
                f"Pre-filtered {total_skipped} emails "
                f"({skipped_count} automated/auto-reply, {forward_skipped} forward-only) "
                f"— saved ~${total_skipped * 0.001:.3f}"
            )

        return all_emails

    def _mark_skipped(
        self,
        email_id: str,
        mailbox_id: str,
        client_id: Optional[str],
        reason: str,
    ):
        """Mark an email as skipped (pre-filtered, no AI cost)."""
        try:
            self._execute_with_retry(
                self.client.table("ai_email_intelligence")
                .upsert({
                    "email_id": email_id,
                    "mailbox_id": mailbox_id,
                    "client_id": client_id,
                    "processing_status": "skipped",
                    "error_message": f"pre_filter: {reason}",
                    "prompt_version": PROMPT_VERSION,
                }, on_conflict="email_id")
            )
        except Exception as e:
            logger.warning(f"Failed to mark email {email_id} as skipped: {e}")

    # ------------------------------------------------------------------
    # Enrich emails with Sprint 2 data (company, role)
    # ------------------------------------------------------------------
    def _enrich_with_sprint2_data(self, emails: List[dict]) -> None:
        """
        Enrich email dicts with Sprint 2 contact/company data in-place.
        Adds: _contact_job_title, _contact_seniority, _contact_functional_role, _company_name
        This context helps AI classify more accurately without guessing.
        """
        # Collect unique contact/company IDs
        contact_ids = list(set(
            e["customer_contact_id"] for e in emails
            if e.get("customer_contact_id")
        ))
        company_ids = list(set(
            e["customer_company_id"] for e in emails
            if e.get("customer_company_id")
        ))

        contact_lookup = {}
        company_lookup = {}

        # Fetch contact data (job_title, seniority, functional_role)
        for i in range(0, len(contact_ids), 500):
            chunk = contact_ids[i:i + 500]
            try:
                resp = self._execute_with_retry(
                    self.client.table("customer_contacts")
                    .select("id,job_title,seniority_level,functional_role")
                    .in_("id", chunk)
                )
                for c in (resp.data or []):
                    contact_lookup[c["id"]] = c
            except Exception as e:
                logger.warning(f"Could not fetch contact enrichment data: {e}")

        # Fetch company names
        for i in range(0, len(company_ids), 500):
            chunk = company_ids[i:i + 500]
            try:
                resp = self._execute_with_retry(
                    self.client.table("customer_companies")
                    .select("id,company_name")
                    .in_("id", chunk)
                )
                for c in (resp.data or []):
                    company_lookup[c["id"]] = c
            except Exception as e:
                logger.warning(f"Could not fetch company enrichment data: {e}")

        # Enrich emails in-place
        for email in emails:
            contact = contact_lookup.get(email.get("customer_contact_id"), {})
            company = company_lookup.get(email.get("customer_company_id"), {})
            email["_contact_job_title"] = contact.get("job_title") or ""
            email["_contact_seniority"] = contact.get("seniority_level") or ""
            email["_contact_functional_role"] = contact.get("functional_role") or ""
            email["_company_name"] = company.get("company_name") or ""

    # ------------------------------------------------------------------
    # Enrich emails with rule-based tags (from EmailTagger)
    # ------------------------------------------------------------------
    def _enrich_with_rule_based_tags(self, emails: List[dict]) -> None:
        """
        Enrich email dicts with rule-based tags from email_categories table.
        Adds: _rule_tags, _rule_priority, _rule_sender_type
        These provide free, deterministic hints to the AI prompt.
        """
        email_ids = [e["id"] for e in emails]
        tag_lookup: Dict[str, List[str]] = {}

        for i in range(0, len(email_ids), 500):
            chunk = email_ids[i:i + 500]
            try:
                resp = self._execute_with_retry(
                    self.client.table("email_categories")
                    .select("email_id,category")
                    .in_("email_id", chunk)
                )
                for row in (resp.data or []):
                    eid = row.get("email_id")
                    cat = row.get("category", "")
                    if eid:
                        tag_lookup.setdefault(eid, []).append(cat)
            except Exception as e:
                logger.warning(f"Could not fetch rule-based tags: {e}")

        for email in emails:
            tags = tag_lookup.get(email["id"], [])
            priority = None
            sender_type = None
            visible_tags = []
            for tag in tags:
                if tag.startswith("_meta_priority_"):
                    priority = tag.replace("_meta_priority_", "")
                elif tag.startswith("_meta_sender_"):
                    sender_type = tag.replace("_meta_sender_", "")
                elif not tag.startswith("_meta_"):
                    visible_tags.append(tag)
            email["_rule_tags"] = visible_tags
            email["_rule_priority"] = priority
            email["_rule_sender_type"] = sender_type

    # ------------------------------------------------------------------
    # Format emails for the prompt
    # ------------------------------------------------------------------
    def _format_emails_for_prompt(self, emails: List[dict]) -> str:
        """
        Format a batch of emails into the JSON structure for the prompt.
        Includes Sprint 2 enrichment data (company, role) for better AI context.
        """
        formatted = []
        for email in emails:
            body = sanitize_email_body(email.get("body_text") or "")
            entry = {
                "email_id": email["id"],
                "subject": email.get("subject") or "(no subject)",
                "sender": email.get("sender_email") or "unknown",
                "sender_name": email.get("sender_name") or "",
                "direction": email.get("direction") or "unknown",
                "is_reply": email.get("is_reply", False),
                "body": body,
            }
            # Add Sprint 2 context (helps AI classify without guessing)
            company = email.get("_company_name", "")
            job_title = email.get("_contact_job_title", "")
            seniority = email.get("_contact_seniority", "")
            func_role = email.get("_contact_functional_role", "")
            if company or job_title or seniority or func_role:
                context_parts = []
                if company:
                    context_parts.append(f"company: {company}")
                if job_title:
                    context_parts.append(f"title: {job_title}")
                if seniority:
                    context_parts.append(f"seniority: {seniority}")
                if func_role:
                    context_parts.append(f"role: {func_role}")
                entry["sender_context"] = ", ".join(context_parts)

            # Add rule-based pre-classification hints (from EmailTagger)
            rule_tags = email.get("_rule_tags", [])
            rule_sender_type = email.get("_rule_sender_type")
            rule_priority = email.get("_rule_priority")
            if rule_tags or rule_sender_type:
                pre_class = {}
                if rule_tags:
                    pre_class["tags"] = rule_tags
                if rule_sender_type:
                    pre_class["sender_type"] = rule_sender_type
                if rule_priority:
                    pre_class["priority_score"] = rule_priority
                entry["pre_classification"] = pre_class

            formatted.append(entry)
        return json.dumps(formatted, indent=2)

    # ------------------------------------------------------------------
    # Parse + validate AI response
    # ------------------------------------------------------------------
    def _parse_and_validate(
        self,
        ai_response: AIResponse,
        expected_email_ids: List[str],
    ) -> tuple[List[EmailClassificationResult], List[dict]]:
        """
        Parse AI response JSON, validate each item with Pydantic.

        Returns:
            (valid_results, failed_items)
            where failed_items = [{"email_id": ..., "error": ...}]
        """
        valid = []
        failed = []

        try:
            cleaned = clean_llm_output(ai_response.content)
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse AI response as JSON: {e}")
            # Try to repair truncated JSON (common when max_tokens cuts off response)
            parsed = repair_truncated_json(cleaned)
            if parsed is None:
                logger.error(f"JSON repair also failed, entire batch lost")
                for eid in expected_email_ids:
                    failed.append({"email_id": eid, "error": f"json_parse: {str(e)[:200]}"})
                return valid, failed

        if not isinstance(parsed, list):
            parsed = [parsed]

        # Build lookup by email_id
        result_lookup = {}
        for item in parsed:
            if isinstance(item, dict) and "email_id" in item:
                result_lookup[item["email_id"]] = item

        # Validate each expected email
        for eid in expected_email_ids:
            item = result_lookup.get(eid)
            if item is None:
                failed.append({"email_id": eid, "error": "missing_from_response"})
                continue
            try:
                validated = EmailClassificationResult.model_validate(item)
                valid.append(validated)
            except Exception as e:
                failed.append({"email_id": eid, "error": f"validation: {str(e)[:300]}"})

        return valid, failed

    # ------------------------------------------------------------------
    # Retry single failed item
    # ------------------------------------------------------------------
    def _retry_single_email(
        self,
        email: dict,
        mailbox_id: str,
    ) -> Optional[EmailClassificationResult]:
        """Retry a single email that failed validation. One retry only."""
        emails_json = self._format_emails_for_prompt([email])
        user_message = USER_PROMPT_TEMPLATE.format(emails_json=emails_json)

        ai_resp = self.ai_client.call_haiku(SYSTEM_PROMPT, user_message, max_tokens=2048)
        if ai_resp is None:
            return None

        valid, _ = self._parse_and_validate(ai_resp, [email["id"]])
        return valid[0] if valid else None

    # ------------------------------------------------------------------
    # Mark items as processing/failed/completed in DB
    # ------------------------------------------------------------------
    def _mark_processing(self, email_ids: List[str], mailbox_id: str, client_id: Optional[str]):
        """Insert placeholder rows with processing_status='processing'."""
        for eid in email_ids:
            try:
                self._execute_with_retry(
                    self.client.table("ai_email_intelligence")
                    .upsert({
                        "email_id": eid,
                        "mailbox_id": mailbox_id,
                        "client_id": client_id,
                        "processing_status": "processing",
                    }, on_conflict="email_id")
                )
            except Exception as e:
                logger.warning(f"Failed to mark email {eid} as processing: {e}")

    def _save_completed(
        self,
        email_id: str,
        mailbox_id: str,
        client_id: Optional[str],
        row_data: dict,
        ai_response: AIResponse,
    ):
        """Save a successfully analyzed email to ai_email_intelligence."""
        record = {
            "email_id": email_id,
            "mailbox_id": mailbox_id,
            "client_id": client_id,
            **row_data,
            # Processing metadata
            "model_used": ai_response.model,
            "input_tokens": ai_response.input_tokens,
            "output_tokens": ai_response.output_tokens,
            "processing_time_ms": ai_response.processing_time_ms,
            # Idempotent processing
            "processing_status": "completed",
            "processed_at": datetime.utcnow().isoformat(),
            "error_message": None,
            # Version tracking
            "prompt_version": PROMPT_VERSION,
            "scoring_version": SCORING_VERSION,
            # Raw AI output (debugging + compliance)
            "raw_ai_response": ai_response.raw_response,
        }

        try:
            self._execute_with_retry(
                self.client.table("ai_email_intelligence")
                .upsert(record, on_conflict="email_id")
            )
        except Exception as e:
            logger.error(f"Failed to save intelligence for email {email_id}: {e}")

    def _save_failed(
        self,
        email_id: str,
        mailbox_id: str,
        client_id: Optional[str],
        error_message: str,
        ai_response: Optional[AIResponse] = None,
    ):
        """Mark an email as failed in ai_email_intelligence."""
        record = {
            "email_id": email_id,
            "mailbox_id": mailbox_id,
            "client_id": client_id,
            "processing_status": "failed",
            "error_message": error_message[:500],
            "prompt_version": PROMPT_VERSION,
        }
        if ai_response:
            record["raw_ai_response"] = ai_response.raw_response
            record["model_used"] = ai_response.model

        try:
            self._execute_with_retry(
                self.client.table("ai_email_intelligence")
                .upsert(record, on_conflict="email_id")
            )
        except Exception as e:
            logger.error(f"Failed to save failure record for email {email_id}: {e}")

    # ------------------------------------------------------------------
    # Core batch analysis
    # ------------------------------------------------------------------
    def analyze_batch(
        self,
        mailbox_id: str,
        client_id: Optional[str],
        emails: List[dict],
    ) -> dict:
        """
        Analyze a batch of emails (up to BATCH_SIZE) with one Claude Haiku call.

        Returns:
            {"analyzed": int, "failed": int, "skipped": int}
        """
        if not emails:
            return {"analyzed": 0, "failed": 0, "skipped": 0}

        if not self.ai_client.is_available:
            # Graceful degradation — mark all as failed
            for email in emails:
                self._save_failed(email["id"], mailbox_id, client_id, "api_unavailable")
            usage_tracker = get_usage_tracker()
            if usage_tracker:
                usage_tracker.log_usage(
                    operation="email_intelligence",
                    model="none",
                    input_tokens=0,
                    output_tokens=0,
                    mailbox_id=mailbox_id,
                    client_id=client_id,
                    batch_size=len(emails),
                    success=False,
                    error_type="api_unavailable",
                    prompt_version=PROMPT_VERSION,
                )
            return {"analyzed": 0, "failed": len(emails), "skipped": 0}

        email_ids = [e["id"] for e in emails]

        # Mark as processing
        self._mark_processing(email_ids, mailbox_id, client_id)

        # Enrich with Sprint 2 data (company name, contact role) for better AI context
        self._enrich_with_sprint2_data(emails)

        # Enrich with rule-based tags (from EmailTagger) for pre-classification hints
        self._enrich_with_rule_based_tags(emails)

        # Build prompt
        emails_json = self._format_emails_for_prompt(emails)
        user_message = USER_PROMPT_TEMPLATE.format(emails_json=emails_json)

        # Call Claude Haiku — scale max_tokens with batch size (~500 tokens per email)
        max_tokens = max(4096, len(emails) * 500)
        ai_response = self.ai_client.call_haiku(SYSTEM_PROMPT, user_message, max_tokens=max_tokens)

        if ai_response is None:
            # API failure — mark all as failed
            for eid in email_ids:
                self._save_failed(eid, mailbox_id, client_id, "api_call_failed")
            usage_tracker = get_usage_tracker()
            if usage_tracker:
                usage_tracker.log_usage(
                    operation="email_intelligence",
                    model="none",
                    input_tokens=0,
                    output_tokens=0,
                    mailbox_id=mailbox_id,
                    client_id=client_id,
                    batch_size=len(emails),
                    success=False,
                    error_type="api_timeout",
                    prompt_version=PROMPT_VERSION,
                )
            return {"analyzed": 0, "failed": len(emails), "skipped": 0}

        # Parse + validate
        valid_results, failed_items = self._parse_and_validate(ai_response, email_ids)

        # Retry failed items (one retry per item)
        email_lookup = {e["id"]: e for e in emails}
        retry_successes = []
        final_failures = []

        for fail in failed_items:
            eid = fail["email_id"]
            email = email_lookup.get(eid)
            if email and "json_parse" not in fail["error"]:
                # Retry single item
                logger.info(f"Retrying single email {eid}: {fail['error'][:100]}")
                retried = self._retry_single_email(email, mailbox_id)
                if retried:
                    retry_successes.append(retried)
                    continue
            final_failures.append(fail)

        # Save valid results
        analyzed_count = 0
        all_valid = valid_results + retry_successes
        for result in all_valid:
            row_data = post_process_classification(result)
            self._save_completed(result.email_id, mailbox_id, client_id, row_data, ai_response)
            analyzed_count += 1

        # Save failures
        for fail in final_failures:
            error_type = "json_parse" if "json_parse" in fail["error"] else "validation"
            self._save_failed(
                fail["email_id"], mailbox_id, client_id,
                fail["error"], ai_response
            )

        # Log usage
        usage_tracker = get_usage_tracker()
        if usage_tracker:
            usage_tracker.log_usage(
                operation="email_intelligence",
                model=ai_response.model,
                input_tokens=ai_response.input_tokens,
                output_tokens=ai_response.output_tokens,
                mailbox_id=mailbox_id,
                client_id=client_id,
                processing_time_ms=ai_response.processing_time_ms,
                batch_size=len(emails),
                success=len(final_failures) == 0,
                error_type="validation" if final_failures else None,
                retry_count=len(retry_successes),
                prompt_version=PROMPT_VERSION,
            )

        logger.info(
            f"Batch complete: {analyzed_count} analyzed, "
            f"{len(final_failures)} failed, "
            f"{len(retry_successes)} recovered via retry"
        )

        return {
            "analyzed": analyzed_count,
            "failed": len(final_failures),
            "skipped": 0,
        }

    # ------------------------------------------------------------------
    # Analyze all unanalyzed emails for a mailbox
    # ------------------------------------------------------------------
    def analyze_all_unanalyzed(
        self,
        mailbox_id: str,
        client_id: Optional[str] = None,
        max_emails: int = 5000,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> dict:
        """
        Loop through all unanalyzed emails in batches.

        Args:
            mailbox_id: Target mailbox UUID
            client_id: Optional client UUID for scoping
            max_emails: Max emails to process
            date_from: ISO date string — only analyze emails after this date (default: 7 days ago)
            date_to: ISO date string — only analyze emails before this date (default: now)

        Circuit breaker: stops after 3 consecutive batches with 0 successes
        (e.g., API key invalid, no credits, service down).

        Returns:
            {"total_analyzed": int, "total_failed": int, "batches": int, "date_range": dict}
        """
        # Apply default date range: last 7 days if not specified
        if not date_from:
            date_from = (datetime.utcnow() - timedelta(days=DEFAULT_LOOKBACK_DAYS)).isoformat()
        if not date_to:
            date_to = datetime.utcnow().isoformat()

        logger.info(f"Analyzing emails from {date_from} to {date_to} for mailbox {mailbox_id}")

        total_analyzed = 0
        total_failed = 0
        batch_count = 0
        consecutive_failures = 0
        MAX_CONSECUTIVE_FAILURES = 3

        while total_analyzed + total_failed < max_emails:
            # Fetch next batch of unanalyzed emails
            remaining = max_emails - total_analyzed - total_failed
            fetch_limit = min(BATCH_SIZE, remaining)
            emails = self._get_unanalyzed_emails(
                mailbox_id, limit=fetch_limit,
                date_from=date_from, date_to=date_to,
            )

            if not emails:
                logger.info("No more unanalyzed emails found")
                break

            result = self.analyze_batch(mailbox_id, client_id, emails)
            total_analyzed += result["analyzed"]
            total_failed += result["failed"]
            batch_count += 1

            # Circuit breaker: stop if API is consistently failing
            if result["analyzed"] == 0 and result["failed"] > 0:
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    logger.error(
                        f"Circuit breaker triggered: {consecutive_failures} consecutive "
                        f"batches with 0 successes. Stopping to avoid wasting resources. "
                        f"Check your ANTHROPIC_API_KEY and account credits."
                    )
                    break
            else:
                consecutive_failures = 0

            logger.info(
                f"Progress: {total_analyzed} analyzed, {total_failed} failed "
                f"after {batch_count} batches"
            )

        return {
            "total_analyzed": total_analyzed,
            "total_failed": total_failed,
            "batches": batch_count,
            "date_range": {"from": date_from, "to": date_to},
        }

    # ------------------------------------------------------------------
    # Helper: get email IDs within a sent_date range
    # ------------------------------------------------------------------
    def _get_email_ids_in_date_range(
        self, mailbox_id: str, date_from: Optional[str], date_to: Optional[str]
    ) -> Optional[list]:
        """Get email IDs from the emails table within a sent_date range.

        Returns None if no date filtering needed, empty list if no emails match.
        """
        if not date_from and not date_to:
            return None

        query = self.client.table("emails").select("id").eq("mailbox_id", mailbox_id)
        if date_from:
            query = query.gte("sent_date", date_from)
        if date_to:
            query = query.lte("sent_date", date_to)

        all_ids = []
        offset = 0
        while True:
            resp = self._execute_with_retry(query.range(offset, offset + 499))
            batch = resp.data or []
            all_ids.extend(e["id"] for e in batch)
            if len(batch) == 0:
                break
            offset += len(batch)

        return all_ids

    # ------------------------------------------------------------------
    # Query intelligence results
    # ------------------------------------------------------------------
    def get_intelligence(
        self,
        mailbox_id: str,
        page: int = 1,
        page_size: int = 25,
        intent: Optional[str] = None,
        urgency: Optional[str] = None,
        sentiment: Optional[str] = None,
        primary_bucket: Optional[str] = None,
        action_type: Optional[str] = None,
        business_signal: Optional[str] = None,
        has_budget_signal: Optional[bool] = None,
        has_buying_signal: Optional[bool] = None,
        has_competitor_mention: Optional[bool] = None,
        min_confidence: Optional[float] = None,
        processing_status: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> dict:
        """
        Query analyzed emails with filters. Joins with emails table for display fields.

        Returns: {"items": [...], "total": int, "page": int, "page_size": int}
        """
        # Date filtering: get email IDs in date range (uses emails.sent_date)
        valid_email_ids = self._get_email_ids_in_date_range(mailbox_id, date_from, date_to)
        if valid_email_ids is not None and not valid_email_ids:
            return {"items": [], "page": page, "page_size": page_size}

        # Build query on ai_email_intelligence
        query = (
            self.client.table("ai_email_intelligence")
            .select("*")
            .eq("mailbox_id", mailbox_id)
            .order("created_at", desc=True)
        )

        # Apply date filter via email IDs
        if valid_email_ids is not None:
            query = query.in_("email_id", valid_email_ids[:500])

        # Apply filters
        if intent:
            query = query.eq("intent", intent)
        if urgency:
            query = query.eq("urgency", urgency)
        if sentiment:
            query = query.eq("sentiment", sentiment)
        if primary_bucket:
            query = query.eq("primary_bucket", primary_bucket)
        if action_type:
            query = query.eq("action_type", action_type)
        if business_signal:
            query = query.eq("business_signal", business_signal)
        if processing_status:
            query = query.eq("processing_status", processing_status)
        else:
            query = query.eq("processing_status", "completed")

        # Boolean filters — use lowercase string 'true' for Supabase
        if has_budget_signal is True:
            query = query.eq("has_budget_signal", 'true')
        if has_buying_signal is True:
            query = query.eq("has_buying_signal", 'true')
        if has_competitor_mention is True:
            query = query.eq("has_competitor_mention", 'true')

        # Confidence filter — cast to int for INTEGER column
        if min_confidence is not None:
            # confidence is DECIMAL(3,2), use gte directly
            query = query.gte("confidence", min_confidence)

        # Paginate
        offset = (page - 1) * page_size
        resp = self._execute_with_retry(
            query.range(offset, offset + page_size - 1)
        )
        items = resp.data or []

        # Enrich with email data (subject, sender) for display
        email_ids = [item["email_id"] for item in items if item.get("email_id")]
        email_lookup = {}
        if email_ids:
            # Fetch in chunks of 500 (Supabase .in_() limit)
            for i in range(0, len(email_ids), 500):
                chunk = email_ids[i:i + 500]
                email_resp = self._execute_with_retry(
                    self.client.table("emails")
                    .select("id,subject,sender_email,sender_name,sent_date,direction")
                    .in_("id", chunk)
                )
                for e in (email_resp.data or []):
                    email_lookup[e["id"]] = e

        # Merge email display fields + sanitize nulls for Pydantic
        # Supabase returns null for DB NULLs, but Pydantic str fields reject None
        _STR_DEFAULTS = [
            "summary", "suggested_action", "justification",
            "email_subject", "email_sender", "email_sender_name", "email_direction",
        ]
        _LIST_DEFAULTS = [
            "key_topics", "competitors_mentioned", "products_mentioned",
            "buying_signals", "people_mentioned", "dates_mentioned",
            "action_items_extracted", "action_buckets",
        ]

        for item in items:
            email_data = email_lookup.get(item.get("email_id"), {})
            item["email_subject"] = email_data.get("subject") or ""
            item["email_sender"] = email_data.get("sender_email") or ""
            item["email_sender_name"] = email_data.get("sender_name") or ""
            item["email_date"] = email_data.get("sent_date") or ""
            item["email_direction"] = email_data.get("direction") or ""

            # Coerce None → "" for str fields, None → [] for list fields
            for key in _STR_DEFAULTS:
                if item.get(key) is None:
                    item[key] = ""
            for key in _LIST_DEFAULTS:
                if item.get(key) is None:
                    item[key] = []

        return {
            "items": items,
            "page": page,
            "page_size": page_size,
        }

    # ------------------------------------------------------------------
    # Re-analysis: find old-version emails and reset for reprocessing
    # ------------------------------------------------------------------
    def get_reanalysis_candidates(
        self,
        mailbox_id: str,
        target_prompt_version: str,
        include_failed: bool = False,
        limit: int = 500,
    ) -> list:
        """
        Find emails analyzed with an older prompt version.

        Args:
            mailbox_id: Mailbox to search in
            target_prompt_version: Prompt version to look for (e.g. "v1.0")
            include_failed: Also include failed rows for retry
            limit: Max number of candidates to return

        Returns:
            List of dicts with {id, email_id, prompt_version, processing_status}
        """
        candidates = []
        offset = 0
        PAGE_SIZE = 500

        while len(candidates) < limit:
            query = (
                self.client.table("ai_email_intelligence")
                .select("id,email_id,prompt_version,processing_status")
                .eq("mailbox_id", mailbox_id)
                .eq("prompt_version", target_prompt_version)
                .range(offset, offset + PAGE_SIZE - 1)
            )
            resp = self._execute_with_retry(query)
            batch = resp.data or []

            for row in batch:
                status = row.get("processing_status")
                if status == "completed":
                    candidates.append(row)
                elif include_failed and status == "failed":
                    candidates.append(row)

                if len(candidates) >= limit:
                    break

            if len(batch) == 0:
                break
            offset += len(batch)

        logger.info(
            f"Found {len(candidates)} reanalysis candidates "
            f"(prompt_version={target_prompt_version}, include_failed={include_failed})"
        )
        return candidates

    def reset_for_reanalysis(self, email_ids: list, mailbox_id: str) -> int:
        """
        Reset processing_status to 'pending' for given email_ids,
        so analyze_all_unanalyzed() picks them up naturally.

        Returns: number of rows reset
        """
        if not email_ids:
            return 0

        reset_count = 0

        # Process in chunks of 100 (Supabase batch update limit)
        for i in range(0, len(email_ids), 100):
            chunk = email_ids[i:i + 100]
            try:
                resp = self._execute_with_retry(
                    self.client.table("ai_email_intelligence")
                    .update({
                        "processing_status": "pending",
                        "processed_at": None,
                        "error_message": None,
                    })
                    .eq("mailbox_id", mailbox_id)
                    .in_("email_id", chunk)
                )
                reset_count += len(resp.data or [])
            except Exception as e:
                logger.error(f"Failed to reset chunk {i}: {e}")

        logger.info(f"Reset {reset_count}/{len(email_ids)} emails for reanalysis")
        return reset_count

    # ------------------------------------------------------------------
    # Stats breakdown
    # ------------------------------------------------------------------
    def get_stats(self, mailbox_id: str) -> dict:
        """
        Get intelligence stats for a mailbox.

        Returns counts by intent, urgency, sentiment, processing_status, bucket.
        """
        # Fetch all completed intelligence rows (just the fields we need)
        all_rows = []
        offset = 0
        PAGE_SIZE = 500
        while True:
            resp = self._execute_with_retry(
                self.client.table("ai_email_intelligence")
                .select("intent,urgency,sentiment,processing_status,primary_bucket,business_signal,confidence")
                .eq("mailbox_id", mailbox_id)
                .range(offset, offset + PAGE_SIZE - 1)
            )
            batch = resp.data or []
            all_rows.extend(batch)
            if len(batch) == 0:
                break
            offset += len(batch)

        # Compute distributions in Python
        stats = {
            "total": len(all_rows),
            "by_status": {},
            "by_intent": {},
            "by_urgency": {},
            "by_sentiment": {},
            "by_bucket": {},
            "by_business_signal": {},
            "avg_confidence": 0.0,
        }

        confidence_sum = 0.0
        confidence_count = 0

        for row in all_rows:
            # Status
            status = row.get("processing_status", "unknown")
            stats["by_status"][status] = stats["by_status"].get(status, 0) + 1

            # Only count completed for other distributions
            if status != "completed":
                continue

            intent = row.get("intent", "other")
            stats["by_intent"][intent] = stats["by_intent"].get(intent, 0) + 1

            urgency = row.get("urgency", "none")
            stats["by_urgency"][urgency] = stats["by_urgency"].get(urgency, 0) + 1

            sentiment = row.get("sentiment", "neutral")
            stats["by_sentiment"][sentiment] = stats["by_sentiment"].get(sentiment, 0) + 1

            bucket = row.get("primary_bucket")
            if bucket:
                stats["by_bucket"][bucket] = stats["by_bucket"].get(bucket, 0) + 1

            signal = row.get("business_signal")
            if signal:
                stats["by_business_signal"][signal] = stats["by_business_signal"].get(signal, 0) + 1

            conf = row.get("confidence")
            if conf is not None:
                confidence_sum += float(conf)
                confidence_count += 1

        if confidence_count > 0:
            stats["avg_confidence"] = round(confidence_sum / confidence_count, 3)

        return stats


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_analyzer: Optional[AIEmailAnalyzer] = None


def init_email_analyzer(supabase_client) -> AIEmailAnalyzer:
    """Initialize the global email analyzer with a Supabase client."""
    global _analyzer
    _analyzer = AIEmailAnalyzer(supabase_client)
    return _analyzer


def get_email_analyzer() -> Optional[AIEmailAnalyzer]:
    """Get the initialized email analyzer instance."""
    return _analyzer
