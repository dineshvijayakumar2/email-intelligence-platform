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

from pydantic import BaseModel, model_validator

from .ai_client import get_ai_client, AIResponse
from .ai_action_bucket_engine import get_bucket_engine
from .ai_usage_tracker import get_usage_tracker
from .ai_email_analyzer import clean_llm_output

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Versioning
# ---------------------------------------------------------------------------
DIGEST_PROMPT_VERSION = "v2.0"  # v2: QB business context in digest

# ---------------------------------------------------------------------------
# Prompts (Sonnet — higher quality for synthesis)
# ---------------------------------------------------------------------------
DIGEST_SYSTEM_PROMPT = """You are an executive intelligence analyst generating deep insights from email data.

Your job is to surface NON-OBVIOUS patterns, risks, and opportunities that are NOT visible from basic counts or bucket labels alone. The user already sees bucket counts and email lists in the UI — do NOT restate those numbers.

Focus on:
- Cross-email patterns (e.g. multiple contacts from same company raising issues = systemic problem)
- Timing patterns (e.g. sudden increase in outbound with no replies = engagement drop)
- Relationship dynamics (e.g. a key contact going silent, a new stakeholder appearing)
- Strategic implications (e.g. competitive mentions alongside pricing inquiries)
- Actionable connections between emails that aren't obvious individually

Be factual. Never invent data. Never cite specific counts from the bucket summary — those are already displayed.
Return STRICT JSON only. No markdown. No explanation. No extra keys."""

DIGEST_USER_TEMPLATE = """Generate a {scope} email intelligence digest with DEEP INSIGHTS.

TIME WINDOW: {time_window_label}

STATS (already shown in UI — do NOT repeat these):
- Emails received: {in_count} | Sent: {out_count}
- Open threads: {open_threads} | Overdue: {overdue_threads}
- Bucket counts: {bucket_summary_json}

BUSINESS CONTEXT (from CRM — use to calibrate importance):
{business_context_json}

RELATIONSHIP CONTEXT (90-day lookback — use for trend awareness):
{relationship_context_json}

BUSINESS SIGNAL EMAILS (analyze for cross-cutting patterns):
{top_signal_emails_json}

RECENT HIGH PRIORITY EMAILS (analyze for hidden risks/opportunities):
{priority_emails_json}

Return JSON with this schema:

{{
  "summary": "2-3 sentences of NON-OBVIOUS insights. Do NOT restate bucket counts or email totals. Focus on patterns, risks, relationship shifts, or strategic implications that connect multiple data points.",
  "action_items": [
    {{"email_id": "string", "priority": 1, "bucket": "string or null",
     "action": "short action sentence", "contact_name": "string or null"}}
  ],
  "highlights": [
    {{"label": "short insight label", "detail": "non-obvious pattern or risk explanation"}}
  ]
}}

Rules:
- NEVER cite specific bucket counts (the user already sees "Buying Signal: 3, Churn Risk: 2" etc in the UI).
- Focus summary on PATTERNS and CONNECTIONS across emails, not individual email descriptions.
- Highlights should surface things the user would NOT notice from scanning subject lines alone.
- Action items should reference specific emails with concrete next steps.
- Do not exceed 3 sentences in summary.
- Do not repeat raw email text.
- Return JSON only."""

WEEKLY_DIGEST_SYSTEM_PROMPT = """You are an executive intelligence analyst generating a WEEKLY strategic review from email data for a B2B commercial printing company.

Unlike the daily digest, your job is to identify WEEK-LEVEL TRENDS and STRATEGIC PATTERNS:

Focus on:
- Week-over-week shifts: Is engagement increasing or dropping? Are new industries/verticals appearing?
- Pipeline momentum: Are quotes progressing to jobs? Are there stalled deals that need intervention?
- AM workload distribution: Who handled the most volume? Who has overdue threads piling up?
- Customer behavior patterns: Which companies increased/decreased communication? Any re-engagement or churn signals?
- Opportunity clusters: Multiple inquiries for similar products/services = market trend worth pursuing
- Competitive pressure: Any competitor mentions, price sensitivity, or lost-deal signals this week?

Be specific with company names, AM names, and dollar amounts where available.
Do NOT restate email counts or bucket numbers — the user sees those in the UI.
Return STRICT JSON only. No markdown. No explanation."""

