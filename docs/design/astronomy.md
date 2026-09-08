# Sun and moon

> **Superseded, 2026-09-08.** The band is gone. The sun line and the moon moved
> onto the footer line, in the lane between the lock screen buttons, because the
> lane was standing half empty — `ft=week` uses a third of it — and a band under
> the grid could only pay for itself out of the dots. What follows is kept for
> the reasoning it carries: the astronomy, the moon's geometry, the privacy
> argument and the `tz` finding all still hold. What it says about *placement*
> does not. The lane cannot hold `ft` and a full sun line at once, so the day's
> length and its change are dropped first and the type size never moves.


## The recommendation

Build it, but build one thing, not four. A single band under the grid, holding
a moon glyph and — when the URL carries coordinates — one line of numbers:
`06:12 – 19:48 · 13:36 +2:14`. The moon is drawn, not typed, at the size of a
grid dot and in the grid's own two tones, so it reads as one more dot rather
than as an emoji pasted onto a wallpaper. The band does not get a strip of its
own: it stands in the quote's slot, one occupant and never both, exactly as `qt`
and `q` already share that one slot (`Style.shows_quote`,
`src/wallcal/render.py`). So it is free whenever a quote was going to be there
anyway, and costs a quote's worth of pitch when it was not — which is the price
of the band being under the field rather than in it. Everything else this
feature could grow — twilight, golden hour, moonrise, a phase name, a
percentage, a default city, an IP lookup — is left out, and the reasons are at
the bottom.

## Where it sits

`layout.py` draws four horizontal lines across the bottom of the screen, and it
is worth being exact about where, because the room for the band is not a matter
of taste.

The grid lives between `CLOCK_TOP` and a floor that is computed rather than
named: `grid_floor` is `FOOTER_ROW` less `footer_slot`, and `FOOTER_ROW` is
`0.862h` (`src/wallcal/layout.py:45`, `layout.py:74-102`). Below that:

| what | where | source |
| ---- | ----- | ------ |
| grid floor | `0.837h` | `grid_floor(h)`, `layout.py:93` |
| footer line | `0.862h` | `FOOTER_ROW`, `layout.py:45` |
| top of the buttons | `0.8834h` on `i16` | `CONTROLS_ROW`, `CONTROLS_RADIUS` |
| progress rule | `0.943h` | `BAR_ROW`, `layout.py:38` |

**This is where the first draft of this note was wrong, and it is worth saying
so.** It was written against a layout that parked the footer down in the button
lane at `0.912h` and left the strip between `0.83h` and `0.8756h` empty — a free
`0.0456h` the grid could never reach and nothing else used, which is where the
band was going to sit for nothing. The footer has since moved up into exactly
that strip, for its own reasons (`layout.py:39-45`), and the free space is gone.
There is no longer a place under the grid that costs nothing.

So the band does not get a strip of its own. It gets *the quote's* — the same
reserve, the same centre line, and never both at once:

- the reserve is `QUOTE_BAND` plus `QUOTE_CLEARANCE`, taken off the grid's floor
  when anything at all wants the slot (`layout.py:93-102`, and `Style.shows_band`
  in `render.py`);
- the centre is `quote_center_y`, half way between the grid's last row and
  `quote_floor`, so it follows the grid when the clock preset or the manual
  nudge moves it instead of being a fourth magic fraction to re-tune beside
  them.

Measured on `i16` with a one-year span the band centre lands at `0.795h`; on a
three-month span it sits lower, because the grid ends higher. Which is the whole
point of deriving it rather than fixing it: it is not a fraction of the screen,
it is the middle of what is left.

**Cost to the grid: the quote's cost, and only when nothing was already paying
it.** With `q=1` the reserve is taken anyway and `sky` is free. With `q=0` it
costs what a quote costs — on `i16` at one year, `pitch_y` drops from 48 to 40
and the dot from 32px to 26px.

Sizing the reserve to the occupant instead — a shallow band for one line and a
moon, a deep one for three lines of prose — was the other option, and it is
worse for the reason `footer_slot` gives in its own docstring
(`layout.py:74-85`): a picture that lifts half an inch because a caption was
swapped for a moon is not the same picture. One slot, one size, whichever thing
is standing in it.

