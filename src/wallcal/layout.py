"""Geometry: where the grid, its axes and the footer sit on a phone screen.

Two integer steps drive everything: `pitch_x` across days, `pitch_y` down rows.
Whole pixels are what keep the dot field machine-regular instead of jittering by
a fraction of a pixel every few columns.

The dot field is centered on the screen, not on the screen minus a gutter: the
month labels live in matching reserves on both sides, so turning the axes off
does not shift a single dot.

The two pitches may differ, within ASPECT_CAP. Fourteen columns of a long span
on a 1:2.2 screen would otherwise force cells so small the wallpaper reads as a
smudge; stretching the looser axis fills the screen, and capping the ratio keeps
it from reading as a stretched image.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from .fonts import FONT_LIGHT, widest
from .strings import MONTHS

# Fractions of screen height kept clear of the grid: the lock screen clock and
# date live above, the flashlight and camera buttons below. iOS lets the clock
# be set much taller, and then the standard reserve is not enough — the grid
# would start underneath the digits.
CLOCK_TOP = {"std": 0.30, "big": 0.38}
SAFE_TOP = CLOCK_TOP["std"]
SIDE_MARGIN = 0.035  # fraction of width

# The two round buttons sit side by side near the bottom with a wide empty lane
# between them. That lane is where the progress line goes: it reads as part of
# the system UI rather than as something stranded above it.
CONTROLS_ROW = 0.912  # vertical center of the buttons, checked against a real phone
BAR_ROW = 0.943  # the progress bar rides below the words, above the home indicator
# The words do not go there. iOS parks the Focus pill in that same lane, and the
# notification stack lands on top of it whenever anything has arrived, so a line
# of text down there is legible on an empty phone and gone on a used one. It
# sits above the buttons instead, right under the grid's own floor — the last
# strip the notifications reach. The rule stays below: a hairline still reads
# under a pill, a sentence does not.
FOOTER_ROW = 0.862  # the lowest line of our own drawing, footer or not
CONTROLS_CLEAR = 0.20  # fraction of width each button occupies, from its edge
CONTROLS_RADIUS = 0.062  # button radius, as a fraction of width
QUOTE_CLEARANCE = 0.008  # gap kept between the quote and the top of the buttons

# The two pitches diverge asymmetrically. Widening columns rescues a long span
# that would otherwise be a thin ribbon, so it gets room; stretching rows only
# ever thins the field out, so it gets almost none.
WIDEN_CAP = 1.5  # pitch_x may exceed pitch_y by this much
STRETCH_CAP = 1.15  # pitch_y may exceed pitch_x by this much

# A row of several weeks reads as one run of days without a break between them.
GROUP_GAP_RATIO = 0.5  # gap between weeks in a row, as a fraction of pitch_x

DOT_RATIO = 0.66  # dot size as a fraction of the tighter pitch
# Softer than GitHub's own 2px-on-10px cell: at wallpaper scale that reads hard.
CORNER_RATIO = 0.30  # rounded-square corner radius as a fraction of the dot size

# Axis type is meant to be read only when looked for: small and light, so the
# dots stay the thing you see.
AXIS_RATIO = 0.42  # axis type size as a fraction of the tighter pitch
AXIS_MAX = 0.011  # ...but never more than this fraction of screen height
FOOTER_SIZE = 0.017  # footer type size as a fraction of screen height
QUOTE_BAND = 0.075  # fraction of height given to the quote, under the grid
QUOTE_SIZE = 0.0165  # quote type size as a fraction of screen height
# The sun and moon band is the quote's slot with something else in it, so it
# needs no reserve of its own — only a size. A hair under the quote's: the line
# is digits, and digits at the quote's size read as a readout.
SKY_SIZE = 0.0155  # sun and moon type size as a fraction of screen height

MIN_PITCH = 4


def footer_slot(height: int) -> int:
    """The strip the footer line occupies, whether or not it is switched on.

    Held even when the line is off. The dots are the picture, and a picture that
    grows and drops half an inch because a caption was turned off is not the
    same picture: the field would sit low with a gap under the clock, and every
    toggle below it would shuffle the whole wallpaper. The room that frees up
    goes to the quote instead, which is measured against this floor rather than
    fixed to it.
    """
    return max(11, round(FOOTER_SIZE * height)) + round(QUOTE_CLEARANCE * height)


def quote_floor(height: int, footer: bool = True) -> int:
    """How far down the quote may reach: onto the footer's strip when it is off."""
    floor = round(FOOTER_ROW * height)
    return floor - footer_slot(height) if footer else floor


def grid_floor(height: int, quote: bool = False) -> int:
    """The lowest row the dots may reach.

    Only the quote takes room from them — it is the one thing below the field
    that is worth shrinking the field for. Everything else keeps its strip.
    """
    floor = round(FOOTER_ROW * height) - footer_slot(height)
    if quote:
        floor -= round(QUOTE_BAND * height) + round(QUOTE_CLEARANCE * height)
    return floor


