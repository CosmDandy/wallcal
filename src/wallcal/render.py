"""Rasterizer.

Pillow's shape drawing has no anti-aliasing, so every dot is stamped from a
single mask rendered at SUPERSAMPLE times the final size and reduced with
Lanczos. One mask, reused thousands of times: the edges are clean and the whole
wallpaper still renders in tens of milliseconds.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, replace
from datetime import UTC, date, timedelta, tzinfo
from enum import Enum
from functools import lru_cache

from PIL import Image, ImageChops, ImageDraw, ImageFont

from . import layout as layout_mod
from . import quotes, workdays
from .fonts import FONT_LIGHT, FONT_REGULAR, load_font
from .grid import DAYS_PER_WEEK, CellState, Grid, month_end
from .markers import Marker
from .palette import RGB, Ramp, lerp, mix, ramp_for
from .sky import SkyMode, moon_phase, sun_day
from .strings import days_left, month, polar, week_of, weekday

SUPERSAMPLE = 8

# A marker is the reader's own note on a day, not a fact about the calendar, so
# it carries less weight than the month-end mark: a halo hugging the dot instead
# of the whole cell filled, and the colour mixed in short of the ramp's own tint.
# Filling the cell at full tint made a weekly rule read as a second grid.
MARKER_INSET = 0.5  # of the clear space between the dot and the cell edge
MARKER_TINT = 0.7  # of the ramp's tint
BAND_RADIUS = 0.35  # corner radius of the non-working band, as a fraction of pitch_x
FADE_FLOOR = 0.0  # 0 lands on the ramp's faint end, 1 on its strong end
FADE_STEPS = 40  # quantised so the sprite tiles stay cacheable
# Below 1 the curve is steep far from today and shallow near it: recent days sit
# close together and the fall-off happens gradually, out in the old part.
FADE_CURVE = 0.7
QUOTE_MAX_LINES = 3
QUOTE_ALPHA = 0.62  # against the footer tone: present, still quieter than the dots

# The moon is a hair over the type beside it and, on a two-weeks-to-a-row span,
# within a couple of pixels of a grid dot — which is why it reads as one more
# dot rather than as an icon. Tied to the type and not to `lay.dot`: on a
# one-year span the dot falls to 30px, and a 30px moon beside 40px numerals is
# a bullet point.
MOON_RATIO = 1.05  # moon diameter as a fraction of the sky type size
SKY_GAP = 0.55  # space between the moon and the line, in type sizes
# Quantised for the same reason FADE_STEPS is: the masks are then reused across
# the days either side. At 42px one step is 0.66px, which is under the
# anti-aliasing.
MOON_STEPS = 64


class HeaderMode(Enum):
    """What runs along the top of the grid."""

    DAYS = "days"  # MO TU WE ...
    COUNT = "count"  # 7, 14 - the day each week ends on
    NONE = "none"


class HeaderError(ValueError):
    """Raised for an unknown header mode."""


def parse_header(spec: str) -> HeaderMode:
    try:
        return HeaderMode(spec.strip().lower())
    except ValueError as exc:
        known = ", ".join(mode.value for mode in HeaderMode)
        raise HeaderError(f"unknown header {spec!r}; use one of: {known}") from exc


class FooterMode(Enum):
    """What the line between the lock screen buttons says."""

    PERCENT = "pct"  # 6 / 122 · 4.9%
    LEFT = "left"  # 116 days left
    WEEK = "week"  # Week 3 of 13
    NONE = "none"


class FooterError(ValueError):
    """Raised for an unknown footer mode."""


def parse_footer(spec: str) -> FooterMode:
    key = spec.strip().lower()
    aliases = {
        "1": FooterMode.PERCENT,
        "0": FooterMode.NONE,
        "true": FooterMode.PERCENT,
        "false": FooterMode.NONE,
    }
    if key in aliases:
        return aliases[key]
    try:
        return FooterMode(key)
    except ValueError as exc:
        known = ", ".join(m.value for m in FooterMode)
        raise FooterError(f"unknown footer mode {spec!r}; use one of: {known}") from exc


class BarMode(Enum):
    """Which period the rule under the footer fills with.

    The dot field is already a picture of the span, so a rule that also measures
    the span states one number twice. It earns its place when it measures
    something the dots do not: `mode=month&br=year` says where the month sits in
    the year, which nothing else on the screen says.
    """

    SPAN = "span"  # the drawn span, which is what br=1 has always meant
    YEAR = "year"
    QUARTER = "quarter"
    MONTH = "month"
    NONE = "none"


class BarError(ValueError):
    """Raised for an unknown bar period."""


def parse_bar(spec: str) -> BarMode:
    key = spec.strip().lower()
    # `br` was declared a bool, so FastAPI has been accepting every spelling
    # pydantic calls one. Parsing moved in here, and dropping any of them would
    # turn a link that answers 200 today into a 400.
    aliases = {
        "1": BarMode.SPAN,
        "true": BarMode.SPAN,
        "yes": BarMode.SPAN,
        "on": BarMode.SPAN,
        "t": BarMode.SPAN,
        "y": BarMode.SPAN,
        "0": BarMode.NONE,
        "false": BarMode.NONE,
        "no": BarMode.NONE,
        "off": BarMode.NONE,
        "f": BarMode.NONE,
        "n": BarMode.NONE,
    }
    if key in aliases:
        return aliases[key]
    try:
        return BarMode(key)
    except ValueError as exc:
        known = ", ".join(m.value for m in BarMode)
        raise BarError(f"unknown bar period {spec!r}; use one of: {known}") from exc


class Production(Enum):
    """Whose working year decides which days get the band."""

    OFF = "0"  # Saturday and Sunday, and nothing else
    RU = "ru"  # Russian holidays and the government's transfers


class ProductionError(ValueError):
    """Raised for an unknown production calendar."""


def parse_production(spec: str) -> Production:
    try:
        return Production(spec.strip().lower())
    except ValueError as exc:
        known = ", ".join(p.value for p in Production)
        raise ProductionError(f"unknown production calendar {spec!r}; use one of: {known}") from exc


class Shape(Enum):
    CIRCLE = "c"
    SQUARE = "r"  # rounded square, GitHub contribution style


class ShapeError(ValueError):
    """Raised for an unknown dot shape."""


def parse_shape(spec: str) -> Shape:
    key = spec.strip().lower()
    for shape in Shape:
        if key == shape.value:
            return shape
    aliases = {"circle": Shape.CIRCLE, "dot": Shape.CIRCLE, "square": Shape.SQUARE}
    if key in aliases:
        return aliases[key]
    raise ShapeError(f"unknown shape {spec!r}; use 'c' (circle) or 'r' (rounded square)")


@dataclass(frozen=True)
class Style:
    """Colors are derived from the background unless `dot` overrides them.

    That is what lets one URL read on either theme: set the background and the
    tones follow it, instead of every caller having to restate six of them.
    """

    background: RGB = (0xFD, 0xF6, 0xE3)  # solarized base3
    dot: RGB | None = None  # overrides the ramp's strong end
    accent: RGB = (0xCB, 0x4B, 0x16)  # solarized orange
    shape: Shape = Shape.CIRCLE
    axes: bool = True
    labels: layout_mod.LabelSide = layout_mod.LabelSide.LEFT
    footer: FooterMode = FooterMode.PERCENT
    bar: BarMode = BarMode.SPAN  # which period the rule under the footer fills
    fade: bool = True  # older past days drawn fainter than recent ones
    split: bool = True  # a gap between the weeks inside a row
    weekends: bool = True  # a faint band behind the days that are not worked
    production: Production = Production.OFF  # whose calendar says which days those are
    marks: bool = True  # a tinted cell on the last day of each month
    month_mark: RGB = (0xCB, 0x4B, 0x16)  # solarized orange
    markers: tuple[Marker, ...] = ()  # the reader's own rules, drawn over the marks
    quote: bool = False  # rotate a line of the day under the grid
    quote_text: str = ""  # replaces the rotation when set
    quote_author: str = ""
    sky: SkyMode = SkyMode.NONE  # a moon, a sun line, or both, in the same band
    location: tuple[float, float] | None = None  # rounded latitude and longitude
    day_length: bool = True  # the day's length and how much it changed overnight
    clock: str = "std"  # how much room the lock screen clock needs above
    ink: str = "bright"  # strong end of the ramp: bright or cream
    language: str = "en"
    first_weekday: int = 0  # 0 Monday, 6 Sunday
    header: HeaderMode = HeaderMode.DAYS
    shift: int = 0  # nudge the whole block, in percent of screen height

    @property
    def shows_sky(self) -> bool:
        """Whether anything of the sky is drawn at all."""
        return self.sky is not SkyMode.NONE

    @property
    def shows_quote(self) -> bool:
        """Your own line stands on its own: writing one is asking for a quote."""
        return bool(self.quote_text) or self.quote

    @property
    def shows_band(self) -> bool:
        """Whether the strip under the grid is reserved at all.

        Only the quote takes it. The sky rides the footer line instead, where
        the lane was standing half empty — `Week 3 of 13` uses a third of it —
        and so costs the field nothing: a moon under the grid used to buy its
        place with the dots, eight pixels off their pitch on a year of them.
        """
        return self.shows_quote

    @property
    def ramp(self) -> Ramp:
        base = ramp_for(self.background, self.ink)
        if self.dot is None:
            return base
        # An explicit dot colour replaces the strong end; the faint end and the
        # unlived days are re-derived from it so the fade still lands somewhere.
        return base._replace(
            strong=self.dot,
            faint=mix(self.dot, self.background, 0.45),
            future=mix(self.dot, self.background, 0.16),
        )

    @property
    def strong(self) -> RGB:
        return self.ramp.strong


@lru_cache(maxsize=32)
def _dot_mask(size: int, shape: Shape, corner: int) -> Image.Image:
    big = size * SUPERSAMPLE
    mask = Image.new("L", (big, big), 0)
    draw = ImageDraw.Draw(mask)
    if shape is Shape.CIRCLE:
        draw.ellipse((0, 0, big - 1, big - 1), fill=255)
    else:
        draw.rounded_rectangle((0, 0, big - 1, big - 1), radius=corner * SUPERSAMPLE, fill=255)
    return mask.resize((size, size), Image.Resampling.LANCZOS)


def render_span(
    grid: Grid, width: int, height: int, style: Style, zone: tzinfo = UTC
) -> Image.Image:
    """Draw the whole wallpaper. Raises LayoutError if the span cannot fit.

    `zone` is only read by the sun line, which is the one thing here printed on
    a local clock rather than derived from the span.
    """
    lay = layout_mod.compute(
        width,
        height,
        grid.rows,
        grid.columns,
        groups=grid.columns // DAYS_PER_WEEK,
        split=style.split,
        labels=style.labels,
        quote=style.shows_band,
        footer=style.footer is not FooterMode.NONE,
        clock=style.clock,
        shift=style.shift,
    )
    image = Image.new("RGB", (width, height), style.background)

    _draw_backdrops(image, lay, grid, style)
    _draw_markers(image, lay, grid, style)

    mask = _dot_mask(lay.dot, style.shape, lay.corner)
    ramp = style.ramp
    tiles = {
        CellState.PAST: Image.new("RGB", (lay.dot, lay.dot), ramp.strong),
        CellState.FUTURE: Image.new("RGB", (lay.dot, lay.dot), ramp.future),
        CellState.TODAY: Image.new("RGB", (lay.dot, lay.dot), style.accent),
    }
    faded: dict[int, Image.Image] = {}

    for cell in grid.cells:
        if cell.state is CellState.OUTSIDE:
            continue
        tile = tiles[cell.state]
        if style.fade and cell.state is CellState.PAST:
            step = _fade_step(cell.day, grid)
            if step not in faded:
                along = FADE_FLOOR + (1 - FADE_FLOOR) * (step / FADE_STEPS) ** FADE_CURVE
                faded[step] = Image.new(
                    "RGB", (lay.dot, lay.dot), lerp(ramp.faint, ramp.strong, along)
                )
            tile = faded[step]
        image.paste(tile, lay.dot_origin(cell.row, cell.col), mask)

    if style.axes:
        _draw_axes(image, lay, grid, style)
    if style.shows_quote:
        chosen = (
            (style.quote_text, style.quote_author)
            if style.quote_text
            else quotes.for_day(grid.today)
        )
        _draw_quote(image, lay, style, chosen)
    if style.footer is not FooterMode.NONE or style.shows_sky:
        _draw_footer(image, lay, style, grid, zone)
    if style.bar is not BarMode.NONE:
        _draw_bar(image, lay, grid, style)

    return image


def _fade_step(day: date, grid: Grid) -> int:
    """0 at the start of the span, FADE_STEPS on the day before today.

    Anchored to the span rather than to a fixed number of days: a two-week span
    and a two-year one should both fade across their whole filled part.
    """
    elapsed = (grid.today - grid.start).days
    if elapsed <= 0:
        return FADE_STEPS
    return round(FADE_STEPS * (day - grid.start).days / elapsed)


def _draw_backdrops(image: Image.Image, lay: layout_mod.Layout, grid: Grid, style: Style) -> None:
    """Tints laid under the dots: the non-working band, then single marked days.

    Order is the z-order: the band is the ground everything else sits on.
    """
    draw = ImageDraw.Draw(image)

    ramp = style.ramp
    radius = round(lay.pitch_x * BAND_RADIUS)
    if style.weekends:
        _draw_non_working(draw, lay, grid, style, radius, ramp.weekend)

    if style.marks:
        month_tint = lerp(style.background, style.month_mark, ramp.tint)
        for cell in grid.cells:
            if cell.state is CellState.OUTSIDE or not cell.is_month_end:
                continue
            draw.rounded_rectangle(lay.cell_box(cell.row, cell.col), radius=radius, fill=month_tint)


def _draw_markers(image: Image.Image, lay: layout_mod.Layout, grid: Grid, style: Style) -> None:
    """The reader's own rules, tinted on top of the backdrops.

    The month-end mark's recipe, held back — see MARKER_INSET and MARKER_TINT.
    The background is lifted towards the colour, but less far, and the shape is
    pulled in off the cell edges, so a marker reads as another day worth
    noticing rather than as a second kind of drawing laid over the field.

    Where two markers cover the same day, the last one in the URL wins: the
    order they are written in is the only thing a reader can see, so it is what
    decides. Write the broad rule first and the exception after it.
    """
    if not style.markers:
        return
    draw = ImageDraw.Draw(image)
    inset_x = round((lay.pitch_x - lay.dot) / 2 * MARKER_INSET)
    inset_y = round((lay.pitch_y - lay.dot) / 2 * MARKER_INSET)
    # The radius follows the shrunken box, or a halo this thin would round away
    # into a lozenge.
    radius = round((lay.pitch_x - 2 * inset_x) * 0.35)
    # style.ramp rebuilds the whole ramp on every read, and the tints are the
    # same for every cell: mixed once, here.
    amount = style.ramp.tint * MARKER_TINT

    # Each rule is expanded over the span once. A pulled-back rule has to look
    # at the days around the one it names, so asking it cell by cell would walk
    # the same stretch of calendar again for every day drawn.
    def off(day: date) -> bool:
        return _is_non_working(day, style)

    claimed: dict[date, RGB] = {}
    for marker in style.markers:
        tint = lerp(style.background, marker.color, amount)
        for day in marker.days_in(grid.start, grid.end, off):
            claimed[day] = tint  # later rules paint over earlier ones

    for cell in grid.cells:
        if cell.state is CellState.OUTSIDE:
            continue
        fill = claimed.get(cell.day)
        if fill is None:
            continue
        left, top, right, bottom = lay.cell_box(cell.row, cell.col)
        draw.rounded_rectangle(
            (left + inset_x, top + inset_y, right - inset_x, bottom - inset_y),
            radius=radius,
            fill=fill,
        )


def _is_non_working(day: date, style: Style) -> bool:
    return (
        workdays.is_non_working(day)
        if style.production is Production.RU
        else day.weekday() >= workdays.SATURDAY
    )


def _row_runs(grid: Grid, style: Style, row: int) -> tuple[tuple[int, int], ...]:
    """The row's non-working days as maximal column runs, `(first_col, last_col)`.

    A run stops at the boundary between two weeks, because the row is two whole
    weeks set side by side and a band reaching over the gap would be the one
    mark in the drawing that denies it — but only while there is a gap. With
    `sp=0` the weeks are flush, and stopping there put a two-pixel notch at the
    top and bottom of a seam nothing separates: an hourglass exactly where this
    drawing exists to show an unbroken run of days off.
    """
    runs: list[tuple[int, int]] = []
    for cell in grid.cells[row * grid.columns : (row + 1) * grid.columns]:
        if not _is_non_working(cell.day, style):
            continue
        boundary = cell.col % DAYS_PER_WEEK == 0 and style.split
        joins = bool(runs) and runs[-1][1] == cell.col - 1 and not boundary
        if joins:
            runs[-1] = (runs[-1][0], cell.col)
        else:
            runs.append((cell.col, cell.col))
    return tuple(runs)


def _draw_non_working(  # noqa: PLR0913 - a drawing primitive, given its geometry and its colour
    draw: ImageDraw.ImageDraw,
    lay: layout_mod.Layout,
    grid: Grid,
    style: Style,
    radius: int,
    tint: RGB,
) -> None:
    """The band under days that are not worked, as few shapes as the days allow.

    Which days those are varies by date once a production calendar is on, so the
    band cannot be drawn as columns. It is the union of the cells instead, merged
    across a row and then down the rows: a Friday that is not worked has to read
    as one shape with the weekend, and a plain weekend has to stay the single
    full-height pill it has always been.

    Rounded rectangles are the wrong primitive to stamp per cell — abutting ones
    pinch at the seam — so the union is decomposed into blocks that already share
    an edge, and the seams between blocks are patched square afterwards.
    """
    blocks: list[tuple[int, int, tuple[tuple[int, int], ...]]] = []
    for row in range(grid.rows):
        runs = _row_runs(grid, style, row)
        if blocks and blocks[-1][2] == runs:
            blocks[-1] = (blocks[-1][0], row, runs)
        else:
            blocks.append((row, row, runs))

    for first_row, last_row, runs in blocks:
        top = lay.cell_box(first_row, 0)[1]
        bottom = lay.cell_box(last_row, 0)[3]
        for first_col, last_col in runs:
            left = lay.cell_box(first_row, first_col)[0]
            right = lay.cell_box(first_row, last_col)[2]
            draw.rounded_rectangle((left, top, right, bottom), radius=radius, fill=tint)

    # Where one block sits on another, their two rounded edges leave a scallop
    # between them. A square patch over the columns they share turns it back into
    # the straight run of colour it is, and leaves the corners that really are
    # corners rounded. The radius is under one row tall, so it cannot spill past
    # either block.
    for upper, lower in zip(blocks, blocks[1:], strict=False):
        seam = lay.cell_box(lower[0], 0)[1]
        for above, below in ((a, b) for a in upper[2] for b in lower[2]):
            first_col, last_col = max(above[0], below[0]), min(above[1], below[1])
            if first_col > last_col:
                continue
            left = lay.cell_box(lower[0], first_col)[0]
            right = lay.cell_box(lower[0], last_col)[2]
            draw.rectangle((left, seam - radius, right, seam + radius - 1), fill=tint)


def _draw_axes(image: Image.Image, lay: layout_mod.Layout, grid: Grid, style: Style) -> None:
    draw = ImageDraw.Draw(image)
    font = load_font(FONT_LIGHT, lay.axis_font)
    color = style.ramp.axis

    if style.header is HeaderMode.DAYS:
        for col in range(lay.columns):
            x, _ = lay.cell_center(0, col)
            label = weekday(style.language, (col + style.first_weekday) % DAYS_PER_WEEK)
            draw.text((x, lay.header_center_y), label, font=font, fill=color, anchor="mm")
    elif style.header is HeaderMode.COUNT:
        # One number per week, over the day it ends on: 7, 14, ...
        for week in range(lay.groups):
            col = week * DAYS_PER_WEEK + DAYS_PER_WEEK - 1
            x, _ = lay.cell_center(0, col)
            label = str((week + 1) * DAYS_PER_WEEK)
            draw.text((x, lay.header_center_y), label, font=font, fill=color, anchor="mm")

    for row, label in grid.week_labels:
        _, y = lay.cell_center(row, 0)
        draw.text((lay.week_label_x, y), label, font=font, fill=color, anchor=lay.week_label_anchor)

    for first, last, number in grid.month_spans:
        _, top = lay.cell_center(first, 0)
        _, bottom = lay.cell_center(last, 0)
        name = month(style.language, number)
        _paste_sideways(image, name, font, color, lay.month_center_x, (top + bottom) / 2)


def _paste_sideways(
    image: Image.Image,
    text: str,
    font: ImageFont.FreeTypeFont,
    color: RGB,
    center_x: float,
    center_y: float,
) -> None:
    """Draw `text` rotated a quarter turn, reading bottom to top.

    Pillow cannot rotate text in place, so it is drawn upright on its own mask
    and the mask is turned — which also keeps the glyph anti-aliasing intact.
    """
    left, top, right, bottom = (round(v) for v in font.getbbox(text))
    strip = Image.new("L", (right - left + 2, bottom - top + 2), 0)
    ImageDraw.Draw(strip).text((1 - left, 1 - top), text, font=font, fill=255)
    turned = strip.rotate(90, expand=True)

    tile = Image.new("RGB", (turned.width, turned.height), color)
    image.paste(
        tile,
        (round(center_x - turned.width / 2), round(center_y - turned.height / 2)),
        turned,
    )


def _footer_text(grid: Grid, style: Style, zone: tzinfo, brief: bool) -> str:
    """What the lane says: the span's own line, the sky's, or the two joined.

    `brief` drops the day's length and its change — the part the reader can most
    nearly do without, and the first thing given up when the lane runs out.
    """
    parts = []
    if style.footer is not FooterMode.NONE:
        parts.append(_footer_line(grid, style.footer, style.language))
    if style.shows_sky and style.sky.draws_sun and style.location:
        spoken = replace(style, day_length=False) if brief else style
        parts.append(_sky_line(grid.today, spoken, style.location, zone))
    return " \u00b7 ".join(parts)


def _draw_footer(
    image: Image.Image, lay: layout_mod.Layout, style: Style, grid: Grid, zone: tzinfo
) -> None:
    """The line in the lane between the lock screen buttons, moon at its head.

    The lane is one line wide and no wider, so when the sky rides along there is
    an order to what goes: first the day's length and its change, then the type
    size. The two clock times stay, being the part of it nothing else on the
    screen says.
    """
    draw = ImageDraw.Draw(image)
    color = style.ramp.footer
    moon = style.shows_sky and style.sky.draws_moon

    def width(text: str, size: int) -> float:
        font = load_font(FONT_REGULAR, size)
        span = font.getlength(text) if text else 0.0
        if not moon:
            return span
        return round(size * MOON_RATIO) + (round(size * SKY_GAP) if text else 0) + span

    size = lay.footer_font
    text = _footer_text(grid, style, zone, brief=False)
    if width(text, size) > lay.footer_max_width:
        text = _footer_text(grid, style, zone, brief=True)
    while size > 10 and width(text, size) > lay.footer_max_width:
        size -= 1
    if not text and not moon:
        return

    font = load_font(FONT_REGULAR, size)
    if not moon:
        # Centred on the lane by the anchor, which is not quite where measuring
        # the advance width would put it — and is where the line has always sat.
        draw.text((lay.width / 2, lay.footer_center_y), text, font=font, fill=color, anchor="mm")
        return

    disc = round(size * MOON_RATIO)
    gap = round(size * SKY_GAP) if text else 0
    left = (lay.width - (disc + gap + (font.getlength(text) if text else 0))) / 2
    _paste_moon(image, style, grid.today, round(left), lay.footer_center_y, disc)
    if text:
        draw.text(
            (left + disc + gap, lay.footer_center_y), text, font=font, fill=color, anchor="lm"
        )


def _wrap(text: str, font: ImageFont.FreeTypeFont, width: float) -> list[str]:
    """Greedy word wrap. A word longer than the line simply overhangs."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and font.getlength(candidate) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _draw_quote(
    image: Image.Image, lay: layout_mod.Layout, style: Style, quote: tuple[str, str]
) -> None:
    """The day's line, set to the width of the grid so it squares up with it."""
    line, author = quote
    draw = ImageDraw.Draw(image)
    color = mix(style.ramp.footer, style.background, QUOTE_ALPHA)

    size = lay.quote_font
    body = load_font(FONT_LIGHT, size)
    rows = _wrap(line, body, lay.grid_width)
    while len(rows) > QUOTE_MAX_LINES and size > 10:
        size -= 1
        body = load_font(FONT_LIGHT, size)
        rows = _wrap(line, body, lay.grid_width)

    step = round(size * 1.4)
    credit = load_font(FONT_LIGHT, max(9, round(size * 0.8)))
    block = step * len(rows) + round(step * 0.9)
    top = lay.quote_center_y - block / 2 + step / 2

    for index, row in enumerate(rows):
        draw.text((lay.width / 2, top + index * step), row, font=body, fill=color, anchor="mm")
    if author:
        draw.text(
            (lay.width / 2, top + len(rows) * step + step * 0.15),
            author,
            font=credit,
            fill=mix(color, style.background, 0.75),
            anchor="mm",
        )