### Why the band and not the footer lane

The footer lane is the other candidate, and `_draw_footer` is already written
for it — it takes a tuple of lines and centres the block, and its docstring says
so. It is the wrong home for two reasons, both measurable.

It is narrow. `footer_max_width` is `width − 2·CONTROLS_CLEAR·w` = 707px on
`i16`, still the width of the lane between the two round buttons even now that
the line itself has moved above them. The band, one step higher up the screen,
can use the grid's own width — 899px on the same phone — which is what
`_draw_quote` already wraps to, and which is why the quote squares up with the
dots.

It is crowded. The lane already holds the progress line, and the shrink-to-fit
loop in `_draw_footer` only ever measures width. Stack a second line there and
the block grows downward toward the progress rule at `0.943h` with nothing
checking it, and the render tests compare pixels at the cell, not at the bar.
Mocked up, two lines and a rule read as a status report. The band reads as a
caption.

## The moon

### It has to be drawn

Inter is bundled precisely so that identical bytes in mean identical pixels out
(`src/wallcal/fonts.py`, and the note in the README). It has no moon.
`U+263E ☾` and `U+1F319 🌙` both render byte-identical to the `.notdef` box —
checked against a character certainly absent from the font — as does `U+25D0 ◐`.
`↑`, `↓`, `●`, `○` and `·` are real. So a moon set as text is a tofu box, and a
moon set as an emoji would need a colour font in the image, which would end
"the typeface cannot come from the system". It is a glyph we draw.

### The geometry

The terminator is the great circle dividing lit from unlit hemisphere. Seen from
Earth it projects to a **half-ellipse** sharing the disc's two poles, with signed
semi-axis `x = R·(2k − 1)`, where `k` is the illuminated fraction. At `k > 0.5`
the ellipse bulges past the half-disc and adds to it — gibbous; at `k < 0.5` it
cuts into it — crescent; at `k = 0.5` it degenerates to a straight line.

The folk construction — one disc minus a second disc of the same radius — cannot
do this. A same-radius offset disc only ever cuts a crescent; it has no gibbous
at all, and drawing one means an offset disc of a *different* radius, which puts
a circular arc through the cusps instead of an elliptical one. That is not a
rounding difference at wallpaper scale. Max deviation between the true ellipse
and the best circular arc through the same cusps:

| diameter | `k = 0.10` | `k = 0.25` | `k = 0.35` |
| -------- | ---------- | ---------- | ---------- |
| 42 px | 1.9 px | 2.1 px | 1.5 px |
| 64 px | 2.9 px | 3.2 px | 2.2 px |

At the quarters — the phases you actually look at — a circular terminator is
three pixels fat on a sixty-pixel moon, five percent of the diameter, and it
reads as a lazy crescent. The ellipse costs nothing extra: Pillow draws one with
the same call.

Draw it the way every dot in this renderer is drawn (`render.py:162-171`): two
masks at `SUPERSAMPLE` × the final size, reduced with Lanczos, then used as
paste masks over flat colour. Two rectangles, two ellipses, one multiply, one
lighter-or-subtract:

- `disc` — a full circle.
- `lit` — the half-disc on the sunward side, then the terminator ellipse either
  unioned in (gibbous) or subtracted (crescent).

One trap: when `|x|` falls under a pixel Pillow refuses the ellipse outright
(`x1 must be greater than or equal to x0`). Skip it and draw the straight half.

### Why it reads as a dot and not as a sticker

The disc is painted in `ramp.future` — the tone of a day not yet lived — and the
lit part in `ramp.strong` — the tone of a day just gone (`palette.py:88-104`,
`render.py:194-198`). Nothing else. No outline, no craters, no yellow, and
above all not the accent, which means *today* and must go on meaning only that.

The consequence is the whole design: a new moon is an unlived dot, a full moon
is a lived dot, and the month in between is that dot filling up. The moon runs
the same ramp the calendar runs. It does not need to be told to belong to the
field; it is made of the field.

