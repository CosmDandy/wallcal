# Progress at several levels

Today one rule sits under the footer line and fills with the share of the span
already spent (`_draw_bar`, `src/wallcal/render.py:421-439`). The proposal on
the table is to replace it with three thin rules stacked in the same lane —
year, quarter, month — so the wallpaper says how far through each of them you
are, all at once.

## The recommendation

Do not stack. Build one knob instead: let `br` name the *period* the single rule
measures, so it can say something the dot field does not already say. The
wallpaper is a two-level display already and nobody noticed — the dots are one
level and the rule is the other, and today both are pointed at the same span, so
the second level restates the first. Adding a third and a fourth rule is the
wrong repair for that; setting the second level to a different period is the
right one. `mode=month&br=year` is the shape the idea was reaching for: the dots
give the month at day resolution, the rule gives the year as one line, and the
two never claim the same number. It costs no new geometry, no new tone, no
legend, and one field on `Style`.

## What the screen already says

`grid.progress` is `days_elapsed / days_total` (`src/wallcal/grid.py:61-72`) and
that is exactly what the filled run of dots draws — `CellState.PAST` and
`TODAY` against `FUTURE`, cell by cell (`src/wallcal/render.py:201-213`). The
rule fills to the same fraction (`src/wallcal/render.py:435`). With the default
`ft=pct` the footer prints it a third time as `6 / 122 · 4.9%`
(`src/wallcal/render.py:418`). One number, three drawings. That is the actual
defect the proposal is circling, and it is worth naming before any geometry:
the rule as built carries no information at all.

Which calendar levels would add something depends on what the span already is.
The four implemented modes build their spans in `src/wallcal/modes.py:66-85`:

| mode      | span is            | year rule  | quarter rule | month rule |
| --------- | ------------------ | ---------- | ------------ | ---------- |
| `month`   | 1st → month end    | new        | new          | = the dots |
| `quarter` | quarter, 3 months  | new        | = the dots   | derivable  |
| `year`    | Jan 1 → Dec 31     | = the dots | derivable    | derivable  |
| `span`    | whatever you asked | new        | new          | new        |

"Derivable" means the boundaries are on the screen but not as a fraction: the
last day of each month is tinted (`src/wallcal/grid.py:46`, drawn at
`src/wallcal/render.py:275-281`) and the month name is set sideways beside its
rows (`src/wallcal/render.py:306-310`), so a reader can find where the month
ends but has to count to turn that into a share.

Read the table the other way and the proposal falls apart. In every mode that
has a calendar name — the modes where "how far through the year" is a question
someone would ask — one of the three rules is a duplicate of the dot field, so
three is never the right number. The single case where all three are new is
`mode=span`, an arbitrary range like a thesis deadline, and that is precisely
the case where the calendar levels are least relevant: someone counting down to
June has not asked about Q3.

## The lane, in numbers

Fractions of height, from `src/wallcal/layout.py:38-41`: the buttons are
centred at `CONTROLS_ROW = 0.912`, the rule rides at `BAR_ROW = 0.943`, each
button occupies `CONTROLS_CLEAR = 0.20` of the width from its edge, and its
radius is `CONTROLS_RADIUS = 0.062` of the width. The mock-up puts the home
indicator at `0.972` (`src/wallcal/preview.py:32`) — not a reserve the layout
knows about, but the floor in practice.

On the 1290×2796 screen the task names (reachable through `w`/`h`; the presets
in `src/wallcal/devices.py:25-32` are 1179×2556, 1206×2622 and 1320×2868):

| thing                            | source                                             | px         | fraction           |
| -------------------------------- | -------------------------------------------------- | ---------- | ------------------ |
| footer type                      | `layout.py:61,297` — `0.017h`                       | 48         | 0.0170 h           |
| footer text band                 | anchor `mm` at `0.912h`                             | 2521–2579  | 0.0208 h           |
| rule                             | `render.py:424-425` — `0.62 × lane`, `0.26 × font`  | 480 × 12   | 0.372 w × 0.0043 h |
| rule band                        | centred on `0.943h`                                 | 2631–2643  |                    |
| home indicator                   | `preview.py:32` — `0.972h`                          | 2718       |                    |
| **clear lane, text → indicator** |                                                     | **139**    | **0.0497 h**       |

So the answer to "is the lane tall enough for three" is yes, comfortably. Three
rules at the current 12px height with 12px between them come to 60px — 0.0215
of the height, 43% of the clear lane. Centred on `0.943h` they run 2607–2667,
leaving 28px to the footer text above and 51px to the home indicator below. Drop
them to the 4px floor `render.py:425` already enforces and they need 44px. The
proportions hold on every preset: the clear lane is 0.0497–0.0499 h on all four
screens, and the three-rule band 0.0215–0.0227 h.

