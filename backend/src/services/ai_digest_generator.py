"""
AI Digest Generator — Daily Intelligence Briefing (Session 5)

Uses Claude Sonnet to synthesize a daily digest from:
- Bucket summary (computed in Python, fed as context)
- Top business signal emails
- High priority / urgent emails
- Thread status (open, overdue counts)

Cache-first: checks ai_daily_digests before generating.
Stores raw_ai_response for debugging + compliance.
"""

import json
import time
import logging
from typing import Optional, List
from datetime import datetime, date, timedelta

from pydantic import BaseModel

from .ai_client import get_ai_client, AIResponse
from .ai_action_bucket_engine import get_bucket_engine
from .ai_usage_tracker import get_usage_tracker
from .ai_email_analyzer import clean_llm_output

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Versioning
# ---------------------------------------------------------------------------
DIGEST_PROMPT_VERSION = "v1.0"

# ---------------------------------------------------------------------------
# Prompts (Sonnet — higher quality for synthesis)
# ---------------------------------------------------------------------------
DIGEST_SYSTEM_PROMPT = """You are an executive assistant generating a concise daily email intelligence briefing.

Be action-oriented, prioritized, and factual.
Do not exaggerate.
Do not invent missing data.
Return STRICT JSON only.
No markdown. No explanation. No extra keys."""

DIGEST_USER_TEMPLATE = """Generate a daily email intelligence digest.

CONTEXT:
- Emails received: {in_count}
- Emails sent: {out_count}
- Open threads: {open_threads}
- Overdue threads: {overdue_threads}
- Bucket summary: {bucket_summary_json}

BUSINESS SIGNAL EMAILS:
{top_signal_emails_json}

RECENT HIGH PRIORITY EMAILS:
{priority_emails_json}

Return JSON with this schema:

{{
  "summary": "2-3 concise sentences prioritizing the most critical buckets first",
  "action_items": [
    {{"email_id": "string", "priority": 1, "bucket": "string or null",
     "action": "short action sentence", "contact_name": "string or null"}}
  ],
  "highlights": [
    {{"label": "short label", "detail": "short factual description"}}
  ]
}}

Rules:
- Prioritize churn_risk and buying_signal first.
- Do not exceed 3 sentences in summary.
- Do not repeat raw email text.
- Do not include markdown.
- Return JSON only."""


# ---------------------------------------------------------------------------
# Pydantic validation for digest response
# ---------------------------------------------------------------------------
class DigestActionItem(BaseModel):
    email_id: Optional[str] = None
    priority: int = 3
    bucket: Optional[str] = None
    action: str = ""
    contact_name: Optional[str] = None


class DigestHighlight(BaseModel):
    label: str = ""
    detail: str = ""


class DigestResult(BaseModel):
    summary: str = ""
    action_items: list[DigestActionItem] = []
    highlights: list[DigestHighlight] = []


