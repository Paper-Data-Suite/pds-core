"""C3A staged, guarded teacher workflow for saved workspace preferences.

Accessible only through the private Core #242 qualification menu switch.
The public callable menu remains UNAVAILABLE until integrated acceptance.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from pds_core.classroom_menu_outcome import _outcome_notice

from pds_core.classroom_workspace_commit import (
    GuardedWorkspacePreferencePreview,
    WorkspacePreferenceCommitError,
    WorkspacePreferenceConflictError,
    WorkspacePreferenceWriteError,
    commit_guarded_workspace_preference_change,
    plan_guarded_workspace_preference_change,
)
from pds_core.classroom_workspace_preference import (
    WorkspacePreferenceChange,
    WorkspacePreferencePlanError,
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


def _display_path(value: Path | None) -> str:
    if value is None:
        return "(none)"
    return "".join(
        char
        if not unicodedata.category(char).startswith("C")
        and unicodedata.category(char) not in {"Zl", "Zp"}
        else "\ufffd"
        for char in str(value)
    )


def _receipt(
    request: SharedTeacherMenuRequest,
    exit_kind: TeacherMenuExit,
    durability: TeacherDurability = TeacherDurability.NO_CHANGE,
    message: str = "Returned without a preference change.",
) -> SharedTeacherMenuResult:
    scopes = (
        frozenset({TeacherChangeScope.WORKSPACE})
        if durability is not TeacherDurability.NO_CHANGE
        else frozenset()
    )
    return SharedTeacherMenuResult(
        return_token=request.return_token,
        exit=exit_kind,
        durability=durability,
        change_scopes=scopes,
        message=f"{message} {_REVALIDATE}",
    )


def _read(read_line: Callable[[], str]) -> str | None:
    try:
        value = read_line()
    except (EOFError, StopIteration, KeyboardInterrupt):
        return None
    if type(value) is not str or value == "":
        return None
    return value.strip()


def _navigation(
    raw: str, request: SharedTeacherMenuRequest
) -> SharedTeacherMenuResult | None:
    if raw.casefold() == "m":
        return _receipt(request, TeacherMenuExit.MAIN_MENU)
    if raw.casefold() == "q":
        return _receipt(request, TeacherMenuExit.QUIT)
    return None


def _header(request: SharedTeacherMenuRequest, title: str, output: TextIO) -> None:
    screen.clear_screen(output)
    print_teacher_header(
        TeacherScreenHeader("PDS Core", title, request.context.display_label),
        output=output,
        color="never",
    )
    print("Saved preference only. Existing workspace files are not moved.", file=output)


def _show_actions(request: SharedTeacherMenuRequest, output: TextIO) -> None:
    _header(request, "Workspace preference management", output)
    print("1. Review a new saved workspace root", file=output)
    print("2. Review clearing the saved preference", file=output)
    print("B. Back   M. Caller Main Menu   Q. Quit", file=output)
    print("Choose an option: ", end="", file=output, flush=True)


def _show_review(
    request: SharedTeacherMenuRequest,
    review: GuardedWorkspacePreferencePreview,
    output: TextIO,
) -> None:
    plan = review.proposal
    _header(request, "Review workspace preference", output)
    print(f"Operation: {plan.operation}", file=output)
    print(
        f"Saved preference before: {_display_path(plan.previous_saved_root)}",
        file=output,
    )
    print(
        f"Saved preference after: {_display_path(plan.proposed_saved_root)}",
        file=output,
    )
    print(
        f"Effective workspace now: {_display_path(plan.current_effective_root)}",
        file=output,
    )
    print(
        f"Effective workspace after: {_display_path(plan.proposed_effective_root)}",
        file=output,
    )
    if plan.environment_override_active:
        print("Environment override remains in effect.", file=output)
    if plan.target_would_be_created:
        print("Selected workspace would be initialized on commit.", file=output)
    if plan.no_change:
        print("Saved preference already matches this proposal.", file=output)
    print("PREVIEW ONLY — nothing has been saved.", file=output)
    print("C. Confirm this exact change", file=output)
    print("B. Cancel review   M. Caller Main Menu   Q. Quit", file=output)
    print("Choose an option: ", end="", file=output, flush=True)


def _refusal(
    request: SharedTeacherMenuRequest,
    error: Exception,
    stderr: TextIO,
) -> SharedTeacherMenuResult:
    if isinstance(error, WorkspacePreferenceWriteError):
        if error.reason == "write_outcome_uncertain":
            _outcome_notice("Write outcome uncertain; inspect before retrying.", file=stderr)
            return _receipt(
                request,
                TeacherMenuExit.FAILED,
                TeacherDurability.INDETERMINATE,
                "Saved workspace preference write outcome uncertain.",
            )
        _outcome_notice("Workspace preference write could not proceed.", file=stderr)
    elif isinstance(error, WorkspacePreferenceConflictError):
        _outcome_notice("Workspace preference changed; review it again.", file=stderr)
    else:
        _outcome_notice("Workspace preference request failed safely.", file=stderr)
    return _receipt(
        request,
        TeacherMenuExit.FAILED,
        message="Workspace preference operation refused.",
    )


def run_workspace_preference_review(
    request: SharedTeacherMenuRequest,
    *,
    read_line: Callable[[], str],
    output: TextIO,
    error_output: TextIO,
) -> SharedTeacherMenuResult | None:
    """Return None only when B returns to the parent menu without a write."""
    while True:
        _show_actions(request, output)
        response = _read(read_line)
        if response is None:
            return _receipt(request, TeacherMenuExit.CANCELLED)
        navigation = _navigation(response, request)
        if navigation is not None:
            return navigation
        if response.casefold() == "b":
            return None
        if response == "1":
            _header(request, "Select saved workspace root", output)
            print("Enter a workspace folder, or B to cancel:", file=output)
            print("Path: ", end="", file=output, flush=True)
            destination = _read(read_line)
            if destination is None:
                return _receipt(request, TeacherMenuExit.CANCELLED)
            navigation = _navigation(destination, request)
            if navigation is not None:
                return navigation
            if destination.casefold() == "b":
                continue
            if not destination or len(destination) > 1024:
                print("Enter a valid path of at most 1024 characters.", file=output)
                continue
            change = WorkspacePreferenceChange("set", destination)
        elif response == "2":
            change = WorkspacePreferenceChange("reset")
        else:
            print("Choose 1, 2, B, M or Q.", file=output)
            continue

        try:
            review = plan_guarded_workspace_preference_change(change)
        except (WorkspacePreferencePlanError, ValueError, TypeError) as error:
            return _refusal(request, error, error_output)
        _show_review(request, review, output)
        answer = _read(read_line)
        if answer is None:
            return _receipt(request, TeacherMenuExit.CANCELLED)
        navigation = _navigation(answer, request)
        if navigation is not None:
            return navigation
        if answer.casefold() == "b":
            continue
        if answer.casefold() != "c":
            print("Not confirmed. Returning to preference choices.", file=output)
            continue
        try:
            result = commit_guarded_workspace_preference_change(
                change,
                expected_current_state_token=review.current_state_token,
                expected_candidate_state_token=review.candidate_state_token,
                confirmed=True,
            )
        except WorkspacePreferenceCommitError as error:
            return _refusal(request, error, error_output)
        if result.outcome == "committed":
            _outcome_notice("Saved workspace preference changed.", file=output)
            return _receipt(
                request,
                TeacherMenuExit.BACK,
                TeacherDurability.COMMITTED,
                "Saved workspace preference committed.",
            )
        _outcome_notice("Saved workspace preference already matches.", file=output)
        return _receipt(
            request,
            TeacherMenuExit.BACK,
            message="Saved workspace preference was already current.",
        )
