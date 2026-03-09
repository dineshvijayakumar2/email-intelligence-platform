"""
Business Hours Calculator

Computes the elapsed time between two UTC timestamps counting only the minutes
that fall within configured business hours and business days.

Algorithm:
  Walk day-by-day from start to end.  For each calendar day (in the user's
  local timezone) that is a business day, add the overlap between
  [business_start, business_end] and the [start, end] window.

Performance: O(days between start and end).  For the 7-day max response window
this is at most 7 iterations — negligible.
"""

from datetime import datetime, timedelta, timezone, time
from typing import Optional, List

from dateutil import tz as dateutil_tz


def _get_tz(tz_name: str):
    """Resolve IANA timezone name using dateutil (works on Windows without tzdata)."""
    if not tz_name or tz_name == "UTC":
        return timezone.utc
    try:
        result = dateutil_tz.gettz(tz_name)
        return result if result is not None else timezone.utc
    except Exception:
        return timezone.utc


def calculate_business_seconds(
    start_utc: datetime,
    end_utc: datetime,
    tz_name: str = "UTC",
    bh_start: int = 9,
    bh_end: int = 18,
    business_days: Optional[List[int]] = None,
) -> int:
    """
    Calculate the number of seconds between *start_utc* and *end_utc* that fall
    within business hours.

    Parameters
    ----------
    start_utc : datetime
        Start timestamp (must be UTC-aware or naive-treated-as-UTC).
    end_utc : datetime
        End timestamp.
    tz_name : str
        IANA timezone name, e.g. "Asia/Kolkata", "America/New_York".
    bh_start : int
        Business hours start (0-23), e.g. 9 for 9 AM.
    bh_end : int
        Business hours end (0-23), e.g. 18 for 6 PM.
    business_days : list[int] | None
        ISO weekdays considered business days (1=Mon .. 7=Sun).
        Defaults to [1,2,3,4,5] (Mon–Fri).

    Returns
    -------
    int
        Elapsed seconds that fall within business hours.  Always >= 0.
    """
    if business_days is None:
        business_days = [1, 2, 3, 4, 5]

    if bh_start >= bh_end:
        # Misconfigured — treat entire day as business hours
        bh_start, bh_end = 0, 24

    # Ensure UTC-aware
    if start_utc.tzinfo is None:
        start_utc = start_utc.replace(tzinfo=timezone.utc)
    if end_utc.tzinfo is None:
        end_utc = end_utc.replace(tzinfo=timezone.utc)

    if end_utc <= start_utc:
        return 0

    user_tz = _get_tz(tz_name)

    # Convert to user's local timezone
    start_local = start_utc.astimezone(user_tz)
    end_local = end_utc.astimezone(user_tz)

    total_seconds = 0
    current_date = start_local.date()
    final_date = end_local.date()

    while current_date <= final_date:
        iso_weekday = current_date.isoweekday()  # 1=Mon .. 7=Sun

        if iso_weekday in business_days:
            # Business window for this day in local timezone
            day_bh_start = datetime.combine(current_date, time(bh_start, 0)).replace(tzinfo=user_tz)
            day_bh_end = datetime.combine(current_date, time(bh_end, 0)).replace(tzinfo=user_tz)

            # Overlap of [start_local, end_local] and [day_bh_start, day_bh_end]
            overlap_start = max(start_local, day_bh_start)
            overlap_end = min(end_local, day_bh_end)

            if overlap_end > overlap_start:
                total_seconds += int((overlap_end - overlap_start).total_seconds())

        current_date += timedelta(days=1)

    return max(0, total_seconds)
