"""The astronomy, checked against numbers someone else computed.

Sunrise and sunset come from Open-Meteo's archive API, asked for one day at a
time in UTC:

    https://archive-api.open-meteo.com/v1/archive
        ?latitude=..&longitude=..&start_date=..&end_date=..
        &daily=sunrise,sunset&timezone=UTC

The coordinates below are the ones that API echoes back — it snaps a request to
its own grid — so the comparison is against the point it actually answered for.
Its times agree with timeanddate.com's published tables for the same days, and
both are printed to the minute, which is all this band ever shows.

Moon phases come from the published 2026 lunar calendar: the new moon of
17 February 2026 falls at 12:01 UTC, one minute after the instant `moon_phase`
evaluates, and the full moons of 3 January and 3 March 2026 at 04:02 and
05:37 UTC.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from wallcal.sky import SkyError, SkyMode, moon_phase, parse_location, parse_sky, sun_day

TOLERANCE = 60  # seconds; every published table is rounded to the minute anyway

# place, latitude, longitude, date, sunrise UTC, sunset UTC
ANCHORS = [
    ("London", 51.493847, -0.1630249, date(2026, 6, 21), "2026-06-21T03:43", "2026-06-21T20:21"),
    ("Moscow", 55.782074, 37.576374, date(2025, 12, 21), "2025-12-21T05:57", "2025-12-21T12:57"),
    ("Quito", -0.17574693, -78.486755, date(2026, 3, 20), "2026-03-20T11:18", "2026-03-20T23:24"),
    # Solar noon lands after midnight UTC here, so the day's own sunrise is on
    # the UTC date before it — which is what the reference returns too.
    ("Sydney", -33.848858, 151.19551, date(2026, 6, 21), "2026-06-20T20:59", "2026-06-21T06:53"),
]

TROMSO = (69.65, 18.96)  # well inside the Arctic Circle


def moment(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp).replace(tzinfo=UTC)


@pytest.mark.parametrize(("place", "lat", "lon", "day", "rise", "fall"), ANCHORS)
def test_sunrise_and_sunset_match_published_times(
    place: str, lat: float, lon: float, day: date, rise: str, fall: str
):
    times = sun_day(day, lat, lon)

    assert times.rise is not None and times.set is not None
    assert abs((times.rise - moment(rise)).total_seconds()) < TOLERANCE, place
    assert abs((times.set - moment(fall)).total_seconds()) < TOLERANCE, place


def test_the_equinox_day_is_a_little_over_twelve_hours():
    """Refraction and the sun's own width, in the one place they are the whole story.

    On the equator the day is 12h06 all year rather than 12h00: sunrise is the
    upper limb touching a refracted horizon, not the centre crossing a
    geometric one. A day length of exactly 12h would mean ZENITH was ignored.
    """
    length = sun_day(date(2026, 3, 20), 0.0, 0.0).length

    assert length is not None
    assert 12 * 3600 + 300 < length.total_seconds() < 12 * 3600 + 480


def test_polar_night_and_midnight_sun_are_told_apart():
    lat, lon = TROMSO
    summer = sun_day(date(2026, 6, 21), lat, lon)
    winter = sun_day(date(2026, 12, 21), lat, lon)

    assert (summer.rise, summer.set, summer.up) == (None, None, True)
    assert (winter.rise, winter.set, winter.up) == (None, None, False)
    assert summer.length is None and winter.length is None


def test_the_same_place_still_has_ordinary_days_in_between():
    """The polar branch is a spell, not a property of the latitude."""
    lat, lon = TROMSO
    autumn = sun_day(date(2026, 9, 8), lat, lon)

    assert autumn.rise is not None and autumn.set is not None
    assert autumn.rise < autumn.set


@pytest.mark.parametrize("day", [date(2026, 1, 3), date(2026, 3, 3)])
def test_a_full_moon_is_a_full_disc(day: date):
    fraction, _ = moon_phase(day)
    assert fraction > 0.99


def test_a_new_moon_is_an_empty_disc():
    fraction, _ = moon_phase(date(2026, 2, 17))
    assert fraction < 0.01


def test_a_week_after_the_new_moon_it_is_half_lit_and_filling():
    fraction, waxing = moon_phase(date(2026, 2, 24))

    assert 0.45 < fraction < 0.55
    assert waxing


def test_the_week_before_a_new_moon_is_the_waning_half():
    _, waxing = moon_phase(date(2026, 2, 10))
    assert not waxing


def test_the_phase_turns_on_the_published_day():
    """February 2026 is a whole lunation: full on the 1st, new on the 17th."""
    phases = [moon_phase(date(2026, 2, day)) for day in range(1, 29)]
    fractions = [fraction for fraction, _ in phases]

    assert fractions[0] > 0.99  # the full moon of 1 February, at 16:09 UTC
    assert fractions.index(min(fractions)) == 16  # the new moon of the 17th
    # Noon on the 1st is still four hours short of full, and noon on the 17th a
    # minute past new: the flag turns on both of those days and nowhere else.
    assert [waxing for _, waxing in phases] == [True] + [False] * 15 + [True] * 12


def test_sky_modes_parse_and_say_what_they_draw():
    assert parse_sky("both") is SkyMode.BOTH
    assert parse_sky(" MOON ") is SkyMode.MOON
    assert SkyMode.BOTH.draws_moon and SkyMode.BOTH.draws_sun
    assert SkyMode.MOON.draws_moon and not SkyMode.MOON.draws_sun
    assert not SkyMode.NONE.draws_moon and not SkyMode.NONE.draws_sun


def test_an_unknown_sky_mode_is_refused():
    with pytest.raises(SkyError):
        parse_sky("stars")


def test_a_coordinate_is_rounded_before_anything_sees_it():
    """Two decimals is the whole privacy policy, so it happens in the parser."""
    assert parse_location(SkyMode.SUN, 51.50735, -0.12776) == (51.51, -0.13)


def test_half_a_coordinate_is_refused():
    for lat, lon in ((51.5, None), (None, -0.13)):
        with pytest.raises(SkyError, match="together"):
            parse_location(SkyMode.SUN, lat, lon)


@pytest.mark.parametrize("mode", [SkyMode.SUN, SkyMode.BOTH])
def test_the_sun_needs_a_location(mode: SkyMode):
    with pytest.raises(SkyError, match="lat and lon"):
        parse_location(mode, None, None)


@pytest.mark.parametrize("mode", [SkyMode.NONE, SkyMode.MOON])
def test_the_moon_needs_none(mode: SkyMode):
    """The illuminated fraction is the same for the whole planet."""
    assert parse_location(mode, None, None) is None


def test_the_moon_still_keeps_a_location_it_was_given():
    """Only to know which way up the reader is standing."""
    assert parse_location(SkyMode.MOON, -33.87, 151.21) == (-33.87, 151.21)
