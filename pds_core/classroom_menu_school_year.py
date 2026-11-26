"""C3B4 staged teacher year review; not a public capability."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TextIO

from pds_core.classroom_menu_outcome import _outcome_notice

from pds_core.classroom_admin_preview import SchoolYearChange
from pds_core.classroom_school_year_commit import (
    GuardedSchoolYearReview,
    SchoolYearCommitError,
    SchoolYearConflictError,
    SchoolYearWriteError,
    commit_guarded_school_year_change,
    plan_guarded_school_year_change,
)
from pds_core.cli_support import screen
from pds_core.teacher_context import (
    SharedTeacherMenuRequest,
    SharedTeacherMenuResult,
    TeacherChangeScope,
    TeacherDurability,
    TeacherMenuExit,
)
from pds_core.teacher_ui import TeacherScreenHeader, print_teacher_header

_REVALIDATE = "Revalidate workspace, school year, class, roster and work on return."


def _receipt(
    request: SharedTeacherMenuRequest,
    outcome: TeacherMenuExit,
    *,
    durability: TeacherDurability = TeacherDurability.NO_CHANGE,
    detail: str = "School-year review returned without changes.",
) -> SharedTeacherMenuResult:
    scopes = (
        frozenset({TeacherChangeScope.SCHOOL_YEAR})
        if durability is not TeacherDurability.NO_CHANGE
        else frozenset()
    )
    return SharedTeacherMenuResult(
        request.return_token, outcome, durability, scopes, f"{detail} {_REVALIDATE}"
    )


def _read(read_line: Callable[[], str]) -> str | None:
    try:
        value = read_line()
    except (EOFError, StopIteration, KeyboardInterrupt):
        return None
    return value.strip() if type(value) is str and value else None


def _navigation(
    choice: str, request: SharedTeacherMenuRequest
) -> SharedTeacherMenuResult | None:
    if choice.casefold() == "m":
        return _receipt(request, TeacherMenuExit.MAIN_MENU)
    if choice.casefold() == "q":
        return _receipt(request, TeacherMenuExit.QUIT)
    return None


def _header(request: SharedTeacherMenuRequest, title: str, out: TextIO) -> None:
    screen.clear_screen(out)
    print_teacher_header(
        TeacherScreenHeader("PDS Core", title, request.context.display_label),
        output=out,
        color="never",
    )


def _review(
    request: SharedTeacherMenuRequest,
    review: GuardedSchoolYearReview,
    out: TextIO,
) -> None:
    plan = review.proposal
    _header(request, "Review school-year transition", out)
    print(
        f"Workspace: {json.dumps(str(plan.workspace_root), ensure_ascii=True)}",
        file=out,
    )
    print(f"Operation: {plan.action}", file=out)
    print(f"Previous record: {plan.previous_record_status}", file=out)
    print(f"School year before: {plan.previous_school_year or '(none)'}", file=out)
    print(f"Active year after: {plan.proposed_active_year or '(none)'}", file=out)
    print(f"Effective timestamp: {review.effective_at.isoformat()}", file=out)
    if plan.no_change:
        print("No-op: the existing opening timestamp will be preserved.", file=out)
    elif plan.action == "close":
        print("Existing classes, rosters and work will be preserved.", file=out)
    else:
        print("The first canonical year record will be created.", file=out)
    print("PREVIEW ONLY — no write occurred.", file=out)
    print("C. Confirm exact transition  B. Cancel  M. Main Menu  Q. Quit", file=out)
    print("Choice: ", end="", file=out, flush=True)


def _failure(
    request: SharedTeacherMenuRequest,
    error: SchoolYearCommitError,
    stderr: TextIO,
) -> SharedTeacherMenuResult:
    if isinstance(error, SchoolYearWriteError):
        if error.reason == "write_outcome_uncertain":
            _outcome_notice("Write outcome uncertain; inspect before retrying.", file=stderr)
            return _receipt(
                request,
                TeacherMenuExit.FAILED,
                durability=TeacherDurability.INDETERMINATE,
                detail="School-year write outcome is uncertain.",
            )
        _outcome_notice("School-year writer refused the change.", file=stderr)
    elif isinstance(error, SchoolYearConflictError):
        _outcome_notice("School-year state changed; review again.", file=stderr)
    else:
        _outcome_notice("School-year operation refused safely.", file=stderr)
    return _receipt(
        request, TeacherMenuExit.FAILED, detail="School-year operation was refused."
    )


def _aware(raw: str) -> datetime | None:
    try:
        date = datetime.fromisoformat(raw)
        if date.tzinfo is not None and date.utcoffset() is not None:
            return date
    except (ValueError, OverflowError):
        pass
    return None


def run_school_year_review(
    request: SharedTeacherMenuRequest,
    *,
    workspace_root: Path,
    expected_active_year: str | None,
    read_line: Callable[[], str],
    output: TextIO,
    error_output: TextIO,
) -> SharedTeacherMenuResult | None:
    """Return None on B to parent; after any commit return to caller."""
    while True:
        _header(request, "Manage school year", output)
        print("1. Review opening the first year", file=output)
        print("2. Review closing the active year", file=output)
        print("Closed-year rollover is not available.", file=output)
        print("B. Back  M. Main Menu  Q. Quit", file=output)
        print("Choice: ", end="", file=output, flush=True)
        choice = _read(read_line)
        if choice is None:
            return _receipt(request, TeacherMenuExit.CANCELLED)
        nav = _navigation(choice, request)
        if nav is not None:
            return nav
        if choice.casefold() == "b":
            return None
        if choice == "1":
            _header(request, "Choose first school year", output)
            print("Year YYYY-YYYY (or B): ", end="", file=output, flush=True)
            year = _read(read_line)
            if year is None:
                return _receipt(request, TeacherMenuExit.CANCELLED)
            nav = _navigation(year, request)
            if nav is not None:
                return nav
            if year.casefold() == "b":
                continue
            try:
                if len(year) > 32:
                    raise ValueError("Year too long")
                change = SchoolYearChange("open", year)
            except (ValueError, TypeError):
                print("Enter a valid YYYY-YYYY year.", file=output)
                continue
        elif choice == "2":
            change = SchoolYearChange("close")
        else:
            print("Choose 1, 2, B, M or Q.", file=output)
            continue

        _header(request, "Effective timestamp", output)
        print("Enter an ISO 8601 time with UTC offset, or B.", file=output)
        print("Example: 2026-09-08T08:00:00-04:00", file=output)
        print("Timestamp: ", end="", file=output, flush=True)
        raw = _read(read_line)
        if raw is None:
            return _receipt(request, TeacherMenuExit.CANCELLED)
        nav = _navigation(raw, request)
        if nav is not None:
            return nav
        if raw.casefold() == "b":
            continue
        moment = _aware(raw) if len(raw) <= 80 else None
        if moment is None:
            print("A timezone-aware timestamp is required.", file=output)
            continue
        try:
            review = plan_guarded_school_year_change(
                workspace_root, change, effective_at=moment
            )
        except SchoolYearCommitError as error:
            return _failure(request, error, error_output)

        plan = review.proposal
        active = (
            plan.previous_school_year if plan.previous_record_status == "open" else None
        )
        if active != expected_active_year:
            print("Active year changed while the menu was open.", file=error_output)
            return _receipt(
                request,
                TeacherMenuExit.FAILED,
                detail="Selected school-year context is stale.",
            )

        _review(request, review, output)
        answer = _read(read_line)
        if answer is None:
            return _receipt(request, TeacherMenuExit.CANCELLED)
        nav = _navigation(answer, request)
        if nav is not None:
            return nav
        if answer.casefold() == "b":
            continue
        if answer.casefold() != "c":
            print("Not confirmed; returning to year choices.", file=output)
            continue
        try:
            result = commit_guarded_school_year_change(
                workspace_root,
                change,
                effective_at=review.effective_at,
                expected_current_state_token=review.current_state_token,
                expected_candidate_state_token=review.candidate_state_token,
                confirmed=True,
            )
        except SchoolYearCommitError as error:
            return _failure(request, error, error_output)
        if result.outcome == "committed":
            _outcome_notice("School-year transition committed.", file=output)
            return _receipt(
                request,
                TeacherMenuExit.BACK,
                durability=TeacherDurability.COMMITTED,
                detail="School-year record committed.",
            )
        _outcome_notice("School-year state already matched.", file=output)
        return _receipt(request, TeacherMenuExit.BACK, detail="No year record changed.")
