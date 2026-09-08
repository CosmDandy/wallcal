"""Pixel-level checks, run against every shipped screen preset."""

from __future__ import annotations

import hashlib
import io
import math
from datetime import date
from zoneinfo import ZoneInfo

import pytest
from PIL import Image, ImageChops

from wallcal import layout as L
from wallcal.devices import Device
from wallcal.fonts import FONT_REGULAR, load_font
from wallcal.grid import CellState, build_span
from wallcal.palette import lerp, luminance
from wallcal.render import (
    MOON_RATIO,
    MOON_STEPS,
    SKY_GAP,
    BarMode,
    FooterMode,
    HeaderMode,
    Production,
    Shape,
    ShapeError,
    Style,
    _footer_text,
    _moon_masks,
    _sky_line,
    parse_shape,
    render_span,
    to_png,
)
from wallcal.sky import SkyMode

from .conftest import SPAN_END, SPAN_START, TODAY


def grid_of(start=SPAN_START, end=SPAN_END, today=TODAY):
    return build_span(start, end, today)


def pixel_at_cell(image: Image.Image, lay: L.Layout, cell) -> tuple[int, int, int]:
    cx, cy = lay.cell_center(cell.row, cell.col)
    return image.getpixel((round(cx), round(cy)))


def first_cell(grid, state: CellState):
    return next(c for c in grid.cells if c.state is state)


def test_output_matches_the_device_resolution(device: Device):
    image = render_span(grid_of(), device.width, device.height, Style())
    assert image.size == (device.width, device.height)


def test_png_round_trips_at_the_device_resolution(device: Device):
    payload = to_png(render_span(grid_of(), device.width, device.height, Style()))
    assert payload[:8] == b"\x89PNG\r\n\x1a\n"
    with Image.open(io.BytesIO(payload)) as reopened:
        assert reopened.size == (device.width, device.height)
        assert reopened.format == "PNG"


@pytest.mark.parametrize("clock", list(L.CLOCK_TOP))
def test_clock_area_is_left_untouched(device: Device, clock: str):
    """A taller clock has to push the grid down, not have the grid drawn under it."""
    style = Style(clock=clock)
    image = render_span(grid_of(), device.width, device.height, style)
    top = image.crop((0, 0, device.width, int(L.CLOCK_TOP[clock] * device.height)))
    assert top.getcolors(maxcolors=4) == [(top.width * top.height, style.background)]


def test_no_dots_below_the_grid_band(device: Device):
    style = Style(footer=FooterMode.NONE, bar=BarMode.NONE)
    image = render_span(grid_of(), device.width, device.height, style)
    floor = L.grid_floor(device.height)
    bottom = image.crop((0, floor + 1, device.width, device.height))
    assert bottom.getcolors(maxcolors=4) == [(bottom.width * bottom.height, style.background)]


def test_the_footer_clears_the_button_columns(device: Device):
    """It must live in the lane between the flashlight and the camera, not under them."""
    image = render_span(grid_of(), device.width, device.height, Style())
    lay = L.compute(device.width, device.height, 4, 14, 2)
    top = lay.footer_center_y - lay.footer_font
    bottom = lay.footer_center_y + lay.footer_font
    clear = round(L.CONTROLS_CLEAR * device.width)

    left = image.crop((0, top, clear, bottom))
    right = image.crop((device.width - clear, top, device.width, bottom))
    middle = image.crop((clear, top, device.width - clear, bottom))

    assert len(left.getcolors(maxcolors=4)) == 1
    assert len(right.getcolors(maxcolors=4)) == 1
    assert len(middle.getcolors(maxcolors=2**16)) > 1


