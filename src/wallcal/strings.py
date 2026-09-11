"""Wording, per language.

Kept apart from the drawing code: the grid stores month numbers, and a name is
only chosen when it is about to be painted. Adding a language means adding rows
here and nothing else.
"""

from __future__ import annotations

from datetime import date

LANGUAGES = ("en", "ru")

WEEKDAYS: dict[str, tuple[str, ...]] = {
    "en": ("MO", "TU", "WE", "TH", "FR", "SA", "SU"),
    "ru": ("ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"),
}

MONTHS: dict[str, tuple[str, ...]] = {
    "en": ("JAN", "FEB", "MAR", "APR", "MAY", "JUN",
           "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"),
    "ru": ("ЯНВ", "ФЕВ", "МАР", "АПР", "МАЙ", "ИЮН",
           "ИЮЛ", "АВГ", "СЕН", "ОКТ", "НОЯ", "ДЕК"),
}  # fmt: skip


# The mock-up's date line, which is the one place a whole word is written out.
# strftime would take these from the process locale, which is the container's,
# not the reader's.
FULL_WEEKDAYS: dict[str, tuple[str, ...]] = {
    "en": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
    "ru": ("Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"),
}

# Genitive: a Russian date reads "11 сентября", never "11 сентябрь".
FULL_MONTHS: dict[str, tuple[str, ...]] = {
    "en": ("January", "February", "March", "April", "May", "June",
           "July", "August", "September", "October", "November", "December"),
    "ru": ("января", "февраля", "марта", "апреля", "мая", "июня",
           "июля", "августа", "сентября", "октября", "ноября", "декабря"),
}  # fmt: skip


# Above the Arctic Circle there is no rise and no set to print, for months at a
# time. Everything else on the sun line is digits and punctuation, so this is
# the only wording the band needs.
POLAR: dict[str, tuple[str, ...]] = {
    "en": ("Midnight sun", "Polar night"),
    "ru": ("Полярный день", "Полярная ночь"),
}


class LanguageError(ValueError):
    """Raised for a language we have no wording for."""


def parse_language(spec: str) -> str:
    key = spec.strip().lower()
    if key not in LANGUAGES:
        raise LanguageError(f"unknown language {spec!r}; use one of: {', '.join(LANGUAGES)}")
    return key


def weekday(language: str, index: int) -> str:
    return WEEKDAYS[language][index]


def month(language: str, number: int) -> str:
    return MONTHS[language][number - 1]


def polar(language: str, sun_up: bool) -> str:
    return POLAR[language][0 if sun_up else 1]


def long_date(language: str, when: date) -> str:
    """The date as the lock screen writes it: weekday, day, month."""
    weekday_name = FULL_WEEKDAYS[language][when.weekday()]
    month_name = FULL_MONTHS[language][when.month - 1]
    return f"{weekday_name}, {when.day} {month_name}"


def days_left(language: str, count: int) -> str:
    if language == "ru":
        return "Готово" if count == 0 else f"осталось {count} {_ru_days(count)}"
    return "Done" if count == 0 else f"{count} day{'' if count == 1 else 's'} left"


def week_of(language: str, index: int, total: int) -> str:
    if language == "ru":
        return f"Неделя {index} из {total}"
    return f"Week {index} of {total}"


def _ru_days(count: int) -> str:
    """Russian counts in three forms: день / дня / дней."""
    tail, hundred = count % 10, count % 100
    if 11 <= hundred <= 14:
        return "дней"
    if tail == 1:
        return "день"
    if 2 <= tail <= 4:
        return "дня"
    return "дней"
