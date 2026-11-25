"""C3B7 private empty-class teacher workflow; no public capability."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from pds_core.classroom_admin_preview import ClassCreationChange
from pds_core.classroom_class_commit import (
    ClassCreationError,
    ClassCreationWriteError,
    commit_guarded_class_creation,
    inspect_class_creation_recovery,
    plan_guarded_class_creation,
)
from pds_core.classroom_menu_school_year import _aware, _header, _read
from pds_core.teacher_context import (
    SharedTeacherMenuRequest,
    SharedTeacherMenuResult,
    TeacherChangeScope,
    TeacherDurability,
    TeacherMenuExit,
)

_REVALIDATE = "Revalidate workspace, school year, class, roster and work on return."


def _receipt(
    request: SharedTeacherMenuRequest,
    exit_kind: TeacherMenuExit,
    detail: str,
    durability: TeacherDurability = TeacherDurability.NO_CHANGE,
) -> SharedTeacherMenuResult:
    return SharedTeacherMenuResult(
        request.return_token,
        exit_kind,
        durability,
        (
            frozenset()
            if durability is TeacherDurability.NO_CHANGE
            else frozenset({TeacherChangeScope.CLASS})
        ),
        f"{detail} {_REVALIDATE}",
    )


def _nav(
    request: SharedTeacherMenuRequest, choice: str | None
) -> SharedTeacherMenuResult | None:
    if choice is None:
        return _receipt(request, TeacherMenuExit.CANCELLED, "Input ended.")
    if choice.casefold() == "m":
        return _receipt(request, TeacherMenuExit.MAIN_MENU, "Caller main menu.")
    if choice.casefold() == "q":
        return _receipt(request, TeacherMenuExit.QUIT, "Caller handles exit.")
    return None


def run_class_creation_review(
    request: SharedTeacherMenuRequest,
    *,
    workspace_root: Path,
    expected_active_year: str | None,
    read_line: Callable[[], str],
    output: TextIO,
    error_output: TextIO,
) -> SharedTeacherMenuResult | None:
    """B returns to parent; a confirmed write returns immediately to caller."""
    if expected_active_year is None:
        print("Open a school year before creating a class.", file=error_output)
        return _receipt(
            request, TeacherMenuExit.FAILED, "No active school year."
        )
    _header(request, "Create an empty class", output)
    print(f"Active school year: {expected_active_year}", file=output)
    print("Class ID (letters, digits, hyphens, underscores), or B/M/Q:", file=output)
    choice = _read(read_line)
    nav = _nav(request, choice)
    if nav is not None:
        return nav
    assert choice is not None
    if choice.casefold() == "b":
        return None
    try:
        if len(choice) > 100:
            raise ValueError("Class ID too long")
        change = ClassCreationChange(choice, expected_active_year)
    except (ValueError, TypeError):
        print("Enter a valid class identifier.", file=error_output)
        return _receipt(request, TeacherMenuExit.FAILED, "Invalid class identifier.")

    _header(request, "Class creation timestamp", output)
    print("Enter ISO 8601 time with UTC offset, or B/M/Q.", file=output)
    print("Example: 2026-09-08T08:00:00-04:00", file=output)
    raw = _read(read_line)
    nav = _nav(request, raw)
    if nav is not None:
        return nav
    assert raw is not None
    if raw.casefold() == "b":
        return None
    at = _aware(raw) if len(raw) <= 80 else None
    if at is None:
        print("A timezone-aware timestamp is required.", file=error_output)
        return _receipt(request, TeacherMenuExit.FAILED, "Invalid timestamp.")
    try:
        review = plan_guarded_class_creation(workspace_root, change, created_at=at)
    except ClassCreationError:
        print("Class proposal refused; inspect the current classroom state.", file=error_output)
        return _receipt(request, TeacherMenuExit.FAILED, "Class creation refused.")

    _header(request, "Review new empty class", output)
    print(f"Workspace: {json.dumps(str(review.proposal.workspace_root))}", file=output)
    print(f"Class ID: {change.class_id}", file=output)
    print(f"School year: {change.school_year}", file=output)
    print(f"Created at: {at.isoformat()}", file=output)
    print("Creates class folder and class metadata; no roster is created.", file=output)
    print("Existing classes, rosters and producer work are preserved.", file=output)
    print("PREVIEW ONLY — no write occurred.", file=output)
    print("C. Confirm exact creation  B. Cancel  M. Main Menu  Q. Quit", file=output)
    answer = _read(read_line)
    nav = _nav(request, answer)
    if nav is not None:
        return nav
    assert answer is not None
    if answer.casefold() == "b":
        return None
    if answer.casefold() != "c":
        print("Not confirmed; no write attempted.", file=output)
        return None
    try:
        commit_guarded_class_creation(
            workspace_root,
            change,
            created_at=at,
            expected_current_state_token=review.current_state_token,
            expected_candidate_state_token=review.candidate_state_token,
            confirmed=True,
        )
    except ClassCreationWriteError as error:
        durability = {
            "no_change": TeacherDurability.NO_CHANGE,
            "partial": TeacherDurability.PARTIAL,
            "indeterminate": TeacherDurability.INDETERMINATE,
        }[error.outcome]
        observed = inspect_class_creation_recovery(
            workspace_root, change, created_at=at
        )
        print(f"Class creation incomplete. Recovery observation: {observed}.", file=error_output)
        print("Inspect canonical state before retry. Do not delete or adopt an incomplete class automatically.", file=error_output)
        return _receipt(
            request, TeacherMenuExit.FAILED, "Class creation incomplete.", durability
        )
    except ClassCreationError:
        print("Class creation refused; review current classroom state.", file=error_output)
        return _receipt(request, TeacherMenuExit.FAILED, "Class creation refused.")
    print("Class creation committed.", file=output)
    return _receipt(
        request, TeacherMenuExit.BACK, "Class metadata committed.",
        TeacherDurability.COMMITTED,
    )
