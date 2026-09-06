"""Date arithmetic: turn a span of days into a grid of weeks by weekdays.

A row holds `weeks_per_row` whole ISO weeks (Monday first), so its width is a
multiple of seven days. Days falling outside the requested span are marked
OUTSIDE so the renderer can skip them and the span's real start stays visible.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum

DAYS_PER_WEEK = 7
DEFAULT_WEEKS_PER_ROW = 2
MAX_WEEKS_PER_ROW = 4


class WeekNumbering(Enum):
    """What the numbers down the left edge count."""

    ISO = "iso"  # calendar week of the year, 1-53
    ORDINAL = "n"  # weeks since the span began, starting at 1


class CellState(Enum):
    OUTSIDE = "outside"
    PAST = "past"
    TODAY = "today"
    FUTURE = "future"


@dataclass(frozen=True, slots=True)
class Cell:
    day: date
    row: int
    col: int
    state: CellState

    @property
    def is_weekend(self) -> bool:
        return self.day.weekday() >= 5

    @property
    def is_month_end(self) -> bool:
        return (self.day + timedelta(days=1)).day == 1


@dataclass(frozen=True)
class Grid:
    start: date
    end: date
    today: date
    rows: int
    columns: int
    cells: tuple[Cell, ...]
    month_spans: tuple[tuple[int, int, int], ...]  # (first_row, last_row, month number)
    week_labels: tuple[tuple[int, str], ...]  # (row, "36")
    first_weekday: int = 0

    @property
    def days_total(self) -> int:
        return (self.end - self.start).days + 1

    @property
    def days_elapsed(self) -> int:
        """Days of the span already spent, clamped to the span itself."""
        return max(0, min(self.days_total, (self.today - self.start).days + 1))

    @property
    def progress(self) -> float:
        return self.days_elapsed / self.days_total

    @property
    def days_left(self) -> int:
        return self.days_total - self.days_elapsed

    @property
    def weeks_total(self) -> int:
        """Weeks the span covers, counted from the same day the rows start on.

        Counting from Monday regardless made the ft=week footer claim a total
        the drawn rows did not add up to whenever wd was anything but 0.
        """
        first, last = self._week_start(self.start), self._week_start(self.end)
        return (last - first).days // DAYS_PER_WEEK + 1

    @property
    def week_index(self) -> int:
        """Which week of the span today falls in, clamped to it. 0 before it starts."""
        if self.today < self.start:
            return 0
        first = self._week_start(self.start)
        offset = (self._week_start(self.today) - first).days // DAYS_PER_WEEK
        return min(self.weeks_total, offset + 1)

    def _week_start(self, day: date) -> date:
        return week_start(day, self.first_weekday)


class GridError(ValueError):
    """Raised for a span that cannot be laid out at all."""


MAX_WEEKS = 800  # ~15 years; beyond this a phone screen has no pixels left per day


def week_start(day: date, first_weekday: int = 0) -> date:
    """Start of the week `day` falls in. `first_weekday` is 0 for Monday, 6 for Sunday."""
    return day - timedelta(days=(day.weekday() - first_weekday) % DAYS_PER_WEEK)


def month_end(day: date) -> date:
    following = (day.replace(day=28) + timedelta(days=4)).replace(day=1)
    return following - timedelta(days=1)


def _chunks(start: date, end: date, month_breaks: bool) -> list[tuple[date, date]]:
    """Date ranges that each get their own rows.

    One chunk for the whole span normally; one per month when a new month has to
    start on a fresh row, which is what stops a row from straddling two months.
    """
    if not month_breaks:
        return [(start, end)]

    chunks: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        stop = min(month_end(cursor), end)
        chunks.append((cursor, stop))
        cursor = stop + timedelta(days=1)
    return chunks


def build_span(
    start: date,
    end: date,
    today: date,
    weeks_per_row: int = DEFAULT_WEEKS_PER_ROW,
    numbering: WeekNumbering = WeekNumbering.ISO,
    month_breaks: bool = False,
    first_weekday: int = 0,
) -> Grid:
    if end < start:
        raise GridError("end date must not be before start date")
    if not 1 <= weeks_per_row <= MAX_WEEKS_PER_ROW:
        raise GridError(f"weeks per row must be between 1 and {MAX_WEEKS_PER_ROW}")
    if not 0 <= first_weekday < DAYS_PER_WEEK:
        raise GridError("first weekday must be 0 (Monday) through 6 (Sunday)")

    weeks = (
        (week_start(end, first_weekday) - week_start(start, first_weekday)).days // DAYS_PER_WEEK
    ) + 1
    if weeks > MAX_WEEKS:
        raise GridError(f"span covers {weeks} weeks, more than the {MAX_WEEKS} supported")

    columns = weeks_per_row * DAYS_PER_WEEK
    row_span = timedelta(days=DAYS_PER_WEEK * weeks_per_row)

    # Every row is (origin Monday, the range of days that row may show). Rows of
    # different chunks can cover the same Monday: the days belonging to the other
    # chunk simply fall outside its range and are not drawn twice.
    rows_plan: list[tuple[date, date, date]] = []
    for chunk_start, chunk_end in _chunks(start, end, month_breaks):
        origin = week_start(chunk_start, first_weekday)
        while origin <= week_start(chunk_end, first_weekday):
            rows_plan.append((origin, chunk_start, chunk_end))
            origin += row_span

    rows = len(rows_plan)
    cells: list[Cell] = []
    for row, (origin, chunk_start, chunk_end) in enumerate(rows_plan):
        for col in range(columns):
            day = origin + timedelta(days=col)
            if day < chunk_start or day > chunk_end:
                state = CellState.OUTSIDE
            elif day == today:
                state = CellState.TODAY
            elif day < today:
                state = CellState.PAST
            else:
                state = CellState.FUTURE
            cells.append(Cell(day, row, col, state))

    return Grid(
        start=start,
        end=end,
        today=today,
        rows=rows,
        columns=columns,
        cells=tuple(cells),
        month_spans=_month_spans(cells, rows, columns),
        week_labels=_week_labels(cells, rows, columns, start, numbering, first_weekday),
        first_weekday=first_weekday,
    )


WEEK_LABEL_EVERY = 2  # label every Nth row, so the gutter keeps some air


def _row_month(cells: list[Cell], row: int, columns: int) -> int | None:
    """The month a row mostly belongs to, ties going to the later one.

    Counted over in-span cells only: a label must name the month the reader sees
    dots for, not the month of a leading OUTSIDE cell. A wide row straddles two
    months, and majority is what decides which one it is drawn against.
    """
    band = cells[row * columns : (row + 1) * columns]
    months = [c.day.month for c in band if c.state is not CellState.OUTSIDE]
    if not months:
        return None
    # max() keeps the first maximum, so the candidates are walked latest-first:
    # a row split evenly between two months belongs to the later one, which is
    # the one whose dots continue below it.
    return max(sorted(set(months), reverse=True), key=months.count)


def _month_spans(cells: list[Cell], rows: int, columns: int) -> tuple[tuple[int, int, int], ...]:
    """Consecutive rows of the same month, as (first_row, last_row, month number).

    A range rather than a point, because the label is set vertically alongside
    the rows it covers. The number, not a name: the language is a drawing choice.
    """
    spans: list[tuple[int, int, int]] = []
    for row in range(rows):
        month = _row_month(cells, row, columns)
        if month is None:
            continue
        if spans and spans[-1][2] == month:
            first, _, number = spans[-1]
            spans[-1] = (first, row, number)
        else:
            spans.append((row, row, month))
    return tuple(spans)


def _week_labels(
    cells: list[Cell],
    rows: int,
    columns: int,
    start: date,
    numbering: WeekNumbering,
    first_weekday: int,
) -> tuple[tuple[int, str], ...]:
    """A number for every WEEK_LABEL_EVERY-th row, read off the row's own Monday.

    Taken from the date rather than from the row index, so the numbers stay true
    when month breaks make the rows skip forward.
    """
    labels: list[tuple[int, str]] = []
    for row in range(0, rows, WEEK_LABEL_EVERY):
        band = cells[row * columns : (row + 1) * columns]
        if not any(c.state is not CellState.OUTSIDE for c in band):
            continue
        monday = band[0].day
        if numbering is WeekNumbering.ISO:
            number = monday.isocalendar().week
        else:
            number = (monday - week_start(start, first_weekday)).days // DAYS_PER_WEEK + 1
        labels.append((row, str(number)))
    return tuple(labels)
