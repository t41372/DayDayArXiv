import re

import pytest

from daydayarxiv import utils


def test_normalize_date_format():
    assert utils.normalize_date_format("2025-3-1") == "2025-03-01"
    assert utils.normalize_date_format("20250301") == "2025-03-01"
    assert utils.normalize_date_format("03/01/2025") == "2025-01-03"

    with pytest.raises(utils.DateParseError):
        utils.normalize_date_format("not-a-date")
    with pytest.raises(utils.DateParseError):
        utils.normalize_date_format("2025-02-30")


def test_build_date_range():
    dates = utils.build_date_range("2025-03-01", "2025-03-03")
    assert dates == ["2025-03-01", "2025-03-02", "2025-03-03"]

    with pytest.raises(utils.DateParseError):
        utils.build_date_range("2025-03-05", "2025-03-01")


def test_default_date_list_format():
    dates = utils.default_date_list()
    assert len(dates) == 1
    assert re.match(r"\d{4}-\d{2}-\d{2}", dates[0])


def test_ensure_unique_dates():
    assert utils.ensure_unique_dates(["2025-01-01", "2025-01-01", "2025-01-02"]) == [
        "2025-01-01",
        "2025-01-02",
    ]
