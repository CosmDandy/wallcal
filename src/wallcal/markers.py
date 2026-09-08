"""Day markers: a rule the reader names, and the colour its days take.

One `m` parameter per marker, `<rule>@<colour>[@<label>]`. The rule is the part
that has to stay readable in a link — weekday codes, a day of the month, or a
date — because a marker is the one setting a person edits by hand when the
builder is not at hand.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from .palette import RGB, parse_color

# A URL is the whole configuration here, and it still has to survive being
# pasted into a Shortcut, a chat window and a browser bar. Thirty-two markers
# already make the longest query string the API can produce; past that the link
# stops being something a person can handle, and every marker costs another
# pass over the grid.
MAX_MARKERS = 32

# The label is never drawn. It exists so a shared link carries the names back
# into the builder rather than a row of anonymous colours — which is why it can
# be this short and still do its whole job.
MAX_LABEL = 24

WEEKDAYS = ("mo", "tu", "we", "th", "fr", "sa", "su")
MONTHDAY = re.compile(r"^d([1-9]|[12][0-9]|3[01])$")
# A day pulled back off a non-working day never travels far — the longest
# unbroken run of them in the Russian year is the New Year holidays, about
# eleven days. The bound only stops a runaway loop if a calendar ever says
# every day is a day off; the nominal day is kept if it is ever reached.
PULL_BACK_LIMIT = 31
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# `..` reads as a stretch and needs no encoding in a query string.
RANGE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.\.(\d{4}-\d{2}-\d{2})$")

SHAPE = "<rule>@<colour>[@<label>]"


class MarkerError(ValueError):
    """Raised for a marker spec that does not parse."""


class TooManyMarkers(ValueError):
    """Raised for a URL carrying more markers than MAX_MARKERS."""


@dataclass(frozen=True, slots=True)
class Marker:
    """One rule, the colour its days are tinted with, and what the user calls it.

    Exactly one of the three rule fields carries the rule; which one is settled
    at parse time, so asking about a day is a comparison and never a re-parse.
    """

    color: RGB
    label: str = ""
    weekdays: tuple[int, ...] = ()  # 0 Monday .. 6 Sunday
    monthdays: tuple[int, ...] = ()  # `d10,d25`: those days of every month
    on: date | None = None  # a single calendar date, or the first of a stretch
    until: date | None = None  # the last of a stretch: a holiday, a sprint, a trip
    # Wages are the case this exists for: paying late breaks the law and paying
    # early does not, so a payday landing on a day off moves backwards. Which
    # days count as off is the drawing's own answer — with the production
    # calendar on, a holiday pulls the day back just as a Sunday does.
    pull_back: bool = False

    def days_in(self, start: date, end: date, non_working: Callable[[date], bool]) -> set[date]:
        """Every day between `start` and `end` this rule claims, after any pull-back."""
        # A nominal day just past the end can still land inside it once pulled
        # back, so the rule is expanded over a wider range than it is asked about.
        horizon = end + timedelta(days=PULL_BACK_LIMIT) if self.pull_back else end
        nominal = self._nominal(start, horizon)
        if not self.pull_back:
            return nominal
        moved = set()
        for day in nominal:
            landing = day
            for _ in range(PULL_BACK_LIMIT):
                if not non_working(landing):
                    break
                landing -= timedelta(days=1)
            moved.add(landing)
        return {day for day in moved if start <= day <= end}

    def _nominal(self, start: date, end: date) -> set[date]:
        """The days the rule names, before anything is moved off a day off."""
        if self.on is not None:
            last = self.until or self.on
            first = max(self.on, start)
            stop = min(last, end)
            span = (stop - first).days + 1
            return {first + timedelta(days=offset) for offset in range(max(0, span))}
        if self.monthdays:
            days = set()
            cursor = start.replace(day=1)
            while cursor <= end:
                for number in self.monthdays:
                    try:
                        day = cursor.replace(day=number)
                    except ValueError:
                        continue  # d31 simply does not happen in a 30-day month
                    if start <= day <= end:
                        days.add(day)
                cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
            return days
        span = (end - start).days + 1
        return {
            start + timedelta(days=offset)
            for offset in range(span)
            if (start + timedelta(days=offset)).weekday() in self.weekdays
        }


def _calendar_date(text: str, rule: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise MarkerError(f"marker rule {rule!r} is not a date on the calendar") from exc


def parse_marker(spec: str) -> Marker:
    """`mo,we@blue`, `d10,d25~@green@Wages`, `2026-12-31@red@Deadline`,
    `2026-07-01..2026-07-14@cyan@Holiday`.

    The label comes last so it can hold anything, `@` included: only the first
    two separators are structural. A rule ending in `~` is pulled back off any
    day that is not worked.
    """
    rule, _, rest = spec.partition("@")
    color, _, label = rest.partition("@")

    rule = rule.strip().lower()
    pull_back = rule.endswith("~")
    rule = rule.removesuffix("~").strip()
    label = label.strip()
    if not rule or not color.strip():
        raise MarkerError(f"marker {spec!r} is not {SHAPE}")
    if len(label) > MAX_LABEL:
        raise MarkerError(f"marker label {label!r} is longer than {MAX_LABEL} characters")

    # The same colour vocabulary as `mc` and `a`: a marker is not a place to
    # learn a second one. ColorError carries its own list of what is accepted.
    tint = parse_color(color)

    stretch = RANGE.match(rule)
    if stretch:
        opening, closing = (_calendar_date(text, rule) for text in stretch.groups())
        if closing < opening:
            raise MarkerError(f"marker rule {rule!r} ends before it starts")
        if pull_back:
            # `~` moves one day off a day off. A stretch is already a block of
            # days, and pulling every one of them back would fold it shut.
            raise MarkerError(
                f"marker rule {rule!r} is a stretch of days and cannot be pulled back"
            )
        return Marker(color=tint, label=label, on=opening, until=closing)

    if ISO_DATE.match(rule):
        return Marker(color=tint, label=label, on=_calendar_date(rule, rule), pull_back=pull_back)

    codes = [code.strip() for code in rule.split(",") if code.strip()]
    if not codes:
        raise MarkerError(f"marker {spec!r} is not {SHAPE}")

    # A month-day rule takes a list the way a weekday rule does: wages arrive
    # twice a month on the same two dates, which is the shape people asked for.
    numbers = [MONTHDAY.match(code) for code in codes]
    if all(numbers):
        found = tuple(sorted({int(m.group(1)) for m in numbers if m}))
        return Marker(color=tint, label=label, monthdays=found, pull_back=pull_back)

    if any(code not in WEEKDAYS for code in codes):
        raise MarkerError(
            f"marker rule {rule!r} is neither weekdays ({', '.join(WEEKDAYS)}), "
            f"days of the month (d1..d31), a date (YYYY-MM-DD), "
            f"nor a stretch (YYYY-MM-DD..YYYY-MM-DD)"
        )
    days = tuple(sorted({WEEKDAYS.index(code) for code in codes}))
    return Marker(color=tint, label=label, weekdays=days, pull_back=pull_back)


def parse_markers(specs: Sequence[str] | None) -> tuple[Marker, ...]:
    """Every `m` in the query string, in the order it was written.

    Order is the whole overlap rule: a later marker paints over an earlier one.
    """
    if not specs:
        return ()
    if len(specs) > MAX_MARKERS:
        raise TooManyMarkers(f"{len(specs)} markers; at most {MAX_MARKERS} fit in one URL")
    return tuple(parse_marker(spec) for spec in specs)