Horizontally there is no contest either. The lane the footer may use is
`width - 2 × 0.20w` = 774px, x 258–1032 (`src/wallcal/layout.py:295`), which is
in fact 22px wider on each side than the drawn button (outer edge at
`0.155w + 0.062w = 0.217w` = 280px, `src/wallcal/preview.py:29-30`) — the text
lane nominally runs slightly under the buttons, and it is the `0.62` factor at
`src/wallcal/render.py:424` that buys the real clearance: the rule spans x
405–885, 125px clear of each button.

Geometry, then, is not the objection. Three rules fit. That has to be said
plainly, because it is where an argument against stacking would like to stop,
and it is not available.

One note on the reasoning that is *not* in the repo: `grep` finds no mention
anywhere of the Focus pill or the notification stack. What
`src/wallcal/layout.py:35-37` actually records is that the lane is where the
progress line goes so it "reads as part of the system UI rather than as
something stranded above it", and `layout.py:39` that the rule "rides below the
words, above the home indicator". If iOS parks a notification stack over this
lane, that is a fact about a phone, not a fact about this code, and it should be
checked against a real screen before any design leans on it. Nothing below does.

## What the geometry does not solve

Three rules of equal weight read as a chart, and the fix for that is hierarchy —
different lengths, different tones, or nesting. None of the three survives
contact with the numbers.

**Tone.** The ramp has three greys under the strong end
(`src/wallcal/palette.py:97-103`) and `mix` can step the accent towards the
background (`src/wallcal/palette.py:191`). Neither has room to spend. On the
light theme the rule's fill against its own track is 3.01:1 — the accent at
L=0.178 on `future` at L=0.636 — which is exactly the threshold a graphical
object needs to be distinguishable at all, with nothing left over. On the dark
theme the same pair is **2.17:1**, already under it: the rule is the weakest
distinction on the wallpaper before anything is asked of it. And the steps that
would separate three rules are smaller still — accent at 1.0 / 0.62 / 0.40
against the light background gives 1.76:1 between the first two and 1.40:1
between the next, and 1.74:1 / 1.35:1 on dark. Those are not distinctions at
12px on a phone held at arm's length; they are the same rule drawn three times
in slightly tired ink.

**Length.** Making the year rule longest and the month shortest encodes the
period in length, and the fill already encodes the progress in length. The eye
would have to hold two length readings on one object and keep them apart. That
is the chart failure exactly: correct, decodable, and not readable at a glance.

**Position.** "The top one is the year" is a convention, which is a legend the
reader has to have been told. A wallpaper does not get to teach conventions; it
gets one glance while the phone comes out of a pocket.

**Nesting.** Drawing the month as a brighter segment inside the year rule is one
object, not three, and it does answer the hierarchy question — but the arithmetic
kills it. A month is 1/12 of the year rule: 40px of 480 on this screen. Its own
fill would run 0–40px, below any useful read, and the guard at
`src/wallcal/render.py:436` would suppress most of it anyway.

## The rule, as built

Nothing in `src/wallcal/layout.py` changes. One rule, at `BAR_ROW = 0.943` of
the height, `0.62` of the lane wide (0.372 w) and `0.26` of the footer type tall
(≈0.0043 h), centred on the width, 125px clear of each button and 75px above the
home indicator on a 1290×2796 screen. All of that is what it is today; the
recommendation buys its value from the period, not from the pixels, which is the
main reason to prefer it.

What changes is where the fraction comes from. `grid.progress`
(`src/wallcal/grid.py:71`) becomes one of five choices, and the other four are
the calendar period containing `grid.today` — elapsed days over that period's
length, computed from `today` alone. Both helpers already exist: `month_end` at
`src/wallcal/grid.py:113` and the quarter-start expression at
`src/wallcal/modes.py:78`. The renderer needs nothing else — it never learns the
mode, and does not need to, because a calendar period is defined by today's date
and not by how the span was built.

Anchoring the calendar periods to `today` rather than to the span has one
property worth keeping on purpose: on a wallpaper whose span has ended,
`grid.progress` is pinned at 100% by the clamp at `src/wallcal/grid.py:66-68`
and the rule stops moving, while `br=year` keeps saying something true every
morning. A link written in fixed dates goes stale; the rule on it need not.

The one visible consequence is the guard at `src/wallcal/render.py:436` — the
fill is not drawn until it is at least as long as the rule is tall, because a
rounded capsule shorter than its own diameter draws as a blob. With the span as
the period that empty state lasts hours. With `br=year` it lasts the first eight
or nine days of January (12/480 of a 365-day year is day 9 on this screen, day
10 on the Pro Max), and with `br=quarter` the first two days of a quarter. Leave
it. "The year has barely started" is what an empty track honestly means, and
special-casing it would trade a truthful drawing for a busier one.

## The parameter

`br` grows from a flag into a period, the way `ft` already is one — and
`parse_footer` at `src/wallcal/render.py:71-85` is the precedent to copy, right
down to accepting `1` and `0` as aliases so a link written against the old
spelling keeps meaning what it meant.

