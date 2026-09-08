"""Markers: what a rule accepts, which days it claims, and what the cell looks like."""

from __future__ import annotations

import re
from datetime import date
from importlib.resources import files

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageChops

from wallcal import layout as L
from wallcal import workdays
from wallcal.app import app
from wallcal.devices import Device
from wallcal.grid import build_span
from wallcal.markers import (
    MAX_LABEL,
    MAX_MARKERS,
    MarkerError,
    TooManyMarkers,
    parse_marker,
    parse_markers,
)
from wallcal.palette import SOLARIZED, lerp
from wallcal.render import MARKER_INSET, MARKER_TINT, Shape, Style, render_span

from .conftest import SPAN_END, SPAN_START, TODAY

SPAN = "f=2026-09-01&t=2026-11-30"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


# ── Parsing ─────────────────────────────────────────────────────────────────


def test_weekday_codes_become_weekday_numbers():
    marker = parse_marker("mo,we,su@blue")

    assert marker.weekdays == (0, 2, 6)
    assert marker.color == SOLARIZED["blue"]
    assert marker.label == ""


def test_a_day_of_the_month_is_kept_as_a_number():
    assert parse_marker("d25@green").monthdays == (25,)


def test_a_date_rule_is_kept_as_a_date():
    assert parse_marker("2026-12-31@red").on == date(2026, 12, 31)


def test_the_label_is_optional_and_comes_last():
    assert parse_marker("fr@cyan@Deploy day").label == "Deploy day"


def test_the_label_may_hold_the_separator_itself():
    """Only the first two `@` are structural, so a name is never cut in half."""
    assert parse_marker("fr@cyan@me@work").label == "me@work"


def test_a_marker_takes_hex_like_every_other_colour():
    assert parse_marker("sa@f0a@Rest").color == (0xFF, 0x00, 0xAA)


def test_weekday_codes_are_deduplicated_and_ordered():
    assert parse_marker("fr,mo,fr@blue").weekdays == (0, 4)


@pytest.mark.parametrize(
    "spec",
    [
        "mo",  # no colour at all
        "@blue",  # no rule
        "xx@blue",  # not a weekday
        "mo,xx@blue",  # one bad code among good ones
        "d0@blue",  # months start at 1
        "d32@blue",  # ...and end at 31
        "2026-02-30@blue",  # not a day on the calendar
        "mo@chartreuse",  # not a colour
    ],
)
def test_a_rule_that_does_not_parse_is_refused(spec: str):
    with pytest.raises(ValueError):
        parse_marker(spec)


def test_an_overlong_label_is_refused():
    with pytest.raises(MarkerError, match=str(MAX_LABEL)):
        parse_marker(f"mo@blue@{'x' * (MAX_LABEL + 1)}")


def test_the_cap_is_the_number_of_markers_not_their_size():
    specs = ["mo@blue"] * MAX_MARKERS

    assert len(parse_markers(specs)) == MAX_MARKERS
    with pytest.raises(TooManyMarkers, match=str(MAX_MARKERS)):
        parse_markers([*specs, "tu@red"])


def test_no_markers_at_all_is_the_normal_case():
    assert parse_markers(None) == ()
    assert parse_markers([]) == ()


# ── Matching ────────────────────────────────────────────────────────────────


WEEKEND = (5, 6)


def workweek(day: date) -> bool:
    """Plain Saturday and Sunday: what the drawing asks when pc is off."""
    return day.weekday() in WEEKEND


def claimed(spec: str, start: date, end: date, off=workweek) -> set[date]:
    return parse_marker(spec).days_in(start, end, off)


def test_weekdays_match_every_week():
    days = claimed("we@blue", date(2026, 9, 1), date(2026, 9, 30))

    assert date(2026, 9, 2) in days  # a Wednesday
    assert date(2026, 9, 9) in days
    assert date(2026, 9, 3) not in days
    assert len(days) == 5


def test_a_day_of_the_month_matches_in_every_month():
    days = claimed("d25@blue", date(2026, 9, 1), date(2026, 11, 30))

    assert days == {date(2026, 9, 25), date(2026, 10, 25), date(2026, 11, 25)}


def test_several_days_of_the_month_are_one_rule():
    """Wages arrive twice a month on the same two dates."""
    days = claimed("d10,d25@green", date(2026, 9, 1), date(2026, 10, 31))

    assert days == {
        date(2026, 9, 10),
        date(2026, 9, 25),
        date(2026, 10, 10),
        date(2026, 10, 25),
    }


def test_a_day_the_month_does_not_have_is_skipped_not_clamped():
    days = claimed("d31@blue", date(2026, 4, 1), date(2026, 5, 31))

    assert days == {date(2026, 5, 31)}  # April has no 31st, and gets no mark


def test_a_date_matches_once():
    start, end = date(2026, 1, 1), date(2027, 12, 31)
    assert claimed("2026-12-31@blue", start, end) == {date(2026, 12, 31)}


# ── A stretch of days ───────────────────────────────────────────────────────