def _sky_line(today: date, style: Style, location: tuple[float, float], zone: tzinfo) -> str:
    """`06:12 – 19:48 · 13:36 +2:14`, or the polar words when there is neither.

    The duration would read as a third time of day on its own, two tokens away
    from two clock times; the delta after it is what says it is not one. So the
    two are printed together or not at all.
    """
    lat, lon = location
    day = sun_day(today, lat, lon)
    if day.rise is None or day.set is None or day.length is None:
        return polar(style.language, day.up)

    rise, fall = day.rise.astimezone(zone), day.set.astimezone(zone)
    line = f"{rise:%H:%M} \u2013 {fall:%H:%M}"
    # A day that runs past local midnight — the fortnight either side of a polar
    # spell — leaves the pair reading backwards, `01:31 – 00:02`. The length is
    # the only thing that says that is a 23-hour day and not a 23-minute one, so
    # it goes in even when `dl` asked for no numbers.
    if not style.day_length and rise.date() == fall.date():
        return line
    length = round(day.length.total_seconds())
    line += f" · {length // 3600}:{length // 60 % 60:02d}"
    if not style.day_length:
        return line

    # Only when yesterday had a rise and a set of its own: across the boundary
    # into a polar spell there is nothing to have changed from, and a jump
    # printed there would be a number the reader cannot check.
    before = sun_day(today - timedelta(days=1), lat, lon).length
    if before is not None:
        step = length - round(before.total_seconds())
        sign = "+" if step >= 0 else "\u2212"
        line += f" {sign}{abs(step) // 60}:{abs(step) % 60:02d}"
    return line


