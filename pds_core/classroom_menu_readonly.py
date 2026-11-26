"""Core #242 B2: staged read-only classroom screens with injected I/O.

This controller is not the qualified public classroom menu. It reads only
through Core #242's canonical discovery service and provides no write action.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from pds_core.classroom_discovery import (
    ClassroomDiscoveryError,
    ClassroomOverview,
    ClassroomRosterView,
    inspect_classroom_overview,
    inspect_classroom_roster,
)
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

_PAGE_SIZE = 12
_REVALIDATE = "Revalidate workspace, school year, class, roster and work on return."


def _safe(value: object) -> str:
    return "".join(
        char
        if not unicodedata.category(char).startswith("C")
        and unicodedata.category(char) not in {"Zl", "Zp"}
        else "\ufffd"
        for char in str(value)[:180]
    )


def _receipt(
    request: SharedTeacherMenuRequest, kind: TeacherMenuExit, message: str
) -> SharedTeacherMenuResult:
    return SharedTeacherMenuResult(
        return_token=request.return_token,
        exit=kind,
        durability=TeacherDurability.NO_CHANGE,
        change_scopes=frozenset(),
        message=f"{message} {_REVALIDATE}",
    )


class _ReadOnlyController:
    def __init__(
        self,
        request: SharedTeacherMenuRequest,
        read_line: Callable[[], str],
        output: TextIO,
        error_output: TextIO,
        workspace_changes_enabled: bool = False,
        school_year_changes_enabled: bool = False,
        class_changes_enabled: bool = False,
        standards_changes_enabled: bool = False,
        roster_import_enabled: bool = False,
        student_edits_enabled: bool = False,
    ) -> None:
        self.workspace_changes_enabled = workspace_changes_enabled
        self.school_year_changes_enabled = school_year_changes_enabled
        self.class_changes_enabled = class_changes_enabled
        self.standards_changes_enabled = standards_changes_enabled
        self.roster_import_enabled = roster_import_enabled
        self.student_edits_enabled = student_edits_enabled
        self.request = request
        self.read_line = read_line
        self.output = output
        self.errors = error_output
        self.page = "home"
        self.class_id: str | None = None
        self.student_id: str | None = None
        self.class_page = 0
        self.roster_page = 0
        self.class_max_page = 0
        self.roster_max_page = 0
        self.notice: str | None = None
        self.baseline: tuple[Path, str | None] | None = None

    def _overview(self) -> ClassroomOverview:
        overview = inspect_classroom_overview(self.request.context.workspace_root)
        observation = (overview.workspace.root, overview.active_school_year)
        if self.baseline is None:
            self.baseline = observation
        elif self.baseline != observation:
            raise ClassroomDiscoveryError(
                "context_changed",
                "Workspace or active school year changed during this visit.",
            )
        return overview

    def _roster(self, overview: ClassroomOverview) -> ClassroomRosterView:
        if self.class_id is None or self.class_id not in {
            item.class_id for item in overview.classes
        }:
            raise ClassroomDiscoveryError(
                "class_changed",
                "Previously selected class is no longer available.",
            )
        return inspect_classroom_roster(overview.workspace.root, self.class_id)

    def _header(self, title: str) -> None:
        screen.clear_screen(self.output)
        print_teacher_header(
            TeacherScreenHeader("PDS Core", title, self.request.context.display_label),
            output=self.output,
            color="never",
        )
        if self.notice is not None:
            print(self.notice, file=self.output)
            self.notice = None
        if self.workspace_changes_enabled:
            print(
                (
                    "Administrative changes require review and confirmation; "
                    "roster imports require review."
                    if self.roster_import_enabled
                    else "Administrative changes require review and confirmation; "
                    "roster browsing remains read-only."
                    if self.class_changes_enabled
                    else "Classroom data remains read-only; administrative changes "
                    "require review and confirmation."
                ),
                file=self.output,
            )
        else:
            print(
                "Read-only classroom preview. No changes can be saved.",
                file=self.output,
            )

    def _render(
        self, overview: ClassroomOverview, roster: ClassroomRosterView | None
    ) -> tuple[str, ...]:
        choices: tuple[str, ...] = ()
        if self.page == "home":
            title = "Workspace & Classroom Management"
            if not self.workspace_changes_enabled:
                title += " — Read-only"
            self._header(title)
            print("1. Workspace and school year", file=self.output)
            print("2. Classes and rosters", file=self.output)
            print(
                "3. Standards management"
                if self.standards_changes_enabled
                else "3. Standards (not available in this preview)",
                file=self.output,
            )
            if self.workspace_changes_enabled:
                print("4. Manage saved workspace preference", file=self.output)
            if self.school_year_changes_enabled:
                print("5. Manage school year", file=self.output)
            if self.class_changes_enabled:
                print("6. Create an empty class", file=self.output)
        elif self.page == "workspace":
            self._header("Workspace and school year — Read-only")
            status = overview.workspace
            print(f"Workspace: {_safe(status.root)}", file=self.output)
            print(f"Resolution source: {status.source}", file=self.output)
            state = (
                "not present"
                if not status.exists
                else "directory"
                if status.is_dir
                else "invalid"
            )
            print(f"Workspace state: {state}", file=self.output)
            writable = "yes" if status.is_writable else "no"
            print(f"Writable: {writable}", file=self.output)
            print(
                f"Active school year: {overview.active_school_year or 'none'}",
                file=self.output,
            )
        elif self.page == "classes":
            self._header("Classes — Read-only")
            total = len(overview.classes)
            self.class_max_page = max(0, (total - 1) // _PAGE_SIZE)
            start = self.class_page * _PAGE_SIZE
            if start >= total and self.class_page:
                self.class_page = 0
                start = 0
            page_items = overview.classes[start : start + _PAGE_SIZE]
            choices = tuple(item.class_id for item in page_items)
            print(f"Classes found: {total}", file=self.output)
            if not choices:
                print("No class folders found.", file=self.output)
            for number, item in enumerate(page_items, 1):
                year = item.school_year or "year unspecified"
                enrollment = "roster present" if item.roster_present else "no roster"
                print(
                    f"{number}. {_safe(item.display_label)} "
                    f"[ID: {item.class_id}] — {year}; {enrollment}",
                    file=self.output,
                )
            self._pager(start, total)
        elif self.page == "roster" and roster is not None:
            self._header(
                "Class roster"
                if self.roster_import_enabled
                else "Class roster — Read-only"
            )
            print(f"Class ID: {roster.class_id}", file=self.output)
            total = len(roster.students)
            self.roster_max_page = max(0, (total - 1) // _PAGE_SIZE)
            start = self.roster_page * _PAGE_SIZE
            if start >= total and self.roster_page:
                self.roster_page = 0
                start = 0
            roster_page_items = roster.students[start : start + _PAGE_SIZE]
            choices = tuple(item.student_id for item in roster_page_items)
            if not roster.roster_present:
                print("No canonical roster exists for this class.", file=self.output)
            else:
                print(f"Students enrolled: {total}", file=self.output)
            for number, student_item in enumerate(roster_page_items, 1):
                print(
                    f"{number}. {_safe(student_item.label)} — "
                    f"Period {_safe(student_item.period)}",
                    file=self.output,
                )
            self._pager(start, total)
            if self.roster_import_enabled:
                print("I. Import or replace full roster", file=self.output)
            if self.student_edits_enabled:
                print("A. Add student enrollment", file=self.output)
        elif self.page == "student" and roster is not None:
            self._header(
                "Student enrollment"
                if self.student_edits_enabled
                else "Student enrollment — Read-only"
            )
            selected = next(
                (
                    item
                    for item in roster.students
                    if item.student_id == self.student_id
                ),
                None,
            )
            if selected is None:
                raise ClassroomDiscoveryError(
                    "student_changed",
                    "Previously selected student is no longer enrolled.",
                )
            print(f"Class ID: {roster.class_id}", file=self.output)
            print(f"Student: {_safe(selected.label)}", file=self.output)
            print(f"Period: {_safe(selected.period)}", file=self.output)
            if self.student_edits_enabled:
                print("E. Edit enrollment   R. Remove enrollment", file=self.output)
            else:
                print("Editing is not enabled in this preview.", file=self.output)
        else:
            self._header("Standards — Not yet available")
            print("Standards integration belongs to a later slice.", file=self.output)
        print("B. Back   M. Caller Main Menu   Q. Quit", file=self.output)
        print("Choose an option: ", end="", file=self.output, flush=True)
        return choices

    def _pager(self, start: int, total: int) -> None:
        if start + _PAGE_SIZE < total:
            print(">. Next page", file=self.output)
        if start > 0:
            print("<. Previous page", file=self.output)

    def _back(self) -> TeacherMenuExit | None:
        if self.page == "home":
            return TeacherMenuExit.BACK
        if self.page == "student":
            self.page = "roster"
        elif self.page == "roster":
            self.page = "classes"
            self.student_id = None
        else:
            self.page = "home"
            self.class_id = None
            self.student_id = None
        return None

    def _select(self, response: str, choices: tuple[str, ...]) -> None:
        if response in {">", "<"} and self.page in {"classes", "roster"}:
            current = self.class_page if self.page == "classes" else self.roster_page
            maximum = (
                self.class_max_page if self.page == "classes" else self.roster_max_page
            )
            next_page = min(maximum, max(0, current + (1 if response == ">" else -1)))
            if self.page == "classes":
                self.class_page = next_page
            else:
                self.roster_page = next_page
            return

        if len(response) > 3 or not response.isascii() or not response.isdigit():
            self.notice = "Choose a listed option, B, M or Q."
            return
        number = int(response)
        if self.page == "home" and number in (1, 2, 3):
            self.page = {1: "workspace", 2: "classes", 3: "standards"}[number]
            return
        if not 1 <= number <= len(choices):
            self.notice = "Choose a listed option, B, M or Q."
            return
        if self.page == "classes":
            self.class_id = choices[number - 1]
            self.roster_page = 0
            self.page = "roster"
        elif self.page == "roster":
            self.student_id = choices[number - 1]
            self.page = "student"

    def run(self) -> SharedTeacherMenuResult:
        while True:
            try:
                overview = self._overview()
                roster = (
                    self._roster(overview)
                    if self.page in {"roster", "student"}
                    else None
                )
                choices = self._render(overview, roster)
            except ClassroomDiscoveryError as error:
                print(f"Classroom inspection refused: {error}", file=self.errors)
                return _receipt(
                    self.request,
                    TeacherMenuExit.FAILED,
                    "Classroom inspection failed safely; no changes were made.",
                )
            try:
                raw = self.read_line()
            except (EOFError, StopIteration, KeyboardInterrupt):
                return _receipt(self.request, TeacherMenuExit.CANCELLED, "Input ended.")
            if type(raw) is not str:
                return _receipt(self.request, TeacherMenuExit.FAILED, "Invalid input.")
            if raw == "":
                return _receipt(self.request, TeacherMenuExit.CANCELLED, "Input ended.")
            choice = raw.strip().casefold()
            try:
                navigation = parse_navigation_choice(choice, allow_all=False)
            except ReturnToMainMenu:
                return _receipt(
                    self.request, TeacherMenuExit.MAIN_MENU, "Caller main menu."
                )
            except QuitPDS:
                return _receipt(
                    self.request, TeacherMenuExit.QUIT, "Caller handles exit."
                )
            if navigation is NavigationChoice.BACK:
                outcome = self._back()
                if outcome is not None:
                    return _receipt(
                        self.request, outcome, "Returned to the calling screen."
                    )
                continue
            if self.workspace_changes_enabled and self.page == "home" and choice == "4":
                from pds_core.classroom_menu_workspace import (
                    run_workspace_preference_review,
                )

                receipt = run_workspace_preference_review(
                    self.request,
                    read_line=self.read_line,
                    output=self.output,
                    error_output=self.errors,
                )
                if receipt is not None:
                    return receipt
                continue
            if (
                self.school_year_changes_enabled
                and self.page == "home"
                and choice == "5"
            ):
                from pds_core.classroom_menu_school_year import run_school_year_review

                receipt = run_school_year_review(
                    self.request,
                    workspace_root=overview.workspace.root,
                    expected_active_year=overview.active_school_year,
                    read_line=self.read_line,
                    output=self.output,
                    error_output=self.errors,
                )
                if receipt is not None:
                    return receipt
                continue
            if self.class_changes_enabled and self.page == "home" and choice == "6":
                from pds_core.classroom_menu_class import run_class_creation_review

                receipt = run_class_creation_review(
                    self.request,
                    workspace_root=overview.workspace.root,
                    expected_active_year=overview.active_school_year,
                    read_line=self.read_line,
                    output=self.output,
                    error_output=self.errors,
                )
                if receipt is not None:
                    return receipt
                continue
            if self.standards_changes_enabled and self.page == "home" and choice == "3":
                from pds_core.classroom_menu_standards import run_standards_review

                receipt = run_standards_review(
                    self.request,
                    workspace_root=overview.workspace.root,
                    read_line=self.read_line,
                    output=self.output,
                    error_output=self.errors,
                )
                if receipt is not None:
                    return receipt
                continue
            if (
                self.roster_import_enabled
                and self.page == "roster"
                and choice == "i"
                and roster is not None
            ):
                from pds_core.classroom_menu_roster_import import (
                    run_roster_import_review,
                )

                receipt = run_roster_import_review(
                    self.request,
                    workspace_root=overview.workspace.root,
                    class_id=roster.class_id,
                    expected_active_year=overview.active_school_year,
                    read_line=self.read_line,
                    output=self.output,
                    error_output=self.errors,
                )
                if receipt is not None:
                    return receipt
                continue
            if (
                self.student_edits_enabled
                and roster is not None
                and (
                    (self.page == "roster" and choice == "a")
                    or (self.page == "student" and choice in {"e", "r"})
                )
            ):
                from pds_core.classroom_menu_student_edit import run_student_edit_review

                receipt = run_student_edit_review(
                    self.request,
                    workspace_root=overview.workspace.root,
                    class_id=roster.class_id,
                    expected_active_year=overview.active_school_year,
                    operation="add"
                    if choice == "a"
                    else "update"
                    if choice == "e"
                    else "remove",
                    selected_id=None if choice == "a" else self.student_id,
                    read_line=self.read_line,
                    output=self.output,
                    error_output=self.errors,
                )
                if receipt is not None:
                    return receipt
                continue
            self._select(choice, choices)


def run_classroom_readonly_preview(
    request: SharedTeacherMenuRequest,
    *,
    read_line: Callable[[], str],
    output: TextIO,
    error_output: TextIO | None = None,
) -> SharedTeacherMenuResult:
    """Staged B2 reader for tests; not the qualified public classroom menu."""
    return _ReadOnlyController(
        request=request,
        read_line=read_line,
        output=output,
        error_output=output if error_output is None else error_output,
    ).run()


def run_classroom_workspace_preview(
    request: SharedTeacherMenuRequest,
    *,
    read_line: Callable[[], str],
    output: TextIO,
    error_output: TextIO | None = None,
) -> SharedTeacherMenuResult:
    """Private C3A integration gate. Public callers remain unavailable."""
    return _ReadOnlyController(
        request=request,
        read_line=read_line,
        output=output,
        error_output=output if error_output is None else error_output,
        workspace_changes_enabled=True,
    ).run()


def run_classroom_school_year_preview(
    request: SharedTeacherMenuRequest,
    *,
    read_line: Callable[[], str],
    output: TextIO,
    error_output: TextIO | None = None,
) -> SharedTeacherMenuResult:
    """C3B4 private synthetic gate, not a public menu capability."""
    return _ReadOnlyController(
        request=request,
        read_line=read_line,
        output=output,
        error_output=output if error_output is None else error_output,
        workspace_changes_enabled=True,
        school_year_changes_enabled=True,
    ).run()


def run_classroom_class_preview(
    request: SharedTeacherMenuRequest,
    *,
    read_line: Callable[[], str],
    output: TextIO,
    error_output: TextIO | None = None,
) -> SharedTeacherMenuResult:
    """Private C3B7 class creation gate; no public capability."""
    return _ReadOnlyController(
        request=request,
        read_line=read_line,
        output=output,
        error_output=output if error_output is None else error_output,
        workspace_changes_enabled=True,
        school_year_changes_enabled=True,
        class_changes_enabled=True,
    ).run()


def run_classroom_standards_preview(
    request: SharedTeacherMenuRequest,
    *,
    read_line: Callable[[], str],
    output: TextIO,
    error_output: TextIO | None = None,
) -> SharedTeacherMenuResult:
    """Private C4B Standards composition gate."""
    return _ReadOnlyController(
        request=request,
        read_line=read_line,
        output=output,
        error_output=output if error_output is None else error_output,
        workspace_changes_enabled=True,
        school_year_changes_enabled=True,
        class_changes_enabled=True,
        standards_changes_enabled=True,
    ).run()


def run_classroom_roster_import_preview(
    request: SharedTeacherMenuRequest,
    *,
    read_line: Callable[[], str],
    output: TextIO,
    error_output: TextIO | None = None,
) -> SharedTeacherMenuResult:
    """Private D1 composition gate."""
    return _ReadOnlyController(
        request=request,
        read_line=read_line,
        output=output,
        error_output=output if error_output is None else error_output,
        workspace_changes_enabled=True,
        school_year_changes_enabled=True,
        class_changes_enabled=True,
        standards_changes_enabled=True,
        roster_import_enabled=True,
    ).run()


def run_classroom_student_edit_preview(
    request: SharedTeacherMenuRequest,
    *,
    read_line: Callable[[], str],
    output: TextIO,
    error_output: TextIO | None = None,
) -> SharedTeacherMenuResult:
    """Private D2 composition gate."""
    return _ReadOnlyController(
        request=request,
        read_line=read_line,
        output=output,
        error_output=output if error_output is None else error_output,
        workspace_changes_enabled=True,
        school_year_changes_enabled=True,
        class_changes_enabled=True,
        standards_changes_enabled=True,
        roster_import_enabled=True,
        student_edits_enabled=True,
    ).run()
