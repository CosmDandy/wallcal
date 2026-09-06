"""Wording, and the Russian numerals that trip everyone up."""

from __future__ import annotations

import pytest

from wallcal import strings


def test_every_language_has_a_full_set():
    for language in strings.LANGUAGES:
        assert len(strings.WEEKDAYS[language]) == 7
        assert len(strings.MONTHS[language]) == 12


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (0, "Готово"),
        (1, "осталось 1 день"),
        (2, "осталось 2 дня"),
        (4, "осталось 4 дня"),
        (5, "осталось 5 дней"),
        (11, "осталось 11 дней"),  # teens take дней whatever the last digit says
        (12, "осталось 12 дней"),
        (14, "осталось 14 дней"),
        (21, "осталось 21 день"),
        (22, "осталось 22 дня"),
        (25, "осталось 25 дней"),
        (101, "осталось 101 день"),
        (111, "осталось 111 дней"),
        (114, "осталось 114 дней"),
    ],
)
def test_russian_day_counts_take_the_right_form(count: int, expected: str):
    assert strings.days_left("ru", count) == expected


@pytest.mark.parametrize(
    ("count", "expected"),
    [(0, "Done"), (1, "1 day left"), (2, "2 days left"), (116, "116 days left")],
)
def test_english_day_counts(count: int, expected: str):
    assert strings.days_left("en", count) == expected


def test_week_of():
    assert strings.week_of("en", 3, 13) == "Week 3 of 13"
    assert strings.week_of("ru", 3, 13) == "Неделя 3 из 13"


def test_an_unknown_language_is_refused():
    with pytest.raises(strings.LanguageError):
        strings.parse_language("de")
