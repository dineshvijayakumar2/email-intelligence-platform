"""
Strategic Context Builder — Pre-computes relationship context for strategic digests.

Combines email intelligence data (engagement scores, threads, AI signals) with
Quickbase business data (revenue, quotes, tiers) into a unified relationship
context cache. No LLM calls — pure DB queries, $0 cost.

Used by the strategic digest generator to produce high-value AM-facing summaries
without needing to re-query dozens of tables at generation time.
"""

import time
import threading
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime, timezone, timedelta

from .ai_action_bucket_engine import compute_lifecycle_tier

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BATCH_SIZE = 50  # companies per iteration
ENGAGEMENT_TREND_WINDOW = 5  # minimum data points to compute trend
OVERDUE_THREAD_DAYS = 7  # threads with no reply in N days = overdue


class StrategicContextBuilder:
    """Pre-computes and caches relationship context for strategic digest generation."""

    def __init__(self, supabase_client, client_id: str):
        self.client = supabase_client
        self.client_id = client_id

    # ------------------------------------------------------------------
    # Retry helper (matches codebase pattern)
    # ------------------------------------------------------------------
    @staticmethod
    def _execute_with_retry(query_builder, max_retries: int = 3, base_delay: float = 0.5):
        """Execute a Supabase query with retry for transient errors."""
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                return query_builder.execute()
            except Exception as e:
                last_error = e
                error_str = str(e)
                is_transient = (
                    isinstance(e, OSError) or
                    any(keyword in error_str for keyword in [
                        'SSL handshake failed', '525', '502', '503', '504',
                        'Connection reset', 'Connection refused', 'timed out',
                        'JSON could not be generated', 'ECONNRESET', 'ETIMEDOUT',
                        'ConnectionTerminated', 'PROTOCOL_ERROR',
                        'Resource temporarily unavailable',
                    ])
                )
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
    # 1. Build context for a single company
    # ------------------------------------------------------------------
    def build_company_context(
        self,
        company_id: str,
        lookback_months: int = 6,
    ) -> Optional[Dict[str, Any]]:
        """
        Build full relationship context for one company and upsert into cache.

        Returns the context dict on success, None on failure.
        """
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_months * 30)
            cutoff_iso = cutoff.isoformat()

            # --- Engagement trajectory from metric_history ---
            engagement_trajectory = self._get_engagement_trajectory(company_id, cutoff_iso)

            # --- Communication health from email_response_metrics ---
            communication_health = self._get_communication_health(company_id, cutoff_iso)

            # --- Active threads summary ---
            active_threads = self._get_active_threads(company_id)

            # --- AI signals from ai_email_intelligence ---
            ai_signals = self._get_ai_signals(company_id, cutoff_iso)

            # --- Key contacts ---
            key_contacts = self._get_key_contacts(company_id)

            # --- QB financial data from customer_companies + qb_quotes ---
            qb_summary = self._get_qb_financial_summary(company_id)

            # --- Capability profile from QB operations ---
            capability_profile = self._get_capability_profile(company_id)

            # --- Read company row for QB metadata + engagement ---
            company_resp = self._execute_with_retry(
                self.client.table("customer_companies")
                .select("company_name,qb_customer_type,qb_tier,qb_account_manager,"
                        "qb_days_since_last_invoice,qb_total_revenue,engagement_score,"
                        "frequency_trend")
                .eq("id", company_id)
                .range(0, 0)
            )
            company_data = (company_resp.data or [{}])[0] if company_resp.data else {}

            # --- Compute lifecycle tier ---
            # Derive first-invoice recency from qb_summary (open_quotes not a proxy, use days_since)
            days_since = company_data.get("qb_days_since_last_invoice")
            # Rough proxy for "new customer": days_since is small but revenue is also small
            qb_revenue = float(company_data.get("qb_total_revenue") or 0)
            days_first = days_since if (qb_revenue < 5000 and days_since is not None and days_since < 90) else None
            lifecycle_tier = compute_lifecycle_tier(
                qb_customer_type=company_data.get("qb_customer_type") or "",
                qb_tier=company_data.get("qb_tier") or "",
                qb_total_revenue=company_data.get("qb_total_revenue"),
                qb_days_since_last_invoice=days_since,
                qb_days_since_first_invoice=days_first,
                engagement_score=int(company_data.get("engagement_score") or 0),
                engagement_trend=company_data.get("frequency_trend") or "stable",
            )

            # --- Resolve AM from mailbox → user ---
            # primary_mailbox_id lives on relationship_context_cache, not customer_companies
            am_info = self._get_primary_am(company_id)

            # Compute trend label
            trend = self._compute_trend(engagement_trajectory)

            # Build the context record
            context = {
                "client_id": self.client_id,
                "company_id": company_id,
                "customer_type": company_data.get("qb_customer_type"),
                "customer_tier": company_data.get("qb_tier"),
                "account_manager": am_info.get("am_name") or company_data.get("qb_account_manager"),
                "lifecycle_tier": lifecycle_tier,
                "am_user_id": am_info.get("user_id"),
                "am_name": am_info.get("am_name"),
                "primary_mailbox_id": am_info.get("mailbox_id"),
                "engagement_trajectory": trend,
                "engagement_scores_history": engagement_trajectory,
                "communication_health": communication_health,
                "key_contacts": key_contacts,
                "active_threads_summary": active_threads,
                "ai_signals_summary": ai_signals,
                "qb_financial_summary": qb_summary,
                "capability_profile": capability_profile,
                "computed_at": datetime.now(timezone.utc).isoformat(),
            }

            # Upsert into cache
            self._execute_with_retry(
                self.client.table("relationship_context_cache")
                .upsert(context, on_conflict="client_id,company_id")
            )

            logger.debug(f"Built context for company {company_id} ({company_data.get('company_name', '?')})")
            return context

        except Exception as e:
            logger.error(f"Failed to build context for company {company_id}: {e}")
            return None

    # ------------------------------------------------------------------
    # 2. Build contexts for all companies in client
    # ------------------------------------------------------------------
    def build_all_contexts(self, lookback_months: int = 6, on_progress=None, cancel_check=None) -> Dict[str, Any]:
        """
        Iterate all companies for this client and build context for each.

        Returns: {"total": int, "succeeded": int, "failed": int, "elapsed_s": float}
        """
        start_time = time.time()

        # Fetch all company IDs for this client
        company_ids = []
        offset = 0
        while True:
            resp = self._execute_with_retry(
                self.client.table("customer_companies")
                .select("id")
                .eq("client_id", self.client_id)
                .range(offset, offset + BATCH_SIZE - 1)
            )
            batch = resp.data or []
            if len(batch) == 0:
                break
            company_ids.extend([row["id"] for row in batch])
            offset += len(batch)

        total = len(company_ids)
        logger.info(f"Building strategic context for {total} companies (client={self.client_id})")

        succeeded = 0
        failed = 0
        completed = 0
        lock = threading.Lock()

        def _process(cid: str):
            return self.build_company_context(cid, lookback_months=lookback_months)

        max_workers = min(3, max(1, total))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_process, cid): cid for cid in company_ids}
            for future in as_completed(futures):
                if cancel_check and cancel_check():
                    executor.shutdown(wait=False, cancel_futures=True)
                    logger.info("Context build cancelled by user request")
                    break
                try:
                    result = future.result()
                except Exception as exc:
                    logger.error(f"Company context worker raised: {exc}")
                    result = None

                with lock:
                    completed += 1
                    if result is not None:
                        succeeded += 1
                    else:
                        failed += 1
                    current = completed

                if current % 25 == 0 or current == total:
                    logger.info(f"  Progress: {current}/{total} companies processed")
                    if on_progress:
                        on_progress(
                            "building_context",
                            current,
                            total,
                            f"Building relationship context ({current}/{total} companies)…",
                        )

        elapsed = round(time.time() - start_time, 2)
        logger.info(
            f"Context build complete: {succeeded} succeeded, {failed} failed, "
            f"{elapsed}s elapsed"
        )

        return {
            "total": len(company_ids),
            "succeeded": succeeded,
            "failed": failed,
            "elapsed_s": elapsed,
        }

    # ------------------------------------------------------------------
    # 3. Build AM performance snapshots
    # ------------------------------------------------------------------
    def build_am_performance(
        self,
        period_start: str,
        period_end: str,
        comparison_start: str,
        comparison_end: str,
    ) -> List[Dict[str, Any]]:
        """
        Compute per-AM metrics for the given period and comparison period.
        Stores results in am_performance_snapshots.

        Args:
            period_start/end: ISO date strings for the current period
            comparison_start/end: ISO date strings for the prior period

        Returns: list of AM snapshot dicts
        """
        try:
            # --- Revenue by AM from qb_sales_line_items ---
            current_revenue = self._get_revenue_by_am(period_start, period_end)
            comparison_revenue = self._get_revenue_by_am(comparison_start, comparison_end)

            # --- Quote counts by AM from qb_quotes ---
            current_quotes = self._get_quote_stats_by_am(period_start, period_end)
            comparison_quotes = self._get_quote_stats_by_am(comparison_start, comparison_end)

            # --- Response times by AM ---
            current_response = self._get_response_times_by_am(period_start, period_end)

            # Collect all AM names
            all_ams = set()
            all_ams.update(current_revenue.keys())
            all_ams.update(comparison_revenue.keys())
            all_ams.update(current_quotes.keys())
            all_ams.update(current_response.keys())

            snapshots = []
            now_iso = datetime.now(timezone.utc).isoformat()

            for am_name in all_ams:
                if not am_name:
                    continue

                curr_rev = current_revenue.get(am_name, 0)
                comp_rev = comparison_revenue.get(am_name, 0)
                revenue_growth = None
                if comp_rev and comp_rev > 0:
                    revenue_growth = round((curr_rev - comp_rev) / comp_rev * 100, 2)

                curr_q = current_quotes.get(am_name, {})
                comp_q = comparison_quotes.get(am_name, {})
                curr_conversion = None
                if curr_q.get("total", 0) > 0:
                    curr_conversion = round(curr_q.get("won", 0) / curr_q["total"] * 100, 2)

                resp = current_response.get(am_name, {})

                snapshot = {
                    "client_id": self.client_id,
                    "account_manager": am_name,
                    "period_start": period_start,
                    "period_end": period_end,
                    "revenue_current": curr_rev,
                    "revenue_comparison": comp_rev,
                    "revenue_growth_pct": revenue_growth,
                    "quotes_total": curr_q.get("total", 0),
                    "quotes_won": curr_q.get("won", 0),
                    "quote_conversion_pct": curr_conversion,
                    "avg_response_time_hours": resp.get("avg_hours"),
                    "median_response_time_hours": resp.get("median_hours"),
                    "computed_at": now_iso,
                }
                snapshots.append(snapshot)

            # Batch upsert into am_performance_snapshots
            if snapshots:
                for i in range(0, len(snapshots), 100):
                    batch = snapshots[i:i + 100]
                    self._execute_with_retry(
                        self.client.table("am_performance_snapshots")
                        .upsert(batch, on_conflict="client_id,account_manager,period_start,period_end")
                    )

            logger.info(f"Built AM performance for {len(snapshots)} AMs ({period_start} to {period_end})")
            return snapshots

        except Exception as e:
            logger.error(f"Failed to build AM performance: {e}")
            return []

    # ------------------------------------------------------------------
    # 4. Get cached contexts for digest generation
    # ------------------------------------------------------------------
    def get_contexts_for_digest(self, top_n: int = 20) -> List[Dict[str, Any]]:
        """
        Read from relationship_context_cache, return top N companies
        ranked by a combination of engagement score and QB revenue.
        """
        try:
            all_contexts = []
            offset = 0
            while True:
                resp = self._execute_with_retry(
                    self.client.table("relationship_context_cache")
                    .select("*")
                    .eq("client_id", self.client_id)
                    .range(offset, offset + 499)
                )
                batch = resp.data or []
                if len(batch) == 0:
                    break
                all_contexts.extend(batch)
                offset += len(batch)

            if not all_contexts:
                logger.info("No cached contexts found for digest")
                return []

            # Score each context for ranking
            LIFECYCLE_URGENCY = {
                "at_risk": 150,
                "dormant": 100,
                "champion": 80,
                "active_customer": 20,
                "new_customer": 40,
                "prospect": 10,
            }

            def rank_score(ctx: dict) -> float:
                score = 0.0

                # Lifecycle urgency boost (at-risk/dormant always surface)
                tier = ctx.get("lifecycle_tier") or ""
                score += LIFECYCLE_URGENCY.get(tier, 0)

                # Latest engagement score (from history)
                history = ctx.get("engagement_scores_history") or []
                if history:
                    latest = history[-1] if isinstance(history, list) else None
                    if latest and isinstance(latest, dict):
                        score += latest.get("engagement_score", 0) * 10

                # QB revenue component
                qb = ctx.get("qb_financial_summary") or {}
                revenue = qb.get("total_revenue") or 0
                if revenue > 0:
                    score += min(revenue / 10000, 100)

                # Boost declining relationships
                if ctx.get("engagement_trajectory") == "declining":
                    score += 50

                return score

            all_contexts.sort(key=rank_score, reverse=True)

            return all_contexts[:top_n]

        except Exception as e:
            logger.error(f"Failed to get contexts for digest: {e}")
            return []

    # ==================================================================
    # Private helper methods
    # ==================================================================

    def _get_engagement_trajectory(self, company_id: str, cutoff_iso: str) -> List[Dict]:
        """Fetch engagement score history from metric_history."""
        try:
            resp = self._execute_with_retry(
                self.client.table("metric_history")
                .select("engagement_score,calculated_at,scoring_version")
                .eq("entity_type", "company")
                .eq("entity_id", company_id)
                .gte("calculated_at", cutoff_iso)
                .order("calculated_at", desc=False)
                .range(0, 99)
            )
            rows = resp.data or []
            return [
                {
                    "engagement_score": r.get("engagement_score"),
                    "calculated_at": r.get("calculated_at"),
                    "scoring_version": r.get("scoring_version"),
                }
                for r in rows
            ]
        except Exception as e:
            logger.warning(f"Failed to get engagement trajectory for {company_id}: {e}")
            return []

    def _get_communication_health(self, company_id: str, cutoff_iso: str) -> Dict[str, Any]:
        """Compute communication health from email_response_metrics."""
        try:
            # Get contacts for this company
            contacts_resp = self._execute_with_retry(
                self.client.table("customer_contacts")
                .select("id")
                .eq("customer_company_id", company_id)
                .range(0, 499)
            )
            contact_ids = [c["id"] for c in (contacts_resp.data or [])]

            if not contact_ids:
                return {"avg_response_hours": None, "total_responses": 0, "contact_count": 0}

            # Fetch response metrics for these contacts
            all_metrics = []
            for i in range(0, len(contact_ids), 500):
                chunk = contact_ids[i:i + 500]
                resp = self._execute_with_retry(
                    self.client.table("email_response_metrics")
                    .select("response_time_seconds,business_hours_response_time_seconds,created_at")
                    .in_("responder_contact_id", chunk)
                    .gte("created_at", cutoff_iso)
                    .range(0, 999)
                )
                all_metrics.extend(resp.data or [])

            if not all_metrics:
                return {"avg_response_hours": None, "total_responses": 0, "contact_count": len(contact_ids)}

            # Calculate averages
            response_times = [
                m["response_time_seconds"]
                for m in all_metrics
                if m.get("response_time_seconds") is not None
            ]
            bh_times = [
                m["business_hours_response_time_seconds"]
                for m in all_metrics
                if m.get("business_hours_response_time_seconds") is not None
            ]

            avg_response_hours = round(sum(response_times) / len(response_times) / 3600, 2) if response_times else None
            avg_bh_response_hours = round(sum(bh_times) / len(bh_times) / 3600, 2) if bh_times else None

            return {
                "avg_response_hours": avg_response_hours,
                "avg_bh_response_hours": avg_bh_response_hours,
                "total_responses": len(all_metrics),
                "contact_count": len(contact_ids),
            }

        except Exception as e:
            logger.warning(f"Failed to get communication health for {company_id}: {e}")
            return {"avg_response_hours": None, "total_responses": 0, "contact_count": 0}

    def _get_active_threads(self, company_id: str) -> Dict[str, Any]:
        """Get active and overdue thread counts + subject lines."""
        try:
            overdue_cutoff = datetime.now(timezone.utc) - timedelta(days=OVERDUE_THREAD_DAYS)
            overdue_cutoff_iso = overdue_cutoff.isoformat()

            # Active statuses — threads awaiting a reply or ongoing
            active_statuses = [
                "awaiting_reply", "overdue", "ongoing",
                "awaiting_response", "awaiting_our_response",
            ]

            resp = self._execute_with_retry(
                self.client.table("thread_status")
                .select("thread_id,subject,status,last_message_at")
                .eq("customer_company_id", company_id)
                .in_("status", active_statuses)
                .range(0, 99)
            )
            all_threads = resp.data or []

            company_threads = []
            for t in all_threads:
                is_overdue = (
                    t.get("status") == "overdue" or
                    (t.get("last_message_at") or "") < overdue_cutoff_iso
                )
                company_threads.append({
                    "thread_id": t.get("thread_id"),
                    "subject": t.get("subject", "")[:100],
                    "last_message_at": t.get("last_message_at"),
                    "is_overdue": is_overdue,
                })

            overdue_count = sum(1 for t in company_threads if t.get("is_overdue"))

            return {
                "active_count": len(company_threads),
                "overdue_count": overdue_count,
                "threads": company_threads[:10],  # Cap at 10 for cache size
            }

        except Exception as e:
            logger.warning(f"Failed to get active threads for {company_id}: {e}")
            return {"active_count": 0, "overdue_count": 0, "threads": []}

    def _get_ai_signals(self, company_id: str, cutoff_iso: str) -> Dict[str, Any]:
        """Get AI signal distribution from ai_email_intelligence."""
        try:
            # Get emails linked to this company
            email_resp = self._execute_with_retry(
                self.client.table("emails")
                .select("id")
                .eq("customer_company_id", company_id)
                .gte("sent_date", cutoff_iso)
                .range(0, 999)
            )
            email_ids = [e["id"] for e in (email_resp.data or [])]

            if not email_ids:
                return {"total_analyzed": 0, "bucket_distribution": {}, "top_signals": []}

            # Fetch intelligence rows
            all_intel = []
            for i in range(0, len(email_ids), 500):
                chunk = email_ids[i:i + 500]
                resp = self._execute_with_retry(
                    self.client.table("ai_email_intelligence")
                    .select("primary_bucket,sentiment,business_signal_score,business_signal")
                    .in_("email_id", chunk)
                    .range(0, 999)
                )
                all_intel.extend(resp.data or [])

            # Bucket distribution
            bucket_counts: Dict[str, int] = {}
            escalation_count = 0
            churn_count = 0
            sentiments: List[str] = []

            for row in all_intel:
                bucket = row.get("primary_bucket") or "unknown"
                bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
                if row.get("business_signal") == "escalation":
                    escalation_count += 1
                if row.get("business_signal") == "churn_signal":
                    churn_count += 1
                if row.get("sentiment"):
                    sentiments.append(row["sentiment"])

            # Sentiment summary
            sentiment_dist: Dict[str, int] = {}
            for s in sentiments:
                sentiment_dist[s] = sentiment_dist.get(s, 0) + 1

            # Top signals (high business_signal_score items)
            high_signal = [
                r for r in all_intel
                if (r.get("business_signal_score") or 0) >= 0.7
            ]

            return {
                "total_analyzed": len(all_intel),
                "bucket_distribution": bucket_counts,
                "sentiment_distribution": sentiment_dist,
                "escalation_count": escalation_count,
                "churn_risk_count": churn_count,
                "high_signal_count": len(high_signal),
            }

        except Exception as e:
            logger.warning(f"Failed to get AI signals for {company_id}: {e}")
            return {"total_analyzed": 0, "bucket_distribution": {}, "top_signals": []}

    def _get_key_contacts(self, company_id: str) -> List[Dict[str, Any]]:
        """Get key contacts for a company with their engagement scores."""
        try:
            resp = self._execute_with_retry(
                self.client.table("customer_contacts")
                .select("id,first_name,last_name,email_address,functional_role,engagement_score,total_emails_sent,total_emails_received")
                .eq("customer_company_id", company_id)
                .order("engagement_score", desc=True)
                .range(0, 9)
            )
            contacts = resp.data or []
            return [
                {
                    "id": c.get("id"),
                    "name": f"{c.get('first_name', '')} {c.get('last_name', '')}".strip() or None,
                    "email": c.get("email_address"),
                    "role": c.get("functional_role"),
                    "engagement_score": c.get("engagement_score"),
                    "email_count": (c.get("total_emails_sent") or 0) + (c.get("total_emails_received") or 0),
                }
                for c in contacts
            ]
        except Exception as e:
            logger.warning(f"Failed to get key contacts for {company_id}: {e}")
            return []

    def _get_qb_financial_summary(self, company_id: str) -> Dict[str, Any]:
        """Get Quickbase financial data from customer_companies and qb_quotes."""
        try:
            # QB fields on the company row
            resp = self._execute_with_retry(
                self.client.table("customer_companies")
                .select(
                    "qb_total_revenue,qb_invoiced_ty,qb_invoiced_ly,"
                    "qb_growth_90d,qb_days_since_last_invoice"
                )
                .eq("id", company_id)
                .range(0, 0)
            )
            company = (resp.data or [{}])[0] if resp.data else {}

            # Open quotes for this company
            quotes_resp = self._execute_with_retry(
                self.client.table("qb_quotes")
                .select("id,quote_no,sell_ex_tax,date_accepted")
                .eq("matched_company_id", company_id)
                .range(0, 99)
            )
            quotes = quotes_resp.data or []

            # Not accepted = still open/pending
            open_quotes = [q for q in quotes if q.get("date_accepted") is None]
            open_quotes_total = sum(q.get("sell_ex_tax") or 0 for q in open_quotes)

            return {
                "total_revenue": company.get("qb_total_revenue"),
                "invoiced_ty": company.get("qb_invoiced_ty"),
                "invoiced_ly": company.get("qb_invoiced_ly"),
                "growth_90d": company.get("qb_growth_90d"),
                "days_since_last_invoice": company.get("qb_days_since_last_invoice"),
                "open_quotes_count": len(open_quotes),
                "open_quotes_total": open_quotes_total,
            }

        except Exception as e:
            logger.warning(f"Failed to get QB financial summary for {company_id}: {e}")
            return {}

    def _get_capability_profile(self, company_id: str) -> Dict[str, Any]:
        """Aggregate QB capability/process/embellishment data from two sources:

        1. qb_operations — per-operation tags (granular order history)
        2. qb_unique_emails — QB-maintained rollups per email/customer (authoritative summary)
        """
        try:
            # ── Source 1: Operations-based tags (order history) ──
            cap_counts: dict = {}
            process_set: set = set()
            offset = 0
            while True:
                resp = self._execute_with_retry(
                    self.client.table("qb_operations")
                    .select("qb_capability_tag, qb_process_tag")
                    .eq("client_id", self.client_id)
                    .eq("matched_company_id", company_id)
                    .not_.is_("qb_capability_tag", "null")
                    .range(offset, offset + 999)
                )
                rows = resp.data or []
                for r in rows:
                    cap = (r.get("qb_capability_tag") or "").strip()
                    if cap:
                        cap_counts[cap] = cap_counts.get(cap, 0) + 1
                    proc = (r.get("qb_process_tag") or "").strip()
                    if proc:
                        process_set.add(proc)
                if len(rows) == 0:
                    break
                offset += len(rows)

            primary = sorted(cap_counts, key=lambda k: -cap_counts[k])

            # ── Source 2: QB Unique Emails rollup (QB-maintained summary) ──
            # Get the QB customer ID for this company
            qb_capabilities = set()
            qb_processes = set()
            qb_embellishments = set()
            try:
                # FRAGILE (mixed-space ID): customer_companies.qb_customer_id may hold a
                # customer_key_id OR a qb_record_id depending on which path wrote it. This
                # join assumes record-id space; a row stamped in key-id space resolves to
                # nothing here. Canonical, name-aware resolution is resolve_qb() in
                # scripts/db/merge_duplicate_companies.py — the standing rule until Option A
                # (normalize-on-write to customer_key_id) lands.
                # Translate qb_record_id → customer_key_id (field 92) for unique email lookup
                company_resp = self._execute_with_retry(
                    self.client.table("customer_companies")
                    .select("qb_customer_id")
                    .eq("id", company_id)
                    .limit(1)
                )
                qb_record_id = (company_resp.data[0].get("qb_customer_id") or "") if company_resp.data else ""
                qb_key_id = ""
                if qb_record_id:
                    key_resp = self._execute_with_retry(
                        self.client.table("qb_customers")
                        .select("customer_key_id")
                        .eq("client_id", self.client_id)
                        .eq("qb_record_id", qb_record_id)
                        .limit(1)
                    )
                    qb_key_id = (key_resp.data[0].get("customer_key_id") or "") if key_resp.data else ""
                    if not qb_key_id:
                        logger.warning(
                            "qb_customer_id=%s on company %s did not resolve to a "
                            "qb_customers row via qb_record_id space (mixed key_id/record_id "
                            "field; see resolve_qb in scripts/db/merge_duplicate_companies.py). "
                            "QB tag enrichment skipped.", qb_record_id, company_id)

                if qb_key_id:
                    ue_resp = self._execute_with_retry(
                        self.client.table("qb_unique_emails")
                        .select("capabilities_used, processes_used, embellishments_used")
                        .eq("client_id", self.client_id)
                        .eq("qb_customer_id", qb_key_id)
                        .eq("hide", False)
                    )
                    for r in (ue_resp.data or []):
                        for val in (r.get("capabilities_used") or "").split("|"):
                            val = val.strip()
                            if val:
                                qb_capabilities.add(val)
                        for val in (r.get("processes_used") or "").split("|"):
                            val = val.strip()
                            if val:
                                qb_processes.add(val)
                        for val in (r.get("embellishments_used") or "").split("|"):
                            val = val.strip()
                            if val:
                                qb_embellishments.add(val)
            except Exception as e:
                logger.debug(f"QB unique email capability lookup skipped: {e}")

            return {
                "primary_capabilities": primary[:5],
                "capability_counts": cap_counts,
                "process_types": sorted(process_set),
                "qb_capabilities": sorted(qb_capabilities),
                "qb_processes": sorted(qb_processes),
                "qb_embellishments": sorted(qb_embellishments),
            }
        except Exception as e:
            logger.warning(f"Failed to get capability profile for {company_id}: {e}")
            return {}

    def _compute_trend(self, history: List[Dict]) -> str:
        """Compute engagement trend from score history: improving / declining / stable."""
        if len(history) < ENGAGEMENT_TREND_WINDOW:
            return "insufficient_data"

        scores = [h.get("engagement_score") or 0 for h in history]

        # Compare average of first half vs second half
        mid = len(scores) // 2
        first_half_avg = sum(scores[:mid]) / mid if mid > 0 else 0
        second_half_avg = sum(scores[mid:]) / (len(scores) - mid) if (len(scores) - mid) > 0 else 0

        if second_half_avg == 0 and first_half_avg == 0:
            return "stable"

        # Use a 10% threshold to determine meaningful change
        if first_half_avg > 0:
            change_pct = (second_half_avg - first_half_avg) / first_half_avg
        else:
            change_pct = 1.0 if second_half_avg > 0 else 0.0

        if change_pct > 0.10:
            return "improving"
        elif change_pct < -0.10:
            return "declining"
        else:
            return "stable"

    # ------------------------------------------------------------------
    # AM identity resolution: mailbox → user
    # ------------------------------------------------------------------

    def _get_primary_am(self, company_id: str, existing_mailbox_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Resolve the AM for a company via the mailbox that has the most email activity.
        Falls back to existing_mailbox_id if provided.
        Returns {mailbox_id, user_id, am_name} (all may be None if not found).
        """
        try:
            mailbox_id = existing_mailbox_id

            if not mailbox_id:
                # Find the mailbox with the most emails to/from this company
                resp = self._execute_with_retry(
                    self.client.table("emails")
                    .select("mailbox_id")
                    .eq("customer_company_id", company_id)
                    .range(0, 499)
                )
                emails = resp.data or []
                if not emails:
                    return {}
                # Count by mailbox
                counts: Dict[str, int] = {}
                for e in emails:
                    mid = e.get("mailbox_id")
                    if mid:
                        counts[mid] = counts.get(mid, 0) + 1
                if not counts:
                    return {}
                mailbox_id = max(counts, key=lambda k: counts[k])

            # Resolve mailbox → user_id
            mb_resp = self._execute_with_retry(
                self.client.table("mailboxes")
                .select("id,user_id,name")
                .eq("id", mailbox_id)
                .range(0, 0)
            )
            mb_rows = mb_resp.data or []
            if not mb_rows:
                return {"mailbox_id": mailbox_id}

            mb = mb_rows[0]
            user_id = mb.get("user_id")
            am_name = None

            # Resolve user_id → name from user_profiles
            if user_id:
                up_resp = self._execute_with_retry(
                    self.client.table("user_profiles")
                    .select("name")
                    .eq("id", user_id)
                    .range(0, 0)
                )
                up_rows = up_resp.data or []
                if up_rows:
                    am_name = up_rows[0].get("name")

            return {
                "mailbox_id": mailbox_id,
                "user_id": user_id,
                "am_name": am_name,
            }

        except Exception as e:
            logger.warning(f"Failed to resolve AM for company {company_id}: {e}")
            return {}

    # ------------------------------------------------------------------
    # AM performance helpers
    # ------------------------------------------------------------------

    def _get_revenue_by_am(self, period_start: str, period_end: str) -> Dict[str, float]:
        """Sum revenue from qb_sales_line_items grouped by job_am_name."""
        try:
            all_rows = []
            offset = 0
            while True:
                resp = self._execute_with_retry(
                    self.client.table("qb_sales_line_items")
                    .select("job_am_name,total")
                    .eq("client_id", self.client_id)
                    .gte("inv_date", period_start)
                    .lte("inv_date", period_end)
                    .range(offset, offset + 499)
                )
                batch = resp.data or []
                if len(batch) == 0:
                    break
                all_rows.extend(batch)
                offset += len(batch)

            revenue_by_am: Dict[str, float] = {}
            for row in all_rows:
                am = row.get("job_am_name") or ""
                amt = row.get("total") or 0
                revenue_by_am[am] = revenue_by_am.get(am, 0) + amt

            return revenue_by_am

        except Exception as e:
            logger.warning(f"Failed to get revenue by AM: {e}")
            return {}

    def _get_quote_stats_by_am(self, period_start: str, period_end: str) -> Dict[str, Dict[str, int]]:
        """Get quote counts (total + won) from qb_quotes grouped by AM."""
        try:
            all_rows = []
            offset = 0
            while True:
                resp = self._execute_with_retry(
                    self.client.table("qb_quotes")
                    .select("account_manager,date_accepted")
                    .eq("client_id", self.client_id)
                    .gte("date_created", period_start)
                    .lte("date_created", period_end)
                    .range(offset, offset + 499)
                )
                batch = resp.data or []
                if len(batch) == 0:
                    break
                all_rows.extend(batch)
                offset += len(batch)

            stats: Dict[str, Dict[str, int]] = {}
            for row in all_rows:
                am = row.get("account_manager") or ""
                if am not in stats:
                    stats[am] = {"total": 0, "won": 0}
                stats[am]["total"] += 1
                if row.get("date_accepted") is not None:
                    stats[am]["won"] += 1

            return stats

        except Exception as e:
            logger.warning(f"Failed to get quote stats by AM: {e}")
            return {}

    def _get_response_times_by_am(self, period_start: str, period_end: str) -> Dict[str, Dict[str, float]]:
        """Get avg/median response times grouped by AM from email_response_metrics + company AM."""
        try:
            # Get companies with their AMs
            company_resp = self._execute_with_retry(
                self.client.table("customer_companies")
                .select("id,qb_account_manager")
                .eq("client_id", self.client_id)
                .range(0, 999)
            )
            companies = company_resp.data or []
            am_by_company: Dict[str, str] = {}
            for c in companies:
                if c.get("qb_account_manager"):
                    am_by_company[c["id"]] = c["qb_account_manager"]

            if not am_by_company:
                return {}

            # Get contacts for these companies
            company_ids = list(am_by_company.keys())
            contact_to_am: Dict[str, str] = {}
            for i in range(0, len(company_ids), 500):
                chunk = company_ids[i:i + 500]
                resp = self._execute_with_retry(
                    self.client.table("customer_contacts")
                    .select("id,customer_company_id")
                    .in_("customer_company_id", chunk)
                    .range(0, 999)
                )
                for contact in (resp.data or []):
                    cid = contact.get("customer_company_id")
                    if cid in am_by_company:
                        contact_to_am[contact["id"]] = am_by_company[cid]

            if not contact_to_am:
                return {}

            # Fetch response metrics
            contact_ids = list(contact_to_am.keys())
            all_metrics = []
            for i in range(0, len(contact_ids), 500):
                chunk = contact_ids[i:i + 500]
                resp = self._execute_with_retry(
                    self.client.table("email_response_metrics")
                    .select("responder_contact_id,response_time_seconds")
                    .in_("responder_contact_id", chunk)
                    .gte("created_at", period_start)
                    .lte("created_at", period_end)
                    .range(0, 999)
                )
                all_metrics.extend(resp.data or [])

            # Group by AM
            times_by_am: Dict[str, List[float]] = {}
            for m in all_metrics:
                cid = m.get("responder_contact_id")
                rt = m.get("response_time_seconds")
                if cid and rt is not None and cid in contact_to_am:
                    am = contact_to_am[cid]
                    if am not in times_by_am:
                        times_by_am[am] = []
                    times_by_am[am].append(rt)

            # Calculate avg and median
            result: Dict[str, Dict[str, float]] = {}
            for am, times in times_by_am.items():
                if not times:
                    continue
                avg_hours = round(sum(times) / len(times) / 3600, 2)
                sorted_times = sorted(times)
                mid = len(sorted_times) // 2
                if len(sorted_times) % 2 == 0:
                    median_s = (sorted_times[mid - 1] + sorted_times[mid]) / 2
                else:
                    median_s = sorted_times[mid]
                median_hours = round(median_s / 3600, 2)

                result[am] = {"avg_hours": avg_hours, "median_hours": median_hours}

            return result

        except Exception as e:
            logger.warning(f"Failed to get response times by AM: {e}")
            return {}
