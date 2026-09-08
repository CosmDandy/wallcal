"""The Russian production calendar: which days are actually worked.

Two things decide it. The holidays of Trudovoy Kodeks art. 112 are fixed in law
and repeat every year, so they are a rule. The transfers on top of them are not:
each year the government moves days off around by decree, usually so a holiday
next to a weekend grows into a run, and the price is a Saturday somewhere else
that has to be worked. There is no formula for those — a table is the only
honest way to hold them.

A year the table does not know falls back to plain weekends plus the statutory
holidays. That is wrong by a handful of days rather than by a season, and it is
the failure a calendar can survive; inventing transfers would not be.

Verified against the published production calendars by day count: 2025 comes to
247 working and 118 non-working days, 2026 to 247 and 118, both matching the
official totals. 2027 is deliberately absent — as of September 2026 it exists
only as a Mintrud draft out for public discussion, and a draft is not a decree.
"""

from __future__ import annotations

from datetime import date
from typing import NamedTuple

SATURDAY = 5  # date.weekday(): Saturday and Sunday are the plain weekend

# Trudovoy Kodeks art. 112, as (month, day). Always non-working, whatever the
# decrees do: a transfer moves the day off a holiday earns, never the holiday.
HOLIDAYS: frozenset[tuple[int, int]] = frozenset(
    {
        (1, 1),
        (1, 2),
        (1, 3),
        (1, 4),
        (1, 5),
        (1, 6),  # New Year holidays
        (1, 7),  # Christmas
        (1, 8),  # New Year holidays
        (2, 23),  # Defender of the Fatherland
        (3, 8),  # International Women's Day
        (5, 1),  # Spring and Labour
        (5, 9),  # Victory Day
        (6, 12),  # Russia Day
        (11, 4),  # National Unity Day
    }
)


class Transfers(NamedTuple):
    """One year's departures from the plain week.

    Stated as outcomes rather than as the decree's "from X to Y" pairs. A pair
    says nothing about whether X is worked: when X is a holiday it stays off and
    only the destination moves, and that distinction cost more to re-derive at
    every call than to write down once.
    """

    working: frozenset[date]  # a Saturday or Sunday that is worked
    off: frozenset[date]  # a Monday-to-Friday that is not


TRANSFERS: dict[int, Transfers] = {
    # Government decree of 04.10.2024 N 1335. Four of its five pairs move a day
    # off a holiday that fell on a weekend, so only 1 November is worked.
    2025: Transfers(
        working=frozenset({date(2025, 11, 1)}),
        off=frozenset(
            {
                date(2025, 5, 2),
                date(2025, 5, 8),
                date(2025, 6, 13),
                date(2025, 11, 3),
                date(2025, 12, 31),
            }
        ),
    ),
    # Government decree of 24.09.2025 N 1466 gives 9 January and 31 December.
    # 9 March and 11 May are art. 112 part 2 doing its own work: a holiday
    # landing on a weekend hands its day off to the next working day.
    2026: Transfers(
        working=frozenset(),
        off=frozenset(
            {
                date(2026, 1, 9),
                date(2026, 3, 9),
                date(2026, 5, 11),
                date(2026, 12, 31),
            }
        ),
    ),
}


def is_non_working(day: date) -> bool:
    """True when `day` is a holiday, a weekend, or a day off the government moved."""
    if (day.month, day.day) in HOLIDAYS:
        return True
    transfers = TRANSFERS.get(day.year)
    if transfers is None:
        return day.weekday() >= SATURDAY
    if day in transfers.working:
        return False
    return day.weekday() >= SATURDAY or day in transfers.off
