"""
AM Efficiency Analyzer

Computes per-AM (Account Manager) KPIs from email + QB data.
AM identity is derived from: mailboxes.user_id → user_profiles (no QB name matching).

KPIs per AM:
  - avg_response_time_hours          Raw average reply time
  - avg_bh_response_time_hours       Business-hours-only reply time (excludes overnight/weekend gaps)
  - response_rate_pct                % of inbound emails that got a reply
  - after_hours_email_pct            % of outbound emails sent outside business hours
  - emails_sent / emails_received    Volume
  - revenue_attributed               QB jobs total linked to companies in this AM's mailboxes
  - quotes_sent / quote_conv_rate    QB quotes attributed to AM's companies

Business hours: 09:00–17:00 Mon–Fri in the client's configured timezone (default AEST).
"""

import logging
from datetime import datetime, date, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Business hours window
BH_START_HOUR = 9   # 9 AM
BH_END_HOUR = 17    # 5 PM
BH_WEEKDAYS = {0, 1, 2, 3, 4}  # Mon–Fri


def _business_hours_delta(start_utc: datetime, end_utc: datetime, tz: ZoneInfo) -> float:
    """
    Return the number of seconds that fall inside business hours between two UTC datetimes.
    Used to compute response time excluding overnight / weekend gaps.
    """
    if end_utc <= start_utc:
        return 0.0

    total_bh_seconds = 0.0
    cursor = start_utc.astimezone(tz)
    end_local = end_utc.astimezone(tz)

    while cursor < end_local:
        # Advance to start of business hours if before BH_START
        if cursor.weekday() not in BH_WEEKDAYS:
            # Skip to next Monday
            days_ahead = 7 - cursor.weekday()
            cursor = cursor.replace(hour=BH_START_HOUR, minute=0, second=0, microsecond=0) + timedelta(days=days_ahead)
            continue

        bh_start_today = cursor.replace(hour=BH_START_HOUR, minute=0, second=0, microsecond=0)
        bh_end_today = cursor.replace(hour=BH_END_HOUR, minute=0, second=0, microsecond=0)

        if cursor < bh_start_today:
            cursor = bh_start_today
            continue
        if cursor >= bh_end_today:
            # Past business hours today — jump to next business day
            cursor = bh_start_today + timedelta(days=1)
            while cursor.weekday() not in BH_WEEKDAYS:
                cursor += timedelta(days=1)
            continue

        # We are inside business hours — compute overlap with end_local
        segment_end = min(bh_end_today, end_local)
        total_bh_seconds += (segment_end - cursor).total_seconds()
        cursor = segment_end

    return total_bh_seconds


def _is_business_hours(dt_utc: datetime, tz: ZoneInfo) -> bool:
    local = dt_utc.astimezone(tz)
    return local.weekday() in BH_WEEKDAYS and BH_START_HOUR <= local.hour < BH_END_HOUR


