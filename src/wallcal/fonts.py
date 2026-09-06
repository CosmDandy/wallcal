"""Bundled typefaces.

Vendored rather than taken from the system: the container has no fontconfig at
all, and identical bytes in equals identical pixels out, which is what makes the
render tests meaningful.
"""

from __future__ import annotations

from functools import lru_cache
from importlib.resources import files
from typing import TYPE_CHECKING, cast

from PIL import ImageFont

if TYPE_CHECKING:
    from typing import BinaryIO

FONT_REGULAR = "Inter-Regular.ttf"
FONT_MEDIUM = "Inter-Medium.ttf"
FONT_LIGHT = "Inter-Light.ttf"


@lru_cache(maxsize=16)
def load_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    path = files("wallcal.assets.fonts").joinpath(name)
    with path.open("rb") as fh:
        return ImageFont.truetype(cast("BinaryIO", fh), size)


def widest(name: str, size: int, texts: tuple[str, ...]) -> float:
    font = load_font(name, size)
    return float(max(font.getlength(text) for text in texts))
