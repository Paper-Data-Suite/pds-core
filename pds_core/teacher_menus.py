"""Callable Notes & Tasks boundary — Core #240-A/B, not yet advertised.

The real controller is source-implemented but remains behind a qualification
switch until Slice D. The Slice A navigation preview is retained for its
synthetic tests and is never advertised to consumers.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TextIO

from pds_core.menu_navigation import (
    NavigationChoice,
    QuitPDS,
    ReturnToMainMenu,
    parse_navigation_choice,
)
from pds_core.teacher_context import (
    SharedTeacherMenuRequest,
    SharedTeacherMenuResult,
    TeacherDurability,
    TeacherMenuExit,
)
from pds_core.teacher_ui import TeacherScreenHeader, print_teacher_header

__all__ = ("run_notes_tasks_menu",)

# Not a consumer switch. Enabled only in the synthetic Core-owned navigation
# tests. Production remains unavailable until final acceptance in Slice D.
_NAVIGATION_PREVIEW_TEST_ONLY = False

# Source-only implementation; turn on only after #240-D qualification.
_NOTES_MENU_QUALIFIED = False


def _result(
    request: SharedTeacherMenuRequest,
    exit_kind: TeacherMenuExit,
    message: str,
) -> SharedTeacherMenuResult:
    return SharedTeacherMenuResult(
        return_token=request.return_token,
        exit=exit_kind,
        durability=TeacherDurability.NO_CHANGE,
        change_scopes=frozenset(),
        message=message,
    )


def run_notes_tasks_menu(
    request: SharedTeacherMenuRequest,
    *,
    read_line: Callable[[], str],
    output: TextIO,
    interactive: bool,
    error_output: TextIO | None = None,
) -> SharedTeacherMenuResult:
    """Public in-process seam; real Notes UI remains gated pending acceptance."""
    if not isinstance(request, SharedTeacherMenuRequest):
        raise TypeError("request must be a SharedTeacherMenuRequest")
    if not callable(read_line):
        raise TypeError("read_line must be callable")
    if not callable(getattr(output, "write", None)):
        raise TypeError("output must be writable")
    if type(interactive) is not bool:
        raise TypeError("interactive must be a bool")
    if error_output is not None and not callable(getattr(error_output, "write", None)):
        raise TypeError("error_output must be writable or None")

    if not interactive:
        return _result(
            request,
            TeacherMenuExit.UNAVAILABLE,
            "Notes & Tasks requires a qualified interactive session.",
        )
    if _NAVIGATION_PREVIEW_TEST_ONLY:
        return _run_navigation_preview(request, read_line=read_line, output=output)
    if not _NOTES_MENU_QUALIFIED:
        return _result(
            request,
            TeacherMenuExit.UNAVAILABLE,
            "Notes & Tasks is not available yet. No changes were made.",
        )
    from pds_core.notes_menu_controller import run_notes_controller

    return run_notes_controller(
        request, read_line=read_line, output=output, error_output=error_output
    )


def _run_navigation_preview(
    request: SharedTeacherMenuRequest,
    *,
    read_line: Callable[[], str],
    output: TextIO,
) -> SharedTeacherMenuResult:
    """Synthetic menu stack for navigation verification; never calls storage."""
    # Depth: home, capture category, category preview. No save step exists.
    depth = 0
    category = ""
    while True:
        screen_title = (
            "Notes & Tasks — Navigation Preview"
            if depth == 0
            else "Quick Capture — Preview"
            if depth == 1
            else f"{category} — Preview"
        )
        print_teacher_header(
            TeacherScreenHeader(
                "PDS Core", screen_title, request.context.display_label
            ),
            output=output,
        )
        print("Preview only. Nothing entered here can be saved.", file=output)
        if depth == 0:
            print("1. Quick Capture preview", file=output)
        elif depth == 1:
            print("1. Idea   2. Task   3. Reflection", file=output)
        else:
            print("Saving will be available in Slice 240-B.", file=output)
        print("B. Back   M. Main Menu   Q. Quit", file=output)
        print("Choose an option: ", end="", file=output, flush=True)
        try:
            raw = read_line()
        except (EOFError, StopIteration, KeyboardInterrupt):
            return _result(
                request, TeacherMenuExit.CANCELLED, "Cancelled. No changes were made."
            )
        if type(raw) is not str:
            return _result(
                request, TeacherMenuExit.FAILED, "Invalid input; no changes were made."
            )
        if raw == "":
            return _result(
                request, TeacherMenuExit.CANCELLED, "Cancelled. No changes were made."
            )
        choice = raw.strip().casefold()
        try:
            navigation = parse_navigation_choice(choice, allow_all=False)
        except ReturnToMainMenu:
            return _result(
                request, TeacherMenuExit.MAIN_MENU, "Return to the calling main menu."
            )
        except QuitPDS:
            return _result(
                request, TeacherMenuExit.QUIT, "The calling application may now exit."
            )
        if navigation is NavigationChoice.BACK:
            if depth == 0:
                return _result(
                    request, TeacherMenuExit.BACK, "Returned to the calling screen."
                )
            depth -= 1
            continue
        if depth == 0 and choice == "1":
            depth = 1
        elif depth == 1 and choice in ("1", "2", "3"):
            category = {"1": "Idea", "2": "Task", "3": "Reflection"}[choice]
            depth = 2
        else:
            print("Choose a listed option, B, M, or Q.", file=output)
