"""HTTP layer.

The whole configuration lives in the query string: no database, no accounts,
nothing to back up. A URL is the wallpaper.
"""

from __future__ import annotations

import calendar
import hashlib
import os
import re
import threading
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from datetime import date, datetime, timedelta
from importlib.resources import files
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__, logs, quotes
from .devices import DeviceError
from .devices import resolve as resolve_size
from .grid import DEFAULT_WEEKS_PER_ROW, GridError, WeekNumbering
from .layout import ClockError, LabelError, LayoutError, parse_clock, parse_label_side
from .markers import MarkerError, TooManyMarkers, parse_markers
from .modes import ModeError, ModeNotImplemented, Params, build
from .palette import ColorError, InkError, ThemeError, parse_color, parse_ink, parse_theme
from .preview import overlay
from .quotes import rotation
from .render import (
    BarError,
    FooterError,
    HeaderError,
    ProductionError,
    ShapeError,
    Style,
    parse_bar,
    parse_footer,
    parse_header,
    parse_production,
    parse_shape,
    render_span,
    to_png,
)
from .sky import SkyError, parse_location, parse_sky
from .strings import LanguageError, parse_language

DEFAULT_TZ = os.environ.get("WALLCAL_TZ", "UTC")

# The domain the service answers on, e.g. "wallcal.example.com". A request whose
# Host header is not in this list is refused, which is what stops a page on
# another site from pointing a browser at this container's address and reading
# it as though it were its own. Unset means any Host is accepted: right for a
# laptop, wrong for something on the open internet.
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("WALLCAL_DOMAIN", "*").split(",") if h.strip()]


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Read the quote file before serving.

    It is configuration, and configuration that is wrong should stop the
    container rather than surface as a 500 on the first request that happens to
    ask for a quote — possibly days later.
    """
    rotation()
    yield


app = FastAPI(title="wallcal", docs_url="/docs", redoc_url=None, lifespan=lifespan)
logs.configure()
app.add_middleware(logs.AccessLog)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)


# The plus is optional because a literal "+" in a query string decodes to a
# space: a link written as t=+90d arrives as " 90d" and would never parse.
RELATIVE = re.compile(r"^([+-]?)(\d{1,4})([dwmy])$")
UNIT_DAYS = {"d": 1, "w": 7}

# The grid walks a few days either side of the span — back to the start of the
# first week, forward past the end of the last one — and `date` has no room
# outside [1, 9999] for that walk. Clamping here, at the edge of the system,
# turns what would be an OverflowError deep in the arithmetic into one 400.
EARLIEST = date(2, 1, 1)
LATEST = date(9998, 12, 31)

# FastAPI runs this sync handler in a pool of forty threads, and a render holds
# its whole working set — image, mask, glyphs — in memory. Forty at once is how
# a self-hosted box gets OOM-killed by a single client with a loop.
#
# Two renders at a time, eight more allowed to wait. A render is ~140ms, so a
# full queue clears in well under a second; anything past that is a burst no
# phone is waiting on, and a fast 503 serves it better than a slow 200.
RENDER_SLOTS = threading.BoundedSemaphore(2)
QUEUE_LIMIT = 8
RENDER_WAIT = 5

_queued = 0
_queue_lock = threading.Lock()


@contextmanager
def render_slot() -> Iterator[None]:
    """One of the render slots, or a 503 rather than an unbounded wait."""
    global _queued
    with _queue_lock:
        if _queued >= QUEUE_LIMIT:
            raise HTTPException(503, "busy rendering; retry", headers={"Retry-After": "2"})
        _queued += 1
    try:
        if not RENDER_SLOTS.acquire(timeout=RENDER_WAIT):
            raise HTTPException(503, "busy rendering; retry", headers={"Retry-After": "5"})
    finally:
        with _queue_lock:
            _queued -= 1
    try:
        yield
    finally:
        RENDER_SLOTS.release()


def _parse_date(value: str, field: str, today: date) -> date:
    """An absolute date, `today`, or an offset from it like `+90d` or `-3m`.

    Offsets are what keep a link alive: a span written in fixed dates stops
    meaning anything the day it ends.
    """
    text = value.strip().lower()
    if text in ("today", "now"):
        return today

    match = RELATIVE.match(text)
    if match:
        sign, amount, unit = match.groups()
        step = int(amount) * (-1 if sign == "-" else 1)
        try:
            if unit in UNIT_DAYS:
                return _in_range(today + timedelta(days=step * UNIT_DAYS[unit]), field, value)
            months = step * (12 if unit == "y" else 1)
            return _in_range(_add_months(today, months), field, value)
        except (OverflowError, ValueError) as exc:
            raise HTTPException(400, f"{field}={value!r} lands outside the calendar") from exc

    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return _in_range(datetime.strptime(text, fmt).date(), field, value)
        except ValueError:
            continue
    raise HTTPException(
        400,
        f"{field}={value!r} is not a date; use YYYY-MM-DD, `today`, or an offset like +90d",
    )


def _in_range(day: date, field: str, value: str) -> date:
    if not EARLIEST <= day <= LATEST:
        raise HTTPException(
            400, f"{field}={value!r} is outside {EARLIEST.isoformat()}..{LATEST.isoformat()}"
        )
    return day


def _add_months(day: date, months: int) -> date:
    """Same day of a later month, clamped to that month's length (31 Jan + 1m = 28 Feb)."""
    total = day.year * 12 + (day.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(day.day, last))


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise HTTPException(400, f"unknown time zone {name!r}") from exc


