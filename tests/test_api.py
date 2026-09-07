"""HTTP contract: the URL is the whole configuration, so it has to fail loudly."""

from __future__ import annotations

import io
import re
from importlib.resources import files
from inspect import signature

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from wallcal.app import app, wallpaper
from wallcal.devices import DEVICES

SPAN = "f=2026-09-01&t=2026-11-30"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def test_health(client: TestClient):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_index_serves_the_builder_with_every_device(client: TestClient):
    response = client.get("/")
    body = response.text

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    for key in DEVICES:
        assert f'"{key}"' in body, f"{key} missing from the device selector"
    for mode in ("span", "year", "quarter", "month"):
        assert f'data-mode="{mode}"' in body
    # Every query parameter the API takes should be reachable from the page.
    for knob in ("s", "g", "sp", "mb", "fd", "ax", "lb", "wk", "we", "mk", "th", "ft", "br", "pv"):
        assert f'data-key="{knob}"' in body


def test_the_builder_brings_its_own_calendar(client: TestClient):
    """The native picker is the browser's, in the browser's colours.

    It stays for the value and the parsing, hidden; what opens is the page's own
    calendar. If the input ever loses `hidden`, both would show at once.
    """
    body = client.get("/").text

    for key in ("from", "to"):
        assert f'id="{key}-btn"' in body
        assert f'<input type="date" id="{key}" hidden>' in body
    assert "cal-day" in body   # the grid the page draws itself
    assert "cal-pick" in body  # and the months and years behind the title


def test_builder_defaults_match_the_api_defaults():
    """A knob whose page default differs from the server's silently does nothing.

    The page omits any value equal to `def` from the link, so if `def` drifts
    from the server's own default the control looks dead — which is exactly how
    the mock-up toggle broke.
    """
    page = files("wallcal.assets").joinpath("index.html").read_text(encoding="utf-8")
    declared = dict(re.findall(r'(\w+):\s*\{\s*def:"([^"]*)"', page))

    served = {
        parameter.default.alias: parameter.default.default
        for parameter in signature(wallpaper).parameters.values()
        if hasattr(parameter.default, "alias")
    }
    for key, page_default in declared.items():
        if key not in served:
            continue
        expected = served[key]
        expected = {True: "1", False: "0"}.get(expected, expected)
        assert page_default == str(expected), (
            f"{key}: page defaults to {page_default}, api to {expected}"
        )


@pytest.mark.parametrize("device", list(DEVICES))
def test_span_renders_at_each_device_resolution(client: TestClient, device: str):
    response = client.get(f"/w/span.png?{SPAN}&d={device}")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    with Image.open(io.BytesIO(response.content)) as image:
        assert image.size == (DEVICES[device].width, DEVICES[device].height)


def test_response_is_cacheable_only_until_midnight(client: TestClient):
    response = client.get(f"/w/span.png?{SPAN}&tz=UTC")
    cache = response.headers["cache-control"]

    assert cache.startswith("public, max-age=")
    assert 60 <= int(cache.rsplit("=", 1)[1]) <= 86400
    assert response.headers["etag"]


def test_same_request_yields_the_same_etag(client: TestClient):
    first = client.get(f"/w/span.png?{SPAN}").headers["etag"]
    second = client.get(f"/w/span.png?{SPAN}").headers["etag"]
    assert first == second


def test_different_style_yields_a_different_etag(client: TestClient):
    circle = client.get(f"/w/span.png?{SPAN}&s=c").headers["etag"]
    square = client.get(f"/w/span.png?{SPAN}&s=r").headers["etag"]
    assert circle != square


def test_explicit_size_overrides_the_preset(client: TestClient):
    response = client.get(f"/w/span.png?{SPAN}&w=1080&h=2400")
    with Image.open(io.BytesIO(response.content)) as image:
        assert image.size == (1080, 2400)


def test_named_and_hex_colors_both_work(client: TestClient):
    named = client.get(f"/w/span.png?{SPAN}&fg=base03&bg=base3&a=orange")
    hexed = client.get(f"/w/span.png?{SPAN}&fg=002b36&bg=fdf6e3&a=cb4b16")

    assert named.status_code == hexed.status_code == 200
    assert named.content == hexed.content


