# wallcal

Calendar wallpapers rendered on demand from a URL. Point your phone's daily
automation at one link and the lock screen redraws itself every morning — no
app, no account, no database. The URL *is* the configuration.

```
GET /w/span.png?f=2026-09-01&t=2026-11-30&d=i16&s=r
→ 200 image/png
```

Past days fade with distance: the filled run reads as a gradient towards today
rather than a flat block. A row is two whole weeks — fourteen days across, Monday to Sunday twice, with a
gap between the two so the weeks read as separate blocks. Days already spent are
filled, today is the accent color, the rest of the span is faint. Beside the grid: ISO week numbers every other row, and the month name set
sideways next to the rows it covers. `lb` decides the edge — `left` reads months,
weeks, dots; `right` reads dots, weeks, months; `split` puts weeks on the left
and months on the right, both the same distance from the dots.

Saturday and Sunday share a faint band, and the last day of each month gets a
tinted cell in the accent hue. With `q=1` a line for the day sits under the grid,
picked from `src/wallcal/quotes.py` by the date — the same day always gives the
same line, so a phone that refetches does not flicker between two of them. The dot field sits on the screen's center line — the labels
live in reserves on either side, so switching them off moves nothing. The top
third of the screen is left empty for the lock screen clock, and the progress
line drops into the lane between the flashlight and camera buttons.

Add `pv=1` to any URL to get a lock screen mock-up over the wallpaper — clock,
date, buttons — for judging the composition in a browser. Never set that one as
your wallpaper.

## Run it

```bash
uv sync
uv run wallcal                 # 0.0.0.0:8000
open http://localhost:8000/    # builder: every knob, live preview, copyable link
```

`WALLCAL_HOST`, `WALLCAL_PORT` and `WALLCAL_TZ` override the defaults;
`WALLCAL_TZ` decides which day counts as "today" when a request does not say.

`WALLCAL_DOMAIN` is the domain the service answers on; anything else in the
`Host` header is refused. `WALLCAL_TRUSTED_PROXY` names the proxy whose
`X-Forwarded-For` is believed, so the access log records the real caller rather
than the proxy. Both are unset by default, which is right on a laptop.

`WALLCAL_QUOTES` points at your own list and replaces the built-in one. One
quote per line, the author after a `|`; blank lines and lines starting with `#`
are ignored, so sources can sit in the file as comments. Any language the
bundled Inter covers — Cyrillic included:

```
# мои цитаты
Дело не в том, что у нас мало времени, а в том, что мы много его теряем | Сенека
Два самых главных воина — терпение и время | Лев Толстой
Самое длинное расстояние — от слов до дела
```

A dash is deliberately not a separator: Russian sets dashes inside sentences, and
splitting on one turned half a quote into an attribution. The pipe never appears
in prose, so it can mean exactly one thing; the last one on the line wins. A file
that cannot be read is an error at startup rather than a silent fall back.

## URL parameters

| key  | meaning                            | default | values                                    |
| ---- | ---------------------------------- | ------- | ----------------------------------------- |
| `f`  | span start                         | —       | `YYYY-MM-DD` or `YYYYMMDD`                |
| `t`  | span end                           | —       | same                                      |
| `d`  | screen preset                      | `i16`   | `i16`, `i16p`, `i16pm`                    |
| `w`  | explicit width (with `h`)          | —       | 320–4096, overrides `d`                   |
| `h`  | explicit height (with `w`)         | —       | 320–4096, and `w`×`h` at most 4.2 Mpx     |
| `s`  | dot shape                          | `c`     | `c` circle, `r` rounded square            |
| `th` | background preset                  | `light` | see the theme list below                  |
| `fg` | dot color, overrides the theme     | —       | Solarized name or hex (`dc322f`, `f00`)   |
| `bg` | background, overrides the theme    | —       | same                                      |
| `a`  | today's color                      | `orange`| same                                      |
| `ax` | weekday and month labels           | `1`     | `1`, `0`                                  |
| `lb` | where the labels go                | `left`  | `left`, `right`, `split`                  |
| `hdr`| what runs along the top            | `days`  | `days` MO TU…, `count` 7 · 14, `none`     |
| `lang` | wording on the axes and footer   | `en`    | `en`, `ru`                                |
| `wd` | first day of the week              | `0`     | `0` Monday … `6` Sunday                   |
| `ck` | room kept for the lock screen clock| `std`   | `std`, `big` for the tall iOS clock       |
| `sh` | nudge the grid, percent of height  | `0`     | `-15`…`15`, clamped to the safe band      |
| `ink`| strong end of the ramp             | `bright`| `bright`, `cream`                         |
| `ft` | what the footer says               | `pct`   | `pct`, `left`, `week`, `none`             |
| `br` | progress rule under the footer     | `1`     | `1`, `0`                                  |
| `mb` | start every month on a fresh row   | `0`     | `1`, `0`                                  |
| `fd` | fade older past days               | `1`     | `1`, `0`                                  |
| `g`  | whole weeks per row                | `2`     | `1`–`4`                                   |
| `sp` | gap between weeks in a row         | `1`     | `1`, `0`                                  |
| `we` | band behind Saturday and Sunday    | `1`     | `1`, `0`                                  |
| `mk` | tint the last day of each month    | `1`     | `1`, `0`                                  |
| `mc` | month-end tint                     | `orange`| Solarized name or hex                     |
| `q`  | a line for the day under the grid  | `0`     | `1`, `0`                                  |
| `qt` | your own line, instead of the day's| —       | up to 240 characters                      |
| `qa` | who said it                        | —       | up to 60 characters                       |
| `wk` | what the left-edge numbers count   | `iso`   | `iso` week of year, `n` from span start   |
| `pv` | draw the lock screen mock-up       | `0`     | `1`, `0`                                  |
| `tz` | zone that decides "today"          | env     | IANA name, e.g. `Europe/Moscow`           |

