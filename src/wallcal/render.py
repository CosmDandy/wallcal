"""Rasterizer.

Pillow's shape drawing has no anti-aliasing, so every dot is stamped from a
single mask rendered at SUPERSAMPLE times the final size and reduced with
Lanczos. One mask, reused thousands of times: the edges are clean and the whole
wallpaper still renders in tens of milliseconds.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import date
from enum import Enum
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from . import layout as layout_mod
from . import quotes
from .fonts import FONT_LIGHT, FONT_REGULAR, load_font
from .grid import DAYS_PER_WEEK, CellState, Grid
from .palette import RGB, Ramp, lerp, mix, ramp_for
from .strings import days_left, month, week_of, weekday

SUPERSAMPLE = 8

WEEKEND_INSET = 0.0  # the band ends halfway between two dots, on the cell edge
FADE_FLOOR = 0.0  # 0 lands on the ramp's faint end, 1 on its strong end
FADE_STEPS = 40  # quantised so the sprite tiles stay cacheable
# Below 1 the curve is steep far from today and shallow near it: recent days sit
# close together and the fall-off happens gradually, out in the old part.
FADE_CURVE = 0.7
QUOTE_MAX_LINES = 3
QUOTE_ALPHA = 0.62  # against the footer tone: present, still quieter than the dots


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
    bar: bool = True  # a progress rule under the footer line
    fade: bool = True  # older past days drawn fainter than recent ones
    split: bool = True  # a gap between the weeks inside a row
    weekends: bool = True  # a faint band behind Saturday and Sunday
    marks: bool = True  # a tinted cell on the last day of each month
    month_mark: RGB = (0xCB, 0x4B, 0x16)  # solarized orange
    quote: bool = False  # rotate a line of the day under the grid
    quote_text: str = ""  # replaces the rotation when set
    quote_author: str = ""
    clock: str = "std"  # how much room the lock screen clock needs above
    ink: str = "bright"  # strong end of the ramp: bright or cream
    language: str = "en"
    first_weekday: int = 0  # 0 Monday, 6 Sunday
    header: HeaderMode = HeaderMode.DAYS
    shift: int = 0  # nudge the whole block, in percent of screen height

    @property
    def shows_quote(self) -> bool:
        """Your own line stands on its own: writing one is asking for a quote."""
        return self.quote or bool(self.quote_text)

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


def render_span(grid: Grid, width: int, height: int, style: Style) -> Image.Image:
    """Draw the whole wallpaper. Raises LayoutError if the span cannot fit."""
    lay = layout_mod.compute(
        width,
        height,
        grid.rows,
        grid.columns,
        groups=grid.columns // DAYS_PER_WEEK,
        split=style.split,
        labels=style.labels,
        quote=style.shows_quote,
        clock=style.clock,
        shift=style.shift,
    )
    image = Image.new("RGB", (width, height), style.background)

    _draw_backdrops(image, lay, grid, style)

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
    if style.footer is not FooterMode.NONE:
        _draw_footer(image, lay, style, (_footer_line(grid, style.footer, style.language),))
    if style.bar:
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
    """Tints laid under the dots: weekend columns, then single marked days."""
    draw = ImageDraw.Draw(image)

    ramp = style.ramp
    if style.weekends:
        tint = ramp.weekend
        # Pulled in off the cell edges so it reads as a light outline around the
        # weekend, not as a second grid drawn behind the first.
        inset_x = round((lay.pitch_x - lay.dot) * WEEKEND_INSET)
        inset_y = round((lay.pitch_y - lay.dot) * WEEKEND_INSET)
        radius = round(lay.pitch_x * 0.35)
        top = lay.cell_box(0, 0)[1] + inset_y
        bottom = lay.cell_box(lay.rows - 1, 0)[3] - inset_y
        # Which columns the weekend lands in depends on what starts the week:
        # with wd=6 Saturday is the last column and Sunday the first, so the two
        # are not adjacent and get a band each. When they are adjacent they get
        # one band between them — Saturday and Sunday read as a single block,
        # which is what they are.
        saturday = (5 - style.first_weekday) % DAYS_PER_WEEK
        sunday = (6 - style.first_weekday) % DAYS_PER_WEEK
        if sunday == saturday + 1:
            runs = [(saturday, sunday)]
        else:
            runs = [(saturday, saturday), (sunday, sunday)]
        for week in range(lay.groups):
            for first, last in runs:
                left = lay.cell_box(0, week * DAYS_PER_WEEK + first)[0] + inset_x
                right = lay.cell_box(0, week * DAYS_PER_WEEK + last)[2] - inset_x
                draw.rounded_rectangle((left, top, right, bottom), radius=radius, fill=tint)

    if style.marks:
        month_tint = lerp(style.background, style.month_mark, ramp.tint)
        radius = round(lay.pitch_x * 0.35)
        for cell in grid.cells:
            if cell.state is CellState.OUTSIDE or not cell.is_month_end:
                continue
            draw.rounded_rectangle(lay.cell_box(cell.row, cell.col), radius=radius, fill=month_tint)


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


def _draw_footer(
    image: Image.Image, lay: layout_mod.Layout, style: Style, lines: tuple[str, ...]
) -> None:
    """Centered block of up to a few lines. Today it holds progress; a quote fits here too."""
    if not lines:
        return
    draw = ImageDraw.Draw(image)
    color = style.ramp.footer

    # Shrink to fit the lane between the lock screen buttons rather than run under them.
    def too_wide(size: int) -> bool:
        font = load_font(FONT_REGULAR, size)
        return max(font.getlength(line) for line in lines) > lay.footer_max_width

    size = lay.footer_font
    while size > 10 and too_wide(size):
        size -= 1
    font = load_font(FONT_REGULAR, size)
    step = round(size * 1.35)
    top = lay.footer_center_y - step * (len(lines) - 1) / 2

    for index, line in enumerate(lines):
        draw.text((lay.width / 2, top + index * step), line, font=font, fill=color, anchor="mm")


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


def _footer_line(grid: Grid, mode: FooterMode, language: str) -> str:
    if mode is FooterMode.LEFT:
        return days_left(language, grid.days_left)
    if mode is FooterMode.WEEK:
        return week_of(language, grid.week_index, grid.weeks_total)
    return f"{grid.days_elapsed} / {grid.days_total}  ·  {grid.progress * 100:.1f}%"


def _draw_bar(image: Image.Image, lay: layout_mod.Layout, grid: Grid, style: Style) -> None:
    """A rule the width of the lane, filled to the share of the span already spent."""
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
    filled = round(width * grid.progress)
    if filled >= height:
        draw.rounded_rectangle(
            (left, top, left + filled, top + height), radius=radius, fill=style.accent
        )


def to_png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", compress_level=6)
    return buffer.getvalue()