def test_cell_states_get_their_colors(device: Device):
    style = Style(fade=False)  # fading is checked on its own below
    grid = grid_of()
    lay = L.compute(device.width, device.height, grid.rows, grid.columns, grid.columns // 7)
    image = render_span(grid, device.width, device.height, style)

    assert pixel_at_cell(image, lay, first_cell(grid, CellState.PAST)) == style.ramp.strong
    assert pixel_at_cell(image, lay, first_cell(grid, CellState.TODAY)) == style.accent
    assert pixel_at_cell(image, lay, first_cell(grid, CellState.FUTURE)) == style.ramp.future


def test_outside_cells_are_not_drawn(device: Device):
    style = Style()
    grid = grid_of()
    lay = L.compute(device.width, device.height, grid.rows, grid.columns, grid.columns // 7)
    image = render_span(grid, device.width, device.height, style)

    assert pixel_at_cell(image, lay, first_cell(grid, CellState.OUTSIDE)) == style.background


def test_custom_colors_are_honored(device: Device):
    style = Style(
        background=(0x00, 0x2B, 0x36),
        dot=(0x93, 0xA1, 0xA1),
        accent=(0xCB, 0x4B, 0x16),
        fade=False,
    )
    grid = grid_of()
    lay = L.compute(device.width, device.height, grid.rows, grid.columns, grid.columns // 7)
    image = render_span(grid, device.width, device.height, style)

    assert image.getpixel((0, 0)) == style.background
    assert pixel_at_cell(image, lay, first_cell(grid, CellState.PAST)) == style.dot
    assert pixel_at_cell(image, lay, first_cell(grid, CellState.TODAY)) == style.accent


def test_rendering_is_deterministic(device: Device):
    first = to_png(render_span(grid_of(), device.width, device.height, Style()))
    second = to_png(render_span(grid_of(), device.width, device.height, Style()))
    assert first == second


def ink_coverage(image: Image.Image, lay: L.Layout, cell) -> float:
    """Fraction of the dot's bounding box covered by ink, anti-aliasing included."""
    cx, cy = lay.cell_center(cell.row, cell.col)
    half = lay.dot / 2
    box = image.crop((round(cx - half), round(cy - half), round(cx + half), round(cy + half)))
    darkness = [1 - px[0] / 255 for px in box.convert("RGB").get_flattened_data()]
    return sum(darkness) / len(darkness)


def test_shape_fills_the_cell_the_way_the_geometry_says(device: Device):
    """A circle covers pi/4 of its box; a rounded square, all but four small corners."""
    grid = grid_of()
    lay = L.compute(device.width, device.height, grid.rows, grid.columns, grid.columns // 7)
    cell = first_cell(grid, CellState.PAST)

    circle = render_span(grid, device.width, device.height, Style(shape=Shape.CIRCLE, fade=False))
    square = render_span(grid, device.width, device.height, Style(shape=Shape.SQUARE, fade=False))

    circle_area = math.pi / 4
    corner_loss = (4 - math.pi) * (L.CORNER_RATIO**2)
    assert ink_coverage(circle, lay, cell) == pytest.approx(circle_area, abs=0.05)
    assert ink_coverage(square, lay, cell) == pytest.approx(1 - corner_loss, abs=0.05)


def test_axes_can_be_switched_off(device: Device):
    grid = grid_of()
    lay = L.compute(device.width, device.height, grid.rows, grid.columns, grid.columns // 7)
    band = (0, lay.grid_y - round(lay.axis_font * 1.6), device.width, lay.grid_y - 1)

    with_axes = render_span(grid, device.width, device.height, Style(axes=True))
    without = render_span(grid, device.width, device.height, Style(axes=False))

    assert len(with_axes.crop(band).getcolors(maxcolors=2**16)) > 1
    assert without.crop(band).getcolors(maxcolors=4) == [
        (band[2] * (band[3] - band[1]), Style().background)
    ]


def test_footer_can_be_switched_off(device: Device):
    grid = grid_of()
    lay = L.compute(device.width, device.height, grid.rows, grid.columns, grid.columns // 7)
    band = (
        0,
        lay.footer_center_y - lay.footer_font,
        device.width,
        lay.footer_center_y + lay.footer_font,
    )

    with_footer = render_span(grid, device.width, device.height, Style(footer=FooterMode.PERCENT))
    without = render_span(grid, device.width, device.height, Style(footer=FooterMode.NONE))

    assert len(with_footer.crop(band).getcolors(maxcolors=2**16)) > 1
    assert len(without.crop(band).getcolors(maxcolors=4)) == 1


def test_a_year_still_renders_on_every_device(device: Device):
    grid = grid_of(date(2026, 1, 1), date(2026, 12, 31))
    image = render_span(grid, device.width, device.height, Style())
    assert image.size == (device.width, device.height)
    assert len(image.getcolors(maxcolors=2**16)) > 1


def test_a_span_too_long_for_the_screen_is_refused(device: Device):
    grid = grid_of(date(2012, 1, 1), date(2026, 12, 31))  # 783 weeks: allowed, undrawable
    with pytest.raises(L.LayoutError):
        render_span(grid, device.width, device.height, Style())


@pytest.mark.parametrize(
    ("spec", "expected"),
    [("c", Shape.CIRCLE), ("r", Shape.SQUARE), ("CIRCLE", Shape.CIRCLE), ("square", Shape.SQUARE)],
)
def test_shape_parsing(spec, expected):
    assert parse_shape(spec) is expected


def test_unknown_shape_is_rejected():
    with pytest.raises(ShapeError):
        parse_shape("triangle")


def test_weekday_labels_repeat_for_every_week_in_a_row(device: Device):
    """Two-week rows need the seven weekday letters twice, not fourteen names."""
    grid = grid_of()
    lay = L.compute(device.width, device.height, grid.rows, grid.columns, grid.columns // 7)
    image = render_span(grid, device.width, device.height, Style(footer=FooterMode.NONE))

    band = image.crop(
        (0, lay.header_center_y - lay.axis_font, device.width, lay.header_center_y + lay.axis_font)
    )
    left = band.crop((0, 0, device.width // 2, band.height))
    right = band.crop((device.width // 2, 0, device.width, band.height))

    def ink(part: Image.Image) -> int:
        return sum(1 for px in part.get_flattened_data() if px != Style().background)

    assert ink(left) > 0 and ink(right) > 0
    assert abs(ink(left) - ink(right)) / max(ink(left), ink(right)) < 0.25


def test_weekend_band_sits_under_saturday_and_sunday_only(device: Device):
    grid = grid_of()
    lay = L.compute(device.width, device.height, grid.rows, grid.columns, grid.columns // 7)
    plain = Style(weekends=False, marks=False)
    banded = Style(weekends=True, marks=False)

    with_band = render_span(grid, device.width, device.height, banded)
    without = render_span(grid, device.width, device.height, plain)

    def between_dots(col: int) -> tuple[int, int]:
        """Just above the dot, inside the inset band — where only a band can show."""
        cx, cy = lay.cell_center(0, col)
        return round(cx), round(cy - lay.dot / 2) - 2

    saturday, monday = between_dots(5), between_dots(0)
    assert with_band.getpixel(saturday) != without.getpixel(saturday)
    assert with_band.getpixel(monday) == without.getpixel(monday)


@pytest.mark.parametrize("first_weekday", range(7))
def test_the_weekend_band_follows_the_first_weekday(first_weekday: int):
    """The band tracks Saturday and Sunday, not columns 5 and 6.

    Hard-coded columns put it behind Friday and Saturday at wd=6, while the
    header above it was labelled correctly — the picture contradicted itself.
    """
    grid = build_span(SPAN_START, SPAN_END, TODAY, first_weekday=first_weekday)
    style = Style(first_weekday=first_weekday, weekends=True, marks=False, fade=False)
    lay = L.compute(1179, 2556, grid.rows, grid.columns, grid.columns // 7)
    image = render_span(grid, 1179, 2556, style)

    row = grid.rows // 2
    for col in range(grid.columns):
        x0, y0, _, y1 = lay.cell_box(row, col)
        tinted = image.getpixel((x0 + 1, (y0 + y1) // 2)) != style.background
        cell = next(c for c in grid.cells if c.row == row and c.col == col)
        assert tinted == cell.is_weekend, f"wd={first_weekday} col={col} {cell.day:%a}"


def test_weekend_band_can_be_switched_off(device: Device):
    grid = grid_of()
    off = render_span(grid, device.width, device.height, Style(weekends=False, marks=False))
    ramp = Style().ramp
    dots_only = {Style().background, ramp.strong, ramp.future, Style().accent}
    lay = L.compute(device.width, device.height, grid.rows, grid.columns, grid.columns // 7)
    cx, cy = lay.cell_center(0, 5)
    assert off.getpixel((round(cx), round(cy - lay.dot / 2) - 2)) in dots_only


def test_only_the_last_day_of_a_month_is_tinted(device: Device):
    grid = grid_of(date(2026, 12, 1), date(2027, 1, 31))
    lay = L.compute(device.width, device.height, grid.rows, grid.columns, grid.columns // 7)
    style = Style(weekends=False, marks=True)
    image = render_span(grid, device.width, device.height, style)

    def tint_at(day: date) -> tuple[int, int, int]:
        """Top edge of the cell, mid-width: inside the rounded tint, above the dot."""
        cell = next(c for c in grid.cells if c.day == day)
        _, top, _, _ = lay.cell_box(cell.row, cell.col)
        cx, _ = lay.cell_center(cell.row, cell.col)
        return image.getpixel((round(cx), top + 1))

    tint = lerp(style.background, style.month_mark, style.ramp.tint)
    assert tint_at(date(2026, 12, 31)) == tint
    assert tint_at(date(2027, 1, 1)) == style.background  # new year is no longer special


def test_month_end_is_tinted(device: Device):
    grid = grid_of()
    lay = L.compute(device.width, device.height, grid.rows, grid.columns, grid.columns // 7)
    marked = next(c for c in grid.cells if c.is_month_end and c.state is not CellState.OUTSIDE)
    cx, cy = lay.cell_center(marked.row, marked.col)
    probe = (round(cx), round(cy - lay.pitch_y / 2 + 1))

    with_marks = render_span(grid, device.width, device.height, Style(weekends=False, marks=True))
    without = render_span(grid, device.width, device.height, Style(weekends=False, marks=False))

    assert with_marks.getpixel(probe) != without.getpixel(probe)


def test_fading_makes_older_past_days_fainter(device: Device):
    """The filled run should read as a gradient towards today, not a flat block."""
    grid = grid_of(date(2026, 6, 1), date(2026, 12, 31))
    lay = L.compute(device.width, device.height, grid.rows, grid.columns, grid.columns // 7)
    style = Style(weekends=False, marks=False, fade=True)
    image = render_span(grid, device.width, device.height, style)

    past = [c for c in grid.cells if c.state is CellState.PAST]
    oldest, newest = past[0], past[-1]

    def darkness(cell) -> int:
        cx, cy = lay.cell_center(cell.row, cell.col)
        return 255 - image.getpixel((round(cx), round(cy)))[0]

    assert darkness(oldest) < darkness(newest)
    assert darkness(newest) > 0


def test_fading_can_be_switched_off(device: Device):
    grid = grid_of(date(2026, 6, 1), date(2026, 12, 31))
    lay = L.compute(device.width, device.height, grid.rows, grid.columns, grid.columns // 7)
    image = render_span(grid, device.width, device.height, Style(fade=False))

    past = [c for c in grid.cells if c.state is CellState.PAST]
    for cell in (past[0], past[-1]):
        cx, cy = lay.cell_center(cell.row, cell.col)
        assert image.getpixel((round(cx), round(cy))) == Style().strong


@pytest.mark.parametrize("mode", list(FooterMode))
def test_every_footer_mode_renders(device: Device, mode: FooterMode):
    image = render_span(grid_of(), device.width, device.height, Style(footer=mode))
    assert image.size == (device.width, device.height)


def test_the_bar_fills_with_the_span(device: Device):
    lay = L.compute(device.width, device.height, 7, 14, 2)
    early = render_span(
        grid_of(date(2026, 9, 1), date(2027, 8, 31)),
        device.width,
        device.height,
        Style(bar=BarMode.SPAN),
    )
    late = render_span(
        grid_of(date(2025, 9, 1), date(2026, 9, 30)),
        device.width,
        device.height,
        Style(bar=BarMode.SPAN),
    )

    def filled_width(image: Image.Image) -> int:
        row = image.crop((0, lay.bar_center_y, device.width, lay.bar_center_y + 1))
        return sum(1 for px in row.get_flattened_data() if px == Style().accent)

    assert filled_width(early) < filled_width(late)


def test_the_ramp_follows_the_background_without_being_told(device: Device):
    """One URL, two themes: set the background and every tone follows it."""
    paper, ink = (0xFD, 0xF6, 0xE3), (0x00, 0x2B, 0x36)
    light = Style(background=paper).ramp
    dark = Style(background=ink).ramp

    assert luminance(light.strong) < luminance(paper)
    assert luminance(dark.strong) > luminance(ink)
    # The fade runs towards the background at both ends, never past it.
    assert luminance(light.faint) > luminance(light.strong)
    assert luminance(dark.faint) < luminance(dark.strong)


def test_tones_stay_off_neutral_grey(device: Device):
    """A neutral grey next to the orange accent reads green; Solarized's do not.

    The strong end is exempt: on a dark background it is deliberately pure white,
    to hold its own against the white lock screen clock.
    """
    for background in ((0xFD, 0xF6, 0xE3), (0x00, 0x2B, 0x36), (0, 0, 0), (255, 255, 255)):
        ramp = Style(background=background).ramp
        for tone in (ramp.faint, ramp.axis, ramp.footer):
            assert max(tone) - min(tone) > 4, f"{tone} is neutral grey on {background}"


def test_dark_backgrounds_get_a_pure_white_strong_end(device: Device):
    for background in ((0x00, 0x2B, 0x36), (0x1C, 0x1C, 0x1E), (0, 0, 0)):
        assert Style(background=background).ramp.strong == (0xFF, 0xFF, 0xFF)


def test_an_explicit_dot_color_still_overrides_the_ramp(device: Device):
    style = Style(background=(0, 0, 0), dot=(0xFF, 0xFF, 0xFF))
    assert style.ramp.strong == (0xFF, 0xFF, 0xFF)


def test_the_quote_lands_under_the_grid_and_above_the_footer(device: Device):
    grid = grid_of()
    plain = L.compute(device.width, device.height, grid.rows, grid.columns, grid.columns // 7)
    with_quote = L.compute(
        device.width, device.height, grid.rows, grid.columns, grid.columns // 7, quote=True
    )
    image = render_span(grid, device.width, device.height, Style(quote=True))

    # Reserving the band shortens the grid rather than overlapping it.
    assert with_quote.grid_height <= plain.grid_height
    assert with_quote.quote_center_y > with_quote.grid_y + with_quote.grid_height
    assert with_quote.quote_center_y < with_quote.footer_center_y

    band = image.crop(
        (
            0,
            with_quote.quote_center_y - with_quote.quote_font * 2,
            device.width,
            with_quote.quote_center_y + with_quote.quote_font * 2,
        )
    )
    assert len(band.getcolors(maxcolors=2**16)) > 1, "no quote drawn"


def test_no_quote_band_when_the_quote_is_off(device: Device):
    grid = grid_of()
    lay = L.compute(device.width, device.height, grid.rows, grid.columns, grid.columns // 7)
    image = render_span(grid, device.width, device.height, Style(quote=False))
    quoted = L.compute(
        device.width, device.height, grid.rows, grid.columns, grid.columns // 7, quote=True
    )

    assert lay.quote_center_y == 0
    band = image.crop((0, quoted.quote_center_y - 20, device.width, quoted.quote_center_y + 20))
    assert len(band.getcolors(maxcolors=4)) == 1


def test_cream_ink_uses_the_solarized_end_instead_of_pure_white(device: Device):
    dark = (0x00, 0x2B, 0x36)
    assert Style(background=dark, ink="bright").ramp.strong == (0xFF, 0xFF, 0xFF)
    assert Style(background=dark, ink="cream").ramp.strong == (0xEE, 0xE8, 0xD5)

    paper = (0xFD, 0xF6, 0xE3)
    assert Style(background=paper, ink="bright").ramp.strong == (0x07, 0x36, 0x42)
    assert Style(background=paper, ink="cream").ramp.strong == (0x58, 0x6E, 0x75)


def test_a_line_of_your_own_draws_without_asking_for_the_rotation(device: Device):
    """Writing a quote is asking for one; q=1 is only about the daily rotation."""
    grid = grid_of()
    off = Style(quote=False)
    own = Style(quote=False, quote_text="Ship it")

    assert not off.shows_quote
    assert own.shows_quote
    assert (
        render_span(grid, device.width, device.height, own).tobytes()
        != render_span(grid, device.width, device.height, off).tobytes()
    )


def test_the_rotation_and_a_custom_line_never_both_appear(device: Device):
    """With both set, the custom line wins — there is one slot, not two."""
    grid = grid_of()
    custom = Style(quote=True, quote_text="Ship it", quote_author="Nobody")
    fixed = Style(quote=False, quote_text="Ship it", quote_author="Nobody")

    left = render_span(grid, device.width, device.height, custom)
    right = render_span(grid, device.width, device.height, fixed)
    assert left.tobytes() == right.tobytes()


def header_band(image: Image.Image, lay: L.Layout) -> Image.Image:
    top = lay.header_center_y - lay.axis_font
    return image.crop((0, top, lay.width, lay.header_center_y + lay.axis_font))


def test_the_top_axis_can_count_days_instead_of_naming_them(device: Device):
    """7 and 14 over the day each week ends on, rather than seven letters twice."""
    grid = grid_of()
    lay = L.compute(device.width, device.height, grid.rows, grid.columns, grid.columns // 7)

    days = render_span(grid, device.width, device.height, Style(header=HeaderMode.DAYS))
    count = render_span(grid, device.width, device.height, Style(header=HeaderMode.COUNT))
    blank = render_span(grid, device.width, device.height, Style(header=HeaderMode.NONE))

    def ink(image: Image.Image) -> int:
        band = header_band(image, lay)
        return sum(1 for px in band.get_flattened_data() if px != Style().background)

    assert ink(blank) == 0
    assert 0 < ink(count) < ink(days), "counting should be quieter than naming"


def test_counting_puts_a_number_over_the_end_of_each_week(device: Device):
    grid = grid_of()
    lay = L.compute(device.width, device.height, grid.rows, grid.columns, grid.columns // 7)
    image = render_span(grid, device.width, device.height, Style(header=HeaderMode.COUNT))

    def ink_above(col: int) -> int:
        x, _ = lay.cell_center(0, col)
        strip = image.crop(
            (
                round(x) - lay.pitch_x // 2,
                lay.header_center_y - lay.axis_font,
                round(x) + lay.pitch_x // 2,
                lay.header_center_y + lay.axis_font,
            )
        )
        return sum(1 for px in strip.get_flattened_data() if px != Style().background)

    assert ink_above(6) > 0 and ink_above(13) > 0  # ends of both weeks
    assert ink_above(0) == 0 and ink_above(3) == 0  # nothing over the other days


# The production calendar: the band stops being two fixed columns and becomes the
# union of whatever days are not worked.

# Captured from the drawing before the band learned about production calendars.
# The union has to reduce to exactly those shapes when nothing moves the days
# off, and a hash is the only assertion that can say "exactly".
# Digests of the band as the column-drawing code left it, carried across the
# rewrite that turned it into a union of cells: with no production calendar the
# new code draws the old picture. Two entries are marked, and are the exception
# that proves it — with Sunday starting the week and no gap between weeks, the
# old code left a two-pixel notch where Saturday met Sunday across the boundary.
# Closing that is the whole point of the rewrite, so those two are new pictures
# on purpose. Every other one of the forty-two is byte-identical.
BAND_GOLDEN = {
    (0, True, 1): "5dc3b99f78413e8a",
    (0, True, 2): "6850c38526da92f0",
    (0, True, 4): "7908bbdb8dc1615d",
    (0, False, 1): "5dc3b99f78413e8a",
    (0, False, 2): "3e27864adb44f7cc",
    (0, False, 4): "e3a877b5447f1e8b",
    (1, True, 1): "e9d7664812dbada5",
    (1, True, 2): "9818b36a74850c53",
    (1, True, 4): "5de4e7c3cf7b090f",
    (1, False, 1): "e9d7664812dbada5",
    (1, False, 2): "2fb8538210abc3cb",
    (1, False, 4): "2578607015defd52",
    (2, True, 1): "d7100c2362384fa3",
    (2, True, 2): "79996776858c888f",
    (2, True, 4): "773e88aff29afb2c",
    (2, False, 1): "d7100c2362384fa3",
    (2, False, 2): "c08ba1eaecba6019",
    (2, False, 4): "c6fcdade1d1add63",
    (3, True, 1): "0137c876caf62b81",
    (3, True, 2): "44049cb65cd49174",
    (3, True, 4): "04ffd96ae1d98e7d",
    (3, False, 1): "0137c876caf62b81",
    (3, False, 2): "acf46c43a1b59983",
    (3, False, 4): "dd84dc2cc1a45489",
    (4, True, 1): "97dd01cee35f7606",
    (4, True, 2): "a86d1bfd9d011a89",
    (4, True, 4): "ef21ff63e01ad27b",
    (4, False, 1): "97dd01cee35f7606",
    (4, False, 2): "c399e72f99e98513",
    (4, False, 4): "b91beb4b78fd71dd",
    (5, True, 1): "33cd4ff2a0c95059",
    (5, True, 2): "d75baec2c7162890",
    (5, True, 4): "c390556803ed026b",
    (5, False, 1): "33cd4ff2a0c95059",
    (5, False, 2): "b617644fc910a884",
    (5, False, 4): "a799289727ba4549",
    (6, True, 1): "b09ac533b85db718",
    (6, True, 2): "7491c4a82aef591c",
    (6, True, 4): "b9684601fc81969a",
    (6, False, 1): "b09ac533b85db718",
    (6, False, 2): "2aedbe7de1811382",  # the notch, now closed
    (6, False, 4): "10645a072fe80fd1",  # the notch, now closed
}


@pytest.mark.parametrize(("first_weekday", "split", "groups"), sorted(BAND_GOLDEN))
def test_no_production_calendar_draws_exactly_what_it_always_did(
    first_weekday: int, split: bool, groups: int
):
    grid = build_span(
        SPAN_START, SPAN_END, TODAY, weeks_per_row=groups, first_weekday=first_weekday
    )
    style = Style(first_weekday=first_weekday, split=split)
    payload = to_png(render_span(grid, 590, 1278, style))
    digest = hashlib.sha256(payload).hexdigest()[:16]
    assert digest == BAND_GOLDEN[first_weekday, split, groups]


def ru_span(start: date, end: date, today: date):
    """A span drawn against the Russian calendar, with the geometry to probe it."""
    grid = build_span(start, end, today)
    style = Style(production=Production.RU, marks=False, weekends=True)
    lay = L.compute(1179, 2556, grid.rows, grid.columns, grid.columns // 7)
    return grid, lay, style, render_span(grid, 1179, 2556, style)


# June 2025: Thursday the 12th is Russia Day and Friday the 13th was moved there
# from March, so Thursday through Sunday is one run of days nobody works.
JUNE = (date(2025, 6, 1), date(2025, 6, 30), date(2025, 6, 15))
JUNE_ROW = 1  # 9-22 June, the row that holds the run


def test_a_non_working_friday_joins_the_weekend_band():
    _, lay, style, image = ru_span(*JUNE)
    top = lay.cell_box(JUNE_ROW, 0)[1]

    # Right on the seam between Friday and Saturday, along the band's top edge:
    # two rounded rectangles would have pinched the colour away here.
    assert image.getpixel((lay.cell_box(JUNE_ROW, 4)[2], top)) == style.ramp.weekend


def test_two_adjacent_non_working_weekdays_merge():
    _, lay, style, image = ru_span(*JUNE)
    top = lay.cell_box(JUNE_ROW, 0)[1]

    assert image.getpixel((lay.cell_box(JUNE_ROW, 3)[2], top)) == style.ramp.weekend


def test_the_outer_corners_of_a_merged_band_stay_rounded():
    _, lay, style, image = ru_span(*JUNE)
    top = lay.cell_box(JUNE_ROW, 0)[1]

    # Thursday's top-left is where the shape actually begins, so it rounds.
    assert image.getpixel((lay.cell_box(JUNE_ROW, 3)[0], top)) == style.background


def test_a_wider_run_does_not_scallop_the_row_above_it():
    """The weekend pill runs on through June's longer run instead of pinching at it."""
    _, lay, style, image = ru_span(*JUNE)
    seam = lay.cell_box(JUNE_ROW, 0)[1]
    left = lay.cell_box(JUNE_ROW, 5)[0]  # Saturday's left edge, shared by both rows

    assert image.getpixel((left, seam - 1)) == style.ramp.weekend
    assert image.getpixel((left, seam)) == style.ramp.weekend


# November 2025: the day off for Saturday the 1st was moved to Monday the 3rd,
# so the Saturday is worked and Sunday-Monday-Tuesday is a run of three.
NOVEMBER = (date(2025, 11, 1), date(2025, 11, 30), date(2025, 11, 10))


def above_dot(image: Image.Image, lay: L.Layout, row: int, col: int):
    """Between the dot and the top of its cell - where only a band can show."""
    cx, cy = lay.cell_center(row, col)
    return image.getpixel((round(cx), round(cy - lay.dot / 2) - 2))


def test_a_working_saturday_loses_its_band():
    grid, lay, style, image = ru_span(*NOVEMBER)
    saturday = next(c for c in grid.cells if c.day == date(2025, 11, 1))

    assert above_dot(image, lay, saturday.row, saturday.col) == style.background
    plain = render_span(grid, 1179, 2556, Style(marks=False))
    assert above_dot(plain, lay, saturday.row, saturday.col) == style.ramp.weekend


def test_a_transferred_monday_and_tuesday_are_one_band():
    grid, lay, style, image = ru_span(*NOVEMBER)
    monday = next(c for c in grid.cells if c.day == date(2025, 11, 3))
    top = lay.cell_box(monday.row, 0)[1]

    assert above_dot(image, lay, monday.row, monday.col) == style.ramp.weekend
    assert image.getpixel((lay.cell_box(monday.row, monday.col)[2], top)) == style.ramp.weekend


def test_the_band_stops_at_the_gap_between_the_weeks():
    """Sunday and Monday are both days off here, and the gap still separates them.

    The gap is what makes a row read as two weeks rather than fourteen days; a
    band reaching over it would be the only mark in the drawing that denies that.
    """
    _, lay, style, image = ru_span(*NOVEMBER)
    sunday_row, sunday_col = 0, 6  # 2 November, the last day of the row's first week
    _, top, right, bottom = lay.cell_box(sunday_row, sunday_col)
    middle = (top + bottom) // 2

    assert lay.group_gap > 2, "no gap to test"
    for x in range(right + 1, lay.cell_box(sunday_row, sunday_col + 1)[0]):
        assert image.getpixel((x, middle)) == style.background


def test_a_run_crosses_a_week_boundary_only_when_no_gap_separates_them():
    """With sp=0 the weeks are flush, and a seam there is a notch, not a break."""
    # 2 November 2025 is a Sunday and the 3rd is the day off moved off Saturday
    # the 1st, so with two weeks to a row they are the last and first columns of
    # the two halves.
    grid = build_span(date(2025, 11, 1), date(2025, 11, 30), date(2025, 11, 10))
    by_day = {cell.day: cell for cell in grid.cells}
    sunday, monday = by_day[date(2025, 11, 2)], by_day[date(2025, 11, 3)]
    assert sunday.row == monday.row and monday.col % 7 == 0, "the fixture moved"

    for split, wanted in ((False, 0), (True, None)):
        style = Style(production=Production.RU, marks=False, split=split)
        image = render_span(grid, 1179, 2556, style)
        lay = L.compute(1179, 2556, grid.rows, grid.columns, grid.columns // 7, split=split)
        left = lay.cell_box(sunday.row, sunday.col)
        right = lay.cell_box(monday.row, monday.col)
        # Up where the corners curve: a notch shows here before it shows at the
        # widest part of the band.
        y = left[1] + (left[3] - left[1]) // 4
        bare = sum(
            image.getpixel((x, y)) == style.background for x in range(left[2] - 1, right[0] + 2)
        )
        if wanted is None:
            assert bare == lay.group_gap + 2, "the gap should be the whole of the break"
        else:
            assert bare == wanted, "flush weeks must leave no notch"


def band_bounds(image: Image.Image, lay: L.Layout) -> tuple[int, int, int, int] | None:
    """The ink between the grid's last row and the footer's own strip."""
    top = lay.grid_y + lay.grid_height
    strip = image.crop((0, top, lay.width, L.quote_floor(lay.height)))
    flat = Image.new("RGB", strip.size, Style().background)
    found = ImageChops.difference(strip, flat).getbbox()
    if found is None:
        return None
    return found[0], found[1] + top, found[2], found[3] + top


def sky_layout(grid, device: Device, style: Style) -> L.Layout:
    return L.compute(
        device.width,
        device.height,
        grid.rows,
        grid.columns,
        grid.columns // 7,
        quote=style.shows_band,
        clock=style.clock,
    )


def footer_ink(image: Image.Image, lay: L.Layout, style: Style) -> tuple[int, int, int, int] | None:
    """The ink in the lane between the lock screen buttons."""
    reach = lay.footer_font * 2
    top = lay.footer_center_y - reach
    strip = image.crop((0, top, lay.width, lay.footer_center_y + reach))
    flat = Image.new("RGB", strip.size, style.background)
    found = ImageChops.difference(strip, flat).getbbox()
    if found is None:
        return None
    return found[0], found[1] + top, found[2], found[3] + top


def test_the_moon_rides_the_footer_line(device: Device):
    """It sits in the lane the footer already owns, sized to that line's type."""
    grid = grid_of()
    style = Style(sky=SkyMode.MOON, footer=FooterMode.NONE, bar=BarMode.NONE)
    lay = sky_layout(grid, device, style)
    image = render_span(grid, device.width, device.height, style)

    bounds = footer_ink(image, lay, style)
    assert bounds is not None, "nothing was drawn in the lane"
    left, top, right, bottom = bounds
    size = round(lay.footer_font * MOON_RATIO)

    assert bottom - top == pytest.approx(size, abs=2)
    assert right - left == pytest.approx(size, abs=2)
    assert (top + bottom) / 2 == pytest.approx(lay.footer_center_y, abs=2)
    assert (left + right) / 2 == pytest.approx(lay.width / 2, abs=2)


def test_the_sky_costs_the_field_nothing(device: Device):
    """It moved into the lane precisely so the dots stop paying for it."""
    grid = grid_of(date(2026, 1, 1), date(2026, 12, 31))  # the span that fills a band
    bare, lit = Style(), Style(sky=SkyMode.MOON)

    assert sky_layout(grid, device, bare) == sky_layout(grid, device, lit)

    lay = sky_layout(grid, device, bare)
    plain = render_span(grid, device.width, device.height, bare)
    drawn = render_span(grid, device.width, device.height, lit)
    for cell in grid.cells:
        if cell.state is not CellState.OUTSIDE:
            assert pixel_at_cell(plain, lay, cell) == pixel_at_cell(drawn, lay, cell)


def test_only_the_quote_reserves_the_band(device: Device):
    grid = grid_of(date(2026, 1, 1), date(2026, 12, 31))
    bare = sky_layout(grid, device, Style())
    lit = sky_layout(grid, device, Style(sky=SkyMode.MOON))
    written = sky_layout(grid, device, Style(quote=True))

    assert bare.quote_center_y == lit.quote_center_y == 0
    assert written.quote_center_y > written.grid_y + written.grid_height
    assert written.pitch_y < bare.pitch_y


def test_the_lane_gives_up_the_day_length_before_it_gives_up_size():
    """The two clock times are what nothing else on the screen says, so they stay."""
    grid = grid_of()
    zone = ZoneInfo("Europe/Moscow")
    moscow = (55.75, 37.62)

    alone = Style(footer=FooterMode.NONE, sky=SkyMode.BOTH, location=moscow)
    beside = Style(footer=FooterMode.WEEK, sky=SkyMode.BOTH, location=moscow)

    full = _footer_text(grid, alone, zone, brief=False)
    assert "05:43" in full and "19:10" in full  # the day's two ends
    assert "13:27" in full  # its length
    assert "\u2212" in full or "+" in full  # and how that changed overnight

    # Beside a footer line the lane cannot hold all of it, and the length goes.
    short = _footer_text(grid, beside, zone, brief=True)
    assert "05:43" in short and "19:10" in short
    assert "\u2212" not in short and "13:27" not in short


def test_nothing_in_the_lane_is_ever_shrunk_to_fit_on_a_shipped_screen(device: Device):
    """The give-up rule exists so the type size never has to move. Check it does not."""
    grid = grid_of()
    zone = ZoneInfo("Europe/Moscow")
    for footer in (FooterMode.WEEK, FooterMode.PERCENT, FooterMode.NONE):
        style = Style(footer=footer, sky=SkyMode.BOTH, location=(55.75, 37.62))
        lay = sky_layout(grid, device, style)
        font = load_font(FONT_REGULAR, lay.footer_font)
        text = _footer_text(grid, style, zone, brief=False)
        if font.getlength(text) > lay.footer_max_width:
            text = _footer_text(grid, style, zone, brief=True)
        moon = round(lay.footer_font * MOON_RATIO)
        gap = round(lay.footer_font * SKY_GAP) if text else 0
        assert moon + gap + font.getlength(text) <= lay.footer_max_width


def test_the_sky_and_a_quote_no_longer_compete():
    """They are in two different places now, so neither has to outrank the other."""
    both = Style(sky=SkyMode.MOON, quote=True)
    assert both.shows_sky and both.shows_quote

    written = Style(sky=SkyMode.MOON, quote_text="mine")
    assert written.shows_sky and written.shows_quote


def test_the_rotation_still_wins_when_no_sky_was_asked_for():
    assert Style(quote=True).shows_quote
    assert Style(quote=True, sky=SkyMode.NONE).shows_quote


@pytest.mark.parametrize(
    ("fraction", "expected"),
    [(0.0, "none"), (0.5, "half"), (1.0, "all")],
)
def test_the_terminator_walks_the_disc(fraction: float, expected: str):
    disc, lit = _moon_masks(64, round(fraction * MOON_STEPS), True)
    whole = sum(disc.get_flattened_data())
    part = sum(lit.get_flattened_data())

    if expected == "none":
        assert part == 0
    elif expected == "all":
        assert part == pytest.approx(whole, rel=0.001)
    else:
        assert part == pytest.approx(whole / 2, rel=0.02)


def test_a_gibbous_moon_bulges_past_the_half_disc():
    """The construction the folk one cannot do: more than half lit, and not a disc."""
    disc, half = _moon_masks(64, MOON_STEPS // 2, True)
    _, gibbous = _moon_masks(64, round(0.75 * MOON_STEPS), True)

    def ink(mask: Image.Image) -> int:
        return sum(mask.get_flattened_data())

    assert ink(half) < ink(gibbous) < ink(disc)


def test_a_waxing_moon_is_lit_on_the_right():
    """Cusps to the left, as seen from the northern hemisphere; mirrored below it."""
    _, waxing = _moon_masks(64, round(0.25 * MOON_STEPS), True)
    _, waning = _moon_masks(64, round(0.25 * MOON_STEPS), False)

    def weight(mask: Image.Image, box: tuple[int, int, int, int]) -> int:
        return sum(mask.crop(box).get_flattened_data())

    left, right = (0, 0, 32, 64), (32, 0, 64, 64)
    assert weight(waxing, right) > weight(waxing, left)
    assert weight(waning, left) > weight(waning, right)


def sun_line(day: date, dl: bool, zone: str, place: tuple[float, float]) -> str:
    style = Style(sky=SkyMode.SUN, location=place, day_length=dl)
    return _sky_line(day, style, place, ZoneInfo(zone))


def test_the_day_length_can_be_dropped_from_the_line():
    line = sun_line(date(2026, 9, 8), False, "Europe/London", (51.51, -0.13))
    assert line == "06:24 – 19:31"


def test_a_day_running_past_midnight_keeps_its_length():
    """`01:31 – 00:02` reads as a 23-minute day; only the length says otherwise.

    The fortnight either side of a polar spell has the sun setting after local
    midnight, so the pair alone is backwards. The length goes in even when `dl`
    asked for no numbers — it is not a statistic there, it is the disambiguator.
    """
    tromso = (69.65, 18.96)
    wrapped = sun_line(date(2026, 5, 16), False, "Europe/Oslo", tromso)

    assert wrapped.startswith("01:31 – 00:02")
    assert wrapped.endswith("· 22:31"), wrapped
