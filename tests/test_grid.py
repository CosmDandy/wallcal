from __future__ import annotations

from datetime import date

import pytest

from wallcal.grid import (
    DAYS_PER_WEEK,
    CellState,
    GridError,
    WeekNumbering,
    build_span,
    week_start,
)


def states(grid, row: int) -> list[CellState]:
    return [c.state for c in grid.cells[row * grid.columns : (row + 1) * grid.columns]]


def build(start, end, today, weeks_per_row=1):
    """Most date assertions read clearest one week to a row."""
    return build_span(start, end, today, weeks_per_row)


def test_rows_cover_whole_weeks_of_the_span():
    # 2026-09-01 is a Tuesday, 2026-09-14 a Monday: three ISO weeks are touched.
    grid = build(date(2026, 9, 1), date(2026, 9, 14), date(2026, 9, 6))
    assert grid.rows == 3
    assert len(grid.cells) == 3 * DAYS_PER_WEEK
    assert week_start(date(2026, 9, 1)) == date(2026, 8, 31)


def test_days_before_the_start_are_outside_not_past():
    grid = build(date(2026, 9, 1), date(2026, 9, 30), date(2026, 9, 6))
    # Monday 2026-08-31 precedes the span even though it precedes today too.
    assert states(grid, 0)[0] is CellState.OUTSIDE
    assert states(grid, 0)[1] is CellState.PAST


def test_days_after_the_end_are_outside():
    grid = build(date(2026, 9, 1), date(2026, 9, 30), date(2026, 9, 6))
    last = states(grid, grid.rows - 1)
    assert last[2] is CellState.FUTURE  # Wednesday 2026-09-30, the end
    assert last[3] is CellState.OUTSIDE


def test_today_is_its_own_state():
    grid = build(date(2026, 9, 1), date(2026, 9, 30), date(2026, 9, 6))
    today_cells = [c for c in grid.cells if c.state is CellState.TODAY]
    assert [c.day for c in today_cells] == [date(2026, 9, 6)]


def test_today_outside_the_span_leaves_no_today_cell():
    grid = build(date(2026, 9, 1), date(2026, 9, 30), date(2027, 1, 1))
    assert not [c for c in grid.cells if c.state is CellState.TODAY]


@pytest.mark.parametrize(
    ("today", "elapsed", "total"),
    [
        (date(2026, 8, 1), 0, 30),  # before the span
        (date(2026, 9, 1), 1, 30),  # first day
        (date(2026, 9, 6), 6, 30),
        (date(2026, 12, 1), 30, 30),  # after the span, clamped
    ],
)
def test_progress_is_clamped_to_the_span(today, elapsed, total):
    grid = build_span(date(2026, 9, 1), date(2026, 9, 30), today)
    assert (grid.days_elapsed, grid.days_total) == (elapsed, total)


def test_single_day_span():
    grid = build(date(2026, 9, 6), date(2026, 9, 6), date(2026, 9, 6))
    assert grid.rows == 1
    assert grid.days_total == 1
    assert grid.progress == 1.0
    assert states(grid, 0).count(CellState.OUTSIDE) == 6


def test_month_spans_cover_every_month_once_and_in_order():
    grid = build(date(2026, 1, 1), date(2026, 12, 31), date(2026, 9, 6))
    numbers = [number for _, _, number in grid.month_spans]
    assert numbers == list(range(1, 13))

    for first, last, _ in grid.month_spans:
        assert first <= last
    boundaries = [row for span in grid.month_spans for row in span[:2]]
    assert boundaries == sorted(boundaries)


def test_month_spans_are_contiguous():
    grid = build(date(2026, 1, 1), date(2026, 12, 31), date(2026, 9, 6))
    for previous, following in zip(grid.month_spans, grid.month_spans[1:], strict=False):
        assert following[0] == previous[1] + 1


def test_reversed_span_is_rejected():
    with pytest.raises(GridError):
        build(date(2026, 9, 30), date(2026, 9, 1), date(2026, 9, 6))


def test_absurdly_long_span_is_rejected():
    with pytest.raises(GridError):
        build(date(1900, 1, 1), date(2100, 1, 1), date(2026, 9, 6))


def test_default_row_holds_two_whole_weeks():
    grid = build_span(date(2026, 9, 1), date(2026, 9, 30), date(2026, 9, 6))
    assert grid.columns == 2 * DAYS_PER_WEEK == 14


@pytest.mark.parametrize(("weeks_per_row", "rows"), [(1, 5), (2, 3), (3, 2), (4, 2)])
def test_grouping_packs_weeks_into_rows(weeks_per_row, rows):
    # 2026-09-01..2026-09-30 spans five ISO weeks; rows round up.
    grid = build_span(date(2026, 9, 1), date(2026, 9, 30), date(2026, 9, 6), weeks_per_row)
    assert grid.rows == rows
    assert grid.columns == weeks_per_row * DAYS_PER_WEEK
    assert len(grid.cells) == rows * grid.columns


def test_a_partial_last_row_is_filled_with_outside_cells():
    # Five weeks over two-week rows leaves the sixth week of the last row empty.
    grid = build_span(date(2026, 9, 1), date(2026, 9, 30), date(2026, 9, 6), 2)
    last = states(grid, grid.rows - 1)
    assert last[-DAYS_PER_WEEK:] == [CellState.OUTSIDE] * DAYS_PER_WEEK


