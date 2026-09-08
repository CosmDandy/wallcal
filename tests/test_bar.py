"""The progress rule: which period it measures, and what the old spellings mean."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from wallcal.app import app
from wallcal.grid import build_span
from wallcal.render import BarError, BarMode, _bar_progress, parse_bar


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# `br` was a bool, so FastAPI accepted every spelling pydantic calls one. A link
# written in any of them has to keep answering 200.
@pytest.mark.parametrize("spec", ["1", "true", "yes", "on", "t", "y", "TRUE", " On "])
def test_the_old_true_spellings_still_mean_the_span(spec: str):
    assert parse_bar(spec) is BarMode.SPAN


@pytest.mark.parametrize("spec", ["0", "false", "no", "off", "f", "n", "False"])
def test_the_old_false_spellings_still_mean_no_rule(spec: str):
    assert parse_bar(spec) is BarMode.NONE


def test_an_unknown_period_names_the_ones_that_exist():
    with pytest.raises(BarError) as caught:
        parse_bar("decade")
    assert "quarter" in str(caught.value)


def test_the_span_period_is_the_grid_s_own_progress():
    grid = build_span(date(2026, 1, 1), date(2026, 3, 31), date(2026, 2, 15))
    assert _bar_progress(BarMode.SPAN, grid) == grid.progress


def test_a_calendar_period_is_measured_against_today_not_the_span():
    """A span that ended still leaves the year rule standing where the year is."""
    grid = build_span(date(2026, 1, 1), date(2026, 1, 31), date(2026, 7, 2))
    assert _bar_progress(BarMode.SPAN, grid) == 1.0  # the span is spent
    assert _bar_progress(BarMode.YEAR, grid) == pytest.approx(183 / 365, abs=1e-9)


@pytest.mark.parametrize(
    ("day", "mode", "expected"),
    [
        (date(2026, 12, 31), BarMode.YEAR, 1.0),
        (date(2026, 1, 1), BarMode.YEAR, 1 / 365),
        (date(2024, 12, 31), BarMode.YEAR, 1.0),  # a leap year still fills exactly
        (date(2026, 3, 31), BarMode.QUARTER, 1.0),
        (date(2026, 4, 1), BarMode.QUARTER, 1 / 91),
        (date(2026, 11, 30), BarMode.MONTH, 1.0),
        (date(2026, 2, 14), BarMode.MONTH, 14 / 28),
    ],
)
def test_each_period_fills_and_rolls_over_at_its_own_boundary(
    day: date, mode: BarMode, expected: float
):
    grid = build_span(day, day, day)
    assert _bar_progress(mode, grid) == pytest.approx(expected, abs=1e-9)


def test_a_period_changes_the_drawing(client: TestClient):
    span = "f=2026-09-01&t=2026-12-31"
    year = client.get(f"/w/span.png?{span}&br=year")
    plain = client.get(f"/w/span.png?{span}&br=1")
    assert year.status_code == plain.status_code == 200
    assert year.content != plain.content


def test_two_spellings_of_one_drawing_share_an_etag(client: TestClient):
    span = "f=2026-09-01&t=2026-12-31"
    assert (
        client.get(f"/w/span.png?{span}&br=1").headers["etag"]
        == client.get(f"/w/span.png?{span}&br=span").headers["etag"]
    )


def test_a_bad_period_is_a_400_naming_the_parameter(client: TestClient):
    answer = client.get("/w/span.png?f=2026-09-01&t=2026-12-31&br=decade")
    assert answer.status_code == 400
    assert "bar period" in answer.json()["detail"]