@pytest.mark.parametrize(
    "query",
    [
        "f=2026-09-01",  # no end
        "t=2026-09-30",  # no start
        "f=nonsense&t=2026-09-30",
        "f=2026-11-30&t=2026-09-01",  # reversed
        "f=2026-09-01&t=2026-11-30&d=pixel9",
        "f=2026-09-01&t=2026-11-30&s=triangle",
        "f=2026-09-01&t=2026-11-30&fg=chartreuse",
        "f=2026-09-01&t=2026-11-30&tz=Mars/Olympus",
        "f=2026-09-01&t=2026-11-30&w=1080",  # width without height
        "f=2026-09-01&t=2026-11-30&w=10&h=10",  # below the minimum side
        "f=1900-01-01&t=2026-11-30",  # more weeks than pixels
        "f=2026-09-01&t=2026-11-30&g=0",
        "f=2026-09-01&t=2026-11-30&g=9",
        "f=2026-09-01&t=2026-11-30&wk=roman",
        "f=2026-09-01&t=2026-11-30&ft=quote",
        "f=2026-09-01&t=2026-11-30&ft=bar",
        "f=2026-09-01&t=2026-11-30&lb=middle",
        "f=2026-09-01&t=2026-11-30&th=sepia",
        "f=2026-09-01&t=2026-11-30&ck=huge",
        "f=2026-09-01&t=2026-11-30&ink=neon",
        "f=2026-09-01&t=2026-11-30&lang=de",
        "f=2026-09-01&t=2026-11-30&hdr=roman",
        "f=yesterday&t=2026-11-30",
        "f=2026-09-01&t=90x",
    ],
)
def test_bad_requests_are_rejected(client: TestClient, query: str):
    assert client.get(f"/w/span.png?{query}").status_code == 400


@pytest.mark.parametrize("group", [1, 2, 3, 4])
def test_grouping_is_accepted(client: TestClient, group: int):
    assert client.get(f"/w/span.png?{SPAN}&g={group}").status_code == 200


def test_grouping_changes_the_image(client: TestClient):
    one = client.get(f"/w/span.png?{SPAN}&g=1")
    two = client.get(f"/w/span.png?{SPAN}&g=2")
    assert one.content != two.content
    assert one.headers["etag"] != two.headers["etag"]


def test_default_grouping_is_two_weeks_per_row(client: TestClient):
    default = client.get(f"/w/span.png?{SPAN}")
    explicit = client.get(f"/w/span.png?{SPAN}&g=2")
    assert default.content == explicit.content


@pytest.mark.parametrize("numbering", ["iso", "n"])
def test_both_week_numberings_render(client: TestClient, numbering: str):
    assert client.get(f"/w/span.png?{SPAN}&wk={numbering}").status_code == 200


def test_week_numbering_changes_the_image(client: TestClient):
    iso = client.get(f"/w/span.png?{SPAN}&wk=iso")
    ordinal = client.get(f"/w/span.png?{SPAN}&wk=n")
    assert iso.content != ordinal.content
    assert iso.headers["etag"] != ordinal.headers["etag"]


@pytest.mark.parametrize("mode", ["pct", "left", "week", "none", "0", "1"])
def test_every_footer_mode_is_served(client: TestClient, mode: str):
    assert client.get(f"/w/span.png?{SPAN}&ft={mode}").status_code == 200


def test_footer_modes_differ(client: TestClient):
    seen = {
        client.get(f"/w/span.png?{SPAN}&ft={mode}").content
        for mode in ("pct", "left", "week", "none")
    }
    assert len(seen) == 4


@pytest.mark.parametrize("clock", ["std", "big"])
def test_both_clock_sizes_are_served(client: TestClient, clock: str):
    assert client.get(f"/w/span.png?{SPAN}&ck={clock}").status_code == 200


def test_the_clock_size_changes_the_image(client: TestClient):
    std = client.get(f"/w/span.png?{SPAN}&ck=std")
    big = client.get(f"/w/span.png?{SPAN}&ck=big")
    assert std.content != big.content


