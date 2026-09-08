"""Colors: Solarized names plus hex literals, both accepted in query strings."""

from __future__ import annotations

from typing import NamedTuple

RGB = tuple[int, int, int]

# Ethan Schoonover's Solarized. Named colors are the vocabulary of the URL API,
# so they must stay stable even if defaults change.
SOLARIZED: dict[str, RGB] = {
    "base03": (0x00, 0x2B, 0x36),
    "base02": (0x07, 0x36, 0x42),
    "base01": (0x58, 0x6E, 0x75),
    "base00": (0x65, 0x7B, 0x83),
    "base0": (0x83, 0x94, 0x96),
    "base1": (0x93, 0xA1, 0xA1),
    "base2": (0xEE, 0xE8, 0xD5),
    "base3": (0xFD, 0xF6, 0xE3),
    "yellow": (0xB5, 0x89, 0x00),
    "orange": (0xCB, 0x4B, 0x16),
    "red": (0xDC, 0x32, 0x2F),
    "magenta": (0xD3, 0x36, 0x82),
    "violet": (0x6C, 0x71, 0xC4),
    "blue": (0x26, 0x8B, 0xD2),
    "cyan": (0x2A, 0xA1, 0x98),
    "green": (0x85, 0x99, 0x00),
}

EXTRA: dict[str, RGB] = {
    "black": (0x00, 0x00, 0x00),
    "white": (0xFF, 0xFF, 0xFF),
}

NAMED: dict[str, RGB] = {**SOLARIZED, **EXTRA}


class ColorError(ValueError):
    """Raised for a color spec that is neither a known name nor a hex literal."""


# The device finishes are the published sRGB values of the iPhone 16 and 16 Pro
# bodies, not an impression of them: a wallpaper meant to disappear into the
# phone it is on has to be the same colour as that phone, and eyeballing the
# product shots put every one of them several shades too pale.
THEMES: dict[str, RGB] = {
    "light": SOLARIZED["base3"],
    "dark": SOLARIZED["base03"],
    "gray": (0x1C, 0x1C, 0x1E),
    "grey": (0x1C, 0x1C, 0x1E),
    "white": EXTRA["white"],
    "black": EXTRA["black"],
    # iPhone 16 / 16 Plus
    "teal": (0xB0, 0xD4, 0xD2),
    "ultramarine": (0x9A, 0xAD, 0xF6),
    "pink": (0xF2, 0xAD, 0xDA),
    "onyx": (0x3C, 0x40, 0x42),  # the black body, which is not black
    # iPhone 16 Pro / Pro Max. `sand` keeps its name: it is in links already.
    "sand": (0xBF, 0xA4, 0x8F),  # desert titanium
    "natural": (0xC2, 0xBC, 0xB2),  # natural titanium
}


class ThemeError(ValueError):
    """Raised for an unknown theme name."""


def parse_theme(spec: str) -> RGB:
    background = THEMES.get(spec.strip().lower())
    if background is None:
        raise ThemeError(f"unknown theme {spec!r}; use one of: {', '.join(THEMES)}")
    return background