class LabelSide(Enum):
    """Which edge the week numbers and month names are set against."""

    LEFT = "left"  # months, then weeks, then the dots
    RIGHT = "right"  # the dots, then weeks, then months
    SPLIT = "split"  # weeks on the left, months on the right, equally spaced


def _all_month_names() -> tuple[str, ...]:
    """Every language's months: the gutter is reserved for the widest of them all,
    so switching language cannot shift the grid off centre."""
    return tuple(name for names in MONTHS.values() for name in names)


class ClockError(ValueError):
    """Raised for an unknown clock size."""


def parse_clock(spec: str) -> str:
    key = spec.strip().lower()
    if key not in CLOCK_TOP:
        raise ClockError(f"unknown clock size {spec!r}; use one of: {', '.join(CLOCK_TOP)}")
    return key


class LabelError(ValueError):
    """Raised for an unknown label placement."""


def parse_label_side(spec: str) -> LabelSide:
    try:
        return LabelSide(spec.strip().lower())
    except ValueError as exc:
        known = ", ".join(side.value for side in LabelSide)
        raise LabelError(f"unknown label placement {spec!r}; use one of: {known}") from exc


class LayoutError(ValueError):
    """Raised when the grid cannot be drawn legibly at this size."""


@dataclass(frozen=True)
class Layout:
    width: int
    height: int
    rows: int
    columns: int
    groups: int  # whole weeks per row
    group_gap: int  # pixels between them; 0 when the split is off
    pitch_x: int
    pitch_y: int
    dot: int
    corner: int
    grid_x: int  # left edge of the first column
    grid_y: int  # top edge of the first row
    week_label_x: int  # the edge week numbers are aligned to
    week_label_anchor: str  # Pillow anchor: "rm" when they hang left of the grid
    month_center_x: int  # vertical center line of the sideways month labels
    header_center_y: int  # vertical center of the weekday header text
    footer_center_y: int
    footer_max_width: int  # the lane between the two lock screen buttons
    bar_center_y: int
    quote_center_y: int  # 0 when no band was reserved
    quote_font: int
    sky_font: int
    axis_font: int
    footer_font: int

    @property
    def grid_width(self) -> int:
        return self.columns * self.pitch_x + (self.groups - 1) * self.group_gap

    @property
    def grid_height(self) -> int:
        return self.rows * self.pitch_y

    def month_band_half(self) -> int:
        """Half the width a sideways month label occupies, from its center line."""
        return round(self.axis_font * 1.1) // 2

    def cell_center(self, row: int, col: int) -> tuple[float, float]:
        week = col // (self.columns // self.groups)
        return (
            self.grid_x + col * self.pitch_x + week * self.group_gap + self.pitch_x / 2,
            self.grid_y + row * self.pitch_y + self.pitch_y / 2,
        )

    def dot_origin(self, row: int, col: int) -> tuple[int, int]:
        """Top-left pixel of the dot — where the sprite is actually pasted."""
        cx, cy = self.cell_center(row, col)
        return round(cx - self.dot / 2), round(cy - self.dot / 2)

    def cell_box(self, row: int, col: int) -> tuple[int, int, int, int]:
        """Inclusive pixel bounds of the cell, centered on the dot inside it.

        Derived from the dot's own pixel position rather than from the fractional
        cell center: a tint drawn behind a dot has to sit evenly around it, and
        rounding the two independently pushed the dot two pixels off center.
        """
        ox, oy = self.dot_origin(row, col)
        pad_x = (self.pitch_x - self.dot) // 2
        pad_y = (self.pitch_y - self.dot) // 2
        return ox - pad_x, oy - pad_y, ox - pad_x + self.pitch_x - 1, oy - pad_y + self.pitch_y - 1