# ---------------------------------------------------------------------------
# Main generator class
# ---------------------------------------------------------------------------
class AIDigestGenerator:
    """Generates and caches daily intelligence digests using Claude Sonnet."""

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
    # Cache-first retrieval
    # ------------------------------------------------------------------
    def get_digest(self, mailbox_id: str, digest_date: date) -> Optional[dict]:
        """Get a cached digest for a specific date. Returns None if not found."""
        resp = self._execute_with_retry(
            self.client.table("ai_daily_digests")
            .select("*")
            .eq("mailbox_id", mailbox_id)
            .eq("digest_date", digest_date.isoformat())
            .range(0, 0)
        )
        data = resp.data or []
        return data[0] if data else None

    def get_digest_or_generate(
        self,
        mailbox_id: str,
        client_id: Optional[str] = None,
        digest_date: Optional[date] = None,
    ) -> Optional[dict]:
        """Get cached digest or generate a new one."""
        target_date = digest_date or date.today()

        # Check cache first
        cached = self.get_digest(mailbox_id, target_date)
        if cached:
            return cached

        # Generate new
        return self.generate_digest(mailbox_id, client_id, target_date)

    # ------------------------------------------------------------------
    # Digest history
    # ------------------------------------------------------------------
    def get_digest_history(
        self,
        mailbox_id: str,
        limit: int = 30,
    ) -> list[dict]:
        """Get past digests, newest first."""
        resp = self._execute_with_retry(
            self.client.table("ai_daily_digests")
            .select("id,mailbox_id,digest_date,summary,emails_analyzed,"
                    "bucket_summary,model_used,created_at")
            .eq("mailbox_id", mailbox_id)
            .order("digest_date", desc=True)
            .range(0, limit - 1)
        )
        return resp.data or []

    # ------------------------------------------------------------------
    # Generate digest
    # ------------------------------------------------------------------
    def generate_digest(
        self,
        mailbox_id: str,
        client_id: Optional[str] = None,
        digest_date: Optional[date] = None,
    ) -> Optional[dict]:
        """
        Generate a daily digest using Claude Sonnet.

        Gathers context from:
        1. Email counts (inbound/outbound for the date)
        2. Thread status (open/overdue counts)
        3. Bucket summary (from bucket engine)
        4. Top signal emails
        5. High priority/urgent emails
        """
        target_date = digest_date or date.today()

        if not self.ai_client.is_available:
            logger.error("AI client unavailable — cannot generate digest")
            return None

        # --- Gather context ---
        context = self._gather_context(mailbox_id, client_id, target_date)

        # Build user message
        user_message = DIGEST_USER_TEMPLATE.format(
            in_count=context["in_count"],
            out_count=context["out_count"],
            open_threads=context["open_threads"],
            overdue_threads=context["overdue_threads"],
            bucket_summary_json=json.dumps(context["bucket_summary"]),
            top_signal_emails_json=json.dumps(context["top_signal_emails"], indent=2),
            priority_emails_json=json.dumps(context["priority_emails"], indent=2),
        )

        # Call Claude Sonnet
        ai_response = self.ai_client.call_sonnet(
            DIGEST_SYSTEM_PROMPT, user_message, max_tokens=2048
        )

        if ai_response is None:
            logger.error("Sonnet call failed for digest generation")
            self._log_usage(mailbox_id, client_id, None, success=False, error_type="api_timeout")
            return None

        # Parse + validate
        digest_data = self._parse_digest_response(ai_response)
        if digest_data is None:
            self._log_usage(mailbox_id, client_id, ai_response, success=False, error_type="json_parse")
            return None

        # Save to database
        record = self._save_digest(
            mailbox_id, client_id, target_date, digest_data,
            context, ai_response,
        )

        # Log usage
        self._log_usage(mailbox_id, client_id, ai_response, success=True)

        return record

    # ------------------------------------------------------------------
    # Context gathering (all Python-side, $0 cost)
    # ------------------------------------------------------------------
    def _gather_context(self, mailbox_id: str, client_id: Optional[str], target_date: date) -> dict:
        """Gather all context needed for digest generation.

        Uses strict date filtering — only considers emails/intelligence from the target date.
        """
        date_start = datetime.combine(target_date, datetime.min.time()).isoformat()
        date_end = datetime.combine(target_date, datetime.max.time()).isoformat()

        # Email counts for the day
        in_count = self._count_emails(mailbox_id, date_start, date_end, direction="inbound")
        out_count = self._count_emails(mailbox_id, date_start, date_end, direction="outbound")

        # Thread counts
        open_threads, overdue_threads = self._count_threads(mailbox_id)

        # Bucket summary from engine
        bucket_summary = {}
        bucket_engine = get_bucket_engine()
        if bucket_engine:
            bucket_summary = bucket_engine.get_bucket_summary(mailbox_id, client_id)

        # Top signal emails — filtered by target date (not all-time)
        top_signal_emails = self._get_top_signal_emails(mailbox_id, date_start, date_end, limit=10)

        # High priority/urgent emails — filtered by target date
        priority_emails = self._get_priority_emails(mailbox_id, date_start, date_end, limit=10)

        return {
            "in_count": in_count,
            "out_count": out_count,
            "open_threads": open_threads,
            "overdue_threads": overdue_threads,
            "bucket_summary": bucket_summary,
            "top_signal_emails": top_signal_emails,
            "priority_emails": priority_emails,
        }

    def _count_emails(self, mailbox_id: str, date_start: str, date_end: str, direction: str) -> int:
        """Count emails for a date range and direction."""
        try:
            resp = self._execute_with_retry(
                self.client.table("emails")
                .select("id", count="exact")
                .eq("mailbox_id", mailbox_id)
                .eq("direction", direction)
                .gte("sent_date", date_start)
                .lte("sent_date", date_end)
            )
            return resp.count or 0
        except Exception as e:
            logger.warning(f"Failed to count {direction} emails: {e}")
            return 0

    def _count_threads(self, mailbox_id: str) -> tuple[int, int]:
        """Count open and overdue threads for a mailbox."""
        try:
            # Open threads (not complete, not dropped)
            open_resp = self._execute_with_retry(
                self.client.table("thread_status")
                .select("id", count="exact")
                .eq("mailbox_id", mailbox_id)
                .neq("status", "complete")
                .neq("status", "dropped")
            )
            open_count = open_resp.count or 0

            # Overdue threads
            overdue_resp = self._execute_with_retry(
                self.client.table("thread_status")
                .select("id", count="exact")
                .eq("mailbox_id", mailbox_id)
                .eq("is_overdue", 'true')
            )
            overdue_count = overdue_resp.count or 0

            return open_count, overdue_count
        except Exception as e:
            logger.warning(f"Failed to count threads: {e}")
            return 0, 0

    def _get_top_signal_emails(self, mailbox_id: str, date_start: str, date_end: str, limit: int = 10) -> list[dict]:
        """Get top emails by business_signal_score for context, filtered by date."""
        try:
            resp = self._execute_with_retry(
                self.client.table("ai_email_intelligence")
                .select("email_id,intent,urgency,sentiment,summary,"
                        "suggested_action,primary_bucket,business_signal_score,"
                        "confidence")
                .eq("mailbox_id", mailbox_id)
                .eq("processing_status", "completed")
                .gt("business_signal_score", "0")
                .gte("created_at", date_start)
                .lte("created_at", date_end)
                .order("business_signal_score", desc=True)
                .range(0, limit - 1)
            )
            rows = resp.data or []

            # Enrich with sender name
            email_ids = [r["email_id"] for r in rows if r.get("email_id")]
            sender_lookup = self._get_email_senders(email_ids)

            results = []
            for row in rows:
                sender = sender_lookup.get(row.get("email_id"), {})
                results.append({
                    "email_id": row.get("email_id"),
                    "sender": sender.get("sender_name") or sender.get("sender_email", ""),
                    "subject": sender.get("subject", ""),
                    "intent": row.get("intent"),
                    "urgency": row.get("urgency"),
                    "bucket": row.get("primary_bucket"),
                    "signal_score": row.get("business_signal_score", 0),
                    "summary": row.get("summary", ""),
                })
            return results
        except Exception as e:
            logger.warning(f"Failed to get signal emails: {e}")
            return []

    def _get_priority_emails(self, mailbox_id: str, date_start: str, date_end: str, limit: int = 10) -> list[dict]:
        """Get urgent/critical emails for context, filtered by date."""
        try:
            resp = self._execute_with_retry(
                self.client.table("ai_email_intelligence")
                .select("email_id,intent,urgency,sentiment,summary,"
                        "suggested_action,primary_bucket,confidence")
                .eq("mailbox_id", mailbox_id)
                .eq("processing_status", "completed")
                .in_("urgency", ["critical", "high"])
                .gte("created_at", date_start)
                .lte("created_at", date_end)
                .order("created_at", desc=True)
                .range(0, limit - 1)
            )
            rows = resp.data or []

            email_ids = [r["email_id"] for r in rows if r.get("email_id")]
            sender_lookup = self._get_email_senders(email_ids)

            results = []
            for row in rows:
                sender = sender_lookup.get(row.get("email_id"), {})
                results.append({
                    "email_id": row.get("email_id"),
                    "sender": sender.get("sender_name") or sender.get("sender_email", ""),
                    "subject": sender.get("subject", ""),
                    "intent": row.get("intent"),
                    "urgency": row.get("urgency"),
                    "bucket": row.get("primary_bucket"),
                    "summary": row.get("summary", ""),
                    "action": row.get("suggested_action", ""),
                })
            return results
        except Exception as e:
            logger.warning(f"Failed to get priority emails: {e}")
            return []

    def _get_email_senders(self, email_ids: list[str]) -> dict:
        """Fetch sender info for a list of email IDs."""
        if not email_ids:
            return {}
        lookup = {}
        for i in range(0, len(email_ids), 500):
            chunk = email_ids[i:i + 500]
            try:
                resp = self._execute_with_retry(
                    self.client.table("emails")
                    .select("id,sender_email,sender_name,subject")
                    .in_("id", chunk)
                )
                for e in (resp.data or []):
                    lookup[e["id"]] = e
            except Exception as e:
                logger.warning(f"Failed to fetch email senders: {e}")
        return lookup

    # ------------------------------------------------------------------
    # Parse + validate AI response
    # ------------------------------------------------------------------
    def _parse_digest_response(self, ai_response: AIResponse) -> Optional[DigestResult]:
        """Parse and validate Sonnet response into DigestResult."""
        try:
            cleaned = clean_llm_output(ai_response.content)
            parsed = json.loads(cleaned)
            return DigestResult.model_validate(parsed)
        except json.JSONDecodeError as e:
            logger.error(f"Digest JSON parse failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Digest validation failed: {e}")
            return None

    # ------------------------------------------------------------------
    # Save to database
    # ------------------------------------------------------------------
    def _save_digest(
        self,
        mailbox_id: str,
        client_id: Optional[str],
        digest_date: date,
        digest_data: DigestResult,
        context: dict,
        ai_response: AIResponse,
    ) -> dict:
        """Save generated digest to ai_daily_digests table."""
        record = {
            "mailbox_id": mailbox_id,
            "digest_date": digest_date.isoformat(),
            "summary": digest_data.summary,
            "action_items": [item.model_dump() for item in digest_data.action_items],
            "highlights": [h.model_dump() for h in digest_data.highlights],
            "stats": {
                "in_count": context["in_count"],
                "out_count": context["out_count"],
                "open_threads": context["open_threads"],
                "overdue_threads": context["overdue_threads"],
            },
            "bucket_summary": context["bucket_summary"],
            "emails_analyzed": context["in_count"] + context["out_count"],
            "model_used": ai_response.model,
            "input_tokens": ai_response.input_tokens,
            "output_tokens": ai_response.output_tokens,
            "prompt_version": DIGEST_PROMPT_VERSION,
            "raw_ai_response": ai_response.raw_response,
        }
        if client_id:
            record["client_id"] = client_id

        try:
            resp = self._execute_with_retry(
                self.client.table("ai_daily_digests")
                .upsert(record, on_conflict="mailbox_id,digest_date")
            )
            saved = resp.data[0] if resp.data else record
            logger.info(f"Digest saved for {mailbox_id} on {digest_date}")
            return saved
        except Exception as e:
            logger.error(f"Failed to save digest: {e}")
            return record

    # ------------------------------------------------------------------
    # Usage logging
    # ------------------------------------------------------------------
    def _log_usage(
        self,
        mailbox_id: str,
        client_id: Optional[str],
        ai_response: Optional[AIResponse],
        success: bool,
        error_type: Optional[str] = None,
    ):
        """Log digest generation to usage tracker."""
        usage_tracker = get_usage_tracker()
        if not usage_tracker:
            return
        usage_tracker.log_usage(
            operation="digest",
            model=ai_response.model if ai_response else "none",
            input_tokens=ai_response.input_tokens if ai_response else 0,
            output_tokens=ai_response.output_tokens if ai_response else 0,
            mailbox_id=mailbox_id,
            client_id=client_id,
            processing_time_ms=ai_response.processing_time_ms if ai_response else 0,
            success=success,
            error_type=error_type,
            prompt_version=DIGEST_PROMPT_VERSION,
        )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_digest_generator: Optional[AIDigestGenerator] = None


def init_digest_generator(supabase_client) -> AIDigestGenerator:
    """Initialize the global digest generator."""
    global _digest_generator
    _digest_generator = AIDigestGenerator(supabase_client)
    return _digest_generator


def get_digest_generator() -> Optional[AIDigestGenerator]:
    """Get the initialized digest generator instance."""
    return _digest_generator