It also disposes of the thin-crescent problem without a hack. At a 42 px disc a
two-day-old moon is a 0.8 px sliver and a five-day-old one is 2.0 px — invisible,
or nearly. But the unlit disc is still there, in the tone the wallpaper already
uses for "nothing yet", so a young moon reads as a pale dot with a bright edge
rather than as a rendering failure. No clamping, no minimum crescent width.

### Size and orientation

`MOON_RATIO = 1.05` of the band's type size, itself `SKY_SIZE = 0.0155h`:
42 px on `i16`, 43 on `i16p`, 46 on `i16pm`. That is a hair over the type's own
size and, on a two-weeks-to-a-row span, within two pixels of a grid dot — which
is why it sits in the band as a member of the field rather than as an icon. Tie
it to the type rather than to `lay.dot`: on a one-year span the dot falls to
30 px and a 30 px moon beside 40 px numerals looks like a bullet point.

It is a circle even when `s=r`. Rendered as a rounded square to match the field,
the crescent's cusps get clipped flat and the gibbous bulges into a corner; it
stops reading as a moon and starts reading as a battery indicator. The dot shape
is a texture choice. The moon is a depiction, and it only has one shape.

Cusps point left for waxing, right for waning, as seen from the northern
hemisphere; mirror when `lat` is negative. Do not model the terminator's tilt:
the parallactic angle needs a time of day, which a per-day image does not have,
and at 42 px the tilt is not readable anyway.

Quantise `k` to 1/64 before building the mask so the masks stay cacheable, the
way `FADE_STEPS` quantises the fade for the same reason (`render.py:30`). At
42 px, 1/64 of the diameter is 0.66 px — under the anti-aliasing.

## The sun

NOAA's solar position algorithm, about forty lines of `math` against the stdlib,
no dependency. Julian century, geometric mean longitude and anomaly, equation of
centre, apparent longitude, obliquity, declination and the equation of time;
then the hour angle from `cos H = (cos 90.833° − sin φ · sin δ) / (cos φ · cos δ)`
and sunrise and sunset as solar noon ∓ `4H` minutes. The `90.833°` is the
standard zenith: 34′ of refraction plus the sun's 16′ semidiameter.

Written out and checked against published times it reproduces them to the
second-of-display: London on 21 June 2026 at `04:43 / 21:21` BST, Moscow at
`03:44 / 21:18` MSK, Quito flat at `06:0x / 18:1x` all year. NOAA quotes ±1
minute for latitudes below 72°, degrading beyond. That is far better than the
rendering needs, since the wallpaper prints whole minutes.

The alternative is `astral`, which would be the project's fourth runtime
dependency after `fastapi`, `pillow` and `uvicorn` — a supply-chain edge for
forty lines of arithmetic that will never change. Not worth it.

### The line itself

`06:12 – 19:48 · 13:36 +2:14`, in `FONT_REGULAR` at `SKY_SIZE`, measured at
657 px against the 899 px the grid gives it. An en dash for the pair, because
that is what a range is set with and it needs no explaining in either language;
a middot to break off the duration, matching the footer's own `6 / 122 · 4.9%`.
No `↑`/`↓` arrows — Inter has them, but at 40 px they are two more ink shapes
beside a glyph that is already carrying the band, and a range needs no arrows to
read as one.

`13:36` is a duration sitting two tokens away from two clock times, which is
genuinely ambiguous read cold. The delta disambiguates it: nothing that follows
a wall clock reads as `+2:14`. Which is an argument for keeping `dl=1` the
default — with `dl=0` the line is just `06:12 – 19:48`, and the duration should
go with the delta rather than stand alone looking like a third time of day.

### It has to stay a pure function of the date and the URL

Two constraints, both real.

The image is cached until midnight in the requested zone and answers 304 on an
unchanged `ETag` (`app.py:314-328`). Sunrise, sunset and day length are fixed
for a calendar date, so the cache window is unchanged: the band changes exactly
when "today" changes, which is exactly when the drawing already changes. The
moon does drift continuously through the day, so evaluate it at a fixed instant —
noon UT of the rendered date — and it becomes a step function that also changes
at midnight and nowhere else.

