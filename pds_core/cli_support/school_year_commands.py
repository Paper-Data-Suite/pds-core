"""Script-safe Core #242 school-year review and commit commands."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import TextIO

from pds_core.classroom_admin_preview import SchoolYearChange
from pds_core.classroom_school_year_commit import (
    GuardedSchoolYearReview,
    SchoolYearCommitError,
    SchoolYearCommitResult,
    SchoolYearConflictError,
    SchoolYearWriteError,
    commit_guarded_school_year_change,
    plan_guarded_school_year_change,
)
from pds_core.standards import StandardsLibrary

EXIT_OK = 0
EXIT_INPUT = 2
EXIT_STALE = 4
EXIT_STORAGE = 5
EXIT_WRITE = 6
EXIT_UNCERTAIN = 7

_MESSAGES = {
    "not_confirmed": "Explicit --confirm is required.",
    "invalid_change": "School-year action is invalid.",
    "invalid_timestamp": "A valid offset-aware timestamp is required.",
    "invalid_token": "A reviewed school-year token is invalid.",
    "current_state_changed": "School-year state changed; preview again.",
    "candidate_changed": "School-year proposal differs from its preview.",
    "write_conflict": "Another local school-year writer is active.",
    "active_year_conflict": "Another school year is already open.",
    "year_history_policy_required": "Closed-year history cannot be overwritten.",
    "class_history_policy_required": "Existing classes require historical review.",
    "no_open_year": "There is no active school year to close.",
    "stale_year_state": "School-year state changed during review.",
    "invalid_year_state": "Canonical school-year state is invalid.",
    "oversized_year_state": "School-year record exceeds the review limit.",
    "unavailable_year_state": "School-year state cannot be inspected.",
    "unsafe_path": "A canonical classroom path is redirected.",
    "unavailable_path": "A canonical classroom path is unavailable.",
    "invalid_workspace": "Selected workspace is invalid.",
    "missing_workspace": "An existing workspace is required.",
    "lock_failed": "Local school-year write coordination failed.",
    "write_outcome_uncertain": (
        "School-year write outcome uncertain; inspect state before retrying."
    ),
    "unavailable": "School-year operation is unavailable.",
}
_INPUT = {"not_confirmed", "invalid_change", "invalid_timestamp", "invalid_token"}
_STALE = {
    "current_state_changed",
    "candidate_changed",
    "write_conflict",
    "active_year_conflict",
    "year_history_policy_required",
    "class_history_policy_required",
    "no_open_year",
    "stale_year_state",
}


def _change(args: argparse.Namespace) -> SchoolYearChange:
    if args.year_action == "open":
        return SchoolYearChange("open", args.year)
    if args.year_action == "close":
        return SchoolYearChange("close")
    raise SchoolYearCommitError("invalid_change", "Invalid school-year action.")


def _preview_data(review: GuardedSchoolYearReview) -> dict[str, object]:
    plan = review.proposal
    return {
        "operation": plan.action,
        "workspace_root": str(plan.workspace_root),
        "previous_record_status": plan.previous_record_status,
        "previous_school_year": plan.previous_school_year,
        "proposed_active_year": plan.proposed_active_year,
        "effective_at": review.effective_at.isoformat(),
        "no_change": plan.no_change,
        "current_state_token": review.current_state_token,
        "candidate_state_token": review.candidate_state_token,
        "saved": False,
    }


def _commit_data(
    root: Path, at: datetime, result: SchoolYearCommitResult
) -> dict[str, object]:
    return {
        "operation": result.action,
        "workspace_root": str(root),
        "effective_at": at.isoformat(),
        "status": result.outcome,
        "previous_school_year": result.previous_school_year,
        "active_school_year": result.active_school_year,
        "previous_state_token": result.previous_state_token,
        "committed_state_token": result.committed_state_token,
        "changed_scopes": ["SCHOOL_YEAR"] if result.outcome == "committed" else [],
    }


def _emit(
    args: argparse.Namespace,
    command: str,
    data: dict[str, object],
    stdout: TextIO,
    stderr: TextIO,
    *,
    reason: str | None = None,
    exit_code: int = EXIT_OK,
) -> int:
    if args.format == "json":
        payload: dict[str, object] = {
            "schema_version": "1",
            "command": command,
            "scope": "school_year",
            "ok": reason is None,
            "data": data if reason is None else {},
        }
        if reason is not None:
            payload["error"] = {
                "code": f"school_year.{reason}",
                "message": _MESSAGES[reason],
            }
        print(json.dumps(payload, ensure_ascii=True, sort_keys=True), file=stdout)
    elif reason is not None:
        print(f"Error [school_year.{reason}]: {_MESSAGES[reason]}", file=stderr)
    return exit_code


def _failure(
    args: argparse.Namespace,
    command: str,
    error: SchoolYearCommitError,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    reason = error.reason if error.reason in _MESSAGES else "unavailable"
    if isinstance(error, SchoolYearWriteError):
        code = EXIT_UNCERTAIN if reason == "write_outcome_uncertain" else EXIT_WRITE
    elif isinstance(error, SchoolYearConflictError) or reason in _STALE:
        code = EXIT_STALE
    elif reason in _INPUT:
        code = EXIT_INPUT
    else:
        code = EXIT_STORAGE
    return _emit(args, command, {}, stdout, stderr, reason=reason, exit_code=code)


def _display(data: dict[str, object], *, preview: bool, stdout: TextIO) -> None:
    kind = "preview" if preview else "result"
    print(f"School-year transition {kind}", file=stdout)
    root = json.dumps(str(data["workspace_root"]), ensure_ascii=True)
    print(f"Workspace: {root}", file=stdout)
    print(f"Operation: {data['operation']}", file=stdout)
    if preview:
        print(f"Previous state: {data['previous_record_status']}", file=stdout)
        print(f"Prior year: {data['previous_school_year'] or '(none)'}", file=stdout)
        print(f"Proposed year: {data['proposed_active_year'] or '(none)'}", file=stdout)
        print(f"Current state token: {data['current_state_token']}", file=stdout)
        print(f"Candidate state token: {data['candidate_state_token']}", file=stdout)
        if data["no_change"]:
            print("Status: NO CHANGE REQUIRED", file=stdout)
        print("Status: PREVIEW ONLY - NO WRITE", file=stdout)
    else:
        print(f"Previous year: {data['previous_school_year'] or '(none)'}", file=stdout)
        print(f"Active year: {data['active_school_year'] or '(none)'}", file=stdout)
        print(f"Status: {str(data['status']).upper()}", file=stdout)
        print("Reload workspace, school year, class, roster and work.", file=stdout)
    print(f"Effective timestamp: {data['effective_at']}", file=stdout)


def handle_year_preview(
    args: argparse.Namespace,
    _library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    command = "workspace year-preview"
    try:
        review = plan_guarded_school_year_change(
            args.workspace_root, _change(args), effective_at=args.effective_at
        )
    except SchoolYearCommitError as error:
        return _failure(args, command, error, stdout, stderr)
    data = _preview_data(review)
    if args.format != "json":
        _display(data, preview=True, stdout=stdout)
    return _emit(args, command, data, stdout, stderr)


def handle_year_commit(
    args: argparse.Namespace,
    _library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    command = "workspace year-commit"
    try:
        result = commit_guarded_school_year_change(
            args.workspace_root,
            _change(args),
            effective_at=args.effective_at,
            expected_current_state_token=args.expected_current_state_token,
            expected_candidate_state_token=args.expected_candidate_state_token,
            confirmed=args.confirm,
        )
    except SchoolYearCommitError as error:
        return _failure(args, command, error, stdout, stderr)
    data = _commit_data(args.workspace_root, args.effective_at, result)
    if args.format != "json":
        _display(data, preview=False, stdout=stdout)
    return _emit(args, command, data, stdout, stderr)
