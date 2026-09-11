"""Lock screen mock-up drawn over a finished wallpaper.

For judging composition in a browser, not for a phone: it puts the clock, the
date and the two round buttons roughly where iOS puts them, so you can see what
the grid has to live between. Proportions are eyeballed from an iPhone lock
screen and are deliberately approximate — never ship this image as a wallpaper.
"""

from __future__ import annotations

from datetime import date

from PIL import Image, ImageDraw

from . import layout
from .fonts import FONT_LIGHT, FONT_REGULAR, load_font
from .palette import RGB, mix
from .render import Style
from .strings import long_date

DATE_Y = 0.093
DATE_SIZE = 0.017
# Two clock sizes, matching the reserve the layout keeps for each.
CLOCK_Y = {"std": 0.142, "big": 0.20}
CLOCK_SIZE = {"std": 0.078, "big": 0.155}

# Taken from the layout so the mock-up cannot drift from the space the renderer
# actually keeps clear.
BUTTON_Y = layout.CONTROLS_ROW
BUTTON_X = 0.155  # from either edge
BUTTON_R = layout.CONTROLS_RADIUS

INDICATOR_Y = 0.972
INDICATOR_W = 0.35
INDICATOR_H = 0.0022

CHROME_ALPHA = 0.72  # clock and date
BUTTON_FILL_ALPHA = 0.08
BUTTON_INK_ALPHA = 0.55

CLOCK_TEXT = "9:41"  # the time Apple puts on every iPhone it photographs


def _circle(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, fill: RGB) -> None:
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=fill)


def _flashlight(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, ink: RGB) -> None:
    head = r * 0.34
    draw.polygon(
        [
            (cx - head, cy - r * 0.42),
            (cx + head, cy - r * 0.42),
            (cx + head * 0.62, cy),
            (cx - head * 0.62, cy),
        ],
        fill=ink,
    )
    draw.rounded_rectangle(
        (cx - head * 0.5, cy, cx + head * 0.5, cy + r * 0.46), radius=r * 0.1, fill=ink
    )


def _camera(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, ink: RGB, hole: RGB) -> None:
    body = r * 0.52
    draw.rounded_rectangle(
        (cx - body, cy - body * 0.66, cx + body, cy + body * 0.66), radius=r * 0.16, fill=ink
    )
    lens = body * 0.34
    draw.ellipse((cx - lens, cy - lens, cx + lens, cy + lens), fill=hole)


def overlay(image: Image.Image, style: Style, today: date) -> None:
    """Draw the lock screen furniture onto `image`, in place.

    In place rather than onto a copy: at phone resolution a copy is another
    11 MB held for the length of the request, and the caller has no use for the
    bare wallpaper afterwards.
    """
    mock = image
    draw = ImageDraw.Draw(mock)
    width, height = mock.size

    chrome = mix(style.strong, style.background, CHROME_ALPHA)
    draw.text(
        (width / 2, DATE_Y * height),
        long_date(style.language, today),
        font=load_font(FONT_REGULAR, round(DATE_SIZE * height)),
        fill=chrome,
        anchor="mm",
    )
    draw.text(
        (width / 2, CLOCK_Y[style.clock] * height),
        CLOCK_TEXT,
        font=load_font(FONT_LIGHT, round(CLOCK_SIZE[style.clock] * height)),
        fill=chrome,
        anchor="mm",
    )

    radius = BUTTON_R * width
    fill = mix(style.strong, style.background, BUTTON_FILL_ALPHA)
    ink = mix(style.strong, style.background, BUTTON_INK_ALPHA)
    left_x, right_x = BUTTON_X * width, (1 - BUTTON_X) * width
    button_y = BUTTON_Y * height

    _circle(draw, left_x, button_y, radius, fill)
    _circle(draw, right_x, button_y, radius, fill)
    _flashlight(draw, left_x, button_y, radius, ink)
    _camera(draw, right_x, button_y, radius, ink, fill)

    bar_h = max(2, round(INDICATOR_H * height))
    bar_w = INDICATOR_W * width
    draw.rounded_rectangle(
        (
            width / 2 - bar_w / 2,
            INDICATOR_Y * height,
            width / 2 + bar_w / 2,
            INDICATOR_Y * height + bar_h,
        ),
        radius=bar_h / 2,
        fill=ink,
    )
    return None