Colors accept the sixteen Solarized names (`base03`…`base3`, `yellow`, `orange`,
`red`, `magenta`, `violet`, `blue`, `cyan`, `green`) plus `black` and `white`.

Themes: `light` (Solarized base3) and `dark` (base03), `gray` for a soft
graphite, `white` and `black` for the pure ones, plus `teal`, `ultramarine`,
`pink` and `sand` matched by eye to the iPhone 16 finishes — set the wallpaper to
the colour of the phone holding it.

Tones follow the background on their own. Solarized is one lightness ramp read
from either end, so the dots, the fade, the axes and the bands are picked off
that ramp according to how dark the background is — set `bg` to anything and the
rest stays legible without being restated. Mixing a dot color into the
background instead would land on neutral grey, which beside the orange accent
reads faintly green; the palette's own steps carry a consistent cool cast and do
not. `fg` still overrides the dots when you want an exact color.

The response may be cached until midnight in the requested zone, and no longer —
that is exactly when the drawing changes. Send the `ETag` back as
`If-None-Match` and an unchanged drawing answers `304` with no body: inside one
span most mornings render the same image, and neither the transfer nor the
render has to happen.

`pv=1` is a viewing aid for the builder page, not part of a wallpaper — the
builder never puts it in the link it hands you.

## Modes

`/w/<mode>.png` routes by mode:

- **`span`** — an arbitrary date range. Needs `f` and `t`.
- **`year`**, **`quarter`**, **`month`** — the current one, and no dates in the
  URL at all. A link written in fixed dates stops meaning anything the day its
  span ends; these roll over by themselves at the calendar boundary, so the
  Shortcut on the phone is set up once and never again.
- **`life`** — a whole life in weeks. Declared, returns 501. It will not reuse
  the span geometry: ~4700 weeks cannot be drawn seven columns to a row on a
  phone, so it needs its own row unit.

`f` and `t` also take `today` and offsets from it — `90d`, `-30d`, `4w`, `-2m`,
`1y`. The leading `+` is optional and better left out: a literal `+` in a query
string decodes to a space. `f=today&t=2027-06-01` is the useful shape — a span
that shortens by a day every morning.

## Put it on a phone

**iOS** — Shortcuts → Automation → Time of Day, daily, *Run Immediately*:

1. `Get Contents of URL` with your link
2. `Set Wallpaper Photo` → Lock Screen

In step 2 expand the arrow and turn off **Crop to Subject** and **Show
Preview**, or iOS re-crops the image and asks for confirmation every morning.

**Android** — MacroDroid or Tasker: an HTTP GET saved to a file on a daily
trigger, then Set Wallpaper from that file.

## Deploy

`Dockerfile` builds a self-contained image; `docs/docker.md` covers the build,
the run command and every environment variable. No compose file ships with it on
purpose — the domain, the port mapping and the reverse proxy are yours, and
nothing in the image assumes any of them.

## Develop

```bash
uv run pytest            # 503 tests, every screen preset
uv run mypy --strict src/wallcal
uvx ruff check --fix . && uvx ruff format .
```

Inter is bundled under `src/wallcal/assets/fonts` (SIL Open Font License 1.1) —
the render tests compare pixels, so the typeface cannot come from the system.
