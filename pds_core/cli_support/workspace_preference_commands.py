"""Script-safe workspace-preference preview/commit CLI for Core #242.

This command family manages the *user's saved preference*, not the selected
workspace data root. It performs no prompts and never bypasses C2A guards.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TextIO

from pds_core.classroom_workspace_commit import (
    GuardedWorkspacePreferencePreview,
    WorkspacePreferenceCommitError,
    WorkspacePreferenceCommitResult,
    WorkspacePreferenceConflictError,
    WorkspacePreferenceWriteError,
    commit_guarded_workspace_preference_change,
    plan_guarded_workspace_preference_change,
)
from pds_core.classroom_workspace_preference import (
    WorkspacePreferenceChange,
    WorkspacePreferencePlanError,
)
from pds_core.standards import StandardsLibrary
from pds_core.workspace import WorkspaceRootError

EXIT_OK = 0
EXIT_INPUT = 2
EXIT_STALE = 4
EXIT_STORAGE = 5
EXIT_WRITE = 6
EXIT_UNCERTAIN = 7

_MESSAGES = {
    "invalid_action": "Workspace preference operation is invalid.",
    "invalid_target": "Requested workspace destination is invalid.",
    "unwritable_target": "Requested workspace destination is not writable.",
    "invalid_config": "Saved workspace preference cannot be validated.",
    "redirected_config": "Saved workspace preference is redirected.",
    "oversized_config": "Saved workspace preference exceeds its review limit.",
    "unreadable_config": "Saved workspace preference cannot be inspected.",
    "stale_config": "Preference changed while previewing; preview again.",
    "invalid_default": "Default workspace destination is invalid.",
    "invalid_token": "Reviewed workspace state token is invalid.",
    "invalid_change": "Workspace preference change is invalid.",
    "not_confirmed": "Explicit --confirm is required.",
    "current_state_changed": "Saved preference changed; preview again.",
    "candidate_changed": "Proposed preference differs from reviewed change.",
    "write_conflict": "Another guarded preference writer is active.",
    "unsafe_path": "Preference configuration path is redirected.",
    "path_unavailable": "Preference configuration path cannot be inspected.",
    "lock_failed": "Preference write coordination failed.",
    "write_outcome_uncertain": (
        "Write outcome uncertain; inspect saved preference before retrying."
    ),
    "explicit_workspace": (
        "Do not use --workspace for a user-wide saved preference operation."
    ),
    "write_failed": "Workspace preference could not be saved.",
    "unavailable": "Workspace preference operation is unavailable.",
}


def _path(value: Path | None) -> str | None:
    return None if value is None else str(value)


def _emit(
    args: argparse.Namespace,
    command: str,
    *,
    data: dict[str, object],
    stdout: TextIO,
    stderr: TextIO,
    reason: str | None = None,
    exit_code: int = EXIT_OK,
) -> int:
    ok = reason is None
    if args.format == "json":
        payload: dict[str, object] = {
            "schema_version": "1",
            "command": command,
            "scope": "user_workspace_preference",
            "ok": ok,
            "data": data if ok else {},
        }
        if reason is not None:
            payload["error"] = {
                "code": f"workspace_preference.{reason}",
                "message": _MESSAGES[reason],
            }
        print(
            json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False),
            file=stdout,
        )
    elif reason is not None:
        print(
            f"Error [workspace_preference.{reason}]: {_MESSAGES[reason]}",
            file=stderr,
        )
    return exit_code


def _change(args: argparse.Namespace) -> WorkspacePreferenceChange:
    if args.workspace is not None:
        raise WorkspacePreferenceCommitError(
            "explicit_workspace",
            "User preference commands do not accept --workspace.",
        )
    action = args.preference_action
    if action == "set":
        return WorkspacePreferenceChange("set", args.path)
    if action == "reset":
        return WorkspacePreferenceChange("reset")
    raise WorkspacePreferenceCommitError(
        "invalid_action", "Workspace preference operation is invalid."
    )


def _preview_data(review: GuardedWorkspacePreferencePreview) -> dict[str, object]:
    proposal = review.proposal
    return {
        "operation": proposal.operation,
        "previous_saved_root": _path(proposal.previous_saved_root),
        "proposed_saved_root": _path(proposal.proposed_saved_root),
        "current_effective_root": str(proposal.current_effective_root),
        "proposed_effective_root": str(proposal.proposed_effective_root),
        "current_resolution_source": proposal.current_resolution_source,
        "environment_override_active": proposal.environment_override_active,
        "target_exists": proposal.target_exists,
        "target_would_be_created": proposal.target_would_be_created,
        "no_change": proposal.no_change,
        "current_state_token": review.current_state_token,
        "candidate_state_token": review.candidate_state_token,
        "saved": False,
    }


def _commit_data(result: WorkspacePreferenceCommitResult) -> dict[str, object]:
    return {
        "operation": result.operation,
        "status": result.outcome,
        "previous_saved_root": _path(result.previous_saved_root),
        "saved_root": _path(result.saved_root),
        "previous_state_token": result.previous_state_token,
        "committed_state_token": result.committed_state_token,
    }


def _preview_text(data: dict[str, object], stdout: TextIO) -> None:
    print("Workspace preference change preview", file=stdout)
    print(f"Operation: {data['operation']}", file=stdout)
    print(f"Saved before: {data['previous_saved_root'] or '(none)'}", file=stdout)
    print(f"Saved after: {data['proposed_saved_root'] or '(none)'}", file=stdout)
    print(f"Effective before: {data['current_effective_root']}", file=stdout)
    print(f"Effective after: {data['proposed_effective_root']}", file=stdout)
    print(f"Resolution source: {data['current_resolution_source']}", file=stdout)
    if data["environment_override_active"]:
        print("Environment override remains effective.", file=stdout)
    if data["target_would_be_created"]:
        print("Target workspace would be initialized on commit.", file=stdout)
    if data["no_change"]:
        print("Status: NO CHANGE REQUIRED", file=stdout)
    print(f"Current state token: {data['current_state_token']}", file=stdout)
    print(f"Candidate state token: {data['candidate_state_token']}", file=stdout)
    print("Status: PREVIEW ONLY - NO WRITE", file=stdout)


def _commit_text(data: dict[str, object], stdout: TextIO) -> None:
    print("Workspace preference commit result", file=stdout)
    print(f"Operation: {data['operation']}", file=stdout)
    print(f"Saved before: {data['previous_saved_root'] or '(none)'}", file=stdout)
    print(f"Saved after: {data['saved_root'] or '(none)'}", file=stdout)
    print(f"Previous token: {data['previous_state_token']}", file=stdout)
    print(f"Committed token: {data['committed_state_token']}", file=stdout)
    print(f"Status: {str(data['status']).upper()}", file=stdout)
    print(
        "Reload workspace, school year, class and work before continuing.",
        file=stdout,
    )


def _failure(
    args: argparse.Namespace,
    command: str,
    error: BaseException,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    if isinstance(error, WorkspacePreferenceConflictError):
        status = EXIT_STALE
        reason = error.reason
    elif isinstance(error, WorkspacePreferenceWriteError):
        reason = error.reason
        status = EXIT_UNCERTAIN if reason == "write_outcome_uncertain" else EXIT_WRITE
    elif isinstance(
        error, (WorkspacePreferenceCommitError, WorkspacePreferencePlanError)
    ):
        reason = error.reason
        if reason in {
            "invalid_token",
            "invalid_change",
            "not_confirmed",
            "invalid_action",
            "explicit_workspace",
            "invalid_target",
            "unwritable_target",
        }:
            status = EXIT_INPUT
        elif reason == "stale_config":
            status = EXIT_STALE
        else:
            status = EXIT_STORAGE
    elif isinstance(error, ValueError):
        reason = "invalid_action"
        status = EXIT_INPUT
    else:
        reason = "unavailable"
        status = EXIT_STORAGE
    if reason not in _MESSAGES:
        reason, status = "unavailable", EXIT_STORAGE
    return _emit(
        args,
        command,
        data={},
        stdout=stdout,
        stderr=stderr,
        reason=reason,
        exit_code=status,
    )


def handle_workspace_preference_preview(
    args: argparse.Namespace,
    _library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Strictly read-only preview; never prompt or mutate user config."""
    command = "workspace preference-preview"
    try:
        change = _change(args)
        review = plan_guarded_workspace_preference_change(change)
    except (
        WorkspacePreferenceCommitError,
        WorkspacePreferencePlanError,
        WorkspaceRootError,
        ValueError,
    ) as error:
        return _failure(args, command, error, stdout, stderr)
    data = _preview_data(review)
    if args.format != "json":
        _preview_text(data, stdout)
    return _emit(args, command, data=data, stdout=stdout, stderr=stderr)


def handle_workspace_preference_commit(
    args: argparse.Namespace,
    _library: StandardsLibrary,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Guarded noninteractive commit requiring exact tokens and --confirm."""
    command = "workspace preference-commit"
    try:
        change = _change(args)
        outcome = commit_guarded_workspace_preference_change(
            change,
            expected_current_state_token=args.expected_current_state_token,
            expected_candidate_state_token=args.expected_candidate_state_token,
            confirmed=args.confirm,
        )
    except (
        WorkspacePreferenceCommitError,
        WorkspacePreferencePlanError,
        WorkspaceRootError,
        ValueError,
    ) as error:
        return _failure(args, command, error, stdout, stderr)
    data = _commit_data(outcome)
    if args.format != "json":
        _commit_text(data, stdout)
    return _emit(args, command, data=data, stdout=stdout, stderr=stderr)