@pytest.mark.parametrize("weeks_per_row", [0, -1, 5])
def test_unsupported_grouping_is_rejected(weeks_per_row):
    with pytest.raises(GridError):
        build_span(date(2026, 9, 1), date(2026, 9, 30), date(2026, 9, 6), weeks_per_row)


def test_a_row_straddling_two_months_goes_to_the_month_holding_most_of_it():
    # Two-week rows from Mon 2026-08-31: row 2 covers 28 Sep - 11 Oct, eleven
    # days of which are October, so the row is drawn against October.
    grid = build_span(date(2026, 9, 1), date(2026, 12, 31), date(2026, 9, 6), 2)
    by_row = {
        row: number for first, last, number in grid.month_spans for row in range(first, last + 1)
    }

    assert by_row[0] == 9
    assert by_row[2] == 10


def test_week_numbers_are_iso_and_appear_every_other_row():
    # 2026-09-01 falls in ISO week 36; two-week rows advance the number by two.
    grid = build_span(date(2026, 9, 1), date(2026, 12, 31), date(2026, 9, 6), 2)

    assert grid.week_labels[0] == (0, "36")
    assert [row for row, _ in grid.week_labels] == list(range(0, grid.rows, 2))
    assert grid.week_labels[1] == (2, "40")


def test_week_numbers_follow_the_grouping():
    grid = build_span(date(2026, 9, 1), date(2026, 9, 30), date(2026, 9, 6), 1)
    assert [label for _, label in grid.week_labels] == ["36", "38", "40"]


def test_month_breaks_give_every_month_its_own_rows():
    grid = build_span(date(2026, 9, 1), date(2026, 11, 30), date(2026, 9, 6), 2, month_breaks=True)

    for row in range(grid.rows):
        band = grid.cells[row * grid.columns : (row + 1) * grid.columns]
        months = {c.day.month for c in band if c.state is not CellState.OUTSIDE}
        assert len(months) <= 1, f"row {row} straddles months {months}"


def test_month_breaks_start_each_month_on_a_monday_row():
    grid = build_span(date(2026, 9, 1), date(2026, 11, 30), date(2026, 9, 6), 2, month_breaks=True)
    firsts = [
        next(
            c
            for c in grid.cells[r * grid.columns : (r + 1) * grid.columns]
            if c.state is not CellState.OUTSIDE
        )
        for r in range(grid.rows)
    ]
    starts = [c.day for c in firsts if c.day.day == 1]

    assert starts == [date(2026, 9, 1), date(2026, 10, 1), date(2026, 11, 1)]
    # Every row still begins on a Monday, month break or not.
    assert all(grid.cells[r * grid.columns].day.weekday() == 0 for r in range(grid.rows))


def test_month_breaks_do_not_lose_or_duplicate_a_day():
    grid = build_span(date(2026, 9, 1), date(2026, 11, 30), date(2026, 9, 6), 2, month_breaks=True)
    shown = [c.day for c in grid.cells if c.state is not CellState.OUTSIDE]

    assert len(shown) == len(set(shown)) == grid.days_total


def test_ordinal_week_numbers_stay_true_across_month_breaks():
    grid = build_span(
        date(2026, 9, 1),
        date(2026, 11, 30),
        date(2026, 9, 6),
        1,
        WeekNumbering.ORDINAL,
        month_breaks=True,
    )
    for row, label in grid.week_labels:
        monday = grid.cells[row * grid.columns].day
        assert int(label) == (monday - week_start(date(2026, 9, 1))).days // DAYS_PER_WEEK + 1


def test_sunday_can_start_the_week():
    """2026-09-06 is a Sunday: first column under a Sunday-first calendar."""
    grid = build_span(date(2026, 9, 1), date(2026, 9, 30), date(2026, 9, 6), 1, first_weekday=6)
    today = next(c for c in grid.cells if c.state is CellState.TODAY)

    assert today.col == 0
    assert all(grid.cells[r * grid.columns].day.weekday() == 6 for r in range(grid.rows))


def test_monday_first_is_the_default():
    grid = build_span(date(2026, 9, 1), date(2026, 9, 30), date(2026, 9, 6), 1)
    today = next(c for c in grid.cells if c.state is CellState.TODAY)
    assert today.col == 6  # Sunday closes a Monday-first week


def test_the_week_count_matches_the_rows_drawn_whatever_starts_the_week():
    """The ft=week footer counts the same weeks the grid draws as rows.

    Counted from Monday regardless, this claimed "Week 9 of 9" over eight rows
    for any wd but 0.
    """
    for first in range(7):
        grid = build_span(
            date(2026, 9, 6), date(2026, 10, 31), date(2026, 10, 31), 1, first_weekday=first
        )
        assert grid.weeks_total == grid.rows
        assert grid.week_index == grid.rows


def test_an_impossible_first_weekday_is_refused():
    with pytest.raises(GridError):
        build_span(date(2026, 9, 1), date(2026, 9, 30), date(2026, 9, 6), 1, first_weekday=7)
