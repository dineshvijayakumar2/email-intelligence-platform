"""
AI Usage Tracker — Cost tracking and monitoring for Claude API usage.

Logs every AI operation to `ai_usage_log` with token counts, cost,
error tracking, and retry counts. Provides summary and monitoring queries.

Follows extraction_orchestrator pattern: _execute_with_retry for Supabase.
"""

import time
import logging
from typing import Optional
from datetime import datetime, timedelta
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cost calculation (must match ai_client.py pricing)
# ---------------------------------------------------------------------------
MODEL_PRICING = {
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    "claude-sonnet-4-6-20250514": {"input": 3.00, "output": 15.00},
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate estimated cost in USD."""
    pricing = MODEL_PRICING.get(model, {"input": 1.0, "output": 5.0})
    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    return round(input_cost + output_cost, 6)


@dataclass
class UsageSummary:
    """Summary of AI usage over a period."""
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    total_requests: int
    by_operation: dict  # {operation: {cost, count}}
    by_model: dict      # {model: {cost, count}}
    failure_rate: float  # 0.0-1.0
    avg_latency_ms: float


@dataclass
class MonitoringStats:
    """Real-time monitoring metrics."""
    parse_failure_rate: float
    api_failure_rate: float
    avg_retry_count: float
    cost_per_1000_emails: float
    total_failures_24h: int
    total_requests_24h: int


class AIUsageTracker:
    """Tracks AI API usage, costs, and health metrics."""

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
                    'JSON could not be generated', 'ECONNRESET', 'ETIMEDOUT',
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

    def log_usage(
        self,
        operation: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        mailbox_id: Optional[str] = None,
        client_id: Optional[str] = None,
        processing_time_ms: Optional[int] = None,
        batch_size: int = 1,
        success: bool = True,
        error_type: Optional[str] = None,
        retry_count: int = 0,
        prompt_version: Optional[str] = None,
    ) -> None:
        """
        Log a single AI API usage event.

        Args:
            operation: 'email_intelligence', 'digest', 'relationship_summary'
            model: Model ID string
            input_tokens: Tokens consumed in prompt
            output_tokens: Tokens generated in response
            mailbox_id: Associated mailbox (optional)
            client_id: Associated client (optional)
            processing_time_ms: Wall-clock time for the API call
            batch_size: Number of emails in this batch
            success: Whether the call succeeded
            error_type: 'json_parse', 'validation', 'api_timeout', 'rate_limit', 'api_unavailable'
            retry_count: Number of retries before success/failure
            prompt_version: Version of the prompt template used
        """
        cost = estimate_cost(model, input_tokens, output_tokens)

        row = {
            "operation": operation,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost_usd": cost,
            "processing_time_ms": processing_time_ms,
            "batch_size": batch_size,
            "success": success,
            "retry_count": retry_count,
        }

        # Optional fields — only include if provided (avoid null FK issues)
        if mailbox_id:
            row["mailbox_id"] = mailbox_id
        if client_id:
            row["client_id"] = client_id
        if error_type:
            row["error_type"] = error_type
        if prompt_version:
            row["prompt_version"] = prompt_version

        try:
            self._execute_with_retry(
                self.client.table("ai_usage_log").insert(row)
            )
        except Exception as e:
            # Usage tracking should never block the main pipeline
            logger.error(f"Failed to log AI usage: {e}")

    def get_usage_summary(
        self,
        client_id: Optional[str] = None,
        days: int = 30,
    ) -> UsageSummary:
        """
        Get aggregated usage summary over a time period.

        Fetches all rows and computes aggregates in Python
        (Supabase client lacks GROUP BY).
        """
        since = (datetime.utcnow() - timedelta(days=days)).isoformat()

        query = (
            self.client.table("ai_usage_log")
            .select("*")
            .gte("created_at", since)
            .order("created_at", desc=True)
        )
        if client_id:
            query = query.eq("client_id", client_id)

        # Paginate
        all_rows = []
        offset = 0
        PAGE_SIZE = 500
        while True:
            batch_resp = self._execute_with_retry(
                query.range(offset, offset + PAGE_SIZE - 1)
            )
            batch = batch_resp.data or []
            all_rows.extend(batch)
            if len(batch) == 0:
                break
            offset += len(batch)

        # Aggregate in Python
        total_cost = 0.0
        total_input = 0
        total_output = 0
        total_latency = 0
        latency_count = 0
        failures = 0
        by_operation = {}
        by_model = {}

        for row in all_rows:
            cost = float(row.get("estimated_cost_usd") or 0)
            total_cost += cost
            total_input += row.get("input_tokens", 0)
            total_output += row.get("output_tokens", 0)

            if row.get("processing_time_ms"):
                total_latency += row["processing_time_ms"]
                latency_count += 1

            if not row.get("success", True):
                failures += 1

            # By operation
            op = row.get("operation", "unknown")
            if op not in by_operation:
                by_operation[op] = {"cost": 0.0, "count": 0}
            by_operation[op]["cost"] += cost
            by_operation[op]["count"] += 1

            # By model
            mdl = row.get("model", "unknown")
            if mdl not in by_model:
                by_model[mdl] = {"cost": 0.0, "count": 0}
            by_model[mdl]["cost"] += cost
            by_model[mdl]["count"] += 1

        total_requests = len(all_rows)

        return UsageSummary(
            total_cost_usd=round(total_cost, 4),
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            total_requests=total_requests,
            by_operation=by_operation,
            by_model=by_model,
            failure_rate=round(failures / total_requests, 4) if total_requests > 0 else 0.0,
            avg_latency_ms=round(total_latency / latency_count, 1) if latency_count > 0 else 0.0,
        )

    def get_monitoring_stats(
        self,
        client_id: Optional[str] = None,
    ) -> MonitoringStats:
        """
        Get real-time monitoring metrics (last 24 hours).

        Used by the admin monitoring dashboard to track health.
        """
        since = (datetime.utcnow() - timedelta(hours=24)).isoformat()

        query = (
            self.client.table("ai_usage_log")
            .select("*")
            .gte("created_at", since)
        )
        if client_id:
            query = query.eq("client_id", client_id)

        # Paginate
        all_rows = []
        offset = 0
        PAGE_SIZE = 500
        while True:
            batch_resp = self._execute_with_retry(
                query.range(offset, offset + PAGE_SIZE - 1)
            )
            batch = batch_resp.data or []
            all_rows.extend(batch)
            if len(batch) == 0:
                break
            offset += len(batch)

        total = len(all_rows)
        if total == 0:
            return MonitoringStats(
                parse_failure_rate=0.0,
                api_failure_rate=0.0,
                avg_retry_count=0.0,
                cost_per_1000_emails=0.0,
                total_failures_24h=0,
                total_requests_24h=0,
            )

        parse_failures = 0
        api_failures = 0
        total_retries = 0
        total_cost = 0.0
        total_batch_size = 0
        total_failures = 0

        for row in all_rows:
            error_type = row.get("error_type")
            if error_type in ("json_parse", "validation"):
                parse_failures += 1
            if error_type in ("api_timeout", "rate_limit", "api_unavailable"):
                api_failures += 1
            if not row.get("success", True):
                total_failures += 1

            total_retries += row.get("retry_count", 0)
            total_cost += float(row.get("estimated_cost_usd") or 0)
            total_batch_size += row.get("batch_size", 1)

        cost_per_1000 = (total_cost / total_batch_size * 1000) if total_batch_size > 0 else 0.0

        return MonitoringStats(
            parse_failure_rate=round(parse_failures / total, 4) if total > 0 else 0.0,
            api_failure_rate=round(api_failures / total, 4) if total > 0 else 0.0,
            avg_retry_count=round(total_retries / total, 2) if total > 0 else 0.0,
            cost_per_1000_emails=round(cost_per_1000, 4),
            total_failures_24h=total_failures,
            total_requests_24h=total,
        )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_usage_tracker: Optional[AIUsageTracker] = None


def init_usage_tracker(supabase_client) -> AIUsageTracker:
    """Initialize the global usage tracker with a Supabase client."""
    global _usage_tracker
    _usage_tracker = AIUsageTracker(supabase_client)
    return _usage_tracker


def get_usage_tracker() -> Optional[AIUsageTracker]:
    """Get the initialized usage tracker instance."""
    return _usage_tracker
