"""Sun and moon, computed rather than looked up.

NOAA's solar position algorithm and Meeus' low-precision lunar phase, both
against `math` alone. `astral` would be a fourth runtime dependency for forty
lines of arithmetic that will never change again.

Everything here is a pure function of a calendar date, which is what lets the
image stay cacheable until midnight: sunrise and sunset are fixed for a date,
and the moon — which does drift through the day — is evaluated at noon UT, so
it too steps exactly when "today" steps and never between.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import Enum

# 34' of refraction at the horizon plus the sun's own 16' semidiameter: the
# moment the upper limb touches a sea-level horizon, which is what a published
# sunrise means.
ZENITH = 90.833

# A coordinate is the one piece of personal data this service could hold, so it
# is blunted before anything sees it. Two decimals is about 1.1 km — a
# neighbourhood, not a doorstep — and costs under 3 seconds of sunrise below
# 60 degrees. Cutting to one decimal costs a minute there and ten near the
# Arctic Circle, which is too much to pay for a privacy gain nobody can see.
COORD_DECIMALS = 2


class SkyMode(Enum):
    """What the band under the grid holds."""

    NONE = "none"
    MOON = "moon"
    SUN = "sun"
    BOTH = "both"

    @property
    def draws_moon(self) -> bool:
        return self in (SkyMode.MOON, SkyMode.BOTH)

    @property
    def draws_sun(self) -> bool:
        return self in (SkyMode.SUN, SkyMode.BOTH)


class SkyError(ValueError):
    """Raised for an unknown sky mode, or for coordinates that do not add up."""


def parse_sky(spec: str) -> SkyMode:
    try:
        return SkyMode(spec.strip().lower())
    except ValueError as exc:
        known = ", ".join(mode.value for mode in SkyMode)
        raise SkyError(f"unknown sky {spec!r}; use one of: {known}") from exc


def parse_location(
    mode: SkyMode, lat: float | None, lon: float | None
) -> tuple[float, float] | None:
    """The coordinate pair the sun needs, rounded before anything else sees it.

    Rounding happens here rather than at the drawing so that the render, the
    ETag and the log all agree on the coarse value: a link cannot be made to
    carry a sharper position than the one this service admits to using.
    """
    if (lat is None) != (lon is None):
        raise SkyError("lat and lon must be given together")
    if lat is None or lon is None:
        if mode.draws_sun:
            raise SkyError(f"sky={mode.value} needs lat and lon")
        return None
    return round(lat, COORD_DECIMALS), round(lon, COORD_DECIMALS)


@dataclass(frozen=True, slots=True)
class SunDay:
    """Sunrise and sunset in UTC, or the reason there are none.

    Above the Arctic Circle both are absent for months at a time, and the two
    absences are opposite facts: `up` says which one this is.
    """

    rise: datetime | None
    set: datetime | None
    up: bool = False  # midnight sun when there is no rise; polar night otherwise

    @property
    def length(self) -> timedelta | None:
        if self.rise is None or self.set is None:
            return None
        return self.set - self.rise


def sun_day(day: date, lat: float, lon: float) -> SunDay:
    """Sunrise and sunset bracketing local solar noon of `day`.

    Anchored on solar noon rather than on a UTC midnight so that a longitude far
    from Greenwich still gets its own day's pair, the way every published table
    does.
    """
    rise = _event(day, lat, lon, rising=True)
    fall = _event(day, lat, lon, rising=False)
    if rise is None or fall is None:
        return SunDay(None, None, up=_sun_is_up(day, lat, lon))
    midnight = datetime(day.year, day.month, day.day, tzinfo=UTC)
    return SunDay(midnight + timedelta(minutes=rise), midnight + timedelta(minutes=fall))


def moon_phase(day: date) -> tuple[float, bool]:
    """Illuminated fraction at noon UT, and whether the moon is waxing.

    Meeus' seven-term phase angle. A mean-lunation shortcut is ten lines
    shorter and drifts by up to 0.09 of the fraction, which at the quarters is
    a visibly different moon from the one in the sky.
    """
    t = _century(_julian_day(day) + 0.5)
    elongation = 297.8501921 + 445267.1114034 * t - 0.0018819 * t**2 + t**3 / 545868
    sun_anomaly = 357.5291092 + 35999.0502909 * t - 0.0001536 * t**2
    moon_anomaly = 134.9633964 + 477198.8675055 * t + 0.0087414 * t**2 + t**3 / 69699

    d, m, mp = (math.radians(a) for a in (elongation, sun_anomaly, moon_anomaly))
    angle = (
        180.0
        - elongation
        - 6.289 * math.sin(mp)
        + 2.100 * math.sin(m)
        - 1.274 * math.sin(2 * d - mp)
        - 0.658 * math.sin(2 * d)
        - 0.214 * math.sin(2 * mp)
        - 0.110 * math.sin(d)
    )
    fraction = (1 + math.cos(math.radians(angle))) / 2
    # Elongation runs 0 at new moon to 180 at full, so the first half of that
    # walk is the half that is filling up. It is the *mean* elongation, which
    # can sit a few degrees off the true one — and so flip up to half a day
    # late — but only within hours of full or new, where the disc is either
    # whole or dark and mirroring it changes no pixel.
    waxing = 0 < elongation % 360 < 180
    return fraction, waxing


def _event(day: date, lat: float, lon: float, rising: bool) -> float | None:
    """Minutes past UTC midnight of `day`, or None when the sun never crosses.

    Two passes: the sun's declination moves by up to a quarter degree a day, so
    evaluating it at noon and using that for an event six hours away is worth a
    minute at high latitude. The second pass evaluates it at the time the first
    one found, and lands within a second of converged.
    """
    minutes = None
    when = _julian_day(day) + 0.5 - lon / 360  # local solar noon, to start
    for _ in range(2):
        decl, equation = _sun_position(_century(when))
        hour_angle = _hour_angle(lat, decl)
        if hour_angle is None:
            return None
        noon = 720 - 4 * lon - equation
        minutes = noon - 4 * hour_angle if rising else noon + 4 * hour_angle
        when = _julian_day(day) + minutes / 1440
    return minutes


def _sun_is_up(day: date, lat: float, lon: float) -> bool:
    """Which polar case this is: the sun never sets, or it never rises."""
    decl, _ = _sun_position(_century(_julian_day(day) + 0.5 - lon / 360))
    return _cos_hour_angle(lat, decl) < 0


def _hour_angle(lat: float, decl: float) -> float | None:
    """Half the sun's arc above the horizon, in degrees. None inside a polar spell."""
    cos_h = _cos_hour_angle(lat, decl)
    if not -1 <= cos_h <= 1:
        return None
    return math.degrees(math.acos(cos_h))