@pytest.mark.parametrize("header", ["days", "count", "none"])
def test_every_top_axis_is_served(client: TestClient, header: str):
    assert client.get(f"/w/span.png?{SPAN}&hdr={header}").status_code == 200


def test_top_axis_modes_differ(client: TestClient):
    seen = {client.get(f"/w/span.png?{SPAN}&hdr={h}").content for h in ("days", "count", "none")}
    assert len(seen) == 3


@pytest.mark.parametrize("language", ["en", "ru"])
def test_both_languages_are_served(client: TestClient, language: str):
    assert client.get(f"/w/span.png?{SPAN}&lang={language}").status_code == 200


def test_the_language_changes_the_image(client: TestClient):
    english = client.get(f"/w/span.png?{SPAN}&lang=en&ft=left")
    russian = client.get(f"/w/span.png?{SPAN}&lang=ru&ft=left")
    assert english.content != russian.content


def test_the_first_weekday_changes_the_image(client: TestClient):
    monday = client.get(f"/w/span.png?{SPAN}&wd=0")
    sunday = client.get(f"/w/span.png?{SPAN}&wd=6")
    assert sunday.status_code == 200
    assert monday.content != sunday.content


@pytest.mark.parametrize("ink", ["bright", "cream"])
def test_both_inks_are_served(client: TestClient, ink: str):
    assert client.get(f"/w/span.png?{SPAN}&ink={ink}").status_code == 200


def test_a_nudge_changes_the_image(client: TestClient):
    plain = client.get(f"/w/span.png?{SPAN}")
    nudged = client.get(f"/w/span.png?{SPAN}&sh=6")
    assert nudged.status_code == 200
    assert nudged.content != plain.content


@pytest.mark.parametrize("side", ["left", "right", "split"])
def test_every_label_placement_is_served(client: TestClient, side: str):
    assert client.get(f"/w/span.png?{SPAN}&lb={side}").status_code == 200


def test_label_placements_differ(client: TestClient):
    seen = {client.get(f"/w/span.png?{SPAN}&lb={s}").content for s in ("left", "right", "split")}
    assert len(seen) == 3


def test_dark_theme_inverts_the_page(client: TestClient):
    light = client.get(f"/w/span.png?{SPAN}&th=light")
    dark = client.get(f"/w/span.png?{SPAN}&th=dark")

    assert dark.status_code == 200
    # The themes are Solarized's own two paper tones, base3 and base03.
    with Image.open(io.BytesIO(light.content)) as pale, Image.open(io.BytesIO(dark.content)) as dim:
        assert pale.getpixel((0, 0)) == (0xFD, 0xF6, 0xE3)
        assert dim.getpixel((0, 0)) == (0x00, 0x2B, 0x36)


def test_explicit_colors_override_the_theme(client: TestClient):
    response = client.get(f"/w/span.png?{SPAN}&th=dark&bg=base03")
    with Image.open(io.BytesIO(response.content)) as image:
        assert image.getpixel((0, 0)) == (0x00, 0x2B, 0x36)


def test_a_matching_etag_gets_304_and_no_body(client: TestClient):
    """The phone refetches daily; inside one span most days are the same drawing."""
    first = client.get(f"/w/span.png?{SPAN}")
    again = client.get(f"/w/span.png?{SPAN}", headers={"If-None-Match": first.headers["etag"]})

    assert again.status_code == 304
    assert again.content == b""
    assert again.headers["etag"] == first.headers["etag"]
    assert again.headers["cache-control"].startswith("public, max-age=")


def test_a_stale_etag_gets_the_image(client: TestClient):
    response = client.get(f"/w/span.png?{SPAN}", headers={"If-None-Match": '"nonsense"'})
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"


def test_a_changed_setting_invalidates_the_etag(client: TestClient):
    first = client.get(f"/w/span.png?{SPAN}")
    stale = {"If-None-Match": first.headers["etag"]}
    changed = client.get(f"/w/span.png?{SPAN}&s=r", headers=stale)
    assert changed.status_code == 200


def test_the_quote_rotation_is_served_for_the_builder(client: TestClient):
    body = client.get("/api/quotes").json()

    assert body["today"]["line"] and body["today"]["author"]
    assert len(body["quotes"]) > 10
    assert body["today"] in body["quotes"]