The `ETag` needs one change. `lat` and `lon` ride in for free the moment they
are `Style` fields, because the fingerprint hashes `{style}` and `Style` is a
frozen dataclass (`app.py:315`, `render.py:108`). `tz` does not: it is absent
from the fingerprint, and today that is harmless because nothing depends on the
zone except which day is "today", which is hashed. Print local clock times and
that stops being true — two phones in different zones on the same calendar date
would render different images under one `ETag`, and `Cache-Control` is `public`
(`app.py:322`), so a shared cache is entitled to hand one of them the other's
picture. `tz` joins the fingerprint where it is built in `app.py`. One token, and the
existing `ETag` tests keep passing.

## Parameters

| key | meaning | default | values |
| --- | ------- | ------- | ------ |
| `sky` | what goes in the band under the grid | `none` | `none`, `moon`, `sun`, `both` |
| `lat` | latitude, for `sun` | — | `-90`…`90`, two decimals kept |
| `lon` | longitude, for `sun` | — | `-180`…`180`, same |
| `dl` | day length and the delta from yesterday | `1` | `1`, `0` |

`sky=moon` needs no location at all — the illuminated fraction is the same for
the whole planet, and only the mirroring depends on which hemisphere you are in.
`sky=sun` and `sky=both` need both coordinates; one without the other is a `400`,
with the same wording `w` and `h` already get (`devices.py:52-53`).

One band, one occupant, and the precedence runs from most specific to least:
`qt` (a line you wrote yourself) beats `sky`, which beats `q` (the rotation).
The rule is the one already in the code — writing something explicitly is asking
for it (`Style.shows_sky` and `Style.shows_quote`, `render.py`).

### Where the location comes from

From the URL, because in this service everything comes from the URL. There is no
account to attach a home to and no database to keep it in, and adding either to
hold two floating-point numbers would cost more than the feature is worth. The
builder page can fill them in from the browser's own geolocation prompt, so the
coordinates are chosen on the device and only reach the server inside a link the
user decided to use.

**This is the point at which the service learns something about you that it does
not know today.** Say it plainly. The access log writes the query string next to
the caller's IP (`logs.py:89-100`, `logs.py:40-48`), so `?lat=..&lon=..` turns
one line of `docker logs` into a person and a place. A wallpaper service whose
whole pitch is "no app, no account, no database" should not quietly start
holding the one piece of personal data it never had.

Two mitigations, both cheap:

- **Keep two decimal places, not more.** Round in the parser, so the render and
  the `ETag` see the coarse value. Two decimals is ≈1.1 km — a neighbourhood,
  not a doorstep — and it costs under 3 seconds of sunrise below 60°. The
  tempting move is to cut harder, and the numbers say not to. Worst case from
  rounding to one decimal (≈11 km), sampled every five days through 2026:

  | latitude | error |
  | -------- | ----- |
  | 0°–30° | 19 s |
  | 30°–50° | 27 s |
  | 50°–60° | 46 s |
  | 60°–64° | 84 s |
  | 64°–66.5° | 548 s |

  Sunrise gets hypersensitive to latitude as the sun starts grazing the horizon,
  and near the Arctic Circle no rounding policy rescues it — even two decimals
  cost 89 s there. That is an accuracy fact rather than a privacy one, and it is
  a second reason the ±1-minute claim stops at the Circle. Below 60°, where
  almost everyone lives, two decimals are free.
- **Round it in the log too.** `_record` already truncates the query at 300
  characters (`logs.py:99-100`); rewriting `lat`/`lon` to one decimal on the way
  past is a couple of lines in the same place. The rendered image keeps its two,
  the log keeps a town.

## Accuracy and the edges

