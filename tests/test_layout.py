"""Geometry must hold on every screen we ship a preset for."""

from __future__ import annotations

import pytest

from wallcal import layout as L
from wallcal.devices import Device
from wallcal.fonts import FONT_LIGHT, load_font
from wallcal.grid import DAYS_PER_WEEK
from wallcal.strings import MONTHS

GROUPS = 2
COLUMNS = GROUPS * DAYS_PER_WEEK
ROW_COUNTS = [1, 3, 7, 27]


@pytest.mark.parametrize("rows", ROW_COUNTS)
def test_grid_stays_inside_the_safe_area(device: Device, rows: int):
    lay = L.compute(device.width, device.height, rows, COLUMNS, GROUPS)
    top = L.SAFE_TOP * device.height
    bottom = L.SAFE_BOTTOM * device.height

    assert lay.grid_y - lay.axis_font >= top, "weekday header intrudes on the clock"
    assert lay.grid_y + lay.grid_height <= bottom


@pytest.mark.parametrize("rows", ROW_COUNTS)
def test_grid_and_labels_stay_inside_the_side_margins(device: Device, rows: int):
    lay = L.compute(device.width, device.height, rows, COLUMNS, GROUPS)
    margin = round(L.SIDE_MARGIN * device.width)

    assert lay.grid_x >= margin
    assert lay.grid_x + lay.grid_width <= device.width - margin

    # Measured, not estimated: week numbers next to the dots, sideways month
    # names outside them, both clear of the margin.
    font = load_font(FONT_LIGHT, lay.axis_font)
    week_w = max(font.getlength(str(n)) for n in range(1, 54))
    every_month = [name for names in MONTHS.values() for name in names]
    month_h = max(font.getbbox(name)[3] - font.getbbox(name)[1] for name in every_month)

    assert lay.week_label_x - week_w >= lay.month_center_x + month_h / 2
    assert lay.month_center_x - month_h / 2 >= margin


@pytest.mark.parametrize("rows", ROW_COUNTS)
def test_pitches_are_whole_pixels_within_the_aspect_cap(device: Device, rows: int):
    lay = L.compute(device.width, device.height, rows, COLUMNS, GROUPS)

    assert isinstance(lay.pitch_x, int) and isinstance(lay.pitch_y, int)
    assert min(lay.pitch_x, lay.pitch_y) >= L.MIN_PITCH
    assert lay.pitch_x <= lay.pitch_y * L.WIDEN_CAP + 0.01
    assert lay.pitch_y <= lay.pitch_x * L.STRETCH_CAP + 0.01


@pytest.mark.parametrize("rows", ROW_COUNTS)
def test_dot_never_overflows_its_cell(device: Device, rows: int):
    lay = L.compute(device.width, device.height, rows, COLUMNS, GROUPS)
    assert lay.dot <= min(lay.pitch_x, lay.pitch_y)
    assert lay.corner * 2 <= lay.dot


def test_cell_centers_are_evenly_spaced(device: Device):
    lay = L.compute(device.width, device.height, 7, COLUMNS, GROUPS)
    xs = [lay.cell_center(0, c)[0] for c in range(DAYS_PER_WEEK)]
    ys = [lay.cell_center(r, 0)[1] for r in range(7)]

    assert {round(b - a, 6) for a, b in zip(xs, xs[1:], strict=False)} == {float(lay.pitch_x)}
    assert {round(b - a, 6) for a, b in zip(ys, ys[1:], strict=False)} == {float(lay.pitch_y)}


def test_a_span_too_long_for_the_screen_is_refused(device: Device):
    with pytest.raises(L.LayoutError):
        L.compute(device.width, device.height, 700, COLUMNS, GROUPS)


@pytest.mark.parametrize("rows", ROW_COUNTS)
def test_dots_are_centered_on_the_screen(device: Device, rows: int):
    """Axes live in reserves on both sides, so they never push the grid off center."""
    lay = L.compute(device.width, device.height, rows, COLUMNS, GROUPS)
    left = lay.grid_x
    right = device.width - (lay.grid_x + lay.grid_width)
    assert abs(left - right) <= 1  # odd leftovers cost at most a pixel


