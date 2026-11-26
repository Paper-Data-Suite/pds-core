"""Public callable Notes & Tasks menu backed by Core workspace Notes.

The Source/Core menu is available in this candidate build; producer/Suite
adoption and actual classroom qualification remain separate release gates.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TextIO

from pds_core.cli_support import screen
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

__all__ = ("run_notes_tasks_menu", "run_workspace_classroom_menu")

# Navigation-only simulation for synthetic Core tests; not a consumer switch
# and never offered by the regular Core menu.
_NAVIGATION_PREVIEW_TEST_ONLY = False

# Runtime feature available in this candidate; tests may disable it explicitly to
# verify unavailable/fallback behavior without mutating installed capabilities.
_NOTES_MENU_QUALIFIED = True


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
    """Public in-process Notes entry; requires an interactive caller session."""
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
    notice: str | None = None
    while True:
        screen_title = (
            "Notes & Tasks — Navigation Preview"
            if depth == 0
            else "Quick Capture — Preview"
            if depth == 1
            else f"{category} — Preview"
        )
        screen.clear_screen(output)
        print_teacher_header(
            TeacherScreenHeader(
                "PDS Core", screen_title, request.context.display_label
            ),
            output=output,
        )
        if notice is not None:
            print(notice, file=output)
            notice = None
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
            notice = "Choose a listed option, B, M, or Q."


# Core #242 Slice A is intentionally a *test-only* navigation scaffold.
# Public callers receive UNAVAILABLE until the real service composition,
# mutation/return semantics, installed candidate and capability qualify.
_CLASSROOM_NAVIGATION_PREVIEW_TEST_ONLY = False
# Temporary B2 qualification-only switch; public menu remains unavailable.
_CLASSROOM_READONLY_PREVIEW_TEST_ONLY = False
# C3A confirms saved workspace changes only behind a private synthetic gate.
_CLASSROOM_WORKSPACE_PREVIEW_TEST_ONLY = False
# C3B4 school-year writes are available only in the private acceptance gate.
_CLASSROOM_SCHOOL_YEAR_PREVIEW_TEST_ONLY = False
# C3B7 qualification only; never a consumer capability.
_CLASSROOM_CLASS_PREVIEW_TEST_ONLY = False
_CLASSROOM_STANDARDS_PREVIEW_TEST_ONLY = False


def _classroom_unavailable(
    request: SharedTeacherMenuRequest,
    *,
    interactive: bool,
) -> SharedTeacherMenuResult:
    message = (
        "Workspace & Classroom Management requires an interactive session."
        if not interactive
        else "Workspace & Classroom Management is not qualified in this Core build."
    )
    return SharedTeacherMenuResult(
        return_token=request.return_token,
        exit=TeacherMenuExit.UNAVAILABLE,
        durability=TeacherDurability.NO_CHANGE,
        change_scopes=frozenset(),
        message=(
            f"{message} No changes were made. "
            "Revalidate workspace, class, roster and work on return."
        ),
    )


def run_workspace_classroom_menu(
    request: SharedTeacherMenuRequest,
    *,
    read_line: Callable[[], str],
    output: TextIO,
    interactive: bool,
    error_output: TextIO | None = None,
) -> SharedTeacherMenuResult:
    """Callable #242 boundary; fail closed until classroom menu is qualified.

    The private navigation-preview switch is only for synthetic tests. It
    never reads, selects or modifies a real workspace and is not a capability.
    """
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
        return _classroom_unavailable(request, interactive=False)

    if _CLASSROOM_NAVIGATION_PREVIEW_TEST_ONLY:
        from pds_core.classroom_menu_navigation import run_classroom_navigation_preview

        return run_classroom_navigation_preview(
            request, read_line=read_line, output=output
        )

    if _CLASSROOM_STANDARDS_PREVIEW_TEST_ONLY:
        from pds_core.classroom_menu_readonly import run_classroom_standards_preview

        return run_classroom_standards_preview(
            request, read_line=read_line, output=output, error_output=error_output,
        )

    if _CLASSROOM_CLASS_PREVIEW_TEST_ONLY:
        from pds_core.classroom_menu_readonly import run_classroom_class_preview

        return run_classroom_class_preview(
            request,
            read_line=read_line,
            output=output,
            error_output=error_output,
        )

    if _CLASSROOM_SCHOOL_YEAR_PREVIEW_TEST_ONLY:
        from pds_core.classroom_menu_readonly import run_classroom_school_year_preview

        return run_classroom_school_year_preview(
            request,
            read_line=read_line,
            output=output,
            error_output=error_output,
        )

    if _CLASSROOM_WORKSPACE_PREVIEW_TEST_ONLY:
        from pds_core.classroom_menu_readonly import run_classroom_workspace_preview

        return run_classroom_workspace_preview(
            request,
            read_line=read_line,
            output=output,
            error_output=error_output,
        )

    if _CLASSROOM_READONLY_PREVIEW_TEST_ONLY:
        from pds_core.classroom_menu_readonly import run_classroom_readonly_preview

        return run_classroom_readonly_preview(
            request,
            read_line=read_line,
            output=output,
            error_output=error_output,
        )

    return _classroom_unavailable(request, interactive=True)
