"""Screen presets. Native pixel resolutions, not logical points."""

from __future__ import annotations

from dataclasses import dataclass

MIN_SIDE = 320
MAX_SIDE = 4096
# A per-side cap alone still allows 4096x4096 — sixteen megapixels, and a render
# that costs a couple of hundred megabytes. The endpoint is unauthenticated, so
# the area is what has to be bounded. The largest phone we know is 1320x2868,
# 3.8 Mpx; this leaves room above it and still keeps a burst of concurrent
# requests inside a few hundred megabytes.
MAX_PIXELS = 4_200_000


@dataclass(frozen=True)
class Device:
    key: str
    label: str
    width: int
    height: int


DEVICES: dict[str, Device] = {
    d.key: d
    for d in (
        Device("i16", "iPhone 16", 1179, 2556),
        Device("i16p", "iPhone 16 Pro", 1206, 2622),
        Device("i16pm", "iPhone 16 Pro Max", 1320, 2868),
    )
}

DEFAULT_DEVICE = "i16"

ALIASES = {
    "iphone16": "i16",
    "iphone-16": "i16",
    "iphone16pro": "i16p",
    "iphone-16-pro": "i16p",
    "iphone16promax": "i16pm",
    "iphone-16-pro-max": "i16pm",
}


class DeviceError(ValueError):
    """Raised for an unknown device key or an out-of-range explicit size."""


def resolve(key: str | None, width: int | None, height: int | None) -> tuple[int, int]:
    """Explicit width/height wins over the preset; both must be given together."""
    if (width is None) != (height is None):
        raise DeviceError("w and h must be given together")
    if width is not None and height is not None:
        for name, value in (("w", width), ("h", height)):
            if not MIN_SIDE <= value <= MAX_SIDE:
                raise DeviceError(f"{name}={value} out of range [{MIN_SIDE}, {MAX_SIDE}]")
        if width * height > MAX_PIXELS:
            raise DeviceError(
                f"w*h={width * height} exceeds {MAX_PIXELS} pixels; ask for a smaller screen"
            )
        return width, height

    name = (key or DEFAULT_DEVICE).strip().lower()
    name = ALIASES.get(name, name)
    device = DEVICES.get(name)
    if device is None:
        raise DeviceError(f"unknown device {key!r}; known: {', '.join(DEVICES)}")
    return device.width, device.height