| key  | meaning                        | default | values                                      |
| ---- | ------------------------------ | ------- | ------------------------------------------- |
| `br` | progress rule under the footer | `1`     | `1`, `0`, `span`, `year`, `quarter`, `month` |

| value     | the rule fills with                                                          |
| --------- | ---------------------------------------------------------------------------- |
| `1`       | the span — the long name is `span`, and this is what `br=1` has always drawn  |
| `span`    | same thing, said in words                                                    |
| `year`    | the calendar year containing today                                           |
| `quarter` | the calendar quarter containing today                                        |
| `month`   | the calendar month containing today                                          |
| `0`       | no rule — the long name is `none`                                            |

`br=1` and `br=span` produce the same `Style`, and therefore the same ETag: the
fingerprint at `src/wallcal/app.py:314-317` hashes the style, so two spellings
of one drawing still share a cache entry and nothing about the caching needs
touching.

Two compatibility points that are easy to get wrong. First,
`src/wallcal/app.py:207` declares `br` as `bool`, so FastAPI accepts everything
pydantic calls a boolean — `true`, `false`, `yes`, `no`, `on`, `off`, `t`, `f` —
not only the `1`/`0` the README documents. Changing the annotation to `str`
moves that parsing into `wallcal`, and the parser must keep the whole set or a
URL that answers 200 today starts answering 400. Second, the new `BarError`
belongs in the `except` tuple at `src/wallcal/app.py:278-290`, or a bad value
falls through to the week-numbering handler and reports the wrong parameter.

In the builder, `br` is a segmented control declared at
`src/wallcal/assets/index.html:703` as two items, labelled "Progress rule" at
line 638. It becomes five: Span / Year / Quarter / Month / Off. Five is one more
than `ft` already carries in the same panel, so the row is known to fit.

## Rejected

**Three stacked rules.** They fit — 60px in a 139px lane — and they still should
not be built. Three fractions is more than a glance delivers, no scheme
distinguishes them without a legend (the contrast headroom is 1.4:1 where 3:1 is
needed), and the information case never comes out to three: in every named mode
one of the three is a redrawing of the dot field, and in `mode=span`, where all
three are genuinely new, none of them is what the user asked about.

**The rule segmented into months.** One rule, twelve cells of 40px each,
boundaries drawn as hairlines. This is the most tempting alternative, because it
costs no extra height and it does read: "I am in the ninth cell" is a glance, not
a decode. It is rejected because of what it buys. The fill position already says
how far through the year you are; the segments only convert that into a month
*name* — and the lock screen prints the date two inches higher, which is where
anyone looking for the month will look. Meanwhile the wallpaper already draws
month boundaries twice, as the tinted last day (`src/wallcal/render.py:275-281`)
and as the sideways label (`src/wallcal/render.py:306-310`), so segmenting the
rule is a third statement of a fact that was never in short supply. Structure
added, information not.

**Markers on the one rule.** A tick at the quarter boundary, or at where the
span's own end falls within the year. Same family, same verdict, and worse: a
tick has no meaning at all without being told what it marks, where a segment at
least reads as a period.

**A single rule that picks its period from the mode.** Closest to the
recommendation and rejected on two counts. Mechanically, the renderer does not
know the mode — `render_span` takes a grid, a size and a style
(`src/wallcal/render.py:174`), `Style` has no mode field
(`src/wallcal/render.py:108-137`), and `src/wallcal/app.py:308` uses the mode key
to build the grid and then drops it. That is fixable. What is not fixable is that
the policy has no answer in the most-used mode: for
`mode=span&f=today&t=2027-06-01` there is no period the service can pick that is
more right than another, so "automatic" would mean a coin flip dressed as a
decision. And it would silently change what an existing `br=1` link draws for
anyone on `year`, `quarter` or `month` — the README's first claim is that the URL
is the configuration, and a URL whose meaning shifts underneath it is not one.

## What this does not build

No second rule, under any name — not "the span plus one calendar level", which
is the compromise this document will be asked for next. Two rules bring back
every problem three had, at two thirds of the cost: which one is which is still
a legend, and the span rule is still the dots redrawn.

No rule for a period that does not contain today — "last month", "next quarter".
The rule is a picture of now.

No new tone, no new constant in `src/wallcal/layout.py`, and no change to
`BAR_ROW`, `CONTROLS_ROW` or the clearances. The lane holds one rule well. Its
problem was never that it held too few.

No coupling between `br` and `ft`. With `br=year&ft=pct` the footer states the
span's percentage in words while the rule pictures the year's, and those are two
different numbers with nothing on screen saying which is which. That is the real
cost of this design and it is worth being explicit about rather than engineering
around: a number and a picture do not read as one statement, the scales are
visibly different, and the person looking at the screen is the person who wrote
the URL. Anyone who dislikes the ambiguity has `ft=none`, and the README should
say so on the same line it introduces the periods.