def compute(  # noqa: PLR0913 - geometry needs all of it
    width: int,
    height: int,
    rows: int,
    columns: int,
    groups: int = 1,
    split: bool = True,
    labels: LabelSide = LabelSide.LEFT,
    quote: bool = False,  # or anything else asking for the band under the grid
    footer: bool = True,
    clock: str = "std",
    shift: int = 0,
) -> Layout:
    margin_x = round(SIDE_MARGIN * width)
    avail_w = width - 2 * margin_x
    avail_y0 = round(CLOCK_TOP[clock] * height)
    # The quote hangs below the grid's own floor, stopping just short of the
    # buttons — that empty strip is the lowest a wallpaper may draw.
    footer_font = max(11, round(FOOTER_SIZE * height))
    footer_center_y = round(FOOTER_ROW * height)
    quote_bottom = quote_floor(height, footer=footer)
    avail_y1 = grid_floor(height, quote=quote)
    band_h = avail_y1 - avail_y0

    axis_font = max(8, round(AXIS_MAX * height))
    header_h = round(axis_font * 2.6)
    # Measured, not guessed at from an em ratio, and reserved on both sides so
    # the dots sit on the screen's center line whether or not the axes are drawn.
    label_gap = round(axis_font * 0.55)
    # Two stacked gutters: week numbers next to the dots, month names set
    # sideways outside them. Reserved on both sides so the dots stay centered.
    week_w = math.ceil(widest(FONT_LIGHT, axis_font, ("00",)))
    month_band = round(axis_font * 1.1)  # a sideways line is one line tall
    if labels is LabelSide.SPLIT:
        # One label per side, so both get the same clearance from the dots.
        gutter = label_gap + max(week_w, month_band)
    else:
        gutter = month_band + label_gap + week_w + label_gap

    # Gaps are priced in pitch_x units so the division stays a single expression.
    gap_units = (groups - 1) * GROUP_GAP_RATIO if split else 0.0
    pitch_x = int((avail_w - 2 * gutter) / (columns + gap_units))
    pitch_y = int((band_h - header_h) / rows)
    pitch_x = min(pitch_x, int(pitch_y * WIDEN_CAP))
    pitch_y = min(pitch_y, int(pitch_x * STRETCH_CAP))
    group_gap = round(pitch_x * GROUP_GAP_RATIO) if split else 0

    # Equal padding around a dot needs the leftovers to be even on both axes, so
    # give the two pitches the same parity and match the dot to it. Costs a pixel
    # of step at most, and buys a field that is visibly centered cell by cell.
    if (pitch_y - pitch_x) % 2:
        pitch_y -= 1

    # After the parity trim, not before it: checked first, a pitch of exactly
    # MIN_PITCH passed and then lost its pixel, and the screen came back as a
    # 200 full of one-pixel dots instead of a 400.
    if min(pitch_x, pitch_y) < MIN_PITCH:
        raise LayoutError(
            f"{rows} rows of {columns} days do not fit on a {width}x{height} screen "
            f"(cell would be {min(pitch_x, pitch_y)}px, minimum is {MIN_PITCH}px)"
        )

    tight = min(pitch_x, pitch_y)
    dot = round(tight * DOT_RATIO)
    if (pitch_x - dot) % 2:
        dot -= 1
    dot = max(2, dot)  # the floor comes last, or the parity trim walks through it

    axis_font = max(8, min(round(tight * AXIS_RATIO), axis_font))

    block_h = header_h + rows * pitch_y
    # Centred under a standard clock. Under a big one the whole block drops to
    # the bottom of what is left: shrinking the band from above only moves a
    # centred block by half the reserve, which is too little to see.
    # The clock preset only lowers the ceiling; the block stays centred in what
    # is left. Dropping it to the floor as well made a short grid land almost on
    # the buttons, and made the two knobs fight each other.
    slack = band_h - block_h
    # Hand tuning on top of that, clamped to the band: no amount of nudging may
    # slide the grid under the clock or past what sits below it.
    offset = max(0, min(slack, slack // 2 + round(shift / 100 * height)))

    grid_x = (width - (columns * pitch_x + (groups - 1) * group_gap)) // 2
    grid_right = grid_x + columns * pitch_x + (groups - 1) * group_gap - 1

    if labels is LabelSide.RIGHT:
        week_label_x = grid_right + label_gap
        week_label_anchor = "lm"
        month_center_x = grid_right + label_gap + week_w + label_gap + month_band // 2
    elif labels is LabelSide.SPLIT:
        week_label_x = grid_x - label_gap
        week_label_anchor = "rm"
        month_center_x = grid_right + label_gap + month_band // 2
    else:
        week_label_x = grid_x - label_gap
        week_label_anchor = "rm"
        month_center_x = grid_x - label_gap - week_w - label_gap - month_band // 2
    grid_y = avail_y0 + max(0, offset) + header_h
    # Centred in whatever gap is left between the grid and the buttons, so it
    # follows the grid when the clock preset or the manual nudge moves it.
    quote_center_y = (grid_y + rows * pitch_y + quote_bottom) // 2 if quote else 0

    return Layout(
        width=width,
        height=height,
        rows=rows,
        columns=columns,
        groups=groups,
        group_gap=group_gap,
        pitch_x=pitch_x,
        pitch_y=pitch_y,
        dot=dot,
        corner=max(1, round(dot * CORNER_RATIO)),
        grid_x=grid_x,
        grid_y=grid_y,
        week_label_x=week_label_x,
        week_label_anchor=week_label_anchor,
        month_center_x=month_center_x,
        header_center_y=grid_y - round(header_h * 0.5),
        footer_center_y=footer_center_y,
        bar_center_y=round(BAR_ROW * height),
        quote_center_y=quote_center_y,
        quote_font=max(10, round(QUOTE_SIZE * height)),
        sky_font=max(10, round(SKY_SIZE * height)),
        footer_max_width=width - 2 * round(CONTROLS_CLEAR * width),
        axis_font=axis_font,
        footer_font=footer_font,
    )