@pytest.mark.parametrize("columns", [DAYS_PER_WEEK, 2 * DAYS_PER_WEEK, 4 * DAYS_PER_WEEK])
def test_every_grouping_lays_out(device: Device, columns: int):
    lay = L.compute(device.width, device.height, 7, columns, columns // DAYS_PER_WEEK)
    assert lay.columns == columns
    assert lay.grid_width <= device.width - 2 * round(L.SIDE_MARGIN * device.width)


def test_axis_type_is_small_next_to_the_dots(device: Device):
    lay = L.compute(device.width, device.height, 7, COLUMNS, GROUPS)
    assert lay.axis_font < lay.dot
    assert lay.axis_font <= round(L.AXIS_MAX * device.height)


def test_the_split_opens_a_gap_between_weeks_and_nowhere_else(device: Device):
    lay = L.compute(device.width, device.height, 7, COLUMNS, GROUPS, split=True)
    steps = [
        round(lay.cell_center(0, c + 1)[0] - lay.cell_center(0, c)[0]) for c in range(COLUMNS - 1)
    ]

    assert lay.group_gap > 0
    assert steps[DAYS_PER_WEEK - 1] == lay.pitch_x + lay.group_gap  # Sunday to Monday
    assert set(steps) - {lay.pitch_x + lay.group_gap} == {lay.pitch_x}


def test_the_split_can_be_switched_off(device: Device):
    joined = L.compute(device.width, device.height, 7, COLUMNS, GROUPS, split=False)
    steps = {
        round(joined.cell_center(0, c + 1)[0] - joined.cell_center(0, c)[0])
        for c in range(COLUMNS - 1)
    }

    assert joined.group_gap == 0
    assert steps == {joined.pitch_x}


@pytest.mark.parametrize("split", [True, False])
def test_dots_stay_centered_with_or_without_the_split(device: Device, split: bool):
    lay = L.compute(device.width, device.height, 7, COLUMNS, GROUPS, split=split)
    left = lay.grid_x
    right = device.width - (lay.grid_x + lay.grid_width)
    assert abs(left - right) <= 1


@pytest.mark.parametrize("rows", ROW_COUNTS)
def test_rows_are_not_stretched_far_past_the_column_step(device: Device, rows: int):
    """Vertical air is what made the field look sparse; keep pitch_y near pitch_x."""
    lay = L.compute(device.width, device.height, rows, COLUMNS, GROUPS)
    assert lay.pitch_y <= lay.pitch_x * L.STRETCH_CAP + 0.01


def test_footer_sits_in_the_lane_between_the_lock_screen_buttons(device: Device):
    lay = L.compute(device.width, device.height, 7, COLUMNS, GROUPS)

    assert lay.footer_center_y == round(L.CONTROLS_ROW * device.height)
    assert lay.footer_center_y > lay.grid_y + lay.grid_height, "footer overlaps the grid"
    assert lay.footer_max_width == device.width - 2 * round(L.CONTROLS_CLEAR * device.width)


@pytest.mark.parametrize("rows", ROW_COUNTS)
def test_the_dot_sits_dead_center_in_its_cell(device: Device, rows: int):
    """A tint drawn on the cell box must sit evenly around the dot, not 2px off."""
    lay = L.compute(device.width, device.height, rows, COLUMNS, GROUPS)

    for col in (0, 5, DAYS_PER_WEEK, COLUMNS - 1):
        left, top, right, bottom = lay.cell_box(0, col)
        ox, oy = lay.dot_origin(0, col)

        assert ox - left == right - (ox + lay.dot - 1)
        assert oy - top == bottom - (oy + lay.dot - 1)
        assert right - left + 1 == lay.pitch_x
        assert bottom - top + 1 == lay.pitch_y


@pytest.mark.parametrize("side", list(L.LabelSide))
def test_dots_stay_centered_whatever_side_the_labels_take(device: Device, side):
    lay = L.compute(device.width, device.height, 7, COLUMNS, GROUPS, labels=side)
    left = lay.grid_x
    right = device.width - (lay.grid_x + lay.grid_width)
    assert abs(left - right) <= 1


def test_labels_left_read_months_then_weeks_then_dots(device: Device):
    lay = L.compute(device.width, device.height, 7, COLUMNS, GROUPS, labels=L.LabelSide.LEFT)
    assert lay.week_label_anchor == "rm"
    assert lay.month_center_x < lay.week_label_x <= lay.grid_x


def test_labels_right_read_dots_then_weeks_then_months(device: Device):
    lay = L.compute(device.width, device.height, 7, COLUMNS, GROUPS, labels=L.LabelSide.RIGHT)
    assert lay.week_label_anchor == "lm"
    assert lay.grid_x + lay.grid_width <= lay.week_label_x < lay.month_center_x


def test_split_puts_weeks_left_and_months_right_at_equal_distance(device: Device):
    lay = L.compute(device.width, device.height, 7, COLUMNS, GROUPS, labels=L.LabelSide.SPLIT)
    grid_right = lay.grid_x + lay.grid_width - 1

    assert lay.week_label_x < lay.grid_x
    assert lay.month_center_x > grid_right
    left_clearance = lay.grid_x - lay.week_label_x
    right_clearance = lay.month_center_x - lay.month_band_half() - grid_right
    assert abs(left_clearance - right_clearance) <= 1


def test_every_placement_keeps_labels_on_screen(device: Device):
    base = L.compute(device.width, device.height, 7, COLUMNS, GROUPS)
    font = load_font(FONT_LIGHT, base.axis_font)
    every_month = [name for names in MONTHS.values() for name in names]
    widest_month = max(font.getbbox(name)[3] - font.getbbox(name)[1] for name in every_month)
    week_w = max(font.getlength(str(n)) for n in range(1, 54))

    for side in L.LabelSide:
        lay = L.compute(device.width, device.height, 7, COLUMNS, GROUPS, labels=side)
        assert lay.month_center_x - widest_month / 2 >= 0
        assert lay.month_center_x + widest_month / 2 <= device.width
        near = lay.week_label_x - week_w if lay.week_label_anchor == "rm" else lay.week_label_x
        far = lay.week_label_x if lay.week_label_anchor == "rm" else lay.week_label_x + week_w
        assert near >= 0 and far <= device.width


@pytest.mark.parametrize("rows", [3, 7, 10])
def test_a_big_clock_pushes_the_grid_down(device: Device, rows: int):
    standard = L.compute(device.width, device.height, rows, COLUMNS, GROUPS, clock="std")
    large = L.compute(device.width, device.height, rows, COLUMNS, GROUPS, clock="big")
    assert large.grid_y >= L.CLOCK_TOP["big"] * device.height
    assert large.grid_y + large.grid_height <= L.SAFE_BOTTOM * device.height
    # The preset lowers the ceiling and nothing else, so a centred block moves by
    # half of it. Going further is the nudge's job, not the clock's.
    assert large.grid_y > standard.grid_y


@pytest.mark.parametrize(("clock", "shift"), [("std", 0), ("std", -6), ("big", 0), ("big", 6)])
def test_the_quote_sits_midway_between_the_grid_and_the_buttons(
    device: Device, clock: str, shift: int
):
    """Its place is defined by the two things around it, so it follows both."""
    lay = L.compute(
        device.width, device.height, 7, COLUMNS, GROUPS, quote=True, clock=clock, shift=shift
    )
    floor = round(
        L.CONTROLS_ROW * device.height
        - L.CONTROLS_RADIUS * device.width
        - L.QUOTE_CLEARANCE * device.height
    )
    expected = (lay.grid_y + lay.grid_height + floor) // 2

    assert lay.quote_center_y == expected
    assert lay.grid_y + lay.grid_height < lay.quote_center_y < floor


def test_moving_the_grid_moves_the_quote_with_it(device: Device):
    up = L.compute(device.width, device.height, 7, COLUMNS, GROUPS, quote=True, shift=-6)
    down = L.compute(device.width, device.height, 7, COLUMNS, GROUPS, quote=True, shift=6)

    assert down.grid_y > up.grid_y
    assert down.quote_center_y > up.quote_center_y


def test_the_quote_costs_the_grid_less_than_its_own_height(device: Device):
    plain = L.compute(device.width, device.height, 7, COLUMNS, GROUPS)
    quoted = L.compute(device.width, device.height, 7, COLUMNS, GROUPS, quote=True)
    band = L.QUOTE_BAND * device.height

    lost = plain.grid_height - quoted.grid_height
    assert 0 <= lost < band, "the quote should reach into the button strip, not only upwards"


def test_a_dropped_grid_keeps_clear_of_the_quote(device: Device):
    lay = L.compute(device.width, device.height, 7, COLUMNS, GROUPS, quote=True, clock="big")
    quote_top = lay.quote_center_y - lay.quote_font * 2
    assert lay.grid_y + lay.grid_height < quote_top


@pytest.mark.parametrize("clock", list(L.CLOCK_TOP))
def test_the_quote_band_survives_either_clock(device: Device, clock: str):
    lay = L.compute(device.width, device.height, 7, COLUMNS, GROUPS, quote=True, clock=clock)

    assert lay.quote_center_y > lay.grid_y + lay.grid_height
    assert lay.quote_center_y < lay.footer_center_y


def test_an_unknown_clock_size_is_refused():
    with pytest.raises(L.ClockError):
        L.parse_clock("huge")


@pytest.mark.parametrize("shift", [-8, -2, 0, 2, 8])
def test_a_manual_nudge_moves_the_grid_and_stays_in_the_band(device: Device, shift: int):
    plain = L.compute(device.width, device.height, 7, COLUMNS, GROUPS)
    nudged = L.compute(device.width, device.height, 7, COLUMNS, GROUPS, shift=shift)

    assert nudged.grid_y >= L.SAFE_TOP * device.height
    assert nudged.grid_y + nudged.grid_height <= L.SAFE_BOTTOM * device.height + 1
    if shift > 0:
        assert nudged.grid_y >= plain.grid_y
    elif shift < 0:
        assert nudged.grid_y <= plain.grid_y


def test_a_nudge_that_would_overflow_is_clamped(device: Device):
    """A tall grid has no room to move; the knob must not push it off the band."""
    tall = L.compute(device.width, device.height, 27, COLUMNS, GROUPS, shift=15)
    assert tall.grid_y + tall.grid_height <= L.SAFE_BOTTOM * device.height + 1


@pytest.mark.parametrize("rows", [3, 7])
def test_the_clock_preset_moves_the_grid_by_half_its_own_change(device: Device, rows: int):
    """Lowering the ceiling by X moves a centred block by X/2 — and only that.

    Only holds while the block still fits: a grid tall enough to be squeezed by
    the shorter band shrinks instead, and then its top moves further than half.
    """
    standard = L.compute(device.width, device.height, rows, COLUMNS, GROUPS, clock="std")
    large = L.compute(device.width, device.height, rows, COLUMNS, GROUPS, clock="big")
    reserve = (L.CLOCK_TOP["big"] - L.CLOCK_TOP["std"]) * device.height

    assert standard.grid_height == large.grid_height
    assert abs((large.grid_y - standard.grid_y) - reserve / 2) <= 2


def test_a_tall_grid_shrinks_to_fit_a_lower_ceiling(device: Device):
    standard = L.compute(device.width, device.height, 27, COLUMNS, GROUPS, clock="std")
    large = L.compute(device.width, device.height, 27, COLUMNS, GROUPS, clock="big")

    assert large.grid_height < standard.grid_height
    assert large.grid_y + large.grid_height <= L.SAFE_BOTTOM * device.height


def test_a_short_grid_does_not_slide_onto_the_buttons(device: Device):
    """month + a big clock used to drop a three-row grid almost onto the footer."""
    lay = L.compute(device.width, device.height, 3, COLUMNS, GROUPS, clock="big")
    below = L.SAFE_BOTTOM * device.height - (lay.grid_y + lay.grid_height)

    assert below > 0.05 * device.height
