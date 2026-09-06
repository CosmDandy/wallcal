"""The rotation, and the file that can replace it."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from wallcal import quotes


@pytest.fixture(autouse=True)
def _clear_cache():
    quotes.rotation.cache_clear()
    yield
    quotes.rotation.cache_clear()


def test_the_same_day_always_gives_the_same_line():
    day = date(2026, 9, 6)
    assert quotes.for_day(day) == quotes.for_day(day)


def test_the_line_moves_one_step_a_day():
    day = date(2026, 9, 6)
    picks = [quotes.for_day(day + timedelta(days=n)) for n in range(len(quotes.QUOTES))]
    assert len(set(picks)) == len(quotes.QUOTES)  # a full cycle before it repeats


def test_every_built_in_quote_is_attributed():
    for line, author in quotes.QUOTES:
        assert line.strip() and author.strip()


def test_the_pipe_marks_the_author():
    assert quotes.parse("Время идёт | Сенека") == (("Время идёт", "Сенека"),)


def test_a_quote_file_keeps_cyrillic_and_skips_comments():
    parsed = quotes.parse(
        "\n".join(
            [
                "# мои цитаты",
                "",
                "Дело не в том, что у нас мало времени | Сенека",
                "Без автора тоже можно",
            ]
        )
    )
    assert parsed == (
        ("Дело не в том, что у нас мало времени", "Сенека"),
        ("Без автора тоже можно", ""),
    )


def test_a_dash_inside_the_quote_is_left_alone():
    """Russian sets dashes mid-sentence; they must not be read as attribution."""
    assert quotes.parse("Самое длинное расстояние — от слов до дела") == (
        ("Самое длинное расстояние — от слов до дела", ""),
    )
    assert quotes.parse("Два самых главных воина — терпение и время | Лев Толстой") == (
        ("Два самых главных воина — терпение и время", "Лев Толстой"),
    )


def test_the_last_pipe_wins():
    assert quotes.parse("a | b | Автор") == (("a | b", "Автор"),)


def test_an_empty_file_is_refused():
    with pytest.raises(quotes.QuoteError):
        quotes.parse("# nothing but a comment\n\n")


def test_a_configured_file_replaces_the_built_in_rotation(tmp_path, monkeypatch):
    path = tmp_path / "quotes.txt"
    path.write_text("Мой день | Я\nВторая строка | Тоже я\n", encoding="utf-8")
    monkeypatch.setenv(quotes.ENV_PATH, str(path))

    assert quotes.rotation() == (("Мой день", "Я"), ("Вторая строка", "Тоже я"))
    assert quotes.for_day(date(2026, 9, 6)) in quotes.rotation()


def test_a_missing_file_says_so_rather_than_falling_back(tmp_path, monkeypatch):
    monkeypatch.setenv(quotes.ENV_PATH, str(tmp_path / "absent.txt"))
    with pytest.raises(quotes.QuoteError):
        quotes.rotation()


def test_no_configuration_means_the_built_in_list(monkeypatch):
    monkeypatch.delenv(quotes.ENV_PATH, raising=False)
    assert quotes.rotation() == quotes.QUOTES
