"""Core #242 Slice A: synthetic classroom-menu navigation, with no data access.

This module is a *test-only* navigation scaffold. The public classroom menu
always reports UNAVAILABLE until the real implementation is qualified.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final, TextIO

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


# The page map explicitly separates navigation from every durable operation.
# No storage/service imports, selected-state cache, file creation or command
# execution is allowed in this scaffold.
_PAGES: Final[dict[str, tuple[str, tuple[tuple[str, str], ...]]]] = {
    "home": (
        "Workspace & Classroom Management — Navigation Preview",
        (
            ("Workspace and school years", "workspace"),
            ("Classes and rosters", "classes"),
            ("Standards", "standards"),
        ),
    ),
    "workspace": (
        "Workspace and school years — Preview",
        (
            ("Workspace overview", "workspace-status"),
            ("School-year management", "school-years"),
        ),
    ),
    "classes": (
        "Classes and rosters — Preview",
        (
            ("Class management", "class-management"),
            ("Full-roster imports", "full-import"),
            ("Edit one student enrollment", "student-edit"),
        ),
    ),
    "standards": (
        "Standards — Preview",
        (("Standards Library", "standards-library"),),
    ),
    "workspace-status": ("Workspace overview — Preview", ()),
    "school-years": ("School-year management — Preview", ()),
    "class-management": ("Class management — Preview", ()),
    "full-import": ("Full-roster imports — Preview", ()),
    "student-edit": ("Edit one student enrollment — Preview", ()),
    "standards-library": ("Standards Library — Preview", ()),
}

_REVALIDATE: Final[str] = (
    "Revalidate workspace, class, roster and work before resuming."
)


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
        message=f"{message} {_REVALIDATE}",
    )


def run_classroom_navigation_preview(
    request: SharedTeacherMenuRequest,
    *,
    read_line: Callable[[], str],
    output: TextIO,
) -> SharedTeacherMenuResult:
    """Exercise navigation/return semantics only; never inspect a workspace."""
    stack: list[str] = ["home"]
    notice: str | None = None

    while True:
        title, choices = _PAGES[stack[-1]]
        screen.clear_screen(output)
        print_teacher_header(
            TeacherScreenHeader("PDS Core", title, request.context.display_label),
            output=output,
            color="never",
        )
        if notice is not None:
            print(notice, file=output)
            notice = None
        print(
            "Navigation preview only. No workspace data is accessed or saved.",
            file=output,
        )
        for index, (label, _destination) in enumerate(choices, start=1):
            print(f"{index}. {label}", file=output)
        print("B. Back   M. Caller Main Menu   Q. Quit", file=output)
        print("Choose an option: ", end="", file=output, flush=True)

        try:
            raw = read_line()
        except (EOFError, StopIteration, KeyboardInterrupt):
            return _result(
                request,
                TeacherMenuExit.CANCELLED,
                "Input ended; no changes were made.",
            )
        if type(raw) is not str:
            return _result(
                request,
                TeacherMenuExit.FAILED,
                "Input was invalid; no changes were made.",
            )
        if raw == "":
            return _result(
                request,
                TeacherMenuExit.CANCELLED,
                "Input ended; no changes were made.",
            )

        value = raw.strip().casefold()
        try:
            navigation = parse_navigation_choice(value, allow_all=False)
        except ReturnToMainMenu:
            return _result(
                request,
                TeacherMenuExit.MAIN_MENU,
                "Return to the calling application's main menu.",
            )
        except QuitPDS:
            return _result(
                request,
                TeacherMenuExit.QUIT,
                "The calling application decides whether to exit.",
            )

        if navigation is NavigationChoice.BACK:
            if len(stack) == 1:
                return _result(
                    request,
                    TeacherMenuExit.BACK,
                    "Returned to the calling screen.",
                )
            stack.pop()
            continue

        if value.isascii() and value.isdigit():
            selected = int(value)
            if 1 <= selected <= len(choices):
                stack.append(choices[selected - 1][1])
                continue

        notice = "Choose a listed option, B, M or Q."
