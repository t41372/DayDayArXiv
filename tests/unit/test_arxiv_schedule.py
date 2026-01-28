from datetime import UTC, date, datetime

from daydayarxiv.arxiv_schedule import (
    announcement_utc_datetime_for_utc_date,
    format_arxiv_query_timestamp,
    latest_announcement_utc_date,
    submission_window_utc_for_utc_date,
)


def test_submission_window_utc_weekday() -> None:
    window = submission_window_utc_for_utc_date(date(2026, 1, 15))
    assert window == (
        datetime(2026, 1, 13, 19, 0, tzinfo=UTC),
        datetime(2026, 1, 14, 19, 0, tzinfo=UTC),
    )


def test_submission_window_utc_sunday_announcement() -> None:
    window = submission_window_utc_for_utc_date(date(2026, 1, 19))
    assert window == (
        datetime(2026, 1, 15, 19, 0, tzinfo=UTC),
        datetime(2026, 1, 16, 19, 0, tzinfo=UTC),
    )


def test_submission_window_utc_monday_announcement() -> None:
    window = submission_window_utc_for_utc_date(date(2026, 1, 13))
    assert window == (
        datetime(2026, 1, 9, 19, 0, tzinfo=UTC),
        datetime(2026, 1, 12, 19, 0, tzinfo=UTC),
    )


def test_submission_window_utc_weekend_none() -> None:
    assert submission_window_utc_for_utc_date(date(2026, 1, 17)) is None


def test_announcement_utc_datetime() -> None:
    announcement = announcement_utc_datetime_for_utc_date(date(2026, 1, 15))
    assert announcement == datetime(2026, 1, 15, 1, 0, tzinfo=UTC)
    assert announcement_utc_datetime_for_utc_date(date(2026, 1, 17)) is None


def test_latest_announcement_utc_date() -> None:
    assert latest_announcement_utc_date(datetime(2026, 1, 15, 2, 0, tzinfo=UTC)) == date(
        2026, 1, 15
    )
    assert latest_announcement_utc_date(datetime(2026, 1, 15, 0, 30, tzinfo=UTC)) == date(
        2026, 1, 14
    )
    assert latest_announcement_utc_date(datetime(2026, 1, 17, 12, 0, tzinfo=UTC)) == date(
        2026, 1, 16
    )


def test_format_arxiv_query_timestamp() -> None:
    stamp = format_arxiv_query_timestamp(datetime(2026, 1, 15, 1, 2, 3, tzinfo=UTC))
    assert stamp == "20260115010203"