def test_a_stretch_claims_every_day_between_its_ends():
    """A holiday is one marker, not fourteen."""
    days = claimed("2026-07-06..2026-07-12@cyan@Holiday", date(2026, 7, 1), date(2026, 7, 31))

    assert days == {date(2026, 7, day) for day in range(6, 13)}


def test_a_stretch_is_clipped_to_the_drawn_span_not_dropped():
    days = claimed("2026-06-25..2026-07-05@cyan", date(2026, 7, 1), date(2026, 7, 31))

    assert days == {date(2026, 7, day) for day in range(1, 6)}


def test_a_stretch_of_one_day_is_the_same_as_a_date():
    both = date(2026, 7, 6)
    assert claimed("2026-07-06..2026-07-06@cyan", both, both) == {both}
    assert claimed("2026-07-06@cyan", both, both) == {both}


def test_a_stretch_that_ends_before_it_starts_is_refused():
    with pytest.raises(MarkerError, match="ends before it starts"):
        parse_marker("2026-07-12..2026-07-06@cyan")


def test_a_stretch_cannot_be_pulled_back():
    """Pulling every day of a block back would fold the block shut."""
    with pytest.raises(MarkerError, match="cannot be pulled back"):
        parse_marker("2026-07-06..2026-07-12~@cyan")


def test_a_stretch_outside_the_span_claims_nothing():
    days = claimed("2025-01-01..2025-01-31@cyan", date(2026, 7, 1), date(2026, 7, 31))

    assert days == set()


# ── Pulled back off the days nobody works ───────────────────────────────────


def test_a_payday_on_a_weekend_moves_back_to_the_friday():
    """Paying late breaks the law and paying early does not, so it moves back."""
    # 25 October 2026 is a Sunday; 10 October is a Saturday.
    days = claimed("d10,d25~@green", date(2026, 10, 1), date(2026, 10, 31))

    assert days == {date(2026, 10, 9), date(2026, 10, 23)}  # both Fridays


def test_without_the_tilde_the_day_stays_where_it_falls():
    days = claimed("d25@green", date(2026, 10, 1), date(2026, 10, 31))

    assert days == {date(2026, 10, 25)}  # the Sunday itself


def test_the_pull_back_clears_a_whole_run_of_days_off():
    """January's holidays are one block: a payday inside it lands before all of it."""
    off = workdays.is_non_working
    days = claimed("d5~@green", date(2025, 12, 1), date(2026, 1, 31), off)

    # 5 December is an ordinary Friday and stays put. 5 January is inside the New
    # Year holidays, and the run reaches back to 30 December before it ends.
    assert days == {date(2025, 12, 5), date(2025, 12, 30)}
    assert all(not off(day) for day in days)


def test_a_day_pulled_back_out_of_the_span_is_not_drawn():
    days = claimed("d1~@green", date(2026, 11, 1), date(2026, 11, 30))

    assert days == set()  # 1 November 2026 is a Sunday, and 30 October is outside


def test_a_nominal_day_past_the_end_can_still_land_inside_it():
    """The rule is expanded past the span, or the mark it owes would go missing."""
    # 1 November 2026 is a Sunday, so it is paid on Friday 30 October.
    days = claimed("d1~@green", date(2026, 10, 1), date(2026, 10, 31))

    assert date(2026, 10, 30) in days


# ── Drawing ─────────────────────────────────────────────────────────────────


def marker_tint(style: Style, color: tuple[int, int, int]) -> tuple[int, int, int]:
    """What a marked cell is filled with: the ramp's tint, held back."""
    return lerp(style.background, color, style.ramp.tint * MARKER_TINT)


def halo_ring(lay: L.Layout) -> int:
    """How far the halo stands off the dot, on every side."""
    return round((min(lay.pitch_x, lay.pitch_y) - lay.dot) / 2 * MARKER_INSET)


def tint_at(image, lay: L.Layout, grid, day: date):
    """Mid-width, just inside the halo's top edge: tint there, never the dot."""
    cell = next(c for c in grid.cells if c.day == day)
    _, oy = lay.dot_origin(cell.row, cell.col)
    cx, _ = lay.cell_center(cell.row, cell.col)
    return image.getpixel((round(cx), oy - halo_ring(lay) + 1))