**Polar day and night.** Above the Arctic Circle `cos H` leaves `[−1, 1]` and
there is no rise and no set. This is not rare and not brief: Tromsø in 2026 has
polar night from 28 November to 14 January and midnight sun from 18 May to
25 July — 117 days of the year with nothing to print. The line must say so in
words, which means two rows per language in `strings.py`, the one file that
exists so that adding a language means adding rows and nothing else (`POLAR`). Everything else on the line is digits and punctuation and
survives `lang` untouched.

**The delta at the transition.** The day-length delta is drawn only when both
today and yesterday had a rise and a set. Across the boundary into polar day the
previous day's length is meaningless as a comparison, and the honest thing is to
drop the number rather than print a jump.

**A day that runs past local midnight.** For a fortnight either side of every
polar spell the sun sets after midnight on the local clock, and the pair comes
out `01:31 – 00:02` — which reads as a twenty-three *minute* day. The length is
the only token that says otherwise, so it is printed whenever the two times fall
on different local dates, `dl=0` or not. There it is not a statistic beside two
clock times, it is what makes them readable; the argument for keeping the
duration and the delta together does not reach it.

**The delta at the solstices.** The brief's `+2:14` is a spring figure. Around
the June solstice in London the delta runs `+0:26, +0:20, +0:14, +0:08, +0:02,
−0:03, −0:10 …` — under a minute for four days either side, and two seconds on
the day itself. Near the equinox it is `+3:58` and barely moves. Print it as
`m:ss` and take the tiny numbers as a feature: the solstice is precisely the day
the wallpaper says `+0:02`, and that is the most interesting thing it says all
year. Do not switch units, do not round to minutes and print `+0:00`, and do not
suppress it below a threshold — the near-zero *is* the information.

**Above 72°.** NOAA's ±1 minute does not hold. Near a polar transition the
answer can be a day out. The band is still worth drawing there — the polar words
are right even when the boundary date is not — but the doc should not claim
minute accuracy above the Arctic Circle, and neither should the README.

**No elevation, no pressure.** Standard refraction at sea level. A user at
2000 m gets a sunrise a few minutes late. Modelling it needs a third coordinate
and buys nothing on a lock screen.

**A location never set.** `sky` defaults to `none` and nothing is drawn. If
`sky=sun` arrives without coordinates it is a `400`, not a guess. There is no
default city and no IP lookup: a wrong sunrise is worse than no sunrise, because
a wrong one is believed. The moon needs no location, so `sky=moon` is the
feature's honest entry point — it works from the first URL, for everyone, and
gives away nothing.

## What not to build

**A phase name or a percentage.** "Waxing gibbous · 71%" needs eight rows per
language in `strings.py` and says nothing the glyph does not say better and
faster. The glyph is the whole point; text beside it is an admission that the
glyph failed.

**Twilight, golden hour, solar noon, azimuth.** Each is another number in a band
that holds one line. The dot field is what the wallpaper is for; four more
figures under it turn a calendar into a dashboard.

**Moonrise and moonset.** An order of magnitude more code than the sun — a
lunar ephemeris with topocentric parallax, an iterative solve because the moon's
declination moves fast enough that a single hour-angle pass is wrong by minutes,
and the awkward business of the moon rising twice on some days and not at all on
others. It is also the fact people ask for least. If it is ever wanted, it wants
its own document.

**A moon in the grid.** A full-moon marker on a day cell, or a moon in place of
a dot, was the first idea and it is the wrong one. The field is the subject; a
second meaning inside it makes every dot a question. The month-end tint
(`mk`, `render.py:275-281`) is already the most the field will carry.

**A default location, an IP lookup, a city-name search.** Any of the three means
a network call or a bundled database inside a service that is a pure function of
its URL and has three dependencies. The mean-lunation shortcut goes in the same
bin, for a smaller reason: computing the phase from a fixed synodic month drifts
up to `Δk = 0.094` from the truncated Meeus series over 2026–27, which is 4 px
of terminator on a 42 px moon and, at the quarters, a visibly different phase
from the one in the sky. Seven sine terms fix it, and they are ten lines.

**Timezone inferred from longitude.** Right for a third of the world, wrong for
China, Spain, India and most of the places anyone lives. `tz` already exists and
already means this.