WEEKLY_DIGEST_USER_TEMPLATE = """Generate a WEEKLY strategic intelligence review with trend analysis.

TIME WINDOW: {time_window_label}

STATS (already shown in UI — do NOT repeat these):
- Emails received: {in_count} | Sent: {out_count}
- Open threads: {open_threads} | Overdue: {overdue_threads}
- Bucket counts: {bucket_summary_json}

BUSINESS CONTEXT (from CRM):
{business_context_json}

RELATIONSHIP CONTEXT (90-day lookback — use this to identify trends and compare this week vs recent history):
{relationship_context_json}

BUSINESS SIGNAL EMAILS (this week — analyze for trends, not individual emails):
{top_signal_emails_json}

HIGH PRIORITY EMAILS (this week — look for patterns across the week):
{priority_emails_json}

Return JSON with this schema:

{{
  "summary": "3-5 sentences covering: (1) the dominant theme of the week, (2) pipeline health trend, (3) any emerging risks or opportunities that need action next week. Be specific — name companies and AMs.",
  "action_items": [
    {{"email_id": "string or null", "priority": 1, "bucket": "string or null",
     "action": "specific action for next week", "contact_name": "string or null"}}
  ],
  "highlights": [
    {{"label": "short trend label", "detail": "week-level pattern: what changed, what it means, what to do"}}
  ]
}}

Rules:
- Summary must cover the WHOLE WEEK trend, not describe individual emails.
- Highlights should be week-level patterns (e.g., "3 inquiries for specialty materials" not "Email from X about Y").
- Action items should be prioritized for NEXT WEEK, not retroactive.
- Name specific companies and AMs where relevant.
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
    model_config = {"extra": "allow"}  # Accept extra fields from Gemini

    summary: str = ""
    action_items: list[DigestActionItem] = []
    highlights: list[DigestHighlight] = []

    @model_validator(mode="before")
    @classmethod
    def normalize_keys(cls, data):
        """Gemini often returns different key names. Map them to expected schema."""
        if not isinstance(data, dict):
            return data

        # Map common Gemini key variations to our schema
        # Summary: might be "executive_summary", "overview", "analysis", "insight", etc.
        if not data.get("summary"):
            for alt_key in ["executive_summary", "overview", "analysis", "insight",
                            "daily_summary", "weekly_summary", "digest_summary"]:
                if data.get(alt_key) and isinstance(data[alt_key], str):
                    data["summary"] = data[alt_key]
                    break
            # If still no summary, build one from any string values in the dict
            if not data.get("summary"):
                parts = []
                for k, v in data.items():
                    if isinstance(v, str) and len(v) > 20 and k not in ("summary",):
                        parts.append(v)
                if parts:
                    data["summary"] = " ".join(parts[:3])

        # Action items: might be "actions", "next_steps", "recommendations", "tasks"
        if not data.get("action_items"):
            for alt_key in ["actions", "next_steps", "recommendations", "tasks",
                            "priority_actions", "suggested_actions"]:
                if data.get(alt_key) and isinstance(data[alt_key], list):
                    items = []
                    for item in data[alt_key]:
                        if isinstance(item, dict):
                            items.append(item)
                        elif isinstance(item, str):
                            items.append({"action": item, "priority": 3})
                    data["action_items"] = items
                    break

        # Highlights: might be "key_observations", "insights", "findings", "patterns"
        if not data.get("highlights"):
            for alt_key in ["key_observations", "insights", "findings", "patterns",
                            "key_insights", "observations"]:
                if data.get(alt_key) and isinstance(data[alt_key], list):
                    items = []
                    for item in data[alt_key]:
                        if isinstance(item, dict):
                            label = item.get("label") or item.get("title") or item.get("type") or "Insight"
                            detail = item.get("detail") or item.get("description") or item.get("text") or str(item)
                            items.append({"label": label, "detail": detail})
                        elif isinstance(item, str):
                            items.append({"label": "Insight", "detail": item})
                    data["highlights"] = items
                    break

        return data


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
                    'ConnectionTerminated', 'PROTOCOL_ERROR', 'SEND_HEADERS', 'StreamInput', 'state 5',
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
    def get_digest(self, mailbox_id: str, digest_date: date, digest_type: str = "daily") -> Optional[dict]:
        """Get a cached digest for a specific date + type. Returns None if not found."""
        resp = self._execute_with_retry(
            self.client.table("ai_daily_digests")
            .select("*")
            .eq("mailbox_id", mailbox_id)
            .eq("digest_date", digest_date.isoformat())
            .eq("digest_type", digest_type)
            .range(0, 0)
        )
        data = resp.data or []
        return data[0] if data else None

    def get_digest_or_generate(
        self,
        mailbox_id: str,
        client_id: Optional[str] = None,
        digest_date: Optional[date] = None,
        tz_offset_minutes: int = 0,
        digest_type: str = "daily",
    ) -> Optional[dict]:
        """Get cached digest or generate a new one."""
        target_date = digest_date or date.today()

        # Check cache first (cache key includes digest_type)
        cached = self.get_digest(mailbox_id, target_date, digest_type)
        if cached:
            return cached

        # Generate new
        return self.generate_digest(
            mailbox_id, client_id, target_date, tz_offset_minutes, digest_type
        )

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
        tz_offset_minutes: int = 0,
        digest_type: str = "daily",
    ) -> Optional[dict]:
        """
        Generate a daily or weekly digest using Claude Sonnet.

        Args:
            digest_type: "daily" (1 day window) or "weekly" (7 day window)
            tz_offset_minutes: user's UTC offset in minutes (JS getTimezoneOffset convention:
                negative = east of UTC, e.g. -330 for IST).
        """
        target_date = digest_date or date.today()

        if not self.ai_client.is_available:
            logger.error("AI client unavailable — cannot generate digest")
            return None

        # Compute time window based on digest type
        if digest_type == "weekly":
            window_days = 7
            scope = "weekly"
            time_window_label = f"{(target_date - timedelta(days=6)).isoformat()} to {target_date.isoformat()}"
        else:
            window_days = 1
            scope = "daily"
            time_window_label = target_date.isoformat()

        # --- Gather context ---
        context = self._gather_context(
            mailbox_id, client_id, target_date, tz_offset_minutes, window_days
        )

        # Sprint 3: Gather QB business context for richer insights
        business_context = self._gather_business_context(client_id)

        # Gather relationship context (lookback 90 days) for trend awareness
        relationship_context = self._gather_relationship_context(client_id)

        # Select prompt based on digest type
        if digest_type == "weekly":
            default_system = WEEKLY_DIGEST_SYSTEM_PROMPT
            user_template = WEEKLY_DIGEST_USER_TEMPLATE
            prompt_key = "weekly_digest"
        else:
            default_system = DIGEST_SYSTEM_PROMPT
            user_template = DIGEST_USER_TEMPLATE
            prompt_key = "daily_digest"

        # Apply client's model preferences from DB
        from .ai_email_analyzer import _apply_client_model_settings
        _apply_client_model_settings(self.client, client_id)

        # Load configurable prompt (DB override → hardcoded default)
        from .ai_prompt_loader import get_prompt
        digest_system_prompt = get_prompt(self.client, prompt_key,
                                          default_system, client_id)

        # Build user message with context data only (no schema — that's in the system prompt)
        # This keeps the user message clean and lets the custom prompt define the output schema.
        data_context = f"""TIME WINDOW: {time_window_label}