def _cos_hour_angle(lat: float, decl: float) -> float:
    phi, delta = math.radians(lat), math.radians(decl)
    numerator = math.cos(math.radians(ZENITH)) - math.sin(phi) * math.sin(delta)
    return numerator / (math.cos(phi) * math.cos(delta))


def _julian_day(day: date) -> float:
    """Julian day at 00:00 UT. Gregorian only, which is every date this serves."""
    year, month = day.year, day.month
    if month <= 2:  # January and February count as months 13 and 14 of the year before
        year -= 1
        month += 12
    century = year // 100
    gregorian = 2 - century + century // 4
    return (
        math.floor(365.25 * (year + 4716))
        + math.floor(30.6001 * (month + 1))
        + day.day
        + gregorian
        - 1524.5
    )


def _century(julian: float) -> float:
    """Julian centuries since J2000.0, the argument every series below takes."""
    return (julian - 2451545.0) / 36525.0


def _sun_position(t: float) -> tuple[float, float]:
    """Declination in degrees and the equation of time in minutes."""
    mean_long = 280.46646 + t * (36000.76983 + t * 0.0003032)
    anomaly = 357.52911 + t * (35999.05029 - 0.0001537 * t)
    eccentricity = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)
    radians_anomaly = math.radians(anomaly)
    centre = (
        math.sin(radians_anomaly) * (1.914602 - t * (0.004817 + 0.000014 * t))
        + math.sin(2 * radians_anomaly) * (0.019993 - 0.000101 * t)
        + math.sin(3 * radians_anomaly) * 0.000289
    )
    node = math.radians(125.04 - 1934.136 * t)
    apparent = math.radians(mean_long + centre - 0.00569 - 0.00478 * math.sin(node))
    obliquity = math.radians(
        23
        + (26 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60) / 60
        + 0.00256 * math.cos(node)
    )
    decl = math.degrees(math.asin(math.sin(obliquity) * math.sin(apparent)))

    y = math.tan(obliquity / 2) ** 2
    long_radians = math.radians(mean_long)
    equation = math.degrees(
        y * math.sin(2 * long_radians)
        - 2 * eccentricity * math.sin(radians_anomaly)
        + 4 * eccentricity * y * math.sin(radians_anomaly) * math.cos(2 * long_radians)
        - 0.5 * y * y * math.sin(4 * long_radians)
        - 1.25 * eccentricity * eccentricity * math.sin(2 * radians_anomaly)
    )
    return decl, 4 * equation
