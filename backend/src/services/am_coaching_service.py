"""
AM Communication-Quality Coaching Service — Tier-A STRUCTURAL layer (task 15.2)

Computes the four research-grounded Tier-A structural metrics per AM, SELF-REFERENTIALLY
(each AM vs their own baseline over time) — NOT a cross-AM ranking. The cross-AM /
management comparison is task 15.5 and is deliberately not built here.

Design: docs/design/AM_QUALITY_LAYER_DESIGN.md. The four metrics:
  - exchange_velocity     emails exchanged per active thread + per active week (Gong: strongest
                          close predictor)
  - responsiveness        median reply latency to inbound (our outbound replies)
  - multithreading        distinct contacts engaged per company (Gong: critical to deal success)
  - follow_up_persistence re-touch after the customer goes silent vs let the thread go cold

The heavy aggregation runs server-side in the am_structural_metrics() SQL function (migration
126); this service orchestrates the windows, computes self-referential trend, and applies the
honesty guards:
  * trailing-12-month headline window (where 15.1 found volume is even, CV 0.41-0.62) — not all-history
  * STALENESS flag per AM: a stalled sync (Ehab ~2026-05-21, Kenneth ~2026-05-16 at 15.1) must read
    as "data current as of {date} — may be stale", NOT as the AM going quiet. When stale, the
    recent-window trend is marked unreliable rather than shown as a behavioural decline.
  * every metric carries its population/coverage so thin coverage is visible, not hidden.
  * business-hours latency: the stored business_hours_response_time_seconds was ~85% zero (a
    timezone artifact — the backfill evaluated 9-18 in UTC, not Australia/Sydney). Recomputed
    2026-06-15 for Carbon8 (scripts/db/_recompute_bh_response_time.py); positive-bh share is now
    ~94% and business_hours_reliable flips true for the live AMs. The data-driven reliability
    gate below is RETAINED as a guard: it self-heals and re-flags degradation if the artifact
    ever recurs. The source was also fixed — response_time_tracker now resolves the BH zone from
    clients.timezone, so new syncs compute business-hours latency correctly (no regression).

Mary Serratore-Howe / Peter Musarra have NO mailbox -> email metrics are absent by construction;
the service returns a clear no-mailbox state (email_coachable=False), never zeros.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# A mailbox with no email in this many days is treated as a likely STALLED SYNC, not a quiet AM.
# 15.1: Nic/Linda current (0d), Ehab ~25d, Kenneth ~30d -> 14 flags the two stale boxes, not the live ones.
STALE_DAYS = 14

HEADLINE_DAYS = 365   # trailing-12-month headline window (even volume per 15.1)
TREND_DAYS = 90       # current vs prior 90-day windows for self-referential trend

# bh latency considered reliable only if at least this share of replies have a positive
# business-hours value. Post-recompute (2026-06-15) the live AMs sit at ~89-99%; this gate is
# kept as a self-healing guard against a future sync re-introducing the UTC tz artifact.
BH_RELIABLE_MIN_FRAC = 0.5

_RESEARCH = {
    "exchange_velocity": "Gong: email velocity is the single strongest close predictor (won deals ~8.2 emails/week vs lost ~1.9).",
    "responsiveness": "Fast, business-hours response signals engagement and lifts conversion.",
    "multithreading": "Gong: engaging multiple stakeholders per account is critical to deal success.",
    "follow_up_persistence": "Consistent follow-up after silence drives conversion; letting threads go cold loses winnable deals.",
}

_POLARITY = {
    "exchange_velocity": "higher_better",
    "responsiveness": "lower_better",
    "multithreading": "higher_better",
    "follow_up_persistence": "higher_better",
}


class AMCoachingService:
    """Stateless compute service. Holds only the Supabase client."""

    def __init__(self, supabase_client):
        self.supabase = supabase_client

    # ------------------------------------------------------------------ #
    # AM resolution
    # ------------------------------------------------------------------ #
    def get_am_mailboxes(self, am_user_id: str) -> list[dict]:
        """Mailboxes owned by this AM (user). 4 target AMs have exactly one each."""
        try:
            resp = (
                self.supabase.table("mailboxes")
                .select("id, name, client_id, user_id")
                .eq("user_id", am_user_id)
                .execute()
            )
            return resp.data or []
        except Exception as e:
            logger.warning(f"get_am_mailboxes failed for {am_user_id}: {e}")
            return []

    def _get_am_profile(self, am_user_id: str) -> Optional[dict]:
        try:
            resp = (
                self.supabase.table("user_profiles")
                .select("id, name, email")
                .eq("id", am_user_id).limit(1).execute()
            )
            return resp.data[0] if resp.data else None
        except Exception as e:
            logger.warning(f"_get_am_profile failed for {am_user_id}: {e}")
            return None

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def compute_structural(self, am_user_id: str, now: Optional[datetime] = None) -> dict:
        """
        Returns the per-AM Tier-A structural object. States:
          - state="unknown_am"  : no user_profiles row and no mailbox  (endpoint -> 404)
          - state="no_mailbox"  : AM exists but has no mailbox (Mary/Peter)  -> email_coachable=False
          - state="ok"          : full structural metrics
        """
        now = now or datetime.now(timezone.utc)
        profile = self._get_am_profile(am_user_id)
        mailboxes = self.get_am_mailboxes(am_user_id)

        if not profile and not mailboxes:
            return {"state": "unknown_am", "am_id": am_user_id, "email_coachable": False,
                    "message": "No user or mailbox found for this AM id."}

        am_name = (profile or {}).get("name") or "(unknown)"

        if not mailboxes:
            return {
                "state": "no_mailbox", "am_id": am_user_id, "am_name": am_name,
                "email_coachable": False,
                "message": ("This AM has no mailbox, so email-derived communication metrics do not "
                            "exist for them. Coach via the QB-outcome track (separate), not email."),
                "framing": "self-referential structural layer (15.2); email metrics require a mailbox.",
            }

        # Primary mailbox = the one with the most all-time email (the 4 target AMs have exactly one).
        primary = self._pick_primary(mailboxes)
        client_id = primary["client_id"]
        mailbox_id = primary["id"]

        headline = self._metrics(mailbox_id, client_id, now - timedelta(days=HEADLINE_DAYS), now)
        current = self._metrics(mailbox_id, client_id, now - timedelta(days=TREND_DAYS), now)
        prior = self._metrics(mailbox_id, client_id,
                              now - timedelta(days=2 * TREND_DAYS), now - timedelta(days=TREND_DAYS))

        if headline is None:
            return {"state": "error", "am_id": am_user_id, "am_name": am_name,
                    "email_coachable": True, "message": "Metric computation failed (see logs)."}

        freshness = self._freshness(headline, now)
        reliable = not freshness["is_stale"]

        metrics = {
            "exchange_velocity": self._assemble(
                "exchange_velocity", headline, current, prior, reliable,
                primary_key="emails_per_active_week",
                coverage=self._velocity_coverage(headline)),
            "responsiveness": self._assemble(
                "responsiveness", headline, current, prior, reliable,
                primary_key="median_raw_hours",
                coverage=self._responsiveness_coverage(headline)),
            "multithreading": self._assemble(
                "multithreading", headline, current, prior, reliable,
                primary_key="avg_contacts_per_company",
                coverage={"companies": headline["multithreading"]["companies"]}),
            "follow_up_persistence": self._assemble(
                "follow_up_persistence", headline, current, prior, reliable,
                primary_key="persistence_pct",
                coverage=self._persistence_coverage(headline)),
        }

        result = {
            "state": "ok",
            "am_id": am_user_id,
            "am_name": am_name,
            "email_coachable": True,
            "mailbox": {"id": mailbox_id, "name": primary.get("name"), "client_id": client_id},
            "framing": ("Self-referential: this AM vs their own baseline over time. NOT a cross-AM "
                        "ranking (management comparison is 15.5, gated on the sync fix + Tier-B pilot)."),
            "data_freshness": freshness,
            "headline_window": {"label": "trailing_12_months",
                                "start": (now - timedelta(days=HEADLINE_DAYS)).date().isoformat(),
                                "end": now.date().isoformat()},
            "trend_windows": {"current_90d": "last 90 days", "prior_90d": "the 90 days before that"},
            "metrics": metrics,
            "windows_raw": {"headline": headline, "current_90d": current, "prior_90d": prior},
        }
        if len(mailboxes) > 1:
            result["note_multiple_mailboxes"] = (
                f"AM owns {len(mailboxes)} mailboxes; metrics shown for the primary "
                f"('{primary.get('name')}'). Multi-mailbox aggregation is a later enhancement.")
        return result

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _pick_primary(self, mailboxes: list[dict]) -> dict:
        if len(mailboxes) == 1:
            return mailboxes[0]
        best, best_n = mailboxes[0], -1
        for mb in mailboxes:
            try:
                r = (self.supabase.table("emails").select("id", count="exact")
                     .eq("mailbox_id", mb["id"]).limit(1).execute())
                n = r.count or 0
            except Exception:
                n = 0
            if n > best_n:
                best, best_n = mb, n
        return best

    def _metrics(self, mailbox_id, client_id, start: datetime, end: datetime) -> Optional[dict]:
        try:
            resp = self.supabase.rpc("am_structural_metrics", {
                "p_mailbox_id": mailbox_id,
                "p_client_id": client_id,
                "p_start": start.isoformat(),
                "p_end": end.isoformat(),
            }).execute()
            return resp.data
        except Exception as e:
            logger.error(f"am_structural_metrics RPC failed ({mailbox_id}, {start}..{end}): {e}")
            return None

    def _freshness(self, headline: dict, now: datetime) -> dict:
        rec = headline.get("recency") or {}
        days = rec.get("days_since_last_email")
        as_of = rec.get("last_email_date")
        is_stale = isinstance(days, int) and days > STALE_DAYS
        note = None
        if is_stale:
            note = (f"Data current only as of {as_of} ({days} days ago) — this mailbox's sync appears "
                    f"STALLED. Recent-window metrics are depressed by missing email, NOT by the AM "
                    f"going quiet; trend marked unreliable. Fix the sync before reading recent activity.")
        return {
            "as_of": as_of,
            "days_since_last_email": days,
            "is_stale": is_stale,
            "stale_threshold_days": STALE_DAYS,
            "total_emails_all_time": rec.get("total_emails_all_time"),
            "note": note,
        }

    def _assemble(self, metric: str, headline, current, prior, reliable, primary_key, coverage) -> dict:
        h = headline[metric]
        polarity = _POLARITY[metric]
        cur_v = (current or {}).get(metric, {}).get(primary_key) if current else None
        pri_v = (prior or {}).get(metric, {}).get(primary_key) if prior else None
        return {
            "headline": h,
            "primary_value": {"name": primary_key, "value": h.get(primary_key), "polarity": polarity},
            "trend": self._trend(cur_v, pri_v, polarity, reliable),
            "coverage": coverage,
            "research_basis": _RESEARCH[metric],
        }

    def _trend(self, cur, prior, polarity, reliable) -> dict:
        if cur is None or prior is None:
            return {"current_90d": cur, "prior_90d": prior, "direction": "unknown",
                    "interpretation": "insufficient data in one or both 90-day windows",
                    "reliable": reliable}
        delta = round(cur - prior, 2)
        pct = round(delta / prior * 100, 1) if prior else None
        if abs(delta) < 1e-9:
            direction, interp = "flat", "stable"
        else:
            direction = "up" if delta > 0 else "down"
            improving = (direction == "up") if polarity == "higher_better" else (direction == "down")
            interp = "improving" if improving else "declining"
        if not reliable:
            interp = f"{interp} — UNRELIABLE (stalled sync depresses the recent window)"
        return {"current_90d": cur, "prior_90d": prior, "change_abs": delta, "change_pct": pct,
                "direction": direction, "interpretation": interp, "reliable": reliable}

    # per-metric coverage extractors -----------------------------------------
    def _velocity_coverage(self, headline) -> dict:
        v = headline["exchange_velocity"]; vol = headline["volume"]
        threaded_pct = round(vol["threaded"] / vol["emails"] * 100, 1) if vol.get("emails") else None
        return {"threads_active": v["threads_active"], "emails": vol["emails"],
                "active_weeks": vol["active_weeks"], "threaded_pct": threaded_pct}

    def _responsiveness_coverage(self, headline) -> dict:
        r = headline["responsiveness"]
        reply_rows = r.get("reply_rows") or 0
        bh_pos = r.get("bh_positive_rows") or 0
        bh_frac = (bh_pos / reply_rows) if reply_rows else 0
        bh_reliable = bh_frac >= BH_RELIABLE_MIN_FRAC
        return {
            "reply_rows": reply_rows,
            "coverage_pct_of_inbound": r.get("coverage_pct_of_inbound"),
            "business_hours_reliable": bh_reliable,
            "bh_positive_pct": round(bh_frac * 100, 1),
            "business_hours_note": (None if bh_reliable else
                "business_hours_response_time_seconds is mostly zero (timezone artifact in the historical "
                "backfill); use median_raw_hours as the reliable figure until the column is recomputed."),
        }

    def _persistence_coverage(self, headline) -> dict:
        f = headline["follow_up_persistence"]
        judged = (f.get("re_touch") or 0) + (f.get("cold") or 0)
        return {"outbound": f.get("outbound"), "silence_points_judged": judged,
                "re_touch": f.get("re_touch"), "cold": f.get("cold"), "answered": f.get("answered")}


# ── module singleton (matches the init/get pattern used across services) ──────
_coaching_service: Optional[AMCoachingService] = None


def init_coaching_service(supabase_client) -> AMCoachingService:
    global _coaching_service
    _coaching_service = AMCoachingService(supabase_client)
    logger.info("AM coaching service initialized")
    return _coaching_service


def get_coaching_service() -> Optional[AMCoachingService]:
    return _coaching_service
