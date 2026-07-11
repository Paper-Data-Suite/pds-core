"""Tests for shared terminal-menu navigation primitives."""

from io import StringIO

import pytest

from pds_core.menu_navigation import (
    NavigationChoice,
    QuitPDS,
    ReturnToMainMenu,
    navigation_hint,
    navigation_labels,
    parse_navigation_choice,
    print_navigation_options,
)


@pytest.mark.parametrize("value", ["b", "B", "  B  "])
def test_parse_back(value: str) -> None:
    assert parse_navigation_choice(value) is NavigationChoice.BACK


@pytest.mark.parametrize("value", ["m", "M", "  M  "])
def test_parse_main_menu(value: str) -> None:
    with pytest.raises(ReturnToMainMenu):
        parse_navigation_choice(value)


@pytest.mark.parametrize("value", ["q", "Q", "  Q  "])
def test_parse_quit(value: str) -> None:
    with pytest.raises(QuitPDS):
        parse_navigation_choice(value)


def test_parse_all_is_opt_in() -> None:
    assert parse_navigation_choice("a") is None
    assert parse_navigation_choice(" A ", allow_all=True) is NavigationChoice.ALL


@pytest.mark.parametrize(
    ("value", "kwargs"),
    [
        ("b", {"allow_back": False}),
        ("m", {"allow_main_menu": False}),
        ("q", {"allow_quit": False}),
    ],
)
def test_disabled_commands_return_none(value: str, kwargs: dict[str, bool]) -> None:
    assert parse_navigation_choice(value, **kwargs) is None


@pytest.mark.parametrize("value", ["", "unknown", "1"])
def test_unknown_input_returns_none(value: str) -> None:
    assert parse_navigation_choice(value) is None


def test_navigation_labels() -> None:
    assert navigation_labels() == ("B. Back", "M. Main Menu", "Q. Quit")
    assert navigation_labels(all_items=True) == (
        "A. All", "B. Back", "M. Main Menu", "Q. Quit"
    )
    assert navigation_labels(back=False, quit=False) == ("M. Main Menu",)


def test_print_navigation_options_uses_injected_stream() -> None:
    stream = StringIO()
    print_navigation_options(file=stream)
    assert stream.getvalue().splitlines() == list(navigation_labels())


def test_navigation_hints() -> None:
    assert navigation_hint() == "Please choose a listed option, B, M, or Q."
    assert navigation_hint(all_items=True) == (
        "Please choose a listed option, A, B, M, or Q."
    )