def _paste_moon(
    image: Image.Image, style: Style, today: date, left: int, center_y: int, size: int
) -> None:
    """The moon at its phase for `today`, in two tones off the grid's own ramp.

    The disc is an unlived day and the lit part is a day just gone, which makes
    a new moon an empty dot and a full one a filled dot: the moon runs the same
    ramp the field runs, and does not have to be told it belongs there.
    """
    fraction, waxing = moon_phase(today)
    # Cusps point left for a waxing moon seen from the north, and the southern
    # hemisphere sees the same moon the other way up. Its tilt is not modelled:
    # the parallactic angle needs a time of day, which a per-day image has not
    # got, and at this size it would not be readable anyway.
    south = style.location is not None and style.location[0] < 0
    disc, lit = _moon_masks(size, round(fraction * MOON_STEPS), waxing != south)

    ramp = style.ramp
    top = center_y - size // 2
    image.paste(Image.new("RGB", (size, size), ramp.future), (left, top), disc)
    image.paste(Image.new("RGB", (size, size), ramp.strong), (left, top), lit)


@lru_cache(maxsize=32)
def _moon_masks(size: int, step: int, lit_right: bool) -> tuple[Image.Image, Image.Image]:
    """The whole disc and the lit part of it, as paste masks.

    The terminator is the great circle between the two hemispheres, and from
    here it projects to a half-ellipse sharing the disc's poles: past half lit
    it bulges beyond the half-disc and is added to it, short of half it cuts
    in. The folk construction — one disc minus another of the same radius — has
    no gibbous at all, and giving it one means an arc of the wrong curvature
    through the cusps: three pixels of error on a sixty-pixel moon, at exactly
    the phases anyone looks at.
    """
    big = size * SUPERSAMPLE
    box = (0, 0, big - 1, big - 1)
    disc = Image.new("L", (big, big), 0)
    ImageDraw.Draw(disc).ellipse(box, fill=255)

    lit = Image.new("L", (big, big), 0)
    pen = ImageDraw.Draw(lit)
    pen.pieslice(box, start=-90, end=90, fill=255)  # the sunward half
    fraction = step / MOON_STEPS
    half = abs(big / 2 * (2 * fraction - 1))
    # Under a pixel wide Pillow refuses the ellipse outright, and a terminator
    # that thin is a straight line anyway — which is what the half-disc already
    # is.
    if half >= 1:
        pen.ellipse(
            (big / 2 - half, 0, big / 2 + half, big - 1),
            fill=255 if fraction > 0.5 else 0,
        )
    lit = ImageChops.multiply(lit, disc)
    if not lit_right:
        lit = lit.transpose(Image.Transpose.FLIP_LEFT_RIGHT)

    return (
        disc.resize((size, size), Image.Resampling.LANCZOS),
        lit.resize((size, size), Image.Resampling.LANCZOS),
    )