class AMEfficiencyAnalyzer:
    """
    Computes AM efficiency KPIs for all AMs belonging to a client.
    Designed to be called from StrategicDigestPipeline / StrategicContextBuilder.
    """

    def __init__(self, supabase_client, client_id: str):
        self.supabase = supabase_client
        self.client_id = client_id

    def _execute(self, query):
        resp = query.execute()
        return resp.data or []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute_all(self, period_start: date, period_end: date) -> list[dict]:
        """
        Returns a list of AM efficiency records, one per AM (user) found
        via mailboxes belonging to this client.
        """
        timezone = self._get_client_timezone()
        tz = ZoneInfo(timezone)

        mailboxes = self._get_client_mailboxes()
        if not mailboxes:
            return []

        results = []
        for mb in mailboxes:
            mailbox_id = mb["id"]
            user_id = mb.get("user_id")
            am_name = mb.get("_user_name") or mb.get("name") or mailbox_id

            kpis = self._compute_mailbox_kpis(mailbox_id, period_start, period_end, tz)
            kpis.update({
                "mailbox_id": mailbox_id,
                "user_id": user_id,
                "am_name": am_name,
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
            })
            results.append(kpis)

        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_client_timezone(self) -> str:
        try:
            rows = self._execute(
                self.supabase.table("clients")
                .select("timezone")
                .eq("id", self.client_id)
                .limit(1)
            )
            return (rows[0].get("timezone") or "Australia/Sydney") if rows else "Australia/Sydney"
        except Exception:
            return "Australia/Sydney"

    def _get_client_mailboxes(self) -> list[dict]:
        """Return mailboxes with joined user name."""
        try:
            rows = self._execute(
                self.supabase.table("mailboxes")
                .select("id,name,user_id,user_profiles(name)")
                .eq("client_id", self.client_id)
                .eq("is_active", True)
            )
            result = []
            for r in rows:
                user_profile = r.get("user_profiles") or {}
                r["_user_name"] = user_profile.get("name") if isinstance(user_profile, dict) else None
                result.append(r)
            return result
        except Exception as e:
            logger.warning(f"Failed to get mailboxes for client {self.client_id}: {e}")
            return []

    def _compute_mailbox_kpis(
        self,
        mailbox_id: str,
        period_start: date,
        period_end: date,
        tz: ZoneInfo,
    ) -> dict:
        start_iso = period_start.isoformat()
        end_iso = period_end.isoformat()

        kpis = {
            "emails_sent": 0,
            "emails_received": 0,
            "avg_response_time_hours": None,
            "avg_bh_response_time_hours": None,
            "response_rate_pct": None,
            "after_hours_email_pct": None,
            "revenue_attributed": 0.0,
            "quotes_sent": 0,
            "quotes_accepted": 0,
            "quote_conversion_rate": None,
        }

        # --- Email volumes ---
        try:
            emails = self._execute(
                self.supabase.table("emails")
                .select("id,direction,sent_date")
                .eq("mailbox_id", mailbox_id)
                .gte("sent_date", start_iso)
                .lte("sent_date", end_iso)
            )
            sent = [e for e in emails if e.get("direction") == "outbound"]
            received = [e for e in emails if e.get("direction") == "inbound"]
            kpis["emails_sent"] = len(sent)
            kpis["emails_received"] = len(received)

            # After-hours outbound
            if sent:
                after_hours = sum(
                    1 for e in sent
                    if e.get("sent_date") and not _is_business_hours(
                        datetime.fromisoformat(e["sent_date"].replace("Z", "+00:00")), tz
                    )
                )
                kpis["after_hours_email_pct"] = round(after_hours / len(sent) * 100, 1)
        except Exception as e:
            logger.warning(f"Email volume query failed for mailbox {mailbox_id}: {e}")

        # --- Response times ---
        try:
            metrics = self._execute(
                self.supabase.table("email_response_metrics")
                .select("response_time_seconds,created_at")
                .eq("mailbox_id", mailbox_id)
                .gte("created_at", start_iso)
                .lte("created_at", end_iso)
                .not_.is_("response_time_seconds", "null")
            )
            if metrics:
                raw_times_s = [m["response_time_seconds"] for m in metrics if m.get("response_time_seconds")]
                if raw_times_s:
                    kpis["avg_response_time_hours"] = round(sum(raw_times_s) / len(raw_times_s) / 3600, 2)

            # Business-hours response times require start + end timestamps
            # Use email_response_metrics.created_at (when response was recorded) as end point
            # and estimated start from response_time_seconds subtracted from created_at
            bh_times = []
            for m in metrics:
                rts = m.get("response_time_seconds")
                created_str = m.get("created_at")
                if not rts or not created_str:
                    continue
                try:
                    end_utc = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                    start_utc = end_utc - timedelta(seconds=rts)
                    bh_secs = _business_hours_delta(start_utc, end_utc, tz)
                    bh_times.append(bh_secs)
                except Exception:
                    pass
            if bh_times:
                kpis["avg_bh_response_time_hours"] = round(sum(bh_times) / len(bh_times) / 3600, 2)
        except Exception as e:
            logger.warning(f"Response time query failed for mailbox {mailbox_id}: {e}")

        # --- Response rate ---
        try:
            # response rate = rows in email_response_metrics / inbound emails
            if kpis["emails_received"] > 0:
                responded = self._execute(
                    self.supabase.table("email_response_metrics")
                    .select("id", count="exact")
                    .eq("mailbox_id", mailbox_id)
                    .gte("created_at", start_iso)
                    .lte("created_at", end_iso)
                )
                # Supabase count returns in .count attr — use len of rows as proxy
                resp_count = len(responded)
                kpis["response_rate_pct"] = round(
                    min(resp_count, kpis["emails_received"]) / kpis["emails_received"] * 100, 1
                )
        except Exception as e:
            logger.warning(f"Response rate query failed for mailbox {mailbox_id}: {e}")

        # --- QB revenue + quotes attributed to companies in this mailbox ---
        try:
            # Derive company IDs from emails in this mailbox (no direct FK exists yet)
            email_rows = self._execute(
                self.supabase.table("emails")
                .select("customer_company_id")
                .eq("mailbox_id", mailbox_id)
                .not_.is_("customer_company_id", "null")
                .range(0, 999)
            )
            company_ids = list({r["customer_company_id"] for r in email_rows if r.get("customer_company_id")})

            if company_ids:
                # Revenue from QB sales line items
                batch_ids = company_ids[:500]
                sales = self._execute(
                    self.supabase.table("qb_sales_line_items")
                    .select("total")
                    .in_("matched_company_id", batch_ids)
                    .gte("inv_date", start_iso)
                    .lte("inv_date", end_iso)
                )
                kpis["revenue_attributed"] = round(
                    sum(float(s.get("total") or 0) for s in sales), 2
                )

                # Quotes
                quotes = self._execute(
                    self.supabase.table("qb_quotes")
                    .select("date_accepted,date_created")
                    .in_("matched_company_id", batch_ids)
                    .gte("date_created", start_iso)
                    .lte("date_created", end_iso)
                )
                kpis["quotes_sent"] = len(quotes)
                kpis["quotes_accepted"] = sum(1 for q in quotes if q.get("date_accepted"))
                if kpis["quotes_sent"] > 0:
                    kpis["quote_conversion_rate"] = round(
                        kpis["quotes_accepted"] / kpis["quotes_sent"] * 100, 1
                    )
        except Exception as e:
            logger.warning(f"QB revenue/quotes query failed for mailbox {mailbox_id}: {e}")

        return kpis

    def save_snapshots(self, snapshots: list[dict]) -> None:
        """Upsert computed KPI snapshots to am_performance_snapshots."""
        for snap in snapshots:
            try:
                self.supabase.table("am_performance_snapshots").upsert(
                    {
                        "client_id": self.client_id,
                        "account_manager": snap["am_name"],
                        "user_id": snap.get("user_id"),
                        "mailbox_ids": [snap["mailbox_id"]],
                        "period_start": snap["period_start"],
                        "period_end": snap["period_end"],
                        "emails_sent": snap["emails_sent"],
                        "emails_received": snap["emails_received"],
                        "avg_response_time_hours": snap.get("avg_response_time_hours"),
                        "avg_bh_response_time_hours": snap.get("avg_bh_response_time_hours"),
                        "response_rate": snap.get("response_rate_pct"),
                        "after_hours_email_pct": snap.get("after_hours_email_pct"),
                        "revenue_attributed": snap.get("revenue_attributed", 0),
                        "quotes_sent": snap.get("quotes_sent", 0),
                        "quotes_accepted": snap.get("quotes_accepted", 0),
                        "quote_conversion_rate": snap.get("quote_conversion_rate"),
                    },
                    on_conflict="client_id,account_manager,period_start,period_end",
                ).execute()
            except Exception as e:
                logger.warning(f"Failed to save AM snapshot for {snap.get('am_name')}: {e}")
