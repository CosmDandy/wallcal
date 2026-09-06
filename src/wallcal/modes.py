"""Calendar modes.

Only `span` is built. `life` and `year` are declared here — not as dead code but
as the contract the HTTP layer already routes and documents, so adding one means
writing its builder and flipping `builder` from None.

`life` will not reuse the span geometry: 90 years is ~4700 weeks, which no phone
screen can show at seven columns per row. It needs its own row unit (a year per
row, weeks across) and therefore its own builder.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from .grid import DEFAULT_WEEKS_PER_ROW, Grid, WeekNumbering, build_span, month_end


@dataclass(frozen=True)
class Params:
    """Everything a builder may read. Not every mode uses every field."""

    start: date | None = None
    end: date | None = None
    today: date = date.min
    weeks_per_row: int = DEFAULT_WEEKS_PER_ROW
    numbering: WeekNumbering = WeekNumbering.ISO
    month_breaks: bool = False
    first_weekday: int = 0


@dataclass(frozen=True)
class Mode:
    key: str
    label: str
    required: tuple[str, ...]
    builder: Callable[[Params], Grid] | None

    @property
    def implemented(self) -> bool:
        return self.builder is not None


class ModeError(ValueError):
    """Raised for an unknown mode key."""


class ModeNotImplemented(NotImplementedError):
    """Raised for a declared but unbuilt mode."""


def _between(start: date, end: date, params: Params) -> Grid:
    return build_span(
        start,
        end,
        params.today,
        params.weeks_per_row,
        params.numbering,
        params.month_breaks,
        params.first_weekday,
    )


def _build_span(params: Params) -> Grid:
    if params.start is None or params.end is None:
        raise ValueError("span requires both f (from) and t (to)")
    return _between(params.start, params.end, params)


def _build_year(params: Params) -> Grid:
    year = params.today.year
    return _between(date(year, 1, 1), date(year, 12, 31), params)


def _build_quarter(params: Params) -> Grid:
    first_month = (params.today.month - 1) // 3 * 3 + 1
    start = date(params.today.year, first_month, 1)
    return _between(start, month_end(date(params.today.year, first_month + 2, 1)), params)


def _build_month(params: Params) -> Grid:
    start = params.today.replace(day=1)
    return _between(start, month_end(start), params)


MODES: dict[str, Mode] = {
    m.key: m
    for m in (
        Mode("span", "Date span, week rows by weekday columns", ("f", "t"), _build_span),
        # No dates in the URL at all: these follow the calendar, so the link
        # never expires and rolls over on its own at midnight on the boundary.
        Mode("year", "The current year", (), _build_year),
        Mode("quarter", "The current quarter", (), _build_quarter),
        Mode("month", "The current month", (), _build_month),
        Mode("life", "Whole life in weeks", ("f",), None),
    )
}


def build(mode_key: str, params: Params) -> Grid:
    mode = MODES.get(mode_key.strip().lower())
    if mode is None:
        raise ModeError(f"unknown mode {mode_key!r}; known: {', '.join(MODES)}")
    if mode.builder is None:
        raise ModeNotImplemented(f"mode {mode.key!r} is not implemented yet")
    return mode.builder(params)
