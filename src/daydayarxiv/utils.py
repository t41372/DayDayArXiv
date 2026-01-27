"""Utility helpers for date handling and parsing."""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from daydayarxiv.arxiv_schedule import latest_announcement_utc_date

SUPPORTED_DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y%m%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d-%m-%Y",
    "%m-%d-%Y",
    "%Y/%m/%d",
    "%b %d %Y",
    "%d %b %Y",
    "%B %d %Y",
    "%d %B %Y",
)


class DateParseError(ValueError):
    """Raised when a date string cannot be parsed."""


def normalize_date_format(date_str: str) -> str:
    """Normalize date strings into YYYY-MM-DD.

    Args:
        date_str: Input date string.

    Returns:
        Normalized date string.

    Raises:
        DateParseError: If the date cannot be parsed.
    """
    raw = date_str.strip()

    match = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$", raw)
    if match:
        year, month, day = match.groups()
        normalized = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        try:
            datetime.strptime(normalized, "%Y-%m-%d")
        except ValueError as exc:
            raise DateParseError(
                f"Date string '{date_str}' does not match supported formats"
            ) from exc
        return normalized

    for fmt in SUPPORTED_DATE_FORMATS:
        try:
            parsed = datetime.strptime(raw, fmt)
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue

    raise DateParseError(f"Date string '{date_str}' does not match supported formats")


def build_date_range(start: str, end: str) -> list[str]:
    """Build a list of normalized dates between start and end (inclusive)."""
    start_date = datetime.strptime(normalize_date_format(start), "%Y-%m-%d")
    end_date = datetime.strptime(normalize_date_format(end), "%Y-%m-%d")
    if end_date < start_date:
        raise DateParseError("End date must be after start date")

    dates: list[str] = []
    cursor = start_date
    while cursor <= end_date:
        dates.append(cursor.strftime("%Y-%m-%d"))
        cursor += timedelta(days=1)
    return dates


def default_date_list() -> list[str]:
    """Default to the latest UTC announcement date."""
    default_date = latest_announcement_utc_date(datetime.now(UTC))
    return [default_date.strftime("%Y-%m-%d")]


def ensure_unique_dates(dates: Iterable[str]) -> list[str]:
    """Return dates in order with duplicates removed."""
    seen: set[str] = set()
    result: list[str] = []
    for date in dates:
        if date not in seen:
            seen.add(date)
            result.append(date)
    return result