def _seconds_to_midnight(now: datetime) -> int:
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(60, int((tomorrow - now).total_seconds()))


@app.get("/w/{mode}.png")
def wallpaper(  # noqa: PLR0913 - every parameter is a documented knob of the URL API
    request: Request,
    mode: str,
    start: Annotated[str | None, Query(alias="f", description="span start, YYYY-MM-DD")] = None,
    end: Annotated[str | None, Query(alias="t", description="span end, YYYY-MM-DD")] = None,
    device: Annotated[str | None, Query(alias="d", description="screen preset")] = None,
    width: Annotated[int | None, Query(alias="w", description="explicit width")] = None,
    height: Annotated[int | None, Query(alias="h", description="explicit height")] = None,
    shape: Annotated[str, Query(alias="s", description="c=circle, r=rounded square")] = "c",
    theme: Annotated[str, Query(alias="th", description="light or dark")] = "light",
    background: Annotated[
        str | None, Query(alias="bg", description="background color, overrides the theme")
    ] = None,
    dot: Annotated[
        str | None, Query(alias="fg", description="dot color, overrides the theme")
    ] = None,
    accent: Annotated[str, Query(alias="a", description="today's color")] = "orange",
    axes: Annotated[bool, Query(alias="ax", description="weekday and month labels")] = True,
    header: Annotated[
        str, Query(alias="hdr", description="top axis: days, count or none")
    ] = "days",
    footer: Annotated[str, Query(alias="ft", description="pct, left, week or none")] = "pct",
    bar: Annotated[
        str, Query(alias="br", description="progress rule: span, year, quarter, month, none")
    ] = "1",
    fade: Annotated[bool, Query(alias="fd", description="fade older past days")] = True,
    month_breaks: Annotated[
        bool, Query(alias="mb", description="start every month on a fresh row")
    ] = False,
    split: Annotated[bool, Query(alias="sp", description="gap between weeks in a row")] = True,
    labels: Annotated[
        str, Query(alias="lb", description="label placement: left, right or split")
    ] = "left",
    clock: Annotated[
        str, Query(alias="ck", description="room for the lock screen clock: std or big")
    ] = "big",
    shift: Annotated[
        int, Query(alias="sh", ge=-15, le=15, description="nudge the grid, percent of height")
    ] = 0,
    ink: Annotated[str, Query(description="strong end of the ramp: bright or cream")] = "bright",
    language: Annotated[str, Query(alias="lang", description="en or ru")] = "en",
    first_weekday: Annotated[
        int, Query(alias="wd", ge=0, le=6, description="0 Monday .. 6 Sunday")
    ] = 0,
    weekends: Annotated[bool, Query(alias="we", description="band behind days off")] = True,
    production: Annotated[str, Query(alias="pc", description="production calendar: 0 or ru")] = "0",
    marks: Annotated[bool, Query(alias="mk", description="tint the last day of a month")] = True,
    month_mark: Annotated[str, Query(alias="mc", description="month-end tint")] = "orange",
    markers: Annotated[
        list[str] | None,
        Query(alias="m", description="tint a rule's days: <rule>@<colour>[@<label>]"),
    ] = None,
    quote: Annotated[
        bool, Query(alias="q", description="a line for the day under the grid")
    ] = False,
    quote_text: Annotated[
        str, Query(alias="qt", max_length=240, description="your own line, instead of the rotation")
    ] = "",
    quote_author: Annotated[str, Query(alias="qa", max_length=60, description="who said it")] = "",
    sky: Annotated[
        str, Query(alias="sky", description="band under the grid: none, moon, sun or both")
    ] = "none",
    lat: Annotated[
        float | None, Query(ge=-90, le=90, description="latitude, kept to two decimals")
    ] = None,
    lon: Annotated[
        float | None, Query(ge=-180, le=180, description="longitude, kept to two decimals")
    ] = None,
    day_length: Annotated[
        bool, Query(alias="dl", description="day length and the change from yesterday")
    ] = True,
    numbering: Annotated[
        str, Query(alias="wk", description="iso week number, or n from the span start")
    ] = "iso",
    preview: Annotated[
        bool, Query(alias="pv", description="draw a lock screen mock-up over it")
    ] = False,
    group: Annotated[
        int, Query(alias="g", description="whole weeks per row")
    ] = DEFAULT_WEEKS_PER_ROW,
    tz: Annotated[str | None, Query(description="IANA zone deciding what 'today' is")] = None,
) -> Response:
    zone = _zone(tz or DEFAULT_TZ)
    now = datetime.now(zone)

    # Too many markers is a 422 rather than a 400: the URL is well formed and
    # every marker in it is valid, there are just more than one link may carry.
    try:
        rules = parse_markers(markers)
    except TooManyMarkers as exc:
        raise HTTPException(422, str(exc)) from exc
    except (MarkerError, ColorError) as exc:
        raise HTTPException(400, str(exc)) from exc

    try:
        size = resolve_size(device, width, height)
        sky_mode = parse_sky(sky)
        style = Style(
            background=parse_color(background) if background else parse_theme(theme),
            dot=parse_color(dot) if dot else None,
            accent=parse_color(accent),
            shape=parse_shape(shape),
            axes=axes,
            header=parse_header(header),
            footer=parse_footer(footer),
            bar=parse_bar(bar),
            fade=fade,
            split=split,
            labels=parse_label_side(labels),
            clock=parse_clock(clock),
            shift=shift,
            ink=parse_ink(ink),
            language=parse_language(language),
            first_weekday=first_weekday,
            weekends=weekends,
            production=parse_production(production),
            marks=marks,
            month_mark=parse_color(month_mark),
            markers=rules,
            quote=quote,
            quote_text=quote_text,
            quote_author=quote_author,
            sky=sky_mode,
            location=parse_location(sky_mode, lat, lon),
            day_length=day_length,
        )
        week_numbering = WeekNumbering(numbering.strip().lower())
    except (
        DeviceError,
        ColorError,
        ShapeError,
        BarError,
        FooterError,
        HeaderError,
        LabelError,
        ThemeError,
        ClockError,
        InkError,
        LanguageError,
        ProductionError,
        SkyError,
    ) as exc:
        raise HTTPException(400, str(exc)) from exc
    except ValueError as exc:
        known = ", ".join(n.value for n in WeekNumbering)
        raise HTTPException(
            400, f"unknown week numbering {numbering!r}; use one of: {known}"
        ) from exc

    params = Params(
        start=_parse_date(start, "f", now.date()) if start else None,
        end=_parse_date(end, "t", now.date()) if end else None,
        today=now.date(),
        weeks_per_row=group,
        numbering=week_numbering,
        month_breaks=month_breaks,
        first_weekday=first_weekday,
    )

    try:
        grid = build(mode, params)
    except ModeNotImplemented as exc:
        raise HTTPException(501, str(exc)) from exc
    except (ModeError, GridError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc

    # The zone is in there for the sun line alone: it is the one thing drawn on
    # a local clock, so two zones on the same date are two different images.
    # `Cache-Control` is public, and a shared cache holding one ETag for both
    # would be entitled to hand one of them the other's picture.
    fingerprint = hashlib.sha256(
        f"{mode}|{size}|{style}|{zone.key}|{grid.start}|{grid.end}|{grid.today}"
        f"|{grid.rows}|{grid.columns}|{grid.week_labels}|{preview}".encode()
    ).hexdigest()[:32]
    etag = f'"{fingerprint}"'
    headers = {
        # The image changes when "today" moves, so it may be cached exactly
        # until midnight in the requested zone and not a second longer.
        "Cache-Control": f"public, max-age={_seconds_to_midnight(now)}",
        "ETag": etag,
    }
    # A phone refetches this every morning; most mornings inside one span it is
    # the same drawing. Answering 304 saves the transfer and the render both.
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)

    try:
        with render_slot():
            image = render_span(grid, size[0], size[1], style, zone)
            if preview:
                overlay(image, style, now.date())
            payload = to_png(image)
            # The image is the largest thing in the request; the bytes are all
            # that is left to send.
            del image
    except LayoutError as exc:
        raise HTTPException(400, str(exc)) from exc

    return Response(content=payload, media_type="image/png", headers=headers)