def test_a_custom_quote_replaces_the_rotation(client: TestClient):
    rotated = client.get(f"/w/span.png?{SPAN}&q=1")
    custom = client.get(f"/w/span.png?{SPAN}&q=1&qt=Ship%20it&qa=Nobody")

    assert custom.status_code == 200
    assert custom.content != rotated.content


def test_a_custom_quote_needs_no_q_flag(client: TestClient):
    """qt alone must draw: the flag is about the rotation, not about quoting."""
    plain = client.get(f"/w/span.png?{SPAN}")
    own = client.get(f"/w/span.png?{SPAN}&qt=Ship%20it")

    assert own.status_code == 200
    assert own.content != plain.content
    assert own.content == client.get(f"/w/span.png?{SPAN}&q=1&qt=Ship%20it").content


def test_an_overlong_quote_is_rejected(client: TestClient):
    response = client.get(f"/w/span.png?{SPAN}&q=1&qt={'x' * 400}")
    assert response.status_code == 422


def test_a_retired_parameter_is_simply_ignored(client: TestClient):
    """`yc` set the new-year tint before that mark was dropped; old links must not 400."""
    assert client.get(f"/w/span.png?{SPAN}&yc=green").status_code == 200


def test_the_quote_is_off_by_default_and_changes_the_image(client: TestClient):
    plain = client.get(f"/w/span.png?{SPAN}")
    quoted = client.get(f"/w/span.png?{SPAN}&q=1")

    assert quoted.status_code == 200
    assert quoted.content != plain.content
    assert quoted.headers["etag"] != plain.headers["etag"]


@pytest.mark.parametrize(
    "theme",
    ["light", "dark", "gray", "grey", "white", "black", "teal", "ultramarine", "pink", "sand"],
)
def test_every_theme_is_served(client: TestClient, theme: str):
    assert client.get(f"/w/span.png?{SPAN}&th={theme}").status_code == 200


def test_the_bar_toggles_on_its_own(client: TestClient):
    with_bar = client.get(f"/w/span.png?{SPAN}&br=1&ft=none")
    without = client.get(f"/w/span.png?{SPAN}&br=0&ft=none")
    assert with_bar.status_code == 200
    assert with_bar.content != without.content


def test_month_breaks_change_the_image(client: TestClient):
    joined = client.get(f"/w/span.png?{SPAN}&mb=0")
    broken = client.get(f"/w/span.png?{SPAN}&mb=1")
    assert broken.status_code == 200
    assert joined.content != broken.content


def test_fade_can_be_switched_off(client: TestClient):
    faded = client.get(f"/w/span.png?{SPAN}&fd=1")
    flat = client.get(f"/w/span.png?{SPAN}&fd=0")
    assert faded.content != flat.content


@pytest.mark.parametrize("query", ["we=0", "mk=0", "we=0&mk=0"])
def test_backdrops_can_be_switched_off(client: TestClient, query: str):
    plain = client.get(f"/w/span.png?{SPAN}&{query}")
    full = client.get(f"/w/span.png?{SPAN}")
    assert plain.status_code == 200
    assert plain.content != full.content


def test_preview_draws_the_lock_screen_over_the_wallpaper(client: TestClient):
    wallpaper = client.get(f"/w/span.png?{SPAN}")
    preview = client.get(f"/w/span.png?{SPAN}&pv=1")

    assert preview.status_code == 200
    assert preview.content != wallpaper.content
    with Image.open(io.BytesIO(preview.content)) as image:
        assert image.size == (DEVICES["i16"].width, DEVICES["i16"].height)


def test_declared_but_unbuilt_modes_say_so(client: TestClient):
    response = client.get(f"/w/life.png?{SPAN}")
    assert response.status_code == 501
    assert "not implemented" in response.json()["detail"]


@pytest.mark.parametrize("mode", ["year", "quarter", "month"])
def test_calendar_modes_need_no_dates_at_all(client: TestClient, mode: str):
    """The point of these links is that they never expire, so they carry no dates."""
    response = client.get(f"/w/{mode}.png?d=i16")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"


