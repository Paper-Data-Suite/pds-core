"""Shared navigation primitives for teacher-facing PDS menus."""

from __future__ import annotations

import sys
from enum import Enum
from typing import TextIO


class NavigationChoice(Enum):
    """Navigation choices shared by controlled PDS prompts."""

    BACK = "b"
    MAIN_MENU = "m"
    QUIT = "q"
    ALL = "a"


class ReturnToMainMenu(Exception):
    """Unwind the current workflow and redraw the active module's main menu."""


class QuitPDS(Exception):
    """Unwind the current workflow and exit the active PDS module cleanly."""


def parse_navigation_choice(
    value: str,
    *,
    allow_back: bool = True,
    allow_main_menu: bool = True,
    allow_quit: bool = True,
    allow_all: bool = False,
) -> NavigationChoice | None:
    """Parse one navigation command without performing any menu routing."""
    choice = value.strip().casefold()
    if choice == NavigationChoice.BACK.value and allow_back:
        return NavigationChoice.BACK
    if choice == NavigationChoice.MAIN_MENU.value and allow_main_menu:
        raise ReturnToMainMenu
    if choice == NavigationChoice.QUIT.value and allow_quit:
        raise QuitPDS
    if choice == NavigationChoice.ALL.value and allow_all:
        return NavigationChoice.ALL
    return None


def navigation_labels(
    *,
    back: bool = True,
    main_menu: bool = True,
    quit: bool = True,
    all_items: bool = False,
) -> tuple[str, ...]:
    """Return enabled navigation labels in their standard display order."""
    labels: list[str] = []
    if all_items:
        labels.append("A. All")
    if back:
        labels.append("B. Back")
    if main_menu:
        labels.append("M. Main Menu")
    if quit:
        labels.append("Q. Quit")
    return tuple(labels)


def print_navigation_options(
    *,
    back: bool = True,
    main_menu: bool = True,
    quit: bool = True,
    all_items: bool = False,
    file: TextIO | None = None,
) -> None:
    """Print enabled navigation labels to the supplied stream."""
    output = sys.stdout if file is None else file
    for label in navigation_labels(
        back=back, main_menu=main_menu, quit=quit, all_items=all_items
    ):
        print(label, file=output)


def navigation_hint(*, all_items: bool = False) -> str:
    """Return the standard invalid-selection guidance."""
    commands = "A, B, M, or Q" if all_items else "B, M, or Q"
    return f"Please choose a listed option, {commands}."