STATS:
- Emails received: {context["in_count"]} | Sent: {context["out_count"]}
- Open threads: {context["open_threads"]} | Overdue: {context["overdue_threads"]}

BUSINESS CONTEXT (from CRM):
{json.dumps(business_context, indent=2) if business_context else "Not available"}

RELATIONSHIP CONTEXT (90-day lookback):
{json.dumps(relationship_context, indent=2) if relationship_context else "Not available"}

BUSINESS SIGNAL EMAILS:
{json.dumps(context["top_signal_emails"], indent=2)}

HIGH PRIORITY EMAILS:
{json.dumps(context["priority_emails"], indent=2)}

Generate the {scope} digest now. Return ONLY valid JSON."""

        # Call strategic model (respects client's model preference)
        ai_response = self.ai_client.call_sonnet(
            digest_system_prompt, data_context, max_tokens=8192
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

        # Don't save empty digests — they poison the cache
        if not digest_data:
            logger.warning("Digest is empty after parsing — not saving to DB")
            self._log_usage(mailbox_id, client_id, ai_response, success=False, error_type="empty_result")
            return None

        # Save to database
        record = self._save_digest(
            mailbox_id, client_id, target_date, digest_data,
            context, ai_response, digest_type,
        )

        # Log usage
        self._log_usage(mailbox_id, client_id, ai_response, success=True)

        return record

    # ------------------------------------------------------------------
    # Context gathering (all Python-side, $0 cost)
    # ------------------------------------------------------------------
    def _gather_context(self, mailbox_id: str, client_id: Optional[str], target_date: date, tz_offset_minutes: int = 0, window_days: int = 1) -> dict:
        """Gather all context needed for digest generation.

        Uses strict date filtering — only considers emails whose sent_date falls
        within the target date window **in the user's local timezone**.

        Args:
            target_date: The end date of the window.
            tz_offset_minutes: JS-style getTimezoneOffset (negative = east of UTC).
            window_days: Number of days to include (1 = daily, 7 = weekly).

        The ai_email_intelligence rows are filtered by matching email_id
        (via sent_date on the emails table), NOT by their own created_at
        timestamp (which reflects analysis time, not send time).
        """
        from datetime import timezone as tz_mod, timedelta

        # Build timezone-aware day boundaries in the user's local timezone,
        # then convert to UTC ISO strings for Supabase queries.
        user_tz = tz_mod(timedelta(minutes=-(tz_offset_minutes or 0)))
        window_start_date = target_date - timedelta(days=window_days - 1)
        day_start_local = datetime.combine(window_start_date, datetime.min.time()).replace(tzinfo=user_tz)
        day_end_local = datetime.combine(target_date, datetime.max.time()).replace(tzinfo=user_tz)
        date_start = day_start_local.astimezone(tz_mod.utc).isoformat()
        date_end = day_end_local.astimezone(tz_mod.utc).isoformat()

        logger.info(f"Digest context: target_date={target_date}, tz_offset={tz_offset_minutes}, "
                     f"window_days={window_days}, date_start={date_start}, date_end={date_end}")

        # Email counts for the day — try direction first, fall back to is_outbound
        in_count = self._count_emails(mailbox_id, date_start, date_end, direction="inbound")
        out_count = self._count_emails(mailbox_id, date_start, date_end, direction="outbound")

        # If direction column is unpopulated, fall back to is_outbound
        if in_count == 0 and out_count == 0:
            try:
                total_resp = self._execute_with_retry(
                    self.client.table("emails")
                    .select("id", count="exact")
                    .eq("mailbox_id", mailbox_id)
                    .gte("sent_date", date_start)
                    .lte("sent_date", date_end)
                )
                total_in_range = total_resp.count or 0
                logger.info(f"Digest: direction cols empty, total emails in range: {total_in_range}")
                if total_in_range > 0:
                    out_resp = self._execute_with_retry(
                        self.client.table("emails")
                        .select("id", count="exact")
                        .eq("mailbox_id", mailbox_id)
                        .eq("is_outbound", "true")
                        .gte("sent_date", date_start)
                        .lte("sent_date", date_end)
                    )
                    out_count = out_resp.count or 0
                    in_count = total_in_range - out_count
            except Exception as e:
                logger.warning(f"Fallback email count failed: {e}")

        # Thread counts (scoped to digest date window)
        open_threads, overdue_threads = self._count_threads(mailbox_id, date_start, date_end)

        # Bucket summary from engine
        bucket_summary = {}
        bucket_engine = get_bucket_engine()
        if bucket_engine:
            bucket_summary = bucket_engine.get_bucket_summary(mailbox_id, client_id)

        # Get email IDs that were actually sent/received on the target date
        # This is used to filter ai_email_intelligence by sent_date, not analysis created_at
        date_email_ids = self._get_email_ids_for_date_range(mailbox_id, date_start, date_end)

        # Top signal emails — filtered by sent_date via email IDs
        top_signal_emails = self._get_top_signal_emails(mailbox_id, date_email_ids, limit=10)

        # High priority/urgent emails — filtered by sent_date via email IDs
        priority_emails = self._get_priority_emails(mailbox_id, date_email_ids, limit=10)

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

    def _count_threads(self, mailbox_id: str, date_start: str = None, date_end: str = None) -> tuple[int, int]:
        """Count open and overdue threads for a mailbox within the digest period.

        Only counts threads with recent activity (last_message_at within window),
        not all historical threads. Falls back to 30-day window if no dates provided.
        """
        try:
            # Default: threads active in last 30 days
            if not date_start:
                from datetime import timedelta
                date_start = (datetime.utcnow() - timedelta(days=30)).isoformat()

            # Open threads with activity in the window
            open_query = (
                self.client.table("thread_status")
                .select("id", count="exact")
                .eq("mailbox_id", mailbox_id)
                .neq("status", "complete")
                .neq("status", "dropped")
                .gte("last_message_at", date_start)
            )
            if date_end:
                open_query = open_query.lte("last_message_at", date_end)
            open_resp = self._execute_with_retry(open_query)
            open_count = open_resp.count or 0

            # Overdue threads with activity in the window
            overdue_query = (
                self.client.table("thread_status")
                .select("id", count="exact")
                .eq("mailbox_id", mailbox_id)
                .eq("is_overdue", 'true')
                .gte("last_message_at", date_start)
            )
            if date_end:
                overdue_query = overdue_query.lte("last_message_at", date_end)
            overdue_resp = self._execute_with_retry(overdue_query)
            overdue_count = overdue_resp.count or 0

            return open_count, overdue_count
        except Exception as e:
            logger.warning(f"Failed to count threads: {e}")
            return 0, 0

    def _get_email_ids_for_date_range(self, mailbox_id: str, date_start: str, date_end: str) -> list[str]:
        """Get email IDs whose sent_date falls within the date range.

        Used to bridge the emails table (has sent_date) with ai_email_intelligence
        (which only has created_at = analysis timestamp, NOT email send time).
        """
        try:
            all_ids: list[str] = []
            offset = 0
            PAGE = 500
            while True:
                resp = self._execute_with_retry(
                    self.client.table("emails")
                    .select("id")
                    .eq("mailbox_id", mailbox_id)
                    .gte("sent_date", date_start)
                    .lte("sent_date", date_end)
                    .range(offset, offset + PAGE - 1)
                )
                batch = resp.data or []
                all_ids.extend(r["id"] for r in batch)
                if len(batch) == 0:
                    break
                offset += len(batch)
            logger.info(f"Digest: {len(all_ids)} emails found for date range {date_start[:10]}")
            return all_ids
        except Exception as e:
            logger.warning(f"Failed to get email IDs for date range: {e}")
            return []

    def _get_top_signal_emails(self, mailbox_id: str, email_ids: list[str], limit: int = 10) -> list[dict]:
        """Get top emails by business_signal_score, filtered by email IDs (sent_date)."""
        if not email_ids:
            return []
        try:
            # Chunk email IDs (Supabase max 500 per .in_())
            all_rows: list[dict] = []
            for i in range(0, len(email_ids), 500):
                chunk = email_ids[i:i + 500]
                resp = self._execute_with_retry(
                    self.client.table("ai_email_intelligence")
                    .select("email_id,intent,urgency,sentiment,summary,"
                            "suggested_action,primary_bucket,business_signal_score,"
                            "confidence")
                    .eq("mailbox_id", mailbox_id)
                    .eq("processing_status", "completed")
                    .gt("business_signal_score", "0")
                    .in_("email_id", chunk)
                    .order("business_signal_score", desc=True)
                    .range(0, limit - 1)
                )
                all_rows.extend(resp.data or [])

            # Sort and limit across chunks
            all_rows.sort(key=lambda r: r.get("business_signal_score", 0), reverse=True)
            rows = all_rows[:limit]

            # Enrich with sender name
            row_email_ids = [r["email_id"] for r in rows if r.get("email_id")]
            sender_lookup = self._get_email_senders(row_email_ids)

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

    def _get_priority_emails(self, mailbox_id: str, email_ids: list[str], limit: int = 10) -> list[dict]:
        """Get urgent/critical emails, filtered by email IDs (sent_date)."""
        if not email_ids:
            return []
        try:
            all_rows: list[dict] = []
            for i in range(0, len(email_ids), 500):
                chunk = email_ids[i:i + 500]
                resp = self._execute_with_retry(
                    self.client.table("ai_email_intelligence")
                    .select("email_id,intent,urgency,sentiment,summary,"
                            "suggested_action,primary_bucket,confidence")
                    .eq("mailbox_id", mailbox_id)
                    .eq("processing_status", "completed")
                    .in_("urgency", ["critical", "high"])
                    .in_("email_id", chunk)
                    .order("confidence", desc=True)
                    .range(0, limit - 1)
                )
                all_rows.extend(resp.data or [])

            # Sort by confidence and limit across chunks
            all_rows.sort(key=lambda r: r.get("confidence", 0), reverse=True)
            rows = all_rows[:limit]

            row_email_ids = [r["email_id"] for r in rows if r.get("email_id")]
            sender_lookup = self._get_email_senders(row_email_ids)

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
    # Sprint 3: Gather QB business context for digest
    # ------------------------------------------------------------------
    def _gather_business_context(self, client_id: Optional[str]) -> Optional[list]:
        """
        Fetch top companies with QB data to give the digest business context.
        Returns a compact list of company summaries for the LLM prompt.
        """
        if not client_id:
            return None
        try:
            resp = self._execute_with_retry(
                self.client.table("customer_companies")
                .select("company_name,qb_customer_type,qb_tier,qb_total_revenue,"
                        "qb_invoiced_ty,qb_invoiced_ly,qb_days_since_last_invoice,"
                        "engagement_score")
                .eq("client_id", client_id)
                .not_.is_("qb_total_revenue", "null")
                .order("qb_total_revenue", desc=True)
                .range(0, 9)  # Top 10 by revenue
            )
            if not resp.data:
                return None

            summaries = []
            for c in resp.data:
                rev_ty = c.get("qb_invoiced_ty") or 0
                rev_ly = c.get("qb_invoiced_ly") or 0
                trend = "growing" if rev_ty > rev_ly else ("declining" if rev_ty < rev_ly * 0.9 else "stable")
                summaries.append({
                    "company": c["company_name"],
                    "type": c.get("qb_customer_type") or "unknown",
                    "tier": c.get("qb_tier") or "?",
                    "revenue": f"${c.get('qb_total_revenue', 0):,.0f}",
                    "trend": trend,
                    "days_since_order": c.get("qb_days_since_last_invoice"),
                    "engagement": c.get("engagement_score"),
                })
            return summaries
        except Exception as e:
            logger.warning(f"Failed to gather business context: {e}")
            return None

    def _gather_relationship_context(self, client_id: Optional[str]) -> Optional[list]:
        """
        Fetch pre-computed relationship context from cache (built by strategic context builder).
        Provides 90-day lookback: engagement trends, lifecycle tiers, overdue threads, response times.
        Gives the digest awareness of broader relationship health beyond just today's/this week's emails.
        """
        if not client_id:
            return None
        try:
            resp = self._execute_with_retry(
                self.client.table("relationship_context_cache")
                .select("company_id,lifecycle_tier,am_name,"
                        "engagement_trajectory,active_threads_summary,"
                        "communication_health,ai_signals_summary,"
                        "qb_financial_summary,"
                        "customer_companies(company_name)")
                .eq("client_id", client_id)
                .order("computed_at", desc=True)
                .range(0, 19)  # Top 20 most recently computed
            )
            if not resp.data:
                return None

            summaries = []
            for r in resp.data:
                threads = r.get("active_threads_summary") or {}
                if isinstance(threads, str):
                    try:
                        threads = json.loads(threads)
                    except Exception:
                        threads = {}
                health = r.get("communication_health") or {}
                if isinstance(health, str):
                    try:
                        health = json.loads(health)
                    except Exception:
                        health = {}
                signals = r.get("ai_signals_summary") or {}
                if isinstance(signals, str):
                    try:
                        signals = json.loads(signals)
                    except Exception:
                        signals = {}
                financial = r.get("qb_financial_summary") or {}
                if isinstance(financial, str):
                    try:
                        financial = json.loads(financial)
                    except Exception:
                        financial = {}

                # company_name comes from FK join
                company_ref = r.get("customer_companies") or {}
                company_name = company_ref.get("company_name") if isinstance(company_ref, dict) else None

                summaries.append({
                    "company": company_name or "Unknown",
                    "lifecycle_tier": r.get("lifecycle_tier") or "unknown",
                    "am": r.get("am_name") or "unassigned",
                    "engagement_trend": r.get("engagement_trajectory") or "unknown",
                    "overdue_threads": threads.get("overdue_count", 0),
                    "active_threads": threads.get("active_count", 0),
                    "avg_response_hours": health.get("avg_response_hours"),
                    "urgency_signals": signals.get("bucket_distribution", {}).get("response_urgency", 0),
                    "retention_risk_signals": signals.get("bucket_distribution", {}).get("retention_risk", 0),
                    "revenue": financial.get("total_revenue"),
                    "days_since_invoice": financial.get("days_since_last_invoice"),
                })
            return summaries
        except Exception as e:
            logger.warning(f"Failed to gather relationship context: {e}")
            return None

    # ------------------------------------------------------------------
    # Parse + validate AI response
    # ------------------------------------------------------------------
    def _parse_digest_response(self, ai_response: AIResponse) -> Optional[dict]:
        """Parse AI response into a dict. Accepts any JSON structure — the prompt defines the schema."""
        try:
            cleaned = clean_llm_output(ai_response.content)

            # Primary: json_repair (handles Gemini quirks)
            parsed = None
            try:
                from json_repair import repair_json
                repaired = repair_json(cleaned, return_objects=True)
                if isinstance(repaired, dict):
                    parsed = repaired
            except Exception:
                pass

            # Fallback: standard json.loads
            if parsed is None:
                parsed = json.loads(cleaned)

            if not isinstance(parsed, dict):
                logger.error(f"Digest response is not a dict: {type(parsed)}")
                return None

            # Check if it has any meaningful content
            has_content = False
            for v in parsed.values():
                if v and v != [] and v != {} and v is not None:
                    has_content = True
                    break

            if not has_content:
                logger.warning(f"Digest parsed but empty. Raw (first 500): {ai_response.content[:500]}")
                return None

            # Normalize: ensure legacy keys exist for frontend compatibility
            # (frontend reads summary, action_items, highlights)
            if "summary" not in parsed:
                # Build summary from headline or first string field
                headline = parsed.get("headline")
                if isinstance(headline, dict):
                    parts = [v for v in headline.values() if isinstance(v, str) and v]
                    parsed["summary"] = " | ".join(parts[:3])
                elif isinstance(headline, str):
                    parsed["summary"] = headline
                else:
                    # Use first long string value
                    for v in parsed.values():
                        if isinstance(v, str) and len(v) > 20:
                            parsed["summary"] = v
                            break

            if "action_items" not in parsed:
                # Map urgent_today to action_items for frontend
                urgent = parsed.get("urgent_today") or parsed.get("actions") or []
                if isinstance(urgent, list):
                    parsed["action_items"] = [
                        {
                            "priority": 1,
                            "action": item.get("action") or item.get("next_action") or str(item),
                            "contact_name": item.get("customer") or item.get("am"),
                            "bucket": item.get("quote_no"),
                        }
                        for item in urgent if isinstance(item, dict)
                    ]

            if "highlights" not in parsed:
                # Map positive_signals or pipeline_watch to highlights
                signals = parsed.get("positive_signals") or parsed.get("pipeline_watch") or []
                if isinstance(signals, list):
                    parsed["highlights"] = [
                        {
                            "label": item.get("customer") or item.get("signal") or "Signal",
                            "detail": item.get("signal") or item.get("status") or str(item),
                        }
                        for item in signals if isinstance(item, dict)
                    ]

            logger.info(f"Digest parsed successfully with keys: {list(parsed.keys())}")
            return parsed

        except json.JSONDecodeError as e:
            logger.error(f"Digest JSON parse failed: {e}. Raw (first 500): {ai_response.content[:500]}")
            # Degraded: return raw text as summary
            return {"summary": ai_response.content[:1000], "action_items": [], "highlights": []}
        except Exception as e:
            logger.error(f"Digest parse error: {e}. Raw (first 500): {ai_response.content[:500]}")
            return None

    # ------------------------------------------------------------------
    # Save to database
    # ------------------------------------------------------------------
    def _save_digest(
        self,
        mailbox_id: str,
        client_id: Optional[str],
        digest_date: date,
        digest_data: dict,
        context: dict,
        ai_response: AIResponse,
        digest_type: str = "daily",
    ) -> dict:
        """Save generated digest to ai_daily_digests table."""
        # Extract standard fields + store full AI response for custom schemas
        summary = digest_data.get("summary", "")
        action_items = digest_data.get("action_items", [])
        highlights = digest_data.get("highlights", [])
        # Ensure they're serializable
        if not isinstance(action_items, list):
            action_items = []
        if not isinstance(highlights, list):
            highlights = []

        record = {
            "mailbox_id": mailbox_id,
            "digest_date": digest_date.isoformat(),
            "digest_type": digest_type,
            "summary": summary[:5000] if isinstance(summary, str) else json.dumps(summary)[:5000],
            "action_items": action_items,
            "highlights": highlights,
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
                .upsert(record, on_conflict="mailbox_id,digest_date,digest_type")
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