def test_calendar_modes_differ_from_each_other(client: TestClient):
    seen = {client.get(f"/w/{mode}.png").content for mode in ("year", "quarter", "month")}
    assert len(seen) == 3


@pytest.mark.parametrize("value", ["today", "now", "90d", "-30d", "4w", "-2m", "1y", "%2B90d"])
def test_relative_dates_are_accepted(client: TestClient, value: str):
    response = client.get(f"/w/span.png?f=2026-01-01&t={value}")
    # Some offsets land before the start; either a picture or a clear 400, never a 500.
    assert response.status_code in (200, 400)


@pytest.mark.parametrize(
    "query",
    [
        "f=today&t=9999y",  # the year runs past 9999
        "f=today&t=-8000y",  # and past year 1 the other way
        "f=0001-01-01&t=0001-01-02&wd=3",  # week_start walks back into year 0
        "f=9999-12-31&t=9999-12-31",  # the row walk steps past the last day
        "f=today&t=%2B9999y",
    ],
)
def test_dates_at_the_edge_of_the_calendar_are_refused_not_crashed(client: TestClient, query: str):
    """Date arithmetic outside [1, 9999] used to escape as a 500 with a traceback.

    The grid walks a few days either side of the span, so the span itself has to
    stop short of the boundary — checked once, at the parser.
    """
    assert client.get(f"/w/span.png?{query}").status_code == 400


def test_the_render_queue_sheds_load_instead_of_growing(client: TestClient):
    """Past the queue limit a request is refused at once, not left to pile up.

    Forty threads each holding a whole image is how the container gets
    OOM-killed; the queue is what bounds how many can be in flight.
    """
    import threading

    from wallcal import app as app_mod

    # Hold both slots, then fill the queue, so the next caller has nowhere to go.
    app_mod.RENDER_SLOTS.acquire()
    app_mod.RENDER_SLOTS.acquire()
    with app_mod._queue_lock:
        app_mod._queued = app_mod.QUEUE_LIMIT
    try:
        response = client.get(f"/w/span.png?{SPAN}")
        assert response.status_code == 503
        assert response.headers["Retry-After"]
    finally:
        with app_mod._queue_lock:
            app_mod._queued = 0
        app_mod.RENDER_SLOTS.release()
        app_mod.RENDER_SLOTS.release()

    assert client.get(f"/w/span.png?{SPAN}").status_code == 200
    assert threading.active_count() >= 1


def test_a_screen_too_large_to_render_is_refused(client: TestClient):
    """Per-side limits still allowed 4096x4096 — sixteen megapixels per request."""
    response = client.get("/w/span.png?w=4096&h=4096&" + SPAN.split("&", 2)[0])
    assert response.status_code == 400
    assert "pixels" in response.json()["detail"]


def test_the_largest_real_phone_still_fits(client: TestClient):
    assert client.get(f"/w/span.png?{SPAN}&d=i16pm").status_code == 200


def test_todays_quote_matches_the_zone_the_wallpaper_uses(client: TestClient):
    """/api/quotes and the render must agree on what day it is."""
    from datetime import datetime

    from wallcal import quotes
    from wallcal.app import DEFAULT_TZ, _zone

    payload = client.get("/api/quotes").json()
    line, author = quotes.for_day(datetime.now(_zone(DEFAULT_TZ)).date())
    assert payload["today"] == {"line": line, "author": author}


def test_a_bare_plus_in_the_query_still_works(client: TestClient):
    """A literal + decodes to a space; the parser has to survive both spellings."""
    plus = client.get("/w/span.png?f=today&t=+90d")
    bare = client.get("/w/span.png?f=today&t=90d")

    assert plus.status_code == 200
    assert plus.content == bare.content


def test_a_relative_end_gives_a_link_that_outlives_its_span(client: TestClient):
    fixed = client.get("/w/span.png?f=2026-01-01&t=2026-12-31")
    rolling = client.get("/w/span.png?f=today&t=90d")

    assert rolling.status_code == 200
    assert rolling.content != fixed.content


def test_unknown_mode_is_rejected(client: TestClient):
    assert client.get(f"/w/moon.png?{SPAN}").status_code == 400
