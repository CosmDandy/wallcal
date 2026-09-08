# wallcal

[![Open in GitHub Codespaces][codespaces]](https://codespaces.new/CosmDandy/wallcal)

[![build][build]](https://github.com/CosmDandy/wallcal/actions/workflows/image.yml) [![scorecard][scorecard]](https://scorecard.dev/viewer/?uri=github.com/CosmDandy/wallcal) [![SLSA][SLSA]](https://slsa.dev) [![ghcr.io][ghcr.io]](https://github.com/CosmDandy/wallcal/pkgs/container/wallcal) [![license][license]](LICENSE)

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
of the screen is left empty for the lock screen clock, sized for the tall one by
default. The footer line sits just under the grid: the lane between the
flashlight and camera buttons is where iOS puts the Focus pill and the
notification stack, so only the progress rule goes down there — a hairline still
reads under a notification, a sentence does not.

`pc=ru` hands that band to the Russian production calendar instead of to the
weekend. It then follows the days actually not worked: the Friday moved next to
12 June joins Thursday and the weekend into one four-day shape, and the Saturday
the government turned into a working day loses its band. The band is the union
of those days rather than two fixed columns — a run merges sideways and down the
rows, so what you see is the shape of the time off. It stops at the gap between
the two weeks in a row: the gap is what makes a row read as two weeks, and
nothing else in the drawing crosses it.

The holidays come from art. 112 of the Labour Code and never move. The transfers
on top of them do, once a year and by decree, so they are a table in
`src/wallcal/workdays.py` rather than a rule — 2025 and 2026 are in it. A year
that is not falls back to plain weekends plus the holidays: wrong by a handful
of days rather than by a season, which is the failure a calendar can survive.
Guessing at a decree is not.

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
| `ck` | room kept for the lock screen clock| `big`   | `big` for the tall iOS clock, `std`       |
| `sh` | nudge the grid, percent of height  | `0`     | `-15`…`15`, clamped to the safe band      |
| `ink`| strong end of the ramp             | `bright`| `bright`, `cream`                         |
| `ft` | what the footer says               | `pct`   | `pct`, `left`, `week`, `none`             |
| `br` | period the progress rule fills     | `1`     | `1` span, `year`, `quarter`, `month`, `0` |
| `mb` | start every month on a fresh row   | `0`     | `1`, `0`                                  |
| `fd` | fade older past days               | `1`     | `1`, `0`                                  |
| `g`  | whole weeks per row                | `2`     | `1`–`4`                                   |
| `sp` | gap between weeks in a row         | `1`     | `1`, `0`                                  |
| `we` | band behind the days not worked    | `1`     | `1`, `0`                                  |
| `pc` | production calendar behind the band| `0`     | `0` weekends only, `ru` Russia            |
| `mk` | tint the last day of each month    | `1`     | `1`, `0`                                  |
| `mc` | month-end tint                     | `orange`| Solarized name or hex                     |
| `m`  | tint a rule's days, repeatable     | —       | `<rule>[~]@<color>[@<label>]`             |
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

`m` marks days of your own, one `m` per rule: `m=mo,we@blue@Gym` tints every
Monday and Wednesday, `m=d10,d25@green@Payday` the 10th and the 25th of every
month, `m=2026-12-31@red@Ship` a single date, and
`m=2026-07-06..2026-07-12@cyan@Holiday` every day of a stretch — a trip, a
sprint, a notice period. Weekdays and days of the month
both take a list, because the thing being marked usually happens more than once
a month. A day the month does not have is skipped rather than clamped: `d31`
marks no day in April.

A rule ending in `~` is pulled back off any day nobody works —
`m=d10,d25~@green@Wages`. Wages are the case it exists for: paying late breaks
the law and paying early does not, so a day landing on a day off moves backwards
to the last working day before it, however long the run. Which days count as not
worked is the drawing's own answer, so with `pc=ru` a holiday pulls the day back
exactly as a Sunday does. A day pulled back out of the drawn span is simply not
drawn, and a stretch cannot be pulled back at all — it is a block of days
already, and moving every one of them would fold it shut.

The tint is the month-end recipe held back — the background lifted towards the
colour, but less far, and the shape pulled in off the cell edges — so a marked
day reads as a note on the field rather than a second grid over it, and it is
laid over both the non-working band and the month-end mark. Where two rules
cover the same day the last one in the URL wins, so write the rule first and its
exception after it.

The label after the colour is never drawn. It is there so a link handed to
someone else opens in the builder with the names still on it — a row of
anonymous colours is not something a second person can edit. Thirty-two markers
is the cap and past it the request is refused: the whole configuration is the
URL, and a URL nobody can paste has stopped being one.

The response may be cached until midnight in the requested zone, and no longer —
that is exactly when the drawing changes. Send the `ETag` back as
`If-None-Match` and an unchanged drawing answers `304` with no body: inside one
span most mornings render the same image, and neither the transfer nor the
render has to happen.

The progress rule under the footer measures whatever `br` names. Left at `1`
it fills with the drawn span — which the dot field already pictures, so the two
say one thing twice. Point it at a calendar period instead and it says something
the dots cannot: `mode=month&br=year` puts the month you are looking at inside
its year. `br=year&ft=pct` then shows two different numbers, one in words and
one as a picture, with nothing naming which is which; `ft=none` is the way out.

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
uv run pytest            # 561 tests, every screen preset
uv run pytest            # 598 tests, every screen preset
uv run mypy --strict src/wallcal
uvx ruff check --fix . && uvx ruff format .
```

Inter is bundled under `src/wallcal/assets/fonts` (SIL Open Font License 1.1) —
the render tests compare pixels, so the typeface cannot come from the system.

[codespaces]: https://github.com/codespaces/badge.svg
[build]: https://img.shields.io/github/actions/workflow/status/CosmDandy/wallcal/image.yml?branch=master&style=flat&label=build&labelColor=21262d&logo=githubactions&logoColor=8b949e
[scorecard]: https://img.shields.io/ossf-scorecard/github.com/CosmDandy/wallcal?style=flat&label=scorecard&labelColor=21262d
[SLSA]: https://img.shields.io/badge/SLSA-3-7828dc?style=flat&labelColor=21262d&logo=data%3Aimage%2Fpng%3Bbase64%2CiVBORw0KGgoAAAANSUhEUgAAAA4AAAAOCAMAAAAolt3jAAAABGdBTUEAALGPC%2FxhBQAAACBjSFJNAAB6JgAAgIQAAPoAAACA6AAAdTAAAOpgAAA6mAAAF3CculE8AAABMlBMVEXvMQDvMADwMQDwMADwMADvMADvMADwMADwMQDvMQDvMQDwMADwMADvMADwMADwMADwMQDvMQDvMQDwMQDvMQDwMQDwMADwMADwMQDwMADwMADvMADvMQDvMQDwMADwMQDwMADvMQDwMADwMQDwMADwMADwMADwMADwMADwMADvMQDvMQDwMADwMQDwMADvMQDvMQDwMADvMQDvMQDwMADwMQDwMQDwMQDvMQDwMADvMADwMADwMQDvMQDwMADwMQDwMQDwMQDwMQDvMQDvMQDvMADwMADvMADvMADvMADwMQDwMQDvMADvMQDvMQDvMADvMADvMQDwMQDvMQDvMADvMADvMADvMQDwMQDvMQDvMQDvMADvMADwMADvMQDvMQDvMQDvMADwMADwMQDwMAAAAAA%2FHoSwAAAAY3RSTlMpsvneQlQrU%2FLQSWzvM5DzmzeF9Pi%2BN6vvrk9HuP3asTaPgkVFmO3rUrMjqvL6d0LLTVjI%2FPuMQNSGOWa%2F6YU8zNuDLihJ0e6aMGzl8s2IT7b6lIFkRj1mtvQ0eJW95rG0%2BSid59x%2FAAAAAWJLR0Rltd2InwAAAAlwSFlzAAAOwwAADsMBx2%2BoZAAAAAd0SU1FB%2BYHGg0tGLrTaD4AAACqSURBVAjXY2BgZEqGAGYWVjYGdg4oj5OLm4eRgZcvBcThFxAUEk4WYRAVE09OlpCUkpaRTU6WY0iWV1BUUlZRVQMqUddgSE7W1NLS1gFp0NXTB3KTDQyNjE2Sk03NzC1A3GR1SytrG1s7e4dkBogtjk7OLq5uyTCuu4enl3cyhOvj66fvHxAIEmYICg4JDQuPiAQrEmGIio6JjZOFOjSegSHBBMpOToxPAgCJfDZC%2Fm2KHgAAACV0RVh0ZGF0ZTpjcmVhdGUAMjAyMi0wNy0yNlQxMzo0NToyNCswMDowMC8AywoAAAAldEVYdGRhdGU6bW9kaWZ5ADIwMjItMDctMjZUMTM6NDU6MjQrMDA6MDBeXXO2AAAAGXRFWHRTb2Z0d2FyZQB3d3cuaW5rc2NhcGUub3Jnm%2B48GgAAAABJRU5ErkJggg%3D%3D
[ghcr.io]: https://img.shields.io/badge/ghcr.io-wallcal-00a8c8?style=flat&labelColor=21262d&logo=docker&logoColor=8b949e
[license]: https://img.shields.io/github/license/CosmDandy/wallcal?style=flat&label=license&labelColor=21262d&color=484f58&logo=opensourceinitiative&logoColor=8b949e
