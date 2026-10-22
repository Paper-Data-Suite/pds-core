"""Pure, explicitly opted-in teacher command parsing under Core contract v1.

The caller owns the prompt, local shortcuts, navigation, and any later dispatch.
This module never opens Notes, intercepts input globally, or checks whether a
Notes record service/menu exists. Import and parse have no I/O side effects.
"""

from __future__ import annotations

from enum import Enum

__all__ = ("PromptKind", "SharedTeacherCommand", "parse_shared_teacher_command")


class PromptKind(str, Enum):
    """Caller-declared prompt kind; never inferred from a prompt's text."""

    MENU_CHOICE = "menu_choice"
    DATA_ENTRY = "data_entry"
    CONFIRMATION = "confirmation"
    PAUSE = "pause"


class SharedTeacherCommand(str, Enum):
    """Shared requests recognized by this pure parser, not menu actions."""

    NOTES = "notes"


def parse_shared_teacher_command(
    value: str,
    *,
    prompt_kind: PromptKind,
    interactive: bool,
    allow_notes: bool = False,
) -> SharedTeacherCommand | None:
    """Recognize only exact ``:notes`` at an eligible interactive choice prompt.

    The explicit flags are caller-owned opt-in and are not proof that the Notes
    service, Notes menu, current workspace, or producer adoption is qualified.
    Invalid types fail before any parsing, even when a flag would otherwise
    disable recognition. Existing Core/producer navigation remains untouched.
    """
    if type(value) is not str:
        raise TypeError("value must be a str")
    if type(prompt_kind) is not PromptKind:
        raise TypeError("prompt_kind must be a PromptKind")
    if type(interactive) is not bool:
        raise TypeError("interactive must be a bool")
    if type(allow_notes) is not bool:
        raise TypeError("allow_notes must be a bool")

    if (
        prompt_kind is PromptKind.MENU_CHOICE
        and interactive is True
        and allow_notes is True
        and value.strip().casefold() == ":notes"
    ):
        return SharedTeacherCommand.NOTES
    return None