def _footer_line(grid: Grid, mode: FooterMode, language: str) -> str:
    if mode is FooterMode.LEFT:
        return days_left(language, grid.days_left)
    if mode is FooterMode.WEEK:
        return week_of(language, grid.week_index, grid.weeks_total)
    return f"{grid.days_elapsed} / {grid.days_total}  ·  {grid.progress * 100:.1f}%"


def _bar_progress(mode: BarMode, grid: Grid) -> float:
    """How full the rule stands: the share of its period already spent.

    A calendar period is measured against today rather than against the span, so
    the rule keeps meaning something on a link whose span has run out.
    """
    if mode is BarMode.SPAN:
        return grid.progress
    day = grid.today
    if mode is BarMode.YEAR:
        first, last = date(day.year, 1, 1), date(day.year, 12, 31)
    elif mode is BarMode.QUARTER:
        opening = 3 * ((day.month - 1) // 3) + 1
        first = date(day.year, opening, 1)
        last = month_end(date(day.year, opening + 2, 1))
    else:
        first, last = day.replace(day=1), month_end(day)
    # Today counts as spent, the way the span's own progress counts it.
    return ((day - first).days + 1) / ((last - first).days + 1)


def _draw_bar(image: Image.Image, lay: layout_mod.Layout, grid: Grid, style: Style) -> None:
    """A rule the width of the lane, filled to the share of its period spent."""
    draw = ImageDraw.Draw(image)
    width = round(lay.footer_max_width * 0.62)
    height = max(4, round(lay.footer_font * 0.26))
    left = round(lay.width / 2 - width / 2)
    top = round(lay.bar_center_y - height / 2)
    radius = height / 2

    draw.rounded_rectangle(
        (left, top, left + width, top + height),
        radius=radius,
        fill=style.ramp.future,
    )
    filled = round(width * _bar_progress(style.bar, grid))
    if filled >= height:
        draw.rounded_rectangle(
            (left, top, left + filled, top + height), radius=radius, fill=style.accent
        )


def to_png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", compress_level=6)
    return buffer.getvalue()