def luminance(color: RGB) -> float:
    """Relative luminance, WCAG's formula. Only used to ask: is this dark or light?"""

    def channel(value: int) -> float:
        srgb = value / 255
        return srgb / 12.92 if srgb <= 0.04045 else ((srgb + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in color)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def lerp(start: RGB, end: RGB, t: float) -> RGB:
    amount = max(0.0, min(1.0, t))
    return tuple(  # type: ignore[return-value]
        round(a + (b - a) * amount) for a, b in zip(start, end, strict=True)
    )


class Ramp(NamedTuple):
    """The tones a page uses, all taken from Solarized's own monotone scale.

    Solarized is built as one lightness ramp, base03 through base3, meant to be
    read from either end. Mixing a dot colour into the background instead lands
    on a neutral grey, which beside the orange accent reads faintly green — the
    palette's own steps do not, because they carry a consistent cool cast.
    """

    strong: RGB  # a day just gone
    faint: RGB  # the oldest day of the span
    future: RGB  # a day not yet lived
    axis: RGB  # week numbers, month names, weekday letters
    footer: RGB
    weekend: RGB  # the band behind Saturday and Sunday
    tint: float  # how much accent to mix in for a marked day


DARK_RAMP = Ramp(
    # Pure white, not Solarized's base2. iOS sets its clock in white, and beside
    # it the cream tone reads as dirty rather than as a warm choice. The steps
    # below it stay on the palette, so the fade keeps its cool cast.
    strong=EXTRA["white"],
    faint=SOLARIZED["base01"],
    future=SOLARIZED["base02"],
    axis=SOLARIZED["base00"],
    footer=SOLARIZED["base0"],
    weekend=SOLARIZED["base02"],
    tint=0.55,
)

LIGHT_RAMP = Ramp(
    strong=SOLARIZED["base02"],
    faint=SOLARIZED["base1"],
    future=SOLARIZED["base2"],
    axis=SOLARIZED["base1"],
    footer=SOLARIZED["base00"],
    weekend=SOLARIZED["base2"],
    tint=0.30,
)

DARK_THRESHOLD = 0.2  # relative luminance below which a background counts as dark
# The device finishes are mid-tone — desert titanium, ultramarine — and against
# those a fixed Solarized step for small type lands at a contrast of under two.
# Type is pulled towards the strong end until it clears this; the dots are left
# alone, since a fading field is the whole point of them.
TEXT_CONTRAST = 3.0


INKS = ("bright", "cream")


class InkError(ValueError):
    """Raised for an unknown ink choice."""


def parse_ink(spec: str) -> str:
    key = spec.strip().lower()
    if key not in INKS:
        raise InkError(f"unknown ink {spec!r}; use one of: {', '.join(INKS)}")
    return key


def contrast(one: RGB, other: RGB) -> float:
    """WCAG contrast ratio, 1 (identical) to 21 (black on white)."""
    light, dark = sorted((luminance(one), luminance(other)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def _readable(tone: RGB, background: RGB, strong: RGB) -> RGB:
    """The given tone, or as far towards `strong` as it takes to be legible."""
    if contrast(tone, background) >= TEXT_CONTRAST:
        return tone
    for step in range(1, 11):
        candidate = lerp(tone, strong, step / 10)
        if contrast(candidate, background) >= TEXT_CONTRAST:
            return candidate
    return strong


def ramp_for(background: RGB, ink: str = "bright") -> Ramp:
    """Pick the ramp that reads on this background, and pull its ends towards it.

    Anchoring the faint end and the two backdrops to the actual background keeps
    the contrast honest when someone sets a colour of their own rather than one
    of the two themes.
    """
    dark = luminance(background) < DARK_THRESHOLD
    base = DARK_RAMP if dark else LIGHT_RAMP
    if ink == "cream":
        # Solarized's own end of the ramp: quieter, and it sits closer to the
        # tones below it, so the fade reads as one material.
        base = base._replace(strong=SOLARIZED["base2"] if dark else SOLARIZED["base01"])
    # The faint end stays a fixed Solarized step. Pulling it towards the
    # background made it neutral on a neutral background — the far dots then
    # went plain grey, which is the one thing the ramp exists to avoid.
    faint = base.faint
    # Unlived days and the weekend band are stepped off the faint tone rather
    # than off a fixed base colour: on a neutral background a fixed base02 would
    # sit at the same lightness but a visibly different hue, and read as a stain.
    return base._replace(
        faint=faint,
        future=lerp(background, faint, 0.42),
        weekend=lerp(background, faint, 0.16),
        axis=_readable(base.axis, background, base.strong),
        footer=_readable(base.footer, background, base.strong),
    )


def parse_color(spec: str) -> RGB:
    """Accept `red`, `base03`, `dc322f`, `#dc322f`, `f00`."""
    key = spec.strip().lower()
    if key in NAMED:
        return NAMED[key]

    hexpart = key[1:] if key.startswith("#") else key
    if len(hexpart) == 3 and all(c in "0123456789abcdef" for c in hexpart):
        return tuple(int(c * 2, 16) for c in hexpart)  # type: ignore[return-value]
    if len(hexpart) == 6 and all(c in "0123456789abcdef" for c in hexpart):
        return tuple(int(hexpart[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]

    raise ColorError(
        f"unknown color {spec!r}; use a hex value (rgb or rrggbb) "
        f"or one of: {', '.join(sorted(NAMED))}"
    )


def mix(fg: RGB, bg: RGB, alpha: float) -> RGB:
    """Flatten `fg` over `bg` at `alpha`, so downstream code only deals in opaque colors."""
    a = max(0.0, min(1.0, alpha))
    return tuple(round(f * a + b * (1 - a)) for f, b in zip(fg, bg, strict=True))  # type: ignore[return-value]
