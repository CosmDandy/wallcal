"""The Russian production calendar: the table has to agree with the decrees."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from wallcal.workdays import TRANSFERS, is_non_working


def count_non_working(year: int) -> int:
    day = date(year, 1, 1)
    total = 0
    while day.year == year:
        total += is_non_working(day)
        day += timedelta(days=1)
    return total


@pytest.mark.parametrize(
    "day",
    [
        date(2026, 1, 1),
        date(2026, 1, 7),
        date(2026, 2, 23),
        date(2026, 5, 1),
        date(2026, 6, 12),
        date(2026, 11, 4),
    ],
)
def test_statutory_holidays_are_never_worked(day: date):
    assert is_non_working(day)


def test_a_plain_weekday_is_worked():
    assert not is_non_working(date(2026, 9, 8))  # a Tuesday with nothing on it


def test_a_plain_weekend_is_not():
    assert is_non_working(date(2026, 9, 5))
    assert is_non_working(date(2026, 9, 6))


def test_a_transfer_can_make_a_saturday_a_working_day():
    """1 November 2025: its day off went to Monday the 3rd, so the Saturday was worked."""
    assert not is_non_working(date(2025, 11, 1))
    assert is_non_working(date(2025, 11, 3))


@pytest.mark.parametrize(
    "day",
    [date(2025, 5, 2), date(2025, 5, 8), date(2025, 6, 13), date(2025, 12, 31)],
)
def test_transferred_days_off_land_on_weekdays(day: date):
    assert day.weekday() < 5
    assert is_non_working(day)


@pytest.mark.parametrize("day", [date(2026, 1, 9), date(2026, 3, 9), date(2026, 5, 11)])
def test_2026_gets_its_own_transfers(day: date):
    assert is_non_working(day)


@pytest.mark.parametrize(("year", "expected"), [(2025, 118), (2026, 118)])
def test_the_year_adds_up_to_the_published_total(year: int, expected: int):
    """The one check that catches a mistyped transfer: the official day count."""
    assert count_non_working(year) == expected


def test_a_year_with_no_table_falls_back_to_weekends_and_holidays():
    """Better a handful of days wrong than a season: no table means no guesses."""
    assert 2030 not in TRANSFERS
    assert is_non_working(date(2030, 5, 9))  # Victory Day, a Thursday
    assert is_non_working(date(2030, 5, 11))  # a Saturday
    assert not is_non_working(date(2030, 5, 10))  # the Friday between them is worked