@pytest.mark.parametrize("shape", [Shape.SQUARE, Shape.CIRCLE])
def test_the_halo_stands_off_the_dot_evenly_on_every_side(device: Device, shape: Shape):
    """The cell is not square and the dot is, so a halo cut from the cell slips sideways."""
    grid = build_span(SPAN_START, SPAN_END, TODAY)
    lay = L.compute(device.width, device.height, grid.rows, grid.columns, grid.columns // 7)
    style = Style(
        shape=shape,
        weekends=False,
        marks=False,
        fade=False,
        markers=parse_markers(["we@blue@Gym"]),
    )
    image = render_span(grid, device.width, device.height, style)
    cell = next(c for c in grid.cells if c.day == date(2026, 9, 2))  # a Wednesday
    ox, oy = lay.dot_origin(cell.row, cell.col)

    # The ink inside the cell is the halo; the dot sits inside it at a known box,
    # so the four gaps between the two boxes are the ring.
    box = lay.cell_box(cell.row, cell.col)
    patch = image.crop((box[0], box[1], box[2] + 1, box[3] + 1))
    flat = Image.new("RGB", patch.size, style.background)
    found = ImageChops.difference(patch, flat).getbbox()
    assert found is not None, "nothing was drawn"
    left, top, right, bottom = (
        found[0] + box[0],
        found[1] + box[1],
        found[2] + box[0] - 1,
        found[3] + box[1] - 1,
    )

    sides = [ox - left, right - (ox + lay.dot - 1), oy - top, bottom - (oy + lay.dot - 1)]
    assert max(sides) - min(sides) <= 1, f"the halo is lopsided: {sides}"
    assert min(sides) >= 1, f"the halo vanished into the dot: {sides}"


def test_the_halo_shares_the_dot_s_rounding(device: Device):
    """Offsetting a rounded rectangle by d gives radius r + d. Anything else reads wrong."""
    grid = build_span(SPAN_START, SPAN_END, TODAY)
    lay = L.compute(device.width, device.height, grid.rows, grid.columns, grid.columns // 7)
    ring = halo_ring(lay)

    # The corner the renderer uses, restated here so a change to one has to face
    # the other: half the dot for a circle, the dot's own corner for a square.
    assert round(lay.dot / 2 + ring) == round(lay.dot / 2) + ring
    assert lay.corner + ring > lay.corner, "a halo with the dot's radius would not nest"


def test_only_a_marked_day_takes_the_tint(device: Device):
    grid = build_span(SPAN_START, SPAN_END, TODAY)
    lay = L.compute(device.width, device.height, grid.rows, grid.columns, grid.columns // 7)
    style = Style(weekends=False, marks=False, markers=parse_markers(["we@blue@Gym"]))
    image = render_span(grid, device.width, device.height, style)

    wanted = marker_tint(style, SOLARIZED["blue"])
    assert tint_at(image, lay, grid, date(2026, 9, 2)) == wanted  # Wednesday
    assert tint_at(image, lay, grid, date(2026, 9, 3)) == style.background


def test_the_last_marker_wins_a_day_they_both_claim(device: Device):
    grid = build_span(SPAN_START, SPAN_END, TODAY)
    lay = L.compute(device.width, device.height, grid.rows, grid.columns, grid.columns // 7)
    style = Style(
        weekends=False,
        marks=False,
        markers=parse_markers(["we@blue@Gym", "2026-09-02@red@Dentist"]),
    )
    image = render_span(grid, device.width, device.height, style)

    assert tint_at(image, lay, grid, date(2026, 9, 2)) == marker_tint(style, SOLARIZED["red"])
    assert tint_at(image, lay, grid, date(2026, 9, 9)) == marker_tint(style, SOLARIZED["blue"])


def test_a_marker_is_drawn_over_the_month_end_mark(device: Device):
    """Z-order: the weekend band, then the month end, then the reader's own rules."""
    grid = build_span(date(2026, 9, 1), date(2026, 9, 30), TODAY)
    lay = L.compute(device.width, device.height, grid.rows, grid.columns, grid.columns // 7)
    style = Style(weekends=False, marks=True, markers=parse_markers(["d30@blue"]))
    image = render_span(grid, device.width, device.height, style)

    assert tint_at(image, lay, grid, date(2026, 9, 30)) == marker_tint(style, SOLARIZED["blue"])


# ── Over HTTP ───────────────────────────────────────────────────────────────


def test_a_marker_changes_the_drawing(client: TestClient):
    plain = client.get(f"/w/span.png?{SPAN}")
    marked = client.get(f"/w/span.png?{SPAN}&m=mo,we@blue@Gym")

    assert marked.status_code == 200
    assert marked.content != plain.content
    assert marked.headers["etag"] != plain.headers["etag"]


def test_a_label_never_changes_the_drawing(client: TestClient):
    """It is not drawn: it rides in the link so the builder gets the names back."""
    bare = client.get(f"/w/span.png?{SPAN}&m=mo@blue")
    named = client.get(f"/w/span.png?{SPAN}&m=mo@blue@Gym%20night")

    assert named.status_code == 200
    assert named.content == bare.content


def test_a_broken_marker_is_a_400(client: TestClient):
    assert client.get(f"/w/span.png?{SPAN}&m=someday@blue").status_code == 400
    assert client.get(f"/w/span.png?{SPAN}&m=mo@chartreuse").status_code == 400


def test_too_many_markers_is_a_422_naming_the_cap(client: TestClient):
    query = "&".join(["m=mo@blue"] * (MAX_MARKERS + 1))
    response = client.get(f"/w/span.png?{SPAN}&{query}")

    assert response.status_code == 422
    assert str(MAX_MARKERS) in response.json()["detail"]


def test_the_builder_offers_markers_under_the_same_cap():
    """A page that lets you add more than the server takes builds a dead link."""
    page = files("wallcal.assets").joinpath("index.html").read_text(encoding="utf-8")

    assert 'id="marker-add"' in page
    assert 'id="marker-list"' in page
    assert re.search(rf"MARKER_CAP = {MAX_MARKERS}\b", page)
    assert re.search(rf"MARKER_LABEL_MAX = {MAX_LABEL}\b", page)
