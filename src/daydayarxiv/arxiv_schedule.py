"""Utilities for mapping UTC dates to arXiv announcement submission windows."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

EASTERN_TZ = ZoneInfo("America/New_York")
CUTOFF_TIME_ET = time(14, 0)
ANNOUNCEMENT_TIME_ET = time(20, 0)


def _announcement_et_date(utc_date: date) -> date:
    """arXiv announcements at 20:00 ET map to the next UTC date."""
    return utc_date - timedelta(days=1)


def submission_window_et_for_announcement_date(
    announcement_date: date,
) -> tuple[datetime, datetime] | None:
    """Return ET submission window for a given announcement date.

    The window is defined by arXiv's 14:00 ET cutoff and weekday schedule.
    Returns None when no announcement occurs on the given ET date (Fri/Sat).
    """
    weekday = announcement_date.weekday()  # Monday=0
    if weekday in (4, 5):  # Friday/Saturday: no announcements
        return None

    if weekday == 6:  # Sunday announcement: Thu 14:00 -> Fri 14:00
        start_date = announcement_date - timedelta(days=3)
        end_date = announcement_date - timedelta(days=2)
    elif weekday == 0:  # Monday announcement: Fri 14:00 -> Mon 14:00
        start_date = announcement_date - timedelta(days=3)
        end_date = announcement_date
    else:  # Tue/Wed/Thu announcements: previous day 14:00 -> same day 14:00
        start_date = announcement_date - timedelta(days=1)
        end_date = announcement_date

    start_et = datetime.combine(start_date, CUTOFF_TIME_ET, tzinfo=EASTERN_TZ)
    end_et = datetime.combine(end_date, CUTOFF_TIME_ET, tzinfo=EASTERN_TZ)
    return start_et, end_et


def submission_window_utc_for_utc_date(utc_date: date) -> tuple[datetime, datetime] | None:
    """Return UTC submission window for a given UTC announcement date."""
    announcement_date = _announcement_et_date(utc_date)
    window = submission_window_et_for_announcement_date(announcement_date)
    if window is None:
        return None
    start_et, end_et = window
    return start_et.astimezone(UTC), end_et.astimezone(UTC)


def announcement_utc_datetime_for_utc_date(utc_date: date) -> datetime | None:
    """Return the UTC datetime when the announcement should appear."""
    announcement_date = _announcement_et_date(utc_date)
    if announcement_date.weekday() in (4, 5):
        return None
    announcement_et = datetime.combine(announcement_date, ANNOUNCEMENT_TIME_ET, tzinfo=EASTERN_TZ)
    return announcement_et.astimezone(UTC)


def latest_announcement_utc_date(now: datetime | None = None) -> date:
    """Return the latest UTC announcement date whose release time has passed."""
    current = now or datetime.now(UTC)
    candidate = current.date()
    while True:
        window = submission_window_utc_for_utc_date(candidate)
        if window is None:
            candidate -= timedelta(days=1)
            continue
        release_time = announcement_utc_datetime_for_utc_date(candidate)
        if release_time and release_time <= current:
            return candidate
        candidate -= timedelta(days=1)


def format_arxiv_query_timestamp(dt: datetime) -> str:
    """Format UTC datetime for arXiv query strings (YYYYMMDDHHMMSS)."""
    return dt.astimezone(UTC).strftime("%Y%m%d%H%M%S")