@app.get("/api/quotes")
def quote_list(response: Response) -> dict[str, object]:
    """The whole rotation plus today's pick, so the builder can shuffle offline."""
    # The same zone the wallpaper uses. On `date.today()` this drifted a day
    # from the render whenever WALLCAL_TZ differed from the container clock,
    # and the builder page then previewed a line the phone would not get.
    now = datetime.now(_zone(DEFAULT_TZ))
    line, author = quotes.for_day(now.date())
    # The rotation is a file and today's pick turns over at midnight, so this
    # answer is good until then — and it is asked for again on every visit.
    response.headers["Cache-Control"] = f"public, max-age={_seconds_to_midnight(now)}"
    return {
        "today": {"line": line, "author": author},
        "quotes": [{"line": text, "author": who} for text, who in rotation()],
    }


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


# Read once, not per request: it is a single file that only changes on deploy.
# The version goes in with it, which is what lets the page ask for a preview the
# browser can keep between visits and still get a new one after an upgrade.
_PAGE = (
    files("wallcal.assets")
    .joinpath("index.html")
    .read_text(encoding="utf-8")
    .replace("__WALLCAL_VERSION__", __version__)
)
_PAGE_ETAG = f'"{hashlib.sha256(_PAGE.encode()).hexdigest()[:32]}"'


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> Response:
    """The builder page: every knob of the URL API, with a live preview."""
    # no-cache, not no-store: the browser keeps the page and asks whether it is
    # still good. A revisit then costs one round trip and no bytes, and a deploy
    # still lands immediately.
    headers = {"Cache-Control": "no-cache", "ETag": _PAGE_ETAG}
    if request.headers.get("if-none-match") == _PAGE_ETAG:
        return Response(status_code=304, headers=headers)
    return HTMLResponse(_PAGE, headers=headers)
