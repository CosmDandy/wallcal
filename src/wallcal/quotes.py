"""A line for the day, chosen by the date.

Deterministic on purpose: the same day gives the same line on every device and
on every retry, so a phone that refetches the wallpaper twice does not flicker
between two quotes.
"""

from __future__ import annotations

import os
from datetime import date
from functools import lru_cache
from pathlib import Path

Quote = tuple[str, str]  # (line, who said it)

QUOTES: tuple[Quote, ...] = (
    ("It is not that we have a short time to live, but that we waste much of it.", "Seneca"),
    ("How we spend our days is, of course, how we spend our lives.", "Annie Dillard"),
    ("You could leave life right now. Let that determine what you do and say.", "Marcus Aurelius"),
    ("The days are long but the decades are short.", "Sam Altman"),
    ("Someday is not a day of the week.", "Janet Dailey"),
    ("Lost time is never found again.", "Benjamin Franklin"),
    ("You do not rise to the level of your goals. You fall to your systems.", "James Clear"),
    ("The two most powerful warriors are patience and time.", "Leo Tolstoy"),
    (
        "Time is the coin of your life. Only you can determine how it will be spent.",
        "Carl Sandburg",
    ),
    ("Begin at once to live, and count each separate day as a separate life.", "Seneca"),
    ("A year from now you may wish you had started today.", "Karen Lamb"),
    ("The best time to plant a tree was twenty years ago. The second best is now.", "Proverb"),
    ("What we do now echoes in eternity.", "Marcus Aurelius"),
    ("Ordinary people think merely of spending time. Great people think of using it.", "Unknown"),
    ("Nothing is worth more than this day.", "Goethe"),
    ("You have exactly one life in which to do everything you will ever do.", "Arnold Bennett"),
    ("Time flies over us, but leaves its shadow behind.", "Nathaniel Hawthorne"),
    (
        "It is not enough to be busy. The question is: what are we busy about?",
        "Henry David Thoreau",
    ),
    ("Either you run the day, or the day runs you.", "Jim Rohn"),
    ("The trouble is, you think you have time.", "Jack Kornfield"),
    ("Small deeds done are better than great deeds planned.", "Peter Marshall"),
    ("He who every morning plans the transactions of the day succeeds.", "Victor Hugo"),
    ("Time is what we want most and what we use worst.", "William Penn"),
    ("Your future is created by what you do today, not tomorrow.", "Robert Kiyosaki"),
    ("Doing nothing is very hard to do. You never know when you are finished.", "Leslie Nielsen"),
    ("Until we can manage time, we can manage nothing else.", "Peter Drucker"),
    ("The way we spend our time defines who we are.", "Jonathan Estrin"),
    ("Patience is bitter, but its fruit is sweet.", "Aristotle"),
    ("This is the only moment you can act in.", "Unknown"),
    ("Yesterday is gone. Tomorrow has not yet come. We have only today.", "Mother Teresa"),
)


ENV_PATH = "WALLCAL_QUOTES"
SEPARATOR = "|"


class QuoteError(ValueError):
    """Raised when a quote file is unreadable or holds nothing usable."""


def parse(text: str) -> tuple[Quote, ...]:
    """One quote per line, author after a `|`.

    A dash is deliberately NOT a separator. Russian punctuation puts dashes
    inside sentences all the time — "Самое длинное расстояние — от слов до дела"
    has no author at all — so splitting on one turned half a sentence into an
    attribution. The pipe never appears in prose, so it can mean exactly one
    thing. The split takes the last pipe, leaving any earlier one in the quote.

    Blank lines and lines starting with # are skipped, so the file can carry
    sources and section headings as comments.
    """
    found: list[Quote] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        head, sep, tail = line.rpartition(SEPARATOR)
        found.append((head.strip(), tail.strip()) if sep else (line, ""))
    if not found:
        raise QuoteError("quote file holds no quotes")
    return tuple(found)


@lru_cache(maxsize=1)
def rotation() -> tuple[Quote, ...]:
    """The active list: your own file if WALLCAL_QUOTES points at one, else the built-in.

    Read once and cached — the file is configuration, not content that changes
    under a running server.
    """
    configured = os.environ.get(ENV_PATH)
    if not configured:
        return QUOTES
    path = Path(configured)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise QuoteError(f"cannot read {ENV_PATH}={configured}: {exc}") from exc
    return parse(text)


def for_day(day: date) -> Quote:
    """The line for `day`. Walks the list one step per day, then wraps."""
    active = rotation()
    return active[day.toordinal() % len(active)]
